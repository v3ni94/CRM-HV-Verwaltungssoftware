"""AE10 / AA07-01: allocation variant per acquisition kind (tenant rule, default manual release).

Expected values (hand derived): without a rule every kind is ``manual_release`` and
``allocation_owner`` returns ``owner_at(default_day)`` unchanged. Unit 01 changes owner by
inheritance on 01.03.2026: due 15.02.2026 (old owner), resolution 10.06.2026 (new owner).
``by_due_date`` picks the old owner, ``by_resolution_date`` the new one, ``manual_release`` the
owner of the default day (here the resolution day, so the new owner)."""

import asyncio
from collections.abc import Iterator
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.hoa import acquisition_rule, calc
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import _settings
from tests.integration.test_m21_portal_owner import _ok
from tests.integration.test_m24_hoa import _hoa_ledger

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae10a-{RUN}", name=f"AE10 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae10b-{RUN}", name=f"AE10 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae10admin", a, "tenant_admin"),
            ("ae10reader", a, "read_only"),
            ("ae10other", b, "tenant_admin"),
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


def test_rules_default_put_validation_and_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae10admin"))
    hr = bearer(login(client, world, "ae10reader"))
    ho = bearer(login(client, world, "ae10other"))
    listed = _ok(client.get(f"{H}/acquisition-rules", headers=h))
    assert [i["variant"] for i in listed["items"]] == ["manual_release"] * 6
    assert all(i["is_default"] for i in listed["items"])
    assert listed["note"]
    put = _ok(
        client.put(
            f"{H}/acquisition-rules/inheritance",
            json={"variant": "by_due_date", "source_note": "Gutachten Anwalt"},
            headers=h,
        )
    )
    assert (put["variant"], put["is_default"]) == ("by_due_date", False)
    again = _ok(
        client.put(
            f"{H}/acquisition-rules/inheritance", json={"variant": "by_resolution_date"}, headers=h
        )
    )
    assert again["variant"] == "by_resolution_date"
    items = {
        i["acquisition_kind"]: i
        for i in _ok(client.get(f"{H}/acquisition-rules", headers=h))["items"]
    }
    assert items["inheritance"]["variant"] == "by_resolution_date"
    assert items["gift"]["variant"] == "manual_release"
    # other tenant sees defaults only; reader may read but not write; validation 422
    other = _ok(client.get(f"{H}/acquisition-rules", headers=ho))["items"]
    assert all(i["is_default"] for i in other)
    assert client.get(f"{H}/acquisition-rules", headers=hr).status_code == 200
    body = {"variant": "by_due_date"}
    assert client.put(f"{H}/acquisition-rules/gift", json=body, headers=hr).status_code == 403
    assert (
        client.put(f"{H}/acquisition-rules/gift", json={"variant": "x"}, headers=h).status_code
        == 422
    )
    assert client.put(f"{H}/acquisition-rules/nope", json=body, headers=h).status_code == 422
    assert client.put(f"{H}/acquisition-rules/gift", json={}, headers=h).status_code == 422
    assert client.get(f"{H}/acquisition-rules?x=1", headers=h).status_code == 422


def test_listing_shows_variant_of_special_acquisition(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae10admin"))
    w = _hoa_ledger(client, h, "981")
    unit = _unit(client, h, w["property"], "01")
    party, _ = _party(client, h, "AE10Erbe")
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2026-03-01",
                "title_transfer_date": "2026-03-01",
                "acquisition_kind": "foreclosure",
            },
            headers=h,
        ),
        201,
    )
    st = _ok(
        client.post(f"{H}/statements", json={"ledger_id": w["ledger"], "year": 2026}, headers=h),
        201,
    )
    _ok(
        client.put(f"{H}/acquisition-rules/foreclosure", json={"variant": "by_due_date"}, headers=h)
    )
    items = _ok(client.get(f"{H}/statements/{st['id']}/acquisitions", headers=h))["items"]
    assert [(i["acquisition_kind"], i["allocation_variant"]) for i in items] == [
        ("foreclosure", "by_due_date")
    ]


DUE, RESOLUTION = date(2026, 2, 15), date(2026, 6, 10)


@pytest.mark.parametrize(
    ("variant", "expected"),
    [
        ("manual_release", "new"),
        ("by_due_date", "old"),
        ("by_resolution_date", "new"),
    ],
)
def test_allocation_owner_per_variant(
    monkeypatch: pytest.MonkeyPatch, variant: str, expected: str
) -> None:
    new = SimpleNamespace(name="new", acquisition_kind=SimpleNamespace(value="inheritance"))
    old = SimpleNamespace(name="old", acquisition_kind=None)

    async def fake_owner_at(_s: Any, _u: Any, day: date) -> Any:
        return old if day < date(2026, 3, 1) else new

    async def fake_variant(_s: Any, kind: str | None) -> str:
        assert kind == "inheritance"
        return variant

    monkeypatch.setattr(calc, "owner_at", fake_owner_at)
    monkeypatch.setattr(acquisition_rule, "resolve_variant", fake_variant)
    got = asyncio.run(
        calc.allocation_owner(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            default_day=RESOLUTION,
            due_day=DUE,
            resolution_day=RESOLUTION,
        )
    )
    assert got.name == expected


def test_pick_day_defaults_unchanged() -> None:
    kw = {"default_day": RESOLUTION, "due_day": None, "resolution_day": None}
    for v in acquisition_rule.VARIANTS:
        assert acquisition_rule.pick_day(v, **kw) == RESOLUTION
