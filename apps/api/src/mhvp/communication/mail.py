"""E-mail parsing and deterministic classification (M20). The AI tasks classify_email and
draft_reply need a released provider with DPA (M12-01); until then rules only. Text in mails
is data, never an instruction (PÜ04)."""

import email
import re
from datetime import date, datetime, time
from email import policy
from email.message import EmailMessage
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

from mhvp.communication.html import html_to_text, looks_like_markup
from mhvp.core.text import strip_nul

URGENT_WORDS = (
    "dringend",
    "notfall",
    "sofort",
    "wasserschaden",
    "rohrbruch",
    "heizungsausfall",
    "gasgeruch",
    "brand",
)
DATE_RE = re.compile(
    r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b(?:[^\d\n]{0,12}(\d{1,2})[:.](\d{2})\s*Uhr)?"
)
PROPERTY_RE = re.compile(r"\bObjekt\s*(?:Nr\.?\s*)?(\d{3})\b", re.IGNORECASE)


def _clean(value: str, limit: int) -> str:
    return (strip_nul(value) or "")[:limit]


def parse(raw: bytes) -> dict[str, Any]:
    msg = email.message_from_bytes(raw, policy=policy.default)
    if not isinstance(msg, EmailMessage):  # pragma: no cover - policy.default yields EmailMessage
        raise ValueError("Keine E-Mail")
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body is not None else ""
    html_part = msg.get_body(preferencelist=("html",))
    html = html_part.get_content() if html_part is not None else None
    # Text preferably from text/plain; from HTML only via html_to_text, which drops style,
    # script, head and comments (operator report 30.09.2026). A text/plain part that itself
    # carries CSS (some newsletter generators) is replaced by the text of the HTML part.
    if body is not None and body.get_content_type() == "text/html":
        text = html_to_text(text)
    elif html and looks_like_markup(text):
        text = html_to_text(html) or text
    attachments = []
    inline_skipped = 0
    for part in msg.iter_attachments():
        if is_inline_part(part):
            # Signaturgrafiken und eingebettete Bilder (Review 26.09.2026, M8) bleiben im
            # Roh-.eml und werden nicht als eigenständige Dokumente abgelegt.
            inline_skipped += 1
            continue
        attachments.append(
            {
                # Anhangname und MIME-Typ kommen aus der Kopfzeile des Mailteils und können
                # ebenso ein NUL-Byte tragen wie Betreff oder Absender (Betreibermeldung
                # 27.09.2026); beide landen unverändert in Dokument und Klassifikation.
                "filename": _clean(part.get_filename() or "anhang", 255),
                "mime": _clean(part.get_content_type(), 255),
                "data": part.get_payload(decode=True) or b"",
            }
        )
    received = None
    if msg["Date"]:
        try:
            received = parsedate_to_datetime(str(msg["Date"]))
        except (TypeError, ValueError):
            received = None
    # PostgreSQL rejects NUL bytes in text columns; column limits mirror the model.
    clean = _clean
    sender = (getaddresses([str(msg["From"] or "")]) or [("", "")])[0][1].lower()
    reply_to_addrs = getaddresses([str(msg["Reply-To"] or "")])
    reply_to_raw = reply_to_addrs[0][1] if reply_to_addrs else ""
    reply_to = clean(reply_to_raw.lower(), 320) or None
    references = " ".join(str(msg["References"] or "").split())
    return {
        "from": clean(sender, 320) or None,
        "reply_to": reply_to,
        "to": [
            clean(a.lower(), 320)
            for _, a in getaddresses([str(msg["To"] or ""), str(msg["Cc"] or "")])
            if a
        ],
        "cc": [clean(a.lower(), 320) for _, a in getaddresses([str(msg["Cc"] or "")]) if a],
        "subject": clean(str(msg["Subject"] or ""), 998) or None,
        "body": clean(text.strip(), 100000),
        "body_html": clean(html, 400000) if html else None,
        "message_id": clean(str(msg["Message-ID"] or "").strip(), 998) or None,
        "in_reply_to": clean(str(msg["In-Reply-To"] or "").strip(), 998) or None,
        "references": clean(references, 20000) or None,
        "received_at": received,
        "attachments": attachments,
        "inline_skipped": inline_skipped,
        "auto_submitted": is_auto_submitted(msg),
    }


def is_auto_submitted(msg: Any) -> bool:
    """Automatic reply such as an out of office notice, detected only from the headers the
    sending system sets (Regel M19-10): ``Auto-Submitted`` other than ``no`` (RFC 3834),
    ``X-Autoreply`` or ``X-Autorespond`` present, or ``Precedence: auto_reply``. No guess from
    the subject or the text; an undetected automatic reply is handled like any other mail."""
    auto = str(msg["Auto-Submitted"] or "").split(";", 1)[0].strip().lower()
    if auto and auto != "no":
        return True
    if msg["X-Autoreply"] is not None or msg["X-Autorespond"] is not None:
        return True
    return str(msg["Precedence"] or "").strip().lower() == "auto_reply"


def is_inline_part(part: Any) -> bool:
    """Inline part referenced from the HTML body (``Content-Disposition: inline`` with a
    ``Content-ID``), typically a signature image; never a document of its own."""
    return part.get_content_disposition() == "inline" and bool(part["Content-ID"])


def reference_ids(header: str | None) -> list[str]:
    """Message ids of a ``References`` (or ``In-Reply-To``) header, last (closest) first."""
    return [i for i in reversed((header or "").split()) if i]


def build_reply_all(
    *,
    from_address: str | None,
    reply_to: str | None,
    to_addresses: list[str] | None,
    cc_addresses: list[str] | None,
    own_addresses: set[str],
) -> tuple[list[str], list[str]]:
    """Empfänger für "Antworten an alle" (operator 27.09.2026): ``To`` ist die
    ``Reply-To``-Adresse der Ursprungsmail, sonst der Absender. ``Cc`` sind alle
    ursprünglichen To- und Cc-Empfänger ohne die eigenen Postfachadressen des Mandanten
    (``own_addresses``, alle Adressen, Groß-/Kleinschreibung ignoriert) und ohne Duplikate von
    ``To`` oder untereinander. Reihenfolge bleibt stabil, die erste Nennung einer Adresse
    gewinnt.

    ``To`` ist nie eine eigene Postfachadresse (Review 1.40.2): ist ``Reply-To`` eine eigene
    Adresse, gilt der Absender, ist auch dieser eigen (Mail zwischen eigenen Postfächern oder
    eigene gesendete Mail), der erste fremde ursprüngliche To-Empfänger; ohne fremde Adresse
    bleibt ``To`` leer. Weicht ``Reply-To`` vom Absender ab, wird der Absender nicht zusätzlich
    in ``Cc`` gesetzt: nach RFC 5322 Abschnitt 3.6.2 nennt ``Reply-To`` die Adresse, an die der
    Verfasser Antworten erbittet (wie beim Antworten an alle üblicher Mailprogramme); steht der
    Absender selbst in To oder Cc der Ursprungsmail, bleibt er in ``Cc``."""
    # Hotfix 27.09.2026: stored arrays may hold NULL or blank entries (rows from older imports
    # or maintenance); they are skipped instead of raising on ``.lower()``.
    own_lower = {a.strip().lower() for a in own_addresses if a}
    to = (reply_to or "").strip() or (from_address or "").strip() or None
    if to and to.lower() in own_lower:
        candidates = [from_address, *(to_addresses or [])]
        to = next(
            (
                a
                for a in ((c or "").strip() for c in candidates)
                if a and a.lower() not in own_lower
            ),
            None,
        )
    to_list = [to] if to else []
    to_lower = {to.lower()} if to else set()
    seen = set(to_lower)
    cc: list[str] = []
    for raw in [*(to_addresses or []), *(cc_addresses or [])]:
        addr = (raw or "").strip()
        low = addr.lower()
        if not addr or low in own_lower or low in seen:
            continue
        seen.add(low)
        cc.append(addr)
    return to_list, cc


_QUOTE_RE = re.compile(
    r"^(>|Am .{3,120} schrieb .{0,200}:\s*$|On .{3,120} wrote:\s*$"
    r"|-{2,}\s*Urspr.ngliche Nachricht\s*-{2,}|-{2,}\s*Original Message\s*-{2,}"
    r"|_{5,}\s*$|Von: .{1,200}$|From: .{1,200}$)",
    re.IGNORECASE,
)
_SIGNATURE_RE = re.compile(
    r"^(-- |--\s*$|Mit freundlichen Gr..en|Viele Gr..e|Beste Gr..e|Freundliche Gr..e)"
)


def strip_quoted(body: str | None, limit: int = 4000) -> str | None:
    """First text block of a mail without quoted earlier mails and without the signature
    (Review 26.09.2026, M17): the ticket description shows what the sender wrote, the full
    text stays on the message. Returns ``None`` when nothing is left."""
    if not body:
        return None
    kept: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if _QUOTE_RE.match(stripped) or _SIGNATURE_RE.match(stripped):
            break
        kept.append(line.rstrip())
    text = "\n".join(kept).strip()
    if not text:
        text = body.strip()
    return text[:limit] or None


def urgency(subject: str | None, body: str | None) -> str:
    text = f"{subject or ''} {body or ''}".lower()
    return "urgent" if any(w in text for w in URGENT_WORDS) else "normal"


def property_number(subject: str | None, body: str | None) -> str | None:
    match = PROPERTY_RE.search(f"{subject or ''}\n{body or ''}")
    return match.group(1) if match else None


def appointments(body: str | None, today: date) -> list[dict[str, Any]]:
    """Dates (and times) mentioned in the text as suggestions; nothing is entered automatically."""
    out = []
    for m in DATE_RE.finditer(body or ""):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if d < today:
            continue
        at = None
        if m.group(4):
            try:
                at = datetime.combine(d, time(int(m.group(4)), int(m.group(5)))).isoformat()
            except ValueError:
                at = None
        out.append({"date": d.isoformat(), "time": at, "text": m.group(0)})
    return out[:5]


# Prozesskatalog (Regel M19-11): deterministische Schlüsselwörter je Vorgangsart. Reihenfolge
# ist die Prüfreihenfolge bei Gleichstand (spezifischere Vorgänge zuerst). Ein Treffer im
# Betreff zählt doppelt. Die Codes sind ``mhvp.tickets.flows.PROCESS_CODES``.
PROCESS_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "gericht",
        (
            "amtsgericht",
            "landgericht",
            "klage",
            "mahnbescheid",
            "aktenzeichen",
            "versäumnisurteil",
            "gerichtsvollzieher",
            "einstweilige verfügung",
            "az.:",
        ),
    ),
    (
        "versicherungsschaden",
        (
            "versicherungsschaden",
            "schadenmeldung",
            "schadensmeldung",
            "schadennummer",
            "schadensnummer",
            "versicherung",
            "leitungswasser",
            "sturmschaden",
            "elementarschaden",
            "gebäudeversicherung",
        ),
    ),
    (
        "objektabgabe",
        (
            "verwaltung beenden",
            "verwaltervertrag gekündigt",
            "kündigung der verwaltung",
            "kündigung des verwaltervertrags",
            "abgabe des objekts",
            "nachfolgeverwaltung",
            "neue verwaltung übernimmt",
            "verwalterwechsel zum",
        ),
    ),
    (
        "objektuebernahme",
        (
            "verwalterwechsel",
            "übernahme der verwaltung",
            "neues objekt",
            "vorverwaltung",
            "verwaltungsbeginn",
            "bestellung zum verwalter",
            "verwaltervertrag",
            "objektübernahme",
            "unterlagen der vorverwaltung",
        ),
    ),
    (
        "mieterhoehung",
        (
            "mieterhöhung",
            "mieterhoehung",
            "mietanpassung",
            "mietspiegel",
            "vergleichsmiete",
            "kappungsgrenze",
            "zustimmung zur erhöhung",
            "staffelmiete",
            "indexmiete",
        ),
    ),
    (
        "kaution",
        (
            "kaution",
            "mietsicherheit",
            "kautionsabrechnung",
            "kautionsrückzahlung",
            "kautionskonto",
            "bürgschaft",
        ),
    ),
    (
        "uebergabe",
        (
            "übergabe",
            "uebergabe",
            "übergabeprotokoll",
            "wohnungsübergabe",
            "schlüsselübergabe",
            "abnahme der wohnung",
            "rückgabe der wohnung",
            "zählerstände",
        ),
    ),
    (
        "kuendigung",
        (
            "kündigung",
            "kuendigung",
            "kündige",
            "kuendige",
            "mietverhältnis beenden",
            "aufhebungsvertrag",
            "auszug zum",
            "kündigungsfrist",
            "kündigen",
        ),
    ),
    (
        "vermietung",
        (
            "vermietung",
            "neuvermietung",
            "mietinteressent",
            "wohnungsbesichtigung",
            "besichtigungstermin",
            "selbstauskunft",
            "mietangebot",
            "wohnung frei",
            "bewerbung um die wohnung",
            "mietvertrag anlegen",
            "neuer mieter",
        ),
    ),
    (
        "beschwerde",
        (
            "beschwerde",
            "beschweren",
            "lärmbelästigung",
            "ruhestörung",
            "hausordnung",
            "nachbar",
            "belästigung",
            "verstoß gegen",
            "unzumutbar",
        ),
    ),
    (
        "reparaturanfrage",
        (
            "reparatur",
            "defekt",
            "kaputt",
            "tropft",
            "funktioniert nicht",
            "heizung",
            "handwerker",
            "mangel",
            "mängel",
            "wasserschaden",
            "rohrbruch",
            "aufzug",
            "schimmel",
            "undicht",
            "instandsetzung",
        ),
    ),
    (
        "buchhaltung",
        (
            "buchhaltung",
            "kontoauszug",
            "abrechnung",
            "nebenkosten",
            "betriebskosten",
            "hausgeld",
            "mahnung",
            "überweisung",
            "zahlung",
            "rechnung",
            "saldo",
            "lastschrift",
            "wirtschaftsplan",
            "guthaben",
            "nachzahlung",
        ),
    ),
)
PROCESS_MIN_SCORE = 1
PROCESS_STRONG_SCORE = 3


def process_category(subject: str | None, body: str | None) -> dict[str, Any]:
    """Vorschlag der Vorgangsart aus dem Prozesskatalog (Regel M19-11), rein deterministisch:
    ``{"process_code", "confidence", "reason"}``. Treffer im Betreff zählen doppelt; die
    Vorgangsart mit der höchsten Summe gewinnt, bei Gleichstand die zuerst gelistete.
    ``confidence`` ist 0,5 bei einem Treffer, 0,75 bei zwei, 0,9 ab drei; ohne Treffer
    ``process_code`` null. Der Grund nennt die gefundenen Wörter (nie den Mailtext)."""
    subject_text = (subject or "").lower()
    body_text = (body or "").lower()
    best_code: str | None = None
    best_score = 0
    best_hits: list[str] = []
    for code, words in PROCESS_KEYWORDS:
        score = 0
        hits: list[str] = []
        for word in words:
            in_subject = word in subject_text
            in_body = word in body_text
            if in_subject or in_body:
                hits.append(word)
                score += (2 if in_subject else 0) + (1 if in_body else 0)
        if score > best_score:
            best_code, best_score, best_hits = code, score, hits
    if best_code is None or best_score < PROCESS_MIN_SCORE:
        return {"process_code": None, "confidence": 0.0, "reason": "kein Schlüsselwort erkannt"}
    confidence = 0.9 if best_score >= PROCESS_STRONG_SCORE else (0.75 if best_score == 2 else 0.5)
    return {
        "process_code": best_code,
        "confidence": confidence,
        "reason": "Schlüsselwörter: " + ", ".join(best_hits[:5]),
    }


def category(subject: str | None, body: str | None, categories: list[str]) -> str | None:
    text = f"{subject or ''} {body or ''}".lower()
    hits = [c for c in categories if c.lower() in text]
    return sorted(hits, key=len, reverse=True)[0] if hits else None


def draft_reply(salutation: str, subject: str | None, ticket_number: int | None) -> str:
    ref = f" (Vorgang {ticket_number})" if ticket_number else ""
    return (
        f"{salutation},\n\nvielen Dank für Ihre Nachricht{ref}. "
        "Wir haben Ihr Anliegen erhalten und "
        "melden uns mit dem nächsten Schritt.\n\nMit freundlichen Grüßen\n[Name]\n[Firma]"
    )


# Invoice copy request (rule INT-LEXO-01, section 5.1): deterministic, literal number only.
_INV_KEYWORD = (
    r"(?:rechnung(?:en)?|rechnungs(?:nummer|nr\.?|-nr\.?)|re[-\s]?nr\.?|rg[-\s]?nr\.?|rg\b"
    r"|beleg(?:nummer|[-\s]?nr\.?)?)"
)
_INV_INTENT = (
    r"(?:nochmals?|erneut|noch\s+einmal|kopie|duplikat|zweitschrift|zusenden|zuschicken"
    r"|zukommen\s+lassen|(?:senden|schicken|übersenden)\s+sie\s+(?:mir|uns)|nicht\s+erhalten"
    r"|nicht\s+angekommen|verloren)"
)
_INV_NUMBER = r"(?:nr\.?|nummer|no\.?|#)?\s*:?\s*(?P<num>(?:[A-Z]{1,4}[-/]?)?\d{2,}(?:[-/.]\d+)*)"
INVOICE_NUMBER_RE = re.compile(_INV_KEYWORD + r"[^\S\r\n]{0,3}" + _INV_NUMBER, re.IGNORECASE)
INVOICE_INTENT_RE = re.compile(_INV_INTENT, re.IGNORECASE)
INVOICE_KEYWORD_RE = re.compile(_INV_KEYWORD, re.IGNORECASE)
INVOICE_NEGATIVE_RE = re.compile(
    r"(?:anbei|im\s+anhang|beigefügt|überwiesen|bezahlt|zahlung\s+erfolgt|mahnung\s+erhalten)",
    re.IGNORECASE,
)
INVOICE_STATEMENT_RE = re.compile(
    r"(?:betriebskosten|nebenkosten|hausgeld|heizkosten)abrechnung", re.IGNORECASE
)


def invoice_copy_request(subject: str | None, body: str | None) -> dict[str, Any] | None:
    """``{"intent": "invoice_copy_requested", "invoice_number": str | None}`` when the sender
    wants an already issued invoice again; a statement (Abrechnung) is no invoice here and a
    negative phrase within 60 characters before the keyword ("Rechnung anbei", "bezahlt")
    cancels the match. The number is taken verbatim from the text, never normalised."""
    text = (subject or "") + "\n" + (body or "")[:4000]
    keyword = INVOICE_KEYWORD_RE.search(text)
    if keyword is None or INVOICE_INTENT_RE.search(text) is None:
        return None
    if INVOICE_STATEMENT_RE.search(text) and not INVOICE_NUMBER_RE.search(text):
        return None
    for match in INVOICE_KEYWORD_RE.finditer(text):
        window = text[max(0, match.start() - 60) : match.end() + 60]
        if INVOICE_NEGATIVE_RE.search(window):
            return None
    number = INVOICE_NUMBER_RE.search(text)
    return {
        "intent": "invoice_copy_requested",
        "invoice_number": number.group("num") if number else None,
    }
