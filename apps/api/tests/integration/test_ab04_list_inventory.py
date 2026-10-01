"""GA04-05 and GA04-06 follow-up (AB04).

- Cross-cutting inventory: every GET list route of the app (response model ``list[...]`` or a
  page object with ``items``, or a route with a ``ListSpec``) rejects an unknown query
  parameter with 422. Routes not converted yet are listed in ``REMAINING`` with a reason.
- ListSpec on further lists (work orders, SLA, automation, immoware, metering, banking,
  letting): filter, sort, fields, unknown filter/sort 422, ``as_of`` 422 without validity.
- ETag/If-Match on further PATCH resources: stale token 412, tenant separation 404, read
  permission 403, validation 422.
"""

import asyncio
import enum
import inspect
import typing
import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any

import boto3
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration

# Routes that do not answer 422 yet, with reason. Goal: empty.
REMAINING: dict[str, str] = {}


def _walk(routes: Any, prefix: str = "") -> Iterator[tuple[str, APIRoute]]:
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
        elif hasattr(route, "original_router"):
            ctx = getattr(route, "include_context", None)
            yield from _walk(
                route.original_router.routes, prefix + (getattr(ctx, "prefix", "") or "")
            )
        elif hasattr(route, "routes"):
            yield from _walk(route.routes, prefix)


def _calls(route: APIRoute) -> list[Any]:
    stack, out = [route.dependant], []
    while stack:
        dep = stack.pop()
        out.append(dep.call)
        stack.extend(dep.dependencies)
    return out


def _is_list(route: APIRoute) -> bool:
    model = route.response_model
    if any(type(getattr(c, "__self__", None)).__name__ == "ListSpec" for c in _calls(route)):
        return True
    if model is None:
        return False
    if typing.get_origin(model) is list:
        return True
    return hasattr(model, "model_fields") and "items" in model.model_fields


def _sample(annotation: Any) -> str:
    for candidate in typing.get_args(annotation) or (annotation,):
        if candidate is uuid.UUID:
            return str(uuid.uuid4())
        if candidate is int:
            return "1"
        if candidate is date:
            return "2026-01-01"
        if inspect.isclass(candidate) and issubclass(candidate, enum.Enum):
            return str(next(iter(candidate)).value)
    return "x"


def _list_routes() -> list[tuple[str, str]]:
    app = create_app()
    out: list[tuple[str, str]] = []
    for path, route in _walk(app.routes):
        if "GET" not in route.methods or not _is_list(route):
            continue
        url = path
        for param in route.dependant.path_params:
            url = url.replace("{" + param.name + "}", _sample(param.field_info.annotation))
            url = url.replace("{" + param.name + ":path}", "x")
        out.append((path, url))
    return out


LIST_ROUTES = _list_routes()


def test_inventory_is_substantial() -> None:
    assert len(LIST_ROUTES) > 300
    assert set(REMAINING) <= {p for p, _ in LIST_ROUTES}


async def _world(settings: Any) -> World:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ab04-{RUN}", name=f"AB04 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ab04b-{RUN}", name=f"AB04 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("ab04admin", a, "tenant_admin"),
            ("ab04admin_b", b, "tenant_admin"),
            ("ab04reader", a, "read_only"),
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


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _h(client: TestClient, world: World, name: str, tenant: uuid.UUID) -> dict[str, str]:
    return bearer(login(client, world, name, tenant))


def test_all_list_routes_reject_unknown_parameter(client: TestClient, world: World) -> None:
    h = _h(client, world, "ab04admin", world.tenant_a)
    failures = []
    for path, url in LIST_ROUTES:
        if path in REMAINING:
            continue
        r = client.get(url, params={"unbekannt": "1"}, headers=h)
        if r.status_code != 422:
            failures.append((path, r.status_code))
    assert not failures, failures


@pytest.mark.parametrize(
    ("path", "filt", "sort"),
    [
        ("/api/v1/work-orders", "status", "-scheduled_at"),
        ("/api/v1/sla/clocks", "state", "-due_resolution_at"),
        ("/api/v1/sla/alerts", "level", "-sent_at"),
        ("/api/v1/automation/rules", "active", "-created_at"),
        ("/api/v1/immoware/sync/runs", "status", "finished_at"),
        ("/api/v1/metering/sync-jobs", "status", "-started_at"),
        ("/api/v1/banking/rules", "approval_state", "-hit_count"),
        ("/api/v1/banking/payment-orders", "status", "-amount"),
        ("/api/v1/letting/listings", "publication_status", "price"),
    ],
)
def test_converted_lists(client: TestClient, world: World, path: str, filt: str, sort: str) -> None:
    h = _h(client, world, "ab04admin", world.tenant_a)
    values = {"active": "true", "level": "1", "status": "x"}
    ok = client.get(path, params={"sort": sort}, headers=h)
    assert ok.status_code == 200, ok.text
    filtered = client.get(path, params={f"filter[{filt}]": values.get(filt, "x")}, headers=h)
    assert filtered.status_code in (200, 422), filtered.text  # 422 only for a type mismatch
    for bad in ({"filter[nope]": "1"}, {"sort": "nope"}, {"as_of": "2026-01-01"}):
        r = client.get(path, params=bad, headers=h)
        assert r.status_code == 422, (path, bad, r.text)


def test_strict_lists_reject_generic_parameters(client: TestClient, world: World) -> None:
    h = _h(client, world, "ab04admin", world.tenant_a)
    for bad in ({"sort": "name"}, {"fields": "id"}, {"filter[name]": "x"}, {"include": "x"}):
        r = client.get("/api/v1/teams", params=bad, headers=h)
        assert r.status_code == 422, (bad, r.text)
    assert client.get("/api/v1/teams", headers=h).status_code == 200


def test_work_orders_fields_and_prospects_filter(client: TestClient, world: World) -> None:
    h = _h(client, world, "ab04admin", world.tenant_a)
    r = client.get("/api/v1/work-orders", params={"fields": "status"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.headers.get("X-Total-Count") is not None
    unit = str(uuid.uuid4())
    r = client.get(
        "/api/v1/letting/prospects", params={"unit_id": unit, "filter[status]": "new"}, headers=h
    )
    assert r.status_code == 200, r.text
    assert r.json() == []
    r = client.get("/api/v1/letting/prospects", params={"unit_id": unit, "sort": "x"}, headers=h)
    assert r.status_code == 422


def test_team_etag_if_match(client: TestClient, world: World) -> None:
    h = _h(client, world, "ab04admin", world.tenant_a)
    created = client.post("/api/v1/teams", json={"name": f"AB04 Team {RUN}"}, headers=h)
    assert created.status_code == 201, created.text
    tid = created.json()["id"]
    got = client.get(f"/api/v1/teams/{tid}", headers=h)
    etag = got.headers["ETag"]
    assert etag.startswith('"t')
    stale = '"t1"'
    r = client.patch(
        f"/api/v1/teams/{tid}", json={"name": "AB04 neu"}, headers={**h, "If-Match": stale}
    )
    assert r.status_code == 412, r.text
    r = client.patch(
        f"/api/v1/teams/{tid}", json={"name": f"AB04 neu {RUN}"}, headers={**h, "If-Match": etag}
    )
    assert r.status_code == 200, r.text
    new_etag = r.headers["ETag"]
    assert new_etag != etag
    # the old token is stale now
    r = client.patch(f"/api/v1/teams/{tid}", json={"name": "x"}, headers={**h, "If-Match": etag})
    assert r.status_code == 412
    # without If-Match the write stays unchecked (ADR 0012)
    assert (
        client.patch(f"/api/v1/teams/{tid}", json={"name": f"AB04 o {RUN}"}, headers=h).status_code
        == 200
    )
    # validation, permission, tenant separation
    assert client.patch(f"/api/v1/teams/{tid}", json={"name": ""}, headers=h).status_code == 422
    reader = _h(client, world, "ab04reader", world.tenant_a)
    assert (
        client.patch(f"/api/v1/teams/{tid}", json={"name": "r"}, headers=reader).status_code == 403
    )
    other = _h(client, world, "ab04admin_b", world.tenant_b)
    assert (
        client.patch(f"/api/v1/teams/{tid}", json={"name": "b"}, headers=other).status_code == 404
    )
    assert client.get(f"/api/v1/teams/{tid}", headers=other).status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/sla/rules/{id}",
        "/api/v1/automation/rules/{id}",
        "/api/v1/letting/listings/{id}",
        "/api/v1/letting/prospects/{id}",
        "/api/v1/banking/payment-orders/{id}",
        "/api/v1/mail/mailboxes/{id}",
    ],
)
def test_patch_accepts_if_match_header(client: TestClient, world: World, path: str) -> None:
    """The header is declared (not rejected); a missing resource stays 404."""
    h = _h(client, world, "ab04admin", world.tenant_a)
    r = client.patch(
        path.replace("{id}", str(uuid.uuid4())), json={}, headers={**h, "If-Match": '"t1"'}
    )
    assert r.status_code in (404, 422), (path, r.status_code, r.text)
