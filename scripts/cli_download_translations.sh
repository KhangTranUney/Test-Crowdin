#!/usr/bin/env bash
# Download translations from Crowdin using the CLI.
# Requires a file-based Crowdin project and crowdin.yml in the project root.
#
# Usage:
#   ./download_translations.sh
#   ./download_translations.sh -l vi
#   ./download_translations.sh --export-only-approved --dry-run

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

# Crowdin CLI reads CROWDIN_PERSONAL_TOKEN
export CROWDIN_PERSONAL_TOKEN="${CROWDIN_TOKEN:-}"

: "${CROWDIN_PERSONAL_TOKEN:?CROWDIN_TOKEN not set in scripts/.env}"
: "${CROWDIN_PROJECT_ID:?CROWDIN_PROJECT_ID not set in scripts/.env}"

# Parse arguments
EXTRA_ARGS=()
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -l|--language) EXTRA_ARGS+=(--language "$2"); shift 2 ;;
        --export-only-approved) EXTRA_ARGS+=(--export-only-approved); shift ;;
        --dry-run) DRY_RUN=true; EXTRA_ARGS+=(--dryrun); shift ;;
        -h|--help)
            echo "Usage: $0 [-l LANG] [--export-only-approved] [--dry-run]"
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

cd "$PROJECT_DIR"

# Download source file
crowdin download sources \
    --token "$CROWDIN_TOKEN" \
    --project-id "$CROWDIN_PROJECT_ID" \
    --source "/Default.csv" \
    --translation "/%two_letters_code%/Default.csv"

# Move source into crowdin_cli/source/en/
if [ "$DRY_RUN" = false ] && [ -f "$PROJECT_DIR/Default.csv" ]; then
    mkdir -p "$PROJECT_DIR/crowdin_cli/source/en"
    mv "$PROJECT_DIR/Default.csv" "$PROJECT_DIR/crowdin_cli/source/en/Default.csv"
    echo "  Moved → crowdin_cli/source/en/Default.csv"
fi

# Download translations
crowdin download \
    --token "$CROWDIN_TOKEN" \
    --project-id "$CROWDIN_PROJECT_ID" \
    --source "/Default.csv" \
    --translation "/%two_letters_code%/Default.csv" \
    --all \
    "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"

# Move translations into crowdin_cli/source/{lang}/
if [ "$DRY_RUN" = false ]; then
    for f in "$PROJECT_DIR"/*/Default.csv; do
        lang_dir=$(basename "$(dirname "$f")")
        dest="$PROJECT_DIR/crowdin_cli/source/$lang_dir/Default.csv"
        mkdir -p "$(dirname "$dest")"
        mv "$f" "$dest"
        rmdir "$PROJECT_DIR/$lang_dir" 2>/dev/null || true
        echo "  Moved → crowdin_cli/source/$lang_dir/Default.csv"
    done
fi

# Download bundle
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

mkdir -p "$PROJECT_DIR/crowdin_cli/bundle"
crowdin bundle download "$BUNDLE_ID" \
    --token "$CROWDIN_TOKEN" \
    --project-id "$CROWDIN_PROJECT_ID" \
    --base-path "$PROJECT_DIR/crowdin_cli/bundle" \
    "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"

echo "Done."
