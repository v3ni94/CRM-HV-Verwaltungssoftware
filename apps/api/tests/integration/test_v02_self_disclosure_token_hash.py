"""S16-03-01: idempotent data migration of plain self disclosure link tokens to sha256
(platform admin endpoint), issued links keep working, permission and tenant checks."""

import hashlib

import pytest
import sqlalchemy as sa

from tests.integration.conftest import Database
from tests.integration.test_m2_platform import World, bearer, login
from tests.integration.test_m26_letting import (  # noqa: F401  (fixtures)
    L,
    _ok,
    _party,
    _prospect_unit,
    clients,
    world,
)

pytestmark = pytest.mark.integration
URL = "/api/v1/platform/maintenance/self-disclosure-token-hash"


def _stored(database: Database, tenant: object, prospect_id: str) -> str:
    engine = sa.create_engine(database.migrator_url)
    with engine.begin() as conn:
        conn.execute(sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        value = conn.execute(
            sa.text("SELECT token FROM self_disclosure_link WHERE prospect_id = :p"),
            {"p": prospect_id},
        ).scalar_one()
    engine.dispose()
    return str(value)


def _set_plain(database: Database, tenant: object, prospect_id: str, plain: str) -> None:
    engine = sa.create_engine(database.migrator_url)
    with engine.begin() as conn:
        conn.execute(sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        conn.execute(
            sa.text("UPDATE self_disclosure_link SET token = :tok WHERE prospect_id = :p"),
            {"tok": plain, "p": prospect_id},
        )
    engine.dispose()


def test_legacy_plain_tokens_are_hashed_idempotently(clients, world: World, database: Database):  # type: ignore[no-untyped-def]  # noqa: F811
    client, _ = clients
    h = bearer(login(client, world, "m26admin"))
    _, unit = _prospect_unit(client, h, "772")
    _, contact = _party(client, h, "InteressentV02")
    prospect = _ok(
        client.post(
            f"{L}/prospects",
            json={"unit_id": unit, "contact_id": contact["id"], "delete_after": "2027-03-31"},
            headers=h,
        ),
        201,
    )
    link = _ok(
        client.post(
            f"{L}/prospects/{prospect['id']}/self-disclosure-link",
            json={},
            headers=h,
        ),
        201,
    )
    token = link["portal_url"].rsplit("/", 1)[-1]
    # Simulate a legacy row holding the plain token.
    _set_plain(database, world.tenant_a, prospect["id"], token)
    assert _stored(database, world.tenant_a, prospect["id"]) == token
    assert client.get(f"{L}/self-disclosure/{token}").status_code == 200

    # Authorization: a tenant admin is not a platform admin (403); no token is 401.
    assert client.post(URL, headers=h).status_code == 403
    assert client.post(URL).status_code == 401

    ph = bearer(login(client, world, "m26padmin"))
    first = _ok(client.post(URL, headers=ph))
    assert first["converted"] >= 1
    digest = "sha256:" + hashlib.sha256(token.encode()).hexdigest()
    assert _stored(database, world.tenant_a, prospect["id"]) == digest
    # The issued link keeps working, the digest itself is no credential.
    assert client.get(f"{L}/self-disclosure/{token}").status_code == 200
    assert client.get(f"{L}/self-disclosure/{digest}").status_code == 404
    # Idempotent: second run converts nothing and leaves the digest unchanged.
    assert _ok(client.post(URL, headers=ph))["converted"] == 0
    assert _stored(database, world.tenant_a, prospect["id"]) == digest
