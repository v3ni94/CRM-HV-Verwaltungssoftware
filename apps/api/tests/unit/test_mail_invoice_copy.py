"""Deterministic invoice copy detector (rule INT-LEXO-01, spec 5.1): positives with literal
numbers, negatives (attachment, paid, statement, number without intent)."""

from __future__ import annotations

import pytest

from mhvp.communication import mail


@pytest.mark.parametrize(
    ("subject", "body", "number"),
    [
        ("Rechnung", "bitte senden Sie mir die Rechnung RE-1019 nochmals zu", "RE-1019"),
        ("Kopie", "ich bitte um eine Kopie der Rechnungsnummer 2026-0042", "2026-0042"),
        ("Bitte", "Rechnung Nr. 4711 erneut zusenden", "4711"),
        ("Rechnung fehlt", "Ich habe die Rechnung 4711 nicht erhalten.", "4711"),
        ("Duplikat", "Können Sie mir ein Duplikat der Rechnung schicken?", None),
    ],
)
def test_positive(subject: str, body: str, number: str | None) -> None:
    assert mail.invoice_copy_request(subject, body) == {
        "intent": "invoice_copy_requested",
        "invoice_number": number,
    }


@pytest.mark.parametrize(
    ("subject", "body"),
    [
        ("Rechnung", "Rechnung anbei, bitte um Bearbeitung nochmals prüfen"),
        ("Rechnung", "Rechnung 4711 ist bezahlt, bitte nochmals prüfen"),
        ("Abrechnung", "Bitte senden Sie mir die Betriebskostenabrechnung nochmals"),
        ("Rechnung 4711", "Hier die Rechnung 4711 zur Kenntnis."),
        ("Termin", "Bitte schicken Sie mir den Terminvorschlag nochmals"),
    ],
)
def test_negative(subject: str, body: str) -> None:
    assert mail.invoice_copy_request(subject, body) is None


def test_number_is_literal_and_first() -> None:
    result = mail.invoice_copy_request("Rechnungen", "Rechnung RE-1019 und RE-1020 nochmals senden")
    assert result is not None
    assert result["invoice_number"] == "RE-1019"
    assert "RE-1019" in "Rechnung RE-1019 und RE-1020 nochmals senden"
