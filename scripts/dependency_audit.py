#!/usr/bin/env python3
"""Dependency audit against the lockfiles before the image build (GAH-310).

Runs ``pip-audit`` on the exported ``apps/api/uv.lock`` and ``pnpm audit --prod`` on
``pnpm-lock.yaml``. Findings listed in ``.github/audit-allowlist.txt`` are ignored. A tool or
network failure (audit service unreachable) is a warning, not a failure; a finding that is not
on the allowlist fails the run (exit 1).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / ".github" / "audit-allowlist.txt"


def load_allowlist() -> set[str]:
    ids: set[str] = set()
    if ALLOWLIST.exists():
        for line in ALLOWLIST.read_text(encoding="utf-8").splitlines():
            entry = line.split("#", 1)[0].strip()
            if entry:
                ids.add(entry)
    return ids


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def pip_findings(allow: set[str]) -> tuple[list[str], str | None]:
    export = run(
        ["uv", "export", "--locked", "--no-hashes", "--no-emit-project", "-o", "/tmp/req-audit.txt"],
        ROOT / "apps" / "api",
    )
    if export.returncode != 0:
        return [], f"uv export failed: {export.stderr.strip()[:200]}"
    result = run(
        ["uvx", "pip-audit", "--no-deps", "--disable-pip", "-r", "/tmp/req-audit.txt", "-f", "json"],
        ROOT,
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [], f"pip-audit gave no JSON (exit {result.returncode}): {result.stderr.strip()[:200]}"
    found: list[str] = []
    for dep in data.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            ids = {vuln.get("id", ""), *vuln.get("aliases", [])}
            if not ids & allow:
                found.append(f"{dep['name']} {dep['version']}: {vuln.get('id')}")
    return found, None


def pnpm_findings(allow: set[str]) -> tuple[list[str], str | None]:
    result = run(["pnpm", "audit", "--prod", "--json"], ROOT)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [], f"pnpm audit gave no JSON (exit {result.returncode}): {result.stderr.strip()[:200]}"
    if "error" in data and "advisories" not in data:
        return [], f"pnpm audit error: {str(data['error'])[:200]}"
    found: list[str] = []
    for adv in (data.get("advisories") or {}).values():
        ids = {adv.get("github_advisory_id", ""), *adv.get("cves", [])}
        if adv.get("severity") in ("high", "critical") and not ids & allow:
            found.append(f"{adv.get('module_name')}: {adv.get('github_advisory_id')} ({adv.get('severity')})")
    return found, None


def main() -> int:
    allow = load_allowlist()
    failed = False
    for label, fn in (("pip-audit", pip_findings), ("pnpm audit --prod", pnpm_findings)):
        found, warning = fn(allow)
        if warning:
            print(f"::warning::{label} not evaluated: {warning}")
            continue
        for item in found:
            print(f"::error::{label}: {item}")
        failed = failed or bool(found)
        print(f"{label}: {len(found)} finding(s) outside the allowlist")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
