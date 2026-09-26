"""Deterministic rules for mail auto assignment, topic classification and invoice forwarding
(operator 25.09.2026, docs/integrations/mail-optimierung.md). Synthetic names only."""

import uuid
from typing import Any

from mhvp.communication.assignment import ActiveMember, match_by_name
from mhvp.communication.forwarding import classify_invoice, register_confirmation
from mhvp.tickets.competences import classify_topic, full_catalogue, is_known_code, label_for


def _member(name: str, competences: list[str] | None = None) -> ActiveMember:
    return ActiveMember(user_id=uuid.uuid4(), display_name=name, competences=competences or [])


def test_match_by_name_salutation_with_frau_tolerance() -> None:
    members = [_member("Ina Brink"), _member("Sven Kolter")]
    text = "Sehr geehrte Frau Brink,\n\nbitte prüfen Sie den Vorgang.\n\nViele Grüße"
    match = match_by_name(text, members)
    assert match is not None
    assert match.display_name == "Ina Brink"


def test_match_by_name_signature_block() -> None:
    members = [_member("Ina Brink"), _member("Sven Kolter")]
    text = "Hallo,\n\nbitte kümmern Sie sich darum.\n\nViele Grüße\nSven Kolter\nHausverwaltung"
    match = match_by_name(text, members)
    assert match is not None
    assert match.display_name == "Sven Kolter"


def test_match_by_name_no_hit_returns_none() -> None:
    members = [_member("Ina Brink")]
    assert match_by_name("Hallo, ohne Namen im Text.", members) is None


def test_match_by_name_requires_word_boundary_not_substring() -> None:
    # "Brinker" darf nicht fälschlich auf Mitglied "Brink" matchen.
    members = [_member("Ina Brink")]
    text = "Sehr geehrter Herr Brinkerhoff,\n\nGruß"
    assert match_by_name(text, members) is None


def test_classify_topic_keyword_hit() -> None:
    assert classify_topic("Bitte die Nebenkostenabrechnung prüfen") == "abrechnung"
    assert classify_topic("Die Heizung ist ausgefallen, Verbrauch unklar") == "heizkosten"


def test_classify_topic_no_hit_returns_none() -> None:
    assert classify_topic("Ein völlig neutraler Text ohne Schlagwort.") is None


def test_classify_topic_tenant_extra_catalogue() -> None:
    extra = [{"code": "custom_topic", "label": "Eigenes Thema", "keywords": ["sonderwunsch"]}]
    assert classify_topic("Ein Sonderwunsch des Eigentümers.", extra) == "custom_topic"
    assert is_known_code("custom_topic", extra)
    assert label_for("custom_topic", extra) == "Eigenes Thema"
    assert not is_known_code("custom_topic")  # ohne Erweiterung unbekannt


def test_full_catalogue_ignores_duplicate_extra_code() -> None:
    extra = [{"code": "bank", "label": "Anderes Label"}]
    codes = [c["code"] for c in full_catalogue(extra)]
    assert codes.count("bank") == 1


def test_classify_invoice_forwards_only_with_allowlist_and_no_object_reference() -> None:
    result = classify_invoice(
        sender="rechnung@telekom.de",
        subject="Ihre Rechnung",
        body="Zahlungsziel in 14 Tagen.",
        attachment_names=[],
        sender_allowlist=["rechnung@telekom.de"],
    )
    assert result.decision == "forward"


def test_classify_invoice_suggests_when_sender_not_on_allowlist() -> None:
    result = classify_invoice(
        sender="unknown@example.com",
        subject="Rechnung Nr. 123",
        body="Bitte begleichen.",
        attachment_names=[],
        sender_allowlist=["rechnung@telekom.de"],
    )
    assert result.decision == "suggest"


def test_classify_invoice_never_forwards_with_object_number() -> None:
    result = classify_invoice(
        sender="rechnung@telekom.de",
        subject="Rechnung Objekt 042",
        body="Objektbezogene Rechnung.",
        attachment_names=[],
        sender_allowlist=["rechnung@telekom.de"],
    )
    assert result.decision == "suggest"


def test_classify_invoice_none_without_invoice_keyword() -> None:
    result = classify_invoice(
        sender="rechnung@telekom.de",
        subject="Frage zum Vertrag",
        body="Kein Rechnungsbezug.",
        attachment_names=[],
        sender_allowlist=["rechnung@telekom.de"],
    )
    assert result.decision == "none"


def test_register_confirmation_adds_to_learning_list_after_second_confirmation() -> None:
    cfg: dict[str, Any] = {"sender_allowlist": [], "learning_list": [], "confirmed_counts": {}}
    cfg = register_confirmation(cfg, "poetter@example.com")
    assert "poetter@example.com" not in cfg["learning_list"]
    cfg = register_confirmation(cfg, "poetter@example.com")
    assert "poetter@example.com" in cfg["learning_list"]
    assert "poetter@example.com" in cfg["sender_allowlist"]
