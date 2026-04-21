#!/usr/bin/env python3
"""
Download Android translations from a Crowdin string-based project via REST API.

Steps:
  1. Load credentials from scripts/.env (CROWDIN_TOKEN, CROWDIN_PROJECT_ID)
  2. Fetch project info from Crowdin API to get target language list
  3. Build a language mapping: languageId → folder name
     Uses twoLettersCode (e.g. "vi") when unique across all target languages,
     falls back to androidCode (e.g. "zh-rCN") when multiple languages share
     the same two-letter code (e.g. zh-CN, zh-TW, zh-HK all map to "zh").
  4. Export source language (English) → res/values/strings.xml
  5. Export each target language    → res/values-{folder}/strings.xml
     Each export triggers a fresh build on Crowdin's server, then downloads
     the resulting Android XML file directly.
  6. Run validate_strings.py to check for errors and offer to auto-fix them.

Usage:
    python3 download_translations.py                   # all languages
    python3 download_translations.py -l vi             # single language
    python3 download_translations.py --export-only-approved
    python3 download_translations.py --dry-run
"""

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from collections import Counter

from validate_strings import run_interactive as validate_and_fix

# Use certifi's CA bundle on macOS to avoid SSL certificate errors
try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

BASE_API = "https://api.crowdin.com/api/v2"

ANDROID_RES_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "src", "main", "res")
OUTPUT_FILENAME = "strings.xml"


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
# REST API helpers
# ──────────────────────────────────────────────

def api_get(path: str, token: str) -> dict:
    """Send GET request to Crowdin API and return parsed JSON."""
    req = urllib.request.Request(
        f"{BASE_API}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"API error {e.code} GET {path}: {e.read().decode()}")
        sys.exit(1)


def api_post(path: str, token: str, body: dict) -> dict:
    """Send POST request to Crowdin API and return parsed JSON."""
    req = urllib.request.Request(
        f"{BASE_API}{path}",
        method="POST",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"API error {e.code} POST {path}: {e.read().decode()}")
        sys.exit(1)


# ──────────────────────────────────────────────
# Step 4 & 5 — Export and download
# ──────────────────────────────────────────────

def get_export_url(token: str, project_id: str, language_id: str, approved_only: bool) -> str:
    """
    Trigger a translation export on Crowdin for one language and return the download URL.
    Crowdin builds the Android XML file server-side; the URL is valid for a short time.
    """
    body = {"targetLanguageId": language_id, "format": "android"}
    if approved_only:
        body["exportApprovedOnly"] = True
    resp = api_post(f"/projects/{project_id}/translations/exports", token, body)
    return resp["data"]["url"]


def download_and_save(url: str, dest_path: str, label: str, dry_run: bool):
    """Download a file from URL and write it to dest_path."""
    with urllib.request.urlopen(url, context=SSL_CONTEXT) as resp:
        content = resp.read()
    if dry_run:
        print(f"  [dry-run] Would write {len(content)} bytes → {label}")
    else:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(content)
        print(f"  Written → {label}")


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

def main():
    # Step 1 — load credentials
    load_env()

    parser = argparse.ArgumentParser(description="Download Crowdin translations into Android res folders")
    parser.add_argument("--token", "-T", default=os.environ.get("CROWDIN_TOKEN"))
    parser.add_argument("--project-id", "-i", default=os.environ.get("CROWDIN_PROJECT_ID"))
    parser.add_argument("--language", "-l", action="append", default=[], metavar="LANG",
                        help="Crowdin language ID(s) to download (e.g. vi, zh-CN). Default: all.")
    parser.add_argument("--export-only-approved", action="store_true",
                        help="Only include approved translations in the export")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be written without changing any files")
    args = parser.parse_args()

    if not args.token or not args.project_id:
        parser.error("--token and --project-id are required (or set them in scripts/.env)")

    # Step 2 — fetch project info (source language + target language list)
    print("Fetching project info...")
    project = api_get(f"/projects/{args.project_id}", args.token)["data"]

    # Step 3 — build language mapping: languageId → res folder name
    # Prefer twoLettersCode (e.g. "vi") for brevity; fall back to androidCode
    # (e.g. "zh-rCN") when multiple target languages share the same two-letter code.
    two_letter_counts = Counter(lang["twoLettersCode"] for lang in project["targetLanguages"])
    all_languages = {
        lang["id"]: (
            lang["twoLettersCode"] if two_letter_counts[lang["twoLettersCode"]] == 1
            else lang["androidCode"]
        )
        for lang in project["targetLanguages"]
    }

    # Determine which languages to download (default: all target languages)
    languages = args.language if args.language else list(all_languages.keys())

    # Warn about any unrecognised language codes passed via -l
    unknown = [l for l in languages if l not in all_languages]
    if unknown:
        print(f"Warning: {unknown} not in project target languages. Skipping.")
        languages = [l for l in languages if l in all_languages]

    # Step 4 — export and download source language → res/values/strings.xml
    source_lang = project["sourceLanguageId"]
    print(f"Exporting source '{source_lang}'...", end=" ", flush=True)
    source_url = get_export_url(args.token, args.project_id, source_lang, args.export_only_approved)
    print("done.")
    download_and_save(
        source_url,
        os.path.join(ANDROID_RES_DIR, "values", OUTPUT_FILENAME),
        f"values/{OUTPUT_FILENAME}",
        args.dry_run,
    )

    # Step 5 — export and download each target language → res/values-{folder}/strings.xml
    for lang in languages:
        folder = all_languages[lang]
        print(f"Exporting '{lang}' → values-{folder}/...", end=" ", flush=True)
        url = get_export_url(args.token, args.project_id, lang, args.export_only_approved)
        print("done.")
        download_and_save(
            url,
            os.path.join(ANDROID_RES_DIR, f"values-{folder}", OUTPUT_FILENAME),
            f"values-{folder}/{OUTPUT_FILENAME}",
            args.dry_run,
        )

    # Step 6 — validate all strings.xml files and offer to auto-fix errors
    if not args.dry_run:
        ok = validate_and_fix(os.path.abspath(ANDROID_RES_DIR))
        if not ok:
            sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    main()
