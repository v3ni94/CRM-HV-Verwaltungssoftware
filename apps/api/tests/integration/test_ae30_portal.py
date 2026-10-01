"""AE30 (AA14-01, AA14-02): form builder with 20 element types (type register, preview as dry
run, check per type at the submission) and provider ratings in the portal administration
behind a tenant switch (default off, management only, no free text, nothing for the provider).
Other tenant keeps its own switch and sees no data, read only role 403 on the switch, bad value
422, unknown query parameter 422."""

import asyncio
from collections.abc import Iterator
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
from tests.integration.test_m21_portal import _ok, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"
F = f"{PA}/features"
RATINGS = f"{PA}/provider-ratings"
SECRET_COMMENT = "AE30 interner Freitext"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae30a-{RUN}", name=f"AE30 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae30b-{RUN}", name=f"AE30 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("ae30admin", a, "tenant_admin"),
            ("ae30adminb", b, "tenant_admin"),
            ("ae30ro", a, "read_only"),
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


def _provider_with_rating(
    c: TestClient, h: dict[str, str], no: str, rating: int | None
) -> tuple[str, str, str]:
    """A provider contact with one completed and, if ``rating`` is given, rated work order;
    returns provider, order and property id."""
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": no, "name": f"AE30-Objekt {no}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    provider = _ok(
        c.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"AE30 Handwerk {no} {RUN} GmbH"},
            headers=h,
        ),
        201,
    )["id"]
    order = _ok(
        c.post(
            "/api/v1/work-orders",
            json={
                "property_id": prop["id"],
                "provider_contact_id": provider,
                "description": "Heizung instand setzen",
            },
            headers=h,
        ),
        201,
    )
    steps = f"/api/v1/work-orders/{order['id']}/steps"
    for status in ("requested", "approved", "in_progress"):
        _ok(c.post(steps, json={"status": status}, headers=h))
    _ok(c.post(steps, json={"status": "done", "completion_report": "erledigt"}, headers=h))
    accept: dict[str, Any] = {"status": "accepted"}
    if rating is not None:
        accept |= {"rating": rating, "rating_comment": SECRET_COMMENT}
    _ok(c.post(steps, json=accept, headers=h))
    return provider, order["id"], prop["id"]


# AA14-01 ----------------------------------------------------------------------------------


def test_element_types_and_preview(client: TestClient, world: World) -> None:
    ha = bearer(login(client, world, "ae30admin"))
    ro = bearer(login(client, world, "ae30ro"))

    types = _ok(client.get(f"{PA}/forms/element-types", headers=ro))
    assert len(types) == 20
    assert {t["kind"] for t in types} == {"input", "display"}
    assert all("AA14-01" in t["source_status"] for t in types)
    assert client.get(f"{PA}/forms/element-types?x=1", headers=ro).status_code == 422
    assert client.get(f"{PA}/forms/element-types").status_code == 401

    forms_before = _ok(client.get(f"{PA}/forms", headers=ha))
    tickets_before = _ok(client.get("/api/v1/tickets", headers=ha))
    fields = [
        {"key": "anschrift", "label": "Anschrift", "type": "address", "required": True},
        {"key": "ort", "label": "Standort", "type": "location"},
        {"key": "name", "label": "Unterschrift", "type": "signature", "required": True},
        {"key": "betrag", "label": "Betrag", "type": "amount"},
        {"key": "ok", "label": "Einwilligung", "type": "consent", "required": True},
        {"key": "linie", "label": "Trennlinie", "type": "divider"},
    ]
    good = {
        "anschrift": "Musterweg 1, 40822 Mettmann",
        "name": "Max Muster",
        "betrag": "1234,5",
        "ok": "true",
    }
    ok = _ok(
        client.post(f"{PA}/forms/preview", json={"fields": fields, "values": good}, headers=ro)
    )
    assert ok["valid"] is True
    assert "Betrag: 1.234,50 EUR" in ok["rendered"]
    assert "Anschrift: Musterweg 1, 40822 Mettmann" in ok["rendered"]
    bad = _ok(
        client.post(
            f"{PA}/forms/preview",
            json={"fields": fields, "values": {**good, "anschrift": "Musterweg 1", "name": "M"}},
            headers=ro,
        )
    )
    assert bad["valid"] is False
    assert {e["field"] for e in bad["errors"]} == {"values.anschrift", "values.name"}
    # a defect of the definition is a 422, an unknown field in the body as well
    broken = [{"key": "a", "label": "A", "type": "select"}]
    assert (
        client.post(
            f"{PA}/forms/preview", json={"fields": broken, "values": {}}, headers=ha
        ).status_code
        == 422
    )
    assert (
        client.post(f"{PA}/forms/preview", json={"fields": [], "extra": 1}, headers=ha).status_code
        == 422
    )
    assert client.post(f"{PA}/forms/preview", json={"fields": []}).status_code == 401
    # dry run: nothing saved, no ticket
    assert _ok(client.get(f"{PA}/forms", headers=ha)) == forms_before
    assert _ok(client.get("/api/v1/tickets", headers=ha)) == tickets_before


def test_submission_uses_the_type_rules(client: TestClient, world: World) -> None:
    ha = bearer(login(client, world, "ae30admin"))
    ro = bearer(login(client, world, "ae30ro"))
    template = _ok(
        client.post(
            f"{PA}/forms",
            json={
                "name": "AE30 Adressänderung",
                "category": "Antrag",
                "audience": "all",
                "fields": [
                    {
                        "key": "anschrift",
                        "label": "Neue Anschrift",
                        "type": "address",
                        "required": True,
                    },
                    {"key": "name", "label": "Unterschrift", "type": "signature", "required": True},
                ],
            },
            headers=ha,
        ),
        201,
    )
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Mia", "last_name": f"AE30{RUN}"},
            headers=ha,
        ),
        201,
    )["id"]
    portal = _portal_user(client, ha, world, "ae30portal1", contact)
    url = f"{P}/forms/{template['id']}/submissions"
    short = client.post(
        url, json={"values": {"anschrift": "Musterweg 1", "name": "Mia Muster"}}, headers=portal
    )
    assert short.status_code == 422
    assert [e["field"] for e in short.json()["errors"]] == ["values.anschrift"]
    created = _ok(
        client.post(
            url,
            json={"values": {"anschrift": "Musterweg 1\n40822 Mettmann", "name": " Mia  Muster "}},
            headers=portal,
        ),
        201,
    )
    ticket = _ok(client.get(f"/api/v1/tickets/{created['ticket_id']}", headers=ha))
    text = ticket["public_description"]
    assert "Neue Anschrift: Musterweg 1, 40822 Mettmann" in text
    assert "Unterschrift: Mia Muster" in text
    # the read only member cannot change templates but may preview
    assert client.post(f"{PA}/forms/preview", json={"fields": []}, headers=ro).status_code == 200
    assert (
        client.patch(f"{PA}/forms/{template['id']}", json={"active": False}, headers=ro).status_code
        == 403
    )


# AA14-02 ----------------------------------------------------------------------------------


def test_provider_ratings_behind_switch(client: TestClient, world: World) -> None:
    ha = bearer(login(client, world, "ae30admin"))
    hb = bearer(login(client, world, "ae30adminb"))
    ro = bearer(login(client, world, "ae30ro"))
    provider, _, prop = _provider_with_rating(client, ha, "941", 4)
    other, _, _ = _provider_with_rating(client, ha, "942", 5)
    unrated, _, _ = _provider_with_rating(client, ha, "943", None)

    # default off: switch visible to the management, no data in the view
    features = _ok(client.get(F, headers=ha))
    assert features["provider_rating_display"] == "off"
    off = _ok(client.get(RATINGS, headers=ha))
    assert off["enabled"] is False
    assert off["mode"] == "off"
    assert off["providers"] == []
    assert SECRET_COMMENT not in str(off)

    # validation, permission, unknown parameter
    assert client.patch(F, json={"provider_rating_display": "all"}, headers=ha).status_code == 422
    assert client.patch(F, json={"provider_rating_display": "staff"}, headers=ro).status_code == 403
    assert client.get(f"{RATINGS}?x=1", headers=ha).status_code == 422
    assert client.get(RATINGS).status_code == 401

    # staff: aggregated per provider, no free text
    _ok(client.patch(F, json={"provider_rating_display": "staff"}, headers=ha))
    on = _ok(client.get(RATINGS, headers=ha))
    assert on["enabled"] is True
    assert SECRET_COMMENT not in str(on)
    by_id = {p["provider_contact_id"]: p for p in on["providers"]}
    assert set(by_id) == {provider, other}  # the unrated order is not part of it
    assert by_id[provider]["rated_count"] == 1
    assert by_id[provider]["average"] == "4.0"
    assert by_id[provider]["distribution"] == {"1": 0, "2": 0, "3": 0, "4": 1, "5": 0}
    assert unrated not in by_id
    assert all("rating_comment" not in p for p in on["providers"])
    # reading needs only the right to read tickets
    assert _ok(client.get(RATINGS, headers=ro))["enabled"] is True

    # a second rating for the same provider changes count and mean
    _provider_with_rating_again(client, ha, provider, prop, 5)
    again = {p["provider_contact_id"]: p for p in _ok(client.get(RATINGS, headers=ha))["providers"]}
    assert again[provider]["rated_count"] == 2
    assert again[provider]["average"] == "4.5"

    # the other tenant has its own switch and sees nothing of tenant A
    assert _ok(client.get(F, headers=hb))["provider_rating_display"] == "off"
    _ok(client.patch(F, json={"provider_rating_display": "staff"}, headers=hb))
    b_view = _ok(client.get(RATINGS, headers=hb))
    assert b_view["enabled"] is True
    assert b_view["providers"] == []
    _ok(client.patch(F, json={"provider_rating_display": "off"}, headers=hb))

    # switching back hides the data again
    _ok(client.patch(F, json={"provider_rating_display": "off"}, headers=ha))
    assert _ok(client.get(RATINGS, headers=ha))["providers"] == []


def _provider_with_rating_again(
    c: TestClient, h: dict[str, str], provider: str, prop_id: str, rating: int
) -> None:
    order = _ok(
        c.post(
            "/api/v1/work-orders",
            json={
                "property_id": prop_id,
                "provider_contact_id": provider,
                "description": "Zweiter Auftrag",
            },
            headers=h,
        ),
        201,
    )
    steps = f"/api/v1/work-orders/{order['id']}/steps"
    for status in ("requested", "approved", "in_progress"):
        _ok(c.post(steps, json={"status": status}, headers=h))
    _ok(c.post(steps, json={"status": "done", "completion_report": "ok"}, headers=h))
    _ok(c.post(steps, json={"status": "accepted", "rating": rating}, headers=h))


def test_provider_never_sees_the_rating(client: TestClient, world: World) -> None:
    ha = bearer(login(client, world, "ae30admin"))
    provider, _, _ = _provider_with_rating(client, ha, "951", 3)
    _ok(client.patch(F, json={"provider_rating_display": "staff"}, headers=ha))
    try:
        portal = _portal_user(client, ha, world, "ae30provider", provider)
        orders = _ok(client.get(f"{P}/work-orders", headers=portal))
        assert orders, "the provider sees its own order"
        assert all("rating" not in o and "rating_comment" not in o for o in orders)
        assert SECRET_COMMENT not in str(orders)
        me = _ok(client.get(f"{P}/me", headers=portal))
        assert "provider_rating_display" not in me["features"]
        # no portal route for ratings, and the administration view refuses portal users
        assert client.get(f"{P}/provider/ratings", headers=portal).status_code == 404
        assert client.get(RATINGS, headers=portal).status_code in (401, 403)
        assert client.get(F, headers=portal).status_code in (401, 403)
    finally:
        _ok(client.patch(F, json={"provider_rating_display": "off"}, headers=ha))
