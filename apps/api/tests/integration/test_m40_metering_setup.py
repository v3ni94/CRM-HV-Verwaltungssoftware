"""Messdienstleister, Ordnungsbegriffsabgleich as its own transmission kind
``billing_unit_setup`` (master prompt Messdienstleister section 6, Q8): preview with internal
and external identifiers side by side, deliberate submission through check, release and order,
asynchronous provider processing (``waiting_provider`` until the fetched result says
``COMPLETED``, never "vollständig zugeordnet" on acceptance alone) and the fetched result as
verification basis of the technical confirmation. Artificial data only: the ``fake`` adapter
records every write, nothing reaches a provider."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_m2_platform import World, bearer, client, login
from tests.integration.test_m40_metering import (
    _assign,
    _connection,
    _ok,
    _problem,
    _property,
    _unit,
    admin,
)
from tests.integration.test_m40_metering_write import _check, _fake, _setup, _step

pytestmark = pytest.mark.integration

__all__ = ["admin", "client"]

KIND = "billing_unit_setup"
RESULT_BOTH = {
    "billingunitMscnumber": "000123456",
    "matched": [
        {"residentialunitMscnumber": "0001", "residentialunitPmnumber": "01"},
        {"residentialunitMscnumber": "0002", "residentialunitPmnumber": "02"},
    ],
    "additional": [{"residentialunitMscnumber": "0009", "positiontext": "DG"}],
}


def _patch_config(
    client: TestClient, h: dict[str, str], conn: dict[str, Any], **config: Any
) -> dict[str, Any]:
    current = _ok(client.get(f"/api/v1/metering/connections/{conn['id']}", headers=h))
    return dict(
        _ok(
            client.patch(
                f"/api/v1/metering/connections/{conn['id']}",
                json={"version": current["version"], "config": {**current["config"], **config}},
                headers=h,
            )
        )
    )


def _setup_bu(
    client: TestClient, h: dict[str, str], number: str, ext: str, **config: Any
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Write connection of the roles tests plus the account release of billing unit data."""
    conn, assignment, units = _setup(client, h, number, ext, **config)
    conn = _ok(
        client.patch(
            f"/api/v1/metering/connections/{conn['id']}",
            json={"version": conn["version"], "account_release": {"billing_unit_data": True}},
            headers=h,
        )
    )
    return dict(conn), assignment, units


def _poll(client: TestClient, h: dict[str, str], row: dict[str, Any]) -> Any:
    return client.post(f"/api/v1/metering/transmissions/{row['id']}/poll", headers=h)


def test_setup_lifecycle_is_asynchronous_and_result_confirms_assignment(
    client: TestClient, admin: dict[str, str]
) -> None:
    fake = _fake()
    conn, assignment, units = _setup_bu(client, admin, "931", "000123456")
    assert assignment["remote_confirmed"] is False
    checked = _check(client, admin, {"assignment_id": assignment["id"], "kind": KIND})
    assert checked["status"] == "checked", checked["validation"]
    # preview: internal identifiers next to the external ones, nothing sent yet
    summary = checked["summary"]
    assert summary["external"]["external_number"] == "000123456"
    assert summary["internal"]["property_id"] == assignment["property_id"]
    assert summary["customer_number"] == "0000123"
    assert [(u["unit_number"], u["external_unit_number"]) for u in summary["units"]] == [
        ("01", "0001"),
        ("02", "0002"),
    ]
    assert all(u["matched"] is None for u in summary["units"])
    body = checked["payload"]["body"]
    assert body["customerMscnumber"] == "0000123"
    assert [u["residentialunitMscnumber"] for u in body["residentialunits"]] == ["0001", "0002"]
    assert body["residentialunits"][0]["currentbillingrecipient"]["name"].startswith("Mieterin")
    assert checked["diff"]["first_transmission"] is True
    assert fake.writes == []
    # poll before the send is refused: there is no provider processing yet
    _problem(_poll(client, admin, checked), 409, "MHVP-METR-0011")
    released = _ok(_step(client, admin, checked, "release", acknowledge_warnings=True))
    assert released["status"] == "released"
    ordered = _ok(_step(client, admin, released, "order"))
    # accepted for processing only: never "ordered" or confirmed by the acceptance
    assert ordered["status"] == "waiting_provider"
    assert ordered["provider_transaction_id"] == "FAKE-TX-1"
    assert [w[:3] for w in fake.writes] == [("billing_unit_setup", "SEND", "000123456")]
    assert fake.writes[0][3]["residentialunits"] == body["residentialunits"]
    after_order = _ok(client.get(f"/api/v1/metering/assignments/{assignment['id']}", headers=admin))
    assert after_order["remote_confirmed"] is False
    # the provider is still processing (fake default IN_PROGRESS)
    waiting = _ok(_poll(client, admin, ordered))
    assert waiting["status"] == "waiting_provider"
    assert waiting["provider_response"]["poll"]["setupstatus"] == "IN_PROGRESS"
    assert fake.setup_polls == ["000123456"]
    # the provider result arrives: every sent unit matched, one additional at the provider
    _patch_config(client, admin, conn, fake_setup_status="COMPLETED", fake_setup_result=RESULT_BOTH)
    done = _ok(_poll(client, admin, waiting))
    assert done["status"] == "completed"
    assert done["summary"]["unmatched"] == []
    assert done["summary"]["additional"] == ["0009"]
    assert done["summary"]["remote_confirmed"] is True
    assert [u["matched"] for u in done["summary"]["units"]] == [True, True]
    assert done["provider_response"]["result"]["matched"] == RESULT_BOTH["matched"]
    confirmed = _ok(client.get(f"/api/v1/metering/assignments/{assignment['id']}", headers=admin))
    assert confirmed["remote_confirmed"] is True
    assert confirmed["remote_confirmed_at"] is not None
    assert "Anbieterergebnis" in confirmed["verification_basis"]
    assert "FAKE-TX-1" in confirmed["verification_basis"]
    assert confirmed["version"] == after_order["version"] + 1
    # a completed transmission is final: no second poll, no second send
    _problem(_poll(client, admin, done), 409, "MHVP-METR-0011")
    _problem(_step(client, admin, done, "order"), 409, "MHVP-METR-0011")
    assert len(fake.writes) == 1
    # the next check shows the provider's knowledge and the diff against the sent set
    again = _check(client, admin, {"assignment_id": assignment["id"], "kind": KIND})
    assert again["diff"] == {
        "first_transmission": False,
        "added": [],
        "removed": [],
        "changed": [],
    }
    assert again["summary"]["external"]["setupstatus"] == "COMPLETED"
    assert [u["known_at_provider"] for u in again["summary"]["units"]] == [True, True]
    assert any("0009" in w for w in again["validation"]["warnings"])
    assert len(units) == 2


def test_setup_partial_match_never_confirms_and_timeout_stays_unclear(
    client: TestClient, admin: dict[str, str]
) -> None:
    fake = _fake()
    conn, assignment, _units = _setup_bu(
        client,
        admin,
        "932",
        "000123457",
        fake_setup_status="COMPLETED",
        fake_setup_result={
            "billingunitMscnumber": "000123457",
            "matched": [{"residentialunitMscnumber": "0001"}],
            "additional": [],
        },
    )
    checked = _check(client, admin, {"assignment_id": assignment["id"], "kind": KIND})
    released = _ok(_step(client, admin, checked, "release", acknowledge_warnings=True))
    ordered = _ok(_step(client, admin, released, "order"))
    assert ordered["status"] == "waiting_provider"
    done = _ok(_poll(client, admin, ordered))
    assert done["status"] == "completed"
    assert done["summary"]["unmatched"] == ["0002"]
    assert done["summary"]["remote_confirmed"] is False
    assert [u["matched"] for u in done["summary"]["units"]] == [True, False]
    row = _ok(client.get(f"/api/v1/metering/assignments/{assignment['id']}", headers=admin))
    assert row["remote_confirmed"] is False
    # case 11: a write timeout ends in "unclear", nothing is repeated, no poll on it
    _patch_config(client, admin, conn, fake_write_unclear=True)
    checked = _check(client, admin, {"assignment_id": assignment["id"], "kind": KIND})
    released = _ok(_step(client, admin, checked, "release", acknowledge_warnings=True))
    unclear = _ok(_step(client, admin, released, "order"))
    assert unclear["status"] == "unclear"
    assert unclear["provider_response"]["results"][0]["outcome"] == "unclear"
    _problem(_step(client, admin, unclear, "order"), 409, "MHVP-METR-0011")
    _problem(_poll(client, admin, unclear), 409, "MHVP-METR-0011")
    assert len(fake.writes) == 2
    # missing customer number is a validation error, not a guess
    conn = _ok(client.get(f"/api/v1/metering/connections/{conn['id']}", headers=admin))
    _ok(
        client.patch(
            f"/api/v1/metering/connections/{conn['id']}",
            json={"version": conn["version"], "customer_references": []},
            headers=admin,
        )
    )
    invalid = _check(client, admin, {"assignment_id": assignment["id"], "kind": KIND})
    assert invalid["status"] == "invalid"
    assert any("Kundennummer" in e for e in invalid["validation"]["errors"])
    given = _check(
        client,
        admin,
        {"assignment_id": assignment["id"], "kind": KIND, "inputs": {"customer_number": "K-77"}},
    )
    assert given["status"] == "checked"
    assert given["payload"]["body"]["customerMscnumber"] == "K-77"


def test_setup_documentation_required_stays_at_local_preview(
    client: TestClient, admin: dict[str, str]
) -> None:
    fake = _fake()
    # Techem: no endpoint documentation, manual adapter (M40-02)
    conn = _connection(
        client,
        admin,
        "Techem manuell",
        provider_code="techem",
        secrets=False,
        config={},
        account_release={"billing_unit_data": True},
    )
    prop = _property(client, admin, "933")
    assignment = _ok(_assign(client, admin, conn, prop, external_number="000123458"), 201)
    unit_id = _unit(client, admin, prop, "01")
    _ok(
        client.post(
            f"/api/v1/metering/assignments/{assignment['id']}/units",
            json={
                "unit_id": unit_id,
                "external_unit_number": "0001",
                "valid_from": "2026-01-01",
                "occupancy_status": "vacant",
            },
            headers=admin,
        ),
        201,
    )
    checked = _check(client, admin, {"assignment_id": assignment["id"], "kind": KIND})
    assert checked["status"] == "checked"
    assert checked["validation"]["function_available"] is False
    assert checked["summary"]["units"][0]["external_unit_number"] == "0001"
    released = _ok(_step(client, admin, checked, "release", acknowledge_warnings=True))
    _problem(_step(client, admin, released, "order"), 409, "MHVP-METR-0004")
    assert fake.writes == []


def test_setup_permissions_write_release_and_tenant_boundaries(
    client: TestClient, world: World, admin: dict[str, str]
) -> None:
    fake = _fake()
    fake.setup_polls.clear()
    conn, assignment, _units = _setup_bu(client, admin, "934", "000123459")
    reader = bearer(login(client, world, "reader"))
    body = {"assignment_id": assignment["id"], "kind": KIND}
    assert (
        client.post("/api/v1/metering/transmissions/check", json=body, headers=reader).status_code
        == 403
    )
    checked = _check(client, admin, body)
    released = _ok(_step(client, admin, checked, "release", acknowledge_warnings=True))
    assert _step(client, reader, released, "order").status_code == 403
    assert _poll(client, reader, released).status_code == 403
    # write release of the connection off: the read function stays, the send is refused
    conn = _ok(
        client.patch(
            f"/api/v1/metering/connections/{conn['id']}",
            json={"version": conn["version"], "write_sync_enabled": False},
            headers=admin,
        )
    )
    _problem(_step(client, admin, released, "order"), 409, "MHVP-METR-0004")
    assert fake.writes == []
    conn = _ok(
        client.patch(
            f"/api/v1/metering/connections/{conn['id']}",
            json={"version": conn["version"], "write_sync_enabled": True},
            headers=admin,
        )
    )
    ordered = _ok(_step(client, admin, released, "order"))
    assert ordered["status"] == "waiting_provider"
    # the other tenant sees nothing and can neither poll nor order
    other = bearer(login(client, world, "both", tenant_id=world.tenant_b))
    assert (
        client.get(f"/api/v1/metering/transmissions/{ordered['id']}", headers=other).status_code
        == 404
    )
    assert _poll(client, other, ordered).status_code in {403, 404}
    assert ordered["id"] not in {
        r["id"]
        for r in _ok(client.get("/api/v1/metering/transmissions?kind=" + KIND, headers=other))
    }
    assert fake.setup_polls == []
    listed = _ok(
        client.get(
            f"/api/v1/metering/transmissions?assignment_id={assignment['id']}", headers=admin
        )
    )
    assert [r["kind"] for r in listed] == [KIND]
    assert uuid.UUID(ordered["id"])
