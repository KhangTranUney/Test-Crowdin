#!/usr/bin/env python3
"""
Download Android translations from Crowdin via CLI bundle.

Steps:
  1. Load credentials from scripts/.env (CROWDIN_TOKEN, CROWDIN_PROJECT_ID)
  2. Fetch all target languages from Crowdin and build a mapping:
       androidCode → folder name
     Uses twoLettersCode (e.g. "vi") when unique across all target languages,
     falls back to androidCode (e.g. "zh-rCN") when multiple languages share
     the same two-letter code (e.g. zh-CN, zh-TW, zh-HK all map to "zh").
  3. Find or create the 'android-translations' bundle on Crowdin.
     Always updates the bundle to ensure the translation pattern is
     /%android_code%/strings.xml so every region gets its own unique folder.
  4. Download the bundle into a temp directory.
     Crowdin builds a single ZIP archive containing ALL target languages at once,
     extracted to: <tmp>/<android_code>/strings.xml
  5. Move each strings.xml to the correct res/ folder:
       Source language (e.g. en-rUS, not in target list) → res/values/strings.xml
       Target language                                    → res/values-{folder}/strings.xml
     Temp directory is automatically cleaned up afterwards.
  6. Run validate_strings.py to check for errors and offer to auto-fix them.

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
from collections import Counter

from validate_strings import run_interactive as validate_and_fix

BUNDLE_NAME = "android-translations"
# Translation pattern uses %android_code% so every language-region combination
# gets a unique folder in the archive (e.g. zh-rCN/, zh-rTW/ instead of both → zh/)
BUNDLE_TRANSLATION_PATTERN = "/%android_code%/strings.xml"

ANDROID_RES_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "src", "main", "res")


# ──────────────────────────────────────────────
# Credentials
# ──────────────────────────────────────────────

def load_env(env_file: str = ".env"):
    """Load KEY=VALUE pairs from scripts/.env into environment variables."""
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


# ──────────────────────────────────────────────
# Crowdin CLI helpers
# ──────────────────────────────────────────────

def crowdin_capture(*args) -> str:
    """Run a crowdin CLI command and return stdout as a string (for parsing)."""
    result = subprocess.run(["crowdin", *args], capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr.strip())
        sys.exit(result.returncode)
    return result.stdout.strip()


def crowdin_run(*args):
    """Run a crowdin CLI command with live output (used for bundle download / progress bars)."""
    result = subprocess.run(["crowdin", *args])
    if result.returncode != 0:
        sys.exit(result.returncode)


# ──────────────────────────────────────────────
# Step 2 — Language mapping
# ──────────────────────────────────────────────

def fetch_lang_mapping(token: str, project_id: str) -> dict[str, str]:
    """
    Returns {androidCode: folderName} for all project target languages.

    Prefers the short two-letter code as the folder name (e.g. "vi", "fr")
    because it matches the standard Android res folder convention.
    Falls back to the full androidCode (e.g. "zh-rCN") when two or more
    target languages share the same two-letter code (e.g. zh-CN and zh-TW
    both map to "zh" — using "zh" would cause one to overwrite the other).
    """
    # Fetch the full Android resource code for each target language (e.g. "zh-rCN", "vi", "en-rUS")
    android_codes = crowdin_capture(
        "language", "list",
        "--token", token, "--project-id", project_id,
        "--code", "android_code", "--plain", "--no-progress",
    ).splitlines()

    # Fetch the two-letter ISO code for each target language (e.g. "zh", "vi", "en")
    two_letter_codes = crowdin_capture(
        "language", "list",
        "--token", token, "--project-id", project_id,
        "--code", "two_letters_code", "--plain", "--no-progress",
    ).splitlines()

    # Count how many target languages share each two-letter code
    two_letter_counts = Counter(two_letter_codes)

    # Use short code if unique, otherwise fall back to full android code
    return {
        android: (two if two_letter_counts[two] == 1 else android)
        for android, two in zip(android_codes, two_letter_codes)
    }


# ──────────────────────────────────────────────
# Step 3 — Bundle setup
# ──────────────────────────────────────────────

def find_or_create_bundle(token: str, project_id: str) -> str:
    """
    Return the bundle ID for BUNDLE_NAME, creating it if it doesn't exist.

    The bundle is configured with translation pattern /%android_code%/strings.xml
    so every language-region combination gets a unique folder in the archive
    (e.g. zh-rCN/, zh-rTW/ instead of both colliding into zh/).

    Note: the Crowdin CLI does not support editing an existing bundle.
    If the bundle was previously created with a different pattern (e.g. %two_letters_code%),
    delete it from the Crowdin dashboard and run this script again to recreate it correctly.
    """
    # List all bundles and look for one named BUNDLE_NAME
    output = crowdin_capture(
        "bundle", "list",
        "--token", token, "--project-id", project_id,
        "--plain", "--no-progress",
    )
    for line in output.splitlines():
        # Each line: "<id>  <name>"
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1] == BUNDLE_NAME:
            bundle_id = parts[0]
            print(f"Bundle '{BUNDLE_NAME}' found (ID: {bundle_id}).")
            return bundle_id

    # Bundle not found — create it with the correct pattern
    print(f"Bundle '{BUNDLE_NAME}' not found, creating...")
    output = crowdin_capture(
        "bundle", "add", BUNDLE_NAME,
        "--token", token, "--project-id", project_id,
        "--format", "android",
        "--source", "/**",               # include all source files
        "--translation", BUNDLE_TRANSLATION_PATTERN,
        "--include-source-language",     # include English (source) in the archive
        "--plain", "--no-progress",
    )
    bundle_id = output.split()[0]
    print(f"  Created bundle ID: {bundle_id}")
    return bundle_id


# ──────────────────────────────────────────────
# Step 5 — Move files to res/
# ──────────────────────────────────────────────

def move_to_res(temp_dir: str, res_dir: str, lang_mapping: dict[str, str], dry_run: bool):
    """
    Move each strings.xml from the extracted bundle into the correct res/ folder.

    The bundle archive is extracted as:
        <temp_dir>/<android_code>/strings.xml

    Destination mapping:
        Source language (android_code not in lang_mapping) → res/values/strings.xml
        Target language                                     → res/values-{folder}/strings.xml

    The source language is detected by absence from lang_mapping (which only
    contains target languages). For example, if the source is English, Crowdin
    puts it under "en-rUS/" in the archive, which won't be in the target list.
    """
    for android_code in sorted(os.listdir(temp_dir)):
        src = os.path.join(temp_dir, android_code, "strings.xml")
        if not os.path.isfile(src):
            continue  # skip non-language entries (e.g. __MACOSX)

        if android_code not in lang_mapping:
            # This android_code is not a target language → it must be the source language
            dest = os.path.join(res_dir, "values", "strings.xml")
            label = "values/strings.xml"
        else:
            folder = lang_mapping[android_code]
            dest = os.path.join(res_dir, f"values-{folder}", "strings.xml")
            label = f"values-{folder}/strings.xml"

        if dry_run:
            print(f"  [dry-run] Would write → {label}")
        else:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(src, dest)
            print(f"  Written → {label}")


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

def main():
    # Step 1 — load credentials
    load_env()

    parser = argparse.ArgumentParser(description="Download Crowdin translations via CLI bundle")
    parser.add_argument("--token", "-T", default=os.environ.get("CROWDIN_TOKEN"))
    parser.add_argument("--project-id", "-i", default=os.environ.get("CROWDIN_PROJECT_ID"))
    parser.add_argument("--export-only-approved", action="store_true",
                        help="Only include approved translations in the export")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be written without changing any files")
    args = parser.parse_args()

    if not args.token or not args.project_id:
        parser.error("--token and --project-id are required (or set them in scripts/.env)")

    # Step 2 — build language mapping: androidCode → res folder name
    print("Fetching language list...")
    lang_mapping = fetch_lang_mapping(args.token, args.project_id)

    # Step 3 — ensure bundle exists with the correct pattern
    bundle_id = find_or_create_bundle(args.token, args.project_id)

    extra_args = []
    if args.export_only_approved:
        extra_args.append("--export-only-approved")
    if args.dry_run:
        extra_args.append("--dryrun")

    # Steps 4 & 5 — download bundle and move files
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Step 4 — download: Crowdin builds one ZIP with all languages, CLI extracts it here
        print(f"Downloading bundle {bundle_id}...")
        crowdin_run(
            "bundle", "download", bundle_id,
            "--token", args.token, "--project-id", args.project_id,
            "--base-path", tmp_dir,
            *extra_args,
        )
        # Step 5 — move each <android_code>/strings.xml to res/values[-{lang}]/strings.xml
        print("Moving files to res/...")
        move_to_res(tmp_dir, os.path.abspath(ANDROID_RES_DIR), lang_mapping, args.dry_run)
    # temp directory is automatically deleted here

    # Step 6 — validate all strings.xml files and offer to auto-fix errors
    if not args.dry_run:
        ok = validate_and_fix(os.path.abspath(ANDROID_RES_DIR))
        if not ok:
            sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    main()
