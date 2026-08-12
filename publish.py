#!/usr/bin/env python3
"""
publish.py — Hourly Instagram Publisher for @upscbite

Called by GitHub Actions every hour to publish the next pending Instagram post.
Can also be run locally for testing.

Usage:
    python publish.py              Publish next pending post
    python publish.py --dry-run    Simulate without publishing
    python publish.py --status     Show queue status

Environment variables (used in GitHub Actions — overrides config.json):
    META_USER_ACCESS_TOKEN   — Long-lived Meta User Access Token
    META_IG_USER_ID          — Instagram Business Account ID
    META_PAGE_ACCESS_TOKEN   — Facebook Page Access Token
    META_PAGE_ID             — Facebook Page ID
    IMGBB_API_KEY            — imgbb API key (not used here, but kept for consistency)
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Fix for Windows terminals throwing UnicodeEncodeError on emojis
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

try:
    import requests
except ImportError:
    print("❌ Missing 'requests' library. Run: pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths & Constants
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
QUEUE_PATH = SCRIPT_DIR / "queue.json"
CONFIG_PATH = SCRIPT_DIR / "config.json"
LOG_PATH = SCRIPT_DIR / "post_log.json"

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
IST = timezone(timedelta(hours=5, minutes=30))


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def atomic_write_json(filepath: Path, data):
    """Write JSON atomically: write .tmp → fsync → rename."""
    filepath = Path(filepath)
    tmp_path = filepath.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp_path), str(filepath))


def load_json(filepath: Path, default=None):
    """Load JSON safely; return default if missing or corrupt."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def append_log(entry: dict):
    """Append to post_log.json."""
    log = load_json(LOG_PATH, [])
    if not isinstance(log, list):
        log = []
    log.append(entry)
    atomic_write_json(LOG_PATH, log)


def get_config() -> dict:
    """
    Load configuration from environment variables (GitHub Actions) or
    config.json (local). Environment variables take precedence.
    """
    # Check environment variables first (GitHub Actions / CI)
    env_token = os.environ.get("META_USER_ACCESS_TOKEN", "")
    env_ig_id = os.environ.get("META_IG_USER_ID", "")

    if env_token and env_ig_id:
        print("ℹ️  Using environment variables for config (CI mode)")
        return {
            "meta": {
                "user_access_token": env_token,
                "ig_user_id": env_ig_id,
                "page_access_token": os.environ.get("META_PAGE_ACCESS_TOKEN", ""),
                "page_id": os.environ.get("META_PAGE_ID", ""),
            }
        }

    # Fall back to config.json (local mode)
    if CONFIG_PATH.exists():
        return load_json(CONFIG_PATH)

    print("❌ No config found. Set environment variables or create config.json.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Instagram Graph API
# ---------------------------------------------------------------------------

def check_container_status(container_id: str, access_token: str) -> str:
    """Poll the status_code of an Instagram media container."""
    resp = requests.get(
        f"{GRAPH_API_BASE}/{container_id}",
        params={
            "fields": "status_code",
            "access_token": access_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("status_code", "UNKNOWN")


def wait_for_container(container_id: str, access_token: str, max_wait: int = 180):
    """Wait until the container is FINISHED, or raise on error / timeout."""
    waited = 0
    interval = 5
    last_status = "UNKNOWN"

    while waited < max_wait:
        last_status = check_container_status(container_id, access_token)
        if last_status in ("FINISHED", "PUBLISHED"):
            return
        if last_status == "ERROR":
            raise RuntimeError(f"Container {container_id} failed with ERROR status")
        time.sleep(interval)
        waited += interval

    raise TimeoutError(
        f"Container {container_id} not ready after {max_wait}s "
        f"(last status: {last_status})"
    )


def publish_container(container_id: str, ig_user_id: str, access_token: str) -> str:
    """Publish an Instagram media container and return the post ID."""
    wait_for_container(container_id, access_token)

    resp = requests.post(
        f"{GRAPH_API_BASE}/{ig_user_id}/media_publish",
        data={
            "creation_id": container_id,
            "access_token": access_token,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Main Logic
# ---------------------------------------------------------------------------

def publish_next(dry_run: bool = False):
    """Find and publish the next pending Instagram post from the queue."""
    config = get_config()
    access_token = config["meta"]["user_access_token"]
    ig_user_id = config["meta"]["ig_user_id"]

    # Load queue
    queue = load_json(QUEUE_PATH, {"posts": []})
    posts = queue.get("posts", [])

    if not posts:
        print("📭 Queue is empty. Nothing to publish.")
        return

    now = datetime.now(IST)

    # Find next post that:
    # 1. Has a container ID (was processed by prepare.py)
    # 2. Is NOT yet published to Instagram
    # 3. Scheduled time has passed
    # Find ALL pending posts whose scheduled time has passed
    targets = []
    for post in posts:
        if not post.get("ig_container_id") or post.get("ig_published"):
            continue

        sched_str = post.get("scheduled_time", "")
        if sched_str:
            sched_time = datetime.fromisoformat(sched_str)
            if sched_time.tzinfo is None:
                sched_time = sched_time.replace(tzinfo=IST)
            if sched_time > now:
                continue

        targets.append(post)

    if not targets:
        all_done = all(p.get("ig_published") for p in posts if p.get("ig_container_id"))
        if all_done:
            print("✅ All Instagram posts have been published! Queue complete.")
        else:
            pending = [p for p in posts if p.get("ig_container_id") and not p.get("ig_published")]
            if pending:
                next_time = pending[0].get("scheduled_time", "unknown")[:16]
                print(f"⏳ No posts due yet. Next scheduled at: {next_time}")
            else:
                print("📭 No publishable posts in queue.")
        return

    print(f"📦 Found {len(targets)} overdue post(s) to publish.")

    for i, target in enumerate(targets):
        filename = target["filename"]
        container_id = target["ig_container_id"]

        print(f"\n🚀 Publishing ({i+1}/{len(targets)}): {filename}")
        print(f"   Container ID: {container_id}")
        print(f"   Scheduled:    {target.get('scheduled_time', 'N/A')[:16]}")

        if dry_run:
            print("   🧪 DRY RUN — skipping actual publish")
            target["ig_published"] = True
            target["ig_post_id"] = "dry-run-id"
        else:
            try:
                post_id = publish_container(container_id, ig_user_id, access_token)
                target["ig_published"] = True
                target["ig_post_id"] = post_id
                print(f"   ✅ Published! Instagram Post ID: {post_id}")

                append_log({
                    "platform": "instagram",
                    "filename": filename,
                    "post_id": post_id,
                    "container_id": container_id,
                    "timestamp": datetime.now(IST).isoformat(),
                })

            except Exception as exc:
                print(f"   ❌ Publishing failed: {exc}")
                append_log({
                    "platform": "instagram",
                    "filename": filename,
                    "container_id": container_id,
                    "error": str(exc),
                    "timestamp": datetime.now(IST).isoformat(),
                })
                
                if "OAuthException" in str(exc) or "400 Client Error" in str(exc):
                    # Save queue before exiting so we don't lose progress on successful ones
                    atomic_write_json(QUEUE_PATH, queue)
                    sys.exit(1)
                
                continue  # Skip to the next post if it's a minor error

        # Save progress after every post
        atomic_write_json(QUEUE_PATH, queue)

        # Sleep between posts to prevent rate-limiting (unless it's the last one)
        if i < len(targets) - 1 and not dry_run:
            print("   ⏳ Sleeping for 60 seconds to prevent rate-limiting...")
            time.sleep(60)

    # Save updated queue
    atomic_write_json(QUEUE_PATH, queue)

    # Summary
    total = sum(1 for p in posts if p.get("ig_container_id"))
    done = sum(1 for p in posts if p.get("ig_published"))
    print(f"\n📊 Progress: {done}/{total} Instagram posts published")

    if done < total:
        remaining = [
            p for p in posts
            if p.get("ig_container_id") and not p.get("ig_published")
        ]
        if remaining:
            next_time = remaining[0].get("scheduled_time", "")[:16].replace("T", " ")
            print(f"   Next post at: {next_time}")


def show_status():
    """Display compact queue status."""
    queue = load_json(QUEUE_PATH, {"posts": []})
    posts = queue.get("posts", [])

    if not posts:
        print("📭 No queue found.")
        return

    print("=" * 60)
    print(f"  📊 Queue Status")
    print("=" * 60)
    print(f"  {'#':>3}  {'IG':^6}  {'FB':^4}  {'Scheduled':^16}  {'Filename'}")
    print("  " + "─" * 55)

    for p in posts:
        ig = "✅ LIVE" if p.get("ig_published") else ("📦 RDY" if p.get("ig_container_id") else "❌")
        fb = "✅" if p.get("fb_scheduled") else "❌"
        sched = p.get("scheduled_time", "")[:16].replace("T", " ")
        print(f"  {p.get('index', 0) + 1:>3}  {ig:^6}  {fb:^4}  {sched:^16}  {p['filename']}")

    done = sum(1 for p in posts if p.get("ig_published"))
    total = sum(1 for p in posts if p.get("ig_container_id"))
    print("  " + "─" * 55)
    print(f"  Instagram: {done}/{total} published")
    print()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Publish next pending Instagram post for @upscbite"
    )
    parser.add_argument("--dry-run", action="store_true", help="Simulate without publishing")
    parser.add_argument("--status", action="store_true", help="Show queue status")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        publish_next(dry_run=args.dry_run)
