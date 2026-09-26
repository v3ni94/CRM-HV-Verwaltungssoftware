"""M30-01: invitation text for helper accesses (mail draft and letter)."""

from datetime import UTC, date, datetime

from mhvp.documents import letters
from mhvp.handover.routers import HelperAccessIn, invitation_text, router

TOKEN = "0123abcd.secret-code"


def test_invitation_text_contains_url_code_validity_and_second_factor() -> None:
    subject, body = invitation_text(
        number="UP-20260926-001",
        name="Erika Muster",
        token=TOKEN,
        expires_at=datetime(2026, 10, 10, 8, 0, tzinfo=UTC),
        portal_url="https://portal.example.test",
    )
    assert subject == "Zugang zum Übergabeprotokoll UP-20260926-001"
    assert "Guten Tag Erika Muster," in body
    assert "https://portal.example.test" in body
    assert body.count(TOKEN) == 1
    assert "bis zum 10.10.2026 gültig" in body
    assert "zweiten Faktor" in body
    assert " \u2013 " not in body
    assert " - " not in body


def test_invitation_text_without_portal_url_and_expiry() -> None:
    _subject, body = invitation_text(
        number="UP-1", name=None, token=TOKEN, expires_at=None, portal_url=None
    )
    assert body.startswith("Guten Tag,")
    assert "Kundenportal der Verwaltung" in body
    assert "nur einmal verwendet" in body


def test_mail_draft_is_default_option_on_create() -> None:
    body = HelperAccessIn(name="A B", email="a@example.test")
    assert body.invitation_as_mail_draft is True
    assert (
        HelperAccessIn(
            name="A B", email="a@example.test", invitation_as_mail_draft=False
        ).invitation_as_mail_draft
        is False
    )


def test_delivery_routes_are_post_only() -> None:
    base = "/handover/protocols/{protocol_id}/helper-access/{grant_id}/"
    methods: dict[str, set[str]] = {
        getattr(r, "path", ""): getattr(r, "methods", set())
        for r in router.routes
        if "invitation-" in getattr(r, "path", "")
    }
    assert methods == {
        base + "invitation-draft": {"POST"},
        base + "invitation-letter": {"POST"},
    }


def test_letter_renders_as_pdf() -> None:
    subject, body = invitation_text(
        number="UP-1", name="Erika <Muster>", token=TOKEN, expires_at=None, portal_url=None
    )
    head = letters.Letterhead(
        company={"name": "Test GmbH", "street": "Weg 1", "postal_code": "40000", "city": "Ort"},
        branding={},
    )
    pdf = letters.render_pdf(
        head,
        letters.Letter(
            recipient_lines=["Erika Muster"],
            subject=letters.render_text("{{ s }}", {"s": subject}),
            body=letters.render_text("{{ b }}", {"b": body}),
            letter_date=date(2026, 9, 26),
        ),
    )
    assert pdf.startswith(b"%PDF")
