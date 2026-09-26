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
    return value.replace("\x00", "")[:limit]


def parse(raw: bytes) -> dict[str, Any]:
    msg = email.message_from_bytes(raw, policy=policy.default)
    if not isinstance(msg, EmailMessage):  # pragma: no cover - policy.default yields EmailMessage
        raise ValueError("Keine E-Mail")
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body is not None else ""
    if body is not None and body.get_content_type() == "text/html":
        text = re.sub(r"<[^>]+>", " ", text)
    html_part = msg.get_body(preferencelist=("html",))
    html = html_part.get_content() if html_part is not None else None
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
                "filename": part.get_filename() or "anhang",
                "mime": part.get_content_type(),
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
    references = " ".join(str(msg["References"] or "").split())
    return {
        "from": clean(sender, 320) or None,
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
    }


def is_inline_part(part: Any) -> bool:
    """Inline part referenced from the HTML body (``Content-Disposition: inline`` with a
    ``Content-ID``), typically a signature image; never a document of its own."""
    return part.get_content_disposition() == "inline" and bool(part["Content-ID"])


def reference_ids(header: str | None) -> list[str]:
    """Message ids of a ``References`` (or ``In-Reply-To``) header, last (closest) first."""
    return [i for i in reversed((header or "").split()) if i]


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
