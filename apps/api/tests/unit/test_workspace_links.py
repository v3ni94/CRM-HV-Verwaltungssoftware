"""Deep links of notifications (operator 26.09.2026): one route per target type for the CRM
and for the portal, no link for unknown targets."""

import uuid
from datetime import date

import pytest

from mhvp.workspace.links import target_href

ID = uuid.UUID("01920000-0000-7000-8000-000000000001")


@pytest.mark.parametrize(
    ("target_type", "expected"),
    [
        ("ticket", f"/tickets/{ID}"),
        ("work_order", f"/auftraege/{ID}"),
        ("document", f"/dokumente/{ID}"),
        ("contract", f"/vertraege/{ID}"),
        ("property", f"/objekte/{ID}"),
        ("message", f"/mail?message={ID}"),
        ("approval", f"/mail?message={ID}"),
        ("appointment", f"/kalender?termin={ID}"),
        ("calendar_entry", f"/kalender?termin={ID}"),
        ("compliance_deadline", "/fristen"),
        ("digest_run", "/start"),
        ("bank_connection", "/bank"),
        ("proposal", "/assistent"),
        ("maintenance_item", "/objekte"),
        ("unknown_thing", None),
    ],
)
def test_crm_routes(target_type: str, expected: str | None) -> None:
    assert target_href(target_type, ID) == expected


def test_crm_hints() -> None:
    assert target_href("appointment", ID, appointment_date=date(2026, 10, 5)) == (
        f"/kalender?termin={ID}&datum=2026-10-05"
    )
    prop = uuid.uuid4()
    assert target_href("maintenance_item", ID, property_id=prop) == f"/objekte/{prop}#wartung"


def test_missing_target() -> None:
    assert target_href(None, None) is None
    assert target_href("", ID) is None
    assert target_href("ticket", None) is None
    assert target_href("message", None) == "/mail"
    assert target_href("appointment", None) == "/kalender"


@pytest.mark.parametrize(
    ("target_type", "expected"),
    [
        ("ticket", f"/meldungen/{ID}"),
        ("work_order", f"/auftraege/{ID}"),
        ("handover", f"/uebergabe/{ID}"),
        ("document", "/dokumente"),
        ("message", None),
        ("appointment", None),
        ("compliance_deadline", None),
    ],
)
def test_portal_routes(target_type: str, expected: str | None) -> None:
    """Portal recipients never receive CRM routes."""
    assert target_href(target_type, ID, portal=True) == expected


def test_resolution_contested_notification_kind_and_target() -> None:
    """AN19-CRM: the kind is switchable in the preferences, the target leads to the WEG list."""
    from mhvp.workspace.notification_prefs import CATALOGUE, MANDATORY_KINDS

    assert "hoa.resolution_contested" in CATALOGUE
    assert "hoa.resolution_contested" not in MANDATORY_KINDS
    assert target_href("resolution", ID) == "/weg"
    assert target_href("resolution", ID, portal=True) is None
