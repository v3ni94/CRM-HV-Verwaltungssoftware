"""Sicherheitsreview 1.22 (docs/reviews/2026-09-26-sicherheitsreview-1.22.md), Befunde 3, 4, 5
und 7: accounting rights for the reconciliation reports, the legal entity scope of a tax advisor
in the WEG finance and inspection endpoints, and the community binding of owner payments.
Second pass: Befunde 5 (board, majority rules), 10 (notice attachment visibility), 11 to 13
(webhook secret, DNS pinning, dry run without resolution), 14 and 15 (inspection package size
and retrieval status), 18 (telephony answer), 20 (intake uuid parsing) and 21 (majority rule
community)."""

import asyncio
import json
import socket
import time
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from sqlalchemy import create_engine, text

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_a70_telephony import _deliver, _event
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m18_tax_advisor_scope import assign_ledger_scope
from tests.integration.test_m24_hoa import _hoa_ledger, _ok, _owner

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"
R = "/api/v1/imports/reconciliation-reports"
BUCKET = "mhvp-review-1-22"


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
    )


def _grant(world: World, role_code: str, grants: list[tuple[str, str]]) -> None:
    """Test helper: extra rights on a system role of tenant A directly in the role table
    (same pattern as test_m18_tax_advisor_scope)."""
    engine = create_engine(world.app_url)
    with engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
        )
        role_id = conn.execute(
            text("SELECT id FROM role WHERE tenant_id = :t AND code = :c"),
            {"t": str(world.tenant_a), "c": role_code},
        ).scalar_one()
        for resource, action in grants:
            conn.execute(
                text(
                    "INSERT INTO role_permission (id, tenant_id, role_id, resource, action) "
                    "VALUES (:id, :t, :r, :res, :act) ON CONFLICT DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "t": str(world.tenant_a),
                    "r": role_id,
                    "res": resource,
                    "act": action,
                },
            )
    engine.dispose()


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"r22-{RUN}", name=f"R22 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"r22b-{RUN}", name=f"R22B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("r22admin", a, "tenant_admin"),
            ("r22tax", a, "tax_advisor"),
            ("r22ai", a, "caretaker"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    built = asyncio.run(_world(_settings(database, redis_url)))
    # The tax advisor gets the inspection rights, the caretaker only AI rights: neither role
    # carries accounting:read by itself, only the tax advisor does through its system role.
    _grant(built, "tax_advisor", [("hoa", "read"), ("hoa", "update")])
    # The caretaker additionally gets hoa:read only (retrieval of a package without hoa:update).
    _grant(built, "caretaker", [("ai", "read"), ("ai", "create"), ("hoa", "read")])
    return built


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


def _contact(client: TestClient, h: dict[str, str], name: str) -> str:
    return str(
        _ok(
            client.post(
                "/api/v1/contacts",
                json={"kind": "person", "first_name": "Antrag", "last_name": f"{name}{RUN}"},
                headers=h,
            ),
            201,
        )["id"]
    )


def _loan(client: TestClient, h: dict[str, str], ledger: str) -> str:
    return str(
        _ok(
            client.post(
                f"{H}/loans",
                json={
                    "ledger_id": ledger,
                    "lender": "Sparkasse",
                    "principal": "10000.00",
                    "interest_rate_percent": "3.5",
                    "start_date": "2025-01-01",
                    "purpose": "Dachsanierung",
                },
                headers=h,
            ),
            201,
        )["id"]
    )


def _claim(client: TestClient, h: dict[str, str], ledger: str) -> str:
    return str(
        _ok(
            client.post(
                f"{H}/insurance-claims",
                json={"ledger_id": ledger, "title": "Wasserschaden", "damage_date": "2025-03-02"},
                headers=h,
            ),
            201,
        )["id"]
    )


def _measure(client: TestClient, h: dict[str, str], ledger: str) -> str:
    return str(
        _ok(
            client.post(
                f"{H}/measures",
                json={"ledger_id": ledger, "title": "Fassade", "cost_frame": "5000.00"},
                headers=h,
            ),
            201,
        )["id"]
    )


def _inspection(client: TestClient, h: dict[str, str], hoa: str, contact: str) -> str:
    return str(
        _ok(
            client.post(
                f"{H}/inspection-requests",
                json={
                    "legal_entity_id": hoa,
                    "applicant_contact_id": contact,
                    "requested_on": "2026-09-01",
                    "scope_kinds": ["statement"],
                },
                headers=h,
            ),
            201,
        )["id"]
    )


def test_reconciliation_reports_need_accounting_rights(client: TestClient, world: World) -> None:
    """Befund 3: AI rights alone open no financial comparison; accounting:read does."""
    ai = bearer(login(client, world, "r22ai"))
    assert client.get(R, headers=ai).status_code == 403
    assert client.get(f"{R}/columns", headers=ai).status_code == 403
    assert client.post(R, json={}, headers=ai).status_code == 403
    tax = bearer(login(client, world, "r22tax"))
    assert _ok(client.get(R, headers=tax)) == []
    assert client.post(R, json={}, headers=tax).status_code == 403  # no accounting:create


def test_tax_advisor_scope_limits_hoa_finance_and_inspection(
    client: TestClient, world: World
) -> None:
    """Befunde 4 und 5 (A37): a tax advisor assigned to community 1 sees loans, claims,
    measures and inspection requests of community 1 only; community 2 answers 404 or an empty
    list, and a new request for community 2 is refused as not found."""
    h = bearer(login(client, world, "r22admin"))
    w1, w2 = _hoa_ledger(client, h, "921"), _hoa_ledger(client, h, "922")
    applicant = _contact(client, h, "Scope")
    rows = {
        "loans": (_loan(client, h, w1["ledger"]), _loan(client, h, w2["ledger"])),
        "insurance-claims": (_claim(client, h, w1["ledger"]), _claim(client, h, w2["ledger"])),
        "measures": (_measure(client, h, w1["ledger"]), _measure(client, h, w2["ledger"])),
    }
    req1 = _inspection(client, h, w1["hoa"], applicant)
    req2 = _inspection(client, h, w2["hoa"], applicant)
    assign_ledger_scope(client, h, world.users["r22tax"], w1["ledger"])
    tax = bearer(login(client, world, "r22tax"))

    for path, (own, foreign) in rows.items():
        listed_own = _ok(
            client.get(f"{H}/{path}", params={"legal_entity_id": w1["hoa"]}, headers=tax)
        )
        assert [r["id"] for r in listed_own] == [own], path
        assert (
            _ok(client.get(f"{H}/{path}", params={"legal_entity_id": w2["hoa"]}, headers=tax)) == []
        )
        assert client.get(f"{H}/{path}/{own}", headers=tax).status_code == 200, path
        assert client.get(f"{H}/{path}/{foreign}", headers=tax).status_code == 404, path
        # The administrator (unscoped) still sees both.
        assert client.get(f"{H}/{path}/{foreign}", headers=h).status_code == 200, path

    listed = _ok(client.get(f"{H}/inspection-requests", headers=tax))
    assert [r["id"] for r in listed] == [req1]
    assert client.get(f"{H}/inspection-requests/{req1}", headers=tax).status_code == 200
    assert client.get(f"{H}/inspection-requests/{req2}", headers=tax).status_code == 404
    assert client.get(f"{H}/inspection-requests/{req2}/candidates", headers=tax).status_code == 404
    refused = client.post(
        f"{H}/inspection-requests",
        json={
            "legal_entity_id": w2["hoa"],
            "applicant_contact_id": applicant,
            "requested_on": "2026-09-02",
            "scope_kinds": ["receipts"],
        },
        headers=tax,
    )
    assert refused.status_code == 404, refused.text
    assert len(_ok(client.get(f"{H}/inspection-requests", headers=h))) == 2


def test_owner_payment_needs_contract_of_the_same_community(
    client: TestClient, world: World
) -> None:
    """Befund 7 (6.9.1): a payment to an owner is bound to an ownership contract of the
    community of the claim; a contract of another community is refused with 422."""
    h = bearer(login(client, world, "r22admin"))
    w1, w2 = _hoa_ledger(client, h, "923"), _hoa_ledger(client, h, "924")
    _, own = _owner(client, h, w1["property"], "01", "1000", w1["keys"]["MEA"], {})
    _, other = _owner(client, h, w2["property"], "01", "1000", w2["keys"]["MEA"], {})
    claim = _claim(client, h, w1["ledger"])
    item = {"kind": "owner_payment", "booking_date": "2025-05-15", "amount": "150.00"}
    foreign = client.post(
        f"{H}/insurance-claims/{claim}/items",
        json=item | {"contract_id": other["id"]},
        headers=h,
    )
    assert foreign.status_code == 422, foreign.text
    assert "Gemeinschaft" in foreign.json()["detail"]
    _ok(
        client.post(
            f"{H}/insurance-claims/{claim}/items",
            json=item | {"contract_id": own["id"]},
            headers=h,
        ),
        201,
    )


# --- second pass ---------------------------------------------------------------------------


def _upload(
    client: TestClient,
    h: dict[str, str],
    name: str,
    data: bytes,
    entity_type: str,
    entity_id: str,
    visibility: list[str] | None,
) -> str:
    links = json.dumps([{"entity_type": entity_type, "entity_id": entity_id}])
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": (name, data, "application/pdf")},
            data={"links": links},
            headers=h,
        ),
        201,
    )
    if visibility is not None:
        _ok(
            client.patch(
                f"/api/v1/documents/{doc['id']}", json={"visibility": visibility}, headers=h
            )
        )
    return str(doc["id"])


def _audit(client: TestClient, h: dict[str, str], hoa: str, contact: str) -> str:
    return str(
        _ok(
            client.post(
                f"{H}/audits",
                json={
                    "legal_entity_id": hoa,
                    "period_from": "2025-01-01",
                    "period_to": "2025-12-31",
                    "purpose": "Stichprobe (Review 1.22)",
                    "auditor_contact_ids": [contact],
                },
                headers=h,
            ),
            201,
        )["id"]
    )


def test_tax_advisor_scope_limits_board_and_majority_rules(
    client: TestClient, world: World
) -> None:
    """Befund 5 (A37) in hoa/board.py and hoa/majority.py: engagements, candidates, reports and
    board sections of a foreign community answer 404 or an empty list; community rules of a
    foreign community are not listed."""
    h = bearer(login(client, world, "r22admin"))
    w1, w2 = _hoa_ledger(client, h, "925"), _hoa_ledger(client, h, "926")
    board = _contact(client, h, "Beirat")
    eng1, eng2 = _audit(client, h, w1["hoa"], board), _audit(client, h, w2["hoa"], board)
    rule2 = _ok(
        client.post(
            f"{H}/majority-rules/subject-rules",
            json={
                "subject_kind": "maintenance",
                "majority_type": "qualified_2_3",
                "counting_basis": "heads",
                "source": "Teilungserklärung § 9 (Testannahme)",
                "legal_entity_id": w2["hoa"],
            },
            headers=h,
        ),
        201,
    )
    assign_ledger_scope(client, h, world.users["r22tax"], w1["ledger"])
    tax = bearer(login(client, world, "r22tax"))

    own = _ok(client.get(f"{H}/audits", params={"legal_entity_id": w1["hoa"]}, headers=tax))
    assert [e["id"] for e in own] == [eng1]
    assert _ok(client.get(f"{H}/audits", params={"legal_entity_id": w2["hoa"]}, headers=tax)) == []
    for path in (
        f"{H}/audit-engagements/{eng2}/board",
        f"{H}/audits/{eng2}/candidates",
        f"{H}/audits/{eng2}/reports",
    ):
        assert client.get(path, headers=tax).status_code == 404, path
        assert client.get(path, headers=h).status_code == 200, path
    assert client.get(f"{H}/audit-engagements/{eng1}/board", headers=tax).status_code == 200
    assert client.post(
        f"{H}/audit-engagements/{eng2}/board-access",
        json={"contact_id": board},
        headers=tax,
    ).status_code in (403, 404)

    listed = _ok(client.get(f"{H}/majority-rules/subject-rules", headers=tax))
    assert rule2["id"] not in {r["id"] for r in listed}
    assert rule2["id"] in {
        r["id"] for r in _ok(client.get(f"{H}/majority-rules/subject-rules", headers=h))
    }


def test_majority_rule_needs_a_community_of_the_tenant(client: TestClient, world: World) -> None:
    """Befund 21: a community override names a GdWE; a rental owner entity is refused with 422,
    an unknown id as well."""
    h = bearer(login(client, world, "r22admin"))
    rental = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "927", "name": "Miethaus 927", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(client, h, "Vermieter927", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{rental['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    entities = _ok(client.get(f"/api/v1/properties/{rental['id']}", headers=h))["legal_entities"]
    rental_owner = next(e["id"] for e in entities if e["kind"] == "rental_owner")
    body = {
        "subject_kind": "economic_plan",
        "majority_type": "simple",
        "counting_basis": "heads",
        "source": "Teilungserklärung § 3 (Testannahme)",
    }
    for entity in (rental_owner, str(uuid.uuid4())):
        refused = client.post(
            f"{H}/majority-rules/subject-rules",
            json=body | {"legal_entity_id": entity},
            headers=h,
        )
        assert refused.status_code == 422, refused.text
        assert "GdWE" in refused.json()["detail"]
    hoa = _hoa_ledger(client, h, "928")["hoa"]
    _ok(
        client.post(
            f"{H}/majority-rules/subject-rules",
            json=body | {"legal_entity_id": hoa},
            headers=h,
        ),
        201,
    )


def test_notice_attachment_must_be_visible_to_the_audience(
    client: TestClient, world: World
) -> None:
    """Befund 10 (6.9.6): a notice for all needs a document released for tenants and owners;
    a tenant only document fits a tenant notice, and widening the audience by patch is refused
    as long as the attachment stays."""
    h = bearer(login(client, world, "r22admin"))
    prop = _hoa_ledger(client, h, "929")["property"]
    tenant_only = _upload(client, h, "hausordnung.pdf", b"%PDF-1.4 h", "property", prop, ["tenant"])
    both = _upload(client, h, "info.pdf", b"%PDF-1.4 i", "property", prop, ["tenant", "owner"])
    base = {"title": "Aushang", "body": "Text", "valid_from": "2026-09-01"}
    refused = client.post(
        f"/api/v1/properties/{prop}/notices",
        json=base | {"audience": "all", "document_id": tenant_only},
        headers=h,
    )
    assert refused.status_code == 422, refused.text
    assert "Eigentümer" in refused.json()["detail"]
    assert (
        client.post(
            f"/api/v1/properties/{prop}/notices",
            json=base | {"audience": "owner", "document_id": tenant_only},
            headers=h,
        ).status_code
        == 422
    )
    notice = _ok(
        client.post(
            f"/api/v1/properties/{prop}/notices",
            json=base | {"audience": "tenant", "document_id": tenant_only},
            headers=h,
        ),
        201,
    )
    widened = client.patch(f"/api/v1/notices/{notice['id']}", json={"audience": "all"}, headers=h)
    assert widened.status_code == 422, widened.text
    assert (
        client.patch(
            f"/api/v1/notices/{notice['id']}",
            json={"audience": "all", "document_id": both},
            headers=h,
        ).status_code
        == 200
    )
    _ok(
        client.post(
            f"/api/v1/properties/{prop}/notices",
            json=base | {"audience": "all", "document_id": both},
            headers=h,
        ),
        201,
    )


def test_webhook_secret_enc_is_refused_from_the_client(client: TestClient, world: World) -> None:
    """Befund 11: the stored ciphertext is never accepted as input; the plaintext secret is."""
    h = bearer(login(client, world, "r22admin"))
    action = {"type": "webhook", "url": "https://hooks.example.invalid/mhvp"}
    body = {"name": f"Webhook {RUN}", "trigger_event_type": "ticket.created", "actions": []}
    refused = client.post(
        "/api/v1/automation/rules",
        json=body | {"actions": [action | {"secret_enc": "AAAA"}]},
        headers=h,
    )
    assert refused.status_code == 422, refused.text
    rule = _ok(
        client.post(
            "/api/v1/automation/rules",
            json=body | {"actions": [action | {"secret": "webhook-secret-0123456789"}]},
            headers=h,
        ),
        201,
    )
    assert rule["actions"][0] == {
        "type": "webhook",
        "url": action["url"],
        "extra": {},
        "has_secret": True,
    }
    assert (
        client.patch(
            f"/api/v1/automation/rules/{rule['id']}",
            json={"actions": [action | {"secret_enc": "AAAA"}]},
            headers=h,
        ).status_code
        == 422
    )
    # Befund 13: the dry run does not resolve the host name (the .invalid TLD never resolves).
    dry = _ok(
        client.post(
            f"/api/v1/automation/rules/{rule['id']}/test",
            json={"type": "ticket.created", "entity": {"category": "x"}},
            headers=h,
        )
    )
    assert dry["error"] is None, dry
    assert dry["actions"][0]["ok"] is True
    assert client.delete(f"/api/v1/automation/rules/{rule['id']}", headers=h).status_code == 204


def test_pinned_webhook_target_uses_the_checked_address(monkeypatch: pytest.MonkeyPatch) -> None:
    """Befund 12: the call goes to the address that passed the check, with the original host
    in the Host header and as TLS server name; a second resolution cannot redirect it. Befund
    13: ``resolve=False`` performs no DNS query."""
    from mhvp.core.webhooks import UnsafeWebhookTargetError, check_target, pin_target

    calls: list[str] = []

    def fake_getaddrinfo(host: str, port: int, *args: Any, **kwargs: Any) -> list[Any]:
        calls.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    target = pin_target("https://hooks.example.org:8443/x?y=1", allow_private=False)
    assert target.url == "https://93.184.216.34:8443/x?y=1"
    assert target.headers == {"Host": "hooks.example.org:8443"}
    assert target.extensions == {"sni_hostname": "hooks.example.org"}
    plain = pin_target("https://hooks.example.org/x", allow_private=False)
    assert plain.url == "https://93.184.216.34/x"
    assert plain.headers == {"Host": "hooks.example.org"}
    assert calls == ["hooks.example.org", "hooks.example.org"]
    # Private targets allowed (development): pass through, nothing pinned.
    local = pin_target("http://127.0.0.1:9/x", allow_private=True)
    assert (local.url, local.headers, local.extensions) == ("http://127.0.0.1:9/x", {}, {})
    check_target("https://free-name.example.org/x", allow_private=False, resolve=False)
    assert calls == ["hooks.example.org", "hooks.example.org"]
    with pytest.raises(UnsafeWebhookTargetError):
        check_target("http://free-name.example.org/x", allow_private=False, resolve=False)

    def private(host: str, port: int, *args: Any, **kwargs: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))]

    monkeypatch.setattr(socket, "getaddrinfo", private)
    with pytest.raises(UnsafeWebhookTargetError):
        pin_target("https://hooks.example.org/x", allow_private=False)


def test_inspection_package_size_cap_and_retrieval_without_update_right(
    client: TestClient, world: World
) -> None:
    """Befund 14: the package is refused before any blob is read when the indexed sizes exceed
    the document limit. Befund 15: a retrieval with hoa:read only is logged and leaves the
    status at provided; hoa:update moves it to retrieved."""
    h = bearer(login(client, world, "r22admin"))
    w = _hoa_ledger(client, h, "930")
    applicant = _contact(client, h, "Paket")
    rid = _inspection(client, h, w["hoa"], applicant)
    d1 = _upload(client, h, "a.pdf", b"%PDF-1.4 " + b"a" * 100, "legal_entity", w["hoa"], ["owner"])
    d2 = _upload(client, h, "b.pdf", b"%PDF-1.4 " + b"b" * 100, "legal_entity", w["hoa"], ["owner"])
    _ok(
        client.post(
            f"{H}/inspection-requests/{rid}/transition", json={"status": "released"}, headers=h
        )
    )
    settings = client.app.state.settings  # type: ignore[attr-defined]
    client.app.state.settings = settings.model_copy(update={"document_max_bytes": 150})  # type: ignore[attr-defined]
    try:
        refused = client.post(
            f"{H}/inspection-requests/{rid}/package", json={"document_ids": [d1, d2]}, headers=h
        )
        assert refused.status_code == 422, refused.text
        assert "Paket zu groß" in refused.json()["detail"]
        assert (
            _ok(client.get(f"{H}/inspection-requests/{rid}", headers=h))["package_document_id"]
            is None
        )
    finally:
        client.app.state.settings = settings  # type: ignore[attr-defined]
    _ok(
        client.post(
            f"{H}/inspection-requests/{rid}/package", json={"document_ids": [d1, d2]}, headers=h
        )
    )
    _ok(
        client.post(
            f"{H}/inspection-requests/{rid}/transition",
            json={"status": "provided", "delivery_kind": "data_medium"},
            headers=h,
        )
    )
    reader = bearer(login(client, world, "r22ai"))  # hoa:read only
    assert client.get(f"{H}/inspection-requests/{rid}/package", headers=reader).status_code == 200
    detail = _ok(client.get(f"{H}/inspection-requests/{rid}", headers=h))
    assert detail["status"] == "provided"
    assert [(e["kind"], e["to_status"]) for e in detail["events"]][-1] == ("retrieval", None)
    assert client.get(f"{H}/inspection-requests/{rid}/package", headers=h).status_code == 200
    detail = _ok(client.get(f"{H}/inspection-requests/{rid}", headers=h))
    assert detail["status"] == "retrieved"
    assert [(e["kind"], e["to_status"]) for e in detail["events"]][-1] == ("retrieval", "retrieved")


def test_telephony_webhook_answer_carries_no_match(client: TestClient, world: World) -> None:
    """Befund 18: the telephone system learns only that the event was recorded."""
    h = bearer(login(client, world, "r22admin"))
    secret = "a-very-long-telephony-secret-for-review-1-22"
    _ok(
        client.put(
            "/api/v1/communication/telephony/settings",
            json={"enabled": True, "provider_label": "Testanlage", "webhook_secret": secret},
            headers=h,
        )
    )
    number = "+4921100000122"
    _contact_with_phone = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Tel",
                "last_name": f"Review{RUN}",
                "phones": [{"label": "mobile", "number": number, "is_primary": True}],
            },
            headers=h,
        ),
        201,
    )
    out = _ok(
        _deliver(
            client,
            f"r22-{RUN}",
            secret,
            _event("call.started", number, f"r22-{RUN}-{int(time.time())}"),
        )
    )
    assert set(out) == {"status", "call_id"}
    assert out["status"] == "recorded"
    calls = _ok(client.get("/api/v1/communication/calls", headers=h))
    row = next(r for r in calls if r["id"] == out["call_id"])
    assert row["contact_id"] == _contact_with_phone["id"]


def test_intake_pick_rejects_invalid_proposed_uuid() -> None:
    """Befund 20: a broken proposal value ends with a validation error, not a 500."""
    from mhvp.documents.intake_routers import IntakeAcceptIn, _pick

    assert _pick(IntakeAcceptIn(), "property_id", {"property_id": None}) is None
    good = uuid.uuid4()
    assert _pick(IntakeAcceptIn(), "property_id", {"property_id": str(good)}) == good
    with pytest.raises(ProblemError) as info:
        _pick(IntakeAcceptIn(), "property_id", {"property_id": "kaputt"})
    assert info.value.error is ErrorCodes.VALIDATION
