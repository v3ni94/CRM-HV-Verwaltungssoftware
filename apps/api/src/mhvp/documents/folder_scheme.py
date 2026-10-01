"""Folder scheme of the Google Drive filing per tenant (GA01-09, 5.2 DMS-Konfiguration).

The scheme is a path template in ``dms_connection.options["folder_scheme"]`` with the
placeholders ``{objekt}``, ``{jahr}`` and ``{kategorie}``, for example ``{objekt}/{jahr}``
(default, the layout used so far). Segments are separated by ``/``.
"""

import re

OPTION_KEY = "folder_scheme"
DEFAULT_SCHEME = "{objekt}/{jahr}"
PLACEHOLDERS = frozenset({"objekt", "jahr", "kategorie"})
_TOKEN = re.compile(r"\{([a-z]+)\}")
_FORBIDDEN = re.compile(r"[\\\x00-\x1f<>:\"|?*]")
MAX_DEPTH = 5


def validate_folder_scheme(scheme: str) -> str:
    """Return the normalised scheme or raise ``ValueError`` (message in German for the UI)."""
    cleaned = "/".join(seg.strip() for seg in scheme.strip().strip("/").split("/"))
    segments = cleaned.split("/")
    if not cleaned or any(not seg for seg in segments):
        raise ValueError("Ordnerschema: leere Ordnerebene.")
    if len(segments) > MAX_DEPTH or len(cleaned) > 200:
        raise ValueError(f"Ordnerschema: höchstens {MAX_DEPTH} Ebenen und 200 Zeichen.")
    if _FORBIDDEN.search(cleaned) or any(seg in (".", "..") for seg in segments):
        raise ValueError("Ordnerschema: unzulässige Zeichen.")
    tokens = _TOKEN.findall(cleaned)
    unknown = sorted(set(tokens) - PLACEHOLDERS)
    if unknown:
        raise ValueError(f"Ordnerschema: unbekannte Platzhalter {', '.join(unknown)}.")
    if "objekt" not in tokens:
        raise ValueError("Ordnerschema: der Platzhalter {objekt} ist erforderlich.")
    if re.sub(r"\{[a-z]+\}", "", cleaned).count("{") or "}" in re.sub(r"\{[a-z]+\}", "", cleaned):
        raise ValueError("Ordnerschema: geschweifte Klammern nur als Platzhalter.")
    return cleaned


def render_folder_path(
    scheme: str | None, *, objekt: str, jahr: int, kategorie: str = "Sonstiges"
) -> list[str]:
    """Folder names from the root, one per scheme level; no scheme means the default."""
    normalised = validate_folder_scheme(scheme or DEFAULT_SCHEME)
    values = {"objekt": objekt, "jahr": str(jahr), "kategorie": kategorie}
    return [_TOKEN.sub(lambda m: values[m.group(1)], seg) for seg in normalised.split("/")]
