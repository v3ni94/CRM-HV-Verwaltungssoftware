"""Stammdatenänderung aus einer Ticket-Mail (lernendes Ticketsystem, Betreiberauftrag
26.09.2026): erkennt in einer eingehenden Mail eine Änderung der eigenen Kontaktdaten des
Absenders (Name, Anschrift, Telefon, E-Mail) und legt dazu einen ``AiProposal`` mit
``entity_type="contact_change"`` und ``context_id=Ticket`` an.

Ablauf und Grenzen (rule 0.1.6, KI liefert nur Vorschläge):

1. Deterministische Vorstufe (``detect``): Schlüsselwörter je Kategorie, die Muster "von X in
   Y", "heiße jetzt X", "neuer Name lautet X", "trage wieder meinen Geburtsnamen X",
   Umfirmierung ("firmiert unter X GmbH"), PLZ/Ort in beiden Reihenfolgen, Straße/Hausnummer
   (Suffixe, Präfixe wie "Am", Zusätze wie "7a"), ein Datum "ab dem ..." zur Anschrift,
   E-Mail- und Telefonwerte im Umfeld der Schlüsselwörter, die Anrede aus der eigenen Signatur
   des Absenders, Absenderabgleich über den beim Mail-Eingang gesetzten Kontakt
   (``Message.contact_id``), sonst Namenssuche im Mandanten. Der Korpus in
   ``tests/unit/test_ticket_proposal_corpus.py`` sichert die Trefferquote (M19-05).
2. Verfeinerung über den vorhandenen KI-Provider (``AiTask.CONTACT_MASTER_DATA_CHANGE``, gleiche
   Freigabe-, Budget- und Auditlogik wie alle Läufe). E-Mail-Adressen, Telefonnummern und
   IBANs verlassen die Plattform nur maskiert (``mhvp.objektakte.masking.mask_identifiers``);
   die Werte dafür stammen ausschließlich aus der deterministischen Stufe. Ohne freigegebenen
   Anbieter wird nur die deterministische Erkennung verwendet.
3. Bankverbindungen werden nur als Hinweis gemeldet (``bank_change_mentioned``); eine IBAN wird
   nie als Feld vorgeschlagen und bei Annahme oder Korrektur abgewiesen.
4. Entscheidung (accept, correct, reject) über die Endpunkte unter ``/tickets/{id}/proposals``;
   Annahme und Korrektur übernehmen die Felder über denselben Weg wie ``PUT /contacts/{id}``
   (Änderungshistorie über ``contact.updated`` mit Diff, Version, Audit). Jede Entscheidung
   schreibt ein ``AiExample`` des Mandanten (Few-Shot-Kontext künftiger Läufe, 9.1).
5. Der vorbereitete Antwortentwurf (``reply_draft``) bestätigt je Änderungsart: Name und
   Firma ("Stammdaten soeben korrigiert"), Anschrift mit Datum (aus der Mail, sonst Tag der
   Korrektur), E-Mail und Telefon mit dem neuen Wert. Die Anrede nutzt das Geschlecht nur, wenn
   es aus dem Kontakt oder der Signatur der Mail bekannt ist ("Hallo Frau Müller"), sonst
   "Guten Tag Vorname Nachname". Er wird nur auf Anforderung als ``Message``-Entwurf am Ticket
   angelegt und läuft über den bestehenden Antwortweg (Entwurf, Einreichen, Vier-Augen-Freigabe,
   ``mhvp.communication.routers``); nichts wird hier versendet.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai.models import AiExample, AiProposal, AiTask, AiTaskRun, Decision, RunStatus
from mhvp.communication.models import Message
from mhvp.contacts import schemas as contact_schemas
from mhvp.contacts import services as contact_services
from mhvp.contacts.models import Contact, ContactKind
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.config import Settings
from mhvp.core.events import diff, emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.objektakte.masking import mask_identifiers
from mhvp.tickets.models import Ticket, TicketEvent

log = logging.getLogger(__name__)

ENTITY_TYPE = "contact_change"
MAX_EXCERPT = 4000
MIN_AI_CONFIDENCE = 0.5
ALLOWED_FIELDS: frozenset[str] = frozenset(
    {
        "salutation",
        "title",
        "first_name",
        "last_name",
        "company_name",
        "street",
        "house_number",
        "postal_code",
        "city",
        "phone",
        "email",
    }
)
_NAME_FIELDS = ("salutation", "title", "first_name", "last_name", "company_name")
_ADDRESS_FIELDS = ("street", "house_number", "postal_code", "city")
_FIELD_ORDER = (*_NAME_FIELDS, *_ADDRESS_FIELDS, "phone", "email")
# Felder, die nie über einen Vorschlag geändert werden (rule 0.1.6: keine automatische IBAN).
BLOCKED_FIELDS: frozenset[str] = frozenset(
    {"iban", "bic", "bank_name", "bank_account", "bank_accounts", "holder", "mandate_reference"}
)

KEYWORDS: dict[str, tuple[str, ...]] = {
    "name": (
        "namensänderung",
        "name hat sich",
        "mein name hat",
        "neuer name",
        "neuen namen",
        "neuer nachname",
        "neuen nachnamen",
        "heirat",
        "hochzeit",
        "geheiratet",
        "scheidung",
        "geschieden",
        "nachname",
        "familienname",
        "geburtsname",
        "mädchenname",
        "name lautet",
        "heiße jetzt",
        "heisse jetzt",
        "heiße nun",
        "heisse nun",
        "heiße ich",
        "heisse ich",
        "heiße ab",
        "heisse ab",
        "heiße seit",
        "heisse seit",
        "namen geändert",
        "name geändert",
    ),
    "company": (
        "umfirmiert",
        "umfirmierung",
        "firmiert",
        "firmierung",
        "firmenname",
        "firma heißt",
        "firma heisst",
        "gesellschaft heißt",
        "unternehmen heißt",
    ),
    "address": (
        "umgezogen",
        "umzug",
        "umziehen",
        "ziehe um",
        "ziehen um",
        "ziehe ich um",
        "ziehen wir um",
        "neue adresse",
        "neue anschrift",
        "neue wohnung",
        "neue wohnanschrift",
        "neue postanschrift",
        "adressänderung",
        "anschriftenänderung",
        "adresse hat sich",
        "anschrift hat sich",
        "adresse lautet",
        "anschrift lautet",
        "adresse geändert",
        "anschrift geändert",
        "wohne jetzt",
        "wohne ab",
        "wohne seit",
        "wohne ich",
        "wohnen jetzt",
        "wohnen ab",
        "wohnen seit",
        "wohnen wir",
        "wohnhaft",
    ),
    "phone": (
        "neue telefonnummer",
        "neue rufnummer",
        "neue handynummer",
        "neue mobilnummer",
        "neue mobilfunknummer",
        "neue festnetznummer",
        "neue nummer",
        "telefonnummer hat sich",
        "rufnummer hat sich",
        "handynummer hat sich",
        "mobilnummer hat sich",
        "nummer hat sich",
        "telefonnummer geändert",
        "rufnummer geändert",
        "handynummer geändert",
        "telefonnummer lautet",
        "rufnummer lautet",
        "handynummer lautet",
        "telefonisch jetzt",
        "telefonisch ab sofort",
        "telefonisch nur noch",
        "ab sofort erreichbar",
        "jetzt erreichbar",
        "nun erreichbar",
        "künftig erreichbar",
        "zukünftig erreichbar",
        "nur noch erreichbar",
        "ab sofort unter",
        "künftig unter",
        "zukünftig unter",
        "nur noch unter",
    ),
    "email": (
        "neue e-mail",
        "neue email",
        "neue mailadresse",
        "neue mail-adresse",
        "neue e-mailadresse",
        "e-mail-adresse hat sich",
        "e-mail hat sich",
        "emailadresse hat sich",
        "mailadresse hat sich",
        "e-mail-adresse lautet",
        "e-mail-adresse geändert",
        "mailadresse geändert",
        "e-mail ab sofort",
        "e-mails ab sofort",
        "e-mails bitte",
        "e-mails künftig",
        "e-mails zukünftig",
        "mails bitte",
        "mails künftig",
        "per e-mail bitte",
        "ab sofort unter",
        "künftig unter",
        "zukünftig unter",
        "nur noch unter",
    ),
    "bank": ("bankverbindung", "iban", "kontonummer", "konto hat sich", "neues konto"),
}
# Keywords that name the changed value itself; a value may then stand anywhere in the text.
# The generic ones ("ab sofort unter") only count when the value follows within a short range.
_SPECIFIC_MARKERS = {"phone": ("nummer", "telefon"), "email": ("mail",)}
_GENERIC_RANGE = 120

# Words that end a captured name, street or city (line starts, greetings, connectors).
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "ab",
        "alle",
        "als",
        "auch",
        "beste",
        "bitte",
        "danke",
        "das",
        "der",
        "die",
        "freundliche",
        "geaendert",
        "geändert",
        "gewechselt",
        "gruss",
        "gruß",
        "grüsse",
        "grüße",
        "herzliche",
        "ich",
        "ihre",
        "liebe",
        "mein",
        "meine",
        "mit",
        "neue",
        "seit",
        "sie",
        "umbenannt",
        "und",
        "unsere",
        "viele",
        "vielen",
        "wir",
        "zu",
    }
)
_HONORIFICS = ("frau", "herr", "herrn", "dr.", "prof.", "dr", "prof")
_STREET_LEAD_STOP = frozenset(
    {
        "anschrift",
        "adresse",
        "wohnanschrift",
        "postanschrift",
        "wohnung",
        "neue",
        "meine",
        "unsere",
        "lautet",
        "jetzt",
        "nun",
        "ab",
        "in",
        "der",
        "die",
        "nr",
        "nr.",
    }
)

_NAME_WORD = r"[A-ZÄÖÜ][\wäöüß]+(?:-[A-ZÄÖÜ][\wäöüß]+)*"
_NAME_SEQ = rf"{_NAME_WORD}(?:[ \t]+{_NAME_WORD}){{0,3}}"
_VON_IN = re.compile(rf"\bvon\s+({_NAME_SEQ})\s+(?:in|zu|auf)\s+({_NAME_SEQ})\b")
_QUAL = r"(?:(?:jetzt|nun|wieder|künftig|zukünftig|ab[ \t]+sofort|seit[ \t]+\S+)[ \t]+){0,2}"
_NEW_NAME = re.compile(
    rf"(?:hei(?:ß|ss)en?[ \t]+(?:ich[ \t]+|wir[ \t]+)?{_QUAL}:?[ \t]*"
    rf"|(?:neuer?|mein[ \t]+neuer|unser[ \t]+neuer)[ \t]+(?:name|nachname|familienname)"
    rf"(?:[ \t]+(?:lautet|ist))?[ \t]*:?[ \t]*"
    rf"|(?:name|nachname|familienname)[ \t]+(?:lautet|ist)[ \t]+{_QUAL}:?[ \t]*"
    rf"|(?:trage|führe|führen|tragen)[ \t]+(?:ich[ \t]+|wir[ \t]+)?{_QUAL}"
    rf"(?:meinen[ \t]+|unseren[ \t]+|den[ \t]+)?(?:geburtsnamen|mädchennamen|nachnamen|namen)[ \t]+"
    rf"|(?:geburtsnamen?|mädchennamen?)[ \t]+"
    rf")({_NAME_SEQ})",
    re.IGNORECASE,
)
_LEGAL_FORM = (
    r"(?:GmbH(?:[ \t]*&[ \t]*Co\.?[ \t]*KG)?|AG(?:[ \t]*&[ \t]*Co\.?[ \t]*KG)?|KG|OHG|GbR|SE"
    r"|e\.[ \t]?K\.|e\.[ \t]?V\.|UG(?:[ \t]*\(haftungsbeschränkt\))?|mbH|Ltd\.?|Inc\.?)"
)
_COMPANY_WORD = r"(?:[A-ZÄÖÜ][\wäöüß.\-]*|&|und|\+)"
_COMPANY = rf"((?:{_COMPANY_WORD}[ \t]+){{1,5}}{_LEGAL_FORM})(?![\wäöüß])"
_COMPANY_VON_IN = re.compile(rf"\bvon[ \t]+{_COMPANY}[ \t]+(?:in|zu|auf)[ \t]+{_COMPANY}")
_COMPANY_NEW = re.compile(
    rf"(?:firmier(?:t|en)[ \t]+{_QUAL}(?:unter|als)[ \t]+"
    rf"|(?:firma|gesellschaft|unternehmen|wir)[ \t]+hei(?:ß|ss)(?:t|en)[ \t]+{_QUAL}:?[ \t]*"
    rf"|(?:neuer[ \t]+firmenname|neue[ \t]+firmierung|firmenname|firmierung)"
    rf"(?:[ \t]+(?:lautet|ist))?(?:[ \t]+(?:jetzt|nun|ab[ \t]+sofort))?[ \t]*:?[ \t]*"
    rf"){_COMPANY}",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<![\w])(?:\+49|0049|0)[ /()\-]?(?:\d[ /()\-]?){5,13}\d(?![\w])")
_CITY_WORD = r"[A-ZÄÖÜ][\wäöüß\-]+"
_CITY = (
    rf"{_CITY_WORD}(?:[ \t]+(?:am|an|im|in|bei|an[ \t]+der|in[ \t]+der)[ \t]+{_CITY_WORD}"
    rf"|[ \t]+{_CITY_WORD}){{0,2}}"
)
_POSTAL_CITY = re.compile(rf"\b(\d{{5}})[ \t]+({_CITY})")
_CITY_POSTAL = re.compile(rf"\b({_CITY}),?[ \t]+(\d{{5}})\b")
_STREET_SUFFIX = (
    r"(?i:straße|strasse|str\.|str\b|weg|platz|allee|gasse|ring|damm|ufer|chaussee|steig|stieg"
    r"|hof|markt|promenade|wall|graben|berg|feld|winkel|pfad|zeile|park|kamp|busch|garten"
    r"|anger|höhe|hoehe|tal|brücke|bruecke|redder|twiete|stegen)"
)
_STREET_WORD = r"[A-ZÄÖÜ][\wäöüß\-]*"
_STREET_PREFIX = (
    r"(?:Am|An[ \t]+der|An[ \t]+den|Im|In[ \t]+der|In[ \t]+den|Auf[ \t]+dem|Auf[ \t]+der|Zum|Zur"
    r"|Unter[ \t]+den|Hinter[ \t]+dem|Vor[ \t]+dem|Bei[ \t]+der|Alte|Alter|Neue|Neuer|Obere"
    r"|Untere|Kleine|Große|Grosse)"
)
_STREET = re.compile(
    rf"\b((?:{_STREET_WORD}[ \t]+){{0,2}}{_STREET_WORD}{_STREET_SUFFIX}"
    rf"|{_STREET_PREFIX}[ \t]+{_STREET_WORD}(?:[ \t]+{_STREET_WORD})?"
    rf"|{_STREET_WORD}(?:[ \t]+{_STREET_WORD})?[ \t]+{_STREET_SUFFIX})"
    rf"[ \t]+(?:Nr\.?[ \t]*)?(\d{{1,4}}[ \t]?[a-zA-Z]?(?:[ \t]?[-/][ \t]?\d{{1,4}}[a-zA-Z]?)?)"
    rf"(?!\d|\.\d)"
)
_HOUSE_ADDITION = re.compile(r"^(\d{1,4})[ \t]([a-zA-Z])$")
_MONTHS = {
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "maerz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}
_ADDRESS_DATE = re.compile(
    r"\b(?:ab|zum|seit)[ \t]+(?:dem[ \t]+|den[ \t]+)?"
    r"(?:(\d{1,2})\.[ \t]?(\d{1,2})\.[ \t]?(\d{4}|\d{2})"
    r"|(\d{1,2})\.[ \t]?(" + "|".join(_MONTHS) + r")[ \t]+(\d{4}))\b",
    re.IGNORECASE,
)
_TRAILING_STOP = re.compile(r"\s+(?:geändert|geaendert|umbenannt|gewechselt)$", re.IGNORECASE)
_SIGNATURE_SALUTATION = re.compile(
    rf"\b(Frau|Herr|Herrn)[ \t]+(?:Dr\.[ \t]+|Prof\.[ \t]+)?({_NAME_SEQ})"
)
_SIGNATURE_LINE = re.compile(
    rf"^[ \t]*(Ihre|Ihr|Eure|Euer)[ \t]+({_NAME_SEQ})[ \t]*$", re.MULTILINE
)


# Deterministic stage ------------------------------------------------------------------------


@dataclass
class Detection:
    categories: list[str] = field(default_factory=list)
    name_old: str | None = None
    name_new: str | None = None
    changes: list[dict[str, Any]] = field(default_factory=list)
    bank_change_mentioned: bool = False
    company_old: str | None = None
    company_new: str | None = None
    # Date named for the new address ("ab dem 01.10.2026"), ISO 8601; only used in the reply.
    address_valid_from: str | None = None
    # "Frau" or "Herr" when the sender signs with a salutation ("Frau Isabel Roth", "Ihr Max").
    salutation: str | None = None

    @property
    def hit(self) -> bool:
        return bool(self.changes) or bool(self.categories)


def _split_name(full: str) -> tuple[str | None, str]:
    parts = full.split()
    if len(parts) == 1:
        return None, parts[0]
    return " ".join(parts[:-1]), parts[-1]


def _change(field_name: str, old: str | None, new: str | None, confidence: float) -> dict[str, Any]:
    return {"field": field_name, "old": old, "new": new, "confidence": confidence}


def _trim_words(value: str, *, leading: frozenset[str] = frozenset()) -> str:
    """Drops honorifics and leading marker words, then everything from the first stop word."""
    words = value.replace("\n", " ").split()
    while words and (words[0].lower() in _HONORIFICS or words[0].lower() in leading):
        words.pop(0)
    kept: list[str] = []
    for word in words:
        if word.lower() in _STOP_WORDS:
            break
        kept.append(word)
    return " ".join(kept)


def _clean_name(value: str) -> str:
    return _trim_words(_TRAILING_STOP.sub("", value).strip(" ,.;:"))


def _clean_city(value: str) -> str | None:
    city = _trim_words(value.strip(" ,.;:"))
    if not city or city.lower().endswith(("nummer", "nr", "nr.")):
        return None
    return city


def _keyword_positions(lower: str, category: str) -> list[tuple[int, bool]]:
    """Start offsets of the category's keywords, flagged whether the keyword is specific."""
    markers = _SPECIFIC_MARKERS.get(category, ())
    found: list[tuple[int, bool]] = []
    for word in KEYWORDS[category]:
        start = lower.find(word)
        while start >= 0:
            found.append((start, any(m in word for m in markers)))
            start = lower.find(word, start + 1)
    return sorted(found)


def _value_after(
    text: str, lower: str, category: str, pattern: re.Pattern[str], skip: str | None = None
) -> str | None:
    """First value of ``pattern`` that follows a keyword of the category: directly after a
    generic keyword (short range) or anywhere after a specific one; as a fallback the first
    value in the text when a specific keyword exists at all."""
    values = [(m.start(), m.group(0).strip()) for m in pattern.finditer(text)]
    values = [(pos, v) for pos, v in values if skip is None or v.lower() != skip]
    if not values:
        return None
    positions = _keyword_positions(lower, category)
    for start, specific in positions:
        for pos, value in values:
            if pos >= start and (specific or pos - start <= _GENERIC_RANGE):
                return value
    if any(specific for _, specific in positions):
        return values[0][1]
    return None


def _detect_company(text: str, result: Detection) -> None:
    match = _COMPANY_VON_IN.search(text)
    if match:
        result.company_old = match.group(1).strip()
        result.company_new = match.group(2).strip()
    else:
        found = _COMPANY_NEW.search(text)
        if found:
            result.company_new = found.group(1).strip()
    if result.company_new and result.company_new != result.company_old:
        result.changes.append(_change("company_name", result.company_old, result.company_new, 0.7))


def _detect_person_name(text: str, result: Detection) -> None:
    match = _VON_IN.search(text)
    if match:
        old_full, new_full = _clean_name(match.group(1)), _clean_name(match.group(2))
        if old_full and new_full:
            result.name_old, result.name_new = old_full, new_full
            old_first, old_last = _split_name(old_full)
            new_first, new_last = _split_name(new_full)
            if old_last != new_last:
                result.changes.append(_change("last_name", old_last, new_last, 0.8))
            if new_first and old_first and old_first != new_first:
                result.changes.append(_change("first_name", old_first, new_first, 0.6))
            return
    found = _NEW_NAME.search(text)
    if found:
        new_full = _clean_name(found.group(1))
        if new_full:
            result.name_new = new_full
            _, new_last = _split_name(new_full)
            result.changes.append(_change("last_name", None, new_last, 0.7))


def _iso_date(match: re.Match[str]) -> str | None:
    try:
        if match.group(1):
            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            if year < 100:
                year += 2000
        else:
            day, year = int(match.group(4)), int(match.group(6))
            month = _MONTHS[match.group(5).lower()]
        return date(year, month, day).isoformat()
    except (ValueError, KeyError):
        return None


def _detect_address(text: str, result: Detection) -> None:
    street = _STREET.search(text)
    if street:
        name = _trim_words(street.group(1), leading=_STREET_LEAD_STOP)
        number = _HOUSE_ADDITION.sub(r"\1\2", street.group(2).strip())
        if name:
            result.changes.append(_change("street", None, name, 0.6))
            result.changes.append(_change("house_number", None, number, 0.6))
    postal_code = city = None
    postal = _POSTAL_CITY.search(text)
    if postal:
        postal_code, city = postal.group(1), _clean_city(postal.group(2))
    if city is None:
        reverse = _CITY_POSTAL.search(text)
        if reverse:
            candidate = _clean_city(reverse.group(1))
            if candidate:
                postal_code, city = reverse.group(2), candidate
    if postal_code and city:
        result.changes.append(_change("postal_code", None, postal_code, 0.7))
        result.changes.append(_change("city", None, city, 0.6))
    when = _ADDRESS_DATE.search(text)
    if when:
        result.address_valid_from = _iso_date(when)


def _detect_salutation(text: str, result: Detection) -> None:
    """Gender only when the sender signs with it; "Sehr geehrte Frau X" addresses the
    recipient and is ignored unless X is the sender's own (old or new) surname."""
    surnames = {_split_name(n)[1].lower() for n in (result.name_new, result.name_old) if n}
    for match in _SIGNATURE_SALUTATION.finditer(text):
        name = _clean_name(match.group(2))
        own = bool(name) and (not surnames or _split_name(name)[1].lower() in surnames)
        if own and (surnames or text.rstrip().endswith(match.group(0).strip())):
            result.salutation = "Frau" if match.group(1) == "Frau" else "Herr"
            return
    line = _SIGNATURE_LINE.search(text)
    if line:
        name = _clean_name(line.group(2))
        if name and (not surnames or _split_name(name)[1].lower() in surnames):
            result.salutation = "Frau" if line.group(1) in ("Ihre", "Eure") else "Herr"


def detect(subject: str | None, body: str | None, sender: str | None = None) -> Detection:
    """Keyword and pattern stage; never raises. Only the sender's own data is targeted; values
    for phone and e-mail come from here (the provider only sees placeholders)."""
    text = f"{subject or ''}\n{body or ''}"
    lower = text.lower()
    result = Detection()
    for category, words in KEYWORDS.items():
        if any(w in lower for w in words):
            result.categories.append(category)
    result.bank_change_mentioned = "bank" in result.categories

    if "company" in result.categories:
        _detect_company(text, result)
    if "name" in result.categories and result.company_new is None:
        _detect_person_name(text, result)

    if "address" in result.categories:
        _detect_address(text, result)

    if "phone" in result.categories:
        phone = _value_after(body or "", (body or "").lower(), "phone", _PHONE)
        if phone:
            result.changes.append(_change("phone", None, phone, 0.7))

    if "email" in result.categories:
        email = _value_after(
            body or "", (body or "").lower(), "email", _EMAIL, (sender or "").lower() or None
        )
        if email:
            result.changes.append(_change("email", None, email, 0.7))

    _detect_salutation(body or "", result)
    return result


# Contact matching ---------------------------------------------------------------------------


@dataclass
class Match:
    contact_id: uuid.UUID | None
    matched_by: str | None
    candidates: list[dict[str, Any]] = field(default_factory=list)


async def match_contact(
    session: AsyncSession, message: Message, ticket: Ticket, detection: Detection
) -> Match:
    if message.contact_id is not None:
        return Match(message.contact_id, "sender_email")
    if detection.company_old:
        companies = list(
            await session.scalars(
                select(Contact)
                .where(
                    Contact.deleted_at.is_(None),
                    Contact.kind == ContactKind.COMPANY,
                    func.lower(Contact.company_name) == detection.company_old.lower(),
                )
                .order_by(Contact.display_name)
                .limit(6)
            )
        )
        if len(companies) == 1:
            return Match(companies[0].id, "name")
    if detection.name_old:
        first, last = _split_name(detection.name_old)
        query = select(Contact).where(
            Contact.deleted_at.is_(None),
            Contact.kind == ContactKind.PERSON,
            func.lower(Contact.last_name) == last.lower(),
        )
        if first:
            query = query.where(func.lower(Contact.first_name) == first.lower())
        rows = list(await session.scalars(query.order_by(Contact.display_name).limit(6)))
        if len(rows) == 1:
            return Match(rows[0].id, "name")
        if rows:
            return Match(
                None,
                None,
                [{"id": str(r.id), "display_name": r.display_name} for r in rows],
            )
    linked = ticket.contact_id or ticket.initiator_contact_id
    if linked is not None:
        return Match(linked, "ticket")
    return Match(None, None)


# AI refinement ------------------------------------------------------------------------------


def _prompt_text(message: Message, detection: Detection) -> str:
    masked = mask_identifiers((message.body or "")[:MAX_EXCERPT])
    hints = ", ".join(detection.categories) or "-"
    return (
        f"Betreff: {mask_identifiers(message.subject or '')}\n"
        f"Text (Auszug, Kennungen maskiert):\n{masked}\n\n"
        f"Deterministische Hinweise: {hints}\n"
        "Melde nur Änderungen der eigenen Daten des Absenders."
    )


async def _ai_result(
    settings: Settings, message: Message, detection: Detection
) -> tuple[AiTaskRun | None, dict[str, Any] | None, str | None]:
    """Runs the gateway task; returns (run, output, skip_reason). Never raises."""
    from mhvp.communication.suggest import _run_gateway_task

    context = {"context_type": "message", "context_id": str(message.id)}
    try:
        run = await _run_gateway_task(
            settings,
            message.tenant_id,
            AiTask.CONTACT_MASTER_DATA_CHANGE,
            _prompt_text(message, detection),
            context,
        )
    except Exception as exc:  # gateway problems never block the deterministic stage
        log.warning("contact change run failed", extra={"message_id": str(message.id)})
        return None, None, str(exc)[:500]
    if run.status is RunStatus.SUCCEEDED and run.output:
        return run, run.output, None
    return run, None, run.error or "KI-Lauf ohne Ergebnis."


def merge(detection: Detection, ai: dict[str, Any] | None) -> list[dict[str, Any]]:
    """AI wins for name and address fields (it reads the whole sentence), the deterministic
    stage always supplies phone and e-mail (the provider only saw placeholders)."""
    merged: dict[str, dict[str, Any]] = {c["field"]: c for c in detection.changes}
    if ai is not None:
        for change in ai.get("changes", []):
            name = change.get("field")
            if name not in ALLOWED_FIELDS or name in ("phone", "email"):
                continue
            if change.get("new") in (None, "") or float(change.get("confidence", 0)) < (
                MIN_AI_CONFIDENCE
            ):
                continue
            merged[name] = _change(
                name,
                change.get("old"),
                str(change["new"]).strip(),
                min(max(float(change.get("confidence", 0)), 0.0), 1.0),
            )
    return [merged[k] for k in sorted(merged, key=_FIELD_ORDER.index)]


# Proposal build -----------------------------------------------------------------------------


def _full_name(contact: Contact | None) -> str | None:
    if contact is None:
        return None
    if contact.kind is ContactKind.COMPANY:
        return contact.company_name
    return " ".join(p for p in (contact.first_name, contact.last_name) if p) or None


def _apply_name(base: str | None, changes: list[dict[str, Any]]) -> str | None:
    company = next((c["new"] for c in changes if c["field"] == "company_name"), None)
    if company:
        return str(company)
    first, last = _split_name(base) if base else (None, None)
    values: dict[str, str | None] = {"first_name": first, "last_name": last}
    for change in changes:
        if change["field"] in ("first_name", "last_name"):
            values[change["field"]] = change["new"]
    return " ".join(p for p in (values["first_name"], values["last_name"]) if p) or None


FIELD_LABELS = {
    "salutation": "Anrede",
    "title": "Titel",
    "first_name": "Vorname",
    "last_name": "Nachname",
    "company_name": "Firma",
    "street": "Straße",
    "house_number": "Hausnummer",
    "postal_code": "PLZ",
    "city": "Ort",
    "phone": "Telefon",
    "email": "E-Mail",
}


def title_for(old_name: str | None, new_name: str | None, changes: list[dict[str, Any]]) -> str:
    who = old_name or "unbekannt"
    if new_name and new_name != old_name:
        return f"Stammdatenänderung: Kontakt {who} ändern zu {new_name}"
    fields = ", ".join(FIELD_LABELS.get(c["field"], c["field"]) for c in changes) or "Prüfung"
    return f"Stammdatenänderung: Kontakt {who}, {fields}"


def greeting_for(salutation: str | None, last_name: str | None, full_name: str | None) -> str:
    """ "Hallo Frau Müller" only when the gender is known (contact record or the sender's own
    signature in the mail); otherwise the neutral "Guten Tag Vorname Nachname"."""
    if salutation in ("Herr", "Frau") and last_name:
        return f"Hallo {salutation} {last_name}"
    if full_name:
        return f"Guten Tag {full_name}"
    return "Guten Tag"


def _format_date(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        return date.fromisoformat(iso).strftime("%d.%m.%Y")
    except ValueError:
        return None


def reply_sentences(
    changes: list[dict[str, Any]] | None,
    address_valid_from: str | None = None,
    today: date | None = None,
) -> str:
    """One confirmation sentence per kind of change: name and company ("Stammdaten
    korrigiert"), address with the date it applies from (the date named in the mail, else the
    day of the correction), e-mail and phone with the new value."""
    values = {c["field"]: str(c.get("new") or "").strip() for c in changes or []}
    parts: list[str] = []
    if any(f in values for f in _NAME_FIELDS) or not values:
        parts.append("Wir haben unsere Stammdaten soeben korrigiert.")
    if any(f in values for f in _ADDRESS_FIELDS):
        line1 = " ".join(v for v in (values.get("street"), values.get("house_number")) if v)
        line2 = " ".join(v for v in (values.get("postal_code"), values.get("city")) if v)
        address = ", ".join(p for p in (line1, line2) if p)
        when = _format_date(address_valid_from)
        if when:
            parts.append(
                f"Ihre neue Anschrift {address} haben wir ab dem {when} in unseren "
                "Stammdaten hinterlegt."
            )
        else:
            stamp = (today or datetime.now(UTC).date()).strftime("%d.%m.%Y")
            parts.append(
                f"Ihre neue Anschrift {address} haben wir zum {stamp} in unseren "
                "Stammdaten hinterlegt."
            )
    if values.get("email"):
        parts.append(
            f"Ihre neue E-Mail-Adresse {values['email']} haben wir hinterlegt und schreiben "
            "Sie künftig unter dieser Adresse an."
        )
    if values.get("phone"):
        parts.append(f"Ihre neue Telefonnummer {values['phone']} haben wir hinterlegt.")
    return " ".join(parts)


def reply_draft(
    subject: str | None,
    greeting: str,
    changes: list[dict[str, Any]] | None = None,
    address_valid_from: str | None = None,
    today: date | None = None,
) -> dict[str, str]:
    return {
        "subject": f"AW: {subject or 'Ihre Stammdaten'}"[:998],
        "body": (
            f"{greeting},\n\nvielen Dank. "
            f"{reply_sentences(changes, address_valid_from, today)}\n\n"
            "Mit freundlichen Grüßen\n[Name]\n[Firma]"
        ),
    }


def _reply_for(
    contact: Contact | None,
    changes: list[dict[str, Any]],
    subject: str | None,
    mail_salutation: str | None = None,
    address_valid_from: str | None = None,
) -> dict[str, str]:
    values = {
        "salutation": (contact.salutation if contact else None) or mail_salutation,
        "last_name": contact.last_name if contact else None,
        "first_name": contact.first_name if contact else None,
        "company_name": contact.company_name if contact else None,
    }
    for change in changes:
        if change["field"] in values:
            values[change["field"]] = change["new"]
    first, last = values["first_name"], values["last_name"]
    full = f"{first} {last}" if first and last else None
    if full is None and values["company_name"]:
        return reply_draft(subject, "Sehr geehrte Damen und Herren", changes, address_valid_from)
    greeting = greeting_for(values["salutation"], values["last_name"], full)
    return reply_draft(subject, greeting, changes, address_valid_from)


async def _existing(
    session: AsyncSession, ticket_id: uuid.UUID, message_id: uuid.UUID
) -> AiProposal | None:
    rows = await session.scalars(
        select(AiProposal).where(
            AiProposal.entity_type == ENTITY_TYPE,
            AiProposal.context_id == ticket_id,
            AiProposal.decision == Decision.PENDING,
        )
    )
    for row in rows:
        if row.proposed.get("message_id") == str(message_id):
            return row
    return None


async def propose_contact_change(
    session: AsyncSession,
    settings: Settings,
    ticket: Ticket,
    message: Message,
    actor_user_id: uuid.UUID | None,
) -> AiProposal | None:
    """Builds the proposal for one inbound message of a ticket. Returns ``None`` when neither
    stage finds a master data change; never raises for provider problems."""
    existing = await _existing(session, ticket.id, message.id)
    if existing is not None:
        return existing
    detection = detect(message.subject, message.body, message.from_address)
    run, ai, skip_reason = await _ai_result(settings, message, detection)
    if ai is not None and not ai.get("is_master_data_change"):
        return None
    if ai is None and not detection.changes:
        return None
    changes = merge(detection, ai)
    if (
        not changes
        and not (ai or {}).get("bank_change_mentioned")
        and not detection.bank_change_mentioned
    ):
        return None
    if run is None:
        # Kein Lauf (Ausnahme vor dem Gateway): Vorschlag braucht einen Lauf als Nachweis.
        run = AiTaskRun(
            tenant_id=ticket.tenant_id,
            task=AiTask.CONTACT_MASTER_DATA_CHANGE,
            prompt_version="v1",
            input_hash="",
            input_ref={"context": {"context_type": "message", "context_id": str(message.id)}},
            status=RunStatus.BLOCKED,
            error=skip_reason,
        )
        session.add(run)
        await session.flush()
    match = await match_contact(session, message, ticket, detection)
    contact = await session.get(Contact, match.contact_id) if match.contact_id else None
    old_name = _full_name(contact) or detection.name_old or (ai or {}).get("contact_name_old")
    new_name = _apply_name(old_name, changes)
    bank_mentioned = bool(
        detection.bank_change_mentioned or (ai or {}).get("bank_change_mentioned")
    )
    proposed: dict[str, Any] = {
        "message_id": str(message.id),
        "title": title_for(old_name, new_name, changes),
        "contact_id": str(match.contact_id) if match.contact_id else None,
        "contact_display_name": contact.display_name if contact else None,
        "matched_by": match.matched_by,
        "candidates": match.candidates,
        "changes": changes,
        "bank_change_mentioned": bank_mentioned,
        "bank_hint": (
            "Die Mail erwähnt eine Bankverbindung. Bankdaten werden nie automatisch übernommen; "
            "bitte manuell mit Nachweis pflegen."
            if bank_mentioned
            else None
        ),
        "reason": (ai or {}).get("reason"),
        "address_valid_from": detection.address_valid_from,
        "mail_salutation": detection.salutation,
        "source": {
            "deterministic": {
                "categories": detection.categories,
                "name_old": detection.name_old,
                "name_new": detection.name_new,
            },
            "ai": "used" if ai is not None else "skipped",
            "ai_reason": skip_reason,
            "model": run.model,
        },
        "reply_draft": _reply_for(
            contact, changes, message.subject, detection.salutation, detection.address_valid_from
        ),
    }
    proposal = AiProposal(
        tenant_id=ticket.tenant_id,
        created_by=actor_user_id,
        task_run_id=run.id,
        entity_type=ENTITY_TYPE,
        context_id=ticket.id,
        proposed=proposed,
    )
    session.add(proposal)
    await session.flush()
    session.add(
        TicketEvent(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            kind="proposal_created",
            data={"proposal_id": str(proposal.id), "title": proposed["title"]},
            user_id=actor_user_id,
        )
    )
    await emit(
        session,
        tenant_id=ticket.tenant_id,
        type="ai_proposal.created",
        entity_type="ai_proposal",
        entity_id=proposal.id,
        actor_user_id=actor_user_id,
        payload={"entity_type": ENTITY_TYPE, "ticket_id": str(ticket.id)},
    )
    return proposal


async def queue_for_message(
    session: AsyncSession, settings: Settings, tenant_id: uuid.UUID, message: Message
) -> None:
    """Called after a ticket received an inbound mail. Inline in tests and development
    (``ai_inline``), otherwise on the ``ai`` queue; a failure never disturbs mail intake."""
    if message.ticket_id is None or message.direction != "in":
        return
    if settings.ai_inline:
        ticket = await session.get(Ticket, message.ticket_id)
        if ticket is None:
            return
        try:
            await propose_contact_change(session, settings, ticket, message, None)
        except Exception:
            log.warning("contact change proposal failed", extra={"message_id": str(message.id)})
        return
    try:
        from mhvp.worker import get_celery

        get_celery().send_task(
            "mhvp.tickets.propose_contact_change",
            args=[str(tenant_id), str(message.ticket_id), str(message.id)],
            queue="ai",
        )
    except Exception:
        log.warning(
            "could not queue contact change proposal", extra={"message_id": str(message.id)}
        )


# Apply --------------------------------------------------------------------------------------


def _validate_changes(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for change in changes:
        name = str(change.get("field", ""))
        if name in BLOCKED_FIELDS or name.startswith("bank"):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Bankverbindungen werden nie über einen Vorschlag geändert.",
            )
        if name not in ALLOWED_FIELDS:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Feld {name} ist nicht zulässig.")
        new = change.get("new")
        if new is None or not str(new).strip():
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Neuer Wert für {name} fehlt.")
        cleaned.append({"field": name, "old": change.get("old"), "new": str(new).strip()})
    if not cleaned:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Keine Feldänderung enthalten.")
    return cleaned


def _to_contact_in(out: contact_schemas.ContactOut) -> dict[str, Any]:
    data = out.model_dump(mode="json")
    for key in ("id", "display_name", "version", "created_at", "updated_at", "deleted_at"):
        data.pop(key, None)
    data["bank_accounts"] = None  # unverändert lassen (rule 0.1.6, nie IBAN über Vorschlag)
    for key in ("addresses", "phones", "emails", "identifiers"):
        data[key] = [{k: v for k, v in item.items() if k != "id"} for item in data[key]]
    return data


async def apply_changes(
    session: AsyncSession,
    principal: TenantPrincipal,
    contact_id: uuid.UUID,
    changes: list[dict[str, Any]],
    proposal_id: uuid.UUID,
) -> dict[str, Any]:
    """Writes the accepted fields through the same path as ``PUT /contacts/{id}`` (apply_fields,
    write_children, version, ``contact.updated`` with diff). Returns the recorded diff."""
    contact = await session.get(Contact, contact_id)
    if contact is None or contact.deleted_at is not None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Kontakt nicht gefunden.")
    before = await contact_services.load(session, contact_id)
    if before is None:  # pragma: no cover - loaded above
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    data = _to_contact_in(before)
    for change in changes:
        name, value = change["field"], change["new"]
        if name in _NAME_FIELDS:
            data[name] = value
        elif name in _ADDRESS_FIELDS:
            addresses = data["addresses"]
            target = next(
                (a for a in addresses if a.get("is_primary")), addresses[0] if addresses else None
            )
            if target is None:
                target = {"label": "postal", "country": "DE", "is_primary": True}
                addresses.append(target)
            target[name] = value
        elif name == "phone":
            for phone in data["phones"]:
                phone["is_primary"] = False
            data["phones"].append({"label": "mobile", "number": value, "is_primary": True})
        elif name == "email":
            for email in data["emails"]:
                email["is_primary"] = False
            data["emails"].append({"label": "work", "email": value, "is_primary": True})
    try:
        body = contact_schemas.ContactIn.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}",
        ) from exc
    contact_services.apply_fields(
        contact, body, await contact_services.iban_suffixes(session, contact_id)
    )
    await contact_services.write_children(session, principal.tenant_id, contact.id, body)
    contact.version += 1
    contact.updated_by = principal.user_id
    after = await contact_services.load(session, contact_id)
    if after is None:  # pragma: no cover
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    ignore = {"version", "updated_at", "created_at"}
    old = before.model_dump(mode="json", exclude=ignore)
    new = after.model_dump(mode="json", exclude=ignore)
    for doc in (old, new):
        for key in ("addresses", "phones", "emails", "identifiers", "bank_accounts"):
            doc[key] = [{k: v for k, v in item.items() if k != "id"} for item in doc[key]]
    changed = diff(old, new)
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type="contact.updated",
        entity_type="contact",
        entity_id=contact.id,
        actor_user_id=principal.user_id,
        payload={
            "fields": sorted(changed),
            "source": "ai_proposal",
            "proposal_id": str(proposal_id),
        },
        changes=changed,
    )
    # display_name is derived from the name fields; the caller only asked for the fields it sent.
    return {k: v for k, v in changed.items() if k != "display_name"}


# API ----------------------------------------------------------------------------------------

router = APIRouter(tags=["Tickets und Aufträge"])
READ = require_permission("tickets:read")
UPDATE = require_permission("tickets:update")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChangeIn(_In):
    field: str = Field(max_length=64)
    old: str | None = Field(default=None, max_length=300)
    new: str | None = Field(default=None, max_length=300)


class CorrectIn(_In):
    contact_id: uuid.UUID | None = None
    changes: list[ChangeIn] = Field(max_length=20)


class RejectIn(_In):
    reason: str | None = Field(default=None, max_length=500)


class ContactChangeContactOut(BaseModel):
    id: uuid.UUID
    display_name: str
    salutation: str | None
    title: str | None
    first_name: str | None
    last_name: str | None
    company_name: str | None
    street: str | None
    house_number: str | None
    postal_code: str | None
    city: str | None
    phone: str | None
    email: str | None


class ContactChangeProposalOut(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    entity_type: str
    decision: Decision
    proposed: dict[str, Any]
    final: dict[str, Any] | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime
    contact: ContactChangeContactOut | None
    reply_message_id: uuid.UUID | None
    reply_message_status: str | None


async def _snapshot(
    session: AsyncSession, contact_id: str | None
) -> ContactChangeContactOut | None:
    if not contact_id:
        return None
    out = await contact_services.load(session, uuid.UUID(contact_id))
    if out is None:
        return None
    address = next(
        (a for a in out.addresses if a.is_primary), out.addresses[0] if out.addresses else None
    )
    phone = next((p for p in out.phones if p.is_primary), out.phones[0] if out.phones else None)
    email = next((e for e in out.emails if e.is_primary), out.emails[0] if out.emails else None)
    return ContactChangeContactOut(
        id=out.id,
        display_name=out.display_name,
        salutation=out.salutation,
        title=out.title,
        first_name=out.first_name,
        last_name=out.last_name,
        company_name=out.company_name,
        street=address.street if address else None,
        house_number=address.house_number if address else None,
        postal_code=address.postal_code if address else None,
        city=address.city if address else None,
        phone=phone.number if phone else None,
        email=email.email if email else None,
    )


async def _out(session: AsyncSession, proposal: AiProposal) -> ContactChangeProposalOut:
    contact_id = (proposal.final or {}).get("contact_id") or proposal.proposed.get("contact_id")
    reply_id = proposal.proposed.get("reply_message_id")
    reply_status = None
    if reply_id:
        draft = await session.get(Message, uuid.UUID(reply_id))
        reply_status = draft.status if draft else None
    return ContactChangeProposalOut(
        id=proposal.id,
        ticket_id=proposal.context_id or uuid.UUID(int=0),
        entity_type=proposal.entity_type,
        decision=proposal.decision,
        proposed=proposal.proposed,
        final=proposal.final,
        decided_by=proposal.decided_by,
        decided_at=proposal.decided_at,
        created_at=proposal.created_at,
        contact=await _snapshot(session, contact_id),
        reply_message_id=uuid.UUID(reply_id) if reply_id else None,
        reply_message_status=reply_status,
    )


async def _ticket(session: AsyncSession, ticket_id: uuid.UUID) -> Ticket:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return ticket


async def _pending(
    session: AsyncSession, ticket_id: uuid.UUID, proposal_id: uuid.UUID
) -> AiProposal:
    proposal = await session.get(AiProposal, proposal_id)
    if proposal is None or proposal.context_id != ticket_id or proposal.entity_type != ENTITY_TYPE:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if proposal.decision is not Decision.PENDING:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Über den Vorschlag wurde bereits entschieden."
        )
    return proposal


def _features(message: Message | None, proposal: AiProposal) -> dict[str, Any]:
    return {
        "subject": mask_identifiers(message.subject if message else "")[:200],
        "text": mask_identifiers((message.body if message else "") or "")[:1500],
        "deterministic": proposal.proposed.get("source", {}).get("deterministic"),
    }


async def _decide(
    session: AsyncSession,
    principal: TenantPrincipal,
    ticket: Ticket,
    proposal: AiProposal,
    decision: Decision,
    final: dict[str, Any] | None,
    event_kind: str,
) -> None:
    proposal.decision, proposal.decided_by = decision, principal.user_id
    proposal.decided_at = datetime.now(UTC)
    proposal.final = final
    message_id = proposal.proposed.get("message_id")
    message = await session.get(Message, uuid.UUID(message_id)) if message_id else None
    # Lernen je Mandant (9.1): jede Entscheidung wird als bestätigtes Beispiel gespeichert.
    session.add(
        AiExample(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            task=AiTask.CONTACT_MASTER_DATA_CHANGE,
            features=_features(message, proposal),
            result={
                "decision": decision.value,
                "is_master_data_change": decision is not Decision.REJECTED,
                "changes": (final or {}).get("changes", []),
                "bank_change_mentioned": bool(proposal.proposed.get("bank_change_mentioned")),
            },
            proposal_id=proposal.id,
        )
    )
    session.add(
        TicketEvent(
            tenant_id=principal.tenant_id,
            ticket_id=ticket.id,
            kind=event_kind,
            data={"proposal_id": str(proposal.id), "title": proposal.proposed.get("title")},
            user_id=principal.user_id,
        )
    )
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=f"ai_proposal.{decision.value}",
        entity_type="ai_proposal",
        entity_id=proposal.id,
        actor_user_id=principal.user_id,
        payload={"entity_type": ENTITY_TYPE, "ticket_id": str(ticket.id)},
    )
    await session.flush()


def _require_contact_update(principal: TenantPrincipal) -> None:
    if not principal.has("contacts:update"):
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="Missing permission contacts:update."
        )


@router.get("/tickets/{ticket_id}/proposals", summary="Vorschläge zum Ticket (Stammdatenänderung)")
async def list_proposals(
    ticket_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[ContactChangeProposalOut]:
    async with tenant_tx(request, principal) as session:
        await _ticket(session, ticket_id)
        rows = await session.scalars(
            select(AiProposal)
            .where(AiProposal.context_id == ticket_id, AiProposal.entity_type == ENTITY_TYPE)
            .order_by(AiProposal.created_at.desc())
        )
        return [await _out(session, row) for row in rows]


@router.post(
    "/tickets/{ticket_id}/proposals/contact-change",
    status_code=201,
    summary="Stammdatenänderung aus der Ticket-Mail vorschlagen (jetzt berechnen)",
)
async def compute_proposal(
    ticket_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> ContactChangeProposalOut | None:
    async with tenant_tx(request, principal) as session:
        ticket = await _ticket(session, ticket_id)
        message = await session.scalar(
            select(Message)
            .where(Message.ticket_id == ticket_id, Message.direction == "in")
            .order_by(Message.received_at.desc().nulls_last(), Message.created_at.desc())
            .limit(1)
        )
        if message is None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Das Ticket hat keine eingehende E-Mail."
            )
        proposal = await propose_contact_change(
            session, request.app.state.settings, ticket, message, principal.user_id
        )
        return await _out(session, proposal) if proposal is not None else None


@router.post("/tickets/{ticket_id}/proposals/{proposal_id}/accept", summary="Vorschlag akzeptieren")
async def accept_proposal(
    ticket_id: uuid.UUID,
    proposal_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> ContactChangeProposalOut:
    _require_contact_update(principal)
    async with tenant_tx(request, principal) as session:
        ticket = await _ticket(session, ticket_id)
        proposal = await _pending(session, ticket_id, proposal_id)
        contact_id = proposal.proposed.get("contact_id")
        if not contact_id:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Kein Kontakt zugeordnet. Bitte über Korrigieren einen Kontakt wählen.",
            )
        changes = _validate_changes(list(proposal.proposed.get("changes", [])))
        applied = await apply_changes(
            session, principal, uuid.UUID(contact_id), changes, proposal.id
        )
        await _decide(
            session,
            principal,
            ticket,
            proposal,
            Decision.ACCEPTED,
            {"contact_id": contact_id, "changes": changes, "applied": sorted(applied)},
            "proposal_accepted",
        )
        return await _out(session, proposal)


@router.post(
    "/tickets/{ticket_id}/proposals/{proposal_id}/correct",
    summary="Vorschlag korrigieren und übernehmen",
)
async def correct_proposal(
    ticket_id: uuid.UUID,
    proposal_id: uuid.UUID,
    body: CorrectIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> ContactChangeProposalOut:
    _require_contact_update(principal)
    async with tenant_tx(request, principal) as session:
        ticket = await _ticket(session, ticket_id)
        proposal = await _pending(session, ticket_id, proposal_id)
        contact_id = body.contact_id or (
            uuid.UUID(proposal.proposed["contact_id"])
            if proposal.proposed.get("contact_id")
            else None
        )
        if contact_id is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Kontakt fehlt.")
        changes = _validate_changes([c.model_dump() for c in body.changes])
        applied = await apply_changes(session, principal, contact_id, changes, proposal.id)
        proposal.proposed = {
            **proposal.proposed,
            "reply_draft": _reply_after(
                await session.get(Contact, contact_id), proposal.proposed, changes
            ),
        }
        await _decide(
            session,
            principal,
            ticket,
            proposal,
            Decision.MODIFIED,
            {"contact_id": str(contact_id), "changes": changes, "applied": sorted(applied)},
            "proposal_corrected",
        )
        return await _out(session, proposal)


def _reply_after(
    contact: Contact | None, proposed: dict[str, Any], changes: list[dict[str, Any]]
) -> dict[str, str]:
    """Reply draft recomputed from the contact as it is after the change was written; the
    sentences follow the corrected fields, the greeting the stored contact."""
    subject = str(proposed.get("reply_draft", {}).get("subject", "AW: ")).removeprefix("AW: ")
    name_changes = [c for c in changes if c["field"] not in _NAME_FIELDS]
    return _reply_for(
        contact,
        name_changes,
        subject,
        proposed.get("mail_salutation"),
        proposed.get("address_valid_from"),
    )


@router.post("/tickets/{ticket_id}/proposals/{proposal_id}/reject", summary="Vorschlag ablehnen")
async def reject_proposal(
    ticket_id: uuid.UUID,
    proposal_id: uuid.UUID,
    request: Request,
    body: RejectIn | None = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> ContactChangeProposalOut:
    async with tenant_tx(request, principal) as session:
        ticket = await _ticket(session, ticket_id)
        proposal = await _pending(session, ticket_id, proposal_id)
        await _decide(
            session,
            principal,
            ticket,
            proposal,
            Decision.REJECTED,
            {"reason": body.reason if body else None, "changes": []},
            "proposal_rejected",
        )
        return await _out(session, proposal)


@router.post(
    "/tickets/{ticket_id}/proposals/{proposal_id}/reply-draft",
    status_code=201,
    summary="Antwortentwurf zum Vorschlag am Ticket anlegen (kein Versand)",
)
async def create_reply_draft(
    ticket_id: uuid.UUID,
    proposal_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    """Creates the prepared reply as an outbound draft on the ticket's mail thread. Sending
    stays with the existing path (submit, approve by someone else) in ``/mail/messages``."""
    if not principal.has("communication:update"):
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="Missing permission communication:update."
        )
    async with tenant_tx(request, principal) as session:
        ticket = await _ticket(session, ticket_id)
        proposal = await session.get(AiProposal, proposal_id)
        if (
            proposal is None
            or proposal.context_id != ticket_id
            or proposal.entity_type != ENTITY_TYPE
        ):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if proposal.decision not in (Decision.ACCEPTED, Decision.MODIFIED):
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Der Antwortentwurf setzt einen übernommenen Vorschlag voraus.",
            )
        existing_id = proposal.proposed.get("reply_message_id")
        if existing_id:
            existing = await session.get(Message, uuid.UUID(existing_id))
            if existing is not None:
                return {
                    "id": existing.id,
                    "status": existing.status,
                    "subject": existing.subject,
                    "body": existing.body,
                }
        message_id = proposal.proposed.get("message_id")
        inbound = await session.get(Message, uuid.UUID(message_id)) if message_id else None
        if inbound is None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Die eingehende E-Mail wurde nicht gefunden."
            )
        draft_text = proposal.proposed.get("reply_draft") or {}
        draft = Message(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            direction="out",
            status="draft",
            mailbox_id=inbound.mailbox_id,
            to_addresses=[inbound.from_address] if inbound.from_address else [],
            subject=str(draft_text.get("subject") or f"AW: {inbound.subject or ''}")[:998],
            body=str(draft_text.get("body") or ""),
            in_reply_to=inbound.header_message_id,
            thread_id=inbound.thread_id or inbound.id,
            contact_id=(
                uuid.UUID(proposal.final["contact_id"])
                if proposal.final and proposal.final.get("contact_id")
                else inbound.contact_id
            ),
            property_id=inbound.property_id,
            ticket_id=ticket.id,
        )
        session.add(draft)
        await session.flush()
        proposal.proposed = {**proposal.proposed, "reply_message_id": str(draft.id)}
        session.add(
            TicketEvent(
                tenant_id=principal.tenant_id,
                ticket_id=ticket.id,
                kind="proposal_reply_draft",
                data={"proposal_id": str(proposal.id), "message_id": str(draft.id)},
                user_id=principal.user_id,
            )
        )
        await session.flush()
        return {
            "id": draft.id,
            "status": draft.status,
            "subject": draft.subject,
            "body": draft.body,
        }


# Worker entry point -------------------------------------------------------------------------


async def propose_once(
    settings: Settings, tenant_id: uuid.UUID, ticket_id: uuid.UUID, message_id: uuid.UUID
) -> str:
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from mhvp.core.db.engine import create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            ticket = await session.get(Ticket, ticket_id)
            message = await session.get(Message, message_id)
            if ticket is None or message is None:
                return "not_found"
            proposal = await propose_contact_change(session, settings, ticket, message, None)
            return "created" if proposal is not None else "none"
    finally:
        await engine.dispose()
