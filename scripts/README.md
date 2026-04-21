# Scripts

Tools for downloading and validating Android string translations from Crowdin.

## Setup

### Prerequisites

- Python 3.10+
- [Crowdin CLI](https://crowdin.github.io/crowdin-cli/) (`brew install crowdin`)
- `certifi` Python package (optional, fixes SSL on macOS): `pip install certifi`

### .env

Create `scripts/.env` with your Crowdin credentials:

```
# Crowdin API token (Personal Access Token)
CROWDIN_TOKEN=your_token_here

# Numeric project ID from Crowdin project settings
CROWDIN_PROJECT_ID=123456
```

This file is gitignored and never committed.

---

## Scripts

### `download_translations.py`

Downloads translations from a **string-based** Crowdin project via REST API (`POST /translations/exports` with `format=android`). Saves results directly as `strings.xml` into the correct `res/values-{lang}/` folders, then runs validation.

**Steps:**
1. Calls `GET /projects/{id}` to fetch target languages
2. Exports source language (`en`) → `res/values/strings.xml`
3. Exports each target language → `res/values-{lang}/strings.xml`
   - Uses `twoLettersCode` (e.g. `vi`) when unique across target languages
   - Falls back to `androidCode` (e.g. `zh-rCN`) when multiple languages share the same two-letter code
4. Runs `validate_strings.py` interactively

**Usage:**
```bash
python3 scripts/download_translations.py                   # all languages
python3 scripts/download_translations.py -l vi             # single language
python3 scripts/download_translations.py --export-only-approved
python3 scripts/download_translations.py --dry-run
```

---

### `cli_download_translations.py`

Downloads translations from a **string-based or file-based** Crowdin project via the Crowdin CLI using a bundle. The bundle exports all strings in Android XML format. Saves results into the correct `res/values-{lang}/` folders, then runs validation.

**Steps:**
1. Lists bundles via `crowdin bundle list`; creates `android-translations` bundle if not found
   - Bundle config: `--format android`, `--source /**`, `--translation /%two_letters_code%/strings.xml`, `--include-source-language`
2. Downloads bundle to a temp directory via `crowdin bundle download`
3. Moves files to res folders:
   - `en/strings.xml` → `res/values/strings.xml`
   - `{lang}/strings.xml` → `res/values-{lang}/strings.xml`
4. Temp directory is cleaned up automatically
5. Runs `validate_strings.py` interactively

**Usage:**
```bash
python3 scripts/cli_download_translations.py               # all languages
python3 scripts/cli_download_translations.py --export-only-approved
python3 scripts/cli_download_translations.py --dry-run
```

---

### `validate_strings.py`

Validates all `strings.xml` files under `app/src/main/res/values*/`. Can be run standalone or is called automatically by the download scripts.

**Checks:**

| Check | Severity | Impact |
|---|---|---|
| Invalid key characters (`&`, spaces, etc.) | ERROR | AAPT2 build error |
| Duplicate keys | ERROR | AAPT2 build error |
| Unescaped apostrophes | ERROR | AAPT2 build error |
| Format specifier count/type mismatch vs source | ERROR | Runtime crash |
| Orphaned keys (in translation but not in source) | ERROR | — |
| Empty values | WARNING | — |
| Missing translations (in source but not translated) | WARNING | — |

**Interactive prompt:**
After printing results, the script offers to automatically remove all keys with errors from every `strings.xml` file. Press `Enter` to apply or `Esc` to cancel.

**Usage:**
```bash
python3 scripts/validate_strings.py
python3 scripts/validate_strings.py --res-dir app/src/main/res
```
