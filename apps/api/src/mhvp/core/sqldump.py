"""Shared parser for `mysqldump`/MariaDB SQL dumps used by data takeovers (rule 0.1.9, 0.1.12).

No SQL is ever executed: only `INSERT INTO ... VALUES (...), (...);` statements are read, tuple
by tuple, handling quoting, escaping and `NULL` the way MariaDB writes them. This module holds
the table agnostic parsing and literal conversion shared by every dump based import (M30
U-Protokoll, M35 objektakte); an importer supplies its own list of known tables and its own
mapping from parsed rows to CRM models.
"""

import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+`?(?P<table>\w+)`?\s*\((?P<columns>[^()]*)\)\s*VALUES\s*"
    r"(?P<values>.*?)\s*;",
    re.IGNORECASE | re.DOTALL,
)


def strip_comments(sql: str) -> str:
    """mysqldump comments: `-- ...` line comments and `/* ... */` block comments outside of
    string literals. A dump never places these markers inside a data value, so a line based
    strip is sufficient and never touches an INSERT statement's own content."""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    kept = []
    for line in sql.split("\n"):
        if line.strip().startswith("--"):
            continue
        kept.append(line)
    return "\n".join(kept)


def split_columns(columns: str) -> list[str]:
    return [c.strip().strip("`") for c in columns.split(",") if c.strip()]


def split_tuples(values: str) -> list[str]:
    """Split "(...), (...)" into the inner text of each tuple, respecting quoted strings so a
    comma or a parenthesis inside a value never ends the tuple early."""
    out: list[str] = []
    depth = 0
    buf: list[str] = []
    in_string: str | None = None
    i, n = 0, len(values)
    while i < n:
        ch = values[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                buf.append(ch)
                buf.append(values[i + 1])
                i += 2
                continue
            if ch == in_string:
                if i + 1 < n and values[i + 1] == in_string:  # doubled quote = literal quote
                    buf.append(ch)
                    buf.append(ch)
                    i += 2
                    continue
                in_string = None
            buf.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "(":
            depth += 1
            if depth == 1:
                buf = []
                i += 1
                continue
        if ch == ")":
            depth -= 1
            if depth == 0:
                out.append("".join(buf))
                i += 1
                continue
        if depth > 0:
            buf.append(ch)
        i += 1
    return out


def _coerce(text: str, quoted: bool) -> Any:
    if quoted:
        return text
    stripped = text.strip()
    if stripped == "" or stripped.upper() == "NULL":
        return None
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    try:
        return float(stripped)
    except ValueError:
        return stripped


def parse_fields(tup: str) -> list[Any]:
    """One tuple's fields, unescaped and typed: a quoted field stays a string (even "123"), an
    unquoted field becomes int/float/None (NULL) the way MariaDB writes literals."""
    out: list[Any] = []
    buf: list[str] = []
    quoted = False
    in_string: str | None = None
    i, n = 0, len(tup)
    while i < n:
        ch = tup[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                nxt = tup[i + 1]
                buf.append({"n": "\n", "r": "\r", "t": "\t", "0": "\0"}.get(nxt, nxt))
                i += 2
                continue
            if ch == in_string:
                if i + 1 < n and tup[i + 1] == in_string:
                    buf.append(ch)
                    i += 2
                    continue
                in_string = None
                i += 1
                continue
            buf.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = ch
            quoted = True
            i += 1
            continue
        if ch == ",":
            out.append(_coerce("".join(buf), quoted))
            buf, quoted = [], False
            i += 1
            continue
        buf.append(ch)
        i += 1
    out.append(_coerce("".join(buf), quoted))
    return out


def parse_dump(sql_text: str) -> dict[str, list[dict[str, Any]]]:
    """Every `INSERT INTO` statement of the dump, grouped by table. Rows whose value count does
    not match the column list are skipped (malformed statement, e.g. a truncated upload) rather
    than raising, so one bad statement never blocks the rest of the dump."""
    cleaned = strip_comments(sql_text)
    tables: dict[str, list[dict[str, Any]]] = {}
    for m in _INSERT_RE.finditer(cleaned):
        table = m.group("table").lower()
        columns = split_columns(m.group("columns"))
        for tup in split_tuples(m.group("values")):
            values = parse_fields(tup)
            if len(values) != len(columns):
                continue
            tables.setdefault(table, []).append(dict(zip(columns, values, strict=False)))
    return tables


# --- typed conversions of MariaDB literals to Python/SQLAlchemy types (shared across importers) -


def field_str(row: dict[str, Any], key: str, limit: int | None = None) -> str | None:
    v = row.get(key)
    if v is None:
        return None
    text = str(v).strip()
    if text == "":
        return None
    return text[:limit] if limit else text


def to_date(v: Any) -> date | None:
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()  # noqa: DTZ007 -- MariaDB DATE has no tz
    except ValueError:
        return None


def to_time(v: Any) -> time | None:
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:8], "%H:%M:%S").time()  # noqa: DTZ007 -- MariaDB TIME has no tz
    except ValueError:
        return None


def to_datetime(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:19], "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007 -- MariaDB DATETIME has no tz
    except ValueError:
        return None


def to_decimal(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def to_bool(v: Any) -> bool:
    return bool(v) and str(v) not in ("0", "0.0")
