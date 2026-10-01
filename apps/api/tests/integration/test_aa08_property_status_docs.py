# ruff: noqa: F811
"""AA08 (GA02-01, 03, 04, 08, 09): billing period life cycle with lock, energy certificate and
maintenance/provider document references, follow-up due date of a recurring maintenance and
the VAT option history of a unit. Rows and expected values are invented and recomputable."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_m2_platform import World
from tests.integration.test_m5_contracts import _unit
from tests.integration.test_p16_w2 import _contact, _doc, _heads, _ok, client, world  # noqa: F401

pytestmark = pytest.mark.integration

P = "/api/v1/properties"


def _prop(c: TestClient, h: dict[str, str], number: str) -> str:
    body = {"number": number, "name": f"AA08 Objekt {number}", "management_type": "rental"}
    return str(_ok(c.post(P, json=body, headers=h), 201)["id"])


def test_billing_period_life_cycle_and_lock(client: TestClient, world: World) -> None:
    h, reader, other = _heads(client, world)
    pid = _prop(client, h, "881")
    url = f"{P}/{pid}/billing-periods"
    period = _ok(
        client.post(
            url,
            json={"kind": "heating_costs", "valid_from": "2025-01-01", "valid_to": "2025-12-31"},
            headers=h,
        ),
        201,
    )
    assert period["status"] == "open"
    assert period["locked_at"] is None
    st = f"{url}/{period['id']}/status"
    # skipping a step and unknown values are refused
    assert client.post(st, json={"status": "confirmed"}, headers=h).status_code == 409
    assert client.post(st, json={"status": "done"}, headers=h).status_code == 422
    assert client.post(st, json={"status": "open"}, headers=h).status_code == 409
    row = _ok(client.post(st, json={"status": "results_created"}, headers=h))
    assert row["status"] == "results_created"
    # one step back is allowed, then forward to closed
    assert _ok(client.post(st, json={"status": "open"}, headers=h))["status"] == "open"
    for step in ("results_created", "confirmed"):
        assert _ok(client.post(st, json={"status": step}, headers=h))["locked_at"] is None
    closed = _ok(client.post(st, json={"status": "closed"}, headers=h))
    assert closed["status"] == "closed"
    assert closed["locked_at"] is not None
    listed = _ok(client.get(url, headers=h))
    assert listed[0]["status"] == "closed"
    # closed is final and cannot be deleted
    refused = client.post(st, json={"status": "confirmed"}, headers=h)
    assert refused.status_code == 409
    assert refused.json()["code"] == "MHVP-PROP-0006"
    gone = client.delete(f"{url}/{period['id']}", headers=h)
    assert gone.status_code == 409
    assert gone.json()["code"] == "MHVP-PROP-0007"
    # an open period can still be deleted
    other_period = _ok(
        client.post(
            url,
            json={"kind": "heating_costs", "valid_from": "2026-01-01", "valid_to": "2026-12-31"},
            headers=h,
        ),
        201,
    )
    assert client.delete(f"{url}/{other_period['id']}", headers=h).status_code == 204
    # authorization and tenant separation
    assert client.post(st, json={"status": "open"}, headers=reader).status_code == 403
    assert client.post(st, json={"status": "open"}, headers=other).status_code == 404


def test_operating_cost_period_needs_calculated_statement(
    client: TestClient,
    world: World,
) -> None:
    h, _reader, _other = _heads(client, world)
    pid = _prop(client, h, "882")
    period = _ok(
        client.post(
            f"{P}/{pid}/billing-periods",
            json={"kind": "operating_costs", "valid_from": "2025-01-01", "valid_to": "2025-12-31"},
            headers=h,
        ),
        201,
    )
    blocked = client.post(
        f"{P}/{pid}/billing-periods/{period['id']}/status",
        json={"status": "results_created"},
        headers=h,
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "MHVP-PROP-0006"


def test_energy_certificate_and_document_references(
    client: TestClient,
    world: World,
) -> None:
    h, reader, other = _heads(client, world)
    pid = _prop(client, h, "883")
    doc = _doc(client, h, "Energieausweis")
    building = _ok(
        client.post(
            f"{P}/{pid}/buildings",
            json={"name": "Haus A", "energy_certificate_document_id": doc},
            headers=h,
        ),
        201,
    )
    assert building["energy_certificate_document_id"] == doc
    url = f"/api/v1/buildings/{building['id']}"
    fresh = _ok(client.get(f"{P}/{pid}/buildings", headers=h))[0]
    assert fresh["energy_certificate_document_id"] == doc
    version = str(fresh["version"])
    missing = client.patch(
        url,
        json={"energy_certificate_document_id": str(uuid.uuid4())},
        headers=h | {"If-Match": version},
    )
    assert missing.status_code == 422
    cleared = _ok(
        client.patch(
            url,
            json={"energy_certificate_document_id": None},
            headers=h | {"If-Match": version},
        )
    )
    assert cleared["energy_certificate_document_id"] is None

    # maintenance item and provider relation carry documents
    d1, d2 = _doc(client, h, "Pruefbericht"), _doc(client, h, "Vertrag")
    item = _ok(
        client.post(
            f"{P}/{pid}/maintenance",
            json={"kind": "inspection", "title": "Aufzugprüfung", "documents": [d1]},
            headers=h,
        ),
        201,
    )
    assert item["documents"] == [d1]
    mi = f"/api/v1/maintenance/{item['id']}"
    assert _ok(client.patch(mi, json={"documents": [d1, d2]}, headers=h))["documents"] == [d1, d2]
    for bad in ([str(uuid.uuid4())], [d1, d1], ["x"]):
        assert client.patch(mi, json={"documents": bad}, headers=h).status_code == 422
    assert client.patch(mi, json={"documents": []}, headers=reader).status_code == 403
    assert client.patch(mi, json={"documents": []}, headers=other).status_code == 404

    provider = _contact(client, h, "Aufzugbau")
    relation = _ok(
        client.post(
            f"{P}/{pid}/service-providers",
            json={
                "contact_id": provider["id"],
                "contract_type_code": "heating_maintenance",
                "valid_from": "2026-01-01",
                "documents": [d2],
            },
            headers=h,
        ),
        201,
    )
    assert relation["documents"] == [d2]
    rurl = f"{P}/{pid}/service-providers/{relation['id']}"
    assert _ok(client.patch(rurl, json={"documents": [d1]}, headers=h))["documents"] == [d1]
    assert client.patch(rurl, json={"documents": None}, headers=h).status_code == 422
    unknown = client.patch(rurl, json={"documents": [str(uuid.uuid4())]}, headers=h)
    assert unknown.status_code == 422


def test_recurring_maintenance_follow_up_and_reminder(
    client: TestClient,
    world: World,
) -> None:
    """GA02-08: completing sets the due date to done_on plus interval and keeps the reminder
    lead time (remind_before), so the next reminder falls on the new due date minus 1 month."""
    h, _reader, _other = _heads(client, world)
    pid = _prop(client, h, "884")
    item = _ok(
        client.post(
            f"{P}/{pid}/maintenance",
            json={
                "kind": "inspection",
                "title": "Rauchmelderprüfung",
                "due_date": "2026-03-15",
                "interval_months": 6,
                "remind_before": "1m",
            },
            headers=h,
        ),
        201,
    )
    done: dict[str, Any] = _ok(
        client.post(
            f"/api/v1/maintenance/{item['id']}/done", json={"done_on": "2026-03-20"}, headers=h
        )
    )
    # 20.03.2026 + 6 months = 20.09.2026
    assert done["next_due_date"] == "2026-09-20"
    assert done["item"]["status"] == "open"
    assert done["item"]["due_date"] == "2026-09-20"
    assert done["item"]["remind_before"] == "1m"
    assert done["item"]["last_done_on"] == "2026-03-20"
    # a second cycle: 20.09.2026 + 6 months = 20.03.2027
    again = _ok(
        client.post(
            f"/api/v1/maintenance/{item['id']}/done", json={"done_on": "2026-09-20"}, headers=h
        )
    )
    assert again["next_due_date"] == "2027-03-20"


def test_vat_option_history_overlap_and_change(
    client: TestClient,
    world: World,
) -> None:
    """GA02-09: periods of one unit never overlap (409), the change from vacancy to a
    contract tenant is a new period and the history lists both, newest first."""
    h, reader, other = _heads(client, world)
    pid = _prop(client, h, "885")
    unit = _unit(client, h, pid, "01")
    url = f"/api/v1/units/{unit}/vat-options"

    def post(option: str, occupant: str, start: str, end: str | None, hdr: Any = h) -> Any:
        body = {"option": option, "occupant": occupant, "valid_from": start, "valid_to": end}
        return client.post(url, json=body, headers=hdr)

    _ok(post("none", "vacancy", "2026-01-01", "2026-06-30"), 201)
    overlap = post("commercial_full_vat", "contract", "2026-06-30", None)
    assert overlap.status_code == 409
    _ok(post("commercial_full_vat", "contract", "2026-07-01", None), 201)
    history = _ok(client.get(url, headers=h))
    assert [(r["valid_from"], r["occupant"], r["option"]) for r in history] == [
        ("2026-07-01", "contract", "commercial_full_vat"),
        ("2026-01-01", "vacancy", "none"),
    ]
    # open ended period blocks any later start, validation and authorization
    assert post("none", "vacancy", "2027-01-01", None).status_code == 409
    assert post("none", "vacancy", "2026-05-01", "2026-04-01").status_code == 422
    assert post("none", "vacancy", "2030-01-01", None, reader).status_code == 403
    assert post("none", "vacancy", "2030-01-01", None, other).status_code == 404
