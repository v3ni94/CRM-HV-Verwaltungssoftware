"""Contact fields of section 4.1 (Masterprompt Ergänzung 27.09.2026, AP1, migration 0147):
letter salutation, state, phone prefixes, typed dates, bank account type and default flag,
block date, retention profile with deletion reservation, follow up on notes, block list."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.contacts import services
from mhvp.core.clock import local_today
from mhvp.documents.models import RetentionStart
from mhvp.main import create_app
from mhvp.platform import services as platform
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await platform.provision_tenant(factory, slug=f"cp-{RUN}", name=f"P1 A {RUN}")
        b, _ = await platform.provision_tenant(factory, slug=f"cq-{RUN}", name=f"P1 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("admin", a, "tenant_admin"),
            ("second", a, "tenant_admin"),
            ("other", b, "tenant_admin"),
        ]:
            uid = await platform.create_user(
                factory, email=world.email(f"p1{name}"), display_name=name, password=PASSWORD
            )
            world.users[f"p1{name}"] = uid
            await platform.add_member(
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


def _ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _person(suffix: str) -> dict[str, Any]:
    return {
        "kind": "person",
        "salutation": "Herr",
        "letter_salutation": "Sehr geehrter Herr Beispiel",
        "first_name": "Max",
        "last_name": f"Beispiel{RUN}{suffix}",
        "addresses": [
            {
                "label": "postal",
                "street": "Ringstraße",
                "house_number": "7",
                "postal_code": "40213",
                "city": "Düsseldorf",
                "state": "Nordrhein-Westfalen",
            }
        ],
        "phones": [
            {
                "label": "work",
                "number": "0211 123456",
                "country_code": "+49",
                "area_code": "0211",
                "note": "Durchwahl 12",
            }
        ],
        "emails": [
            {"email": f"max.{suffix}.{RUN}@example.org", "is_portal_login": True},
            {"label": "private", "email": f"privat.{suffix}.{RUN}@example.org"},
        ],
        "dates": [{"kind": "wedding", "date": "2010-06-12", "note": "Standesamt"}],
        "bank_accounts": [
            {
                "iban": "DE02120300000000202051",
                "valid_from": "2026-01-01",
                "kind": "rent",
                "is_default": True,
            },
            {"iban": "DE02500105170137075030", "valid_from": "2026-01-01", "kind": "deposit"},
        ],
    }


def test_fields_roundtrip(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p1admin"))
    body = _ok(client.post("/api/v1/contacts", json=_person("a"), headers=h))
    assert body["letter_salutation"] == "Sehr geehrter Herr Beispiel"
    assert body["addresses"][0]["state"] == "Nordrhein-Westfalen"
    phone = body["phones"][0]
    assert (phone["country_code"], phone["area_code"], phone["note"]) == (
        "+49",
        "0211",
        "Durchwahl 12",
    )
    assert body["dates"] == [
        {
            "id": body["dates"][0]["id"],
            "kind": "wedding",
            "date": "2010-06-12",
            "note": "Standesamt",
        }
    ]
    logins = [e for e in body["emails"] if e["is_portal_login"]]
    assert len(logins) == 1
    assert logins[0]["email"].startswith("max.a.")
    defaults = [b for b in body["bank_accounts"] if b["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["kind"] == "rent"
    assert body["blocked_at"] is None
    assert body["delete_after"] is None
    assert body["retention_profile_id"] is None

    changed = dict(_person("a"), dates=[{"kind": "birthday", "date": "1980-01-02"}])
    changed.pop("bank_accounts")  # omitted: accounts stay, the default flag is kept
    updated = _ok(
        client.put(
            f"/api/v1/contacts/{body['id']}",
            json=changed,
            headers=h | {"If-Match": f'"{body["version"]}"'},
        ),
        200,
    )
    assert [d["kind"] for d in updated["dates"]] == ["birthday"]
    assert sum(1 for b in updated["bank_accounts"] if b["is_default"]) == 1


@pytest.mark.parametrize(
    ("patch", "field"),
    [
        (
            {
                "bank_accounts": [
                    {
                        "iban": "DE02120300000000202051",
                        "valid_from": "2026-01-01",
                        "is_default": True,
                    },
                    {
                        "iban": "DE02500105170137075030",
                        "valid_from": "2026-01-01",
                        "is_default": True,
                    },
                ]
            },
            "body",
        ),
        (
            {
                "emails": [
                    {"email": f"eins.{RUN}@example.org", "is_portal_login": True},
                    {"email": f"zwei.{RUN}@example.org", "is_portal_login": True},
                ]
            },
            "body",
        ),
        ({"phones": [{"number": "0211 123456", "country_code": "abc"}]}, "country_code"),
    ],
)
def test_exactly_one_default_and_portal_login(
    client: TestClient, world: World, patch: dict[str, Any], field: str
) -> None:
    h = bearer(login(client, world, "p1admin"))
    response = client.post("/api/v1/contacts", json=dict(_person("v"), **patch), headers=h)
    assert response.status_code == 422, response.text
    assert field in response.text


def test_block_sets_date_and_block_list(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p1admin"))
    body = _ok(client.post("/api/v1/contacts", json=_person("b"), headers=h))
    contact_id = body["id"]
    blocked = _ok(
        client.put(
            f"/api/v1/contacts/{contact_id}",
            json=dict(_person("b"), blocked=True, bank_accounts=None),
            headers=h,
        ),
        200,
    )
    assert blocked["blocked"] is True
    assert blocked["blocked_at"] is not None
    first_blocked_at = blocked["blocked_at"]

    listed = _ok(client.get("/api/v1/contacts", params={"blocked": "true"}, headers=h), 200)
    assert contact_id in {c["id"] for c in listed["items"]}
    unblocked_list = _ok(
        client.get("/api/v1/contacts", params={"blocked": "false"}, headers=h), 200
    )
    assert contact_id not in {c["id"] for c in unblocked_list["items"]}

    # A second save while blocked keeps the original block date.
    again = _ok(
        client.put(
            f"/api/v1/contacts/{contact_id}",
            json=dict(_person("b"), blocked=True, bank_accounts=None, position="Beirat"),
            headers=h,
        ),
        200,
    )
    assert again["blocked_at"] == first_blocked_at

    lifted = _ok(
        client.put(
            f"/api/v1/contacts/{contact_id}",
            json=dict(_person("b"), blocked=False, bank_accounts=None),
            headers=h,
        ),
        200,
    )
    assert lifted["blocked_at"] is None


def test_retention_profile_reservation_only(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p1admin"))
    profile = _ok(
        client.post(
            "/api/v1/retention-profiles",
            json={
                "document_class": f"kontakt-{RUN}",
                "legal_basis": "R18 (Prüfung Steuerberatung offen)",
                "retention_years": 2,
                "retention_months": 6,
                "start_rule": "purpose_end",
            },
            headers=h,
        )
    )
    contact = _ok(client.post("/api/v1/contacts", json=_person("r"), headers=h))
    contact_id = contact["id"]
    payload = dict(_person("r"), bank_accounts=None, retention_profile_id=profile["id"])
    draft = client.put(f"/api/v1/contacts/{contact_id}", json=payload, headers=h)
    assert draft.status_code == 422
    assert "nicht freigegeben" in draft.text

    second = bearer(login(client, world, "p1second"))
    _ok(client.post(f"/api/v1/retention-profiles/{profile['id']}/release", headers=second), 200)
    today = local_today()
    assigned = _ok(client.put(f"/api/v1/contacts/{contact_id}", json=payload, headers=h), 200)
    assert assigned["retention_profile_id"] == profile["id"]
    expected = services.delete_after(
        _profile(2, 6, RetentionStart.PURPOSE_END), blocked_at=None, reference=today
    )
    assert assigned["delete_after"] == expected.isoformat()  # type: ignore[union-attr]

    # Reservation only: the contact stays readable and active, nothing is deleted.
    assert _ok(client.get(f"/api/v1/contacts/{contact_id}", headers=h), 200)["deleted_at"] is None

    unknown = client.put(
        f"/api/v1/contacts/{contact_id}",
        json=dict(payload, retention_profile_id=str(uuid.uuid4())),
        headers=h,
    )
    assert unknown.status_code == 422

    # Blocking moves the start of the period to the block date; releasing the profile clears it.
    blocked = _ok(
        client.put(f"/api/v1/contacts/{contact_id}", json=dict(payload, blocked=True), headers=h),
        200,
    )
    assert blocked["delete_after"] == expected.isoformat()  # type: ignore[union-attr]
    cleared = _ok(
        client.put(
            f"/api/v1/contacts/{contact_id}",
            json=dict(payload, retention_profile_id=None),
            headers=h,
        ),
        200,
    )
    assert cleared["delete_after"] is None
    assert cleared["retention_profile_id"] is None


class _Profile:
    def __init__(self, years: int, months: int, rule: RetentionStart, permanent: bool = False):
        self.retention_years = years
        self.retention_months = months
        self.start_rule = rule
        self.permanent = permanent


def _profile(years: int, months: int, rule: RetentionStart, permanent: bool = False) -> Any:
    return _Profile(years, months, rule, permanent)


@pytest.mark.parametrize(
    ("profile", "blocked_at", "expected"),
    [
        (_profile(2, 6, RetentionStart.PURPOSE_END), None, date(2028, 9, 26)),
        (
            _profile(1, 0, RetentionStart.END_OF_YEAR_CREATED),
            datetime(2026, 3, 1, tzinfo=UTC),
            date(2027, 12, 31),
        ),
        (
            _profile(0, 1, RetentionStart.PURPOSE_END),
            datetime(2026, 1, 31, tzinfo=UTC),
            date(2026, 2, 28),
        ),
        (_profile(10, 0, RetentionStart.CONTRACT_END, permanent=True), None, None),
        (None, None, None),
    ],
)
def test_delete_after_arithmetic(
    profile: Any, blocked_at: datetime | None, expected: date | None
) -> None:
    assert (
        services.delete_after(profile, blocked_at=blocked_at, reference=date(2026, 3, 26))
        == expected
    )


def test_tenant_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p1admin"))
    contact = _ok(client.post("/api/v1/contacts", json=_person("t"), headers=h))
    other = bearer(login(client, world, "p1other"))
    assert client.get(f"/api/v1/contacts/{contact['id']}", headers=other).status_code == 404
    listed = _ok(
        client.get("/api/v1/contacts", params={"q": f"Beispiel{RUN}t"}, headers=other), 200
    )
    assert listed["total"] == 0
    assert (
        client.post(
            f"/api/v1/contacts/{contact['id']}/notes",
            json={"body": "fremd", "follow_up_on": "2026-10-01"},
            headers=other,
        ).status_code
        == 404
    )


def test_note_with_title_and_follow_up(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p1admin"))
    contact = _ok(client.post("/api/v1/contacts", json=_person("n"), headers=h))
    note = _ok(
        client.post(
            f"/api/v1/contacts/{contact['id']}/notes",
            json={
                "title": "Rückruf",
                "body": "Bitte Rückruf wegen Abrechnung",
                "category": "telefon",
                "follow_up_on": "2026-10-15",
            },
            headers=h,
        )
    )
    assert note["title"] == "Rückruf"
    assert note["follow_up_on"] == "2026-10-15"
    listed = _ok(client.get(f"/api/v1/contacts/{contact['id']}/notes", headers=h), 200)
    assert listed[0]["follow_up_on"] == "2026-10-15"
