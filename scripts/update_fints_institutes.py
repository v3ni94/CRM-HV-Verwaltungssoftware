#!/usr/bin/env python3
"""Merges the FinTS institute list of the Deutsche Kreditwirtschaft (DK) into
apps/api/src/mhvp/banking/data/fints_institutes.txt (M11-01, AE26).

The DK publishes the list as an Excel file and as CSV ("fints_institute ... Master"). Save the
Excel file as CSV with semicolons if only the Excel file is at hand. The CSV has one row per
institute and location; the columns used are BLZ, BIC, Institut, Ort, HBCI-Zugang DNS,
HBCI-Version, PIN/TAN-Zugang URL and Version (looked up by header name, not by position).

Rules (what the script changes, and what it never does):
  * Rows are matched by BLZ. An existing row keeps name, city, BIC and check digit; HBCI domain,
    FinTS URL, HBCI version and FinTS version are taken from the DK row. With --match-bic the
    exact BIC is used for BLZ without own DK row (off by default: several BLZ of one BIC are
    often special divisions without FinTS access).
  * A BLZ that exists only in the DK list is added with name, city and BIC of the DK row.
  * A URL is never removed silently: when the DK row has no PIN/TAN URL any more but the
    existing row has one, the row is kept and reported (--allow-clear removes the URL).
  * A DK URL that is not https is not taken over and reported.
  * Rows that are not in the DK list stay as they are and are counted in the report.
  * The legacy hosts of the Fiducia and GAD data centres are not rewritten in the file; the
    parser in mhvp.banking.fints rebuilds the Atruvia address from the domain column.

Default is a dry run. With --apply the file is replaced atomically; without a fixed minimum of
institutes in the DK file or when more than 10 percent of the connectable rows would lose their
URL the script refuses to write (--force overrides after the report was read).

Usage:
  python3 scripts/update_fints_institutes.py --dk-csv "fints_institute NEU mit BIC Master.csv"
  python3 scripts/update_fints_institutes.py --dk-csv list.csv --apply
Exit codes: 0 ok (also dry run), 1 refused by a safety check, 2 usage or unreadable input.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIST = ROOT / "apps" / "api" / "src" / "mhvp" / "banking" / "data" / "fints_institutes.txt"

# Shut down data centre hosts (see mhvp.banking.fints.LEGACY_FINTS_HOSTS, kept equal by a test).
LEGACY_FINTS_HOSTS = frozenset({"hbci-pintan.gad.de", "hbci11.fiducia.de"})
MIN_DK_INSTITUTES = 500
MAX_LOST_SHARE = 0.10

BLZ_RE = re.compile(r"^\d{8}$")
BIC_RE = re.compile(r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$")

REQUIRED = ("BLZ", "BIC", "Institut", "Ort", "HBCI-Zugang DNS", "HBCI-Version", "PIN/TAN-Zugang URL", "Version")


@dataclass
class Row:
    """One line of fints_institutes.txt: BLZ=Name|Ort|BIC|Prüfziffer|Domain|URL|HBCI|FinTS|"""

    blz: str
    name: str
    city: str
    bic: str
    check: str
    domain: str
    url: str
    hbci: str
    fints: str
    # original line of an unchanged row, so an update does not reformat what it did not touch
    raw: str | None = field(default=None, compare=False)

    def render(self) -> str:
        if self.raw is not None:
            return self.raw
        parts = [self.name, self.city, self.bic, self.check, self.domain, self.url, self.hbci, self.fints]
        return f"{self.blz}=" + "|".join(parts) + "|"


@dataclass
class DkEntry:
    name: str
    city: str
    bic: str
    domain: str
    url: str
    hbci: str
    fints: str


def _repair_c1(value: str) -> str:
    """Control characters U+0080 to U+009F in a text are Windows-1252 bytes that were read as
    Latin-1 (for example U+0096 for the en dash); map them back."""
    return "".join(
        ch.encode("latin-1").decode("cp1252", errors="ignore") if "\x80" <= ch <= "\x9f" else ch
        for ch in value
    )


def _clean(value: str) -> str:
    """Field text for the pipe separated file: one line, no separators."""
    return " ".join(_repair_c1(value).replace("|", "/").replace("=", " ").split())


def _norm_header(value: str) -> str:
    return " ".join(value.replace("﻿", "").split()).casefold()


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def read_dk_csv(path: Path) -> tuple[dict[str, DkEntry], list[str]]:
    """DK rows grouped by BLZ (the first row with a URL wins; rows of one BLZ with different
    URLs are reported). Returns (entries, warnings)."""
    text = read_text(path)
    reader = csv.reader(text.splitlines(), delimiter=";")
    try:
        header = next(reader)
    except StopIteration:
        raise SystemExit(f"{path}: empty file") from None
    index = {_norm_header(name): i for i, name in enumerate(header)}
    missing = [name for name in REQUIRED if _norm_header(name) not in index]
    if missing:
        raise SystemExit(f"{path}: columns missing: {', '.join(missing)} (found: {header})")
    col = {name: index[_norm_header(name)] for name in REQUIRED}
    warnings: list[str] = []
    grouped: dict[str, list[DkEntry]] = defaultdict(list)
    for line_no, cells in enumerate(reader, start=2):
        def cell(name: str, cells: list[str] = cells) -> str:
            i = col[name]
            return cells[i].strip() if i < len(cells) else ""

        blz = cell("BLZ")
        if not blz:
            continue
        if not BLZ_RE.fullmatch(blz):
            warnings.append(f"line {line_no}: BLZ '{blz}' is not 8 digits, skipped")
            continue
        url = cell("PIN/TAN-Zugang URL")
        if url and not url.lower().startswith("https://"):
            warnings.append(f"BLZ {blz}: URL '{url}' is not https, not taken over")
            url = ""
        version = cell("Version").replace("FinTS V", "").strip()
        grouped[blz].append(
            DkEntry(
                name=_clean(cell("Institut")),
                city=_clean(cell("Ort")),
                bic=cell("BIC").upper(),
                domain=_clean(cell("HBCI-Zugang DNS")),
                url=_clean(url),
                hbci=_clean(cell("HBCI-Version")),
                fints=_clean(version),
            )
        )
    entries: dict[str, DkEntry] = {}
    for blz, rows in grouped.items():
        with_url = [r for r in rows if r.url]
        chosen = (with_url or rows)[0]
        if len({r.url for r in with_url}) > 1:
            warnings.append(f"BLZ {blz}: several different URLs in the DK list, first one used")
        entries[blz] = chosen
    return entries, warnings


def read_list(path: Path) -> list[Row]:
    rows: list[Row] = []
    for line in path.read_text("utf-8").splitlines():
        if not line.strip() or line.startswith("#") or "=" not in line:
            continue
        blz, _, rest = line.partition("=")
        parts = rest.split("|")
        if not BLZ_RE.fullmatch(blz.strip()) or len(parts) < 8:
            continue
        name, city, bic, check, domain, url, hbci, fints = (p.strip() for p in parts[:8])
        rows.append(Row(blz.strip(), name, city, bic, check, domain, url, hbci, fints, raw=line))
    return rows


@dataclass
class Result:
    rows: list[Row]
    report: list[str]
    refused: list[str]


def merge(
    rows: list[Row],
    dk: dict[str, DkEntry],
    *,
    match_bic: bool = False,
    allow_clear: bool = False,
) -> Result:
    by_bic: dict[str, DkEntry] = {}
    for entry in dk.values():
        if entry.bic and BIC_RE.fullmatch(entry.bic):
            by_bic.setdefault(entry.bic, entry)
    out: list[Row] = []
    seen: set[str] = set()
    updated: list[str] = []
    kept_url: list[str] = []
    not_in_dk = 0
    connectable_before = sum(1 for r in rows if r.url)
    lost = 0
    for row in rows:
        seen.add(row.blz)
        entry = dk.get(row.blz)
        source = "BLZ"
        if entry is None and match_bic and row.bic in by_bic:
            entry, source = by_bic[row.bic], "BIC"
        if entry is None:
            not_in_dk += 1
            out.append(row)
            continue
        new = Row(row.blz, row.name, row.city, row.bic or entry.bic, row.check, entry.domain,
                  entry.url, entry.hbci, entry.fints)
        if row.url and not entry.url:
            if allow_clear:
                lost += 1
            else:
                kept_url.append(f"{row.blz} {row.name}: DK list has no PIN/TAN URL any more, kept {row.url}")
                new.url, new.domain, new.hbci, new.fints = row.url, row.domain, row.hbci, row.fints
        if new != row:
            changes = [
                f"{label} '{old}' -> '{cur}'"
                for label, old, cur in (
                    ("domain", row.domain, new.domain),
                    ("url", row.url, new.url),
                    ("hbci", row.hbci, new.hbci),
                    ("fints", row.fints, new.fints),
                    ("bic", row.bic, new.bic),
                )
                if old != cur
            ]
            updated.append(f"{row.blz} {row.name} (match by {source}): " + "; ".join(changes))
        out.append(new if new != row else row)
    added: list[str] = []
    for blz, entry in dk.items():
        if blz in seen:
            continue
        out.append(Row(blz, entry.name, entry.city, entry.bic, "", entry.domain, entry.url,
                       entry.hbci, entry.fints))
        added.append(f"{blz} {entry.name} {entry.city}" + (f" {entry.url}" if entry.url else ""))
    out.sort(key=lambda r: r.blz)
    legacy = sum(1 for r in out if r.url and _host(r.url) in LEGACY_FINTS_HOSTS)
    report = [
        f"existing rows: {len(rows)}, DK institutes (distinct BLZ): {len(dk)}",
        f"updated: {len(updated)}, added: {len(added)}, not in DK list (unchanged): {not_in_dk}",
        f"connectable (with URL) before: {connectable_before}, after: {sum(1 for r in out if r.url)}",
        f"rows still naming a shut down legacy host (parser redirects to Atruvia): {legacy}",
    ]
    report += [f"UPDATED {line}" for line in updated[:200]]
    if len(updated) > 200:
        report.append(f"... and {len(updated) - 200} more updated rows")
    report += [f"ADDED {line}" for line in added[:200]]
    if len(added) > 200:
        report.append(f"... and {len(added) - 200} more added rows")
    report += [f"KEPT {line}" for line in kept_url]
    refused: list[str] = []
    if len(dk) < MIN_DK_INSTITUTES:
        refused.append(f"the DK file lists only {len(dk)} institutes (minimum {MIN_DK_INSTITUTES}), wrong file?")
    if connectable_before and lost / connectable_before > MAX_LOST_SHARE:
        refused.append(f"{lost} of {connectable_before} connectable rows would lose their URL")
    return Result(out, report, refused)


def _host(url: str) -> str:
    return url.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0].casefold()


def write_atomic(path: Path, rows: list[Row]) -> None:
    text = "".join(row.render() + "\n" for row in rows)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".fints_institutes.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--dk-csv", required=True, type=Path, help="DK institute list as CSV (semicolon)")
    parser.add_argument("--list", type=Path, default=DEFAULT_LIST, help="target list (default: packaged list)")
    parser.add_argument("--apply", action="store_true", help="write the merged list (default: dry run)")
    parser.add_argument("--match-bic", action="store_true", help="match rows without own DK row by exact BIC")
    parser.add_argument("--allow-clear", action="store_true", help="remove URLs the DK list no longer names")
    parser.add_argument("--force", action="store_true", help="write although a safety check refused")
    parser.add_argument("--quiet", action="store_true", help="print only the summary lines")
    args = parser.parse_args(argv)
    for path in (args.dk_csv, args.list):
        if not path.is_file():
            print(f"{path}: file not found", file=sys.stderr)
            return 2
    dk, warnings = read_dk_csv(args.dk_csv)
    result = merge(read_list(args.list), dk, match_bic=args.match_bic, allow_clear=args.allow_clear)
    lines = result.report[:4] if args.quiet else result.report
    for line in lines:
        print(line)
    for warning in warnings[:50]:
        print(f"WARNING {warning}")
    if len(warnings) > 50:
        print(f"WARNING ... and {len(warnings) - 50} more")
    for problem in result.refused:
        print(f"REFUSED {problem}", file=sys.stderr)
    if result.refused and not args.force:
        return 1
    if not args.apply:
        print("dry run: nothing written (use --apply)")
        return 0
    write_atomic(args.list, result.rows)
    print(f"written: {args.list}")
    print("next: update the date line in docs/integrations/fints.md, run tests/unit/test_fints.py, deliver.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
