"""GA14-06 runtime proof (18.0 table, rule 0.1.4): every route of the register
``GATED_ROUTES`` answers 403 ``MHVP-GATE-0001`` with the named gate while the gate is closed.

The test world is its own (tenant slug and users with prefix ``ab01`` plus RUN); the caller is
a tenant administrator, so only the gate can refuse. Path parameters are random UUIDs: the gate
check has to come before any lookup (no 404) and before any effect. Routes of
``REVIEWED_UNGATED`` are not called (classification open, AA01-01).

AC03: routes whose gate follows a lookup get their record prepared first (``PREPARED``), so
the closed gate is proven at runtime for every route of the register. Routes of the gate
procedure (``GATE_REQUEST_ROUTES``) and routes where the closed gate yields a draft or no
effect (``GATE_CONDITIONAL_ROUTES``) are proven with their closed branch.
"""

import asyncio
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, bearer
from tests.integration.test_m5_deposit_settlement import COMPANY
from tests.integration.test_m13_receivable_rules import _ledger, _ok, _rules, _run
from tests.integration.test_m13_rent_invoices import BUCKET, _rental, _settings, _tenancy
from tests.unit.test_ga14_gate_coverage import (
    GATE_CONDITIONAL_ROUTES,
    GATE_REQUEST_ROUTES,
    GATED_ROUTES,
)

pytestmark = pytest.mark.integration

RUN = f"ab01-{uuid.uuid4().hex[:8]}"

_U = str(uuid.uuid4())
# Bodies that pass request validation and choose the gated branch (target, action, channel).
VALID_BODIES: dict[str, dict[str, Any]] = {
    "/api/v1/banking/payment-batches": {"order_ids": [_U]},
    "/api/v1/accounting/ledgers/{ledger_id}/leading": {"leading_system": "mhvp"},
    "/api/v1/accounting/ledgers/{ledger_id}/open-items/settlement-proposal/confirm": {
        "account_id": _U,
        "amount": "10.00",
        "as_of": "2026-09-30",
        "fingerprint": "0" * 64,
        "bank_account_id": _U,
        "booking_date": "2026-09-30",
        "post_immediately": True,
    },
    "/api/v1/accounting/direct-debits/{run_id}/submit": {"reference": "AB01"},
    "/api/v1/statements/{statement_id}/transition": {"target": "issued"},
    "/api/v1/statements/{statement_id}/result-entries": {
        "booking_date": "2026-09-30",
        "due_date": "2026-10-31",
    },
    "/api/v1/billing/owner-statements/{statement_id}/transition": {"target": "issued"},
    "/api/v1/hoa/statements/{statement_id}/transition": {"target": "issued"},
    "/api/v1/hoa/asset-reports/{report_id}/transition": {"target": "issued"},
    "/api/v1/hoa/reserve-statements/{reserve_statement_id}/transition": {"target": "issued"},
    "/api/v1/letting/rent-increases/{case_id}/letter/pdf": {"dispatch": {"channel": "portal"}},
    "/api/v1/letting/rent-increases/{case_id}/actions": {"action": "send"},
    "/api/v1/accounting/payment-runs/payout-orders": {
        "open_item_id": _U,
        "contact_bank_account_id": _U,
        "property_bank_account_id": _U,
        "execution_date": "2026-09-30",
        "reason": "owner_payout",
    },
}

# Routes whose gate check is reached only after a record or configuration exists (lookup
# first, conditional gate). AC03 prepares these records in ``test_prepared_records_*`` and
# proves 403 there; what cannot be prepared without the gate would stay here with reason.
PRECONDITION_FIRST: dict[str, tuple[set[int], str]] = {}

# AC03: route -> precondition prepared before the call (runtime proof in the second test).
PREPARED: dict[str, str] = {
    "/api/v1/imports/migration/ledgers/{ledger_id}/switch-requests": "ledger",
    "/api/v1/imports/migration/switch-requests/{request_id}/approve": (
        "switch request of another person (inserted, the API refuses it with G1 closed)"
    ),
    "/api/v1/accounting/receivable-runs/{run_id}/post": "run with VAT rule items",
    "/api/v1/postal/jobs": "external postal service enabled",
}


def _fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", lambda _m: str(uuid.uuid4()), path)


@dataclass
class Admin:
    client: TestClient
    headers: dict[str, str]
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    settings: Any


@pytest.fixture(scope="module")
def admin(database: Database, redis_url: str) -> Iterator[Admin]:
    settings = _settings(database, redis_url)

    async def build() -> tuple[uuid.UUID, uuid.UUID, str]:
        crypto.set_master_key(b"k" * 32)
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            tenant, _ = await services.provision_tenant(factory, slug=RUN, name=f"Mandant {RUN}")
            email = f"admin-{RUN}@example.org"
            user = await services.create_user(
                factory,
                email=email,
                display_name=f"admin {RUN}",
                password=PASSWORD,
                is_platform_admin=False,
            )
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=user,
                role_codes=["tenant_admin"],
                actor_user_id=None,
            )
            return tenant, user, email
        finally:
            await engine.dispose()

    tenant, user, email = asyncio.run(build())
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(settings)) as client:
            step = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
            assert step.status_code == 200, step.text
            assert step.json()["status"] == "ok", step.json()
            yield Admin(client, bearer(step.json()), tenant, user, settings)


def _refused(response: Any, gate: str, what: str) -> None:
    assert response.status_code == 403, f"{what}: {response.status_code} {response.text}"
    body = response.json()
    assert body.get("code") == "MHVP-GATE-0001", body
    assert body.get("gate") == gate, body


# GAI-620: a refused gate must also leave no effect. Tables whose row count proves that no
# posting, open item, payment order, payment batch, statement or domain event was written.
EFFECT_TABLES = (
    "journal_entry",
    "journal_line",
    "open_item",
    "payment_order",
    "payment_batch",
    "payment_approval",
    "statement",
    "domain_event",
)


def _effect_counts(admin: Admin) -> dict[str, int]:
    from sqlalchemy import create_engine, text

    engine = create_engine(admin.settings.database_url.get_secret_value())
    try:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(admin.tenant_id)}
            )
            return {
                t: int(conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one())
                for t in EFFECT_TABLES
            }
    finally:
        engine.dispose()


@pytest.mark.parametrize(("method", "path", "gate"), GATED_ROUTES, ids=lambda v: str(v))
def test_gated_route_is_refused_while_gate_closed(
    admin: Admin, method: str, path: str, gate: str
) -> None:
    if path in PREPARED:
        pytest.skip(f"proven with prepared record: {PREPARED[path]}")
    before = _effect_counts(admin)
    response = admin.client.request(
        method, _fill(path), json=VALID_BODIES.get(path, {}), headers=admin.headers
    )
    if path in PRECONDITION_FIRST:
        allowed, reason = PRECONDITION_FIRST[path]
        assert response.status_code in allowed, f"{method} {path} ({reason}): {response.text}"
    else:
        _refused(response, gate, f"{method} {path}")
    assert _effect_counts(admin) == before, f"{method} {path}: refused call left an effect"


async def _insert_switch_request(admin: Admin, ledger_id: str, property_id: str) -> uuid.UUID:
    """Legacy state: a pending switch request of another person. The API cannot create one
    while G1 is closed (``request_switch`` checks G1 first), so it is inserted directly, like
    the one-off operator step in ``test_m14_invoices._set_vat_option``."""
    from datetime import date

    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.imports.migration_models import (
        MigrationReconciliationReport,
        MigrationSwitchRequest,
    )

    engine = create_app_engine(admin.settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, admin.tenant_id) as session:
            report = MigrationReconciliationReport(
                tenant_id=admin.tenant_id,
                created_by=admin.user_id,
                property_id=uuid.UUID(property_id),
                as_of=date(2026, 6, 30),
                zero_difference=True,
                compared=0,
                deviations=0,
                total_difference=Decimal("0.00"),
                lines=[],
                summary={},
            )
            session.add(report)
            await session.flush()
            item = MigrationSwitchRequest(
                tenant_id=admin.tenant_id,
                created_by=admin.user_id,
                ledger_id=uuid.UUID(ledger_id),
                report_id=report.id,
                requested_by=uuid.uuid4(),  # another person (four eyes)
            )
            session.add(item)
            await session.flush()
            return item.id
    finally:
        await engine.dispose()


def _vat_world(admin: Admin) -> dict[str, Any]:
    """Commercial tenancy with VAT option, VAT rules on, ledger with output tax account and
    a July receivable run (preview, rule items). Same steps as test_m13_rent_invoices."""
    from tests.integration.test_m14_invoices import _set_vat_option

    c, h = admin.client, admin.headers
    _ok(c.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    _rules(c, h, vat_enabled=True)
    prop, entity = _rental(c, h, "803", tax_id="DE123456789")
    ledger, _acc = _ledger(c, h, entity)
    asyncio.run(_set_vat_option(admin.settings, admin.tenant_id, ledger))
    tax = _ok(
        c.post(
            f"/api/v1/accounting/ledgers/{ledger}/accounts",
            json={
                "number": "017600",
                "name": "Umsatzsteuer Sollstellung",
                "category": "tax",
                "type": "liability",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        c.put(
            f"/api/v1/accounting/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "vat_output", "account_id": tax["id"]},
            headers=h,
        )
    )
    shop = _tenancy(c, h, prop["id"], "01", vat_option="commercial_full_vat")
    run = _run(c, h, "2026-07-01", "contract", shop["id"])
    assert run["items"][0]["status"] == "ready", run
    return {"property": prop["id"], "ledger": ledger, "contract": shop["id"], "run": run["id"]}


@pytest.fixture(scope="module")
def vat_world(admin: Admin) -> dict[str, Any]:
    return _vat_world(admin)


def test_prepared_records_are_refused_while_gate_closed(
    admin: Admin, vat_world: dict[str, Any]
) -> None:
    c, h = admin.client, admin.headers
    seen: set[str] = set()

    # Ledger exists: the switch request is refused by G1 before the reconciliation checks.
    path = "/api/v1/imports/migration/ledgers/{ledger_id}/switch-requests"
    url = path.replace("{ledger_id}", vat_world["ledger"])
    before = _effect_counts(admin)
    _refused(c.post(url, json={}, headers=h), "G1", path)
    assert _effect_counts(admin) == before
    seen.add(path)

    # Pending request of another person: approval is refused by G1, nothing switches.
    request_id = asyncio.run(
        _insert_switch_request(admin, vat_world["ledger"], vat_world["property"])
    )
    path = "/api/v1/imports/migration/switch-requests/{request_id}/approve"
    url = path.replace("{request_id}", str(request_id))
    before = _effect_counts(admin)
    _refused(c.post(url, json={}, headers=h), "G1", path)
    assert _effect_counts(admin) == before
    seen.add(path)
    ledger = _ok(c.get(f"/api/v1/accounting/ledgers/{vat_world['ledger']}", headers=h))
    assert ledger["leading_system"] != "mhvp", ledger

    # Run with rule items (VAT): posting is refused by G1, the run stays unposted.
    path = "/api/v1/accounting/receivable-runs/{run_id}/post"
    before = _effect_counts(admin)
    _refused(c.post(path.replace("{run_id}", vat_world["run"]), headers=h), "G1", path)
    assert _effect_counts(admin) == before  # no journal entry, no open item
    seen.add(path)
    run = _ok(c.get(f"/api/v1/accounting/receivable-runs/{vat_world['run']}", headers=h))
    assert run["status"] != "posted", run

    # External postal service enabled (test mode, no network on save): a dunning letter via
    # the service is refused by G1 before the dunning case lookup.
    _ok(
        c.put(
            "/api/v1/postal/settings",
            json={
                "provider": "letterxpress",
                "username": f"ac03-{RUN}",
                "api_key": "ac03-test-key",
                "mode": "test",
                "enabled": True,
            },
            headers=h,
        )
    )
    path = "/api/v1/postal/jobs"
    before = _effect_counts(admin)
    _refused(c.post(path, json={"dunning_case_id": _U}, headers=h), "G1", path)
    assert _effect_counts(admin) == before
    seen.add(path)

    assert seen == set(PREPARED)

    # Decision on the gate procedure: refusing the pending request needs no gate.
    path = "/api/v1/imports/migration/switch-requests/{request_id}/reject"
    out = _ok(c.post(path.replace("{request_id}", str(request_id)), json={}, headers=h))
    assert out["status"] == "rejected", out


def test_conditional_routes_take_the_closed_branch(admin: Admin, vat_world: dict[str, Any]) -> None:
    c, h = admin.client, admin.headers
    base = f"/api/v1/contracts/{vat_world['contract']}/rent-invoices"
    invoice = _ok(
        c.post(base, json={"period_start": "2026-07-01", "period_end": "2026-07-31"}, headers=h),
        201,
    )
    assert invoice["draft"] is True, invoice
    note = _ok(c.post(f"{base}/{invoice['id']}/credit-note", headers=h), 201)
    assert note["draft"] is True, note
    runner = _ok(c.post("/api/v1/banking/auto-post", headers=h))
    assert runner["posted"] == 0, runner


def test_gate_request_route_works_while_gate_closed(admin: Admin) -> None:
    out = _ok(
        admin.client.post(
            "/api/v1/accounting/g1-opening/request",
            json={"scope": "AC03 Laufzeitnachweis G1"},
            headers=admin.headers,
        ),
        201,
    )
    assert out["status"] == "requested", out


def test_register_and_tables_are_consistent() -> None:
    registered = {path for _m, path, _g in GATED_ROUTES}
    assert set(PRECONDITION_FIRST) <= registered
    assert set(PREPARED) <= registered
    assert set(VALID_BODIES) <= registered
    assert not registered & {p for _m, p, _g in GATE_REQUEST_ROUTES + GATE_CONDITIONAL_ROUTES}
    # AC03: every registered route is proven by the closed gate (403), none only by lookup.
    assert PRECONDITION_FIRST == {}
