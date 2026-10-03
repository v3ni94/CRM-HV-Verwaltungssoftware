"""AE34 (AC06-01 to AC06-03, AD03-01): legal basis per processing, objection, public lookup of
the published portal terms and the evidence of the acceptance in text form.

Own world: tenants ae34a (main), ae34b (other tenant, publishes another version), ae34c
(publishes nothing), ae34d (publishes, then suspended)."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.contacts import consent_rules
from mhvp.core import crypto
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
BUCKET = "ae34-bucket"
NOW = datetime.now(UTC)
PORTAL_HOST = f"ae34a-{RUN}.portal.test"
TRUSTED = {"rate_limit_trust_forwarded_for": True}


def _settings(database: Database, redis_url: str, **overrides: object) -> Any:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        **overrides,
    )


async def _world(settings: Any) -> World:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        tenants = {}
        for key in ("a", "b", "c", "d"):
            tenants[key], _ = await services.provision_tenant(
                factory,
                slug=f"ae34{key}-{RUN}",
                name=f"AE34 {key} {RUN}",
                domains=[PORTAL_HOST] if key == "a" else None,
            )
        world = World(
            tenant_a=tenants["a"],
            tenant_b=tenants["b"],
            app_url=settings.database_url.get_secret_value(),
        )
        world.users["tenant_c"] = tenants["c"]
        world.users["tenant_d"] = tenants["d"]
        for name, tenant, role in (
            ("ae34admin", tenants["a"], "tenant_admin"),
            ("ae34reader", tenants["a"], "read_only"),
            ("ae34other", tenants["b"], "tenant_admin"),
            ("ae34admind", tenants["d"], "tenant_admin"),
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
        with TestClient(create_app(_settings(database, redis_url, **TRUSTED))) as test_client:
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
                json={"kind": kind, "granted_at": NOW.isoformat(), "source": "Formular AE34"},
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
                data={"title": "AE34 Schreiben"},
                files={"file": ("ae34.txt", b"AE34", "text/plain")},
                headers=h,
            ),
            201,
        )["id"]
    )


def _basis(
    client: TestClient, h: dict[str, str], purpose: str, basis: str, note: str | None = None
) -> Any:
    body: dict[str, Any] = {"basis": basis}
    if note is not None:
        body["note"] = note
    return client.put(f"/api/v1/consent-legal-basis/{purpose}", json=body, headers=h)


def _reset(client: TestClient, h: dict[str, str]) -> None:
    for purpose in consent_rules.PURPOSES:
        _ok(client.delete(f"/api/v1/consent-legal-basis/{purpose}", headers=h))
    _ok(
        client.put(
            "/api/v1/consent-policy",
            json={"email_delivery": "consent_only", "data_sharing": "consent_only"},
            headers=h,
        )
    )


def _by_purpose(listing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["purpose"]: item for item in listing["items"]}


# Legal basis register -----------------------------------------------------------------------


def test_register_defaults_validation_and_permissions(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "ae34admin"))
    reader = bearer(login(client, world, "ae34reader"))
    other = bearer(login(client, world, "ae34other"))
    try:
        first = _by_purpose(_ok(client.get("/api/v1/consent-legal-basis", headers=h)))
        assert set(first) == set(consent_rules.PURPOSES)
        assert all(v["basis"] == "consent" and v["origin"] == "default" for v in first.values())
        # GAM-406 (AP13, OPEN_QUESTIONS AP13-04): sms and ai_processing without register entry
        # check nothing but a recorded objection, every other purpose requires consent.
        assert all(
            v["consent_required"] is (p not in consent_rules.UNREGISTERED_OPEN)
            for p, v in first.items()
        )
        assert first["marketing"]["allowed_bases"] == ["consent", "legitimate_interest"]
        # Read right is enough to read, writing needs contacts:approve.
        assert client.get("/api/v1/consent-legal-basis", headers=reader).status_code == 200
        assert _basis(client, reader, "email_delivery", "consent").status_code == 403
        assert client.get("/api/v1/consent-legal-basis").status_code == 401
        # Validation: unknown purpose, unknown basis, advertising never "contract", missing
        # justification, unknown query parameter.
        assert _basis(client, h, "whatsapp", "consent").status_code == 422
        assert _basis(client, h, "email_delivery", "always").status_code == 422
        assert (
            _basis(client, h, "marketing", "contract", "Vertragsklausel Nr. 7").status_code == 422
        )
        assert _basis(client, h, "email_delivery", "contract").status_code == 422
        assert _basis(client, h, "email_delivery", "contract", "kurz").status_code == 422
        assert (
            client.get("/api/v1/consent-legal-basis", params={"x": 1}, headers=h).status_code == 422
        )
        # A justified choice is stored, shown with origin and recorded as an event.
        note = "Textformklausel im Mietvertrag, Stand 2026"
        done = _by_purpose(_ok(_basis(client, h, "email_delivery", "contract", note)))
        assert done["email_delivery"]["basis"] == "contract"
        assert done["email_delivery"]["origin"] == "register"
        assert done["email_delivery"]["note"] == note
        assert done["email_delivery"]["consent_required"] is False
        assert done["data_sharing"]["origin"] == "default"
        # Tenant separation: tenant B still has the defaults.
        theirs = _by_purpose(_ok(client.get("/api/v1/consent-legal-basis", headers=other)))
        assert theirs["email_delivery"]["origin"] == "default"
        assert theirs["email_delivery"]["note"] is None

        async def events() -> list[dict[str, Any]]:
            from sqlalchemy import select

            from mhvp.core.db.engine import create_app_engine, create_session_factory
            from mhvp.core.db.tenancy import tenant_transaction
            from mhvp.core.events import DomainEvent

            engine = create_app_engine(_settings(database, redis_url))
            try:
                async with tenant_transaction(create_session_factory(engine), world.tenant_a) as s:
                    rows = await s.scalars(
                        select(DomainEvent).where(DomainEvent.type == "consent_legal_basis.updated")
                    )
                    return [dict(r.payload) for r in rows.all()]
            finally:
                await engine.dispose()

        payloads = asyncio.run(events())
        assert any(
            p["purpose"] == "email_delivery" and p["after"]["basis"] == "contract" for p in payloads
        )
    finally:
        _reset(client, h)


def test_legacy_switch_counts_as_contract_and_register_overrides(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "ae34admin"))
    try:
        _ok(
            client.put(
                "/api/v1/consent-policy",
                json={"email_delivery": "consent_or_contract", "data_sharing": "consent_only"},
                headers=h,
            )
        )
        legacy = _by_purpose(_ok(client.get("/api/v1/consent-legal-basis", headers=h)))
        assert (legacy["email_delivery"]["basis"], legacy["email_delivery"]["origin"]) == (
            "contract",
            "policy",
        )
        # An explicit register entry wins over the legacy switch.
        _ok(_basis(client, h, "email_delivery", "consent"))
        mixed = _by_purpose(_ok(client.get("/api/v1/consent-legal-basis", headers=h)))
        assert (mixed["email_delivery"]["basis"], mixed["email_delivery"]["origin"]) == (
            "consent",
            "register",
        )
        # PUT /consent-policy replaces only the policy, the register stays.
        _ok(
            client.put(
                "/api/v1/consent-policy",
                json={"email_delivery": "consent_only", "data_sharing": "consent_only"},
                headers=h,
            )
        )
        again = _by_purpose(_ok(client.get("/api/v1/consent-legal-basis", headers=h)))
        assert again["email_delivery"]["origin"] == "register"
        # Reset removes the entry: the default applies again (and is idempotent).
        reader = bearer(login(client, world, "ae34reader"))
        assert (
            client.delete("/api/v1/consent-legal-basis/email_delivery", headers=reader).status_code
            == 403
        )
        gone = _by_purpose(
            _ok(client.delete("/api/v1/consent-legal-basis/email_delivery", headers=h))
        )
        assert (gone["email_delivery"]["basis"], gone["email_delivery"]["origin"]) == (
            "consent",
            "default",
        )
        _ok(client.delete("/api/v1/consent-legal-basis/email_delivery", headers=h))
        assert client.delete("/api/v1/consent-legal-basis/whatsapp", headers=h).status_code == 422
    finally:
        _reset(client, h)


def test_email_delivery_legitimate_interest_and_objection(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae34admin"))
    other = bearer(login(client, world, "ae34other"))
    reader = bearer(login(client, world, "ae34reader"))
    doc = _doc(client, h)
    plain = _contact(client, h, "LiPlain", f"plain{RUN}@example.com")
    objecting = _contact(client, h, "LiWid", f"wid{RUN}@example.com")
    revoked = _contact(client, h, "LiRev", f"rev{RUN}@example.com")
    consented = _contact(client, h, "LiJa", f"ja{RUN}@example.com")
    _grant(client, h, consented, "email_delivery")
    consent_id = _grant(client, h, revoked, "email_delivery")
    _ok(client.post(f"/api/v1/consents/{consent_id}/revoke", headers=h))

    def send(contacts: list[str]) -> Any:
        return _ok(
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
                        for c in contacts
                    ]
                },
                headers=h,
            ),
            201,
        )

    try:
        # Default basis consent: only the consented contact gets e-mail.
        base = send([plain, objecting, revoked, consented])
        assert base["counts"]["email"] == 1
        assert base["counts"]["post"] == 3
        # Legitimate interest: everybody except revoked consent (read as objection).
        _ok(
            _basis(
                client,
                h,
                "email_delivery",
                "legitimate_interest",
                "Interessenabwägung vom 01.10.2026",
            )
        )
        wide = send([plain, objecting, revoked, consented])
        assert wide["counts"]["email"] == 3
        assert wide["consent"]["email_fallback_contact_ids"] == [revoked]
        # An explicit objection blocks the contact; the objection is a separate record.
        bad = client.post(
            f"/api/v1/contacts/{objecting}/objections",
            json={"kind": "whatsapp", "source": "Brief"},
            headers=h,
        )
        assert bad.status_code == 422
        future = (NOW + timedelta(days=3)).isoformat()
        assert (
            client.post(
                f"/api/v1/contacts/{objecting}/objections",
                json={"kind": "email_delivery", "source": "Brief", "received_at": future},
                headers=h,
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/api/v1/contacts/{objecting}/objections",
                json={"kind": "email_delivery", "source": "Brief"},
                headers=reader,
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/contacts/{objecting}/objections",
                json={"kind": "email_delivery", "source": "Brief"},
                headers=other,
            ).status_code
            == 404
        )
        objection = _ok(
            client.post(
                f"/api/v1/contacts/{objecting}/objections",
                json={"kind": "email_delivery", "source": "Schreiben vom Kontakt"},
                headers=h,
            ),
            201,
        )
        assert objection["record_type"] == "objection"
        narrowed = send([plain, objecting, revoked, consented])
        assert narrowed["counts"]["email"] == 2
        assert set(narrowed["consent"]["email_fallback_contact_ids"]) == {objecting, revoked}
        # The objection is no consent: it neither enables nor appears as an e-mail consent.
        rows = _ok(client.get(f"/api/v1/contacts/{objecting}/consents", headers=h))
        assert [r["record_type"] for r in rows] == ["objection"]
        # Withdrawing the objection lifts the block.
        _ok(client.post(f"/api/v1/consents/{objection['id']}/revoke", headers=h))
        assert send([objecting])["counts"]["email"] == 1
        # Back to consent: no consent, post again.
        _ok(_basis(client, h, "email_delivery", "consent"))
        assert send([plain])["counts"]["post"] == 1
    finally:
        _reset(client, h)


def test_marketing_on_legitimate_interest(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae34admin"))
    other = bearer(login(client, world, "ae34other"))
    doc = _doc(client, h)
    plain = _contact(client, h, "MwPlain")
    consented = _contact(client, h, "MwJa")
    objecting = _contact(client, h, "MwObj")
    revoked = _contact(client, h, "MwRev")
    _grant(client, h, consented, "marketing")
    rid = _grant(client, h, revoked, "marketing")
    _ok(client.post(f"/api/v1/consents/{rid}/revoke", headers=h))
    _ok(
        client.post(
            f"/api/v1/contacts/{objecting}/objections",
            json={"kind": "marketing", "source": "Telefonat"},
            headers=h,
        ),
        201,
    )
    items = [
        {"document_id": doc, "contact_id": c, "channel": "post", "submit_postal": False}
        for c in (plain, consented, objecting, revoked)
    ]

    def ads() -> Any:
        return _ok(
            client.post(
                "/api/v1/dispatches/serial", json={"items": items, "advertising": True}, headers=h
            ),
            201,
        )

    try:
        base = ads()
        assert base["counts"]["post"] == 1
        assert base["consent"]["marketing_skipped"] == 3
        _ok(
            _basis(
                client, h, "marketing", "legitimate_interest", "Interessenabwägung Bestandskunden"
            )
        )
        wide = ads()
        sent = {r["contact_id"] for r in wide["by_channel"]["post"]}
        assert sent == {plain, consented}
        assert wide["consent"]["marketing_skipped"] == 2
        # Tenant separation: tenant B keeps the consent basis.
        theirs = _by_purpose(_ok(client.get("/api/v1/consent-legal-basis", headers=other)))
        assert theirs["marketing"]["basis"] == "consent"
    finally:
        _reset(client, h)


def test_data_sharing_basis_decisions(world: World, database: Database, redis_url: str) -> None:
    from mhvp.contacts.models import Consent, ConsentKind, Contact, ContactKind
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    entry = consent_rules.BasisEntry
    contract = consent_rules.ConsentPolicy(
        legal_basis={"data_sharing": entry("contract", "Auftrag")}
    )
    interest = consent_rules.ConsentPolicy(
        legal_basis={"data_sharing": entry("legitimate_interest", "Abwägung vom 01.10.2026")}
    )

    async def run() -> None:
        engine = create_app_engine(_settings(database, redis_url))
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as s:
                ids = []
                for n in ("plain", "obj", "rev"):
                    c = Contact(
                        tenant_id=world.tenant_a,
                        kind=ContactKind.PERSON,
                        last_name=f"AE34DS{n}{RUN}",
                        display_name=f"AE34DS{n}{RUN}",
                    )
                    s.add(c)
                    await s.flush()
                    ids.append(c.id)
                plain, obj, rev = ids
                s.add_all(
                    [
                        Consent(
                            tenant_id=world.tenant_a,
                            contact_id=obj,
                            kind=ConsentKind.DATA_SHARING,
                            granted_at=NOW - timedelta(hours=1),
                            source="Widerspruch",
                            record_type="objection",
                        ),
                        Consent(
                            tenant_id=world.tenant_a,
                            contact_id=rev,
                            kind=ConsentKind.DATA_SHARING,
                            granted_at=NOW - timedelta(days=2),
                            revoked_at=NOW - timedelta(days=1),
                            source="t",
                        ),
                    ]
                )
                await s.flush()
                d = consent_rules.data_sharing_decision
                # Contract covers it only when the caller states the necessity.
                assert (await d(s, plain, contractual_necessity=True, policy=contract)).reason == (
                    "tenant_policy_contract"
                )
                assert not (await d(s, plain, contractual_necessity=False, policy=contract)).allowed
                # Legitimate interest: allowed unless objection or revoked consent.
                assert (await d(s, plain, policy=interest)).reason == "legitimate_interest"
                assert (
                    await d(s, obj, policy=interest)
                ).reason == "data_sharing_objection_recorded"
                assert not (await d(s, rev, policy=interest)).allowed
                # Default basis: nothing without consent, an objection record is no consent.
                for cid in (plain, obj, rev):
                    assert (await d(s, cid)).reason == "data_sharing_consent_missing"
                assert not await consent_rules.has_consent(s, obj, ConsentKind.DATA_SHARING)
            async with tenant_transaction(factory, world.tenant_b) as s:
                # Under RLS of tenant B the objection of tenant A is invisible.
                seen = await consent_rules.data_sharing_decision(s, obj, policy=interest)
                assert seen.reason != "data_sharing_objection_recorded"
        finally:
            await engine.dispose()

    asyncio.run(run())


# Public lookup of the published terms -----------------------------------------------------------


def _publish(client: TestClient, world: World, name: str, version: str | None) -> None:
    h = bearer(login(client, world, name))
    body: dict[str, Any] = {"email_delivery": "consent_only", "data_sharing": "consent_only"}
    if version:
        body["portal_terms_version"] = version
    _ok(client.put("/api/v1/consent-policy", json=body, headers=h))


def _terms(client: TestClient, tenant: str | None, **kwargs: Any) -> Any:
    params = {"tenant": tenant} if tenant is not None else None
    return client.get("/api/v1/portal/public/terms", params=params, **kwargs)


def test_public_terms_lookup_hides_existence(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from sqlalchemy import update

    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import platform_transaction
    from mhvp.platform.models import Tenant, TenantStatus

    version_a, version_b, version_d = f"2026-10-a{RUN}", f"2027-01-b{RUN}", f"2026-12-d{RUN}"
    _publish(client, world, "ae34admin", version_a)
    _publish(client, world, "ae34other", version_b)
    _publish(client, world, "ae34admind", version_d)

    async def suspend() -> None:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            async with platform_transaction(create_session_factory(engine)) as s:
                await s.execute(
                    update(Tenant)
                    .where(Tenant.id == world.users["tenant_d"])
                    .values(status=TenantStatus.SUSPENDED)
                )
        finally:
            await engine.dispose()

    asyncio.run(suspend())
    try:
        slug_a, slug_b = f"ae34a-{RUN}", f"ae34b-{RUN}"
        # Without credentials: the version of exactly the named tenant.
        found = _ok(_terms(client, slug_a))
        assert found["terms_version"] == version_a
        assert found["acceptance"] == "textform"
        assert set(found) == {"terms_version", "acceptance", "evidence"}
        assert found["evidence"] == ["accepted_at", "terms_version", "client_hash"]
        assert _terms(client, slug_a).headers["cache-control"] == "no-store"
        assert _ok(_terms(client, slug_a.upper()))["terms_version"] == version_a
        assert _ok(_terms(client, str(world.tenant_a)))["terms_version"] == version_a
        assert _ok(_terms(client, world.tenant_a.hex))["terms_version"] == version_a
        # Another tenant sees only its own version, never the version of tenant A.
        assert _ok(_terms(client, slug_b))["terms_version"] == version_b
        # Portal host without ?tenant=: Host header or X-Portal-Host (3.3).
        assert (
            _ok(client.get("/api/v1/portal/public/terms", headers={"Host": PORTAL_HOST}))[
                "terms_version"
            ]
            == version_a
        )
        via_proxy = client.get(
            "/api/v1/portal/public/terms", headers={"X-Portal-Host": PORTAL_HOST}
        )
        assert _ok(via_proxy)["terms_version"] == version_a

        # Misses: unknown, malformed, no publication, suspended, other host. One identical
        # answer, nothing that tells the cases apart.
        misses = {
            "unknown": _terms(client, f"ae34-unbekannt-{RUN}"),
            "unknown_id": _terms(client, str(uuid.uuid4())),
            "malformed": _terms(client, "../etc/passwd"),
            "blank_char": _terms(client, "a b"),
            "no_publication": _terms(client, f"ae34c-{RUN}"),
            "suspended": _terms(client, f"ae34d-{RUN}"),
            "id_no_publication": _terms(client, world.users["tenant_c"].hex),
            "no_tenant_no_host": _terms(client, None),
            "foreign_host": client.get(
                "/api/v1/portal/public/terms", headers={"X-Portal-Host": f"fremd-{RUN}.example.org"}
            ),
        }
        bodies = set()
        for label, response in misses.items():
            assert response.status_code == 404, f"{label}: {response.status_code} {response.text}"
            body = response.json()
            assert version_a not in response.text
            assert version_b not in response.text
            assert RUN not in response.text, label
            bodies.add((body.get("code"), body.get("title"), body.get("detail")))
        assert len(bodies) == 1
        # Query validation does not describe tenants either: unknown parameter and overlong
        # value are plain 422, independent of existence.
        assert client.get("/api/v1/portal/public/terms", params={"x": "1"}).status_code == 422
        assert _terms(client, "a" * 65).status_code == 422
        assert _terms(client, "a" * 64).status_code == 404
        # No list, no other method.
        assert client.post("/api/v1/portal/public/terms").status_code == 405
        assert client.get("/api/v1/portal/public").status_code == 404
    finally:
        for name in ("ae34admin", "ae34other"):
            _publish(client, world, name, None)


def test_public_terms_uses_the_anonymous_rate_limit(
    database: Database, redis_url: str, world: World
) -> None:
    """Like the other public paths: the limit for unauthenticated callers counts per client
    address, hits and misses alike, and answers 429 with Retry-After."""
    settings = _settings(
        database,
        redis_url,
        rate_limit_enabled=True,
        rate_limit_per_minute_anonymous=3,
        rate_limit_trust_forwarded_for=True,
    )
    address = f"198.51.100.{uuid.uuid4().int % 250 + 1}"
    with TestClient(create_app(settings)) as strict:
        headers = {"X-Forwarded-For": address}
        for _ in range(3):
            response = strict.get(
                "/api/v1/portal/public/terms", params={"tenant": f"ae34-x-{RUN}"}, headers=headers
            )
            assert response.status_code == 404
            assert response.headers["X-RateLimit-Limit"] == "3"
        limited = strict.get(
            "/api/v1/portal/public/terms", params={"tenant": f"ae34a-{RUN}"}, headers=headers
        )
        assert limited.status_code == 429
        assert "Retry-After" in limited.headers
        # Another client address has its own counter.
        other = strict.get(
            "/api/v1/portal/public/terms",
            params={"tenant": f"ae34a-{RUN}"},
            headers={"X-Forwarded-For": "203.0.113.200"},
        )
        assert other.status_code in (200, 404)


# Evidence of the acceptance in text form --------------------------------------------------------


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


def _stored(world: World, database: Database, redis_url: str, contact: str) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from mhvp.contacts.models import Consent
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    async def run() -> list[dict[str, Any]]:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            async with tenant_transaction(create_session_factory(engine), world.tenant_a) as s:
                rows = await s.scalars(
                    select(Consent).where(Consent.contact_id == uuid.UUID(contact))
                )
                return [
                    {
                        "kind": r.kind.value,
                        "record_type": r.record_type,
                        "text_version": r.text_version,
                        "ip_hash": r.ip_hash,
                        "granted_at": r.granted_at,
                    }
                    for r in rows.all()
                ]
        finally:
            await engine.dispose()

    return asyncio.run(run())


def test_acceptance_records_time_version_and_client_hash(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "ae34admin"))
    version = f"2026-11-{RUN}"
    _publish(client, world, "ae34admin", version)
    try:
        contact, token = _invite(client, h, world, "ae34res")
        before = datetime.now(UTC)
        ip_one = f"203.0.113.{uuid.uuid4().int % 250 + 1}"
        _ok(
            client.post(
                "/api/v1/portal/invitations/accept",
                json={
                    "token": token,
                    "password": PASSWORD,
                    "accept_terms": True,
                    "terms_version": version,
                },
                headers={"X-Forwarded-For": ip_one},
            )
        )
        rows = _stored(world, database, redis_url, contact)
        assert len(rows) == 1
        row = rows[0]
        assert (row["kind"], row["record_type"], row["text_version"]) == (
            "portal_terms",
            "consent",
            version,
        )
        assert before - timedelta(seconds=5) <= row["granted_at"] <= datetime.now(UTC)
        expected = crypto.fingerprint(
            ip_one, scope=f"tenant:{world.tenant_a.hex}:portal-terms-client"
        )
        assert row["ip_hash"] == expected
        assert ip_one not in str(row)
        assert len(row["ip_hash"]) == 64
        # The staff view shows version and that evidence exists, never the hash or the address.
        listed = _ok(client.get(f"/api/v1/contacts/{contact}/consents", headers=h))
        assert listed[0]["text_version"] == version
        assert listed[0]["client_evidence_recorded"] is True
        assert "ip_hash" not in listed[0]
        assert ip_one not in str(listed)
        # A second acceptance of the logged in account from another address: other hash.
        pre_contact, pre_token = _invite(client, h, world, "ae34late")
        _publish(client, world, "ae34admin", None)
        _ok(
            client.post(
                "/api/v1/portal/invitations/accept", json={"token": pre_token, "password": PASSWORD}
            )
        )
        _publish(client, world, "ae34admin", version)
        late = bearer(login(client, world, "ae34late"))
        assert client.get("/api/v1/portal/me", headers=late).status_code == 403
        ip_two = f"198.51.100.{uuid.uuid4().int % 250 + 1}"
        _ok(
            client.post(
                "/api/v1/portal/terms/accept",
                json={"accept_terms": True, "terms_version": version},
                headers={**late, "X-Forwarded-For": ip_two},
            )
        )
        second = _stored(world, database, redis_url, pre_contact)[0]
        assert second["text_version"] == version
        assert second["ip_hash"] == crypto.fingerprint(
            ip_two, scope=f"tenant:{world.tenant_a.hex}:portal-terms-client"
        )
        assert second["ip_hash"] != row["ip_hash"]
        # Wrong version: refused, nothing recorded for another contact.
        assert (
            client.post(
                "/api/v1/portal/terms/accept",
                json={"accept_terms": True, "terms_version": "alt"},
                headers=late,
            ).status_code
            == 403
        )
    finally:
        _publish(client, world, "ae34admin", None)
        _reset(client, h)


def test_acceptance_does_not_store_the_address_without_trusted_header(
    database: Database, redis_url: str, world: World
) -> None:
    """Without the trust switch X-Forwarded-For is ignored (spoofable); the hash then belongs to
    the connecting address of the portal server."""
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as plain:
            h = bearer(login(plain, world, "ae34admin"))
            version = f"2026-12-{RUN}"
            _publish(plain, world, "ae34admin", version)
            try:
                contact, token = _invite(plain, h, world, "ae34noxff")
                _ok(
                    plain.post(
                        "/api/v1/portal/invitations/accept",
                        json={
                            "token": token,
                            "password": PASSWORD,
                            "accept_terms": True,
                            "terms_version": version,
                        },
                        headers={"X-Forwarded-For": "203.0.113.99"},
                    )
                )
                stored = _stored(world, database, redis_url, contact)[0]
                spoofed = crypto.fingerprint(
                    "203.0.113.99", scope=f"tenant:{world.tenant_a.hex}:portal-terms-client"
                )
                assert stored["ip_hash"] is not None
                assert stored["ip_hash"] != spoofed
            finally:
                _publish(plain, world, "ae34admin", None)
