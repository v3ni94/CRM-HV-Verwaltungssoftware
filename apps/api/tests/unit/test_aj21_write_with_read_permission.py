"""AJ21 (GAI-301): mutating routes guarded only by ``*:read`` permissions.

The test walks the dependency tree of every mutating route, collects the permissions
required via ``require_permission`` and fails for a route whose permissions are all read
permissions unless it is classified below. ``PREVIEW_ROUTES`` are functionally read only
(preview, check, calculation, nothing persisted). ``HANDLER_CHECKED`` require a write right
inside the handler or a wrapper dependency. ``PERSONAL_ROUTES`` change only the caller's own
data. ``FIXED_ROUTES`` were switched to a write permission by AJ21 and must keep one.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.routing import APIRoute

from mhvp.core.config import Settings
from tests.unit.helpers import app_with_checks

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
READ_ACTIONS = ("read", "view", "list")

PREVIEW_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/v1/accounting/datev/check-file"),
        ("POST", "/api/v1/accounting/direct-debits/preview"),
        ("POST", "/api/v1/accounting/dunning-cases/{case_id}/letter-preview"),
        ("POST", "/api/v1/accounting/dunning-cases/{case_id}/mahnbescheid-preview"),
        ("POST", "/api/v1/accounting/dunning-settings/letter-preview"),
        ("POST", "/api/v1/accounting/ledgers/{ledger_id}/open-items/settlement-proposal"),
        ("POST", "/api/v1/data-quality/check"),
        ("POST", "/api/v1/deposits/{deposit_id}/settlements/preview"),
        ("POST", "/api/v1/imports/immoware24/files/{source_id}/check"),
        ("POST", "/api/v1/letters/preview"),
        ("POST", "/api/v1/metering/transmissions/check"),
        (
            "POST",
            "/api/v1/objektakte/properties/{property_id}/completeness/nachforderungsschreiben",
        ),
        ("POST", "/api/v1/onboarding/person-match"),
        ("POST", "/api/v1/onboarding/person-match-batch"),
        ("POST", "/api/v1/portal-admin/forms/preview"),
        ("POST", "/api/v1/statements/co2-split"),
        ("POST", "/api/v1/statements/{statement_id}/info-sheet/preview"),
        ("POST", "/api/v1/statements/{statement_id}/letters/preview"),
        ("POST", "/api/v1/tenant/number-formats/preview"),
    }
)
# Write right checked in the handler (tickets: tickets:update or tenant_settings:update via
# _require_template_manage/_require_reply_template_manage; metering: _transmission_writer
# plus KIND_PERMISSION of the transmission).
HANDLER_CHECKED: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/v1/metering/transmissions/{transmission_id}/order"),
        ("POST", "/api/v1/metering/transmissions/{transmission_id}/poll"),
        ("POST", "/api/v1/metering/transmissions/{transmission_id}/release"),
        ("POST", "/api/v1/tickets/process-catalogue/seed"),
        ("POST", "/api/v1/tickets/reply-templates"),
        ("PATCH", "/api/v1/tickets/reply-templates/{template_id}"),
        ("DELETE", "/api/v1/tickets/reply-templates/{template_id}"),
        ("POST", "/api/v1/tickets/templates"),
        ("PATCH", "/api/v1/tickets/templates/{template_id}"),
    }
)
# Personal calendar subscription token of the caller (open question AJ21-01).
PERSONAL_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/v1/workspace/calendar-feed/token"),
        ("DELETE", "/api/v1/workspace/calendar-feed/token"),
    }
)
FIXED_ROUTES: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/mail/mail-approval/deputies"): "communication:update",
    ("DELETE", "/api/v1/mail/mail-approval/deputies/{deputy_id}"): "communication:update",
    ("POST", "/api/v1/mail/playbooks/{playbook_id}/feedback"): "communication:update",
    ("POST", "/api/v1/mail/playbooks/{playbook_id}/use"): "communication:update",
    ("POST", "/api/v1/sla/alerts/{alert_id}/ack"): "sla:update",
    ("POST", "/api/v1/ai/knowledge/{entry_id}/feedback"): "ai:create",
}


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


def _permissions(dependant: Any) -> set[str]:
    found: set[str] = set()
    for dep in dependant.dependencies:
        call = dep.call
        for cell in getattr(call, "__closure__", None) or ():
            value = cell.cell_contents
            if isinstance(value, str) and value.count(":") >= 1 and " " not in value:
                found.add(value)
        found |= _permissions(dep)
    return found


@pytest.fixture(scope="module")
def route_permissions() -> dict[tuple[str, str], set[str]]:
    from tests.conftest import make_settings

    settings: Settings = make_settings()
    app = app_with_checks(settings)
    out: dict[tuple[str, str], set[str]] = {}
    for path, route in _walk(app.routes):
        perms = _permissions(route.dependant)
        for method in route.methods & WRITE_METHODS:
            out[(method, path)] = perms
    return out


def _read_only(perms: set[str]) -> bool:
    return bool(perms) and all(p.rsplit(":", 1)[-1] in READ_ACTIONS for p in perms)


def test_no_unclassified_write_route_with_read_permission(
    route_permissions: dict[tuple[str, str], set[str]],
) -> None:
    allowed = PREVIEW_ROUTES | HANDLER_CHECKED | PERSONAL_ROUTES
    offenders = sorted(
        k for k, perms in route_permissions.items() if _read_only(perms) and k not in allowed
    )
    assert offenders == [], f"Mutating routes guarded only by read rights: {offenders}"


def test_classified_routes_exist(route_permissions: dict[tuple[str, str], set[str]]) -> None:
    every = PREVIEW_ROUTES | HANDLER_CHECKED | PERSONAL_ROUTES | set(FIXED_ROUTES)
    missing = sorted(k for k in every if k not in route_permissions)
    assert missing == []
    stale = sorted(
        k
        for k in PREVIEW_ROUTES | HANDLER_CHECKED | PERSONAL_ROUTES
        if not _read_only(route_permissions[k])
    )
    assert stale == [], f"Classified routes no longer read only, remove them: {stale}"


@pytest.mark.parametrize(("route", "permission"), sorted(FIXED_ROUTES.items()))
def test_fixed_routes_require_write_permission(
    route_permissions: dict[tuple[str, str], set[str]],
    route: tuple[str, str],
    permission: str,
) -> None:
    assert permission in route_permissions[route]
