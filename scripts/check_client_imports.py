#!/usr/bin/env python3
"""Guard against calling "use client" exports from React Server Components.

Next.js turns every export of a module marked "use client" into a client reference when it is
imported from server code. Rendering such an export as a component (`<Badge />`) is fine, but
calling it (`asAttention(x)`), indexing it (`BORDER[x]`) or reading a property of it only fails
at runtime in the production build ("Attempted to call asAttention() from the server but
asAttention is on the client", incident 27.09.2026, /tickets). The dev server, vitest and tsc
do not catch this.

The script walks the server module graph of each Next.js app: it starts at the route files of
the app router (page, layout, template, default, loading, error, not-found, route) that carry
no "use client" directive and follows relative and "@/" imports into further files without the
directive. In every such server module it inspects the named imports that come from a
"use client" module and reports each imported value that is used other than as a JSX tag
(`name(`, `name[`, `name.`). Type-only imports are ignored. Standard library only.

Usage: python3 scripts/check_client_imports.py [--root <repo root>] [--app apps/web-crm ...]
Exit code 1 on any finding, 0 otherwise.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

APPS = ("apps/web-crm", "apps/web-portal")
ROUTE_FILES = ("page", "layout", "template", "default", "loading", "error", "not-found", "route")
EXTENSIONS = (".tsx", ".ts", ".jsx", ".js")

DIRECTIVE_RE = re.compile(r'^\s*(?://[^\n]*\n|/\*.*?\*/\s*)*\s*["\']use client["\']', re.S)
IMPORT_RE = re.compile(
    r'^import\s+(?P<type>type\s+)?(?P<clause>[^;]*?)\s+from\s+["\'](?P<spec>[^"\']+)["\']\s*;?',
    re.M,
)
COMMENT_RE = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)


def has_use_client(source: str) -> bool:
    return DIRECTIVE_RE.match(source) is not None


def strip_comments(source: str) -> str:
    return COMMENT_RE.sub("", source)


def resolve(spec: str, importer: Path, src_root: Path) -> Path | None:
    if spec.startswith("@/"):
        base = src_root / spec[2:]
    elif spec.startswith("."):
        base = (importer.parent / spec).resolve()
    else:
        return None
    for ext in EXTENSIONS:
        candidate = base.with_suffix(base.suffix + ext) if base.suffix not in EXTENSIONS else base
        if candidate.is_file():
            return candidate
    for ext in EXTENSIONS:
        candidate = base / f"index{ext}"
        if candidate.is_file():
            return candidate
    return None


def named_values(clause: str) -> list[str]:
    """Local names of the non-type named imports in an import clause."""
    match = re.search(r"\{(.*)\}", clause, re.S)
    if not match:
        return []
    names: list[str] = []
    for part in match.group(1).split(","):
        item = part.strip()
        if not item or item.startswith("type "):
            continue
        local = item.split(" as ")[-1].strip()
        if local:
            names.append(local)
    return names


def used_as_value(name: str, body: str) -> bool:
    """True when `name` appears as a call, index or member access (not only as a JSX tag)."""
    pattern = re.compile(r"(?<![\w$.<])" + re.escape(name) + r"\s*[(\[.]")
    return pattern.search(body) is not None


def check_app(app_dir: Path) -> list[str]:
    src_root = app_dir / "src"
    app_root = src_root / "app"
    if not app_root.is_dir():
        return []
    sources: dict[Path, str] = {}

    def read(path: Path) -> str:
        if path not in sources:
            sources[path] = path.read_text(encoding="utf-8")
        return sources[path]

    findings: list[str] = []
    queue = [
        p
        for p in app_root.rglob("*")
        if p.suffix in EXTENSIONS and p.stem in ROUTE_FILES and not has_use_client(read(p))
    ]
    seen: set[Path] = set()
    while queue:
        server_file = queue.pop()
        if server_file in seen:
            continue
        seen.add(server_file)
        source = read(server_file)
        body = strip_comments(source)
        for match in IMPORT_RE.finditer(source):
            if match.group("type"):
                continue
            target = resolve(match.group("spec"), server_file, src_root)
            if target is None:
                continue
            target_source = read(target)
            if not has_use_client(target_source):
                queue.append(target)
                continue
            import_end = match.end()
            for name in named_values(match.group("clause")):
                if used_as_value(name, body[import_end:]):
                    findings.append(
                        f"{server_file.relative_to(app_dir.parent.parent)}: `{name}` from "
                        f'"{match.group("spec")}" is a "use client" export used as a value'
                    )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--app", action="append", help="app directory relative to root")
    args = parser.parse_args()
    root = Path(args.root)
    findings: list[str] = []
    for app in args.app or APPS:
        findings.extend(check_app(root / app))
    for line in findings:
        print(line)
    if findings:
        print(f"{len(findings)} server file(s) call exports of \"use client\" modules.")
        return 1
    print("check_client_imports: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
