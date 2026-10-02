#!/usr/bin/env python3
"""Conventional Commits check without npm (GAI-113, CLAUDE.md section 4 rule 12).

Usage: ``check_commits.py [<git range>]`` (default ``origin/main..HEAD``); ``--message <text>``
checks one message. Format: ``type(scope)!: description`` with a known type, an optional scope,
a non empty description and a header of at most 100 characters. Merge commits, ``fixup!`` and
``squash!`` commits are ignored. Exit 1 on a violation.
"""

from __future__ import annotations

import re
import subprocess
import sys

TYPES = (
    "feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert",
)  # fmt: skip
HEADER = re.compile(rf"^(?:{'|'.join(TYPES)})(?:\([a-z0-9][a-z0-9._/-]*\))?!?: \S.*$")
MAX_HEADER = 100


def check_message(message: str) -> str | None:
    """Returns a problem description or None."""
    header = message.strip().splitlines()[0] if message.strip() else ""
    if header.startswith(("Merge ", "fixup! ", "squash! ", "Revert ")):
        return None
    if not HEADER.match(header):
        return f"not a Conventional Commit header: {header!r}"
    if len(header) > MAX_HEADER:
        return f"header longer than {MAX_HEADER} characters ({len(header)})"
    return None


def main(argv: list[str]) -> int:
    if argv[:1] == ["--message"] and len(argv) == 2:
        problem = check_message(argv[1])
        if problem:
            print(f"check_commits: {problem}", file=sys.stderr)  # noqa: T201
        return 1 if problem else 0
    rng = argv[0] if argv else "origin/main..HEAD"
    git = "git"
    out = subprocess.run(  # noqa: S603
        [git, "log", "--format=%H%x1f%B%x1e", rng], capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        print(f"check_commits: git log {rng} failed: {out.stderr.strip()}", file=sys.stderr)  # noqa: T201
        return 2
    bad = 0
    for record in filter(None, (r.strip() for r in out.stdout.split("\x1e"))):
        sha, _, body = record.partition("\x1f")
        problem = check_message(body)
        if problem:
            bad += 1
            print(f"check_commits: {sha[:10]} {problem}", file=sys.stderr)  # noqa: T201
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
