#!/usr/bin/env python3
"""
prepare.py — Daily Instagram/Facebook Post Preparation for @examsfiles

Usage:
    python prepare.py              Normal mode: process images, post & schedule
    python prepare.py --dry-run    Preview captions without posting anything
    python prepare.py --status     Show status of current queue

Flow:
    1. Scans 'bite upload' folder for images
    2. Extracts topic from filename → generates caption with Gemini AI (text-only, no image upload)
    3. Uploads images to imgbb for public URLs
    4. Posts first 2 images to Instagram immediately
    5. Schedules all 20 to Facebook Page (server-side)
    6. Creates Instagram containers for remaining 18
    7. Pushes queue to GitHub for automated hourly publishing
    8. Moves all processed images to 'uploaded exam' folder
"""

import os
import sys
import json
import time
import base64
import re
import shutil
import argparse
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------
try:
    import requests
except ImportError as e:
    print(f"❌ Missing dependency: {e}")
    print("   Run: pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
import os
git_exe = str(SCRIPT_DIR / "git_portable" / "cmd" / "git.exe") if os.name == "nt" else "git"

CONFIG_PATH = SCRIPT_DIR / "config.json"
QUEUE_PATH = SCRIPT_DIR / "queue.json"
LOG_PATH = SCRIPT_DIR / "post_log.json"

# Indian Standard Time (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# Caption prompt — user's clean format with [TOPIC] placeholder
# ---------------------------------------------------------------------------
CAPTION_PROMPT_TEMPLATE = """Generate an Instagram educational caption on {topic} in the exact format below:

- Start with a short title + relevant emoji.
- Write a 2–3 sentence introduction explaining the topic.
- Add 6 concise bullet points covering the most important aspects (definition, types, features, functions, importance, challenges, examples, or related concepts—whichever fits the topic).
- Keep the content factually accurate, exam-oriented, and suitable for UPSC/SSC/School/Competitive exams.
- End with a short list of relevant target audiences (e.g., UPSC, SSC, Indian Polity, Geography, etc.).
- After the audience list, add the channel name: examsfiles
- After the channel name, add: Exams Files notes
- Finish with 8–10 relevant hashtags, always ending with #examsfiles
- Do not use tables, markdown headings, or unnecessary emojis. Keep the caption clean, informative, and easy to read.
- Do NOT wrap the output in markdown code blocks or quotes.
- Total caption MUST be under 2200 characters.
- Output ONLY the caption text, nothing else."""


# ═══════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS — Crash-safe, power-cut resilient
# ═══════════════════════════════════════════════════════════════════════════

def atomic_write_json(filepath: Path, data: dict):
    """
    Write JSON atomically: write to .tmp, flush, fsync, then rename.
    On NTFS (Windows), os.replace() is atomic — if power cuts during write,
    the original file remains intact.
    """
    filepath = Path(filepath)
    tmp_path = filepath.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp_path), str(filepath))


def load_json(filepath: Path, default=None):
    """Load JSON file safely; return default if missing or corrupt."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def load_config() -> dict:
    """Load and validate config.json."""
    if os.environ.get("GITHUB_ACTIONS"):
        return {
            "meta": {
                "user_access_token": os.environ.get("META_USER_ACCESS_TOKEN", ""),
                "page_access_token": os.environ.get("META_PAGE_ACCESS_TOKEN", ""),
                "ig_user_id": os.environ.get("META_IG_USER_ID", ""),
                "page_id": os.environ.get("META_PAGE_ID", ""),
            },
            "groq": {
                "api_key": os.environ.get("GROQ_API_KEY", "")
            },
            "gemini": {
                "api_key": os.environ.get("GEMINI_API_KEY", "")
            },
            "imgbb": {
                "api_key": os.environ.get("IMGBB_API_KEY", "")
            },
            "settings": {
                "posts_per_day": 15,
                "hour_gap": 0.75,
                "immediate_posts": 2,
                "facebook_enabled": False
            }
        }

    if not CONFIG_PATH.exists():
        print("❌ config.json not found!")
        print(f"   Copy config.example.json → config.json and fill in your API keys.")
        print(f"   Expected at: {CONFIG_PATH}")
        sys.exit(1)

    config = load_json(CONFIG_PATH)

    required_keys = [
        ("meta", "user_access_token"),
        ("meta", "page_access_token"),
        ("meta", "ig_user_id"),
        ("meta", "page_id"),
        ("imgbb", "api_key"),
    ]
    for section, key in required_keys:
        value = config.get(section, {}).get(key, "")
        if (not value or "PASTE" in value.upper()) and key != "page_id" and key != "page_access_token":
            print(f"❌ Missing or placeholder value: {section}.{key}")
            print(f"   Open config.json and set a real value.")
            sys.exit(1)
            
    # Check for AI API key (Gemini OR Groq)
    gemini_key = config.get("gemini", {}).get("api_key", "")
    groq_key = config.get("groq", {}).get("api_key", "")
    if (not gemini_key or "PASTE" in gemini_key.upper()) and (not groq_key or "PASTE" in groq_key.upper()):
        print(f"❌ Missing AI API key: Please set either groq.api_key or gemini.api_key.")
        sys.exit(1)

    return config


def extract_topic_from_filename(filepath: Path) -> str:
    """
    Extract a human-readable topic from the image filename.

    Examples:
        0001_Dimensional_Analysis.png      → "Dimensional Analysis"
        0023_Women_Empowerment_Gender.jpg  → "Women Empowerment Gender"
        Fundamental_Rights.png             → "Fundamental Rights"
        42-Indian_Economy_Overview.jpeg     → "Indian Economy Overview"
    """
    name = filepath.stem  # filename without extension

    # Remove leading numeric codes and separators (e.g., "0001_", "42-", "023_")
    name = re.sub(r"^[\d]+[_\-\s]*", "", name)

    # Replace underscores, hyphens, and multiple spaces with single space
    name = re.sub(r"[_\-]+", " ", name)

    # Clean up extra whitespace
    name = name.strip()

    if not name:
        name = filepath.stem  # Fallback to full stem if nothing left

    return name


def append_log(entry: dict):
    """Append a post-log entry to post_log.json."""
    log = load_json(LOG_PATH, [])
    if not isinstance(log, list):
        log = []
    log.append(entry)
    atomic_write_json(LOG_PATH, log)


# ═══════════════════════════════════════════════════════════════════════════
# IMAGE SCANNING
# ═══════════════════════════════════════════════════════════════════════════

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def scan_images(folder: Path) -> list[Path]:
    """Return sorted list of image files in the folder."""
    if not folder.exists():
        print(f"❌ Image folder not found: {folder}")
        sys.exit(1)
    images = sorted(
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    )
    return images


# ═══════════════════════════════════════════════════════════════════════════
# GEMINI AI — Text-Only Caption Generation (no image upload = saves tokens)
# ═══════════════════════════════════════════════════════════════════════════

def generate_caption(image_path: Path, config: dict) -> str:
    """
    Generate caption using Groq AI.
    Topic is extracted from the filename.
    """
    topic = extract_topic_from_filename(image_path)
    prompt = CAPTION_PROMPT_TEMPLATE.format(topic=topic) + "\n\nCRITICAL RULE: DO NOT mention that you are an AI. DO NOT mention \"Gemini Generated Image\" or talk about image generation. Output ONLY the educational caption based on the real topic!"
    
    api_key = config.get("groq", {}).get("api_key")
    if not api_key:
        raise ValueError("No Groq API key found in config")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 2048
    }

    max_retries = 3
    import time
    import requests
    for attempt in range(max_retries):
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
        if response.status_code == 429:
            time.sleep((attempt + 1) * 3)  # exponential backoff
            continue
        response.raise_for_status()
        break
    else:
        response.raise_for_status()
    
    try:
        caption = response.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        caption = response.text.strip()

    # Strip markdown code fences if the model wraps its output
    if caption.startswith("```"):
        lines = caption.split("\n")
        if lines[-1].strip() == "```":
            caption = "\n".join(lines[1:-1]).strip()
            if caption.lower().startswith("text\n") or caption.lower().startswith("markdown\n"):
                caption = caption[caption.find("\n")+1:].strip()

    return caption


# ═══════════════════════════════════════════════════════════════════════════
# imgbb — Image Hosting
# ═══════════════════════════════════════════════════════════════════════════

def upload_to_imgbb(image_path: Path, api_key: str) -> str:
    """Upload image to imgbb; return the public URL. Automatically converts PNGs to JPEGs to prevent Facebook Graph API errors."""
    try:
        from PIL import Image
    except ImportError:
        Image = None

    temp_path = None
    upload_path = image_path
    if image_path.suffix.lower() == ".png" and Image:
        try:
            img = Image.open(image_path)
            img = img.convert("RGB")
            temp_path = image_path.with_suffix(".jpg")
            img.save(temp_path, "JPEG", quality=90)
            upload_path = temp_path
        except Exception as e:
            print(f"⚠️ Failed to convert/pad PNG to JPEG, proceeding with original. Error: {e}")

    with open(upload_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    if temp_path and temp_path.exists():
        try:
            os.remove(temp_path)
        except Exception:
            pass

    resp = requests.post(
        "https://api.imgbb.com/1/upload",
        data={
            "key": api_key,
            "image": image_b64,
            "name": image_path.stem,
        },
        timeout=120,
    )
    resp.raise_for_status()
    result = resp.json()

    if not result.get("success"):
        raise RuntimeError(f"imgbb upload failed: {result}")

    return result["data"]["url"]


# ═══════════════════════════════════════════════════════════════════════════
# INSTAGRAM GRAPH API
# ═══════════════════════════════════════════════════════════════════════════

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


def create_ig_container(image_url: str, caption: str, config: dict) -> str:
    """Create an Instagram media container (stored on Meta's servers)."""
    url = f"{GRAPH_API_BASE}/{config['meta']['ig_user_id']}/media"
    resp = requests.post(url, data={
        "image_url": image_url,
        "caption": caption,
        "access_token": config["meta"]["user_access_token"],
    }, timeout=60)
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"   ❌ IG Container Error: {resp.text}")
        raise e
    return resp.json()["id"]


def check_container_status(container_id: str, config: dict) -> str:
    """Poll the status of an Instagram media container."""
    url = f"{GRAPH_API_BASE}/{container_id}"
    resp = requests.get(url, params={
        "fields": "status_code",
        "access_token": config["meta"]["user_access_token"],
    }, timeout=30)
    resp.raise_for_status()
    return resp.json().get("status_code", "UNKNOWN")


def wait_for_container(container_id: str, config: dict, max_wait: int = 180):
    """Block until the container is FINISHED or raise on timeout / error."""
    waited = 0
    interval = 5
    while waited < max_wait:
        status = check_container_status(container_id, config)
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(
                f"Instagram container {container_id} reached ERROR status. "
                "The image may be invalid or the URL may have expired."
            )
        time.sleep(interval)
        waited += interval
    raise TimeoutError(
        f"Container {container_id} not ready after {max_wait}s (last status: {status})"
    )


def publish_ig_container(container_id: str, config: dict) -> str:
    """Publish a ready Instagram container and return the media ID."""
    wait_for_container(container_id, config)

    url = f"{GRAPH_API_BASE}/{config['meta']['ig_user_id']}/media_publish"
    resp = requests.post(url, data={
        "creation_id": container_id,
        "access_token": config["meta"]["user_access_token"],
    }, timeout=60)
    resp.raise_for_status()
    return resp.json()["id"]


# ═══════════════════════════════════════════════════════════════════════════
# FACEBOOK GRAPH API — Scheduled Page Posts
# ═══════════════════════════════════════════════════════════════════════════

def schedule_fb_post(
    image_url: str,
    caption: str,
    scheduled_time: datetime,
    config: dict,
) -> str:
    """Schedule a photo post on the Facebook Page for a future time."""
    unix_ts = int(scheduled_time.timestamp())

    # Facebook requires scheduled time ≥ 10 min in the future
    earliest = int((datetime.now(IST) + timedelta(minutes=11)).timestamp())
    if unix_ts < earliest:
        unix_ts = earliest

    url = f"{GRAPH_API_BASE}/{config['meta']['page_id']}/photos"
    resp = requests.post(url, data={
        "url": image_url,
        "message": caption,
        "scheduled_publish_time": unix_ts,
        "published": "false",
        "access_token": config["meta"]["page_access_token"],
    }, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data.get("id") or data.get("post_id", "unknown")


def post_fb_immediately(image_url: str, caption: str, config: dict) -> str:
    """Publish a photo to the Facebook Page immediately."""
    url = f"{GRAPH_API_BASE}/{config['meta']['page_id']}/photos"
    resp = requests.post(url, data={
        "url": image_url,
        "message": caption,
        "published": "true",
        "access_token": config["meta"]["page_access_token"],
    }, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data.get("id") or data.get("post_id", "unknown")


# ═══════════════════════════════════════════════════════════════════════════
# GIT — Push queue to GitHub for Actions
# ═══════════════════════════════════════════════════════════════════════════

def git_push_queue():
    """Commit and push queue.json + post_log.json to the GitHub repo."""
    if os.environ.get("GITHUB_ACTIONS"):
        print("   ℹ️  Skipping local git push (handled by GitHub Actions workflow)")
        return

    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    run_kw = dict(cwd=str(SCRIPT_DIR), capture_output=True, text=True, env=env)
    
    # Use portable Git
    import os

    try:
        subprocess.run([git_exe, "add", "queue.json"], check=True, **run_kw)
        if (SCRIPT_DIR / "post_log.json").exists():
            subprocess.run([git_exe, "add", "post_log.json"], check=True, **run_kw)
            
        if (SCRIPT_DIR / "exam upload").exists():
            subprocess.run([git_exe, "add", "exam upload/"], check=True, **run_kw)
        if (SCRIPT_DIR / "uploaded exam").exists():
            subprocess.run([git_exe, "add", "uploaded exam/"], check=True, **run_kw)
        
        result = subprocess.run(
            [git_exe, "commit", "-m",
             f"Queue update {datetime.now(IST).strftime('%Y-%m-%d %H:%M')}"],
            **run_kw,
        )
        if result.returncode != 0 and "nothing to commit" in (result.stdout + result.stderr):
            print("   ℹ️  No changes to commit.")
            return

        subprocess.run([git_exe, "push"], check=True, **run_kw)
        print("   ✅ Queue pushed to GitHub successfully")
    except FileNotFoundError:
        print("   ⚠️  git not found. Ensure git_portable is in the folder.")
    except subprocess.CalledProcessError as e:
        print(f"   ⚠️  Git operation failed:")
        if e.stderr:
            print(f"      {e.stderr.strip()}")
        print("   💡 You can push manually: cd insta-automation && git push")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN LOGIC
# ═══════════════════════════════════════════════════════════════════════════

def prepare(dry_run: bool = False):
    """
    Main preparation pipeline — designed to be crash-safe.
    Every step checkpoints progress to queue.json so that if the script is
    interrupted (power cut, crash), it resumes from the last completed step
    on the next run.
    """
    print("=" * 55)
    print("  📸 @examsfiles — Daily Post Preparation")
    print("=" * 55)

    if dry_run:
        print("  🧪 DRY RUN MODE — nothing will be posted or uploaded\n")

    # ------------------------------------------------------------------
    # Load config
    # ------------------------------------------------------------------
    config = load_config()
    settings = config.get("settings", {})

    image_folder = Path(settings.get("image_folder", r"C:\Users\Welcome\Pictures\bite upload"))
    uploaded_folder = Path(settings.get("uploaded_folder", r"C:\Users\Welcome\Pictures\uploaded exam"))
    
    is_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    if is_ci:
        print("☁️ Running in GitHub Actions (Cloud Vault Mode)")
        image_folder = SCRIPT_DIR / "exam upload"
        uploaded_folder = SCRIPT_DIR / "uploaded exam"
        image_folder.mkdir(parents=True, exist_ok=True)
        uploaded_folder.mkdir(parents=True, exist_ok=True)
    posts_per_day = int(settings.get("posts_per_day", 20))
    immediate_posts = int(settings.get("immediate_posts", 2))
    hour_gap = float(settings.get("hour_gap", 0.75))
    minute_gap = hour_gap * 60  # Convert hours to minutes (0.75h = 45 min)
    # Ensure the uploaded folder exists
    uploaded_folder.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Clean up yesterday's published images from GitHub storage
    # (Only runs in CI — clears 'uploaded exam/' before picking new images)
    # ------------------------------------------------------------------
    if is_ci and uploaded_folder.exists():
        old_files = [f for f in uploaded_folder.iterdir() if f.is_file()]
        if old_files:
            print(f"\n🧹 Cleaning {len(old_files)} previously published image(s) from '{uploaded_folder.name}/'...")
            for f in old_files:
                rel_path = str(f.relative_to(SCRIPT_DIR))
                subprocess.run([git_exe, "rm", "-f", "--ignore-unmatch", rel_path],
                               cwd=str(SCRIPT_DIR), capture_output=True)
            print(f"   ✅ Cleared {len(old_files)} old image(s) to free GitHub storage.")
        else:
            print("\n🧹 No old processed images to clean up.")

    # ------------------------------------------------------------------
    # Scan images
    # ------------------------------------------------------------------
    images = scan_images(image_folder)
    if not images:
        print("📭 No images found in the bite upload folder. Nothing to do.")
        return

    # ------------------------------------------------------------------
    # Load or create queue  (resume-safe)
    # ------------------------------------------------------------------
    queue = load_json(QUEUE_PATH, {"prepared_at": None, "posts": []})
    
    # Always start scheduling at exactly 8:30 AM IST for the current day
    start_time = datetime.now(IST).replace(hour=8, minute=30, second=0, microsecond=0)

    # REMOVE past failed posts from the queue so they can be recycled into today's quota
    # BUT only if they didn't already get scheduled on Facebook (to prevent double-posting)
    new_posts = []
    removed_count = 0
    for p in queue.get("posts", []):
        p_time = datetime.fromisoformat(p["scheduled_time"])
        is_past = p_time.date() < start_time.date()
        if is_past and not p.get("ig_published") and not p.get("fb_scheduled"):
            removed_count += 1
            continue
        new_posts.append(p)
    
    if removed_count > 0:
        print(f"🧹 Recycled {removed_count} failed posts from previous days back into the vault.")
        queue["posts"] = new_posts

    existing = {p["filename"] for p in queue.get("posts", [])}

    # Filter out images that are already in the queue BEFORE slicing
    images = [img for img in images if img.name not in existing]
    
    # Prevent adding new posts if we already prepared a batch today
    if queue.get("prepared_at"):
        try:
            last_prep = datetime.fromisoformat(queue["prepared_at"])
            if last_prep.date() == start_time.date():
                print("⚠️ Already queued posts for today! Skipping adding new posts, but will resume processing existing queue.")
                images = []
        except ValueError:
            pass

    if not images:
        print("📭 No new images to add right now.")
    else:
        images = images[:posts_per_day]
        print(f"\n📸 Found {len(images)} new image(s) to add\n")
        
    new_count = 0

    for idx, img_path in enumerate(images):
        if img_path.name in existing:
            continue  # Already queued from a previous (interrupted) run

        scheduled = start_time + timedelta(minutes=idx * minute_gap)
        queue["posts"].append({
            "index": idx,
            "filename": img_path.name,
            "image_path": str(img_path),
            "caption": None,
            "image_url": None,
            "ig_container_id": None,
            "ig_post_id": None,
            "ig_published": False,
            "fb_post_id": None,
            "fb_scheduled": False,
            "moved": False,
            "scheduled_time": scheduled.isoformat(),
        })
        new_count += 1

    if new_count > 0:
        queue["prepared_at"] = start_time.isoformat()
        atomic_write_json(QUEUE_PATH, queue)
        print(f"📋 Added {new_count} new image(s) to queue")

    if not queue["posts"]:
        print("📭 Queue is empty — nothing to process.")
        return

    # ------------------------------------------------------------------
    # Process each image through the pipeline
    # ------------------------------------------------------------------
    total = len(queue["posts"])

    for post in queue["posts"]:
        idx = post["index"]
        filename = post["filename"]
        img_path = Path(post["image_path"])
        tag = f"[{idx + 1}/{total}]"

        # STEP 1 — Generate caption with Gemini Vision
        if not post["caption"]:
            print(f"🤖 {tag} Generating caption for {filename} ...")
            if dry_run:
                post["caption"] = f"[DRY RUN] AI caption would appear here for {filename}"
            else:
                try:
                    post["caption"] = generate_caption(img_path, config)
                    time.sleep(2)  # Respect Gemini rate limits (15 RPM)
                except Exception as exc:
                    print(f"   ❌ Caption failed: {exc}")
                    print(f"   ⏩ Skipping {filename} for now — will retry on next run")
                    continue
            atomic_write_json(QUEUE_PATH, queue)  # Checkpoint ✓
            print(f"   ✅ Caption ready ({len(post['caption'])} chars)")

        # STEP 2 — Upload image to imgbb
        if not post["image_url"]:
            print(f"📤 {tag} Uploading {filename} to imgbb ...")
            if dry_run:
                post["image_url"] = f"https://dry-run.example.com/{filename}"
            else:
                try:
                    post["image_url"] = upload_to_imgbb(img_path, config["imgbb"]["api_key"])
                    time.sleep(10)  # Wait for ImgBB CDN to propagate before FB fetches it
                except Exception as exc:
                    print(f"   ❌ Upload failed: {exc}")
                    print(f"   ⏩ Skipping — will retry on next run")
                    continue
            atomic_write_json(QUEUE_PATH, queue)  # Checkpoint ✓
            print(f"   ✅ Uploaded → {post['image_url'][:60]}...")

        # STEP 3 — Create Instagram media container
        if not post["ig_container_id"]:
            print(f"📦 {tag} Creating Instagram container ...")
            if dry_run:
                post["ig_container_id"] = f"dry-run-container-{idx}"
            else:
                for attempt in range(3):
                    try:
                        post["ig_container_id"] = create_ig_container(
                            post["image_url"], post["caption"], config
                        )
                        time.sleep(2)
                        break
                    except Exception as exc:
                        if attempt < 2:
                            print(f"   ⚠️ IG container failed (CDN delay?), retrying in 15s... ({exc})")
                            time.sleep(15)
                        else:
                            print(f"   ❌ IG container failed permanently: {exc}")
                
                # If it failed all attempts, skip to next image
                if not post.get("ig_container_id"):
                    continue
            
            atomic_write_json(QUEUE_PATH, queue)  # Checkpoint ✓
            print(f"   ✅ Container → {post['ig_container_id']}")

        # STEP 4 — Schedule Facebook post (if page_id is configured)
        if not post["fb_scheduled"]:
            if not config["meta"].get("page_id"):
                post["fb_scheduled"] = True
                post["fb_post_id"] = "skipped"
                atomic_write_json(QUEUE_PATH, queue)
                print(f"   ⏭️  Facebook skipped (no page_id configured)")
                continue

            sched_dt = datetime.fromisoformat(post["scheduled_time"])
            print(f"📅 {tag} Scheduling Facebook post for {sched_dt.strftime('%I:%M %p')} ...")
            if dry_run:
                post["fb_scheduled"] = True
                post["fb_post_id"] = f"dry-run-fb-{idx}"
            else:
                try:
                    # First 2 posts go immediately on FB as well
                    if idx < immediate_posts:
                        fb_id = post_fb_immediately(
                            post["image_url"], post["caption"], config
                        )
                    else:
                        fb_id = schedule_fb_post(
                            post["image_url"], post["caption"], sched_dt, config
                        )
                    post["fb_post_id"] = fb_id
                    post["fb_scheduled"] = True
                    time.sleep(1)
                except Exception as exc:
                    print(f"   ❌ FB scheduling failed: {exc}")
                    # Mark true anyway so it doesn't block moving the image, or handle differently?
                    post["fb_scheduled"] = True
                    continue
            atomic_write_json(QUEUE_PATH, queue)  # Checkpoint ✓
            action = "Posted" if idx < immediate_posts else "Scheduled"
            print(f"   ✅ Facebook {action}")

    # ------------------------------------------------------------------
    # Publish first N images to Instagram IMMEDIATELY
    # ------------------------------------------------------------------
    published = sum(1 for p in queue["posts"] if p["ig_published"])
    for post in queue["posts"]:
        if published >= immediate_posts:
            break
        if post["ig_published"] or not post["ig_container_id"]:
            continue

        print(f"\n🚀 Publishing to Instagram NOW → {post['filename']}")
        if dry_run:
            post["ig_published"] = True
            post["ig_post_id"] = f"dry-run-ig-{post['index']}"
        else:
            try:
                ig_id = publish_ig_container(post["ig_container_id"], config)
                post["ig_published"] = True
                post["ig_post_id"] = ig_id
                append_log({
                    "platform": "instagram",
                    "filename": post["filename"],
                    "post_id": ig_id,
                    "timestamp": datetime.now(IST).isoformat(),
                })
                print(f"   ✅ LIVE on Instagram! Post ID: {ig_id}")
                time.sleep(3)
            except Exception as exc:
                print(f"   ❌ Publish failed: {exc}")
                continue

        published += 1
        atomic_write_json(QUEUE_PATH, queue)

    # ------------------------------------------------------------------
    # Move ALL fully-processed images to 'uploaded exam'
    # ------------------------------------------------------------------
    moved = 0
    for post in queue["posts"]:
        if post["moved"]:
            continue
        # Only move if both IG container and FB scheduling are done
        if not post["ig_container_id"] or not post["fb_scheduled"]:
            continue

        src = Path(post["image_path"])
        dst = uploaded_folder / post["filename"]
        uploaded_folder.mkdir(parents=True, exist_ok=True)

        if src.exists():
            if dry_run:
                print(f"📁 [DRY] Would move {post['filename']} → {uploaded_folder.name}/")
            else:
                try:
                    shutil.move(str(src), str(dst))
                    # In CI, we want to ensure git removes the file from vault/
                    if is_ci:
                        subprocess.run([git_exe, "rm", str(src)], cwd=str(SCRIPT_DIR), capture_output=True)
                except Exception as exc:
                    print(f"   ⚠️  Could not move {post['filename']}: {exc}")
                    continue
        post["moved"] = True
        moved += 1
    if moved:
        atomic_write_json(QUEUE_PATH, queue)
        print(f"\n📁 Moved {moved} image(s) to uploaded exam/")

    # ------------------------------------------------------------------
    # Push queue to GitHub so Actions can publish remaining IG posts
    # ------------------------------------------------------------------
    if not dry_run:
        print("\n📤 Pushing queue to GitHub ...")
        git_push_queue()

    # ------------------------------------------------------------------
    # Print summary
    # ------------------------------------------------------------------
    ig_done = sum(1 for p in queue["posts"] if p["ig_published"])
    ig_pend = sum(1 for p in queue["posts"] if p["ig_container_id"] and not p["ig_published"])
    fb_done = sum(1 for p in queue["posts"] if p["fb_scheduled"])

    print("\n" + "=" * 55)
    print("  📊 SUMMARY")
    print("=" * 55)
    print(f"  Total images processed :  {total}")
    print(f"  Instagram published    :  {ig_done}  (immediately)")
    print(f"  Instagram pending      :  {ig_pend}  (GitHub Actions hourly)")
    print(f"  Facebook posted/sched  :  {fb_done}")
    print(f"  Images moved           :  {moved}")
    print("=" * 55)

    if not dry_run and ig_pend > 0:
        print("\n🎯 What happens next:")
        print("   → GitHub Actions will publish 1 Instagram post every hour.")
        print("   → Facebook posts are scheduled server-side.")
        print("   → You can turn off your PC now! 🔌\n")

    # ------------------------------------------------------------------
    # Print caption previews
    # ------------------------------------------------------------------
    print("\n" + "─" * 55)
    print("  📝 CAPTION PREVIEWS")
    print("─" * 55)
    for post in queue["posts"]:
        sched = post["scheduled_time"][:16].replace("T", " ")
        status = "✅ LIVE" if post["ig_published"] else f"⏰ {sched}"
        print(f"\n{'─' * 55}")
        print(f"📄 {post['filename']}  |  {status}")
        print(f"{'─' * 55}")
        if post["caption"]:
            # Show first 300 chars of caption
            preview = post["caption"][:300]
            if len(post["caption"]) > 300:
                preview += "..."
            print(preview)
        else:
            print("[Caption not yet generated]")
    print()


# ═══════════════════════════════════════════════════════════════════════════
# STATUS COMMAND
# ═══════════════════════════════════════════════════════════════════════════

def show_status():
    """Display the current queue status in a compact table."""
    queue = load_json(QUEUE_PATH, {"posts": []})
    posts = queue.get("posts", [])

    if not posts:
        print("📭 No queue found. Run: python prepare.py")
        return

    prepared = queue.get("prepared_at", "unknown")
    print("=" * 65)
    print(f"  📊 Queue Status  —  Prepared: {prepared[:16] if prepared else 'N/A'}")
    print("=" * 65)
    print(f"  {'#':>3}  {'IG':^4}  {'FB':^4}  {'Moved':^5}  {'Scheduled':^16}  {'Filename'}")
    print("  " + "─" * 60)

    for p in posts:
        ig = "✅" if p.get("ig_published") else ("📦" if p.get("ig_container_id") else "❌")
        fb = "✅" if p.get("fb_scheduled") else "❌"
        mv = "✅" if p.get("moved") else "—"
        sched = p.get("scheduled_time", "")[:16].replace("T", " ")
        print(f"  {p.get('index', 0) + 1:>3}  {ig:^4}  {fb:^4}  {mv:^5}  {sched:^16}  {p['filename']}")

    ig_done = sum(1 for p in posts if p.get("ig_published"))
    ig_pend = sum(1 for p in posts if p.get("ig_container_id") and not p.get("ig_published"))
    fb_done = sum(1 for p in posts if p.get("fb_scheduled"))
    print("  " + "─" * 60)
    print(f"  Instagram: {ig_done} published, {ig_pend} pending  |  Facebook: {fb_done} scheduled")
    print()


# ═══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Prepare daily Instagram/Facebook posts for @examsfiles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python prepare.py              Process images and post/schedule
  python prepare.py --dry-run    Preview captions without posting
  python prepare.py --status     Show current queue status
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate captions & preview without posting or uploading",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current queue status and exit",
    )
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        prepare(dry_run=args.dry_run)



