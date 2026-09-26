"""M14 Belegeingang: masking of personal data before the text of a receipt leaves the CRM for
an external AI provider (rule 0.1.13, DSGVO). Modelled on `mhvp.objektakte.masking` (same
order, same placeholders for IBAN, e-mail and phone) with one deliberate difference:

* Person names are masked only when introduced by a title (Herr, Frau, Familie, Eheleute,
  z. Hd.). The objektakte heuristic hides every run of two or three capitalised words, which
  on an invoice also hides the supplier name ("Elektro Müller GmbH") that the extraction is
  meant to return. Company names are not personal data; a private supplier without a title
  prefix is an accepted gap (`docs/OPEN_QUESTIONS.md`, M14) and the reviewer sees only the
  masked text when checking what was sent.

Consequence for the IBAN (rule 0.1.6): the model never sees an IBAN, so it cannot propose
one. IBAN candidates are detected deterministically in the unmasked text
(`iban_candidates`), stored encrypted on the draft and shown masked; the reviewer types and
confirms the IBAN before it reaches the invoice draft.

`mask_text` never raises.
"""

from __future__ import annotations

import re

_IBAN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}[0-9]{2}(?:[ ]?[A-Z0-9]{1,4}){2,7}(?![A-Za-z0-9])")
_BIC = re.compile(r"\b(?:BIC|SWIFT)\s*[:.]?\s*([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<![\w])(?:\+49|0049|0)[ /()\-]?(?:\d[ /()\-]?){5,13}\d(?![\w])")
_TITLE = r"(?:Herrn?|Frau|Familie|Eheleute|z\.\s?Hd\.|zu Händen)\s+"
_NAME_WORD = r"[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?"
_TITLED_NAME = re.compile(
    rf"\b{_TITLE}(?:Dr\.\s+|Prof\.\s+)?{_NAME_WORD}(?:\s+{_NAME_WORD}){{0,2}}\b"
)

IBAN_PLACEHOLDER = "[IBAN]"
BIC_PLACEHOLDER = "[BIC]"
EMAIL_PLACEHOLDER = "[E-MAIL]"
PHONE_PLACEHOLDER = "[TELEFON]"
NAME_PLACEHOLDER = "[NAME]"

_IBAN_LENGTHS = {"DE": 22, "AT": 20, "CH": 21, "NL": 18, "FR": 27, "BE": 16, "LU": 20, "IT": 27}


def normalize_iban(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def iban_checksum_ok(iban: str) -> bool:
    """ISO 7064 mod 97-10 check; a wrong checksum marks the candidate as doubtful, it is never
    silently dropped (an OCR error is exactly what the reviewer must see)."""
    value = normalize_iban(iban)
    if len(value) < 15 or not value[:2].isalpha() or not value[2:4].isdigit():
        return False
    expected = _IBAN_LENGTHS.get(value[:2])
    if expected is not None and len(value) != expected:
        return False
    rearranged = value[4:] + value[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


def iban_candidates(text: str | None) -> list[str]:
    """Distinct IBAN-shaped tokens in document order, normalised (no spaces, upper case)."""
    if not text:
        return []
    seen: list[str] = []
    for match in _IBAN.finditer(text):
        value = normalize_iban(match.group(0))
        if value not in seen:
            seen.append(value)
    return seen


def mask_text(text: str | None) -> str:
    """IBAN, BIC, e-mail, phone, then titled person names. Same order as the objektakte masker
    so a later pattern cannot re-expose what an earlier one hid."""
    if not text:
        return ""
    masked = _IBAN.sub(IBAN_PLACEHOLDER, text)
    masked = _BIC.sub(lambda m: m.group(0).replace(m.group(1), BIC_PLACEHOLDER), masked)
    masked = _EMAIL.sub(EMAIL_PLACEHOLDER, masked)
    masked = _PHONE.sub(PHONE_PLACEHOLDER, masked)
    masked = _TITLED_NAME.sub(NAME_PLACEHOLDER, masked)
    return masked


def contains_iban(text: str) -> bool:
    return bool(_IBAN.search(text))
