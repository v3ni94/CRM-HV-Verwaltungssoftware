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


def parse(raw: bytes) -> dict[str, Any]:
    msg = email.message_from_bytes(raw, policy=policy.default)
    if not isinstance(msg, EmailMessage):  # pragma: no cover - policy.default yields EmailMessage
        raise ValueError("Keine E-Mail")
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body is not None else ""
    if body is not None and body.get_content_type() == "text/html":
        text = re.sub(r"<[^>]+>", " ", text)
    attachments = [
        {
            "filename": part.get_filename() or "anhang",
            "mime": part.get_content_type(),
            "data": part.get_payload(decode=True) or b"",
        }
        for part in msg.iter_attachments()
    ]
    received = None
    if msg["Date"]:
        try:
            received = parsedate_to_datetime(str(msg["Date"]))
        except (TypeError, ValueError):
            received = None
    return {
        "from": (getaddresses([str(msg["From"] or "")]) or [("", "")])[0][1].lower() or None,
        "to": [
            a.lower() for _, a in getaddresses([str(msg["To"] or ""), str(msg["Cc"] or "")]) if a
        ],
        "subject": str(msg["Subject"] or "")[:998] or None,
        "body": text.strip()[:100000],
        "message_id": str(msg["Message-ID"] or "").strip() or None,
        "in_reply_to": str(msg["In-Reply-To"] or "").strip() or None,
        "received_at": received,
        "attachments": attachments,
    }


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
