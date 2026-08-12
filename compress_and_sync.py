import os
import json
import shutil
import subprocess
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent

def get_settings():
    try:
        with open(SCRIPT_DIR / "config.json", "r") as f:
            return json.load(f).get("settings", {})
    except:
        return {}

def run_git_command(args, env):
    git_exe = str(SCRIPT_DIR / "git_portable" / "cmd" / "git.exe")
    return subprocess.run([git_exe] + args, cwd=str(SCRIPT_DIR), capture_output=True, text=True, env=env)

def sync_exam upload():
    print("==================================================")
    print("☁️   UPSC Bite - Upload Exam Upload Sync (One-by-One)")
    print("==================================================")
    
    settings = get_settings()
    image_folder = Path(settings.get("image_folder", r"C:\Users\Welcome\Pictures\bite upload"))
    uploaded_folder = Path(settings.get("uploaded_folder", r"C:\Users\Welcome\Pictures\uploaded  bite"))
    uploaded_folder.mkdir(parents=True, exist_ok=True)
    
    exam upload_folder = SCRIPT_DIR / "exam upload"
    exam upload_folder.mkdir(parents=True, exist_ok=True)
    
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    
    images = [f for f in image_folder.iterdir() if f.is_file() and f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']]
    
    if not images:
        print("   ℹ️  No new images found in your 'bite upload' folder.")
        print("   🔄 Checking if there are any unpushed images stuck in the Exam Upload...")
        # Check if there's anything to push
        run_git_command(["add", "exam upload/"], env)
        res = run_git_command(["commit", "-m", "Exam Upload Sync: Recovering stuck images"], env)
        if "nothing to commit" not in res.stdout:
            print("   🚀 Recovering unpushed images...")
            run_git_command(["pull", "--rebase", "--autostash"], env)
            push_res = run_git_command(["push"], env)
            if push_res.returncode == 0:
                print("   🌟 Recovery complete! All images pushed successfully.")
            else:
                print(f"   ⚠️  Failed to recover images. Check connection. Error: {push_res.stderr}")
        else:
            # Maybe there are commits not pushed yet
            run_git_command(["pull", "--rebase", "--autostash"], env)
            push_res = run_git_command(["push"], env)
            if push_res.returncode != 0:
                print(f"   ⚠️  Push failed. Error: {push_res.stderr}")
        return
        
    print(f"   📥 Found {len(images)} images. Uploading strictly one-by-one for maximum safety.")
    
    synced = 0
    for i, img_path in enumerate(images, 1):
        print(f"\n   [{i}/{len(images)}] ⚙️  Processing {img_path.name}...")
        dst_path = exam upload_folder / img_path.name
        
        try:
            # Atomic-like copy: copy to .tmp first, then rename
            tmp_path = dst_path.with_suffix('.tmp')
            shutil.copy2(img_path, tmp_path)
            tmp_path.replace(dst_path)
            
            # Now push this exact image to GitHub
            print(f"   🚀 Uploading {img_path.name} to Cloud Exam Upload...")
            run_git_command(["pull", "--rebase", "--autostash"], env)
            run_git_command(["add", "exam upload/"], env)
            run_git_command(["commit", "-m", f"Exam Upload Sync: Added {img_path.name}"], env)
            
            push_res = run_git_command(["push"], env)
            if push_res.returncode == 0:
                print(f"   ✅ Cloud confirmed! Moving original to 'uploaded' folder.")
                shutil.move(str(img_path), str(uploaded_folder / img_path.name))
                synced += 1
            else:
                print(f"   ⚠️  CRITICAL ERROR: Failed to upload {img_path.name} to GitHub!")
                print(f"   ⚠️  Reason: {push_res.stderr}")
                print(f"   🛑 Stopping process immediately. Your remaining images are safe in 'bite upload'.")
                sys.exit(1)
                
        except Exception as e:
            print(f"   ⚠️  Failed to process {img_path.name}: {e}")
            print(f"   🛑 Stopping process. Check the error above.")
            sys.exit(1)
            
    print(f"\n   🌟 Sync complete! Successfully and safely uploaded {synced} images.")

if __name__ == "__main__":
    sync_exam upload()
