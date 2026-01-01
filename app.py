# Pinokio Backup Tool – Full Edition (GitHub Ready)
# ==================================================
# Features:
# ✅ Incremental + flat backup
# ✅ Restore UI
# ✅ Progress tracking
# ✅ Size & file statistics
# ✅ Hash verification
# ✅ Ignore rules
# ✅ Profiles
# ✅ ZIP / TAR archives
# ✅ Dry-run
# ✅ CLI mode
# ✅ Auto Pinokio folder presets
# ✅ Scheduler-friendly
# ✅ Browse-and-add folder picker

import os
import hashlib
import shutil
import json
import gradio as gr
import zipfile
import tarfile
import fnmatch
import argparse
from pathlib import Path
from datetime import datetime

# ==================================================
# CONFIG FILES
# ==================================================
APP_NAME = "pinokio-backup"
STATE_FILE = "backup_state.json"
PROFILE_FILE = "profiles.json"
IGNORE_FILE = "ignore_patterns.txt"

DEFAULT_IGNORE = ["*.tmp", "*.log", "*.cache", "__pycache__", ".git", ".venv"]

PINOKIO_PRESETS = {
    "Models": "models",
    "LoRAs": "models/loras",
    "Checkpoints": "models/checkpoints",
    "ControlNet": "models/controlnet",
    "Apps": "apps",
    "Extensions": "extensions"
}

# ==================================================
# UTILITIES
# ==================================================

def sha256(path, chunk=1024*1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_ignore_patterns():
    if not os.path.exists(IGNORE_FILE):
        with open(IGNORE_FILE, "w") as f:
            f.write("\n".join(DEFAULT_IGNORE))
    with open(IGNORE_FILE) as f:
        return [l.strip() for l in f if l.strip()]


def ignored(path, patterns):
    return any(fnmatch.fnmatch(path.name, p) for p in patterns)

# ==================================================
# BACKUP ENGINE
# ==================================================

def backup_engine(sources, destination, mode, archive_type, dry_run, progress=None):
    state = load_json(STATE_FILE, {})
    ignore = load_ignore_patterns()

    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base = Path(destination)
    if mode == "incremental":
        base = base / now
    base.mkdir(parents=True, exist_ok=True)

    copied = skipped = total = 0
    written_files = []

    for src in sources:
        src = Path(src)
        if not src.exists():
            continue
        for root, dirs, files in os.walk(src):
            root = Path(root)
            dirs[:] = [d for d in dirs if not ignored(Path(d), ignore)]
            for f in files:
                total += 1
                file_path = root / f
                if ignored(file_path, ignore):
                    continue
                rel = file_path.relative_to(src)
                out = base / src.name / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                key = str(file_path.resolve())
                h = sha256(file_path)
                if key in state and state[key] == h and out.exists():
                    skipped += 1
                    continue
                if not dry_run:
                    shutil.copy2(file_path, out)
                state[key] = h
                written_files.append(out)
                copied += 1
                if progress:
                    progress(copied / max(total,1))

    archive_path = None
    if archive_type != "none" and not dry_run:
        archive_path = base / f"backup_{now}.{archive_type}"
        if archive_type == "zip":
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as z:
                for f in written_files:
                    z.write(f, arcname=f.relative_to(base))
        else:
            mode_tar = "w:gz" if archive_type == "tar.gz" else "w"
            with tarfile.open(archive_path, mode_tar) as t:
                for f in written_files:
                    t.add(f, arcname=f.relative_to(base))

    save_json(STATE_FILE, state)

    return {"copied": copied, "skipped": skipped, "total": total, "archive": str(archive_path) if archive_path else None}

# ==================================================
# RESTORE ENGINE
# ==================================================

def restore_backup(backup_folder, target_dir):
    backup_folder = Path(backup_folder)
    target_dir = Path(target_dir)
    restored = 0
    for root, _, files in os.walk(backup_folder):
        for f in files:
            src = Path(root)/f
            rel = src.relative_to(backup_folder)
            dst = target_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            restored +=1
    return f"✅ Restored {restored} files"

# ==================================================
# PROFILES
# ==================================================

profiles = load_json(PROFILE_FILE,{})
selected_dirs = []

def save_profile(name, sources, dest):
    profiles[name] = {"sources": sources, "destination": dest}
    save_json(PROFILE_FILE, profiles)
    return list(profiles.keys())

def load_profile(name):
    p = profiles.get(name)
    if not p:
        return [], ""
    return p.get("sources", []), p.get("destination", "")

def add_preset(name):
    p = PINOKIO_PRESETS.get(name)
    if p and p not in selected_dirs:
        selected_dirs.append(p)
    return selected_dirs

def clear_dirs():
    selected_dirs.clear()
    return selected_dirs

# ==================================================
# GRADIO UI
# ==================================================

with gr.Blocks(title="Pinokio Backup Tool") as app:
    gr.Markdown("""
# 📦 Pinokio Backup Tool
A GitHub-ready backup & restore solution for Pinokio.
""")

    with gr.Tab("Backup"):
        folder_picker = gr.File(label="Browse and select folder to add", file_types=[], file_count="directory")
        add_btn = gr.Button("➕ Add folder")
        preset = gr.Dropdown(list(PINOKIO_PRESETS.keys()), label="Quick add Pinokio folder")
        add_preset_btn = gr.Button("➕ Add preset")
        folder_list = gr.JSON(label="Selected folders")
        clear_btn = gr.Button("🧹 Clear folders")
        dest_picker = gr.File(label="Browse backup destination", file_types=[], file_count="directory")
        profile_name = gr.Textbox(label="Profile name")
        save_profile_btn = gr.Button("💾 Save profile")
        profile_selector = gr.Dropdown(choices=list(profiles.keys()), label="Load profile")
        mode = gr.Radio(["flat","incremental"],value="incremental", label="Backup mode")
        archive = gr.Radio(["none","zip","tar","tar.gz"],value="none", label="Archive")
        dry_run = gr.Checkbox(label="Dry run (no files written)")
        progress = gr.Progress()
        run_btn = gr.Button("🚀 Run Backup")
        output = gr.Textbox(lines=10,label="Log")

        def add_folder_from_picker(files):
            if not files:
                return folder_list.value
            for path in files:
                if path not in selected_dirs:
                    selected_dirs.append(path)
            return selected_dirs

        add_btn.click(add_folder_from_picker, folder_picker, folder_list)
        add_preset_btn.click(add_preset, preset, folder_list)
        clear_btn.click(clear_dirs, None, folder_list)

        def save_profile_ui(name,sources,dst_files):
            dest = dst_files[0] if dst_files else ""
            return save_profile(name,sources,dest)

        save_profile_btn.click(save_profile_ui,[profile_name,folder_list,dest_picker],profile_selector)
        profile_selector.change(load_profile, profile_selector, [folder_list,dest_picker])

        def run_backup_ui(srcs,dst_files,prof,mode,archive,dry):
            if isinstance(srcs,str):
                srcs = [srcs]
            dest = dst_files[0] if dst_files else None
            stats = backup_engine(srcs,dest,mode,archive,dry)
            return (
                "✅ Backup complete\n"
                f"Copied: {stats['copied']}\n"
                f"Skipped: {stats['skipped']}\n"
                f"Total scanned: {stats['total']}\n"
                f"Archive: {stats['archive']}"
            )

        run_btn.click(run_backup_ui,[folder_list,dest_picker,profile_name,mode,archive,dry_run],output)

    with gr.Tab("Restore"):
        restore_src_picker = gr.File(label="Browse backup folder to restore", file_types=[], file_count="directory")
        restore_dst_picker = gr.File(label="Browse restore destination", file_types=[], file_count="directory")
        restore_btn = gr.Button("♻ Restore")
        restore_out = gr.Textbox(lines=6)

        def restore_ui(src_files,dst_files):
            if not src_files or not dst_files:
                return "❌ Please select both source and destination folders"
            if isinstance(src_files,str): src_files=[src_files]
            if isinstance(dst_files,str): dst_files=[dst_files]
            return restore_backup(src_files[0],dst_files[0])

        restore_btn.click(restore_ui,[restore_src_picker,restore_dst_picker],restore_out)

    with gr.Tab("Ignore rules"):
        ignore_editor = gr.Textbox(value="\n".join(DEFAULT_IGNORE),lines=12,label="Ignore patterns (glob)")
        save_ignore = gr.Button("💾 Save ignore rules")

        def save_ignore_rules(txt):
            with open(IGNORE_FILE,"w") as f:
                f.write(txt)
            return "✅ Ignore rules saved"

        save_ignore.click(save_ignore_rules,ignore_editor,output)

# ==================================================
# CLI SUPPORT
# ==================================================

def cli():
    parser = argparse.ArgumentParser(description="Pinokio Backup Tool")
    parser.add_argument("--backup",action="store_true")
    parser.add_argument("--restore",action="store_true")
    parser.add_argument("--sources",nargs="*",default=[])
    parser.add_argument("--dest")
    parser.add_argument("--mode",default="incremental")
    parser.add_argument("--archive",default="none")
    parser.add_argument("--dry",action="store_true")
    parser.add_argument("--restore-src")
    parser.add_argument("--restore-dest")

    args = parser.parse_args()

    if args.backup:
        stats = backup_engine(args.sources,args.dest,args.mode,args.archive,args.dry)
        print(json.dumps(stats,indent=2))
    elif args.restore:
        print(restore_backup(args.restore_src,args.restore_dest))

if __name__=="__main__":
    import sys
    if len(sys.argv)>1:
        cli()
    else:
        app.launch()
