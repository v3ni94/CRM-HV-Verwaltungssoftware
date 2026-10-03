"""AJ05 (GAI-303): table driven authorization tests for the accounting and banking routes
that had no tenant separation test (404 for a foreign tenant) or no 403 test (read right).

Two tables drive the tests:

* ``SEPARATION_ROUTES``: every route with a path parameter. A tenant administrator of tenant B
  calls it with identifiers that belong to tenant A (ledger, account, supplier contact, DATEV
  mapping created in the own test world) or with identifiers unknown in tenant B. The answer
  must be 404 (never 2xx, never 403, never 500), and the objects of tenant A stay unchanged.
* ``FORBIDDEN_ROUTES``: every writing route. The system role ``read_only`` of tenant A gets 403
  with ``MHVP-AUTH-0003`` before any body validation or object lookup.

Request bodies are derived from the live OpenAPI schema of the app (required fields with
syntactically valid values), so that the guard and the object lookup decide and not the
request validation.
"""

import asyncio
import re
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.services import local_today
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration

P = "/api/v1"
FORBIDDEN_CODE = "MHVP-AUTH-0003"

# GAI-3_liste_ohne_mandantentrennungstest.txt, areas accounting and banking.
SEPARATION_ROUTES: list[tuple[str, str]] = [
    ("POST", "/accounting/admin-fee-invoices/{invoice_id}/posting-drafts"),
    ("DELETE", "/accounting/admin-fees/{fee_id}"),
    ("POST", "/accounting/admin-fees/{fee_id}/invoice-issue"),
    ("POST", "/accounting/credit-payables/{row_id}/payment-order"),
    ("POST", "/accounting/credit-payables/{row_id}/withdraw"),
    ("PATCH", "/accounting/datev-mappings/{mapping_id}"),
    ("DELETE", "/accounting/datev-mappings/{mapping_id}"),
    ("POST", "/accounting/dunning-cases/{case_id}/mahnbescheid"),
    ("POST", "/accounting/dunning-cases/{case_id}/mahnbescheid-preview"),
    ("POST", "/accounting/dunning-cases/{case_id}/mahnbescheid-vorbereitung"),
    ("POST", "/accounting/invoices/{invoice_id}/confirm-iban"),
    ("PATCH", "/accounting/ledgers/{ledger_id}/accounts/{account_id}"),
    ("DELETE", "/accounting/ledgers/{ledger_id}/accounts/{account_id}"),
    ("PUT", "/accounting/ledgers/{ledger_id}/accounts/{account_id}/tax-flags"),
    ("PUT", "/accounting/ledgers/{ledger_id}/interest-tax-config"),
    ("POST", "/accounting/ledgers/{ledger_id}/open-items/settlement-proposal"),
    ("POST", "/accounting/ledgers/{ledger_id}/open-items/settlement-proposal/confirm"),
    ("PATCH", "/accounting/open-items/{open_item_id}/notice-received"),
    ("POST", "/accounting/receivable-runs/{run_id}/reverse"),
    ("PATCH", "/accounting/recurring-invoices/{plan_id}"),
    ("DELETE", "/accounting/recurring-invoices/{plan_id}"),
    ("POST", "/accounting/recurring-invoices/{plan_id}/end"),
    ("POST", "/accounting/recurring-invoices/{plan_id}/generate"),
    ("PATCH", "/accounting/rule-versions/checkpoints/{version_id}"),
    ("POST", "/accounting/tax/invoices/{invoice_id}/second-approval"),
    ("PUT", "/accounting/tax/suppliers/{contact_id}/profile"),
    ("GET", "/accounting/admin-fee-invoices/{invoice_id}"),
    ("GET", "/accounting/admin-fee-invoices/{invoice_id}/xrechnung-credit-note.xml"),
    ("GET", "/accounting/admin-fee-invoices/{invoice_id}/xrechnung-credit-note/check"),
    ("GET", "/accounting/admin-fee-invoices/{invoice_id}/zugferd.pdf"),
    ("POST", "/banking/auto-posting/digests/{digest_id}/confirm"),
    ("POST", "/banking/automation/switch-requests/{request_id}/{decision}"),
    ("POST", "/banking/ebics/subscribers/{subscriber_id}/ini/external"),
    ("POST", "/banking/finapi/connections/{finapi_connection_id}/disconnect"),
    ("POST", "/banking/finapi/connections/{finapi_connection_id}/fetch"),
    ("POST", "/banking/finapi/connections/{finapi_connection_id}/reauthorize"),
    ("PATCH", "/banking/fints/connections/{fints_connection_id}"),
    ("POST", "/banking/fints/sessions/{session_id}/tan"),
    ("POST", "/banking/invoice-matching/{invoice_id}/match"),
    ("PUT", "/banking/payment-bank-config/{account_id}"),
    ("POST", "/banking/transactions/{tx_id}/ai-posting"),
    ("POST", "/banking/transactions/{tx_id}/correct"),
    ("POST", "/banking/transactions/{tx_id}/learn"),
    ("POST", "/banking/transactions/{tx_id}/payer-iban"),
    ("GET", "/banking/ebics/subscribers/{subscriber_id}"),
    ("GET", "/banking/ebics/subscribers/{subscriber_id}/letters"),
    ("GET", "/banking/ebics/subscribers/{subscriber_id}/letters.pdf"),
    ("GET", "/banking/invoice-matching/{invoice_id}"),
    ("GET", "/banking/payment-bank-config/{account_id}"),
    # GAJ-302 (Welle 23, AM12): routes with a path parameter found without a 404 test.
    ("POST", "/accounting/credit-payables/{row_id}/release"),
    ("GET", "/accounting/ledgers/{ledger_id}/accounts/{account_id}/sheet"),
    ("GET", "/accounting/admin-fees/{fee_id}/invoice-preview"),
    ("GET", "/accounting/invoices/{invoice_id}/discount"),
    ("GET", "/accounting/tax/invoices/{invoice_id}/approval"),
    ("GET", "/accounting/ledgers/{ledger_id}/reports/liquidity"),
    ("POST", "/banking/ebics/subscribers/{subscriber_id}/hpb"),
]

# GAI-3_liste_ohne_403_test.txt, routes of the accounting and banking modules.
FORBIDDEN_ROUTES: list[tuple[str, str]] = [
    ("POST", "/accounting/acceptance/cases/{case_id}/expected"),
    ("DELETE", "/accounting/admin-fees/{fee_id}"),
    ("POST", "/accounting/datev-mappings"),
    ("PATCH", "/accounting/datev-mappings/{mapping_id}"),
    ("DELETE", "/accounting/datev-mappings/{mapping_id}"),
    ("PUT", "/accounting/g1-opening/items/{item_key}"),
    ("PATCH", "/accounting/open-items/{open_item_id}/notice-received"),
    ("POST", "/accounting/period-locks"),
    ("PATCH", "/accounting/rule-versions/checkpoints/{version_id}"),
    ("POST", "/banking/automation/switch-requests/{request_id}/{decision}"),
    ("POST", "/banking/imports/csv"),
    ("POST", "/invoices/intake/paperless"),
    ("POST", "/accounting/admin-fees/{fee_id}/invoice-issue"),
    ("POST", "/accounting/credit-payables"),
    ("POST", "/accounting/direct-debits"),
    ("PUT", "/accounting/direct-debits/creditor-ids/tenant"),
    ("POST", "/accounting/dunning-cases/{case_id}/mahnbescheid"),
    ("POST", "/accounting/dunning-cases/{case_id}/mahnbescheid-preview"),
    ("POST", "/accounting/dunning-cases/{case_id}/mahnbescheid-vorbereitung"),
    ("PUT", "/accounting/dunning-interest"),
    ("DELETE", "/accounting/dunning-settings"),
    ("POST", "/accounting/dunning-settings/letter-preview"),
    ("POST", "/accounting/dunning-settings/presets"),
    ("PUT", "/accounting/ledgers/{ledger_id}/interest-tax-config"),
    ("POST", "/accounting/ledgers/{ledger_id}/open-items/settlement-proposal"),
    ("POST", "/banking/ebics/subscribers/{subscriber_id}/ini/external"),
    ("POST", "/banking/finapi/accounts/{link_id}/assign"),
    ("POST", "/banking/finapi/accounts/{link_id}/fetch"),
    ("POST", "/banking/finapi/connections/{finapi_connection_id}/fetch"),
    ("POST", "/banking/finapi/connections/{finapi_connection_id}/reauthorize"),
    ("POST", "/banking/fints/accounts/{link_id}/assign"),
    ("PATCH", "/banking/fints/connections/{fints_connection_id}"),
    ("DELETE", "/banking/fints/connections/{fints_connection_id}"),
    ("POST", "/banking/fints/connections/{fints_connection_id}/restart"),
    ("POST", "/banking/fints/sessions/{session_id}/tan"),
    ("POST", "/banking/invoice-matching/{invoice_id}/match"),
    ("POST", "/contracts/{contract_id}/rent-invoices"),
    ("POST", "/contracts/{contract_id}/rent-invoices/{invoice_id}/credit-note"),
]

# Not in the separation table: ``/accounting/acceptance/cases/{case_id}`` (GET and POST
# ``/expected``). ``case_id`` is an annex D case code of a global catalogue (D01 ...), not a
# tenant object; unknown codes answer 422 and the stored expected values are tenant rows under
# RLS (covered by test_m8_year_acceptance.py).

# Routes that check a closed release gate or a tenant switch before the object lookup. The
# foreign tenant is stopped by that precondition, nothing of tenant A is read or changed; the
# test pins the exact answer so that a later change to the order is noticed.
PRECONDITION_FIRST: dict[tuple[str, str], tuple[int, str]] = {
    ("POST", "/accounting/admin-fee-invoices/{invoice_id}/posting-drafts"): (
        403,
        "MHVP-GATE-0001",
    ),
    ("POST", "/banking/transactions/{tx_id}/ai-posting"): (403, "MHVP-AI-0001"),
    ("POST", "/banking/ebics/subscribers/{subscriber_id}/ini/external"): (409, "MHVP-BANK-0051"),
    ("POST", "/banking/ebics/subscribers/{subscriber_id}/hpb"): (409, "MHVP-BANK-0051"),
}

# Writing methods that persist nothing (previews and proposals) and are guarded by the read
# right on purpose. The reader passes the guard; the expected answer is pinned here.
READ_EFFECT_ONLY: dict[tuple[str, str], int] = {
    ("POST", "/accounting/dunning-cases/{case_id}/mahnbescheid-preview"): 404,
    ("POST", "/accounting/dunning-settings/letter-preview"): 200,
    ("POST", "/accounting/ledgers/{ledger_id}/open-items/settlement-proposal"): 404,
}

# Path parameters that are no object identifiers.
FIXED_PARAMS = {"decision": "approve", "item_key": "aj05-check"}

# Routes whose body validation needs more than the schema derived minimum.
BODY_OVERRIDES: dict[tuple[str, str], Any] = {
    ("PATCH", "/banking/fints/connections/{fints_connection_id}"): {
        "fints_url": "https://fints.aj05.example.org/fints",
        "pin": "aj05-pin",
    },
}


def _ids(rows: list[tuple[str, str]]) -> list[str]:
    return [f"{m} {p}" for m, p in rows]


# Test world ---------------------------------------------------------------------------------


async def _world(settings: Any) -> World:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"aj05-a-{RUN}", name=f"AJ05 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aj05-b-{RUN}", name=f"AJ05 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("aj05admin", a, "tenant_admin"),
            ("aj05read", a, "read_only"),
            ("aj05other", b, "tenant_admin"),
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


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


@pytest.fixture(scope="module")
def headers(client: TestClient, world: World) -> dict[str, dict[str, str]]:
    return {name: bearer(login(client, world, name)) for name in world.users}


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture(scope="module")
def tenant_a_objects(client: TestClient, headers: dict[str, dict[str, str]]) -> dict[str, str]:
    """Objects of tenant A whose identifiers tenant B uses in the separation table."""
    h = headers["aj05admin"]
    prop = _ok(
        client.post(
            f"{P}/properties",
            json={"number": "105", "name": f"AJ05 {RUN}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(client.post(f"{P}/accounting/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{P}/accounting/ledgers",
            json={"legal_entity_id": hoa, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )["id"]
    accounts = _ok(client.get(f"{P}/accounting/ledgers/{ledger}/accounts", headers=h))
    contact = _ok(
        client.post(
            f"{P}/contacts",
            json={"kind": "company", "company_name": f"AJ05 Lieferant {RUN} GmbH"},
            headers=h,
        ),
        201,
    )
    return {
        "ledger_id": ledger,
        "account_id": accounts[0]["id"],
        "contact_id": contact["id"],
    }


# Request construction -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def openapi(client: TestClient) -> dict[str, Any]:
    return dict(client.app.openapi())  # type: ignore[attr-defined]


def _resolve(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        schema = spec["components"]["schemas"][name]
    return schema


def _sample(spec: dict[str, Any], schema: dict[str, Any], depth: int = 0) -> Any:
    """Minimal syntactically valid value for a JSON schema (required fields only)."""
    schema = _resolve(spec, schema)
    if depth > 6:
        return None
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            options = [o for o in schema[key] if _resolve(spec, o).get("type") != "null"]
            return _sample(spec, options[0], depth + 1) if options else None
    kind = schema.get("type")
    fmt = schema.get("format", "")
    if kind == "object" or "properties" in schema:
        props = schema.get("properties", {})
        return {
            name: _sample(spec, props[name], depth + 1)
            for name in schema.get("required", [])
            if name in props
        }
    if kind == "array":
        count = max(int(schema.get("minItems", 0)), 0)
        return [_sample(spec, schema.get("items", {}), depth + 1) for _ in range(count)]
    if kind == "boolean":
        return False
    if kind in ("integer", "number"):
        low = schema.get("minimum", schema.get("exclusiveMinimum", 0))
        value = max(1, int(low) + 1)
        high = schema.get("maximum")
        return min(value, int(high)) if high is not None else value
    if kind == "string":
        if fmt == "uuid":
            return str(uuid.uuid4())
        if fmt == "date":
            return local_today().isoformat()
        if fmt == "date-time":
            return f"{local_today().isoformat()}T00:00:00Z"
        if schema.get("pattern"):
            return None  # needs an override; let the request show it
        size = max(int(schema.get("minLength", 1)), 1)
        return ("aj05-" + "x" * size)[: max(size, int(schema.get("maxLength", 40)))]
    return None


def _body(spec: dict[str, Any], method: str, path: str) -> Any:
    if (method, path) in BODY_OVERRIDES:
        return BODY_OVERRIDES[(method, path)]
    op = spec["paths"][P + path][method.lower()]
    content = op.get("requestBody", {}).get("content", {})
    if "application/json" in content:
        return _sample(spec, content["application/json"].get("schema", {}))
    return None


def _query(spec: dict[str, Any], method: str, path: str) -> dict[str, Any]:
    op = spec["paths"][P + path][method.lower()]
    return {
        p["name"]: _sample(spec, p.get("schema", {}))
        for p in op.get("parameters", [])
        if p.get("in") == "query" and p.get("required")
    }


def _fill(path: str, known: dict[str, str]) -> str:
    def value(match: re.Match[str]) -> str:
        name = match.group(1)
        return FIXED_PARAMS.get(name) or known.get(name) or str(uuid.uuid4())

    return re.sub(r"\{([^}]+)\}", value, path)


def _call(
    client: TestClient,
    spec: dict[str, Any],
    method: str,
    path: str,
    headers: dict[str, str],
    known: dict[str, str],
) -> Any:
    body = _body(spec, method, path)
    kwargs: dict[str, Any] = {"headers": headers, "params": _query(spec, method, path)}
    if body is not None and method != "GET":
        kwargs["json"] = body
    return client.request(method, P + _fill(path, known), **kwargs)


# Tests --------------------------------------------------------------------------------------


def test_tables_match_live_routes(openapi: dict[str, Any]) -> None:
    for method, path in SEPARATION_ROUTES + FORBIDDEN_ROUTES:
        assert P + path in openapi["paths"], path
        assert method.lower() in openapi["paths"][P + path], f"{method} {path}"
    assert all("{" in p for _, p in SEPARATION_ROUTES)


@pytest.mark.parametrize(("method", "path"), SEPARATION_ROUTES, ids=_ids(SEPARATION_ROUTES))
def test_foreign_tenant_gets_404(
    client: TestClient,
    openapi: dict[str, Any],
    headers: dict[str, dict[str, str]],
    tenant_a_objects: dict[str, str],
    method: str,
    path: str,
) -> None:
    response = _call(client, openapi, method, path, headers["aj05other"], tenant_a_objects)
    if (method, path) in PRECONDITION_FIRST:
        status, code = PRECONDITION_FIRST[(method, path)]
        assert response.status_code == status, f"{method} {path}: {response.text}"
        assert response.json().get("code") == code
        return
    assert response.status_code == 404, f"{method} {path}: {response.status_code} {response.text}"


@pytest.mark.parametrize(("method", "path"), FORBIDDEN_ROUTES, ids=_ids(FORBIDDEN_ROUTES))
def test_read_only_role_gets_403(
    client: TestClient,
    openapi: dict[str, Any],
    headers: dict[str, dict[str, str]],
    tenant_a_objects: dict[str, str],
    method: str,
    path: str,
) -> None:
    response = _call(client, openapi, method, path, headers["aj05read"], tenant_a_objects)
    if (method, path) in READ_EFFECT_ONLY:
        expected = READ_EFFECT_ONLY[(method, path)]
        assert response.status_code == expected, f"{method} {path}: {response.text}"
        return
    assert response.status_code == 403, f"{method} {path}: {response.status_code} {response.text}"
    assert response.json().get("code") == FORBIDDEN_CODE


def test_tenant_a_objects_unchanged_after_foreign_calls(
    client: TestClient, headers: dict[str, dict[str, str]], tenant_a_objects: dict[str, str]
) -> None:
    """Runs after the separation table: the ledger account of tenant A still exists and the
    foreign tenant does not see it."""
    h = headers["aj05admin"]
    ledger, account = tenant_a_objects["ledger_id"], tenant_a_objects["account_id"]
    accounts = _ok(client.get(f"{P}/accounting/ledgers/{ledger}/accounts", headers=h))
    assert account in {a["id"] for a in accounts}
    foreign = client.get(f"{P}/accounting/ledgers/{ledger}/accounts", headers=headers["aj05other"])
    assert foreign.status_code == 404
