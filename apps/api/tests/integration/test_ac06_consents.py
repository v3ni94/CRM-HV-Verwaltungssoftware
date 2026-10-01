"""AC06 (GA02-06): consent kinds gate their processing. marketing gates advertising serial
dispatch, email_delivery the e-mail delivery of documents (fallback post), portal_terms the
portal activation and access once terms are published, data_sharing the transfer check.
Each kind: granted, missing, revoked, tenant separation."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
NOW = datetime.now(UTC)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ac6a-{RUN}", name=f"AC06 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ac6b-{RUN}", name=f"AC06 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("ac06admin", a, "tenant_admin"),
            ("ac06other", b, "tenant_admin"),
            ("ac06reader", a, "read_only"),
        ):
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


def _contact(client: TestClient, h: dict[str, str], name: str, email: str | None = None) -> str:
    body: dict[str, Any] = {"kind": "person", "first_name": "A", "last_name": f"{name}{RUN}"}
    if email:
        body["emails"] = [{"email": email}]
        body["preferred_channel"] = "email"
    return str(_ok(client.post("/api/v1/contacts", json=body, headers=h), 201)["id"])


def _grant(client: TestClient, h: dict[str, str], contact: str, kind: str) -> str:
    return str(
        _ok(
            client.post(
                f"/api/v1/contacts/{contact}/consents",
                json={"kind": kind, "granted_at": NOW.isoformat(), "source": "Formular AC06"},
                headers=h,
            ),
            201,
        )["id"]
    )


def _doc(client: TestClient, h: dict[str, str]) -> str:
    return str(
        _ok(
            client.post(
                "/api/v1/documents",
                data={"title": "AC06 Schreiben"},
                files={"file": ("ac06.txt", b"AC06", "text/plain")},
                headers=h,
            ),
            201,
        )["id"]
    )


def test_ac06_policy_endpoint(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ac06admin"))
    assert _ok(client.get("/api/v1/consent-policy", headers=h)) == {
        "email_delivery": "consent_only",
        "data_sharing": "consent_only",
        "portal_terms_version": None,
    }
    reader = bearer(login(client, world, "ac06reader"))
    assert _ok(client.get("/api/v1/consent-policy", headers=reader))["data_sharing"]
    put = {"email_delivery": "consent_only", "data_sharing": "consent_only"}
    assert client.put("/api/v1/consent-policy", json=put, headers=reader).status_code == 403
    bad = {"email_delivery": "always"}
    assert client.put("/api/v1/consent-policy", json=bad, headers=h).status_code == 422
    assert client.get("/api/v1/consent-policy", params={"x": 1}, headers=h).status_code == 422


def test_ac06_email_delivery_fallback(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ac06admin"))
    doc = _doc(client, h)
    granted = _contact(client, h, "MailJa", f"ja{RUN}@example.com")
    missing = _contact(client, h, "MailNein", f"nein{RUN}@example.com")
    revoked = _contact(client, h, "MailWid", f"wid{RUN}@example.com")
    _grant(client, h, granted, "email_delivery")
    consent = _grant(client, h, revoked, "email_delivery")
    _ok(client.post(f"/api/v1/consents/{consent}/revoke", headers=h))
    res = _ok(
        client.post(
            "/api/v1/dispatches/serial",
            json={
                "items": [
                    {
                        "document_id": doc,
                        "contact_id": c,
                        "channel": "email",
                        "submit_postal": False,
                    }
                    for c in (granted, missing, revoked)
                ]
            },
            headers=h,
        ),
        201,
    )
    assert res["counts"]["email"] == 1
    assert res["counts"]["post"] == 2
    assert res["by_channel"]["email"][0]["contact_id"] == granted
    assert res["consent"]["email_fallback_to_post"] == 2
    assert set(res["consent"]["email_fallback_contact_ids"]) == {missing, revoked}

    # Tenant separation: the consent of tenant A does not exist for tenant B.
    other = bearer(login(client, world, "ac06other"))
    assert client.get(f"/api/v1/contacts/{granted}/consents", headers=other).json() == []
    assert (
        client.post(
            f"/api/v1/contacts/{granted}/consents",
            json={"kind": "email_delivery", "granted_at": NOW.isoformat(), "source": "xx"},
            headers=other,
        ).status_code
        == 404
    )

    # Tenant policy "consent_or_contract" accepts e-mail without consent (operator decision).
    _ok(
        client.put(
            "/api/v1/consent-policy",
            json={"email_delivery": "consent_or_contract", "data_sharing": "consent_only"},
            headers=h,
        )
    )
    try:
        single = _ok(
            client.post(
                "/api/v1/dispatches",
                json={"document_id": doc, "contact_id": missing, "channel": "email"},
                headers=h,
            ),
            201,
        )
        assert single["channel"] == "email"
        # Tenant B keeps the default: its own contact without consent falls back to post.
        doc_b = _doc(client, other)
        contact_b = _contact(client, other, "MailB", f"b{RUN}@example.com")
        res_b = _ok(
            client.post(
                "/api/v1/dispatches",
                json={"document_id": doc_b, "contact_id": contact_b, "submit_postal": False},
                headers=other,
            ),
            201,
        )
        assert res_b["channel"] == "post"
    finally:
        _ok(
            client.put(
                "/api/v1/consent-policy",
                json={"email_delivery": "consent_only", "data_sharing": "consent_only"},
                headers=h,
            )
        )


def test_ac06_marketing_serial(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ac06admin"))
    doc = _doc(client, h)
    granted = _contact(client, h, "WerbJa")
    missing = _contact(client, h, "WerbNein")
    revoked = _contact(client, h, "WerbWid")
    _grant(client, h, granted, "marketing")
    consent = _grant(client, h, revoked, "marketing")
    _ok(client.post(f"/api/v1/consents/{consent}/revoke", headers=h))
    items = [
        {"document_id": doc, "contact_id": c, "channel": "post", "submit_postal": False}
        for c in (granted, missing, revoked)
    ]
    ads = _ok(
        client.post(
            "/api/v1/dispatches/serial", json={"items": items, "advertising": True}, headers=h
        ),
        201,
    )
    assert ads["counts"]["post"] == 1
    assert ads["by_channel"]["post"][0]["contact_id"] == granted
    assert ads["consent"]["marketing_skipped"] == 2
    # Mandatory communication (no advertising flag) reaches everybody.
    duty = _ok(client.post("/api/v1/dispatches/serial", json={"items": items}, headers=h), 201)
    assert duty["counts"]["post"] == 3
    assert duty["consent"]["marketing_skipped"] == 0
    # Tenant separation.
    other = bearer(login(client, world, "ac06other"))
    res = client.post(
        "/api/v1/dispatches/serial", json={"items": items, "advertising": True}, headers=other
    )
    # Under RLS of B the consents of A are invisible: nobody is reached, nothing is created.
    body = _ok(res, 201)
    assert sum(body["counts"].values()) == 0
    assert body["consent"]["marketing_skipped"] == 3
    # Without the advertising flag tenant B cannot address A's contacts at all.
    plain = client.post("/api/v1/dispatches/serial", json={"items": items}, headers=other)
    assert plain.status_code == 404


def _invite(client: TestClient, h: dict[str, str], world: World, name: str) -> tuple[str, str]:
    contact = _contact(client, h, name)
    inv = _ok(
        client.post(
            "/api/v1/portal-admin/accounts",
            json={"contact_id": contact, "email": world.email(name), "display_name": name},
            headers=h,
        ),
        201,
    )
    return contact, str(inv["invitation_token"])


def test_ac06_portal_terms(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ac06admin"))
    version = f"2026-10-{RUN}"[:60]
    # Before terms are published, activation works as before (no invented legal text).
    _, token0 = _invite(client, h, world, "ac06pre")
    _ok(
        client.post(
            "/api/v1/portal/invitations/accept", json={"token": token0, "password": PASSWORD}
        )
    )
    pre = bearer(login(client, world, "ac06pre"))
    assert client.get("/api/v1/portal/me", headers=pre).status_code == 200

    _ok(
        client.put(
            "/api/v1/consent-policy",
            json={
                "email_delivery": "consent_only",
                "data_sharing": "consent_only",
                "portal_terms_version": version,
            },
            headers=h,
        )
    )
    try:
        contact, token = _invite(client, h, world, "ac06res")
        # Missing acceptance or a wrong version: no activation.
        miss = client.post(
            "/api/v1/portal/invitations/accept", json={"token": token, "password": PASSWORD}
        )
        assert miss.status_code == 403, miss.text
        wrong = client.post(
            "/api/v1/portal/invitations/accept",
            json={
                "token": token,
                "password": PASSWORD,
                "accept_terms": True,
                "terms_version": "alt",
            },
        )
        assert wrong.status_code == 403
        _ok(
            client.post(
                "/api/v1/portal/invitations/accept",
                json={
                    "token": token,
                    "password": PASSWORD,
                    "accept_terms": True,
                    "terms_version": version,
                },
            )
        )
        rows = _ok(client.get(f"/api/v1/contacts/{contact}/consents", headers=h))
        assert [(r["kind"], r["source"]) for r in rows] == [
            ("portal_terms", f"portal_terms_version={version}")
        ]
        portal = bearer(login(client, world, "ac06res"))
        assert client.get("/api/v1/portal/me", headers=portal).status_code == 200
        # The account activated before publication must accept now.
        assert client.get("/api/v1/portal/me", headers=pre).status_code == 403
        status = _ok(client.get("/api/v1/portal/terms", headers=pre))
        assert status == {
            "terms_version": version,
            "accepted": False,
            "reason": "portal_terms_missing",
        }
        _ok(
            client.post(
                "/api/v1/portal/terms/accept",
                json={"accept_terms": True, "terms_version": version},
                headers=pre,
            )
        )
        assert client.get("/api/v1/portal/me", headers=pre).status_code == 200
        # Revocation ends access at once.
        _ok(client.post(f"/api/v1/consents/{rows[0]['id']}/revoke", headers=h))
        denied = client.get("/api/v1/portal/me", headers=portal)
        assert denied.status_code == 403
        assert denied.json()["code"] == "MHVP-CONT-0020"
        # Tenant separation: tenant B has no published terms and sees no consent of A.
        other = bearer(login(client, world, "ac06other"))
        assert (
            _ok(client.get("/api/v1/consent-policy", headers=other))["portal_terms_version"] is None
        )
        assert client.get(f"/api/v1/contacts/{contact}/consents", headers=other).json() == []
    finally:
        _ok(
            client.put(
                "/api/v1/consent-policy",
                json={"email_delivery": "consent_only", "data_sharing": "consent_only"},
                headers=h,
            )
        )


def test_ac06_data_sharing_decision(world: World, database: Database, redis_url: str) -> None:
    from mhvp.contacts import consent_rules
    from mhvp.contacts.models import Consent, ConsentKind, Contact, ContactKind
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    async def run() -> None:
        engine = create_app_engine(_settings(database, redis_url))
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as s:
                ids = []
                for n in ("ja", "nein", "wid", "zukunft"):
                    c = Contact(
                        tenant_id=world.tenant_a,
                        kind=ContactKind.PERSON,
                        last_name=f"DS{n}{RUN}",
                        display_name=f"DS{n}{RUN}",
                    )
                    s.add(c)
                    await s.flush()
                    ids.append(c.id)
                yes, no, rev, fut = ids
                now = datetime.now(UTC)
                s.add_all(
                    [
                        Consent(
                            tenant_id=world.tenant_a,
                            contact_id=yes,
                            kind=ConsentKind.DATA_SHARING,
                            granted_at=now - timedelta(days=1),
                            source="t",
                        ),
                        Consent(
                            tenant_id=world.tenant_a,
                            contact_id=rev,
                            kind=ConsentKind.DATA_SHARING,
                            granted_at=now - timedelta(days=2),
                            revoked_at=now - timedelta(days=1),
                            source="t",
                        ),
                        Consent(
                            tenant_id=world.tenant_a,
                            contact_id=fut,
                            kind=ConsentKind.DATA_SHARING,
                            granted_at=now + timedelta(days=5),
                            source="t",
                        ),
                    ]
                )
                await s.flush()
                d = consent_rules.data_sharing_decision
                assert (await d(s, yes)).allowed
                for cid in (no, rev, fut):
                    res = await d(s, cid, contractual_necessity=True)
                    assert (res.allowed, res.reason) == (False, "data_sharing_consent_missing")
                wide = consent_rules.ConsentPolicy(data_sharing="consent_or_contract")
                assert (await d(s, no, contractual_necessity=True, policy=wide)).reason == (
                    "tenant_policy_contract"
                )
                assert not (await d(s, no, policy=wide)).allowed
            # Tenant separation: under RLS of tenant B the consent of A is invisible.
            async with tenant_transaction(factory, world.tenant_b) as s:
                assert not (await consent_rules.data_sharing_decision(s, yes)).allowed
        finally:
            await engine.dispose()

    asyncio.run(run())
