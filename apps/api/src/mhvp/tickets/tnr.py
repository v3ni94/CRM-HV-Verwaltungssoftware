"""Ticketnummer im Betreff (operator 26.09.2026, docs/rules/M19-02-tnr.md).

Jede ausgehende Antwort aus einem Ticket trägt im Betreff genau einmal die Kennung
``TNR#<nummer>`` (zum Beispiel ``AW: Wasserschaden Küche TNR#412``). Eingehende Mails mit
dieser Kennung werden dem Ticket des Mandanten zugeordnet, auch ohne Thread-Kopfzeilen. Die
Ticketnummer ist die mandantenweite fortlaufende Nummer aus ``mhvp.core.numbering`` (Sequenz
``ticket``), eindeutig je Mandant (``uq_ticket_tenant_number``).
"""

from __future__ import annotations

import re

TNR_RE = re.compile(r"TNR#(\d{1,12})\b")
_REPLY_PREFIX_RE = re.compile(r"^\s*(?:(?:AW|RE|WG|FW|FWD|SV|VS)\s*:\s*)+", re.IGNORECASE)


def format_tnr(number: int) -> str:
    return f"TNR#{number}"


def extract_tnr(subject: str | None) -> int | None:
    """Erste Ticketnummer im Betreff, sonst ``None``."""
    if not subject:
        return None
    match = TNR_RE.search(subject)
    return int(match.group(1)) if match else None


def subject_with_tnr(subject: str | None, number: int) -> str:
    """Betreff mit genau einer Kennung ``TNR#<nummer>``: fehlt sie, wird sie angehängt; steht
    sie bereits (auch mehrfach oder mit anderer Nummer aus einem Weiterleitungsfehler), bleibt
    eine Kennung mit der Nummer dieses Tickets erhalten, nie zwei."""
    tag = format_tnr(number)
    base = (subject or "").strip()
    stripped = TNR_RE.sub("", base)
    stripped = re.sub(r"[ \t]{2,}", " ", stripped).strip()
    text = f"{stripped} {tag}".strip() if stripped else tag
    return text[:998]


def reply_subject(subject: str | None, number: int) -> str:
    """``AW: <Betreff> TNR#<nummer>``; ein vorhandenes Antwortpräfix wird nicht verdoppelt."""
    base = (subject or "").strip()
    if not _REPLY_PREFIX_RE.match(base):
        base = f"AW: {base}".strip()
    return subject_with_tnr(base, number)
