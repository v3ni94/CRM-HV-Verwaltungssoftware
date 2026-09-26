"""Chat instruction reading for the table import (Betreiberauftrag 26.09.2026)."""

import pytest

from mhvp.ai import imports
from mhvp.ai import instructions as ins


@pytest.mark.parametrize(
    ("text", "role"),
    [
        ("Rolle bank hinterlegen", "bank"),
        ("bitte ROLLE bank hinterlegen", "bank"),
        ("Rolle: Eigentümer", "eigentuemer"),
        ("Rolle = eigentuemer", "eigentuemer"),
        ("alle als Mieter anlegen", "mieter"),
        ("Kontakte als Dienstleister importieren", "dienstleister"),
        ("Rolle Verwalter", "verwalter"),
        ("Rolle sonstige", "sonstiges"),
        ("Rolle „Bank“ setzen", "bank"),
        ("als Banken hinterlegen", "bank"),
    ],
)
def test_role_from_instruction(text: str, role: str) -> None:
    assert ins.role_from_instruction(text) == role


@pytest.mark.parametrize(
    "text", ["Kontakte anlegen", "", None, "als nächstes importieren", "Rolle unbekannt"]
)
def test_no_role_in_instruction(text: str | None) -> None:
    assert ins.role_from_instruction(text) is None


def test_tags_from_instruction() -> None:
    assert ins.tags_from_instruction("Rolle bank, Tag Bank hinterlegen") == ["Bank"]
    assert ins.tags_from_instruction("Kategorie: Hausbank.") == ["Hausbank"]
    assert ins.tags_from_instruction("Rolle bank hinterlegen") == []


def test_contact_role_maps_task_codes() -> None:
    assert ins.contact_role("owner") == "eigentuemer"
    assert ins.contact_role("tenant") == "mieter"
    assert ins.contact_role("bank") == "bank"
    assert ins.contact_role(None) is None


def test_contact_in_adds_default_role_without_removing_row_role() -> None:
    notes: list[str] = []
    item = {"kind": "company", "company_name": "Musterbank AG", "role": "owner"}
    contact = imports._contact_in(item, notes, default_role="bank", tags=["Bank"])
    assert contact is not None
    assert [r.value for r in contact.roles] == ["bank", "eigentuemer"]
    assert contact.tags == ["Bank"]
