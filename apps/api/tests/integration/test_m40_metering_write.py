"""Messdienstleister, controlled write workflows (master prompt Messdienstleister section 12,
cases 11 and 12): user and role submission (On-Site Roles 2.0 semantics) and billing input
with the separate steps "Daten prüfen", release and binding order. Artificial data only: the
``fake`` adapter records every write and never reaches a provider; no real order, user change
or billing is triggered (end to end checks with real access are not executed)."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.metering.adapters import _ADAPTERS, FakeAdapter
from tests.integration.test_m2_platform import RUN, World, bearer, client, login
from tests.integration.test_m40_metering import (
    _assign,
    _connection,
    _ok,
    _problem,
    _property,
    _unit,
    admin,
)

pytestmark = pytest.mark.integration

__all__ = ["admin", "client"]

WRITE_RELEASE = {
    "consumption": True,
    "billing_result": True,
    "roles": True,
    "billing_input": True,
}


def _fake() -> FakeAdapter:
    adapter = _ADAPTERS["fake"]
    assert isinstance(adapter, FakeAdapter)
    adapter.writes.clear()
    return adapter


def _contact(client: TestClient, h: dict[str, str], name: str) -> str:
    return str(
        _ok(
            client.post(
                "/api/v1/contacts",
                json={"kind": "person", "first_name": "Erika", "last_name": f"{name} {RUN}"},
                headers=h,
            ),
            201,
        )["id"]
    )


def _write_connection(
    client: TestClient, h: dict[str, str], name: str, **config: Any
) -> dict[str, Any]:
    conn = _connection(
        client,
        h,
        name,
        account_release=WRITE_RELEASE,
        config={"adapter": "fake", **config},
    )
    _ok(client.post(f"/api/v1/metering/connections/{conn['id']}/test", headers=h))
    conn = _ok(client.get(f"/api/v1/metering/connections/{conn['id']}", headers=h))
    conn = _ok(
        client.patch(
            f"/api/v1/metering/connections/{conn['id']}",
            json={"version": conn["version"], "write_sync_enabled": True},
            headers=h,
        )
    )
    return dict(conn)


def _setup(
    client: TestClient, h: dict[str, str], number: str, ext: str, **config: Any
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    conn = _write_connection(client, h, f"ista Schreiben {number} {RUN}", **config)
    prop = _property(client, h, number)
    assignment = _ok(_assign(client, h, conn, prop, external_number=ext), 201)
    owner = _contact(client, h, "Eigentümerin")
    tenant = _contact(client, h, "Mieterin")
    units = []
    for unit_number, external, occupancy, recipient in (
        ("01", "0001", "occupied", tenant),
        ("02", "0002", "vacant", owner),
    ):
        unit_id = _unit(client, h, prop, unit_number)
        units.append(
            _ok(
                client.post(
                    f"/api/v1/metering/assignments/{assignment['id']}/units",
                    json={
                        "unit_id": unit_id,
                        "external_unit_number": external,
                        "valid_from": "2026-01-01",
                        "occupancy_status": occupancy,
                        "billing_recipient_contact_id": recipient,
                    },
                    headers=h,
                ),
                201,
            )
        )
    return conn, assignment, units


def _check(client: TestClient, h: dict[str, str], body: dict[str, Any], status: int = 201) -> Any:
    return _ok(client.post("/api/v1/metering/transmissions/check", json=body, headers=h), status)


def _step(
    client: TestClient, h: dict[str, str], row: dict[str, Any], step: str, **extra: Any
) -> Any:
    return client.post(
        f"/api/v1/metering/transmissions/{row['id']}/{step}",
        json={"version": row["version"], "fingerprint": row["fingerprint"], **extra},
        headers=h,
    )


def test_roles_full_set_with_vacancy_and_end_markers_and_diff(
    client: TestClient, world: World, admin: dict[str, str]
) -> None:
    fake = _fake()
    _conn, assignment, units = _setup(client, admin, "921", "0004801")
    checked = _check(client, admin, {"assignment_id": assignment["id"], "kind": "roles"})
    assert checked["status"] == "checked", checked["validation"]
    assert checked["diff"]["first_transmission"] is True
    bodies = {u["external_unit_number"]: u["body"] for u in checked["payload"]["units"]}
    # the complete set: both units, the vacant one with an explicit vacancy contract
    assert set(bodies) == {"0001", "0002"}
    assert bodies["0001"]["billingcontracts"][0]["vacancy"] is False
    assert bodies["0002"]["billingcontracts"][0]["vacancy"] is True
    assert bodies["0002"]["billingcontracts"][0]["billingrecipient"]["owner"] is True
    assert "terminateallbillingcontracts" not in bodies["0001"]
    assert fake.writes == []  # "Daten prüfen" of roles never reaches the provider
    released = _ok(_step(client, admin, checked, "release", acknowledge_warnings=True))
    assert released["status"] == "released" and released["released_by"]  # noqa: PT018
    ordered = _ok(_step(client, admin, released, "order"))
    assert ordered["status"] == "ordered"
    assert ordered["provider_transaction_id"] == "FAKE-TX-1"
    assert [w[0:3] for w in fake.writes] == [
        ("roles", "SEND", "0001"),
        ("roles", "SEND", "0002"),
    ]
    actions = [entry["action"] for entry in ordered["log"]]
    assert actions == ["checked", "released", "ordered"]
    assert all(
        entry["user_id"] and entry["at"] and entry["data_version"] for entry in ordered["log"]
    )
    assert ordered["log"][-1]["transaction_id"] == "FAKE-TX-1"
    # end of a unit assignment becomes an explicit end marker, never an omitted role
    ended = _ok(
        client.patch(
            f"/api/v1/metering/unit-assignments/{units[0]['id']}",
            json={"version": units[0]["version"], "valid_to": "2026-03-31"},
            headers=admin,
        )
    )
    assert ended["valid_to"] == "2026-03-31"
    second = _check(client, admin, {"assignment_id": assignment["id"], "kind": "roles"})
    body = next(
        u["body"] for u in second["payload"]["units"] if u["external_unit_number"] == "0001"
    )
    assert body["terminateallbillingcontracts"] is True
    assert body["terminateallbillingcontractsat"] == "2026-03-31"
    assert body["billingcontracts"] == []
    assert second["diff"] == {
        "first_transmission": False,
        "added": [],
        "removed": [],
        "changed": ["0001"],
    }


def test_roles_validation_reports_missing_data_and_unclear_occupancy(
    client: TestClient, world: World, admin: dict[str, str]
) -> None:
    _conn, assignment, units = _setup(client, admin, "922", "0004802")
    unassigned = _unit(client, admin, _property(client, admin, "922"), "03")
    _ok(
        client.patch(
            f"/api/v1/metering/unit-assignments/{units[1]['id']}",
            json={"version": units[1]["version"], "occupancy_status": "unclear"},
            headers=admin,
        )
    )
    row = _check(client, admin, {"assignment_id": assignment["id"], "kind": "roles"})
    assert row["status"] == "invalid"
    errors = "\n".join(row["validation"]["errors"])
    assert "Einheit 03: keine Nutzeinheit zugeordnet" in errors
    assert "Belegung ist ungeklärt" in errors
    assert unassigned
    # an invalid data set can neither be released nor ordered
    _problem(_step(client, admin, row, "release"), 409, "MHVP-METR-0011")
    _problem(_step(client, admin, row, "order"), 409, "MHVP-METR-0011")


def test_billing_input_check_release_and_order_are_separate_and_warnings_are_explicit(
    client: TestClient, world: World, admin: dict[str, str]
) -> None:
    fake = _fake()
    _conn, assignment, _units = _setup(
        client,
        admin,
        "923",
        "0004803",
        fake_billing_template={
            "currency": "EUR",
            "expectedvat": "GROSS",
            "ancillarycosts": [{"key": "9990"}],
        },
        fake_write_messages=[
            {"type": "warning", "message": "Rechnungsdatum außerhalb des Zeitraums"}
        ],
    )
    body = {
        "assignment_id": assignment["id"],
        "kind": "billing_input",
        "period_from": "2026-01-01",
        "period_to": "2026-12-31",
        "inputs": {
            "ancillary_invoices": [
                {"key": "9990", "allocation_key": "AREA", "gross_amount": "1234.56"}
            ]
        },
    }
    checked = _check(client, admin, body)
    assert checked["status"] == "checked", checked["validation"]
    assert checked["validation"]["provider"]["called"] is True
    assert checked["validation"]["provider"]["action"] == "VALIDATE"
    assert checked["summary"]["billing_recipients"] == 2
    assert checked["payload"]["body"]["currency"] == "EUR"
    assert checked["payload"]["body"]["ancillaryinvoices"][0]["amounts"] == {
        "grossamount": "1234.56"
    }
    # "Daten prüfen" is validate only: exactly one VALIDATE, no SEND
    assert [w[1] for w in fake.writes] == ["VALIDATE"]
    # order without release is refused; release without acknowledging the warning too
    _problem(_step(client, admin, checked, "order"), 409, "MHVP-METR-0011")
    _problem(_step(client, admin, checked, "release"), 422, "MHVP-METR-0013")
    released = _ok(_step(client, admin, checked, "release", acknowledge_warnings=True))
    assert released["warnings_acknowledged"] is True
    assert [w[1] for w in fake.writes] == ["VALIDATE"]
    ordered = _ok(_step(client, admin, released, "order"))
    assert ordered["status"] == "ordered"
    assert [w[1] for w in fake.writes] == ["VALIDATE", "SEND_AND_IGNORE_WARNINGS"]
    assert ordered["provider_response"]["results"][0]["transaction_id"] == "FAKE-TX-1"
    # a second order of the same transmission is refused (already ordered)
    _problem(_step(client, admin, ordered, "order"), 409, "MHVP-METR-0011")
    assert len(fake.writes) == 2
    # amounts are validated: three decimals or zero are errors, not rounded
    invalid = _check(
        client,
        admin,
        body
        | {
            "inputs": {
                "ancillary_invoices": [
                    {"key": "9990", "allocation_key": "AREA", "gross_amount": "1.005"}
                ]
            }
        },
    )
    assert invalid["status"] == "invalid"
    assert any("Nachkommastellen" in e for e in invalid["validation"]["errors"])
    assert len(fake.writes) == 2  # local errors: no provider call at all


def test_case_11_payload_change_invalidates_release_and_timeout_stays_unclear(
    client: TestClient, world: World, admin: dict[str, str]
) -> None:
    fake = _fake()
    conn, assignment, units = _setup(client, admin, "924", "0004804")
    checked = _check(client, admin, {"assignment_id": assignment["id"], "kind": "roles"})
    released = _ok(_step(client, admin, checked, "release", acknowledge_warnings=True))
    # a relevant assignment change supersedes the release immediately
    _ok(
        client.patch(
            f"/api/v1/metering/unit-assignments/{units[0]['id']}",
            json={"version": units[0]["version"], "occupancy_status": "owner_use"},
            headers=admin,
        )
    )
    stale = _ok(client.get(f"/api/v1/metering/transmissions/{released['id']}", headers=admin))
    assert stale["status"] == "superseded"
    assert stale["log"][-1]["reason"] == "Einheitenzuordnung geändert."
    _problem(_step(client, admin, stale, "order"), 409, "MHVP-METR-0011")
    assert fake.writes == []
    # a wrong fingerprint (client with an outdated payload) never orders either
    fresh = _check(client, admin, {"assignment_id": assignment["id"], "kind": "roles"})
    wrong = _step(
        client, admin, fresh | {"fingerprint": "0" * 64}, "release", acknowledge_warnings=True
    )
    _problem(wrong, 409, "MHVP-METR-0012")
    assert fake.writes == []
    # write timeout: sent exactly once, status unclear, no automatic retry
    _ok(
        client.patch(
            f"/api/v1/metering/connections/{conn['id']}",
            json={
                "version": conn["version"],
                "config": {"adapter": "fake", "fake_write_unclear": True},
            },
            headers=admin,
        )
    )
    _ok(client.post(f"/api/v1/metering/connections/{conn['id']}/test", headers=admin))
    again = _check(client, admin, {"assignment_id": assignment["id"], "kind": "roles"})
    released = _ok(_step(client, admin, again, "release", acknowledge_warnings=True))
    unclear = _ok(_step(client, admin, released, "order"))
    assert unclear["status"] == "unclear"
    assert len(fake.writes) == 1  # stopped at the first unit, nothing repeated
    assert unclear["provider_response"]["results"][0]["outcome"] == "unclear"
    _problem(_step(client, admin, unclear, "order"), 409, "MHVP-METR-0011")
    assert len(fake.writes) == 1


def test_case_12_permissions_release_flag_and_tenant_boundaries(
    client: TestClient, world: World, admin: dict[str, str]
) -> None:
    fake = _fake()
    conn, assignment, _units = _setup(client, admin, "925", "0004805")
    reader = bearer(login(client, world, "reader"))
    body = {"assignment_id": assignment["id"], "kind": "roles"}
    assert (
        client.post("/api/v1/metering/transmissions/check", json=body, headers=reader).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/metering/transmissions/check",
            json=body
            | {"kind": "billing_input", "period_from": "2025-01-01", "period_to": "2025-12-31"},
            headers=reader,
        ).status_code
        == 403
    )
    checked = _check(client, admin, body)
    released = _ok(_step(client, admin, checked, "release", acknowledge_warnings=True))
    assert _step(client, reader, released, "order").status_code == 403
    # the other tenant sees nothing
    other = bearer(login(client, world, "both", tenant_id=world.tenant_b))
    assert (
        client.get(f"/api/v1/metering/transmissions/{released['id']}", headers=other).status_code
        == 404
    )
    # module switch of tenant B (403) or unknown row (404): never an order, never a 200
    assert _step(client, other, released, "order").status_code in {403, 404}
    assert released["id"] not in {
        r["id"] for r in _ok(client.get("/api/v1/metering/transmissions", headers=other))
    }
    # per connection release flag off: capability unavailable, order refused
    conn = _ok(
        client.patch(
            f"/api/v1/metering/connections/{conn['id']}",
            json={"version": conn["version"], "write_sync_enabled": False},
            headers=admin,
        )
    )
    cap = {c["function"]: c for c in conn["capabilities"]}
    assert cap["roles"]["available"] is False and "write_sync_enabled" in cap["roles"]["reason"]  # noqa: PT018
    _problem(_step(client, admin, released, "order"), 409, "MHVP-METR-0004")
    assert fake.writes == []
    # connection test and read only sync never write (case 12)
    _ok(client.post(f"/api/v1/metering/connections/{conn['id']}/test", headers=admin))
    assert fake.writes == []
    # the module switch locks the write endpoints as well
    _ok(
        client.patch(
            "/api/v1/tenant/settings", json={"metering_module_enabled": False}, headers=admin
        )
    )
    try:
        _problem(
            client.post("/api/v1/metering/transmissions/check", json=body, headers=admin),
            403,
            "MHVP-METR-0001",
        )
    finally:
        _ok(
            client.patch(
                "/api/v1/tenant/settings", json={"metering_module_enabled": True}, headers=admin
            )
        )
    assert uuid.UUID(released["id"])
