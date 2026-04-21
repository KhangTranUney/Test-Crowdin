#!/usr/bin/env python3
"""
Download translations from Crowdin and copy them to Android res directories.

Usage:
    python3 download_translations.py --token <TOKEN> --project-id <ID>

Requirements:
    - Crowdin CLI installed: https://crowdin.github.io/crowdin-cli/
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

# Map Crowdin language codes → Android res folder suffixes
LANGUAGE_MAP = {
    "vi": "vi",
    "fr": "fr",
    "de": "de",
    "es-ES": "es",
    "ja": "ja",
    "ko": "ko",
    "zh-CN": "zh-rCN",
    "zh-TW": "zh-rTW",
    "pt-PT": "pt",
    "pt-BR": "pt-rBR",
}

# Path to Android strings resource directory relative to this script
ANDROID_RES_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "src", "main", "res")


def load_env(env_file: str = ".env"):
    """Load key=value pairs from a .env file into os.environ."""
    env_path = os.path.join(os.path.dirname(__file__), env_file)
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def check_crowdin_cli():
    result = subprocess.run(["crowdin", "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        print("Error: Crowdin CLI not found. Install it from https://crowdin.github.io/crowdin-cli/")
        sys.exit(1)
    print(f"Crowdin CLI: {result.stdout.strip()}")


def download_translations(token: str, project_id: str, languages: list[str], export_only_approved: bool, output_dir: str):
    cmd = [
        "crowdin", "download",
        "--token", token,
        "--project-id", project_id,
        "--base-path", output_dir,
        "--translation", "%locale%/%original_file_name%",
        "--verbose",
    ]

    for lang in languages:
        cmd += ["--language", lang]

    if export_only_approved:
        cmd.append("--export-only-approved")

    print(f"\nRunning: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, text=True)

    if result.returncode != 0:
        print("Error: Crowdin download failed.")
        sys.exit(1)


def copy_to_android_res(output_dir: str, languages: list[str]):
    copied = 0

    for crowdin_lang, android_suffix in LANGUAGE_MAP.items():
        if languages and crowdin_lang not in languages:
            continue

        src_dir = os.path.join(output_dir, crowdin_lang)
        if not os.path.isdir(src_dir):
            print(f"  Skipping {crowdin_lang}: no downloaded files found")
            continue

        dest_dir = os.path.join(ANDROID_RES_DIR, f"values-{android_suffix}")
        os.makedirs(dest_dir, exist_ok=True)

        for filename in os.listdir(src_dir):
            if not filename.endswith(".xml"):
                continue
            src_file = os.path.join(src_dir, filename)
            dest_file = os.path.join(dest_dir, filename)
            shutil.copy2(src_file, dest_file)
            print(f"  Copied: {crowdin_lang}/{filename} → res/values-{android_suffix}/{filename}")
            copied += 1

    print(f"\nDone. {copied} file(s) copied to {ANDROID_RES_DIR}")


def main():
    load_env()

    parser = argparse.ArgumentParser(description="Download Crowdin translations into Android res folders")
    parser.add_argument("--token", "-T", default=os.environ.get("CROWDIN_TOKEN"), help="Crowdin personal access token")
    parser.add_argument("--project-id", "-i", default=os.environ.get("CROWDIN_PROJECT_ID"), help="Crowdin numeric project ID")
    parser.add_argument("--language", "-l", action="append", default=[], metavar="LANG",
                        help="Language code(s) to download (e.g. vi, fr). Repeatable. Default: all.")
    parser.add_argument("--export-only-approved", action="store_true",
                        help="Download only approved translations")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without copying files to res/")
    args = parser.parse_args()

    if not args.token or not args.project_id:
        parser.error("--token and --project-id are required (or set CROWDIN_TOKEN and CROWDIN_PROJECT_ID in .env)")

    check_crowdin_cli()

    with tempfile.TemporaryDirectory() as tmp_dir:
        download_translations(
            token=args.token,
            project_id=args.project_id,
            languages=args.language,
            export_only_approved=args.export_only_approved,
            output_dir=tmp_dir,
        )

        if args.dry_run:
            print("\n[Dry run] Skipping copy to res/")
            print(f"Downloaded files are in: {tmp_dir}")
            input("Press Enter to exit and clean up...")
        else:
            copy_to_android_res(tmp_dir, args.language)


if __name__ == "__main__":
    main()
