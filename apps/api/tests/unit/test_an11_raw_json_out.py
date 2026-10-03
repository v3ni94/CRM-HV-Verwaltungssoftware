"""AN11 (GAI-304, ADR 0037): typed money routes keep their JSON bytes unchanged."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mhvp.accounting.write_responses import RawJsonOut


class _An11ItemOut(RawJsonOut):
    amount: Decimal
    booked_at: datetime | None = None


class _An11Out(RawJsonOut):
    id: uuid.UUID
    total: Decimal
    items: list[_An11ItemOut] | None = None


_ID = uuid.UUID("01890000-0000-7000-8000-000000000001")
PAYLOAD: dict[str, Any] = {
    "id": _ID,
    "total": Decimal("1234.50"),
    "zero": Decimal("0.00"),
    "whole": Decimal("3"),
    "big": 1e16,
    "text": "Müller Straße",
    "day": date(2026, 10, 3),
    "items": [
        {"amount": Decimal("-0.10"), "booked_at": datetime(2026, 10, 3, 8, 0, tzinfo=UTC)},
        {"amount": 7, "extra": {"nested": Decimal("1.005")}},
    ],
}


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/untyped")
    def untyped() -> dict[str, Any]:
        return PAYLOAD

    @app.get("/typed", response_model=_An11Out)
    def typed() -> Any:
        return PAYLOAD

    @app.get("/untyped-list")
    def untyped_list() -> list[dict[str, Any]]:
        return PAYLOAD["items"]

    @app.get("/typed-list", response_model=list[_An11ItemOut])
    def typed_list() -> Any:
        return PAYLOAD["items"]

    return app


def test_typed_bytes_equal_untyped_bytes() -> None:
    client = TestClient(_app())
    before = client.get("/untyped").content
    after = client.get("/typed").content
    assert after == before
    assert b'"total":"1234.50"' in after  # Decimal stays a JSON string (ADR 0037)
    assert b'{"amount":7,' in after  # an int in a Decimal field is not coerced
    assert client.get("/typed-list").content == client.get("/untyped-list").content


def test_schema_documents_fields() -> None:
    schema = _app().openapi()["components"]["schemas"]
    assert set(schema["_An11Out"]["properties"]) >= {"id", "total", "items"}


def test_python_dump_unchanged() -> None:
    model = _An11Out.model_validate(PAYLOAD)
    assert model.total == Decimal("1234.50")
    assert model.model_dump()["id"] == _ID


AN11_TYPED = {
    "GET /api/v1/accounting/admin-fee-invoices/{invoice_id}/xrechnung-credit-note/check",
    "GET /api/v1/accounting/admin-fee-invoices/{invoice_id}/zugferd/check",
    "GET /api/v1/accounting/audit-exports",
    "GET /api/v1/accounting/audit-exports/{run_id}",
    "GET /api/v1/accounting/invoices/{invoice_id}/xrechnung/check",
    "GET /api/v1/accounting/ledgers/{ledger_id}/accounts/{account_id}/sheet",
    "GET /api/v1/accounting/ledgers/{ledger_id}/open-items",
    "GET /api/v1/accounting/ledgers/{ledger_id}/reports/account-sheet",
    "GET /api/v1/accounting/ledgers/{ledger_id}/reports/bank-statement",
    "GET /api/v1/accounting/ledgers/{ledger_id}/reports/income-expense",
    "GET /api/v1/accounting/ledgers/{ledger_id}/reports/line-property-drift",
    "GET /api/v1/accounting/ledgers/{ledger_id}/reports/liquidity",
    "GET /api/v1/accounting/ledgers/{ledger_id}/reports/monthly-matrix",
    "GET /api/v1/accounting/ledgers/{ledger_id}/reports/open-items",
    "GET /api/v1/accounting/ledgers/{ledger_id}/reports/payments-by-debtor",
    "GET /api/v1/accounting/ledgers/{ledger_id}/reports/revenue",
    "GET /api/v1/accounting/ledgers/{ledger_id}/reports/target-actual",
    "GET /api/v1/accounting/ledgers/{ledger_id}/reports/trial-balance",
    "GET /api/v1/accounting/ledgers/{ledger_id}/reports/vat-overview",
    "GET /api/v1/accounting/ledgers/{ledger_id}/reports/vat-overview-by-property",
    "GET /api/v1/accounting/ledgers/{ledger_id}/trial-balance",
    "GET /api/v1/banking/automation/levels",
    "GET /api/v1/banking/automation/switch-requests",
    "GET /api/v1/banking/learning",
    "GET /api/v1/banking/matching-metrics",
    "GET /api/v1/banking/matching/metrics",
    "GET /api/v1/banking/payment-bank-config/{account_id}",
    "GET /api/v1/banking/payment-batches",
    "GET /api/v1/banking/payment-batches/{batch_id}",
    "GET /api/v1/billing/heating-cost-imports",
    "GET /api/v1/billing/heating-cost-imports/{import_id}",
    "GET /api/v1/billing/owner-statements",
    "GET /api/v1/billing/owner-statements/{statement_id}",
    "GET /api/v1/billing/owner-statements/{statement_id}/outputs",
    "PATCH /api/v1/billing/owner-statements/{statement_id}/options",
    "POST /api/v1/accounting/admin-fee-invoices/{invoice_id}/zugferd/document",
    "POST /api/v1/accounting/audit-exports",
    "POST /api/v1/banking/auto-post",
    "POST /api/v1/banking/automation/level-requests",
    "POST /api/v1/banking/automation/level-requests/{request_id}/approve",
    "POST /api/v1/banking/automation/level-requests/{request_id}/reject",
    "POST /api/v1/banking/automation/switch-requests",
    "POST /api/v1/banking/automation/switch-requests/{request_id}/{decision}",
    "POST /api/v1/banking/payment-batches",
    "POST /api/v1/banking/payment-batches/{batch_id}/submit",
    "POST /api/v1/billing/heating-cost-imports",
    "POST /api/v1/billing/heating-cost-imports/{import_id}/apply",
    "POST /api/v1/billing/heating-cost-imports/{import_id}/check",
    "POST /api/v1/billing/heating-cost-imports/{import_id}/csv",
    "POST /api/v1/billing/owner-statements",
    "POST /api/v1/billing/owner-statements/{statement_id}/approve",
    "POST /api/v1/billing/owner-statements/{statement_id}/calculate",
    "POST /api/v1/billing/owner-statements/{statement_id}/transition",
    "PUT /api/v1/banking/automation",
    "PUT /api/v1/banking/automation/outgoing",
    "PUT /api/v1/banking/learning",
    "PUT /api/v1/banking/payment-bank-config/{account_id}",
    "PUT /api/v1/billing/heating-cost-imports/{import_id}",
    "PUT /api/v1/billing/heating-cost-imports/{import_id}/mapping",
    "PUT /api/v1/billing/heating-cost-imports/{import_id}/rows",
}


def test_an11_routes_stay_raw_typed() -> None:
    """The money routes typed in AN11 keep a ``RawJsonOut`` model (bytes unchanged)."""
    import typing

    from mhvp.core.listparams import _walk_routes
    from mhvp.main import app

    found: dict[str, typing.Any] = {}
    for path, route in _walk_routes(app.routes):
        methods = ",".join(sorted(route.methods - {"HEAD"}))
        found[f"{methods} {path}"] = route.response_model
    for key in AN11_TYPED:
        model = found[key]
        inner = (typing.get_args(model) or (model,))[0]
        assert isinstance(inner, type), key
        assert issubclass(inner, RawJsonOut), key
