#!/usr/bin/env python3
"""Lint: the application services must not publish ports in the compose files (AL06-02).

CRM, portal and API are reachable only through the Traefik network. A `ports:` entry (or
`network_mode: host`) on api, web-crm or web-portal would bypass Traefik and with it the
X-Forwarded-For handling and the rate limits (docs/runbooks/server-setup.md, "Vertrauenswürdige
Proxys"). Compose merges `ports` lists of the base and the overlay file, so both are checked.
Standard library only (line based reading of the services block).

Usage: python3 scripts/check_compose_exposure.py [--root <repo root>] [files ...]
Exit code 1 on any finding, 0 otherwise.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROTECTED = ("api", "web-crm", "web-portal")
DEFAULT_FILES = ("infra/compose.yaml", "infra/compose.prod.yaml")
FORBIDDEN_KEYS = ("ports", "network_mode")


def find_violations(text: str, protected: tuple[str, ...] = PROTECTED) -> list[str]:
    """Return findings as "service: key" strings for the protected services."""
    findings: list[str] = []
    in_services = False
    service: str | None = None
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            in_services = line.startswith("services:")
            service = None
            continue
        if not in_services:
            continue
        if indent == 2:
            m = re.match(r"\s{2}([A-Za-z0-9_.-]+):\s*$", line)
            service = m.group(1) if m else None
            continue
        if indent == 4 and service in protected:
            m = re.match(r"\s{4}([A-Za-z_]+):", line)
            if not m:
                continue
            key = m.group(1)
            if key == "ports" or (key == "network_mode" and "host" in line):
                findings.append(f"{service}: {key}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    root = Path(args.root)
    exit_code = 0
    for name in args.files or DEFAULT_FILES:
        path = root / name
        if not path.is_file():
            sys.stderr.write(f"{name}: file not found\n")
            exit_code = 1
            continue
        for finding in find_violations(path.read_text(encoding="utf-8")):
            sys.stdout.write(f"{name}: {finding} (published port or host network is not allowed)\n")
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
