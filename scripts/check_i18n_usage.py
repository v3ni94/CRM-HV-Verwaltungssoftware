#!/usr/bin/env python3
"""Static check of next-intl translation calls against the German message catalogue.

For every non-test source file of the web apps the translator bindings are collected
(``const t = useTranslations("Ns")``, ``const t = await getTranslations("Ns")``,
``getTranslations({ namespace: "Ns" })`` and ``const [a, t] = await Promise.all([...,
getTranslations("Ns")])``). Each call ``t("key")``, ``t.rich("key")``, ``t.markup("key")``
and ``t.raw("key")`` is resolved against ``messages/de.json`` of the app, using the nearest
preceding binding of the same name in the file (heuristic, components in one file are
declared one after another). Reported are:

* ``MISSING``: literal key that does not exist,
* ``OBJECT``: literal key that resolves to a nested object (next-intl INSUFFICIENT_PATH;
  ``t.raw`` is allowed to return objects),
* ``PREFIX``: template key ``prefix.${x}`` whose static prefix is not an object,
* ``ARGS``: literal key whose message needs ICU arguments that the call does not pass
  (only checked when the call passes no values or an object literal).

Dynamic parts of template keys cannot be checked statically; the vitest suites cover them
(the test providers fail on MISSING_MESSAGE, INSUFFICIENT_PATH and FORMATTING_ERROR).
``t.has`` is never reported. Exit code 1 on any finding. Standard library only.

Usage: python3 scripts/check_i18n_usage.py [--root <repo root>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

APPS = ("apps/web-crm", "apps/web-portal")
SOURCE_SUFFIXES = (".ts", ".tsx")

HOOK = r"(?:useTranslations|getTranslations)"
NS_ARG = r"""\(\s*(?:["']([^"']*)["']|\{[^}]*?namespace\s*:\s*["']([^"']*)["'][^}]*\})?\s*\)"""
SIMPLE_BINDING = re.compile(
    r"(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:await\s+)?" + HOOK + NS_ARG
)
PROMISE_ALL = re.compile(r"(?:const|let)\s*\[([^\]]*)\]\s*=\s*await\s+Promise\.all\(\s*\[")
HOOK_CALL = re.compile(r"^\s*(?:await\s+)?" + HOOK + NS_ARG + r"\s*$", re.S)
KEY_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*$")
TAG_RE = re.compile(r"<([A-Za-z][\w]*)>")
CONST_ARRAY = re.compile(
    r"(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::[^=\n]+)?=\s*\[([^\]]*)\]"
)
BRANCHING = {"plural", "select", "selectordinal"}


def icu_arguments(message: str) -> set[str]:
    """Argument names of an ICU message; plural and select branch bodies are recursed."""
    names: set[str] = set()

    def parse(text: str, i: int, stop_at_close: bool) -> int:
        while i < len(text):
            ch = text[i]
            if ch == "'" and i + 1 < len(text) and text[i + 1] in "{}'":
                end = text.find("'", i + 1)
                i = len(text) if end < 0 else end + 1
                continue
            if ch == "}" and stop_at_close:
                return i
            if ch == "{":
                m = re.match(r"\{\s*([A-Za-z_][\w]*)\s*(,\s*([A-Za-z]+)\s*)?", text[i:])
                if not m:
                    i += 1
                    continue
                names.add(m.group(1))
                kind = m.group(3)
                i += m.end()
                if kind in BRANCHING:
                    i = text.find(",", i) + 1 if text[i : i + 1] == "," else i
                    # selector {body} pairs until the closing brace of the argument
                    while i < len(text) and text[i] != "}":
                        if text[i] == "{":
                            i = parse(text, i + 1, True) + 1
                        else:
                            i += 1
                    i += 1
                else:
                    depth = 1
                    while i < len(text) and depth:
                        depth += {"{": 1, "}": -1}.get(text[i], 0)
                        i += 1
                continue
            i += 1
        return i

    parse(message, 0, False)
    return names


def split_top_level(text: str) -> list[str]:
    """Split on commas that are not nested in brackets, braces, parens or strings."""
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    start = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    tail = text[start:]
    if tail.strip():
        parts.append(tail)
    return parts


def matching_end(text: str, open_pos: int) -> int:
    """Index of the bracket closing the one at open_pos (strings are skipped)."""
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack = [pairs[text[open_pos]]]
    quote: str | None = None
    i = open_pos + 1
    while i < len(text) and stack:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if quote == "`" and ch == "$" and i + 1 < len(text) and text[i + 1] == "{":
                # template expression: skip to its closing brace
                end = matching_end(text, i + 1)
                i = end + 1
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'`":
            quote = ch
        elif ch in pairs:
            stack.append(pairs[ch])
        elif ch == stack[-1]:
            stack.pop()
            if not stack:
                return i
        i += 1
    return len(text) - 1


def collect_bindings(src: str) -> list[tuple[int, str, str]]:
    """Return (position, variable, namespace) for all translator bindings in a file."""
    out: list[tuple[int, str, str]] = []
    for m in SIMPLE_BINDING.finditer(src):
        out.append((m.start(), m.group(1), m.group(2) or m.group(3) or ""))
    for m in PROMISE_ALL.finditer(src):
        names = [n.strip() for n in split_top_level(m.group(1))]
        array_open = m.end() - 1
        array_end = matching_end(src, array_open)
        items = split_top_level(src[array_open + 1 : array_end])
        for name, item in zip(names, items, strict=False):
            hm = HOOK_CALL.match(item)
            if hm and re.fullmatch(r"[A-Za-z_$][\w$]*", name):
                out.append((m.start(), name, hm.group(1) or hm.group(2) or ""))
    out.sort()
    return out


def resolve(messages: dict[str, object], path: str) -> object:
    node: object = messages
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def literal_keys(arg: str) -> list[str] | None:
    """Plain literal keys of a call's first argument (also both branches of a ternary)."""
    arg = arg.strip()
    m = re.fullmatch(r"""["']([^"']*)["']|`([^`$]*)`""", arg)
    if m:
        return [m.group(1) if m.group(1) is not None else m.group(2)]
    tern = re.fullmatch(r"""[^"'`?]+\?\s*["']([^"']+)["']\s*:\s*["']([^"']+)["']""", arg, re.S)
    if tern:
        return [tern.group(1), tern.group(2)]
    return None


def template_prefix(arg: str) -> str | None:
    m = re.fullmatch(r"`([A-Za-z0-9_.]*)\$\{.*`", arg.strip(), re.S)
    if m and m.group(1).endswith(".") and len(m.group(1)) > 1:
        return m.group(1)[:-1]
    return None


def string_arrays(src: str) -> dict[str, list[str]]:
    """Module constants that are plain arrays of string literals: const NAME = ["a", "b"]."""
    out: dict[str, list[str]] = {}
    for m in CONST_ARRAY.finditer(src):
        items = [i.strip() for i in split_top_level(m.group(2))]
        values = [re.fullmatch(r"""["']([^"']*)["']""", i) for i in items]
        if items and all(values):
            out[m.group(1)] = [v.group(1) for v in values if v]
    return out


def mapped_values(
    src: str, pos: int, template: str, arrays: dict[str, list[str]]
) -> list[str] | None:
    """Values of ${x} when the call sits in ARRAY.map((x) => ...) over a known string array."""
    m = re.fullmatch(r"`[A-Za-z0-9_.]*\$\{\s*([A-Za-z_$][\w$]*)\s*\}`", template.strip())
    if not m:
        return None
    ident = m.group(1)
    maps = list(re.finditer(rf"\.map\(\s*\(?\s*{re.escape(ident)}\b", src[:pos]))
    if not maps:
        return None
    before = src[: maps[-1].start()]
    named = re.search(r"(?<![\w$.])([A-Za-z_$][\w$]*)$", before)
    if named:
        return arrays.get(named.group(1))
    inline = re.search(r"\[([^\[\]]*)\](?:\s*as\s+const)?\s*\)?$", before)
    if inline:
        items = [i.strip() for i in split_top_level(inline.group(1))]
        values = [re.fullmatch(r"""["']([^"']*)["']""", i) for i in items]
        if items and all(values):
            return [v.group(1) for v in values if v]
    return None


def check_file(path: Path, rel: str, messages: dict[str, object]) -> list[str]:
    src = path.read_text(encoding="utf-8")
    bindings = collect_bindings(src)
    if not bindings:
        return []
    arrays = string_arrays(src)
    findings: list[str] = []
    names = sorted({b[1] for b in bindings}, key=len, reverse=True)
    call_re = re.compile(
        r"(?<![\w$.])(" + "|".join(re.escape(n) for n in names) + r")(\.(?:rich|markup|raw|has))?\("
    )
    for m in call_re.finditer(src):
        var, method = m.group(1), m.group(2) or ""
        if method == ".has":
            continue
        candidates = [b for b in bindings if b[1] == var and b[0] < m.start()]
        if not candidates:
            continue
        namespace = candidates[-1][2]
        open_pos = m.end() - 1
        close_pos = matching_end(src, open_pos)
        args = split_top_level(src[open_pos + 1 : close_pos])
        if not args:
            continue
        line = src.count("\n", 0, m.start()) + 1
        where = f"{rel}:{line}"
        keys = literal_keys(args[0])
        if keys is None:
            prefix = template_prefix(args[0])
            if prefix is not None:
                full = f"{namespace}.{prefix}" if namespace else prefix
                if not isinstance(resolve(messages, full), dict):
                    findings.append(f"{where}: PREFIX {full} (template key {args[0].strip()})")
                else:
                    for value in mapped_values(src, m.start(), args[0], arrays) or []:
                        if value and not isinstance(resolve(messages, f"{full}.{value}"), str):
                            findings.append(
                                f"{where}: MISSING {full}.{value} (value of the mapped array)"
                            )
            continue
        for key in keys:
            if not KEY_RE.match(key):
                continue
            full = f"{namespace}.{key}" if namespace else key
            value = resolve(messages, full)
            if value is None:
                findings.append(f"{where}: MISSING {full}")
            elif isinstance(value, dict):
                if method != ".raw":
                    findings.append(f"{where}: OBJECT {full} (nested messages, not a string)")
            elif isinstance(value, str) and method != ".raw":
                needed = icu_arguments(value)
                if method in (".rich", ".markup"):
                    needed |= set(TAG_RE.findall(value))
                if not needed:
                    continue
                values = args[1].strip() if len(args) > 1 else None
                if values is None:
                    findings.append(f"{where}: ARGS {full} needs {sorted(needed)}, none passed")
                elif values.startswith("{"):
                    missing = [
                        n
                        for n in sorted(needed)
                        if not re.search(rf"(?<![\w$]){n}(?![\w$])", values)
                    ]
                    if missing and "..." not in values:
                        findings.append(f"{where}: ARGS {full} missing {missing}")
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
    findings: list[str] = []
    for app in APPS:
        messages = json.loads((root / app / "messages" / "de.json").read_text(encoding="utf-8"))
        for path in sorted((root / app / "src").rglob("*")):
            if path.suffix not in SOURCE_SUFFIXES or ".test." in path.name:
                continue
            rel = str(path.relative_to(root))
            findings.extend(check_file(path, rel, messages))
    for line in findings:
        print(line)
    if findings:
        print(f"i18n usage check: {len(findings)} finding(s)")
        return 1
    print("i18n usage check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
