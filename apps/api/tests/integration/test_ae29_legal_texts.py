"""AE29 / M21-04, R10-03/04: legal texts of the portal per tenant (impressum, datenschutz,
nutzungsbedingungen) in legal_text_block with release by a second person.

Expected (hand derived): without an approved version the public read shows the marker "Text nicht
freigegeben" and no body; after draft, submit and release by a second person the public read of the
tenant host returns the body, the list and the branding name the code as released; another portal
host never sees it (tenant separation). The terms label of the consent policy is "NB-<version>":
mode manual (default) leaves the label alone, apply sets it only with an approved text and
confirm=true, mode follow_text sets it on release. Changing the label needs contacts:approve (403
for a reader).
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import _settings

pytestmark = pytest.mark.integration
B = "/api/v1/document-text-blocks"
T = "/api/v1/tenant"
HOST_A = {"x-portal-host": f"portal-ae29a-{RUN}.test"}
HOST_B = {"x-portal-host": f"portal-ae29b-{RUN}.test"}


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(
            factory,
            slug=f"ae29a-{RUN}",
            name=f"AE29 A {RUN}",
            domains=[f"portal-ae29a-{RUN}.test"],
        )
        b, _ = await services.provision_tenant(
            factory,
            slug=f"ae29b-{RUN}",
            name=f"AE29 B {RUN}",
            domains=[f"portal-ae29b-{RUN}.test"],
        )
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae29first", a, "tenant_admin"),
            ("ae29second", a, "tenant_admin"),
            ("ae29reader", a, "read_only"),
            ("ae29other", b, "tenant_admin"),
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
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


def _release(
    client: TestClient, author: dict[str, str], approver: dict[str, str], code: str, body: str
) -> dict[str, Any]:
    """Draft by the author, submitted by the author, released by the second person."""
    draft = client.post(B, json={"code": code, "title": code, "body": body}, headers=author)
    assert draft.status_code == 201, draft.text
    bid = draft.json()["id"]
    assert client.post(f"{B}/{bid}/submit", headers=author).status_code == 200
    done = client.post(f"{B}/{bid}/approve", headers=approver)
    assert done.status_code == 200, done.text
    out: dict[str, Any] = done.json()
    return out


def test_public_texts_only_when_approved_and_per_tenant(client: TestClient, world: World) -> None:
    h1 = bearer(login(client, world, "ae29first"))
    h2 = bearer(login(client, world, "ae29second"))
    ho = bearer(login(client, world, "ae29other"))

    # Before any release: marker, no body, nothing released (and the codes are known).
    listing = client.get(f"{T}/legal-texts", headers=HOST_A)
    assert listing.status_code == 200, listing.text
    items = {i["code"]: i for i in listing.json()["items"]}
    assert list(items) == ["impressum", "datenschutz", "nutzungsbedingungen"]
    assert all(
        not i["released"] and i["display"] == "Text nicht freigegeben" for i in items.values()
    )
    one = client.get(f"{T}/legal-texts/impressum", headers=HOST_A).json()
    assert one["released"] is False
    assert one["body"] is None
    assert client.get(f"{T}/branding", headers=HOST_A).json()["legal_texts_released"] == []

    # Unknown code and unknown host are 404, unknown query parameters 422.
    assert client.get(f"{T}/legal-texts/agb", headers=HOST_A).status_code in (404, 422)
    assert (
        client.get(f"{T}/legal-texts", headers={"x-portal-host": "unknown.test"}).status_code == 404
    )
    assert client.get(f"{T}/legal-texts?x=1", headers=HOST_A).status_code == 422

    # A draft or a submitted text is never public.
    draft = client.post(
        B, json={"code": "impressum", "title": "Impressum", "body": "Entwurf Impressum"}, headers=h1
    ).json()
    assert client.get(f"{T}/legal-texts/impressum", headers=HOST_A).json()["body"] is None
    client.post(f"{B}/{draft['id']}/submit", headers=h1)
    assert client.get(f"{T}/legal-texts/impressum", headers=HOST_A).json()["released"] is False
    # Four eyes still applies to the new codes.
    assert client.post(f"{B}/{draft['id']}/approve", headers=h1).status_code in (403, 409)
    assert client.post(f"{B}/{draft['id']}/approve", headers=h2).status_code == 200

    shown = client.get(f"{T}/legal-texts/impressum", headers=HOST_A).json()
    assert shown["released"] is True
    assert shown["version"] == 1
    assert shown["body"] == "Entwurf Impressum"
    assert shown["display"] is None
    assert client.get(f"{T}/branding", headers=HOST_A).json()["legal_texts_released"] == [
        "impressum"
    ]
    # Tenant separation: the other portal host sees nothing, the other tenant admin no block.
    other = client.get(f"{T}/legal-texts/impressum", headers=HOST_B).json()
    assert other["released"] is False
    assert other["body"] is None
    assert client.get(f"{B}/{draft['id']}", headers=ho).status_code == 404
    assert client.get(f"{T}/branding", headers=HOST_B).json()["legal_texts_released"] == []

    # A new version replaces the old one in the public read only after its release.
    v2 = client.post(
        B, json={"code": "impressum", "title": "Impressum", "body": "Zweite Fassung"}, headers=h1
    ).json()
    assert client.get(f"{T}/legal-texts/impressum", headers=HOST_A).json()["body"] == (
        "Entwurf Impressum"
    )
    client.post(f"{B}/{v2['id']}/submit", headers=h1)
    client.post(f"{B}/{v2['id']}/approve", headers=h2)
    now = client.get(f"{T}/legal-texts/impressum", headers=HOST_A).json()
    assert (now["version"], now["body"]) == (2, "Zweite Fassung")


def test_external_link_stands_in_while_unreleased(client: TestClient, world: World) -> None:
    h1 = bearer(login(client, world, "ae29first"))
    patch = client.patch(
        f"{T}/settings",
        json={"branding": {"privacy_url": "https://example.test/datenschutz"}},
        headers=h1,
    )
    assert patch.status_code == 200, patch.text
    one = client.get(f"{T}/legal-texts/datenschutz", headers=HOST_A).json()
    assert one["released"] is False
    assert one["external_url"] == "https://example.test/datenschutz"
    assert client.get(f"{T}/legal-texts/datenschutz", headers=HOST_B).json()["external_url"] is None


def test_terms_version_link_manual_apply_and_follow(client: TestClient, world: World) -> None:
    h1 = bearer(login(client, world, "ae29first"))
    h2 = bearer(login(client, world, "ae29second"))
    hr = bearer(login(client, world, "ae29reader"))
    cfg = f"{T}/legal-texts-config"

    status = client.get(cfg, headers=h1).json()
    assert status["terms_version_mode"] == "manual"
    assert status["policy_terms_version"] is None
    assert status["approved_text_version"] is None
    assert status["in_sync"] is False
    # Reader may look, but not change the label, the mode or apply (403); validation is 422.
    assert client.get(cfg, headers=hr).status_code == 200
    assert (
        client.put(cfg, json={"terms_version_mode": "follow_text"}, headers=hr).status_code == 403
    )
    assert (
        client.post(f"{cfg}/apply-terms-version", json={"confirm": True}, headers=hr).status_code
        == 403
    )
    assert client.put(cfg, json={"terms_version_mode": "auto"}, headers=h1).status_code == 422
    # Without an approved terms text nothing can be applied (409); without confirm it is 422.
    assert (
        client.post(f"{cfg}/apply-terms-version", json={"confirm": True}, headers=h1).status_code
        == 409
    )
    assert (
        client.post(f"{cfg}/apply-terms-version", json={"confirm": False}, headers=h1).status_code
        == 422
    )

    # Mode manual: releasing the terms text leaves the label untouched.
    first = _release(client, h1, h2, "nutzungsbedingungen", "Nutzungsbedingungen Fassung eins")
    assert first["version"] == 1
    assert client.get("/api/v1/consent-policy", headers=h1).json()["portal_terms_version"] is None
    status = client.get(cfg, headers=h1).json()
    assert (status["approved_text_version"], status["suggested_label"], status["in_sync"]) == (
        1,
        "NB-1",
        False,
    )
    public = client.get(f"{T}/legal-texts/nutzungsbedingungen", headers=HOST_A).json()
    assert public["body"] == "Nutzungsbedingungen Fassung eins"
    assert public["terms_version"] is None
    assert public["terms_in_sync"] is False

    # Explicit apply sets the label of the consent policy (other switches stay).
    applied = client.post(f"{cfg}/apply-terms-version", json={"confirm": True}, headers=h1)
    assert applied.status_code == 200, applied.text
    assert applied.json()["policy_terms_version"] == "NB-1"
    assert applied.json()["in_sync"] is True
    policy = client.get("/api/v1/consent-policy", headers=h1).json()
    assert policy["portal_terms_version"] == "NB-1"
    assert policy["email_delivery"] == "consent_only"
    public = client.get(f"{T}/legal-texts/nutzungsbedingungen", headers=HOST_A).json()
    assert (public["terms_version"], public["terms_text_version"], public["terms_in_sync"]) == (
        "NB-1",
        1,
        True,
    )
    # Tenant separation of the label.
    assert client.get(f"{T}/legal-texts", headers=HOST_B).json()["terms_version"] is None

    # A second version in mode manual: the label stays NB-1, status shows the difference.
    _release(client, h2, h1, "nutzungsbedingungen", "Nutzungsbedingungen Fassung zwei")
    status = client.get(cfg, headers=h1).json()
    assert (status["policy_terms_version"], status["approved_text_version"]) == ("NB-1", 2)
    assert status["in_sync"] is False

    # Mode follow_text: the next release moves the label automatically.
    put = client.put(cfg, json={"terms_version_mode": "follow_text"}, headers=h1)
    assert put.status_code == 200, put.text
    assert put.json()["terms_version_mode"] == "follow_text"
    _release(client, h1, h2, "nutzungsbedingungen", "Nutzungsbedingungen Fassung drei")
    assert client.get("/api/v1/consent-policy", headers=h1).json()["portal_terms_version"] == "NB-3"
    assert client.get(cfg, headers=h1).json()["in_sync"] is True
    # Other codes never touch the label.
    _release(client, h2, h1, "datenschutz", "Datenschutz Fassung eins")
    assert client.get("/api/v1/consent-policy", headers=h1).json()["portal_terms_version"] == "NB-3"
    # Back to manual.
    assert (
        client.put(cfg, json={"terms_version_mode": "manual"}, headers=h1).json()[
            "terms_version_mode"
        ]
        == "manual"
    )
