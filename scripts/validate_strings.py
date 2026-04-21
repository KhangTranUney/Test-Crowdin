#!/usr/bin/env python3
"""
Validate Android strings.xml files under res/values*/ directories.

Step 1 — Validate default file (values/strings.xml):
  Key checks   (buildable):  only letters, digits, dots, underscores allowed
  Content checks (buildable): unescaped apostrophes, malformed XML
  Content checks (crashable): format specifier type/count mismatch vs source

Step 2 — Validate each translation file with the same rules,
         plus cross-checks against the source.

Step 3 — Print all results, then ask [Enter] to remove error keys / [Esc] to cancel.

Usage:
    python3 validate_strings.py
    python3 validate_strings.py --res-dir ../app/src/main/res
"""

import argparse
import os
import re
import sys
import termios
import tty
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


SOURCE_DIR   = "values"
STRINGS_FILE = "strings.xml"

# Valid Android resource name: letters, digits, dots, underscores
_VALID_KEY_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9._]*$')

# Matches printf-style format specifiers: %s %d %f %1$s %2$d etc.
_FORMAT_SPEC_RE = re.compile(r'%(\d+\$)?[-+0 #]*(\d+)?(\.\d+)?[sdifetgGxXobc@%]')


# ──────────────────────────────────────────────
# Data
# ──────────────────────────────────────────────

@dataclass
class Issue:
    severity: str   # "error" | "warning"
    code: str
    message: str
    file: str
    key: str = ""


@dataclass
class ValidationResult:
    issues: list = field(default_factory=list)

    @property
    def errors(self):
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self):
        return [i for i in self.issues if i.severity == "warning"]

    def has_issues(self):
        return bool(self.issues)


# ──────────────────────────────────────────────
# Parsing
# ──────────────────────────────────────────────

def find_strings_files(res_dir: str) -> dict[str, str]:
    """Returns {folder_name: absolute_path} for every strings.xml found."""
    result = {}
    for entry in sorted(os.listdir(res_dir)):
        full = os.path.join(res_dir, entry, STRINGS_FILE)
        if (entry == SOURCE_DIR or entry.startswith("values-")) and os.path.isfile(full):
            result[entry] = full
    return result


def parse_strings(path: str) -> tuple[dict[str, str], list[str], str | None]:
    """
    Returns ({key: value}, [duplicate_keys], parse_error_or_None).
    Skips <string translatable="false">.
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        return {}, [], str(e)

    seen = {}
    duplicates = []
    for elem in tree.getroot().findall("string"):
        name = elem.get("name", "").strip()
        if not name or elem.get("translatable") == "false":
            continue
        value = (elem.text or "").strip()
        if name in seen:
            duplicates.append(name)
        else:
            seen[name] = value
    return seen, duplicates, None


# ──────────────────────────────────────────────
# Key checks
# ──────────────────────────────────────────────

def check_key(key: str, rel_file: str) -> list[Issue]:
    issues = []
    if not key:
        issues.append(Issue("error", "empty_key", "Empty key name", rel_file, key))
        return issues
    if not _VALID_KEY_RE.match(key):
        invalid = sorted(set(re.findall(r'[^A-Za-z0-9._]', key)))
        issues.append(Issue(
            "error", "invalid_key_chars",
            f"Key '{key}' contains invalid character(s) {invalid} — only letters, digits, '.' and '_' are allowed (AAPT2 build error)",
            rel_file, key,
        ))
    return issues


# ──────────────────────────────────────────────
# Content checks
# ──────────────────────────────────────────────

def extract_format_specs(value: str) -> list[str]:
    """Return list of format specifier types in order, e.g. ['s', 'd']."""
    return [m.group(0)[-1] for m in _FORMAT_SPEC_RE.finditer(value) if m.group(0) != "%%"]


def check_content(key: str, value: str, rel_file: str) -> list[Issue]:
    issues = []

    if not value:
        issues.append(Issue("warning", "empty_value",
                            f"Key '{key}' has an empty value", rel_file, key))
        return issues

    # Unescaped apostrophe (not inside a CDATA block, not preceded by backslash)
    # Android AAPT2 requires apostrophes to be escaped as \' unless the whole string is "double-quoted"
    stripped = re.sub(r'<!\[CDATA\[.*?\]\]>', '', value, flags=re.DOTALL)
    unescaped_apostrophes = re.findall(r"(?<!\\)'", stripped)
    if unescaped_apostrophes:
        issues.append(Issue(
            "error", "unescaped_apostrophe",
            f"Key '{key}' contains unescaped apostrophe(s) — use \\' or wrap in double quotes (AAPT2 build error)",
            rel_file, key,
        ))

    return issues


def check_content_vs_source(key: str, trans_value: str, source_value: str, rel_file: str) -> list[Issue]:
    """Check that format specifiers in a translation match the source."""
    issues = []
    src_specs  = extract_format_specs(source_value)
    tran_specs = extract_format_specs(trans_value)

    if len(tran_specs) != len(src_specs):
        issues.append(Issue(
            "error", "format_spec_count_mismatch",
            f"Key '{key}': source has {len(src_specs)} format specifier(s) {src_specs}, translation has {len(tran_specs)} {tran_specs} (runtime crash)",
            rel_file, key,
        ))
    else:
        for i, (s, t) in enumerate(zip(src_specs, tran_specs)):
            if s != t:
                issues.append(Issue(
                    "error", "format_spec_type_mismatch",
                    f"Key '{key}': specifier #{i+1} type mismatch — source '%{s}' vs translation '%{t}' (runtime crash)",
                    rel_file, key,
                ))
    return issues


# ──────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────

def validate_file(strings: dict[str, str], duplicates: list[str], rel_file: str,
                  source_strings: dict[str, str] | None = None) -> list[Issue]:
    issues = []

    # Duplicate keys
    for key in duplicates:
        issues.append(Issue("error", "duplicate_key",
                            f"Key '{key}' is duplicated (AAPT2 build error)", rel_file, key))

    for key, value in strings.items():
        issues += check_key(key, rel_file)
        issues += check_content(key, value, rel_file)

        if source_strings is not None:
            if key not in source_strings:
                issues.append(Issue("error", "orphaned_key",
                                    f"Key '{key}' not found in source — remove it", rel_file, key))
            else:
                issues += check_content_vs_source(key, value, source_strings[key], rel_file)

    if source_strings is not None:
        for key in source_strings:
            if key not in strings:
                issues.append(Issue("warning", "missing_translation",
                                    f"Key '{key}' is not translated", rel_file, key))

    return issues


def validate(res_dir: str) -> ValidationResult:
    result = ValidationResult()
    files = find_strings_files(res_dir)

    if SOURCE_DIR not in files:
        result.issues.append(Issue("error", "missing_source",
                                   "Source file values/strings.xml not found", f"{SOURCE_DIR}/{STRINGS_FILE}"))
        return result

    # Step 1 — validate source file
    src_strings, src_dups, src_err = parse_strings(files[SOURCE_DIR])
    rel_src = f"{SOURCE_DIR}/{STRINGS_FILE}"
    if src_err:
        result.issues.append(Issue("error", "parse_error", f"XML parse error: {src_err}", rel_src))
        return result
    result.issues += validate_file(src_strings, src_dups, rel_src)

    # Step 2 — validate each translation file
    for folder, path in files.items():
        if folder == SOURCE_DIR:
            continue
        rel = f"{folder}/{STRINGS_FILE}"
        t_strings, t_dups, t_err = parse_strings(path)
        if t_err:
            result.issues.append(Issue("error", "parse_error", f"XML parse error: {t_err}", rel))
            continue
        result.issues += validate_file(t_strings, t_dups, rel, source_strings=src_strings)

    return result


# ──────────────────────────────────────────────
# Fix
# ──────────────────────────────────────────────

def remove_keys_from_file(path: str, keys_to_remove: set[str]):
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return
    root = tree.getroot()
    for elem in root.findall("string"):
        if elem.get("name") in keys_to_remove:
            root.remove(elem)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="unicode", xml_declaration=True)


def remove_keys(res_dir: str, keys: set[str]):
    files = find_strings_files(res_dir)
    for folder, path in files.items():
        remove_keys_from_file(path, keys)
        print(f"  Removed from {folder}/{STRINGS_FILE}")


# ──────────────────────────────────────────────
# Terminal helpers
# ──────────────────────────────────────────────

def read_key() -> str:
    fd = sys.stdin.fileno()
    try:
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except termios.error:
        ch = sys.stdin.readline().strip()
        return "enter" if ch == "" else "esc" if ch.lower() in ("esc", "q") else ch
    if ch in ("\r", "\n"):
        return "enter"
    if ch == "\x1b":
        return "esc"
    return ch


# ──────────────────────────────────────────────
# Interactive flow
# ──────────────────────────────────────────────

def print_issues(result: ValidationResult):
    if not result.has_issues():
        print("  No issues found.")
        return

    # Group by file
    by_file: dict[str, list[Issue]] = {}
    for issue in result.issues:
        by_file.setdefault(issue.file, []).append(issue)

    for file, issues in by_file.items():
        print(f"\n  {file}")
        for issue in issues:
            tag = "ERROR" if issue.severity == "error" else "WARN "
            print(f"    [{tag}] {issue.message}")

    print(f"\n  Total: {len(result.errors)} error(s), {len(result.warnings)} warning(s)")


def run_interactive(res_dir: str) -> bool:
    """
    Validates and interactively offers to remove keys with errors.
    Returns True to continue, False if cancelled.
    """
    print("\n── Validation ─────────────────────────────")
    print(f"  Step 1: Validating {SOURCE_DIR}/{STRINGS_FILE}...")
    print(f"  Step 2: Validating translation files...")
    result = validate(res_dir)

    print("\n── Results ────────────────────────────────")
    print_issues(result)

    if not result.has_issues():
        return True

    removable = {i.key for i in result.errors if i.key}
    if not removable:
        print("\n  No keys to remove. Press [Enter] to continue or [Esc] to cancel.")
    else:
        print(f"\n  {len(removable)} key(s) with errors will be removed from all strings.xml files.")
        print("  [Enter] Remove and continue   [Esc] Cancel")

    key = read_key()
    print()
    if key == "esc":
        print("  Cancelled.")
        return False

    if removable:
        remove_keys(res_dir, removable)
        print("  Done.")

    return True


# ──────────────────────────────────────────────
# Standalone entry point
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Validate Android strings.xml files")
    parser.add_argument(
        "--res-dir", "-r",
        default=os.path.join(os.path.dirname(__file__), "..", "app", "src", "main", "res"),
    )
    args = parser.parse_args()
    ok = run_interactive(os.path.abspath(args.res_dir))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
