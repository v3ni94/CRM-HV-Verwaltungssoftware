"""M27-01 to M27-03 market readiness (Produktschutz). Expected values: the pricing structure
starts with 10 rows and no amount (complete = False); G5 stays closed while any of the 8
evidence items is open and while the approver is not the superadmin; onboarding creates a
tenant whose administrator sees only that tenant's data (RLS); the export ZIP holds only the
exported tenant's rows and needs a second platform administrator."""

import asyncio
import io
import json
import uuid
import zipfile
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
P = "/api/v1/platform"
BUCKET = "mhvp-market-readiness"


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"mr-{RUN}", name=f"Markt {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, admin in [("mrktadmin", False), ("mrpadmin", True), ("mrpadmin2", True)]:
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=admin,
            )
            world.users[name] = uid
            if not admin:
                await services.add_member(
                    factory,
                    tenant_id=a,
                    user_id=uid,
                    role_codes=["tenant_admin"],
                    actor_user_id=None,
                )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_pricing_structure_without_amounts_and_offer_draft(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "mrktadmin"))
    ph = bearer(login(client, world, "mrpadmin"))
    assert client.get(f"{P}/pricing", headers=h).status_code == 403
    pricing = _ok(client.get(f"{P}/pricing", headers=ph))
    assert pricing["complete"] is False
    assert len(pricing["items"]) >= 10
    assert all(i["amount"] is None for i in pricing["items"] if i["code"].startswith("tier_"))
    assert {i["kind"] for i in pricing["items"]} == {"tier", "module", "trial"}
    tier = next(i for i in pricing["items"] if i["code"] == "tier_s")
    patched = _ok(
        client.patch(f"{P}/pricing/items/{tier['id']}", json={"amount": "1.25"}, headers=ph)
    )
    assert patched["amount"] == "1.25"
    assert patched["amount_missing"] is False
    assert (
        client.patch(
            f"{P}/pricing/items/{tier['id']}", json={"min_units": 5, "max_units": 2}, headers=ph
        ).status_code
        == 422
    )
    cleared = _ok(
        client.patch(f"{P}/pricing/items/{tier['id']}", json={"clear_amount": True}, headers=ph)
    )
    assert cleared["amount"] is None
    assert (
        client.post(
            f"{P}/pricing/items",
            json={"kind": "module", "code": "module_hoa", "label": "Doppelt"},
            headers=ph,
        ).status_code
        == 409
    )
    pdf = client.get(
        f"{P}/pricing/offer.pdf", params={"customer_name": "Test GmbH", "units": 120}, headers=ph
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")
    assert client.get(f"{P}/pricing/offer.pdf", headers=h).status_code == 403


def _upload(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("nachweis.txt", b"Nachweis " + RUN.encode(), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_g5_stays_closed_until_evidence_complete_and_superadmin(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "mrktadmin"))
    ph = bearer(login(client, world, "mrpadmin"))
    ph2 = bearer(login(client, world, "mrpadmin2"))
    tenant = str(world.tenant_a)
    listing = _ok(client.get(f"{P}/tenants/{tenant}/g5-evidence", headers=ph))
    assert len(listing["items"]) == 8
    assert listing["complete"] is False
    assert listing["gate_open"] is False
    assert client.get(f"{P}/tenants/{tenant}/g5-evidence", headers=h).status_code == 403

    req = _ok(
        client.post(
            "/api/v1/tenant/release-gates/requests",
            json={"gate": "G5", "scope": "Drittmandant Pilot", "evidence": "Nachweisliste"},
            headers=h,
        ),
        201,
    )
    approve = f"{P}/tenants/{tenant}/release-gates/requests/{req['id']}/approve"
    blocked = client.post(approve, json={"comment": "zu früh"}, headers=ph)
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "MHVP-GATE-0005"
    assert "pentest_report" in blocked.json()["detail"]

    # "done" needs a document of the tenant; a foreign or missing document is rejected.
    assert (
        client.put(
            f"{P}/tenants/{tenant}/g5-evidence/pentest_report",
            json={"status": "done"},
            headers=ph,
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{P}/tenants/{tenant}/g5-evidence/pentest_report",
            json={"status": "done", "document_id": str(uuid.uuid4())},
            headers=ph,
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{P}/tenants/{tenant}/g5-evidence/unknown", json={"status": "open"}, headers=ph
        ).status_code
        == 404
    )
    doc = _upload(client, h)
    for item in listing["items"]:
        row = _ok(
            client.put(
                f"{P}/tenants/{tenant}/g5-evidence/{item['code']}",
                json={"status": "done", "document_id": doc, "note": "abgelegt"},
                headers=ph,
            )
        )
        assert row["done"] is True
        assert row["document_id"] == doc
    complete = _ok(client.get(f"{P}/tenants/{tenant}/g5-evidence", headers=ph))
    assert complete["complete"] is True
    assert complete["gate_open"] is False
    ready = _ok(client.get(f"{P}/tenants/{tenant}/readiness", headers=ph))
    assert ready["g5_ready"] is True
    assert ready["gates"]["G5"] is False
    assert all(e["done"] for e in ready["g5_evidence"])

    # Complete list, but the approver is not the superadmin: still closed.
    not_super = client.post(approve, json={"comment": "ohne Superadmin"}, headers=ph)
    assert not_super.status_code == 409
    assert not_super.json()["code"] == "MHVP-GATE-0005"
    state = {
        g["gate"]: g["open"] for g in _ok(client.get("/api/v1/tenant/release-gates", headers=h))
    }
    assert state["G5"] is False

    _ok(client.put(f"{P}/users/{world.users['mrpadmin2']}/superadmin", headers=ph))
    try:
        ph2 = bearer(login(client, world, "mrpadmin2"))
        opened = _ok(client.post(approve, json={"comment": "freigegeben"}, headers=ph2))
        assert opened["status"] == "approved"
        assert opened["four_eyes"] is True
        after = _ok(client.get(f"{P}/tenants/{tenant}/g5-evidence", headers=ph))
        assert after["gate_open"] is True
        # Reopening one item does not close the gate by itself: revocation is the gate path.
        _ok(
            client.put(
                f"{P}/tenants/{tenant}/g5-evidence/restore_drill",
                json={"status": "open"},
                headers=ph,
            )
        )
        _ok(
            client.post(
                f"/api/v1/tenant/release-gates/requests/{req['id']}/revoke",
                json={"comment": "Pilot beendet"},
                headers=h,
            )
        )
        assert (
            _ok(client.get(f"{P}/tenants/{tenant}/g5-evidence", headers=ph))["gate_open"] is False
        )
    finally:
        client.delete(f"{P}/users/{world.users['mrpadmin2']}/superadmin", headers=ph)


def test_onboarding_creates_isolated_tenant_and_export_needs_four_eyes(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "mrktadmin"))
    ph = bearer(login(client, world, "mrpadmin"))
    ph2 = bearer(login(client, world, "mrpadmin2"))
    # Data of the existing tenant that must never leak into the new one.
    _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "772", "name": "Fremdhaus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    admin_email = world.email("neuadmin")
    body = {
        "slug": f"dritt-{RUN}",
        "name": f"Dritte Hausverwaltung {RUN}",
        "company": {"name": f"Dritte Hausverwaltung {RUN} GmbH", "city": "Musterstadt"},
        "branding": {"primary_color": "#123456"},
        "legal_entities": [
            {"kind": "manager", "name": "Dritte Hausverwaltung GmbH"},
            {"kind": "rental_owner", "name": "Eigentümer Muster"},
        ],
        "admin": {"email": admin_email, "display_name": "Neu Admin", "password": PASSWORD},
    }
    assert client.post(f"{P}/onboarding", json=body, headers=h).status_code == 403
    result = _ok(client.post(f"{P}/onboarding", json=body, headers=ph), 201)
    assert len(result["legal_entities"]) == 2
    assert result["feature_flags"] == {"auto_posting_enabled": False}
    assert all(v is False for v in result["gates"].values())
    assert result["welcome_email"]["status"] == "draft"
    assert result["welcome_email"]["to"] == admin_email.lower()
    assert client.post(f"{P}/onboarding", json=body, headers=ph).status_code == 409
    assert (
        client.post(
            f"{P}/onboarding",
            json=body | {"slug": f"hoa-{RUN}", "legal_entities": [{"kind": "hoa", "name": "x"}]},
            headers=ph,
        ).status_code
        == 422
    )
    new_tenant = result["tenant_id"]

    # The new administrator lands in the new tenant and sees none of the old tenant's data.
    world.users["neuadmin"] = uuid.UUID(result["admin"]["user_id"])
    session = login(client, world, "neuadmin")
    assert session["tenant_id"] == new_tenant
    nh = bearer(session)
    props = _ok(client.get("/api/v1/properties", headers=nh))
    items = props["items"] if isinstance(props, dict) else props
    assert items == []
    settings = _ok(client.get("/api/v1/tenant/settings", headers=nh))
    assert settings["branding"]["primary_color"] == "#123456"
    roles = {r["code"] for r in _ok(client.get("/api/v1/tenant/roles", headers=nh))}
    assert "tenant_admin" in roles

    # Export: request, four eyes, download only after approval, only own tenant in the ZIP.
    req = _ok(
        client.post(
            f"{P}/tenants/{new_tenant}/export-requests",
            json={"purpose": "portability", "comment": "Anfrage"},
            headers=ph,
        ),
        201,
    )
    base = f"{P}/tenants/{new_tenant}/export-requests/{req['id']}"
    assert client.get(f"{base}/download", headers=ph).status_code == 409
    same = client.post(f"{base}/approve", json={}, headers=ph)
    assert same.status_code == 403
    assert same.json()["code"] == "MHVP-GATE-0002"
    approved = _ok(client.post(f"{base}/approve", json={"comment": "ok"}, headers=ph2))
    assert approved["status"] == "approved"
    assert client.post(f"{base}/approve", json={}, headers=ph2).status_code == 409
    download = client.get(f"{base}/download", headers=ph)
    assert download.status_code == 200, download.text
    assert download.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(download.content))
    names = set(archive.namelist())
    assert {"manifest.json", "tenant.json", "legal_entities.json", "properties.json"} <= names
    entities = json.loads(archive.read("legal_entities.json"))
    assert {e["tenant_id"] for e in entities} == {new_tenant}
    assert len(entities) == 2
    assert json.loads(archive.read("properties.json")) == []
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["purpose"] == "portability"
    assert manifest["status"] == "draft"
    memberships = json.loads(archive.read("memberships.json"))
    assert {m["tenant_id"] for m in memberships} == {new_tenant}
    listed = _ok(client.get(f"{P}/tenants/{new_tenant}/export-requests", headers=ph))
    assert listed[0]["downloads"] == 1
    assert client.get(f"{base}/download", headers=h).status_code == 403
