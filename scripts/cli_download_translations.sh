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

crowdin download \
    --token "$CROWDIN_TOKEN" \
    --project-id "$CROWDIN_PROJECT_ID" \
    "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"

if [ "$DRY_RUN" = false ]; then
    python3 "$SCRIPT_DIR/validate_strings.py" \
        "$PROJECT_DIR/app/src/main/res"
fi

echo "Done."
