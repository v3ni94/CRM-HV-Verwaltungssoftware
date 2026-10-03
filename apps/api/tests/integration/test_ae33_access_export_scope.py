"""AE33 (AC07-01, 7.11 S06): scope of the data subject access export as tenant switches. The
defaults are the conservative variant (other persons by role only, internal notes withheld);
a wider scope shows names and the notes but never contact data or secrets; the scope is frozen
when the export is prepared, so a later change of the switches cannot alter a reviewed
export."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
SETTINGS = "/api/v1/contact-access-export-settings"
PLACEHOLDER = "Dritte Person (Angaben zurückgehalten)"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae33c-{RUN}", name=f"AE33 C {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae33d-{RUN}", name=f"AE33 D {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae33xprep", a, "tenant_admin"),
            ("ae33xrev", a, "tenant_admin"),
            ("ae33xview", a, "read_only"),
            ("ae33xother", b, "tenant_admin"),
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def _setup(client: TestClient, h: dict[str, str]) -> str:
    subject = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Clara",
                "last_name": f"Scope{RUN}",
                "notes": "Interner Vermerk: schwieriger Kontakt",
                "bank_accounts": [
                    {
                        "iban": "DE02 1203 0000 0000 2020 51",
                        "valid_from": "2026-01-01",
                        "holder": f"Fremd{RUN}, Dora",
                    }
                ],
            },
            headers=h,
        ),
        201,
    )
    third = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Dora",
                "last_name": f"Fremd{RUN}",
                "emails": [{"email": f"dora.{RUN}@example.org"}],
                "addresses": [{"street": "Geheimweg", "house_number": "9", "city": "Nirgendwo"}],
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/parties",
            json={
                "members": [
                    {"contact_id": subject["id"], "role": "primary", "share_percent": "50"},
                    {"contact_id": third["id"], "role": "co_party", "share_percent": "50"},
                ]
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/contacts/{subject['id']}/relations",
            json={"related_contact_id": third["id"], "kind": "spouse"},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/contacts/{subject['id']}/notes",
            json={"body": "Geheimer Rückrufvermerk", "title": "Rückruf"},
            headers=h,
        ),
        201,
    )
    return str(subject["id"])


def _released_download(
    client: TestClient, contact_id: str, prep: dict[str, str], rev: dict[str, str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    base = f"/api/v1/contacts/{contact_id}/access-exports"
    export = _ok(client.post(base, headers=prep), 201)
    url = f"{base}/{export['id']}"
    _ok(client.post(f"{url}/review", headers=rev))
    _ok(client.post(f"{url}/approve", headers=rev))
    return export, _ok(client.get(f"{url}/download", headers=prep))  # type: ignore[no-any-return]


def test_settings_default_permissions_validation_and_tenant_separation(
    client: TestClient, world: World
) -> None:
    prep = bearer(login(client, world, "ae33xprep"))
    viewer = bearer(login(client, world, "ae33xview"))
    other = bearer(login(client, world, "ae33xother"))
    assert _ok(client.get(SETTINGS, headers=prep)) == {
        "third_party_scope": "none",
        "include_internal_notes": False,
        # GAI-506 (AJ13): further sources, off by default.
        "include_tickets": False,
        "include_communication": False,
        "include_documents": False,
        # GAI-506 (AK06): portal account, payments and contracts, off by default.
        "include_portal_account": False,
        "include_payments": False,
        "include_contracts": False,
    }
    wide = {"third_party_scope": "names", "include_internal_notes": True}
    wide_out = {
        **wide,
        "include_tickets": False,
        "include_communication": False,
        "include_documents": False,
        "include_portal_account": False,
        "include_payments": False,
        "include_contracts": False,
    }
    assert client.put(SETTINGS, json=wide, headers=viewer).status_code == 403
    assert client.put(SETTINGS, json={"third_party_scope": "all"}, headers=prep).status_code == 422
    assert client.put(SETTINGS, json={"x": 1}, headers=prep).status_code == 422
    assert client.get(SETTINGS, params={"x": "1"}, headers=prep).status_code == 422
    assert _ok(client.put(SETTINGS, json=wide, headers=prep)) == wide_out
    assert _ok(client.get(SETTINGS, headers=viewer)) == wide_out
    assert _ok(client.get(SETTINGS, headers=other))["third_party_scope"] == "none"
    _ok(client.put(SETTINGS, json={}, headers=prep))
    assert _ok(client.get(SETTINGS, headers=prep))["include_internal_notes"] is False


def test_default_scope_keeps_third_parties_and_notes_out(client: TestClient, world: World) -> None:
    prep = bearer(login(client, world, "ae33xprep"))
    rev = bearer(login(client, world, "ae33xrev"))
    _ok(client.put(SETTINGS, json={}, headers=prep))
    contact_id = _setup(client, prep)
    export, data = _released_download(client, contact_id, prep, rev)
    text = str(data)
    assert export["third_party_scope"] == "none"
    assert export["internal_notes_included"] is False
    assert "Dora" not in text
    assert f"Fremd{RUN}" not in text
    assert "Geheimer Rückrufvermerk" not in text
    assert "schwieriger Kontakt" not in text
    assert "internal_notes" not in data
    assert data["withheld"]["internal_notes_count"] == 2
    assert "internal_notes" in data["withheld"]["categories"]
    assert data["relations"] == [{"kind": "spouse", "related_person": PLACEHOLDER}]
    assert data["parties"] == [{"own_role": "primary", "further_members": 1}]


def test_wider_scope_shows_names_and_notes_but_no_contact_data(
    client: TestClient, world: World
) -> None:
    prep = bearer(login(client, world, "ae33xprep"))
    rev = bearer(login(client, world, "ae33xrev"))
    contact_id = _setup(client, prep)
    _ok(
        client.put(
            SETTINGS,
            json={"third_party_scope": "names", "include_internal_notes": True},
            headers=prep,
        )
    )
    export, data = _released_download(client, contact_id, prep, rev)
    text = str(data)
    assert export["third_party_scope"] == "names"
    assert export["internal_notes_included"] is True
    # Names and roles of the other person.
    assert data["relations"] == [{"kind": "spouse", "related_person": f"Fremd{RUN}, Dora"}]
    assert data["parties"] == [
        {
            "own_role": "primary",
            "further_members": 1,
            "members": [{"name": f"Fremd{RUN}, Dora", "role": "co_party"}],
        }
    ]
    assert data["bank_accounts"][0]["holder"] == f"Fremd{RUN}, Dora"
    # Never contact data of the other person.
    assert "Geheimweg" not in text
    assert f"dora.{RUN}@example.org" not in text
    # Internal notes without author or pin state.
    assert data["internal_notes"]["contact_note"] == "Interner Vermerk: schwieriger Kontakt"
    assert [n["body"] for n in data["internal_notes"]["notes"]] == ["Geheimer Rückrufvermerk"]
    assert not {"created_by", "updated_by", "pinned", "id"} & set(
        data["internal_notes"]["notes"][0]
    )
    assert "internal_notes_count" not in data["withheld"]
    assert "internal_notes" not in data["withheld"]["categories"]
    assert "Namen und Rolle" in data["withheld"]["categories"]["third_parties"]
    # Secrets stay out in every scope.
    assert "fingerprint" not in text
    assert not {k for k in _keys(data) if "hash" in k or "token" in k}
    _ok(client.put(SETTINGS, json={}, headers=prep))


def test_scope_is_frozen_at_preparation(client: TestClient, world: World) -> None:
    prep = bearer(login(client, world, "ae33xprep"))
    rev = bearer(login(client, world, "ae33xrev"))
    contact_id = _setup(client, prep)
    base = f"/api/v1/contacts/{contact_id}/access-exports"
    _ok(client.put(SETTINGS, json={}, headers=prep))
    narrow = _ok(client.post(base, headers=prep), 201)
    _ok(
        client.put(
            SETTINGS,
            json={"third_party_scope": "names", "include_internal_notes": True},
            headers=prep,
        )
    )
    wide = _ok(client.post(base, headers=prep), 201)
    _ok(client.put(SETTINGS, json={}, headers=prep))
    # Both exports keep the scope they were prepared with, whatever the switches say now.
    for export, scope, notes in ((narrow, "none", False), (wide, "names", True)):
        url = f"{base}/{export['id']}"
        shown = _ok(client.get(f"{url}/preview", headers=rev))
        assert ("internal_notes" in shown) is notes
        _ok(client.post(f"{url}/review", headers=rev))
        _ok(client.post(f"{url}/approve", headers=rev))
        data = _ok(client.get(f"{url}/download", headers=prep))
        assert ("internal_notes" in data) is notes
        listed = next(x for x in _ok(client.get(base, headers=prep)) if x["id"] == export["id"])
        assert listed["third_party_scope"] == scope
        assert listed["internal_notes_included"] is notes
        assert listed["downloads"] == 1
