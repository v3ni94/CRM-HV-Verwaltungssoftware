# ruff: noqa: F811
"""AA08 (GA02-07): portal account with roles, invited_at and the statuses of 6.1. ``roles``
follow the access grants (owner from an ownership contract), ``invited_at`` is set on the
invitation, an invitation past its expiry reads ``expired`` (derived, the stored value stays
``invited``), an accepted one reads ``active``. A contact without contract has no roles."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from mhvp.portal.routers import effective_account_status
from tests.integration.conftest import Database
from tests.integration.test_a86_portal_accounts import PA, client, world  # noqa: F401
from tests.integration.test_m2_platform import PASSWORD, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m21_portal import _contact_of, _ok
from tests.integration.test_m21_read_receipts import _db

pytestmark = pytest.mark.integration


def test_effective_status_is_derived() -> None:
    now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    past, future = now - timedelta(days=1), now + timedelta(days=1)
    free = SimpleNamespace(active=True, locked_until=None)
    locked = SimpleNamespace(active=True, locked_until=future)
    disabled = SimpleNamespace(active=False, locked_until=None)

    def account(status: str, expires: datetime | None) -> Any:
        return SimpleNamespace(status=status, invitation_expires_at=expires)

    assert effective_account_status(account("invited", future), free, now) == "invited"
    assert effective_account_status(account("invited", past), free, now) == "expired"
    assert effective_account_status(account("active", None), free, now) == "active"
    assert effective_account_status(account("active", None), locked, now) == "locked"
    assert effective_account_status(account("active", None), disabled, now) == "locked"
    assert effective_account_status(account("revoked", None), free, now) == "revoked"


def test_portal_account_roles_invited_at_and_expiry(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "a86admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "814", "name": "AA08 WEG", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    unit = _unit(client, h, prop["id"], "01")
    party, _ = _party(client, h, "AA08Eigentuemer")
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    contact = _contact_of(client, h, party)
    before = datetime.now(UTC)
    _ok(
        client.post(
            f"{PA}/accounts",
            json={"contact_id": contact, "email": world.email("aa08owner"), "display_name": "o"},
            headers=h,
        ),
        201,
    )
    row = _ok(client.get(f"{PA}/accounts", params={"contact_id": contact}, headers=h))[0]
    assert row["roles"] == ["owner"]
    assert row["status"] == "invited"
    assert datetime.fromisoformat(row["invited_at"]) >= before - timedelta(seconds=5)

    async def expire(s: Any) -> None:
        await s.execute(
            text("UPDATE portal_account SET invitation_expires_at = :at WHERE contact_id = :c"),
            {"at": datetime.now(UTC) - timedelta(days=1), "c": uuid.UUID(contact)},
        )

    _db(database, redis_url, world, expire)
    row = _ok(client.get(f"{PA}/accounts", params={"contact_id": contact}, headers=h))[0]
    assert row["status"] == "expired"
    assert PASSWORD not in str(row)


def test_contact_without_contract_has_no_roles(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "a86admin"))
    party, _ = _party(client, h, "AA08Ohne")
    contact = _contact_of(client, h, party)
    _ok(
        client.post(
            f"{PA}/accounts",
            json={"contact_id": contact, "email": world.email("aa08none"), "display_name": "n"},
            headers=h,
        ),
        201,
    )
    row = _ok(client.get(f"{PA}/accounts", params={"contact_id": contact}, headers=h))[0]
    assert row["roles"] == []
    other = bearer(login(client, world, "a86other"))
    assert _ok(client.get(f"{PA}/accounts", params={"contact_id": contact}, headers=other)) == []
