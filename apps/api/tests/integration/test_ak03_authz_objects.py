"""AK03 (GAI-303 Rest der Pakete AJ06 und AJ24): tenant separation with real objects.

Every object is created in tenant A: rental statement with heating, heating cost import,
owner statement, metering connection, assignment, unit assignment and transmission, a
telephony call, a mailbox and a playbook. The administrator of tenant B must receive 404
(the object does not exist for him), the read only user of tenant A must receive 403.
The portal handover is checked with portal users: a portal user of tenant B and a portal
user of tenant A without a grant on the protocol both receive 404. Afterwards the objects
are unchanged for tenant A.
"""

import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.communication import telephony as hook
from mhvp.main import create_app
from tests.integration.ak03_authz_world import (
    RUN,
    AuthzWorld,
    build_world,
    call,
    headers,
    ok,
    settings,
)
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD

pytestmark = pytest.mark.integration

FP = "0" * 64
SECRET = "ak03-telephony-secret-for-tenant-a-only"


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> AuthzWorld:
    return build_world(database, redis_url)


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(settings(database, redis_url))) as test_client:
        yield test_client


def _contact(c: TestClient, h: dict[str, str], last: str, **extra: Any) -> str:
    body = {"kind": "person", "first_name": "Test", "last_name": f"{last} {RUN}", **extra}
    return str(ok(c.post("/api/v1/contacts", json=body, headers=h))["id"])


def _billing(c: TestClient, h: dict[str, str], out: dict[str, str]) -> None:
    prop = ok(
        c.post(
            "/api/v1/properties",
            json={
                "number": "903",
                "name": f"Objekt {RUN}",
                "management_type": "rental",
                "street": "Rheinpromenade",
                "house_number": "3",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        )
    )
    building = ok(
        c.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h)
    )
    unit = ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={"building_id": building["id"], "number": "01", "unit_type": "apartment"},
            headers=h,
        )
    )
    owner_contact = ok(
        c.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Vermieter {RUN} GmbH"},
            headers=h,
        )
    )
    owner = ok(
        c.post(
            "/api/v1/parties", json={"members": [{"contact_id": owner_contact["id"]}]}, headers=h
        )
    )
    entity = ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner["id"], "valid_from": "2020-01-01"},
            headers=h,
        )
    )["legal_entity_id"]
    ledger = ok(c.post("/api/v1/accounting/ledgers", json={"legal_entity_id": entity}, headers=h))
    period = {"ledger_id": ledger["id"], "period_from": "2025-01-01", "period_to": "2025-12-31"}
    statement = ok(c.post("/api/v1/statements", json=period, headers=h))
    owner_statement = ok(c.post("/api/v1/billing/owner-statements", json=period, headers=h))
    provider = _contact(c, h, "Messdienst")
    imp = ok(
        c.post(
            "/api/v1/billing/heating-cost-imports",
            json={
                "property_id": prop["id"],
                "provider_contact_id": provider,
                "provider_name": "Messdienst Test",
                "period_from": "2025-01-01",
                "period_to": "2025-12-31",
                "document_total": "2300.00",
            },
            headers=h,
        )
    )
    out.update(
        property=prop["id"],
        building=building["id"],
        unit=unit["id"],
        statement=statement["id"],
        owner_statement=owner_statement["id"],
        heating_import=imp["id"],
        contact=provider,
    )


def _metering(c: TestClient, h: dict[str, str], out: dict[str, str]) -> None:
    conn = ok(
        c.post(
            "/api/v1/metering/connections",
            json={
                "display_name": f"ista {RUN}",
                "provider_code": "ista",
                "environment": "test",
                "customer_references": ["0000903"],
                "config": {"adapter": "fake"},
                "account_release": {
                    "consumption": True,
                    "billing_result": True,
                    "roles": True,
                    "billing_input": True,
                },
                "secrets": {"api_key": "ak03-fake-key"},
            },
            headers=h,
        )
    )
    assignment = ok(
        c.post(
            "/api/v1/metering/assignments",
            json={
                "connection_id": conn["id"],
                "property_id": out["property"],
                "external_number": "0090301",
                "service_scope": "heating",
                "valid_from": "2026-01-01",
            },
            headers=h,
        )
    )
    unit_assignment = ok(
        c.post(
            f"/api/v1/metering/assignments/{assignment['id']}/units",
            json={
                "unit_id": out["unit"],
                "external_unit_number": "0001",
                "valid_from": "2026-01-01",
                "occupancy_status": "vacant",
                "billing_recipient_contact_id": out["contact"],
            },
            headers=h,
        )
    )
    transmission = ok(
        c.post(
            "/api/v1/metering/transmissions/check",
            json={"assignment_id": assignment["id"], "kind": "roles"},
            headers=h,
        )
    )
    out.update(
        connection=conn["id"],
        assignment=assignment["id"],
        unit_assignment=unit_assignment["id"],
        transmission=transmission["id"],
    )


def _communication(
    c: TestClient, h: dict[str, str], world: AuthzWorld, out: dict[str, str]
) -> None:
    ok(
        c.put(
            "/api/v1/communication/telephony/settings",
            json={"enabled": True, "provider_label": "Testanlage", "webhook_secret": SECRET},
            headers=h,
        ),
        200,
    )
    raw = json.dumps(
        {
            "event": "call.started",
            "number": "+4921190300001",
            "direction": "inbound",
            "provider_ref": f"call-{RUN}",
        }
    ).encode()
    ts = int(time.time())
    delivered = ok(
        c.post(
            "/api/v1/communication/webhooks/telephony",
            content=raw,
            headers={
                "Content-Type": "application/json",
                hook.TIMESTAMP_HEADER: str(ts),
                hook.SIGNATURE_HEADER: hook.sign(SECRET, ts, raw),
                hook.TENANT_HEADER: str(world.tenant_a),
            },
        ),
        200,
    )
    mailbox = ok(
        c.post(
            "/api/v1/mail/mailboxes",
            json={"address": f"box-{RUN}@example.com", "kind": "imap"},
            headers=h,
        )
    )
    playbook = ok(
        c.post(
            "/api/v1/mail/playbooks",
            json={
                "title": f"Heizung {RUN}",
                "category": "Heizung",
                "keywords": ["heizung"],
                "summary": "Heizungsausfall melden.",
                "steps": ["Notdienst kontaktieren"],
                "reply_template": "Guten Tag,\n\nwir kümmern uns.",
                "status": "draft",
            },
            headers=h,
        )
    )
    out.update(call=delivered["call_id"], mailbox=mailbox["id"], playbook=playbook["id"])


def _handover(c: TestClient, h: dict[str, str], world: AuthzWorld, name: str) -> str:
    """A protocol with a portal participant ``name`` who accepted the invitation."""
    pid = ok(c.post("/api/v1/handover/protocols", json={"kind": "rental"}, headers=h))["id"]
    contact = _contact(c, h, name, emails=[{"email": world.email(name), "is_primary": True}])
    mover = ok(
        c.post(
            f"/api/v1/handover/protocols/{pid}/participants",
            json={"contact_id": contact, "role": "moving_in"},
            headers=h,
        )
    )
    grant = ok(
        c.post(
            f"/api/v1/handover/protocols/{pid}/participants/{mover['id']}/portal-access",
            json={},
            headers=h,
        )
    )
    ok(
        c.post(
            "/api/v1/portal/invitations/accept",
            json={"token": grant["invitation_token"], "password": PASSWORD},
        ),
        200,
    )
    return str(pid)


@pytest.fixture(scope="module")
def objects(client: TestClient, world: AuthzWorld) -> dict[str, str]:
    h = headers(client, world, "ak03adm")
    out: dict[str, str] = {}
    # The metering module lock would otherwise answer 403 before the lookup.
    for user in ("ak03adm", "ak03oth"):
        ok(
            client.patch(
                "/api/v1/tenant/settings",
                json={"metering_module_enabled": True},
                headers=headers(client, world, user),
            ),
            200,
        )
    _billing(client, h, out)
    _metering(client, h, out)
    _communication(client, h, world, out)
    out["handover"] = _handover(client, h, world, "ak03pa")
    # A second protocol of tenant A without a grant for the portal user ak03pa.
    out["handover_other"] = ok(
        client.post("/api/v1/handover/protocols", json={"kind": "rental"}, headers=h)
    )["id"]
    _handover(client, headers(client, world, "ak03oth"), world, "ak03pb")
    return out


H = "/api/v1/statements/{statement}/heating"
I = "/api/v1/billing/heating-cost-imports/{heating_import}"  # noqa: E741
O = "/api/v1/billing/owner-statements/{owner_statement}"  # noqa: E741
M = "/api/v1/metering"
VFP = {"version": 1, "fingerprint": FP}

# (method, path template, body); every route requires a write permission. Bodies are valid
# so that the foreign tenant reaches the lookup (404) and not the validation (422).
CASES: list[tuple[str, str, Any]] = [
    # billing: rental statement and heating
    ("PATCH", "/api/v1/statements/{statement}", {"purpose": "fremde Änderung"}),
    ("POST", "/api/v1/statements/{statement}/calculate", None),
    ("POST", "/api/v1/statements/{statement}/transition", {"target": "board_reviewed"}),
    ("POST", "/api/v1/statements/{statement}/new-version", {"reason": "fremde Version"}),
    ("PUT", H + "/consumptions", {}),
    ("POST", H + "/calculate", {}),
    # billing: heating cost import
    ("PUT", I + "/mapping", {"mapping": {}}),
    ("PUT", I + "/rows", {"rows": []}),
    ("POST", I + "/csv", {"content": "a;b", "column_map": {}}),
    ("POST", I + "/check", {}),
    ("POST", I + "/apply", {"statement_id": "{statement}"}),
    # billing: owner statement
    ("POST", O + "/calculate", None),
    ("POST", O + "/approve", None),
    # Non gated target: the closed gate G3 is checked before the lookup.
    ("POST", O + "/transition", {"target": "board_reviewed"}),
    # metering
    ("PATCH", M + "/connections/{connection}", {"version": 1, "display_name": "fremd"}),
    ("PUT", M + "/connections/{connection}/secrets", {"secrets": {"api_key": "fremd"}}),
    ("POST", M + "/connections/{connection}/test", None),
    ("PATCH", M + "/assignments/{assignment}", {"version": 1, "note": "fremd"}),
    (
        "POST",
        M + "/assignments/{assignment}/change-provider",
        {
            "version": 1,
            "change_date": "2026-06-01",
            "new_connection_id": "{connection}",
            "new_external_number": "0090399",
        },
    ),
    ("PATCH", M + "/unit-assignments/{unit_assignment}", {"version": 1, "note": "fremd"}),
    ("POST", M + "/transmissions/{transmission}/release", VFP),
    ("POST", M + "/transmissions/{transmission}/order", VFP),
    ("POST", M + "/transmissions/{transmission}/poll", None),
    # telephony
    ("PATCH", "/api/v1/communication/calls/{call}", {"note": "fremd"}),
    ("POST", "/api/v1/communication/calls/{call}/assign", {"contact_id": "{contact}"}),
    ("POST", "/api/v1/communication/calls/{call}/proposal/dismiss", None),
    # mail
    ("PATCH", "/api/v1/mail/mailboxes/{mailbox}", {"enabled": True}),
    ("PUT", "/api/v1/mail/mailboxes/{mailbox}/users", {"user_ids": []}),
    ("POST", "/api/v1/mail/mailboxes/{mailbox}/sync", None),
    ("POST", "/api/v1/mail/mailboxes/{mailbox}/reconcile-state", {}),
    ("DELETE", "/api/v1/mail/mailboxes/{mailbox}", None),
    ("PATCH", "/api/v1/mail/playbooks/{playbook}", {"title": "fremd"}),
    ("POST", "/api/v1/mail/playbooks/{playbook}/feedback", {"helpful": False}),
    ("POST", "/api/v1/mail/playbooks/{playbook}/use", None),
    ("DELETE", "/api/v1/mail/playbooks/{playbook}", None),
]

# Reading routes with a path parameter of the same objects.
READS: list[str] = [
    "/api/v1/statements/{statement}",
    I,
    O,
    M + "/connections/{connection}",
    M + "/transmissions/{transmission}",
    "/api/v1/handover/protocols/{handover}",
]


def _fill(value: Any, objects: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format(**objects)
    if isinstance(value, dict):
        return {k: _fill(v, objects) for k, v in value.items()}
    return value


@pytest.mark.parametrize(("method", "template", "body"), CASES)
def test_foreign_tenant_gets_404(
    client: TestClient,
    world: AuthzWorld,
    objects: dict[str, str],
    method: str,
    template: str,
    body: Any,
) -> None:
    h = headers(client, world, "ak03oth")
    response = call(client, method, template.format(**objects), h, _fill(body, objects))
    assert response.status_code == 404, response.text


@pytest.mark.parametrize(("method", "template", "body"), CASES)
def test_read_only_user_gets_403(
    client: TestClient,
    world: AuthzWorld,
    objects: dict[str, str],
    method: str,
    template: str,
    body: Any,
) -> None:
    h = headers(client, world, "ak03rd")
    response = call(client, method, template.format(**objects), h, _fill(body, objects))
    assert response.status_code == 403, response.text


@pytest.mark.parametrize("template", READS)
def test_foreign_tenant_read_gets_404(
    client: TestClient, world: AuthzWorld, objects: dict[str, str], template: str
) -> None:
    h = headers(client, world, "ak03oth")
    assert client.get(template.format(**objects), headers=h).status_code == 404


PORTAL_CASES: list[tuple[str, str, Any]] = [
    ("GET", "/api/v1/portal/handover/{pid}", None),
    ("PATCH", "/api/v1/portal/handover/{pid}", {"street": "Fremdweg"}),
    ("POST", "/api/v1/portal/handover/{pid}/complete", {}),
]


@pytest.mark.parametrize(("method", "template", "body"), PORTAL_CASES)
@pytest.mark.parametrize(("user", "key"), [("ak03pb", "handover"), ("ak03pa", "handover_other")])
def test_portal_user_without_grant_gets_404(
    client: TestClient,
    world: AuthzWorld,
    objects: dict[str, str],
    method: str,
    template: str,
    body: Any,
    user: str,
    key: str,
) -> None:
    h = headers(client, world, user)
    response = call(client, method, template.format(pid=objects[key]), h, body)
    assert response.status_code == 404, response.text


def test_portal_user_with_grant_reads_protocol(
    client: TestClient, world: AuthzWorld, objects: dict[str, str]
) -> None:
    h = headers(client, world, "ak03pa")
    listed = ok(client.get("/api/v1/portal/handover", headers=h), 200)
    assert [x["id"] for x in listed] == [objects["handover"]]


def test_objects_unchanged_for_owner_tenant(
    client: TestClient, world: AuthzWorld, objects: dict[str, str]
) -> None:
    # Runs after the parametrised denials (file order): nothing was changed or deleted.
    h = headers(client, world, "ak03adm")
    statement = ok(client.get(f"/api/v1/statements/{objects['statement']}", headers=h), 200)
    assert statement["status"] == "draft"
    assert statement.get("purpose") in (None, "")
    owner = ok(client.get(O.format(**objects), headers=h), 200)
    assert owner["status"] == "draft"
    conn = ok(client.get(f"{M}/connections/{objects['connection']}", headers=h), 200)
    assert conn["display_name"] == f"ista {RUN}"
    boxes = ok(client.get("/api/v1/mail/mailboxes", headers=h), 200)
    box = next(b for b in boxes if b["id"] == objects["mailbox"])
    assert box["enabled"] is False  # created disabled, foreign PATCH tried to enable
    playbooks = ok(client.get("/api/v1/mail/playbooks", headers=h), 200)
    assert next(p for p in playbooks if p["id"] == objects["playbook"])["title"] == f"Heizung {RUN}"
    calls = ok(client.get("/api/v1/communication/calls", headers=h), 200)
    assert next(x for x in calls if x["id"] == objects["call"]).get("note") in (None, "")
