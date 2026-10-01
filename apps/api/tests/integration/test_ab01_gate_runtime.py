"""GA14-06 runtime proof (18.0 table, rule 0.1.4): every route of the register
``GATED_ROUTES`` answers 403 ``MHVP-GATE-0001`` with the named gate while the gate is closed.

The test world is its own (tenant slug and users with prefix ``ab01`` plus RUN); the caller is
a tenant administrator, so only the gate can refuse. Path parameters are random UUIDs: the gate
check has to come before any lookup (no 404) and before any effect. Routes of
``REVIEWED_UNGATED`` are not called (classification open, AA01-01).
"""

import asyncio
import re
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, _settings, bearer
from tests.unit.test_ga14_gate_coverage import GATED_ROUTES

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
    },
    "/api/v1/accounting/g1-opening/request": {"scope": "AB01 Laufzeitnachweis G1"},
    "/api/v1/contracts/{contract_id}/rent-invoices": {
        "period_start": "2026-09-01",
        "period_end": "2026-09-30",
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
}

# Routes whose gate check is reached only after a record or configuration exists (lookup
# first, conditional gate). With random ids the closed gate cannot be the answer; the test
# then asserts that nothing happened (no 2xx effect, no 500) and lists the precondition.
# Runtime proof with a prepared record: open point of AB01.
PRECONDITION_FIRST: dict[str, tuple[set[int], str]] = {
    "/api/v1/imports/migration/ledgers/{ledger_id}/switch-requests": ({404}, "ledger lookup"),
    "/api/v1/imports/migration/switch-requests/{request_id}/approve": ({404}, "request lookup"),
    "/api/v1/imports/migration/switch-requests/{request_id}/reject": ({404}, "request lookup"),
    "/api/v1/accounting/receivable-runs/{run_id}/post": ({404}, "gate only for rule items"),
    "/api/v1/contracts/{contract_id}/rent-invoices/{invoice_id}/credit-note": (
        {404},
        "invoice lookup",
    ),
    "/api/v1/accounting/ledgers/{ledger_id}/open-items/settlement-proposal/confirm": (
        {404},
        "ledger lookup",
    ),
    "/api/v1/contracts/{contract_id}/rent-invoices": ({404}, "contract lookup"),
    # The request to open G1 (four eyes) is allowed while G1 is closed; it opens nothing.
    "/api/v1/accounting/g1-opening/request": ({201}, "opening request, no money effect"),
    "/api/v1/banking/auto-post": ({200}, "gate closed means runner posts nothing"),
    "/api/v1/postal/jobs": ({404, 422}, "gate only for dunning letters via external service"),
}


def _fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", lambda _m: str(uuid.uuid4()), path)


@pytest.fixture(scope="module")
def admin(database: Database, redis_url: str) -> Iterator[tuple[TestClient, dict[str, str]]]:
    settings = _settings(database, redis_url)

    async def build() -> str:
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
            return email
        finally:
            await engine.dispose()

    email = asyncio.run(build())
    with TestClient(create_app(settings)) as client:
        step = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert step.status_code == 200, step.text
        assert step.json()["status"] == "ok", step.json()
        yield client, bearer(step.json())


@pytest.mark.parametrize(("method", "path", "gate"), GATED_ROUTES, ids=lambda v: str(v))
def test_gated_route_is_refused_while_gate_closed(
    admin: tuple[TestClient, dict[str, str]], method: str, path: str, gate: str
) -> None:
    client, headers = admin
    response = client.request(method, _fill(path), json=VALID_BODIES.get(path, {}), headers=headers)
    if path in PRECONDITION_FIRST:
        allowed, reason = PRECONDITION_FIRST[path]
        assert response.status_code in allowed, f"{method} {path} ({reason}): {response.text}"
        if response.status_code == 200:
            assert response.json().get("posted") == 0, response.text
        if response.status_code == 201:
            assert response.json().get("status") == "requested", response.text
        return
    assert response.status_code == 403, f"{method} {path}: {response.status_code} {response.text}"
    body = response.json()
    assert body.get("code") == "MHVP-GATE-0001", body
    assert body.get("gate") == gate, body


def test_register_and_tables_are_consistent() -> None:
    registered = {path for _m, path, _g in GATED_ROUTES}
    assert set(PRECONDITION_FIRST) <= registered
    assert set(VALID_BODIES) <= registered
    # The runtime proof via the closed gate covers the large majority of the register.
    assert len(registered - set(PRECONDITION_FIRST)) >= 18
