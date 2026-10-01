"""GA14-06 (18.0 table, rule 0.1.4): gate coverage of money, statement and dispatch routes.

``GATED_ROUTES`` is the register of routes that must check a release gate; the test proves
statically (endpoint source, its dependencies and the mhvp helpers it calls, up to five
levels) that the named gate is referenced. Every other mutating route whose path looks like
a money, statement or dispatch function must be listed in ``REVIEWED_UNGATED``: a new route
of that kind fails the test until it is gated or classified. ``REVIEWED_UNGATED`` is the
inventory of 01.10.2026; its classification is open question AA01-01 (operator, G1 to G4),
it is not a release. The runtime proof (403 MHVP-GATE-0001 with the closed resolver) for every
route of the register is ``tests/integration/test_ab01_gate_runtime.py`` (AB01).
"""

import inspect
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.routing import APIRoute

from mhvp.core.config import Settings
from mhvp.core.release_gates import ReleaseGate
from tests.unit.helpers import app_with_checks

GATED_ROUTES: tuple[tuple[str, str, str], ...] = (
    ("POST", "/api/v1/deposit-settlements/{settlement_id}/release", "G3"),
    ("POST", "/api/v1/imports/migration/ledgers/{ledger_id}/switch-requests", "G1"),
    ("POST", "/api/v1/imports/migration/switch-requests/{request_id}/approve", "G1"),
    ("POST", "/api/v1/imports/migration/switch-requests/{request_id}/reject", "G1"),
    ("POST", "/api/v1/accounting/ledgers/{ledger_id}/leading", "G1"),
    ("POST", "/api/v1/accounting/ledgers/{ledger_id}/open-items/settlement-proposal/confirm", "G1"),
    ("POST", "/api/v1/accounting/receivable-runs/{run_id}/post", "G1"),
    ("POST", "/api/v1/accounting/dunning-cases/{case_id}/letter/send", "G1"),
    ("POST", "/api/v1/accounting/g1-opening/request", "G1"),
    ("POST", "/api/v1/accounting/admin-fee-invoices/{invoice_id}/posting-drafts", "G1"),
    ("POST", "/api/v1/contracts/{contract_id}/rent-invoices", "G1"),
    ("POST", "/api/v1/contracts/{contract_id}/rent-invoices/{invoice_id}/credit-note", "G1"),
    ("POST", "/api/v1/banking/auto-post", "G1"),
    ("POST", "/api/v1/banking/payment-batches", "G2"),
    ("POST", "/api/v1/banking/payment-batches/{batch_id}/submit", "G2"),
    ("POST", "/api/v1/accounting/direct-debits/{run_id}/submit", "G2"),
    ("POST", "/api/v1/integrations/lexoffice/export/invoices", "G1"),
    ("POST", "/api/v1/integrations/lexoffice/export/contacts", "G1"),
    ("POST", "/api/v1/statements/{statement_id}/transition", "G3"),
    ("POST", "/api/v1/statements/{statement_id}/letters/send", "G3"),
    ("POST", "/api/v1/statements/{statement_id}/result-entries", "G3"),
    ("POST", "/api/v1/billing/owner-statements/{statement_id}/transition", "G3"),
    ("POST", "/api/v1/hoa/statements/{statement_id}/transition", "G4"),
    ("POST", "/api/v1/hoa/statements/{statement_id}/post", "G4"),
    ("POST", "/api/v1/hoa/asset-reports/{report_id}/transition", "G4"),
    ("POST", "/api/v1/hoa/reserve-statements/{reserve_statement_id}/transition", "G4"),
    ("POST", "/api/v1/letting/rent-increases/{case_id}/letter/pdf", "G3"),
    ("POST", "/api/v1/letting/rent-increases/{case_id}/actions", "G3"),
    ("POST", "/api/v1/postal/jobs", "G1"),
)

REVIEWED_UNGATED: frozenset[tuple[str, str]] = frozenset(
    {
        ("PATCH", "/api/v1/banking/payment-orders/{order_id}"),
        ("POST", "/api/v1/accounting/admin-fee-invoices/{invoice_id}/release"),
        ("POST", "/api/v1/accounting/direct-debits"),
        ("POST", "/api/v1/accounting/direct-debits/preview"),
        ("POST", "/api/v1/accounting/direct-debits/{run_id}/approve"),
        ("POST", "/api/v1/accounting/direct-debits/{run_id}/bank-status"),
        ("POST", "/api/v1/accounting/direct-debits/{run_id}/cancel"),
        ("POST", "/api/v1/accounting/direct-debits/{run_id}/file"),
        ("POST", "/api/v1/accounting/direct-debits/{run_id}/pre-notifications"),
        ("POST", "/api/v1/accounting/dunning-blocks/{block_id}/release"),
        ("POST", "/api/v1/accounting/invoices/{invoice_id}/post"),
        ("POST", "/api/v1/accounting/invoices/{invoice_id}/release"),
        ("POST", "/api/v1/accounting/ledgers/{ledger_id}/entries/cost-transfer"),
        ("POST", "/api/v1/accounting/ledgers/{ledger_id}/entries/interest"),
        ("POST", "/api/v1/accounting/ledgers/{ledger_id}/entries/{entry_id}/post"),
        ("POST", "/api/v1/accounting/ledgers/{ledger_id}/entries/{entry_id}/reverse"),
        ("POST", "/api/v1/accounting/ledgers/{ledger_id}/open-items/settlement-proposal"),
        ("POST", "/api/v1/accounting/payment-runs/bank-status-reports"),
        ("POST", "/api/v1/accounting/payment-runs/orders"),
        ("POST", "/api/v1/accounting/payment-runs/payout-orders"),
        ("POST", "/api/v1/accounting/payment-runs/previews"),
        ("POST", "/api/v1/accounting/receivable-runs/{run_id}/reverse"),
        ("POST", "/api/v1/accounting/templates/{template_id}/release"),
        ("POST", "/api/v1/ai/knowledge/{entry_id}/submit"),
        ("POST", "/api/v1/ai/providers/{provider}/release"),
        ("POST", "/api/v1/banking/auto-posting/digests/build"),
        ("POST", "/api/v1/banking/auto-posting/digests/{digest_id}/confirm"),
        ("POST", "/api/v1/banking/auto-posting/reviews/{item_id}"),
        ("POST", "/api/v1/banking/payment-batches/{batch_id}/bank-status"),
        ("POST", "/api/v1/banking/payment-orders"),
        ("POST", "/api/v1/banking/payment-orders/{order_id}/approve"),
        ("POST", "/api/v1/banking/payment-orders/{order_id}/cancel"),
        ("POST", "/api/v1/dispatches"),
        ("POST", "/api/v1/dispatches/serial"),
        ("POST", "/api/v1/dispatches/serial-merge"),
        ("POST", "/api/v1/dispatches/{dispatch_id}/evidence"),
        ("POST", "/api/v1/documents/{document_id}/redactions/{redaction_id}/release"),
        ("POST", "/api/v1/handover/protocols/{protocol_id}/dispatches"),
        ("POST", "/api/v1/handover/protocols/{protocol_id}/meters/transfer"),
        ("POST", "/api/v1/hoa/inspection-requests/{request_id}/transition"),
        ("POST", "/api/v1/hoa/plans/{plan_id}/transition"),
        ("POST", "/api/v1/hoa/statements/{statement_id}/acquisitions/{contract_id}/release"),
        ("POST", "/api/v1/imports/migration/ledgers/{ledger_id}/opening-balances/import"),
        ("POST", "/api/v1/imports/migration/opening-balances/{balance_id}/post"),
        ("POST", "/api/v1/imports/migration/opening-balances/{balance_id}/release"),
        ("POST", "/api/v1/letters"),
        ("POST", "/api/v1/letters/preview"),
        ("POST", "/api/v1/letters/serial"),
        ("POST", "/api/v1/mail/messages/{message_id}/submit"),
        ("POST", "/api/v1/metering/transmissions/{transmission_id}/release"),
        ("POST", "/api/v1/portal-admin/sepa-mandate-proposals/{proposal_id}/decide"),
        ("POST", "/api/v1/portal/sepa-mandates"),
        ("POST", "/api/v1/privacy/deletion-profiles/{profile_id}/release"),
        ("POST", "/api/v1/retention-profiles/{profile_id}/release"),
        ("POST", "/api/v1/sepa-mandates"),
        ("POST", "/api/v1/sepa-mandates/{mandate_id}/revoke"),
        ("POST", "/api/v1/statements/{statement_id}/letters"),
        ("POST", "/api/v1/statements/{statement_id}/letters/preview"),
        ("PUT", "/api/v1/accounting/direct-debits/creditor-ids/legal-entities/{legal_entity_id}"),
        ("PUT", "/api/v1/accounting/direct-debits/creditor-ids/tenant"),
        ("PUT", "/api/v1/accounting/ledgers/{ledger_id}/payment-type-accounts"),
        ("PUT", "/api/v1/accounting/payment-runs/bank-limits/{account_id}"),
        ("PUT", "/api/v1/accounting/payment-runs/settings"),
        ("PUT", "/api/v1/banking/payment-bank-config/{account_id}"),
        ("PUT", "/api/v1/imports/migration/ledgers/{ledger_id}/opening-balances"),
    }
)

MONEY_PATH = re.compile(
    r"/(post|submit|send|auto-post|auto-posting|pay|payment-[a-z-]+|payment-batches|"
    r"payment-orders|payment-runs|direct-debits|sepa-[a-z-]+|transfer|settlement-proposal|"
    r"dispatches|transition|release|letters|result-entries|opening-balances|interest|"
    r"cost-transfer|reverse)(/|$)"
)
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_GATE = re.compile(r"ReleaseGate\.(G[1-5])")
_CALL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\s*\(")


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


def _gates_of(fn: Callable[..., Any], depth: int = 0, seen: set[int] | None = None) -> set[str]:
    seen = seen if seen is not None else set()
    fn = inspect.unwrap(fn)
    if id(fn) in seen or depth > 4:
        return set()
    seen.add(id(fn))
    try:
        source = inspect.getsource(fn)
    except (OSError, TypeError):
        return set()
    found = set(_GATE.findall(source))
    # ``require_release_gate(ReleaseGate.Gx)`` dependencies carry the gate in their closure.
    for cell in getattr(fn, "__closure__", None) or ():
        value = cell.cell_contents
        if isinstance(value, ReleaseGate):
            found.add(value.value)
    namespace = getattr(fn, "__globals__", {})
    for name in set(_CALL.findall(source)):
        head, _, attr = name.partition(".")
        obj = namespace.get(head)
        if obj is not None and attr:
            obj = getattr(obj, attr, None)
        if (
            callable(obj)
            and str(getattr(obj, "__module__", "")).startswith("mhvp")
            and inspect.isfunction(inspect.unwrap(obj))
        ):
            found |= _gates_of(obj, depth + 1, seen)
    return found


@pytest.fixture(scope="module")
def routes() -> dict[tuple[str, str], set[str]]:
    from tests.conftest import make_settings

    settings: Settings = make_settings()
    app = app_with_checks(settings)
    out: dict[tuple[str, str], set[str]] = {}
    for path, route in _walk(app.routes):
        gates = _gates_of(route.endpoint)
        for dep in route.dependant.dependencies:
            if dep.call is not None:
                gates |= _gates_of(dep.call)
        for method in route.methods & WRITE_METHODS:
            out[(method, path)] = gates
    return out


def test_register_routes_exist_and_check_their_gate(
    routes: dict[tuple[str, str], set[str]],
) -> None:
    missing = [(m, p) for m, p, _ in GATED_ROUTES if (m, p) not in routes]
    assert missing == [], f"Registered gated routes no longer exist: {missing}"
    ungated = [(m, p, g) for m, p, g in GATED_ROUTES if g not in routes[(m, p)]]
    assert ungated == [], f"Registered routes without their release gate: {ungated}"


def test_no_unclassified_money_route(routes: dict[tuple[str, str], set[str]]) -> None:
    registered = {(m, p) for m, p, _ in GATED_ROUTES}
    unknown = sorted(
        key
        for key, gates in routes.items()
        if MONEY_PATH.search(key[1])
        and key not in registered
        and key not in REVIEWED_UNGATED
        and not gates
    )
    assert unknown == [], (
        "New money, statement or dispatch routes without release gate; gate them or classify "
        f"them in REVIEWED_UNGATED (AA01-01): {unknown}"
    )


def test_reviewed_inventory_is_current(routes: dict[tuple[str, str], set[str]]) -> None:
    stale = sorted(key for key in REVIEWED_UNGATED if key not in routes)
    assert stale == [], f"Reviewed routes no longer exist, remove them: {stale}"
