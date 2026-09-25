"""Rechnungs-Weiterleitung an das Buchhaltungspostfach (operator 25.09.2026,
docs/integrations/mail-optimierung.md). Deterministische Regel, kein KI-Aufruf:

Automatisch weitergeleitet und archiviert wird nur eine Mail, deren Absender auf der
Positivliste steht (vom Betreiber gepflegt oder über die Lernliste zweimal bestätigt) UND die
das Schlagwort "Rechnung" in Betreff oder Anhangsname trägt UND KEIN Objektnummernmuster (drei
Ziffern) UND KEINE Adresse eines Objekts im Text enthält (sonst ist es eine Objektrechnung, die
nie automatisch weitergeleitet wird). Jede andere erkannte Rechnung wird nur vorgeschlagen
("Weiterleiten?"); nichts wird ohne diese Bedingungen automatisch verschickt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from mhvp.communication.mail import PROPERTY_RE

INVOICE_WORD_RE = re.compile(r"rechnung", re.IGNORECASE)

Decision = Literal["forward", "suggest", "none"]


@dataclass(frozen=True)
class InvoiceClassification:
    decision: Decision
    reason: str


def _looks_like_invoice(subject: str | None, attachment_names: list[str]) -> bool:
    haystack = f"{subject or ''} {' '.join(attachment_names)}"
    return bool(INVOICE_WORD_RE.search(haystack))


def _has_object_reference(
    subject: str | None, body: str | None, known_addresses: list[str]
) -> bool:
    text = f"{subject or ''}\n{body or ''}"
    if PROPERTY_RE.search(text):
        return True
    lowered = text.lower()
    return any(addr and addr.lower() in lowered for addr in known_addresses)


def classify_invoice(
    *,
    sender: str | None,
    subject: str | None,
    body: str | None,
    attachment_names: list[str],
    sender_allowlist: list[str],
    known_property_addresses: list[str] | None = None,
) -> InvoiceClassification:
    """Reine Funktion, leicht zu testen: liefert "forward" nur, wenn alle Bedingungen erfüllt
    sind; erkennt sie nur das Schlagwort ohne Positivlisten-Treffer, ist es ein Vorschlag."""
    if not _looks_like_invoice(subject, attachment_names):
        return InvoiceClassification("none", "Kein Rechnungshinweis erkannt.")
    has_object = _has_object_reference(subject, body, known_property_addresses or [])
    sender_norm = (sender or "").lower().strip()
    on_allowlist = any(sender_norm == a.lower().strip() for a in sender_allowlist if a)
    if has_object:
        return InvoiceClassification(
            "suggest", "Objektbezug erkannt, Rechnung wird nicht automatisch weitergeleitet."
        )
    if on_allowlist:
        return InvoiceClassification("forward", "Absender auf der Positivliste, kein Objektbezug.")
    return InvoiceClassification(
        "suggest", "Rechnungshinweis erkannt, Absender nicht auf der Positivliste."
    )


def register_confirmation(settings: dict[str, Any], sender: str) -> dict[str, Any]:
    """Erhöht den Bestätigungszähler eines Absenders; ab zwei Bestätigungen wandert er auf die
    Lernliste und damit dauerhaft in die Positivliste (operator 25.09.2026)."""
    sender_norm = (sender or "").lower().strip()
    enabled = bool(settings.get("enabled", True))
    forward_address = settings.get("forward_address")
    sender_allowlist: list[str] = list(settings.get("sender_allowlist", []))
    learning_list: list[str] = list(settings.get("learning_list", []))
    confirmed_counts: dict[str, int] = dict(settings.get("confirmed_counts", {}))
    if not sender_norm:
        return {
            "enabled": enabled,
            "forward_address": forward_address,
            "sender_allowlist": sender_allowlist,
            "learning_list": learning_list,
            "confirmed_counts": confirmed_counts,
        }
    count = int(confirmed_counts.get(sender_norm, 0)) + 1
    confirmed_counts[sender_norm] = count
    if count >= 2 and sender_norm not in {s.lower() for s in learning_list}:
        learning_list.append(sender_norm)
    if sender_norm not in {s.lower() for s in sender_allowlist} and count >= 2:
        sender_allowlist.append(sender_norm)
    return {
        "enabled": enabled,
        "forward_address": forward_address,
        "sender_allowlist": sender_allowlist,
        "learning_list": learning_list,
        "confirmed_counts": confirmed_counts,
    }
