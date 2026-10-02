#!/usr/bin/env python3
"""Sets or checks the version everywhere it is kept (GAI-111, GAI-112, CLAUDE.md section 10).

Source of truth: ``VERSION``. ``--check`` verifies that ``VERSION``, the first entry of
``CHANGELOG.md`` and the first entry of ``apps/web-crm/src/lib/changelog.ts`` agree;
``--manifests`` also compares ``apps/api/pyproject.toml`` and both ``package.json`` files.
``bump_version.py <X.Y.Z>`` writes ``VERSION``, ``pyproject.toml`` and the ``package.json``
files; the changelog entries (date, list of changes) are written by hand and never by this
script, the log is never changed retroactively.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
PACKAGE_JSONS = ("apps/web-crm/package.json", "apps/web-portal/package.json")
PYPROJECT = "apps/api/pyproject.toml"
_PKG_RE = re.compile(r'^(\s*"version"\s*:\s*)"([^"]*)"', re.M)
_TOML_RE = re.compile(r'^(version\s*=\s*)"([^"]*)"', re.M)


def read_version(root: Path = ROOT) -> str:
    return (root / "VERSION").read_text(encoding="utf-8").strip()


def changelog_md_first(root: Path = ROOT) -> str | None:
    m = re.search(r"^## (\d+\.\d+\.\d+)\b", (root / "CHANGELOG.md").read_text("utf-8"), re.M)
    return m.group(1) if m else None


def changelog_ts_first(root: Path = ROOT) -> str | None:
    text = (root / "apps/web-crm/src/lib/changelog.ts").read_text("utf-8")
    m = re.search(r'version:\s*"(\d+\.\d+\.\d+)"', text)
    return m.group(1) if m else None


def file_version(path: Path, pattern: re.Pattern[str]) -> str | None:
    m = pattern.search(path.read_text("utf-8"))
    return m.group(2) if m else None


def check(root: Path = ROOT, *, manifests: bool = False) -> list[str]:
    current = read_version(root)
    problems: list[str] = []
    if not SEMVER.match(current):
        problems.append(f"VERSION is not MAJOR.MINOR.PATCH: {current!r}")
    for label, value in (
        ("CHANGELOG.md first entry", changelog_md_first(root)),
        ("changelog.ts first entry", changelog_ts_first(root)),
        *(
            [
                (PYPROJECT, file_version(root / PYPROJECT, _TOML_RE)),
                *((p, file_version(root / p, _PKG_RE)) for p in PACKAGE_JSONS),
            ]
            if manifests
            else []
        ),
    ):
        if value != current:
            problems.append(f"{label}: {value!r} differs from VERSION {current!r}")
    return problems


def bump(new: str, root: Path = ROOT) -> None:
    if not SEMVER.match(new):
        raise SystemExit(f"bump_version: {new!r} is not MAJOR.MINOR.PATCH")
    (root / "VERSION").write_text(new + "\n", encoding="utf-8")
    for rel, pattern in ((PYPROJECT, _TOML_RE), *((p, _PKG_RE) for p in PACKAGE_JSONS)):
        path = root / rel
        text = pattern.sub(lambda m: f'{m.group(1)}"{new}"', path.read_text("utf-8"), count=1)
        path.write_text(text, "utf-8")
    print(  # noqa: T201
        f"bump_version: set {new}; now add the entry with date and changes to CHANGELOG.md "
        "and apps/web-crm/src/lib/changelog.ts (first position)."
    )


def main(argv: list[str]) -> int:
    if argv in (["--check"], ["--check", "--manifests"], []):
        problems = check(manifests="--manifests" in argv)
        for p in problems:
            print(f"bump_version: {p}", file=sys.stderr)  # noqa: T201
        return 1 if problems else 0
    if len(argv) == 1 and not argv[0].startswith("-"):
        bump(argv[0])
        return 0
    print("usage: bump_version.py [--check [--manifests] | X.Y.Z]", file=sys.stderr)  # noqa: T201
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
