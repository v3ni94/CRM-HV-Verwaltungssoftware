"""M14 Belegeingang: masking of personal data before the text of a receipt leaves the CRM for
an external AI provider (rule 0.1.13, DSGVO). Modelled on `mhvp.objektakte.masking` (same
order, same placeholders for IBAN, e-mail and phone) with one deliberate difference:

* Person names are masked when introduced by a title (Herr, Frau, Familie, Eheleute,
  z. Hd.) and, deterministically, when they are known names (A65): the person contacts of
  the tenant (`first_name last_name`, `last_name, first_name`) and an issuer name that looks
  like a natural person (`issuer_person_name`, e.g. a sole trader without a legal form
  suffix). The objektakte heuristic hides every run of two or three capitalised words, which
  on an invoice also hides the supplier name ("Elektro Müller GmbH") that the extraction is
  meant to return. Company names are not personal data. A single surname is never masked on
  its own ("Elektro Müller GmbH" must survive); an unknown private supplier whose name is
  neither in the contacts nor in the issuer field remains a gap the reviewer sees in the
  masked excerpt.

Consequence for the IBAN (rule 0.1.6): the model never sees an IBAN, so it cannot propose
one. IBAN candidates are detected deterministically in the unmasked text
(`iban_candidates`), stored encrypted on the draft and shown masked; the reviewer types and
confirms the IBAN before it reaches the invoice draft.

`mask_text` never raises.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

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


# Known person names (A65) --------------------------------------------------------------

_COMPANY_MARKERS = {
    "gmbh", "mbh", "ag", "kg", "ohg", "ug", "gbr", "e.k.", "ek", "e.v.", "ev", "se", "ltd",
    "ltd.", "inc", "inc.", "llc", "sarl", "sa", "co", "co.", "kgaa", "eg", "partg", "&", "und",
    "partner", "partners", "stiftung", "verein", "gesellschaft", "bank", "sparkasse", "stadt",
    "gemeinde", "werke", "service", "services", "handel", "bau", "elektro", "sanitär",
    "heizung", "haustechnik", "hausverwaltung", "verwaltung", "immobilien", "versicherung",
    "kanzlei", "praxis", "büro", "büro.", "amt", "finanzamt", "energie", "netz", "gmbh.",
}  # fmt: skip
_TITLE_WORD = re.compile(r"^(?:Dr|Prof|Dipl|Ing|Mag|Med|Jur|Rer|Nat|Phil|Habil)\.?$", re.I)
# Trade words of a sole trader ("Malerbetrieb Max Mustermann"): dropped, the person part stays.
_TRADE_WORD = re.compile(
    r"^[A-ZÄÖÜ][a-zäöüß]*(?:betrieb|technik|bau|service|handel|werk|werke|praxis|büro|kanzlei"
    r"|verwaltung|meister|dienst|dienste|pflege|reinigung|montage|studio|shop|laden)$"
)
_PERSON_WORD = re.compile(rf"^{_NAME_WORD}$")
MIN_NAME_CHARS = 5


def issuer_person_name(issuer: str | None) -> str | None:
    """The issuer (supplier) name when it looks like a natural person: two to four capitalised
    words (academic titles and a leading trade word such as "Malerbetrieb" are dropped), no
    legal form or trade marker. Returns the normalised person name to mask, otherwise
    ``None``. A single word is never a person name here."""
    if not issuer:
        return None
    words = issuer.replace(",", " ").split()
    if any(word.lower().strip("()") in _COMPANY_MARKERS for word in words):
        return None
    words = [w for w in words if not _TITLE_WORD.match(w) and not _TRADE_WORD.match(w)]
    if not 2 <= len(words) <= 4 or not all(_PERSON_WORD.match(w) for w in words):
        return None
    return " ".join(words)


def name_variants(first_name: str | None, last_name: str | None) -> list[str]:
    """Spellings of one person to mask: ``first last`` and ``last, first``. Both parts are
    required; a surname alone is never masked (it may be part of a company name)."""
    first = " ".join((first_name or "").split())
    last = " ".join((last_name or "").split())
    if not first or not last:
        return []
    return [f"{first} {last}", f"{last}, {first}"]


def compile_names(names: Iterable[str]) -> re.Pattern[str] | None:
    """One case-insensitive pattern for all known names, longest first so that a longer
    name is hidden before a shorter one contained in it; whitespace inside a name matches any
    run of blanks (OCR). Names shorter than ``MIN_NAME_CHARS`` are ignored."""
    cleaned = sorted(
        {" ".join(n.split()) for n in names if n and len(" ".join(n.split())) >= MIN_NAME_CHARS},
        key=lambda n: (-len(n), n),
    )
    if not cleaned:
        return None
    parts = [r"\s+".join(re.escape(word) for word in name.split()) for name in cleaned]
    return re.compile(r"(?<![\w])(?:" + "|".join(parts) + r")(?![\w])", re.IGNORECASE)


def mask_text(text: str | None, names: Iterable[str] = ()) -> str:
    """IBAN, BIC, e-mail, phone, then titled person names and known names (A65). Same order
    as the objektakte masker so a later pattern cannot re-expose what an earlier one hid."""
    if not text:
        return ""
    masked = _IBAN.sub(IBAN_PLACEHOLDER, text)
    masked = _BIC.sub(lambda m: m.group(0).replace(m.group(1), BIC_PLACEHOLDER), masked)
    masked = _EMAIL.sub(EMAIL_PLACEHOLDER, masked)
    masked = _PHONE.sub(PHONE_PLACEHOLDER, masked)
    masked = _TITLED_NAME.sub(NAME_PLACEHOLDER, masked)
    known = compile_names(names)
    if known is not None:
        masked = known.sub(NAME_PLACEHOLDER, masked)
    return masked


def contains_iban(text: str) -> bool:
    return bool(_IBAN.search(text))
