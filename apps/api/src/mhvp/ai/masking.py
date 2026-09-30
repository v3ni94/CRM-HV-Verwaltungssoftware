"""Address masking for provider calls (M7-10, 9.1 Datenschutz).

Deterministic, pattern based: street with house number and postal code with town are replaced
by placeholders before the text leaves the platform. Names are deliberately kept (decision
M34-05 is open): text drafts need the salutation, and the name rule is documented in
``docs/rules/AI-MASK-02.md``. The masking is best effort and no proof of anonymity; it never
replaces the AVV and provider release checks of the gateway.
"""

from __future__ import annotations

import re

from mhvp.objektakte.masking import mask_identifiers

STREET_PLACEHOLDER = "[Straße]"
POSTAL_PLACEHOLDER = "[PLZ Ort]"

_SUFFIXES = (
    "straße|strasse|str\\.|weg|allee|platz|gasse|damm|ring|ufer|chaussee|park|pfad|steig|markt|hof"
)
_WORD = r"[A-ZÄÖÜ][\wäöüß.\-]*"
# "Hauptstraße 5", "Am Panke Park 3", "Bahnhofstr. 5a", "Lindenallee 7-9"
_STREET = re.compile(
    rf"\b(?:(?:Am|An der|An den|Auf dem|Zum|Zur|Im|In der)\s+)?(?:{_WORD}\s+){{0,2}}"
    rf"(?:[\wäöüß\-]*(?:{_SUFFIXES})|(?i:{_SUFFIXES}))\s+\d{{1,4}}\s?[a-zA-Z]?\b"
    r"(?:\s?[-/]\s?\d{1,4}\s?[a-zA-Z]?)?"
)
_POSTAL = re.compile(
    r"\b\d{5}\s+(?!Euro\b|EUR\b)[A-ZÄÖÜ][\wäöüß\-]+"
    r"(?:\s(?:am|an der|bei)\s[A-ZÄÖÜ][\wäöüß\-]+)?"
)


def mask_addresses(text: str | None) -> str:
    """Street with house number and postal code with town masked, everything else kept."""
    if not text:
        return ""
    masked = _STREET.sub(STREET_PLACEHOLDER, text)
    return _POSTAL.sub(POSTAL_PLACEHOLDER, masked)


def mask_personal_data(text: str | None) -> str:
    """IBAN, e-mail, phone (objektakte) plus addresses; names stay (see module docstring)."""
    return mask_addresses(mask_identifiers(text))
