"""Small escaping helpers for values that leave the application in a foreign syntax: SQL
``LIKE`` patterns built from user search terms and CSV cells opened in spreadsheet programs
(Sicherheitsreview 26.09.2026, Befunde 5 und 6)."""

from typing import Any

LIKE_ESCAPE = "\\"
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def escape_like(value: str, escape: str = LIKE_ESCAPE) -> str:
    """Escapes ``%``, ``_`` and the escape character itself so that a search term matches
    literally inside a ``LIKE``/``ILIKE`` pattern. Use together with
    ``column.ilike(f"%{escape_like(q)}%", escape=LIKE_ESCAPE)``."""
    return (
        value.replace(escape, escape + escape).replace("%", escape + "%").replace("_", escape + "_")
    )


def csv_safe_cell(value: Any) -> Any:
    """Neutralises spreadsheet formula injection: a string starting with ``=``, ``+``, ``-``,
    ``@``, tab or carriage return gets a leading apostrophe, which Excel and LibreOffice show as
    text. Non strings (numbers, dates, None) pass through unchanged so amounts keep their sign."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value
