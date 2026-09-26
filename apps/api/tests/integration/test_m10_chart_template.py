"""M10-01 (operator decision 26.09.2026): the chart of accounts template carries the proposed
rental revenue accounts as drafts (``review_status = "entwurf"``, note "Freigabe durch
Steuerberatung offen"). The seed is idempotent and never overwrites existing template rows,
templates stay tenant separated and the draft marker is visible on the ledger accounts.
G1 stays closed; nothing here posts."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.accounting.defaults import (
    A1_ACCOUNTS,
    DRAFT_NOTE,
    PROPOSED_ACCOUNTS,
    REVIEW_DRAFT,
    TEMPLATE_ACCOUNTS,
    merge_missing,
)
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m10_ledger import A, _hoa_ledger, _ok

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    """Own tenants and users (distinct from test_m10_ledger, which shares the database)."""
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ct-{RUN}", name=f"Konten {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ct2-{RUN}", name=f"Konten2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ctadmin", a, "tenant_admin"),
            ("ctreader", a, "read_only"),
            ("ctother", b, "tenant_admin"),
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


PROPOSED_NUMBERS = {"060300", "060400", "060500", "060600", "060700", "060800"}


def test_template_rows_follow_annex_a1_pattern() -> None:
    """Numbers are unique, six digits, in the revenue range of 7.2, and only proposals are drafts."""
    numbers = [row["number"] for row in TEMPLATE_ACCOUNTS]
    assert len(numbers) == len(set(numbers))
    assert {row["number"] for row in PROPOSED_ACCOUNTS} == PROPOSED_NUMBERS
    for row in PROPOSED_ACCOUNTS:
        assert row["number"].startswith("06")
        assert len(row["number"]) == 6
        assert (row["category"], row["type"]) == ("revenue", "income")
        assert row["applies_to"] == ["rental_owner", "sev_owner"]
        assert (row["review_status"], row["review_note"]) == (REVIEW_DRAFT, DRAFT_NOTE)
        # M10-02 open: allocation, statement kind and VAT option stay unset.
        assert (row["allocation_category"], row["statement_kind"], row["vat_option"]) == (
            "none",
            "none",
            "none",
        )
    # M10-02 (26.09.2026): cost accounts with a preset are drafts too, all other A.1 rows not.
    for row in A1_ACCOUNTS:
        if row["category"] == "cost" and row["allocation_category"] != "none":
            assert (row["review_status"], row["review_note"]) == (REVIEW_DRAFT, DRAFT_NOTE)
        else:
            assert row["review_status"] == "none"


def test_merge_missing_keeps_existing_rows() -> None:
    edited = dict(A1_ACCOUNTS[0], name="Vom Mandanten umbenannt")
    merged = merge_missing([edited], TEMPLATE_ACCOUNTS)
    assert merged[0]["name"] == "Vom Mandanten umbenannt"
    assert [r["number"] for r in merged] == [r["number"] for r in TEMPLATE_ACCOUNTS]
    assert merge_missing(merged, TEMPLATE_ACCOUNTS) == merged


def _rental_owner_ledger(c: TestClient, h: dict[str, str], number: str) -> str:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"Miethaus {number}", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    contact = _ok(
        c.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Bestand {number} {RUN} GmbH"},
            headers=h,
        ),
        201,
    )
    party = _ok(
        c.post("/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h),
        201,
    )
    entity = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": party["id"], "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers",
            json={"legal_entity_id": entity, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )
    return str(ledger["id"])


def test_seed_idempotent_and_draft_flag_visible(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ctadmin"))
    first: dict[str, Any] = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    second: dict[str, Any] = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    assert first["id"] == second["id"]
    assert first["released"] is False  # V8 open, G1 closed
    assert second["released"] is False
    assert len(_ok(client.get(f"{A}/templates", headers=h))) == 1
    by_number = {row["number"]: row for row in second["accounts"]}
    assert len(by_number) == len(second["accounts"]) == len(TEMPLATE_ACCOUNTS)
    assert set(by_number) >= PROPOSED_NUMBERS
    for number in PROPOSED_NUMBERS:
        assert by_number[number]["review_status"] == REVIEW_DRAFT
        assert by_number[number]["review_note"] == DRAFT_NOTE
    assert by_number["060100"]["review_status"] == "none"

    # Rental owner ledger: proposals are created as accounts with the draft marker.
    ledger = _rental_owner_ledger(client, h, "741")
    accounts = {
        a["number"]: a for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    assert set(accounts) >= PROPOSED_NUMBERS
    assert accounts["060300"]["name"] == "Miete"
    assert accounts["060300"]["review_status"] == REVIEW_DRAFT
    assert accounts["060300"]["review_note"] == DRAFT_NOTE
    assert accounts["060300"]["is_system"] is True
    assert accounts["001300"]["review_status"] == "none"
    assert "060100" not in accounts  # Hausgeld is HOA only

    # HOA ledger: rental proposals are not created, existing HOA accounts unchanged.
    hoa_ledger, hoa_accounts, _ = _hoa_ledger(client, h, "742")
    assert PROPOSED_NUMBERS.isdisjoint(hoa_accounts)
    assert {"060100", "060200"} <= set(hoa_accounts)
    hoa_rows = {
        a["number"]: a for a in _ok(client.get(f"{A}/ledgers/{hoa_ledger}/accounts", headers=h))
    }
    assert hoa_rows["060100"]["review_status"] == "none"


def test_template_tenant_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ctadmin"))
    other = bearer(login(client, world, "ctother"))
    mine = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    theirs = _ok(client.post(f"{A}/templates/default", headers=other), 201)
    assert mine["id"] != theirs["id"]
    assert [t["id"] for t in _ok(client.get(f"{A}/templates", headers=other))] == [theirs["id"]]
    assert [t["id"] for t in _ok(client.get(f"{A}/templates", headers=h))] == [mine["id"]]
    assert client.post(f"{A}/templates/{mine['id']}/release", headers=other).status_code == 404
    reader = bearer(login(client, world, "ctreader"))
    assert client.post(f"{A}/templates/default", headers=reader).status_code == 403
