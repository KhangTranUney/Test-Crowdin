#!/usr/bin/env python3
"""
Download Android translations from Crowdin via CLI bundle.
Finds or creates the 'android-translations' bundle, downloads it,
moves strings.xml files to the correct res/values-{lang}/ directories,
then validates.

Usage:
    python3 cli_download_translations.py
    python3 cli_download_translations.py --export-only-approved
    python3 cli_download_translations.py --dry-run
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

from validate_strings import run_interactive as validate_and_fix

BUNDLE_NAME = "android-translations"
SOURCE_LANG = "en"
ANDROID_RES_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "src", "main", "res")


def load_env(env_file: str = ".env"):
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


def crowdin_capture(*args) -> str:
    """Run a crowdin CLI command and return stdout (for parsing)."""
    result = subprocess.run(["crowdin", *args], capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr.strip())
        sys.exit(result.returncode)
    return result.stdout.strip()


def crowdin_run(*args):
    """Run a crowdin CLI command with live output (for download/progress)."""
    result = subprocess.run(["crowdin", *args])
    if result.returncode != 0:
        sys.exit(result.returncode)


def find_or_create_bundle(token: str, project_id: str) -> str:
    """Return bundle ID for BUNDLE_NAME, creating it if it doesn't exist."""
    output = crowdin_capture(
        "bundle", "list",
        "--token", token, "--project-id", project_id,
        "--plain", "--no-progress",
    )
    for line in output.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1] == BUNDLE_NAME:
            return parts[0]

    print(f"Bundle '{BUNDLE_NAME}' not found, creating...")
    output = crowdin_capture(
        "bundle", "add", BUNDLE_NAME,
        "--token", token, "--project-id", project_id,
        "--format", "android",
        "--source", "/**",
        "--translation", "/%two_letters_code%/strings.xml",
        "--include-source-language",
        "--plain", "--no-progress",
    )
    bundle_id = output.split()[0]
    print(f"  Created bundle ID: {bundle_id}")
    return bundle_id


def move_to_res(temp_dir: str, res_dir: str, dry_run: bool):
    for lang_dir in sorted(os.listdir(temp_dir)):
        src = os.path.join(temp_dir, lang_dir, "strings.xml")
        if not os.path.isfile(src):
            continue
        if lang_dir == SOURCE_LANG:
            dest = os.path.join(res_dir, "values", "strings.xml")
            label = "values/strings.xml"
        else:
            dest = os.path.join(res_dir, f"values-{lang_dir}", "strings.xml")
            label = f"values-{lang_dir}/strings.xml"

        if dry_run:
            print(f"  [dry-run] Would write → {label}")
        else:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(src, dest)
            print(f"  Written → {label}")


def main():
    load_env()

    parser = argparse.ArgumentParser(description="Download Crowdin translations via CLI bundle")
    parser.add_argument("--token", "-T", default=os.environ.get("CROWDIN_TOKEN"))
    parser.add_argument("--project-id", "-i", default=os.environ.get("CROWDIN_PROJECT_ID"))
    parser.add_argument("--export-only-approved", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    args = parser.parse_args()

    if not args.token or not args.project_id:
        parser.error("--token and --project-id are required (or set them in scripts/.env)")

    bundle_id = find_or_create_bundle(args.token, args.project_id)

    extra_args = []
    if args.export_only_approved:
        extra_args.append("--export-only-approved")
    if args.dry_run:
        extra_args.append("--dryrun")

    with tempfile.TemporaryDirectory() as tmp_dir:
        crowdin_run(
            "bundle", "download", bundle_id,
            "--token", args.token, "--project-id", args.project_id,
            "--base-path", tmp_dir,
            *extra_args,
        )
        move_to_res(tmp_dir, os.path.abspath(ANDROID_RES_DIR), args.dry_run)

    if not args.dry_run:
        ok = validate_and_fix(os.path.abspath(ANDROID_RES_DIR))
        if not ok:
            sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    main()
