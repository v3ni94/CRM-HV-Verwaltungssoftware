"""AA14 (GA11-05, GA03-05): one access path protocol for portal users. Every path (list and
detail API, direct download, bundle, search, tenant export, privacy and CRM documents API, AI
retrieval scope and AI input) shows only documents released for the person, also when the
release comes from a document class grant (6.9.6).

Expected values by hand (synthetic): a board grant on the class "abrechnungsbeleg" of one
legal entity releases exactly the one document with that class, that entity link and the
visibility "board"; a document of another class, one without board visibility and one of
another entity stay hidden on every path."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import text

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _doc, _ok, _portal_user
from tests.integration.test_m21_read_receipts import _db

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"
CLASS = "abrechnungsbeleg"
OTHER_CLASS = "mietvertrag"


async def _world_aa14(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services
    from tests.integration.test_m2_platform import RUN

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"aa14a-{RUN}", name=f"AA14 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aa14b-{RUN}", name=f"AA14 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("aa14admin", a), ("aa14adminb", b)):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=["tenant_admin"],
                actor_user_id=None,
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world_aa14(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _hoa(client: TestClient, ha: dict[str, str], number: str) -> str:
    weg = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"AA14-WEG {number}", "management_type": "hoa"},
            headers=ha,
        ),
        201,
    )
    return str(next(e["id"] for e in weg["legal_entities"] if e["kind"] == "hoa"))


def test_document_class_grant_and_all_access_paths(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from mhvp.documents.models import Document, RetentionProfile, RetentionStart, TextStatus

    ha = bearer(login(client, world, "aa14admin"))
    hb = bearer(login(client, world, "aa14adminb"))
    hoa, other_hoa = _hoa(client, ha, "941"), _hoa(client, ha, "942")
    d_ok = _doc(client, ha, "Beleg frei", "legal_entity", hoa, ["board"])
    d_class = _doc(client, ha, "Vertrag anderer Klasse", "legal_entity", hoa, ["board"])
    d_vis = _doc(client, ha, "Beleg nur Eigentuemer", "legal_entity", hoa, ["owner"])
    d_entity = _doc(client, ha, "Beleg anderer Entitaet", "legal_entity", other_hoa, ["board"])

    async def prepare(s: Any) -> None:
        profiles = {}
        for cls in (CLASS, OTHER_CLASS):
            row = RetentionProfile(
                tenant_id=world.tenant_a,
                document_class=cls,
                legal_basis="Testwert, synthetisch",
                retention_years=10,
                start_rule=RetentionStart.END_OF_YEAR_CREATED,
            )
            s.add(row)
            profiles[cls] = row
        await s.flush()
        for doc_id, cls in (
            (d_ok, CLASS),
            (d_class, OTHER_CLASS),
            (d_vis, CLASS),
            (d_entity, CLASS),
        ):
            doc = await s.get(Document, uuid.UUID(doc_id))
            doc.retention_profile_id = profiles[cls].id
            doc.ocr_text = "Abrechnung Heizkosten Beleg"
            doc.text_status = TextStatus.EXTRACTED

    _db(database, redis_url, world, prepare)

    _, guest = _party(client, ha, "AA14Beirat")
    portal = _portal_user(client, ha, world, "aa14beirat", str(guest["id"]))
    account = _ok(client.get(f"{PA}/accounts", params={"contact_id": guest["id"]}, headers=ha))[0]
    acc = account["id"]

    def paths(headers: dict[str, str], visible: set[str], hidden: set[str]) -> None:
        listed = {d["id"] for d in _ok(client.get(f"{P}/documents", headers=headers))}
        assert listed == visible
        searched = {
            d["id"]
            for d in _ok(client.get(f"{P}/documents", params={"q": "Beleg"}, headers=headers))
        }
        assert searched <= visible
        for doc in hidden:  # API detail and direct download
            assert client.get(f"{P}/documents/{doc}", headers=headers).status_code == 404
            assert client.get(f"{P}/documents/{doc}/download", headers=headers).status_code == 404
            bundle = client.post(
                f"{P}/documents/bundle", json={"document_ids": [doc]}, headers=headers
            )
            assert bundle.status_code == 404
        for doc in visible:
            assert client.get(f"{P}/documents/{doc}", headers=headers).status_code == 200
            assert client.get(f"{P}/documents/{doc}/download", headers=headers).status_code == 200
            bundle = client.post(
                f"{P}/documents/bundle", json={"document_ids": [doc]}, headers=headers
            )
            assert bundle.status_code == 200
        # Export and CRM paths are no portal paths: a portal user has no permission there.
        assert client.post("/api/v1/tenant/export-jobs", headers=headers).status_code == 403
        assert client.get("/api/v1/documents", headers=headers).status_code == 403
        assert client.get("/api/v1/privacy/register", headers=headers).status_code == 403

    # Before the grant nothing is released on any path.
    paths(portal, set(), {d_ok, d_class, d_vis, d_entity})
    assert _scope(database, redis_url, world, acc) == set()

    # Validation, authorization and tenant separation of the grant endpoint.
    url = f"{PA}/accounts/{acc}/document-class-grants"
    good = {"legal_entity_id": hoa, "document_class": CLASS, "role": "board"}
    assert (
        client.post(url, json={**good, "document_class": "erfunden"}, headers=ha).status_code == 422
    )
    assert client.post(url, json={**good, "role": "chef"}, headers=ha).status_code == 422
    assert client.post(url, json={**good, "valid_to": "2000-01-01"}, headers=ha).status_code == 422
    assert client.post(url, json={**good, "x": 1}, headers=ha).status_code == 422
    assert (
        client.post(
            url, json={**good, "legal_entity_id": str(uuid.uuid4())}, headers=ha
        ).status_code
        == 404
    )
    assert client.post(url, json=good, headers=portal).status_code == 403
    assert client.post(url, json=good, headers=hb).status_code == 404
    assert client.get(url, headers=hb).status_code == 404
    created = _ok(client.post(url, json=good, headers=ha), 201)
    assert created["document_class"] == CLASS
    assert [g["id"] for g in _ok(client.get(url, headers=ha))] == [created["id"]]

    # After the grant exactly the one document is released, on every path.
    paths(portal, {d_ok}, {d_class, d_vis, d_entity})
    assert _scope(database, redis_url, world, acc) == {uuid.UUID(d_ok)}

    # A resync of the contract grants keeps the manual class grant.
    _ok(client.post(f"{PA}/accounts/{acc}/sync-grants", headers=ha))
    paths(portal, {d_ok}, {d_class, d_vis, d_entity})

    # An expired grant releases nothing.
    async def expire(s: Any) -> None:
        await s.execute(
            text(
                "UPDATE access_grant SET valid_from = :d, valid_to = :d "
                "WHERE scope_type = 'document_class'"
            ),
            {"d": date(2000, 1, 1)},
        )

    _db(database, redis_url, world, expire)
    paths(portal, set(), {d_ok, d_class, d_vis, d_entity})


def _scope(database: Database, redis_url: str, world: World, account_id: str) -> set[uuid.UUID]:
    """AI retrieval path (RAG): the scope that filters the retrieval and blocks attached
    documents of the run; checked together with the keyword retrieval and ``build_input``."""
    from mhvp.ai import gateway
    from mhvp.ai.models import AiTask, AiTaskRun
    from mhvp.portal.access import document_scope_for_user
    from mhvp.portal.models import PortalAccount
    from mhvp.workspace.services import local_today

    async def run(s: Any) -> set[uuid.UUID]:
        account = await s.get(PortalAccount, uuid.UUID(account_id))
        scope = await document_scope_for_user(s, account.user_id, local_today())
        assert scope is not None
        retrieved = await gateway.retrieve_keyword(s, "Abrechnung Heizkosten Beleg")
        assert len(retrieved) >= 4  # the tenant holds more than the person may see
        released = {d.id for d in retrieved if d.id in scope}
        assert released == scope & {d.id for d in retrieved}
        foreign = [d.id for d in retrieved if d.id not in scope]
        if foreign:
            ai_run = AiTaskRun(
                tenant_id=world.tenant_a,
                created_by=account.user_id,
                task=AiTask.ANSWER_QUESTION,
                input_ref={"document_ids": [str(foreign[0])], "instruction": "Frage"},
            )
            with pytest.raises(gateway.GatewayBlockedError):
                await gateway.build_input(s, None, ai_run)  # type: ignore[arg-type]
        return set(scope)

    return _db(database, redis_url, world, run)


def test_provider_framework_contracts_and_availability(client: TestClient, world: World) -> None:
    """GA11-04: a provider sees only its own contracts and windows, read only; creating needs
    the management permission, the other tenant sees nothing (404)."""
    ha = bearer(login(client, world, "aa14admin"))
    hb = bearer(login(client, world, "aa14adminb"))
    _, provider = _party(client, ha, "AA14Handwerker", kind="company")
    _, stranger = _party(client, ha, "AA14Fremd", kind="company")
    own = _portal_user(client, ha, world, "aa14prov", str(provider["id"]))
    foreign = _portal_user(client, ha, world, "aa14fremd", str(stranger["id"]))
    base = {
        "provider_contact_id": provider["id"],
        "title": "Winterdienst",
        "starts_at": "2026-01-01",
    }
    _ok(
        client.post(
            "/api/v1/service-contracts",
            json={**base, "notice_period_days": 3, "ends_at": "2030-12-31"},
            headers=ha,
        ),
        201,
    )
    admin = f"{PA}/provider-availability"
    window = {
        "provider_contact_id": provider["id"],
        "starts_at": "2099-01-05T07:00:00+01:00",
        "ends_at": "2099-01-05T15:00:00+01:00",
        "kind": "unavailable",
        "note": "Urlaub",
    }
    created = _ok(client.post(admin, json=window, headers=ha), 201)
    assert (
        client.post(admin, json={**window, "ends_at": window["starts_at"]}, headers=ha).status_code
        == 422
    )
    assert client.post(admin, json={**window, "kind": "x"}, headers=ha).status_code == 422
    assert (
        client.post(
            admin, json={**window, "starts_at": "2099-01-05T07:00:00"}, headers=ha
        ).status_code
        == 422
    )
    assert client.post(admin, json=window, headers=own).status_code == 403
    assert client.post(admin, json=window, headers=hb).status_code == 404
    assert _ok(client.get(admin, headers=hb)) == []

    contracts = _ok(client.get(f"{P}/provider/framework-contracts", headers=own))
    assert [c["title"] for c in contracts] == ["Winterdienst"]
    assert contracts[0]["active"] is True
    assert "notes" not in contracts[0]
    windows = _ok(client.get(f"{P}/provider/availability", headers=own))
    assert [w["id"] for w in windows] == [created["id"]]
    assert _ok(client.get(f"{P}/provider/framework-contracts", headers=foreign)) == []
    assert _ok(client.get(f"{P}/provider/availability", headers=foreign)) == []
    # Read only for the provider: no write routes in the portal.
    assert client.post(f"{P}/provider/availability", json=window, headers=own).status_code in (
        404,
        405,
    )
    assert client.delete(f"{admin}/{created['id']}", headers=own).status_code == 403
    assert client.delete(f"{admin}/{created['id']}", headers=hb).status_code == 404
    assert client.delete(f"{admin}/{created['id']}", headers=ha).status_code == 204
    assert _ok(client.get(f"{P}/provider/availability", headers=own)) == []
