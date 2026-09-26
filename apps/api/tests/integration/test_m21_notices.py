"""Schwarzes Brett je Objekt (14, M21-01, A54): the management maintains notices at a property
(title, text, validity, audience, optional document, end); tenants and owners of that property
see only current notices of the matching audience in the portal; a second tenant reaches
nothing. Reading a notice writes no read receipt and is no delivery."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _doc, _ok, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
TODAY: date = datetime.now(tz=UTC).date()


def _d(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"nt-{RUN}", name=f"Aushang {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"nu-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("ntadmin", a), ("nuadmin", b)):
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
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _notice(
    c: TestClient, h: dict[str, str], prop: str, title: str, **fields: Any
) -> dict[str, Any]:
    body = {"title": title, "body": f"Text {title}", "valid_from": _d(0), "audience": "all"}
    body.update(fields)
    return dict(_ok(c.post(f"/api/v1/properties/{prop}/notices", json=body, headers=h), 201))


def _titles(c: TestClient, h: dict[str, str]) -> list[str]:
    return sorted(n["title"] for n in _ok(c.get(f"{P}/notices", headers=h)))


def test_notices_maintenance_and_portal_visibility(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ntadmin"))
    weg = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "821", "name": "Aushang-WEG", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    rental = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "822", "name": "Aushang-Miethaus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    owner_party, _ = _party(client, h, "AushangEig")
    owner_contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": _unit(client, h, weg["id"], "01"),
                "party_id": owner_party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(client, h, "AushangVermieter", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{rental['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    tenant_party, _ = _party(client, h, "AushangMieter")
    tenant_contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": _unit(client, h, rental["id"], "A"),
                "party_id": tenant_party,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    owner = _portal_user(client, h, world, "ntowner", _contact_of(client, h, owner_party))
    tenant = _portal_user(client, h, world, "nttenant", _contact_of(client, h, tenant_party))
    assert owner_contract["id"] != tenant_contract["id"]

    # Validation: audience, validity order, unknown document, unknown property.
    assert (
        client.post(
            f"/api/v1/properties/{weg['id']}/notices",
            json={"title": "x", "body": "y", "valid_from": _d(0), "audience": "staff"},
            headers=h,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/properties/{weg['id']}/notices",
            json={"title": "x", "body": "y", "valid_from": _d(1), "valid_to": _d(0)},
            headers=h,
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/properties/{weg['id']}/notices",
            json={
                "title": "x",
                "body": "y",
                "valid_from": _d(0),
                "document_id": "01920000-0000-7000-8000-000000000000",
            },
            headers=h,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/properties/01920000-0000-7000-8000-000000000000/notices",
            json={"title": "x", "body": "y", "valid_from": _d(0)},
            headers=h,
        ).status_code
        == 404
    )

    # Maintenance at the WEG: all, owner only, tenant only, future, expired, with document.
    # Review 1.22 Nr. 10: the attachment of a notice for all must be released for both groups.
    attachment = _doc(client, h, "Hausordnung", "property", weg["id"], ["tenant", "owner"])
    _notice(client, h, weg["id"], "WEG alle")
    _notice(client, h, weg["id"], "WEG Eigentuemer", audience="owner")
    _notice(client, h, weg["id"], "WEG Mieter", audience="tenant")
    _notice(client, h, weg["id"], "WEG kuenftig", valid_from=_d(1))
    _notice(client, h, weg["id"], "WEG abgelaufen", valid_from=_d(-10), valid_to=_d(-1))
    with_doc = _notice(
        client, h, weg["id"], "WEG Hausordnung", valid_to=_d(30), document_id=attachment
    )
    ended = _notice(client, h, weg["id"], "WEG beendet")
    _notice(client, h, rental["id"], "Miethaus alle")
    _notice(client, h, rental["id"], "Miethaus Eigentuemer", audience="owner")
    _notice(client, h, rental["id"], "Miethaus Mieter", audience="tenant", valid_to=_d(0))

    listed = _ok(client.get(f"/api/v1/properties/{weg['id']}/notices", headers=h))
    assert {n["title"] for n in listed} == {
        "WEG alle",
        "WEG Eigentuemer",
        "WEG Mieter",
        "WEG kuenftig",
        "WEG abgelaufen",
        "WEG Hausordnung",
        "WEG beendet",
    }
    by_title = {n["title"]: n for n in listed}
    assert by_title["WEG alle"]["is_current"] is True
    assert by_title["WEG kuenftig"]["is_current"] is False
    assert by_title["WEG abgelaufen"]["is_current"] is False

    # End: leaves the portal at once, stays in the CRM list, is no longer editable.
    ended_out = _ok(client.post(f"/api/v1/notices/{ended['id']}/end", headers=h))
    assert ended_out["ended_at"] is not None
    assert ended_out["is_current"] is False
    assert (
        client.patch(
            f"/api/v1/notices/{ended['id']}", json={"title": "spaeter"}, headers=h
        ).status_code
        == 409
    )
    assert "WEG beendet" in {
        n["title"] for n in _ok(client.get(f"/api/v1/properties/{weg['id']}/notices", headers=h))
    }

    # Portal: owner of the WEG sees "all" and "owner" of the WEG only (no tenant, no future,
    # no expired, no ended, nothing of the rental property).
    assert _titles(client, owner) == ["WEG Eigentuemer", "WEG Hausordnung", "WEG alle"]
    # Tenant of the rental property: "all" and "tenant" there, including the last valid day.
    assert _titles(client, tenant) == ["Miethaus Mieter", "Miethaus alle"]
    owner_rows = {n["title"]: n for n in _ok(client.get(f"{P}/notices", headers=owner))}
    assert owner_rows["WEG Hausordnung"]["has_document"] is True
    assert owner_rows["WEG Hausordnung"]["is_new"] is True
    assert owner_rows["WEG Hausordnung"]["property_number"] == "821"
    assert set(owner_rows["WEG alle"]) == {
        "id",
        "property_id",
        "property_number",
        "property_name",
        "title",
        "body",
        "valid_from",
        "valid_to",
        "has_document",
        "is_new",
        "created_at",
    }

    # Attachment follows the notice visibility; the tenant of the other property gets 404.
    assert (
        client.get(f"{P}/notices/{with_doc['id']}/document", headers=owner).content
        == b"Hausordnung"
    )
    assert client.get(f"{P}/notices/{with_doc['id']}/document", headers=tenant).status_code == 404
    # A notice attachment writes no read receipt: it is information, not a delivery.
    receipts = _ok(client.get(f"/api/v1/documents/{attachment}/portal-read-receipts", headers=h))
    assert receipts["items"] == []

    # Patch: audience change moves the notice between roles; clearing valid_to; ending date.
    patched = _ok(
        client.patch(
            f"/api/v1/notices/{by_title['WEG Mieter']['id']}",
            json={"audience": "all", "title": "WEG Mieter jetzt alle"},
            headers=h,
        )
    )
    assert patched["audience"] == "all"
    assert "WEG Mieter jetzt alle" in _titles(client, owner)
    _ok(
        client.patch(
            f"/api/v1/notices/{with_doc['id']}",
            json={"clear_valid_to": True, "clear_document": True},
            headers=h,
        )
    )
    assert client.get(f"{P}/notices/{with_doc['id']}/document", headers=owner).status_code == 404
    _ok(
        client.patch(
            f"/api/v1/notices/{by_title['WEG alle']['id']}",
            json={"valid_from": _d(-5), "valid_to": _d(-1)},
            headers=h,
        )
    )
    assert "WEG alle" not in _titles(client, owner)

    # Portal users cannot maintain notices (no CRM permission).
    assert (
        client.post(
            f"/api/v1/properties/{weg['id']}/notices",
            json={"title": "x", "body": "y", "valid_from": _d(0)},
            headers=owner,
        ).status_code
        == 403
    )
    assert client.get(f"/api/v1/properties/{weg['id']}/notices", headers=owner).status_code == 403

    # Tenant separation: the administrator of another tenant reaches nothing.
    hb = bearer(login(client, world, "nuadmin", tenant_id=world.tenant_b))
    assert client.get(f"/api/v1/properties/{weg['id']}/notices", headers=hb).status_code == 404
    assert (
        client.patch(
            f"/api/v1/notices/{with_doc['id']}", json={"title": "fremd"}, headers=hb
        ).status_code
        == 404
    )
    assert client.post(f"/api/v1/notices/{with_doc['id']}/end", headers=hb).status_code == 404
    assert (
        client.post(
            f"/api/v1/properties/{weg['id']}/notices",
            json={"title": "x", "body": "y", "valid_from": _d(0)},
            headers=hb,
        ).status_code
        == 404
    )
