#!/usr/bin/env bash
# Download Android translations from Crowdin using a bundle.
#
# Usage:
#   ./cli_download_translations.sh
#   ./cli_download_translations.sh --export-only-approved
#   ./cli_download_translations.sh --dry-run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/.."

# Load .env
if [ -f "$SCRIPT_DIR/.env" ]; then
    while IFS='=' read -r key value || [[ -n "$key" ]]; do
        [[ "$key" =~ ^[[:space:]]*# || -z "$key" ]] && continue
        export "$key=$value"
    done < "$SCRIPT_DIR/.env"
fi

: "${CROWDIN_TOKEN:?CROWDIN_TOKEN not set in scripts/.env}"
: "${CROWDIN_PROJECT_ID:?CROWDIN_PROJECT_ID not set in scripts/.env}"

# Parse arguments
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --export-only-approved) EXTRA_ARGS+=(--export-only-approved); shift ;;
        --dry-run) EXTRA_ARGS+=(--dryrun); shift ;;
        -h|--help)
            echo "Usage: $0 [--export-only-approved] [--dry-run]"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

cd "$PROJECT_DIR"

# Find or create bundle
BUNDLE_NAME="android-translations"
BUNDLE_ID=$(crowdin bundle list \
    --token "$CROWDIN_TOKEN" \
    --project-id "$CROWDIN_PROJECT_ID" \
    --plain --no-progress 2>/dev/null \
    | awk -v name="$BUNDLE_NAME" '$2 == name { print $1; exit }')

if [ -z "$BUNDLE_ID" ]; then
    echo "Bundle '$BUNDLE_NAME' not found, creating..."
    BUNDLE_ID=$(crowdin bundle add "$BUNDLE_NAME" \
        --token "$CROWDIN_TOKEN" \
        --project-id "$CROWDIN_PROJECT_ID" \
        --format android \
        --source "/**" \
        --translation "/%two_letters_code%/strings.xml" \
        --include-source-language \
        --plain --no-progress 2>/dev/null \
        | awk '{ print $1 }')
    echo "  Created bundle ID: $BUNDLE_ID"
fi

TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

crowdin bundle download "$BUNDLE_ID" \
    --token "$CROWDIN_TOKEN" \
    --project-id "$CROWDIN_PROJECT_ID" \
    --base-path "$TEMP_DIR" \
    "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"

# Move bundle files to Android res folders
SOURCE_LANG="en"
for f in "$TEMP_DIR"/*/strings.xml; do
    lang=$(basename "$(dirname "$f")")
    if [ "$lang" = "$SOURCE_LANG" ]; then
        dest="$PROJECT_DIR/app/src/main/res/values/strings.xml"
    else
        dest="$PROJECT_DIR/app/src/main/res/values-$lang/strings.xml"
    fi
    mkdir -p "$(dirname "$dest")"
    mv "$f" "$dest"
    echo "  Moved → res/$(basename "$(dirname "$dest")")/strings.xml"
done

echo "Done."
