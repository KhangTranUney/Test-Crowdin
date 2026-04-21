#!/usr/bin/env python3
"""
Validate Android strings.xml files under res/values*/ directories.

Checks:
  - Duplicate keys within the same file
  - Empty string values
  - Keys present in translations but missing from the source (orphaned)
  - Keys present in source but missing from a translation file

Usage (standalone):
    python3 validate_strings.py
    python3 validate_strings.py --res-dir ../app/src/main/res
"""

import argparse
import os
import sys
import termios
import tty
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


SOURCE_DIR = "values"
STRINGS_FILE = "strings.xml"


# ──────────────────────────────────────────────
# Data
# ──────────────────────────────────────────────

@dataclass
class Issue:
    severity: str          # "error" | "warning"
    code: str              # machine-readable code
    message: str           # human-readable message
    file: str              # relative path to the file
    key: str = ""          # affected string key (if any)


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
    """Returns {relative_folder: absolute_path} for every strings.xml found."""
    result = {}
    for entry in sorted(os.listdir(res_dir)):
        full = os.path.join(res_dir, entry, STRINGS_FILE)
        if (entry == SOURCE_DIR or entry.startswith("values-")) and os.path.isfile(full):
            result[entry] = full
    return result


def parse_strings(path: str) -> tuple[dict[str, str], list[str]]:
    """
    Returns ({key: value}, [duplicate_keys]) from a strings.xml file.
    Skips <string translatable="false">.
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return {}, []

    seen = {}
    duplicates = []
    for elem in tree.getroot().findall("string"):
        name = elem.get("name", "").strip()
        if not name:
            continue
        if elem.get("translatable") == "false":
            continue
        value = (elem.text or "").strip()
        if name in seen:
            duplicates.append(name)
        else:
            seen[name] = value
    return seen, duplicates


# ──────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────

def validate(res_dir: str) -> ValidationResult:
    result = ValidationResult()
    files = find_strings_files(res_dir)

    if SOURCE_DIR not in files:
        result.issues.append(Issue(
            severity="error",
            code="missing_source",
            message=f"Source file not found: {os.path.join(res_dir, SOURCE_DIR, STRINGS_FILE)}",
            file=f"{SOURCE_DIR}/{STRINGS_FILE}",
        ))
        return result

    source_strings, source_dups = parse_strings(files[SOURCE_DIR])

    # Duplicates in source
    for key in source_dups:
        result.issues.append(Issue(
            severity="error", code="duplicate_key",
            message=f"Duplicate key '{key}'",
            file=f"{SOURCE_DIR}/{STRINGS_FILE}", key=key,
        ))

    # Empty values in source
    for key, value in source_strings.items():
        if not value:
            result.issues.append(Issue(
                severity="warning", code="empty_value",
                message=f"Empty value for key '{key}'",
                file=f"{SOURCE_DIR}/{STRINGS_FILE}", key=key,
            ))

    # Validate each translation file
    for folder, path in files.items():
        if folder == SOURCE_DIR:
            continue
        rel = f"{folder}/{STRINGS_FILE}"
        trans_strings, trans_dups = parse_strings(path)

        # Duplicates in translation
        for key in trans_dups:
            result.issues.append(Issue(
                severity="error", code="duplicate_key",
                message=f"Duplicate key '{key}'",
                file=rel, key=key,
            ))

        # Orphaned keys (in translation but not in source)
        for key in trans_strings:
            if key not in source_strings:
                result.issues.append(Issue(
                    severity="error", code="orphaned_key",
                    message=f"Key '{key}' not found in source",
                    file=rel, key=key,
                ))

        # Missing translations (in source but not in translation)
        for key in source_strings:
            if key not in trans_strings:
                result.issues.append(Issue(
                    severity="warning", code="missing_translation",
                    message=f"Key '{key}' missing in translation",
                    file=rel, key=key,
                ))

    return result


# ──────────────────────────────────────────────
# Fix
# ──────────────────────────────────────────────

def remove_keys_from_file(path: str, keys_to_remove: set[str]):
    """Remove <string> entries with the given names from a strings.xml file."""
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return
    root = tree.getroot()
    for elem in root.findall("string"):
        if elem.get("name") in keys_to_remove:
            root.remove(elem)
    ET.indent(tree, space="    ")
    tree.write(path, encoding="unicode", xml_declaration=True)


def remove_keys(res_dir: str, keys: set[str]):
    """Remove keys from source and all translation strings.xml files."""
    files = find_strings_files(res_dir)
    for folder, path in files.items():
        remove_keys_from_file(path, keys)
        print(f"  Removed {len(keys)} key(s) from {folder}/{STRINGS_FILE}")


# ──────────────────────────────────────────────
# Terminal helpers
# ──────────────────────────────────────────────

def read_key() -> str:
    """Read a single keypress. Returns 'enter', 'esc', or the character."""
    fd = sys.stdin.fileno()
    try:
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except termios.error:
        # Fallback for non-interactive terminals: read a full line
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

    for issue in result.issues:
        prefix = "ERROR  " if issue.severity == "error" else "WARN   "
        key_str = f" [{issue.key}]" if issue.key else ""
        print(f"  {prefix} {issue.file}{key_str}: {issue.message}")

    print(f"\n  {len(result.errors)} error(s), {len(result.warnings)} warning(s)")


def run_interactive(res_dir: str) -> bool:
    """
    Validates strings.xml files and interactively offers to remove problematic keys.
    Returns True if the caller should continue, False if the user cancelled.
    """
    print("\nValidating strings.xml files...")
    result = validate(res_dir)
    print_issues(result)

    if not result.has_issues():
        return True

    # Collect keys that can be removed (errors only — warnings are informational)
    removable_keys = {i.key for i in result.errors if i.key}
    if not removable_keys:
        return True

    print(f"\nRemovable keys (errors): {sorted(removable_keys)}")
    print("Remove these keys from all strings.xml files?")
    print("  [Enter] Remove and continue   [Esc] Cancel")

    key = read_key()
    print()

    if key == "esc":
        print("Cancelled.")
        return False

    remove_keys(res_dir, removable_keys)
    print("Keys removed.")
    return True


# ──────────────────────────────────────────────
# Standalone entry point
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Validate Android strings.xml files")
    parser.add_argument(
        "--res-dir", "-r",
        default=os.path.join(os.path.dirname(__file__), "..", "app", "src", "main", "res"),
        help="Path to the Android res/ directory",
    )
    args = parser.parse_args()
    res_dir = os.path.abspath(args.res_dir)
    ok = run_interactive(res_dir)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
