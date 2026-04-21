#!/usr/bin/env python3
"""
Download translations from a Crowdin string-based project via REST API
and copy Android strings XML files into res/values-{lang}/ directories.

Usage:
    python3 download_translations.py
    python3 download_translations.py -l vi
    python3 download_translations.py --export-only-approved --dry-run
"""

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

from validate_strings import run_interactive as validate_and_fix

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

BASE_API = "https://api.crowdin.com/api/v2"

ANDROID_RES_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "src", "main", "res")
OUTPUT_FILENAME = "strings.xml"


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


def api_get(path: str, token: str) -> dict:
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


def export_language(token: str, project_id: str, language_id: str, approved_only: bool) -> str:
    """Trigger an export and return the download URL."""
    body = {"targetLanguageId": language_id, "format": "android"}
    if approved_only:
        body["exportApprovedOnly"] = True
    resp = api_post(f"/projects/{project_id}/translations/exports", token, body)
    return resp["data"]["url"]


def download_xml(url: str) -> str:
    with urllib.request.urlopen(url, context=SSL_CONTEXT) as resp:
        return resp.read().decode("utf-8")


def fetch_source_xml(token: str, project_id: str) -> str:
    """Fetch all source strings and build an Android strings.xml."""
    items = []
    offset = 0
    while True:
        resp = api_get(f"/projects/{project_id}/strings?limit=500&offset={offset}", token)
        page = resp.get("data", [])
        items.extend(item["data"] for item in page)
        if len(page) < 500:
            break
        offset += 500

    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<resources>"]
    for s in items:
        key = s["identifier"]
        text = (s.get("text") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        key_escaped = key.replace("&", "&amp;")
        comment = f' comment="{s["context"]}"' if s.get("context") else ""
        lines.append(f'    <string name="{key_escaped}"{comment}>{text}</string>')
    lines.append("</resources>")
    return "\n".join(lines)


def write_or_print(xml: str, dest_path: str, label: str, dry_run: bool):
    if dry_run:
        print(f"\n--- [dry-run] {label} ---")
        print(xml[:500] + ("..." if len(xml) > 500 else ""))
    else:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(xml)
        print(f"  Written → {label}")


def main():
    load_env()

    parser = argparse.ArgumentParser(description="Download Crowdin translations into Android res folders")
    parser.add_argument("--token", "-T", default=os.environ.get("CROWDIN_TOKEN"))
    parser.add_argument("--project-id", "-i", default=os.environ.get("CROWDIN_PROJECT_ID"))
    parser.add_argument("--language", "-l", action="append", default=[], metavar="LANG",
                        help="Crowdin language code(s) to download. Default: all target languages.")
    parser.add_argument("--export-only-approved", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print XML without writing files")
    args = parser.parse_args()

    if not args.token or not args.project_id:
        parser.error("--token and --project-id are required (or set them in scripts/.env)")

    project = api_get(f"/projects/{args.project_id}", args.token)["data"]
    all_languages = {lang["id"]: lang["androidCode"] for lang in project["targetLanguages"]}
    languages = args.language if args.language else list(all_languages.keys())

    unknown = [l for l in languages if l not in all_languages]
    if unknown:
        print(f"Warning: {unknown} not in project target languages. Skipping.")
        languages = [l for l in languages if l in all_languages]

    # Download source language → values/strings.xml
    print(f"Exporting source '{project['sourceLanguageId']}'...", end=" ", flush=True)
    source_xml = fetch_source_xml(args.token, args.project_id)
    print("done.")
    write_or_print(
        source_xml,
        os.path.join(ANDROID_RES_DIR, "values", OUTPUT_FILENAME),
        f"values/{OUTPUT_FILENAME}",
        args.dry_run,
    )

    # Download each target language → values-{androidCode}/strings.xml
    for lang in languages:
        android_code = all_languages[lang]  # e.g. "vi-rVN", "zh-rCN"
        print(f"Exporting '{lang}' ({android_code})...", end=" ", flush=True)
        url = export_language(args.token, args.project_id, lang, args.export_only_approved)
        xml = download_xml(url)
        print("done.")
        write_or_print(
            xml,
            os.path.join(ANDROID_RES_DIR, f"values-{android_code}", OUTPUT_FILENAME),
            f"values-{android_code}/{OUTPUT_FILENAME}",
            args.dry_run,
        )

    if not args.dry_run:
        ok = validate_and_fix(os.path.abspath(ANDROID_RES_DIR))
        if not ok:
            sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    main()
