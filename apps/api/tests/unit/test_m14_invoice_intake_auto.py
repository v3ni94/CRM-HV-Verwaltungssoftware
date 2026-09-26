from typing import cast

from sqlalchemy import Table

"""M14-05 automatischer Belegeingang: Heuristik und Idempotenz der Kandidatenauswahl."""

import uuid

import pytest

from mhvp.communication.invoice_intake import (
    PDF,
    Attachment,
    MailInfo,
    candidates,
    looks_like_invoice,
)
from mhvp.communication.models import InvoiceIntakeAutoRun
from mhvp.platform.models import TenantSettings


@pytest.mark.parametrize(
    ("subject", "sender", "filename"),
    [
        ("Ihre Rechnung Nr. 4711", "service@firma.de", "dokument.pdf"),
        ("INVOICE 2026-09", None, "scan.pdf"),
        ("Beleg zur Bestellung", "a@b.de", "x.pdf"),
        ("Hallo", "rechnung@stadtwerke.de", "x.pdf"),
        ("Hallo", "Telekom <Billing@telekom.de>", "x.pdf"),
        ("Unterlagen", "a@b.de", "Rechnung_09-2026.pdf"),
        ("Unterlagen", "a@b.de", "invoice-123.pdf"),
        ("Unterlagen", "a@b.de", "RE-2026-001.pdf"),
        ("Unterlagen", "a@b.de", "Scan_RE-4711.pdf"),
    ],
)
def test_heuristic_matches(subject: str, sender: str | None, filename: str) -> None:
    assert looks_like_invoice(subject, sender, filename)


@pytest.mark.parametrize(
    ("subject", "sender", "filename"),
    [
        ("Re: Termin Treppenhaus", "mieter@example.org", "foto.pdf"),
        ("Protokoll Versammlung", "verwalter@example.org", "Pre-Order.pdf"),
        (None, None, None),
        ("Angebot", "info@example.org", "re-scan.pdf"),
    ],
)
def test_heuristic_rejects(subject: str | None, sender: str | None, filename: str | None) -> None:
    assert not looks_like_invoice(subject, sender, filename)


def _mail(direction: str = "in", subject: str = "Rechnung") -> MailInfo:
    return MailInfo(uuid.uuid4(), subject, "a@b.de", direction)


def test_candidates_only_inbound_pdf_matching() -> None:
    inbound, outbound, other = _mail(), _mail("out"), _mail(subject="Hallo")
    pdf = Attachment(inbound.message_id, uuid.uuid4(), "scan.pdf", PDF)
    image = Attachment(inbound.message_id, uuid.uuid4(), "rechnung.jpg", "image/jpeg")
    out_pdf = Attachment(outbound.message_id, uuid.uuid4(), "rechnung.pdf", PDF)
    no_hint = Attachment(other.message_id, uuid.uuid4(), "foto.pdf", PDF)
    result = candidates([inbound, outbound, other], [pdf, image, out_pdf, no_hint], set())
    assert result == [pdf]


def test_candidates_idempotent_per_document() -> None:
    first, second = _mail(), _mail()
    doc = uuid.uuid4()
    a = Attachment(first.message_id, doc, "rechnung.pdf", PDF)
    b = Attachment(second.message_id, doc, "rechnung.pdf", PDF)
    # same document on two mails in one batch: one run only
    assert candidates([first, second], [a, b, a], set()) == [a]
    # a document already claimed by an earlier sync: no second run
    assert candidates([first, second], [a, b], {doc}) == []


def test_marker_unique_and_switch_default_off() -> None:
    table = cast(Table, InvoiceIntakeAutoRun.__table__)
    uniques = [
        tuple(c.name for c in con.columns)
        for con in table.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    ]
    assert ("tenant_id", "document_id") in uniques
    column = TenantSettings.__table__.c.invoice_intake_auto
    assert column.default is not None
    assert column.default.arg is False
    assert "false" in str(column.server_default.arg)
