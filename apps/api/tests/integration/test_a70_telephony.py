"""Telefonie-Webhook (master prompt 13.5, M23, Lückenliste A70). Expected values by hand:
a valid HMAC delivery writes exactly one call note; invalid, missing or stale signatures and a
disabled tenant are 401 (MHVP-HOOK-0002); the same delivery again is a replay, 409
(MHVP-HOOK-0003); a body above the limit is 413 (MHVP-HOOK-0004); the number is matched
uniquely, ambiguously (candidate list) or not at all; a missed call yields the proposal
"Rückruf" and never a ticket by itself; accepting creates one ticket with source phone; the
secret of tenant B never signs for tenant A and A's calls are invisible in B; a user without
``contacts:read`` sees the number masked; the rate limit counts webhook deliveries."""

import asyncio
import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.communication import telephony as hook
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
W = "/api/v1/communication/webhooks/telephony"
S = "/api/v1/communication/telephony/settings"
C = "/api/v1/communication/calls"
SECRET_A = "a-very-long-telephony-secret-for-tenant-a"
SECRET_B = "b-very-long-telephony-secret-for-tenant-b"
SLUG_A = f"tela-{RUN}"
SLUG_B = f"telb-{RUN}"
NUMBER_UNIQUE = "+4921112345601"
NUMBER_SHARED = "+4921112345602"
NUMBER_UNKNOWN = "+4921112345699"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=SLUG_A, name=f"Telefonie A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=SLUG_B, name=f"Telefonie B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("teladmin", a, "tenant_admin"),
            ("telother", b, "tenant_admin"),
            ("telcare", a, "caretaker"),
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
    return asyncio.run(_world(base_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(base_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _configure(client: TestClient, h: dict[str, str], *, secret: str | None, enabled: bool) -> Any:
    body: dict[str, Any] = {"enabled": enabled, "provider_label": "Testanlage"}
    if secret is not None:
        body["webhook_secret"] = secret
    return _ok(client.put(S, json=body, headers=h))


def _deliver(
    client: TestClient,
    tenant_key: str,
    secret: str,
    payload: dict[str, Any],
    *,
    timestamp: int | None = None,
    signature: str | None = None,
    via_path: bool = False,
    raw: bytes | None = None,
) -> Any:
    raw = raw if raw is not None else json.dumps(payload).encode()
    ts = timestamp if timestamp is not None else int(time.time())
    headers = {
        "Content-Type": "application/json",
        hook.TIMESTAMP_HEADER: str(ts),
        hook.SIGNATURE_HEADER: signature or hook.sign(secret, ts, raw),
    }
    if via_path:
        return client.post(f"{W}/{tenant_key}", content=raw, headers=headers)
    headers[hook.TENANT_HEADER] = tenant_key
    return client.post(W, content=raw, headers=headers)


def _event(
    event: str, number: str, ref: str, *, direction: str = "inbound", **extra: Any
) -> dict[str, Any]:
    return {"event": event, "number": number, "direction": direction, "provider_ref": ref, **extra}


def _contact(client: TestClient, h: dict[str, str], last_name: str, number: str) -> str:
    out = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Test",
                "last_name": last_name,
                "phones": [{"label": "mobile", "number": number, "is_primary": True}],
            },
            headers=h,
        ),
        201,
    )
    return str(out["id"])


@pytest.fixture(scope="module")
def contacts(database: Database, redis_url: str, world: World) -> dict[str, str]:
    """Three contacts of tenant A: one unique number, two sharing a number."""
    with TestClient(create_app(base_settings(database, redis_url))) as client:
        h = bearer(login(client, world, "teladmin", world.tenant_a))
        return {
            "unique": _contact(client, h, f"Eindeutig {RUN}", NUMBER_UNIQUE),
            "shared1": _contact(client, h, f"Doppel A {RUN}", NUMBER_SHARED),
            "shared2": _contact(client, h, f"Doppel B {RUN}", NUMBER_SHARED),
        }


def test_settings_secret_is_write_only_and_enable_needs_secret(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "teladmin", world.tenant_a))
    initial = _ok(client.get(S, headers=h))
    assert initial["enabled"] is False
    without = client.put(S, json={"enabled": True}, headers=h)
    assert without.status_code == 422
    out = _configure(client, h, secret=SECRET_A, enabled=True)
    assert out["has_webhook_secret"] is True
    assert out["enabled"] is True
    assert out["webhook_path"] == W
    assert "webhook_secret" not in out
    assert "webhook_secret" not in _ok(client.get(S, headers=h))
    # The caretaker holds no tenant_settings permission.
    hc = bearer(login(client, world, "telcare", world.tenant_a))
    assert client.get(S, headers=hc).status_code == 403


def test_valid_signature_records_unique_match_and_folds_started_into_ended(
    client: TestClient, world: World, contacts: dict[str, str]
) -> None:
    h = bearer(login(client, world, "teladmin", world.tenant_a))
    _configure(client, h, secret=SECRET_A, enabled=True)
    ref = f"call-unique-{RUN}"
    first = _ok(_deliver(client, SLUG_A, SECRET_A, _event("call.started", NUMBER_UNIQUE, ref)))
    assert first["status"] == "recorded"
    assert first["match_status"] == "matched"
    assert first["contact_id"] == contacts["unique"]
    assert first["proposal"] == "none"  # answered call, no open ticket: no proposal
    ended = _ok(
        _deliver(
            client,
            str(world.tenant_a),
            SECRET_A,
            _event("call.ended", NUMBER_UNIQUE, ref, duration_seconds=95),
            via_path=True,
            timestamp=int(time.time()) + 1,
        )
    )
    assert ended["status"] == "updated"
    assert ended["call_id"] == first["call_id"]
    rows = _ok(client.get(f"/api/v1/contacts/{contacts['unique']}/calls", headers=h))
    mine = [r for r in rows if r["id"] == first["call_id"]]
    assert len(mine) == 1
    assert mine[0]["event"] == "ended"
    assert mine[0]["duration_seconds"] == 95
    assert mine[0]["number"] == NUMBER_UNIQUE
    assert mine[0]["number_masked"] is False
    assert mine[0]["contact_name"] == f"Eindeutig {RUN}, Test"


def test_ambiguous_number_gives_candidates_and_manual_assignment(
    client: TestClient, world: World, contacts: dict[str, str]
) -> None:
    h = bearer(login(client, world, "teladmin", world.tenant_a))
    _configure(client, h, secret=SECRET_A, enabled=True)
    out = _ok(
        _deliver(client, SLUG_A, SECRET_A, _event("call.started", "0211 12345602", f"amb-{RUN}"))
    )
    assert out["match_status"] == "ambiguous"
    assert out["contact_id"] is None
    assert out["candidates"] == 2
    row = next(r for r in _ok(client.get(C, headers=h)) if r["id"] == out["call_id"])
    assert set(row["candidate_contact_ids"]) == {contacts["shared1"], contacts["shared2"]}
    assert row["number"] == NUMBER_SHARED  # normalised to E.164
    assigned = _ok(
        client.post(
            f"{C}/{out['call_id']}/assign", json={"contact_id": contacts["shared2"]}, headers=h
        )
    )
    assert assigned["match_status"] == "matched"
    assert assigned["contact_id"] == contacts["shared2"]
    assert assigned["candidate_contact_ids"] == []


def test_unknown_number_and_unreadable_number(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "teladmin", world.tenant_a))
    _configure(client, h, secret=SECRET_A, enabled=True)
    unknown = _ok(
        _deliver(client, SLUG_A, SECRET_A, _event("call.started", NUMBER_UNKNOWN, f"unk-{RUN}"))
    )
    assert unknown["match_status"] == "unknown"
    assert unknown["contact_id"] is None
    anonymous = _ok(
        _deliver(client, SLUG_A, SECRET_A, _event("call.missed", "anonym", f"anon-{RUN}"))
    )
    assert anonymous["match_status"] == "unknown"
    assert anonymous["proposal"] == "proposed"


def test_missed_call_proposes_callback_and_accept_creates_one_ticket(
    client: TestClient, world: World, contacts: dict[str, str]
) -> None:
    h = bearer(login(client, world, "teladmin", world.tenant_a))
    _configure(client, h, secret=SECRET_A, enabled=True)
    before = {
        t["id"]
        for t in _ok(
            client.get("/api/v1/tickets", params={"contact_id": contacts["unique"]}, headers=h)
        )
    }
    out = _ok(
        _deliver(client, SLUG_A, SECRET_A, _event("call.missed", NUMBER_UNIQUE, f"miss-{RUN}"))
    )
    assert out["proposal"] == "proposed"
    # No ticket by the webhook itself (rule 0.1.6).
    after = {
        t["id"]
        for t in _ok(
            client.get("/api/v1/tickets", params={"contact_id": contacts["unique"]}, headers=h)
        )
    }
    assert after == before
    created = _ok(client.post(f"{C}/{out['call_id']}/proposal/accept", json={}, headers=h), 201)
    ticket = _ok(client.get(f"/api/v1/tickets/{created['ticket_id']}", headers=h))
    assert ticket["source"] == "phone"
    assert ticket["contact_id"] == contacts["unique"]
    assert ticket["title"] == f"Rückruf Eindeutig {RUN}, Test"
    row = next(r for r in _ok(client.get(C, headers=h)) if r["id"] == out["call_id"])
    assert row["proposal_status"] == "accepted"
    assert row["ticket_id"] == created["ticket_id"]
    # Accepting twice is refused; the open ticket now marks the next call as ticket related.
    assert (
        client.post(f"{C}/{out['call_id']}/proposal/accept", json={}, headers=h).status_code == 409
    )
    related = _ok(
        _deliver(client, SLUG_A, SECRET_A, _event("call.started", NUMBER_UNIQUE, f"rel-{RUN}"))
    )
    assert related["proposal"] == "proposed"
    rel_row = next(r for r in _ok(client.get(C, headers=h)) if r["id"] == related["call_id"])
    assert rel_row["related_ticket_id"] == created["ticket_id"]
    dismissed = _ok(client.post(f"{C}/{related['call_id']}/proposal/dismiss", headers=h))
    assert dismissed["proposal_status"] == "dismissed"
    noted = _ok(
        client.patch(f"{C}/{related['call_id']}", json={"note": "Rückruf erledigt."}, headers=h)
    )
    assert noted["note"] == "Rückruf erledigt."


def test_invalid_missing_stale_signature_disabled_tenant_and_size_limit(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "teladmin", world.tenant_a))
    _configure(client, h, secret=SECRET_A, enabled=True)
    payload = _event("call.started", NUMBER_UNKNOWN, f"sig-{RUN}")
    wrong = _deliver(client, SLUG_A, "not-the-secret-of-tenant-a", payload)
    assert wrong.status_code == 401
    assert "MHVP-HOOK-0002" in wrong.text
    missing = client.post(W, content=b"{}", headers={hook.TENANT_HEADER: SLUG_A})
    assert missing.status_code == 401
    stale = _deliver(client, SLUG_A, SECRET_A, payload, timestamp=int(time.time()) - 3600)
    assert stale.status_code == 401
    unknown_tenant = _deliver(client, f"nobody-{RUN}", SECRET_A, payload)
    assert unknown_tenant.status_code == 401
    too_large = _deliver(
        client,
        SLUG_A,
        SECRET_A,
        {},
        raw=b'{"event":"call.started","number":"' + b"1" * hook.MAX_BODY_BYTES + b'"}',
    )
    assert too_large.status_code == 413
    assert "MHVP-HOOK-0004" in too_large.text
    # Conversation content or unknown fields are refused (extra="forbid").
    content = _deliver(client, SLUG_A, SECRET_A, {**payload, "transcript": "Hallo"})
    assert content.status_code == 422
    # Disabled tenant: a correctly signed delivery is refused.
    _configure(client, h, secret=None, enabled=False)
    off = _deliver(client, SLUG_A, SECRET_A, payload)
    assert off.status_code == 401
    _configure(client, h, secret=None, enabled=True)
    assert all(r["provider_ref"] != f"sig-{RUN}" for r in _ok(client.get(C, headers=h)))


def test_replay_of_the_same_delivery_is_409(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "teladmin", world.tenant_a))
    _configure(client, h, secret=SECRET_A, enabled=True)
    ts = int(time.time())
    payload = _event("call.started", NUMBER_UNKNOWN, f"replay-{RUN}")
    raw = json.dumps(payload).encode()
    sig = hook.sign(SECRET_A, ts, raw)
    _ok(_deliver(client, SLUG_A, SECRET_A, payload, timestamp=ts, signature=sig))
    replay = _deliver(client, SLUG_A, SECRET_A, payload, timestamp=ts, signature=sig)
    assert replay.status_code == 409
    assert "MHVP-HOOK-0003" in replay.text


def test_tenant_separation(client: TestClient, world: World, contacts: dict[str, str]) -> None:
    ha = bearer(login(client, world, "teladmin", world.tenant_a))
    hb = bearer(login(client, world, "telother", world.tenant_b))
    _configure(client, ha, secret=SECRET_A, enabled=True)
    _configure(client, hb, secret=SECRET_B, enabled=True)
    assert (
        _deliver(
            client, SLUG_A, SECRET_B, _event("call.started", NUMBER_UNIQUE, f"x-{RUN}")
        ).status_code
        == 401
    )
    assert (
        _deliver(
            client, SLUG_B, SECRET_A, _event("call.started", NUMBER_UNIQUE, f"x-{RUN}")
        ).status_code
        == 401
    )
    a_call = _ok(
        _deliver(client, SLUG_A, SECRET_A, _event("call.missed", NUMBER_UNIQUE, f"sep-{RUN}"))
    )
    assert a_call["contact_id"] == contacts["unique"]
    # The same number in B matches nothing: A's contacts are invisible (RLS).
    b_call = _ok(
        _deliver(client, SLUG_B, SECRET_B, _event("call.missed", NUMBER_UNIQUE, f"sep-{RUN}"))
    )
    assert b_call["match_status"] == "unknown"
    assert b_call["call_id"] != a_call["call_id"]
    b_ids = {r["id"] for r in _ok(client.get(C, headers=hb))}
    assert b_call["call_id"] in b_ids
    assert a_call["call_id"] not in b_ids
    assert client.get(f"/api/v1/contacts/{contacts['unique']}/calls", headers=hb).status_code == 404
    assert (
        client.patch(f"{C}/{a_call['call_id']}", json={"note": "x"}, headers=hb).status_code == 404
    )
    assert (
        client.post(f"{C}/{a_call['call_id']}/proposal/accept", json={}, headers=hb).status_code
        == 404
    )


def test_number_is_masked_without_contacts_read(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "teladmin", world.tenant_a))
    _configure(client, h, secret=SECRET_A, enabled=True)
    # A custom role with communication:read only (no system role has it without contacts).
    code = f"telread_{RUN}"
    role = client.post(
        "/api/v1/tenant/roles",
        json={"code": code, "name": "Telefonliste", "permissions": ["communication:read"]},
        headers=h,
    )
    assert role.status_code == 201, role.text
    members = _ok(client.get("/api/v1/tenant/members", headers=h))
    care = next(m for m in members if m["user_id"] == str(world.users["telcare"]))
    assert (
        client.put(
            f"/api/v1/tenant/members/{care['membership_id']}/roles",
            json={"role_codes": ["caretaker", code]},
            headers=h,
        ).status_code
        == 204
    )
    _ok(_deliver(client, SLUG_A, SECRET_A, _event("call.started", NUMBER_UNKNOWN, f"mask-{RUN}")))
    hc = bearer(login(client, world, "telcare", world.tenant_a))
    rows = _ok(client.get(C, headers=hc))
    row = next(r for r in rows if r["provider_ref"] == f"mask-{RUN}")
    assert row["number_masked"] is True
    assert row["number"] == "+4921****99"
    assert NUMBER_UNKNOWN not in json.dumps(rows)
    # The contact list per contact needs contacts:read.
    assert client.get(f"/api/v1/contacts/{world.tenant_a}/calls", headers=hc).status_code == 403
    # Without communication:read the list is refused as well.
    assert (
        client.put(
            f"/api/v1/tenant/members/{care['membership_id']}/roles",
            json={"role_codes": ["caretaker"]},
            headers=h,
        ).status_code
        == 204
    )
    hc = bearer(login(client, world, "telcare", world.tenant_a))
    assert client.get(C, headers=hc).status_code == 403


def test_rate_limit_counts_webhook_deliveries(
    database: Database, redis_url: str, world: World
) -> None:
    """The platform wide limit (A49, off in the shared test settings) treats the webhook like
    any unauthenticated request: the delivery carries the anonymous limit and a decreasing
    remaining count."""
    settings = base_settings(database, redis_url, rate_limit_enabled=True)
    with TestClient(create_app(settings)) as client:
        h = bearer(login(client, world, "teladmin", world.tenant_a))
        _configure(client, h, secret=SECRET_A, enabled=True)
        first = _deliver(
            client, SLUG_A, SECRET_A, _event("call.started", NUMBER_UNKNOWN, f"rl1-{RUN}")
        )
        second = _deliver(
            client, SLUG_A, SECRET_A, _event("call.started", NUMBER_UNKNOWN, f"rl2-{RUN}")
        )
    assert first.headers["X-RateLimit-Limit"] == str(settings.rate_limit_per_minute_anonymous)
    assert int(second.headers["X-RateLimit-Remaining"]) < int(
        first.headers["X-RateLimit-Remaining"]
    )
