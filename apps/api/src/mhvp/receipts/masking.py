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
  neither in the contacts nor in the issuer field is covered heuristically (A84,
  `header_person_names`): a name line in the sender block of the letterhead (before the
  first address line, professions and academic titles stripped) and a name below a closing
  greeting are masked; a doubtful header line (not followed by an address) only when the
  name occurs at least twice in the document. Heuristic names get a stable placeholder per
  name (``[NAME 1]``, ``[NAME 2]``) so the model can still tell two persons apart.

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
    "stadtwerke", "verband", "innung", "genossenschaft", "kammer", "gruppe", "group",
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


# Heuristic header and signature names (A84) ---------------------------------------------

HEADER_LINES = 8
SIGNATURE_LINES = 3
DOUBTFUL_MIN_OCCURRENCES = 2

_ADDRESS_LINE = re.compile(
    r"(?<!\d)\d{5}\s+[A-ZÄÖÜ]"  # postal code and town
    r"|(?:straße|strasse|str\.|weg|platz|allee|gasse|ring|damm|ufer|chaussee|markt|steig|promenade)"
    r"\s*\d+",
    re.IGNORECASE,
)
_GREETING = re.compile(
    r"^(?:mit\s+(?:freundlichen|besten|freundlichem)\s+gr(?:ü|ue|u)(?:ß|ss)(?:en)?"
    r"|freundliche\s+gr(?:ü|ue)(?:ß|ss)e|viele\s+gr(?:ü|ue)(?:ß|ss)e|beste\s+gr(?:ü|ue)(?:ß|ss)e"
    r"|hochachtungsvoll|mit\s+freundlichen\s+gr(?:ü|ue)(?:ß|ss)en\s+aus\s+\S+)\s*[,.]?\s*$",
    re.IGNORECASE,
)
# Professions and titles that accompany a sole trader's name; dropped, the name stays.
_PROFESSION_WORD = re.compile(
    r"^(?:[A-ZÄÖÜ][a-zäöüß]*meister(?:in)?|Dipl\.?-?\s?Ing\.?|Dipl\.?-?\s?Kfm\.?|Dr\.?"
    r"|Prof\.?|Ing\.?|Ingenieur(?:in)?|Steuerberater(?:in)?|Rechtsanwalt|Rechtsanwältin"
    r"|Architekt(?:in)?|Handwerker(?:in)?|Inhaber(?:in)?|Geschäftsführer(?:in)?"
    r"|Sachverständige[rn]?|Hausmeister(?:in)?|Gärtner(?:in)?|Maler(?:in)?|Elektriker(?:in)?"
    r"|Installateur(?:in)?|Dachdecker(?:in)?|Schornsteinfeger(?:in)?|Fliesenleger(?:in)?"
    r"|Tischler(?:in)?|Schreiner(?:in)?|Klempner(?:in)?|Freiberufler(?:in)?)$"
)
# Words of an invoice head that never form a person name; a line with one of them is no name.
_DOCUMENT_WORDS = {
    "rechnung", "rechnungsnummer", "rechnungsdatum", "angebot", "auftrag", "auftragsnummer",
    "kunde", "kundennummer", "kundennr", "datum", "betreff", "leistung", "leistungszeitraum",
    "seite", "lieferschein", "lieferdatum", "zahlung", "zahlbar", "zahlungsziel", "summe",
    "netto", "brutto", "gesamt", "gesamtbetrag", "position", "pos", "menge", "steuer",
    "steuernummer", "umsatzsteuer", "mwst", "ust", "sehr", "geehrte", "geehrter", "vielen",
    "dank", "bitte", "objekt", "einheit", "wohnung", "mieter", "eigentümer", "an", "von",
    "telefon", "tel", "fax", "mobil", "mail", "email", "e-mail", "web", "www", "iban", "bic",
    "bank", "konto", "kontoinhaber", "gutschrift", "mahnung", "zahlungserinnerung", "anschrift",
    "postfach", "hausnummer", "ort", "plz", "belegnummer", "beleg", "nr", "nummer",
}  # fmt: skip
_SEPARATORS = re.compile(r"[,;|/·•]|\s[-\u2013]\s")


def _line_person_name(line: str) -> str | None:
    """A person name when the line consists of a name plus optional profession or title words
    ("Max Mustermann, Malermeister", "Dipl.-Ing. Anna Maria Schmidt"). Digits, company
    markers and document words disqualify the line; two to three name words remain."""
    if any(ch.isdigit() for ch in line) or ":" in line or "@" in line:
        return None
    words = _SEPARATORS.sub(" ", line).split()
    lowered = [w.lower().strip("().") for w in words]
    if any(w in _COMPANY_MARKERS or w in _DOCUMENT_WORDS for w in lowered):
        return None
    words = [
        w.strip(".")
        for w in words
        if not (_TITLE_WORD.match(w) or _TRADE_WORD.match(w) or _PROFESSION_WORD.match(w))
    ]
    if not 2 <= len(words) <= 3 or not all(_PERSON_WORD.match(w) for w in words):
        return None
    return " ".join(words)


def _header_variants(name: str) -> list[str]:
    parts = name.split()
    return name_variants(" ".join(parts[:-1]), parts[-1]) or [name]


def header_person_names(text: str | None) -> list[str]:
    """Deterministic, conservative candidates of a sole trader's name in the document (A84),
    in order of first appearance, no provider involved:

    * sender block: a name line among the first ``HEADER_LINES`` non-empty lines that is
      followed (within two lines) by an address line is certain;
    * signature: a name line within ``SIGNATURE_LINES`` lines after a closing greeting is
      certain;
    * a name line in the header without a following address line is doubtful and only kept
      when the name occurs at least ``DOUBTFUL_MIN_OCCURRENCES`` times in the document.

    Company names (legal form or trade marker) and lines with document words are never
    candidates. Returns the names as written in the header (``Vorname Nachname``)."""
    if not text:
        return []
    lines = [" ".join(ln.split()) for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    certain: list[str] = []
    doubtful: list[str] = []

    def add(bucket: list[str], name: str) -> None:
        if bucket is certain and name in doubtful:
            doubtful.remove(name)
        if name not in certain and name not in doubtful:
            bucket.append(name)

    for index, line in enumerate(lines[:HEADER_LINES]):
        if _ADDRESS_LINE.search(line):
            break
        name = _line_person_name(line)
        if name is None:
            continue
        following = lines[index + 1 : index + 3]
        if any(_ADDRESS_LINE.search(ln) for ln in following):
            add(certain, name)
        else:
            add(doubtful, name)

    for index, line in enumerate(lines):
        if not _GREETING.match(line):
            continue
        for candidate in lines[index + 1 : index + 1 + SIGNATURE_LINES]:
            name = _line_person_name(candidate)
            if name is not None:
                add(certain, name)
                break

    result = list(certain)
    for name in doubtful:
        pattern = compile_names(_header_variants(name))
        if pattern is not None and len(pattern.findall(text)) >= DOUBTFUL_MIN_OCCURRENCES:
            result.append(name)
    return result


def numbered_placeholder(index: int) -> str:
    return f"[NAME {index}]"


def mask_text(
    text: str | None, names: Iterable[str] = (), *, header_names: Iterable[str] = ()
) -> str:
    """IBAN, BIC, e-mail, phone, then titled person names and known names (A65), then the
    heuristic header names (A84) with a stable placeholder per name (``[NAME 1]`` for the
    first name given, ``[NAME 2]`` for the second, both spellings). Same order as the
    objektakte masker so a later pattern cannot re-expose what an earlier one hid."""
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
    cleaned = [" ".join(n.split()) for n in header_names if n]
    for index, name in enumerate(dict.fromkeys(n for n in cleaned if n), start=1):
        pattern = compile_names(_header_variants(name))
        if pattern is not None:
            masked = pattern.sub(numbered_placeholder(index), masked)
    return masked


def contains_iban(text: str) -> bool:
    return bool(_IBAN.search(text))
