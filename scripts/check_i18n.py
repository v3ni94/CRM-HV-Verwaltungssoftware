#!/usr/bin/env python3
"""Consistency check for the next-intl message catalogues.

For each web app the German (de.json) and English (en.json) catalogues are compared
recursively. Reported are keys that exist in only one of the two files, German texts
containing dashes as sentence punctuation (U+2013 en dash, U+2014 em dash) and empty
values in either file. Exit code 1 on any finding, 0 otherwise. Standard library only.

Usage: python3 scripts/check_i18n.py [--root <repo root>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

APPS = ("apps/web-crm", "apps/web-portal")
LOCALES = ("de", "en")
DASHES = {"–": "U+2013 (en dash)", "—": "U+2014 (em dash)"}


def flatten(node: object, prefix: str = "") -> dict[str, object]:
    """Flatten a nested message object into dotted keys -> leaf values."""
    out: dict[str, object] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                if not value:
                    out[path] = value
                else:
                    out.update(flatten(value, path))
            else:
                out[path] = value
    return out


def load(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"{path}: file not found")
        return None
    except json.JSONDecodeError as exc:
        print(f"{path}: invalid JSON ({exc})")
        return None
    if not isinstance(data, dict):
        print(f"{path}: top level must be an object")
        return None
    return flatten(data)


def check_app(root: Path, app: str) -> list[str]:
    findings: list[str] = []
    catalogues: dict[str, dict[str, object]] = {}
    for locale in LOCALES:
        path = root / app / "messages" / f"{locale}.json"
        flat = load(path)
        if flat is None:
            findings.append(f"{app}: {locale}.json could not be read")
            continue
        catalogues[locale] = flat
        for key, value in flat.items():
            if value == "" or value == {} or value is None:
                findings.append(f"{app}/messages/{locale}.json: empty value at '{key}'")
            elif not isinstance(value, str):
                findings.append(
                    f"{app}/messages/{locale}.json: value at '{key}' is not a string"
                )
    de = catalogues.get("de")
    en = catalogues.get("en")
    if de is not None:
        for key, value in de.items():
            if not isinstance(value, str):
                continue
            for char, name in DASHES.items():
                if char in value:
                    findings.append(f"{app}/messages/de.json: dash {name} in '{key}': {value!r}")
    if de is not None and en is not None:
        only_de = sorted(set(de) - set(en))
        only_en = sorted(set(en) - set(de))
        for key in only_de:
            findings.append(f"{app}: key only in de.json: {key}")
        for key in only_en:
            findings.append(f"{app}: key only in en.json: {key}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parent.parent),
        help="repository root (default: parent of the scripts directory)",
    )
    args = parser.parse_args()
    root = Path(args.root)
    all_findings: list[str] = []
    for app in APPS:
        all_findings.extend(check_app(root, app))
    for line in all_findings:
        print(line)
    if all_findings:
        print(f"i18n check: {len(all_findings)} finding(s)")
        return 1
    print("i18n check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
