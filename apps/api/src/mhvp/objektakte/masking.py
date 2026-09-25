"""M35 Stufe 3 part 2 (AI stage): masking of personal data before text leaves the CRM for an
external AI provider (rule 0.1.13, DSGVO). No existing masker was found under `mhvp.ai` or
`mhvp.communication` (checked before writing this), so this is a small, dedicated one for the
document classification prompt; it is deliberately conservative (over-masking is acceptable,
an IBAN or phone number reaching the provider is not).

Masks, in this order so a later pattern cannot re-expose what an earlier one hid:
1. IBAN (`DE`-style and generic, spaces optional; rule 0.1.13 cites IBANs by name).
2. E-Mail addresses.
3. Phone numbers (German-style: `+49`/`0` prefix, digits, spaces, hyphens, at least 6 digits).
4. Person names: a conservative heuristic (two or three capitalised words in a row, optionally
   with a title such as "Herr"/"Frau"), since general German NER is out of scope for this
   stage. This heuristic both under- and over-matches (it also catches ordinary capitalised
   phrases such as street names); over-matching is the safe direction here, under-matching is
   noted as an open point (`docs/rules/M35-02.md` addendum) rather than pretended away.

`mask_text` never raises: an input that cannot be parsed as text is returned unchanged, since
document classification tolerates a less useful, still-safe prompt far better than a crash.
"""

from __future__ import annotations

import re

_IBAN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}[0-9]{2}(?:[ ]?[A-Z0-9]{1,4}){2,7}(?![A-Za-z0-9])")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<![\w])(?:\+49|0049|0)[ /()\-]?(?:\d[ /()\-]?){5,13}\d(?![\w])")
_TITLE = r"(?:Herr|Frau|Familie|Firma)\s+"
_NAME_WORD = r"[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?"
_NAME = re.compile(rf"\b(?:{_TITLE})?{_NAME_WORD}(?:\s+{_NAME_WORD}){{1,2}}\b")

IBAN_PLACEHOLDER = "[IBAN]"
EMAIL_PLACEHOLDER = "[E-MAIL]"
PHONE_PLACEHOLDER = "[TELEFON]"
NAME_PLACEHOLDER = "[NAME]"


def mask_text(text: str | None) -> str:
    """Replace IBANs, e-mail addresses, phone numbers and probable person names with a fixed
    placeholder. Order matters: IBAN/e-mail/phone first, so a name-shaped fragment inside one
    of them (unlikely, but not impossible for an all-letter IBAN-like token) is already gone
    before the name pattern runs."""
    if not text:
        return ""
    masked = _IBAN.sub(IBAN_PLACEHOLDER, text)
    masked = _EMAIL.sub(EMAIL_PLACEHOLDER, masked)
    masked = _PHONE.sub(PHONE_PLACEHOLDER, masked)
    masked = _NAME.sub(NAME_PLACEHOLDER, masked)
    return masked


def contains_iban(text: str) -> bool:
    """Used only by tests/assertions that no IBAN reached a provider call."""
    return bool(_IBAN.search(text))
