"""Messdienstleister stage 2: real ista and KALO adapters against ``httpx.MockTransport``
(artificial data; no sandbox or production system is called). Master prompt section 13,
cases 9 (environment separation, no secrets in outputs), 10 (expired credentials, partial
fetches), 11 (write timeout never blindly repeated) and 12 (test and fetch order nothing)."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest

from mhvp.core.webhooks import PinnedTarget
from mhvp.metering import bved
from mhvp.metering.adapters import DocumentRecord, adapter_for
from mhvp.metering.adapters_ista import IstaAdapter
from mhvp.metering.adapters_kalo import KaloAdapter
from mhvp.metering.http import ProviderHttp, ProviderHttpError, sanitize
from mhvp.metering.providers import Function

CLIENT_SECRET = "s3cr3t-client-value"
BASIC_PASSWORD = "b4sic-password-value"
TOKEN = "tok-abc-123"

ISTA_CONFIG: dict[str, Any] = {
    "config_environment": "test",
    "base_urls": {
        "billing_unit_data": "https://bud.example.test",
        "billing_result": "https://br.example.test",
        "consumption": "https://eed.example.test",
        "documents": "https://docs.example.test",
        "roles": "https://roles.example.test",
        "billing_input": "https://bi.example.test",
    },
    "token_url": "https://auth.example.test/oauth/token",
    "backoff_seconds": 0.5,
}
ISTA_SECRETS = {
    "client_id": "cid",
    "client_secret": CLIENT_SECRET,
    "basic_username": "user",
    "basic_password": BASIC_PASSWORD,
    "client_cert_pem": "-----BEGIN CERTIFICATE-----\nAAA\n-----END CERTIFICATE-----\n",
    "client_key_pem": "-----BEGIN PRIVATE KEY-----\nBBB\n-----END PRIVATE KEY-----\n",
}


class Recorder:
    """Scripted provider: ``routes`` maps ``METHOD path`` to a handler or a list of handlers
    consumed in order (for retry scripts)."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = f"{request.method} {request.url.path}"
        route = self.routes.get(key)
        if route is None:
            return httpx.Response(404, json={"error": "no route"})
        step = route.pop(0) if isinstance(route, list) else route
        if isinstance(step, Exception):
            raise step
        if callable(step):
            response: httpx.Response = step(request)
            return response
        return step  # type: ignore[no-any-return]

    def attach(self, adapter: Any) -> Any:
        adapter.transport = httpx.MockTransport(self.handler)
        adapter.pin = lambda url: PinnedTarget(url=url)
        adapter.sleep = self.sleeps.append
        return adapter


def _token(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"].startswith("Basic ")
    user, password = base64.b64decode(request.headers["Authorization"][6:]).decode().split(":", 1)
    assert (user, password) == ("cid", CLIENT_SECRET)
    assert b"grant_type=client_credentials" in request.content
    return httpx.Response(200, json={"access_token": TOKEN, "expires_in": 300})


def _bearer(body: Any, status: int = 200) -> Callable[[httpx.Request], httpx.Response]:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert request.headers["Accept"] == "application/json"
        return httpx.Response(status, json=body)

    return handle


def _basic(body: Any, status: int = 200) -> Callable[[httpx.Request], httpx.Response]:
    def handle(request: httpx.Request) -> httpx.Response:
        expected = "Basic " + base64.b64encode(f"user:{BASIC_PASSWORD}".encode()).decode()
        assert request.headers["Authorization"] == expected
        return httpx.Response(status, json=body)

    return handle


# Registration and honest capability state ----------------------------------------------


def test_real_adapters_registered_and_documented_functions_only() -> None:
    ista = adapter_for("ista", {})
    kalo = adapter_for("kalo", {})
    assert isinstance(ista, IstaAdapter) and isinstance(kalo, KaloAdapter)  # noqa: PT018
    # write families from the bved zip files (on-site-roles 2.0.2, billing-input 1.0.3)
    assert Function.ROLES in ista.implemented and Function.BILLING_INPUT in ista.implemented  # noqa: PT018
    # KALO: billing unit data and billing result are not documented on Q3 -> not implemented
    assert kalo.implemented == {Function.CONSUMPTION, Function.DOCUMENTS}
    assert "26.09.2026" in ista.spec_version and "26.09.2026" in kalo.spec_version  # noqa: PT018
    # the fake adapter is never selected outside the test environment
    assert adapter_for("ista", {"adapter": "fake", "_environment": "production"}).code == "ista"


# Authentication per family (Q9) ------------------------------------------------------------


def test_ista_test_connection_uses_oauth2_and_basic_per_family_and_is_read_only() -> None:
    rec = Recorder(
        {
            "POST /oauth/token": _token,
            "GET /billingunitdata/v1/billingunits": _bearer(
                {"billingunits": [], "totalentries": 0}
            ),
            "GET /documents/out/count": _basic({"count": 3}),
            "GET /eedbillingunits/count": _basic({"count": 1}),
        }
    )
    adapter = rec.attach(IstaAdapter())
    result = adapter.test_connection(config=ISTA_CONFIG, secrets=ISTA_SECRETS, environment="test")
    assert result.outcome == "ok", result.detail
    assert set(result.functions_released) == {
        "billing_unit_data",
        "billing_result",
        "consumption",
        "documents",
        "roles",
        "billing_input",
    }
    assert "Objektzugriff" in result.detail
    assert all(r.method == "GET" for r in rec.requests if r.url.path != "/oauth/token")
    assert not any(r.url.path.startswith("/documents/in") for r in rec.requests)
    # the token is obtained once and reused (cache), never sent to the Basic families
    assert sum(1 for r in rec.requests if r.url.path == "/oauth/token") == 1
    assert CLIENT_SECRET not in result.detail and BASIC_PASSWORD not in result.detail  # noqa: PT018


def test_ista_mtls_material_required_in_test_only_and_removed_after_use(tmp_path: Any) -> None:
    rec = Recorder({})
    adapter = rec.attach(IstaAdapter())
    without = {k: v for k, v in ISTA_SECRETS.items() if not k.startswith("client_")}
    without.update({"client_id": "cid", "client_secret": CLIENT_SECRET})
    result = adapter.test_connection(config=ISTA_CONFIG, secrets=without, environment="test")
    assert result.outcome == "credentials_missing" and "mTLS" in result.detail  # noqa: PT018
    # production of the new bved APIs needs no certificate (Q9)
    prod = {**ISTA_CONFIG, "config_environment": "production"}
    rec.routes["POST /oauth/token"] = _token
    rec.routes["GET /billingunitdata/v1/billingunits"] = _bearer(
        {"billingunits": [], "totalentries": 0}
    )
    result = adapter.test_connection(config=prod, secrets=without, environment="production")
    assert result.outcome == "ok" and "billing_unit_data" in result.functions_released  # noqa: PT018


def test_expired_credentials_and_missing_release_are_distinguished() -> None:
    rec = Recorder(
        {
            "POST /oauth/token": httpx.Response(401, json={"error": "invalid_client"}),
            "GET /documents/out/count": _basic({"count": 0}, status=403),
            "GET /eedbillingunits/count": _basic({"count": 0}, status=401),
        }
    )
    adapter = rec.attach(IstaAdapter())
    result = adapter.test_connection(config=ISTA_CONFIG, secrets=ISTA_SECRETS, environment="test")
    assert result.outcome == "auth_failed"
    assert result.functions_released == ()
    assert "HTTP 401" in result.detail and "HTTP 403" in result.detail  # noqa: PT018
    assert CLIENT_SECRET not in result.detail and BASIC_PASSWORD not in result.detail  # noqa: PT018


# Environment separation (case 9) ------------------------------------------------------------


def test_configuration_never_runs_in_another_environment() -> None:
    rec = Recorder({"POST /oauth/token": _token})
    adapter = rec.attach(IstaAdapter())
    result = adapter.test_connection(
        config=ISTA_CONFIG, secrets=ISTA_SECRETS, environment="production"
    )
    assert result.outcome == "credentials_missing" and "config_environment" in result.detail  # noqa: PT018
    assert rec.requests == []
    fetch = adapter.fetch(
        function=Function.CONSUMPTION,
        config=ISTA_CONFIG,
        secrets=ISTA_SECRETS,
        environment="production",
        external_billing_units=["000123456"],
        period_from=None,
        period_to=None,
    )
    assert fetch.errors and rec.requests == []  # noqa: PT018


def test_kalo_production_urls_fixed_and_test_never_points_to_production() -> None:
    adapter = KaloAdapter()
    prod = {"config_environment": "production", "base_url": "https://evil.example.test"}
    family = adapter.families[Function.DOCUMENTS]
    assert adapter.base_url(prod, "production", family) == "https://api.kalo.de/arge/documents/v1"
    assert adapter.token_url(prod, "production").startswith("https://meine.kalo.de/")
    rec = Recorder({})
    rec.attach(adapter)
    test_cfg = {
        "config_environment": "test",
        "base_url": "https://api.kalo.de/arge",
        "token_url": "https://auth.example.test/token",
    }
    result = adapter.test_connection(config=test_cfg, secrets=ISTA_SECRETS, environment="test")
    assert result.outcome != "ok" and "Produktionssystem" in result.detail  # noqa: PT018
    assert rec.requests == []
    missing = adapter.test_connection(
        config={"config_environment": "test"}, secrets=ISTA_SECRETS, environment="test"
    )
    assert "Testsystem" in missing.detail


# KALO consumption (Q3, consumption-data 1.2.1) ---------------------------------------------


def test_kalo_consumption_fetch_keeps_actual_estimated_missing_and_converted_apart() -> None:
    period_body = {
        "billingunit": {
            "reference": {"mscnumber": "000123456", "pmnumber": "HVM-1"},
            "period": "2026-01",
            "residentialunits": [
                {
                    "reference": {"mscnumber": "0001"},
                    "consumptions": [
                        {
                            "service": "HEATING",
                            "unitofmeasure": "KWH",
                            "amount": 12.5,
                            "estimated": False,
                            "errors": False,
                            "converted": False,
                        },
                        {
                            "service": "HOT_WATER",
                            "unitofmeasure": "M3",
                            "amount": 3.25,
                            "estimated": True,
                            "errors": False,
                            "converted": False,
                        },
                        {
                            "service": "COLD_WATER",
                            "unitofmeasure": "M3",
                            "estimated": False,
                            "errors": True,
                            "converted": False,
                        },
                        {
                            "service": "HEATING",
                            "unitofmeasure": "KWH",
                            "amount": 99.03,
                            "estimated": False,
                            "errors": False,
                            "converted": True,
                        },
                    ],
                }
            ],
        }
    }
    rec = Recorder(
        {
            "POST /token": _token,
            "GET /consumptions/v1/billingunits/000123456/consumptions/periods": _bearer(
                {
                    "billingunit": {
                        "reference": {"mscnumber": "000123456"},
                        "periods": [
                            {"period": "2026-01", "update": "2026-02-01T00:00:00Z"},
                            {"period": "2025-12", "update": "2026-01-01T00:00:00Z"},
                        ],
                    }
                }
            ),
            "GET /consumptions/v1/billingunits/000123456/consumptions/periods/2026-01": _bearer(
                period_body
            ),
        }
    )
    adapter = rec.attach(KaloAdapter())
    cfg = {
        "config_environment": "test",
        "base_url": "https://kalo-test.example.test",
        "token_url": "https://kalo-test.example.test/token",
    }
    result = adapter.fetch(
        function=Function.CONSUMPTION,
        config=cfg,
        secrets={"client_id": "cid", "client_secret": CLIENT_SECRET},
        environment="test",
        external_billing_units=["000123456"],
        period_from=None,
        period_to=None,
    )
    assert result.errors == ()
    rows = {(r.kind, r.unit_of_measure): r for r in result.consumption}
    assert rows[("heating", "KWH")].value == Decimal("12.5")
    assert rows[("heating", "KWH")].value_kind == "actual"
    assert rows[("hot_water", "M3")].value_kind == "estimated"
    assert rows[("cold_water", "M3")].value is None
    assert rows[("cold_water", "M3")].value_kind == "missing"
    assert rows[("heating", "KWH_CONVERTED")].value == Decimal("99.03")
    assert all(
        r.period_from.isoformat() == "2026-01-01" and r.period_to.isoformat() == "2026-01-31"
        for r in result.consumption
    )
    # both listed periods are fetched (no filter); the 2025-12 detail answers 404 and
    # "no data" is not an error (section 10)
    assert any(r.url.path.endswith("/periods/2025-12") for r in rec.requests)


# Retries, backoff, pagination, partial results (case 10) -----------------------------------


def test_get_retries_with_backoff_and_partial_result_per_billing_unit() -> None:
    periods = _bearer({"periods": [{"from": "2025-01-01", "to": "2025-12-31"}]})
    rec = Recorder(
        {
            "POST /oauth/token": _token,
            "GET /billingresult/v1/billingunits/A/billingperiods": [
                httpx.Response(503, text="busy"),
                httpx.ReadTimeout("slow"),
                periods,
            ],
            "GET /billingresult/v1/billingunits/A/billingperiods/2025-12-31/billingresult": _bearer(
                {
                    "billingunitMscnumber": "A",
                    "billingdate": "2026-03-01",
                    "billingperiod": {"from": "2025-01-01", "to": "2025-12-31"},
                    "individualbillingresults": [
                        {
                            "residentialunitMscnumber": "0001",
                            "billingrecipient": {"name": "Muster", "partnerPmnumber": "P1"},
                            "usageperiod": {"from": "2025-01-01", "to": "2025-12-31"},
                            "billingbalances": [
                                {
                                    "costblock": "OVERALL",
                                    "totalcosts": {"amounts": {"grossamount": 1234.56}},
                                    "balances": {"amounts": {"grossamount": -12.34}},
                                }
                            ],
                        }
                    ],
                    "totalbillingresult": {},
                }
            ),
            "GET /billingresult/v1/billingunits/B/billingperiods": [
                httpx.Response(500),
                httpx.Response(500),
                httpx.Response(500),
            ],
        }
    )
    adapter = rec.attach(IstaAdapter())
    result = adapter.fetch(
        function=Function.BILLING_RESULT,
        config={**ISTA_CONFIG, "max_parallel": 1},
        secrets=ISTA_SECRETS,
        environment="test",
        external_billing_units=["A", "B"],
        period_from=None,
        period_to=None,
    )
    assert rec.sleeps == [0.5, 1.0, 0.5, 1.0]  # exponential backoff, retries bounded
    assert len(result.billing_results) == 1
    record = result.billing_results[0]
    assert record.amount == Decimal("1234.56") and record.currency == "EUR"  # noqa: PT018
    assert record.payload["balance"] == "-12.34"
    assert record.external_document_ref == "BR/A/2025-12-31/0001/OVERALL"
    assert len(result.errors) == 1 and result.errors[0].startswith("Abrechnungseinheit B")  # noqa: PT018
    assert not result.unclear


def test_billing_result_amount_with_three_decimals_is_a_payload_error_not_rounded() -> None:
    with pytest.raises(bved.BvedPayloadError):
        bved.parse_billing_result(
            {
                "billingunitMscnumber": "A",
                "billingperiod": {"from": "2025-01-01", "to": "2025-12-31"},
                "individualbillingresults": [
                    {
                        "billingbalances": [
                            {
                                "costblock": "OVERALL",
                                "totalcosts": {"amounts": {"grossamount": Decimal("1.005")}},
                            }
                        ]
                    }
                ],
            }
        )


def test_documents_pagination_follows_next_on_same_host_only_and_limit_is_capped() -> None:
    page1 = {
        "documents": [
            {
                "documentid": "D1",
                "filename": "a.pdf",
                "doctype": "HKA-G",
                "mimetype": "application/pdf",
                "hashvalue": "h1",
                "metadata": [
                    {
                        "reftype": "billingunit",
                        "mscnumber": "000123456",
                        "from": "2025-01-01",
                        "to": "2025-12-31",
                    }
                ],
                "propertymanagement": "PM",
            }
        ],
        "_links": {"next": {"href": "https://docs.example.test/documents/out?offset=1&limit=1"}},
    }
    page2 = {
        "documents": [
            {
                "documentid": "D2",
                "filename": "b.pdf",
                "doctype": "UVI-E",
                "propertymanagement": "PM",
                "metadata": [{"reftype": "resident", "mscnumber": "0991234560001"}],
            }
        ],
        "_links": {},
    }
    pages = [page1, page2]

    def list_docs(request: httpx.Request) -> httpx.Response:
        assert int(request.url.params.get("limit", 100)) <= 100
        return httpx.Response(200, json=pages.pop(0))

    rec = Recorder({"GET /documents/out": list_docs})
    adapter = rec.attach(IstaAdapter())
    result = adapter.fetch(
        function=Function.DOCUMENTS,
        config={**ISTA_CONFIG, "documents_auth": "basic"},
        secrets=ISTA_SECRETS,
        environment="test",
        external_billing_units=[],
        period_from=None,
        period_to=None,
    )
    assert [d.external_id for d in result.documents] == ["D1", "D2"]
    assert result.documents[0].external_billing_unit == "000123456"
    assert result.documents[0].version == "h1"
    assert result.documents[1].external_billing_unit is None  # resident reference: clearing
    # a foreign host in _links.next is refused (secrets never leave the configured host)
    rec2 = Recorder(
        {
            "GET /documents/out": httpx.Response(
                200,
                json={
                    **page1,
                    "_links": {"next": {"href": "https://evil.example.test/documents/out"}},
                },
            )
        }
    )
    adapter2 = rec2.attach(IstaAdapter())
    result2 = adapter2.fetch(
        function=Function.DOCUMENTS,
        config=ISTA_CONFIG,
        secrets=ISTA_SECRETS,
        environment="test",
        external_billing_units=[],
        period_from=None,
        period_to=None,
    )
    assert result2.errors and "fremden Host" in result2.errors[0]  # noqa: PT018
    assert all(r.url.host == "docs.example.test" for r in rec2.requests)


def test_document_download_and_receipt_are_separate_calls() -> None:
    rec = Recorder(
        {
            "GET /documents/out/D1/data": httpx.Response(
                200, content=b"%PDF-1.4 x", headers={"Content-Type": "application/pdf"}
            ),
            "PUT /documents/out/D1/status": lambda request: httpx.Response(
                200, json=json.loads(request.content)
            ),
        }
    )
    adapter = rec.attach(IstaAdapter())
    record = DocumentRecord(
        "D1", "a.pdf", "HKA-G", "application/pdf", "h1", None, "000123456", None, None, None
    )
    data = adapter.download_document(
        config=ISTA_CONFIG, secrets=ISTA_SECRETS, environment="test", document=record
    )
    assert data == b"%PDF-1.4 x"
    assert [r.method for r in rec.requests] == ["GET"]
    adapter.acknowledge_document(
        config=ISTA_CONFIG, secrets=ISTA_SECRETS, environment="test", document=record
    )
    assert json.loads(rec.requests[-1].content) == {
        "code": 200,
        "statustype": "ok",
        "message": "received and stored",
    }


# Billing unit data: asynchronous Ordnungsbegriffsabgleich (Q8) ---------------------------


def test_billing_unit_data_preview_status_and_result_with_cursor() -> None:
    rec = Recorder(
        {
            "POST /oauth/token": _token,
            "GET /billingunitdata/v1/billingunits": _bearer(
                {
                    "totalentries": 3,
                    "billingunits": [
                        {
                            "billingunitMscnumber": "000123456",
                            "customerMscnumber": "C1",
                            "setupstatus": "COMPLETED",
                            "lastupdate": "2026-09-01T00:00:00Z",
                            "address": {
                                "street": "Zählerweg 1",
                                "postalcode": "40789",
                                "city": "Monheim",
                            },
                        },
                        {
                            "billingunitMscnumber": "000123457",
                            "customerMscnumber": "C1",
                            "setupstatus": "IN_PROGRESS",
                            "lastupdate": "2026-09-02T00:00:00Z",
                        },
                        {
                            "billingunitMscnumber": "000999999",
                            "customerMscnumber": "C1",
                            "setupstatus": "OPEN",
                            "lastupdate": "2026-09-02T00:00:00Z",
                        },
                    ],
                }
            ),
            "GET /billingunitdata/v1/billingunits/setup/000123456": _bearer(
                {
                    "billingunitMscnumber": "000123456",
                    "matched": [
                        {"residentialunitMscnumber": "0001", "residentialunitPmnumber": "WE-1"}
                    ],
                    "additional": [
                        {"residentialunitMscnumber": "0002", "positiontext": "EG links"}
                    ],
                }
            ),
        }
    )
    adapter = rec.attach(IstaAdapter())
    result = adapter.fetch(
        function=Function.BILLING_UNIT_DATA,
        config=ISTA_CONFIG,
        secrets=ISTA_SECRETS,
        environment="test",
        external_billing_units=["000123456", "000123457"],
        period_from=None,
        period_to=None,
        cursor="2026-08-01T00:00:00+00:00",
    )
    listing = next(r for r in rec.requests if r.url.path == "/billingunitdata/v1/billingunits")
    assert listing.url.params["from"] == "2026-08-01T00:00:00+00:00"
    assert listing.url.params["limit"] == "100"
    assert result.waiting_provider is True and result.errors == ()  # noqa: PT018
    by_number = {u.external_number: u for u in result.billing_units}
    assert set(by_number) == {"000123456", "000123457"}  # out of scope unit is not returned
    done = by_number["000123456"]
    assert done.payload["setupstatus"] == "COMPLETED"
    assert done.address == "Zählerweg 1 40789 Monheim"
    assert [(u.external_unit_number, u.label) for u in done.units] == [("0001", "WE-1")]
    assert done.payload["additional"][0]["residentialunitMscnumber"] == "0002"
    assert by_number["000123457"].units == ()
    # the read path never posted anything (case 12)
    assert all(r.method == "GET" for r in rec.requests if r.url.path != "/oauth/token")


# Case 11: a write timeout is never blindly repeated ---------------------------------------


def test_setup_submission_timeout_is_unclear_and_sent_exactly_once() -> None:
    rec = Recorder(
        {
            "POST /oauth/token": _token,
            "POST /billingunitdata/v1/billingunits/setup/000123456": [
                httpx.ReadTimeout("gone"),
                httpx.Response(200, json={"transactionid": "T1"}),
            ],
        }
    )
    adapter = rec.attach(IstaAdapter())
    with pytest.raises(ProviderHttpError) as excinfo:
        adapter.submit_billing_unit_setup(
            config=ISTA_CONFIG,
            secrets=ISTA_SECRETS,
            environment="test",
            external_billing_unit="000123456",
            residential_units=[{"residentialunitPmnumber": "WE-1"}],
            customer_number="C1",
        )
    assert excinfo.value.unclear is True
    assert sum(1 for r in rec.requests if r.method == "POST" and "setup" in r.url.path) == 1
    assert rec.sleeps == []
    # a 5xx on a write is not retried either
    rec.routes["POST /billingunitdata/v1/billingunits/setup/000123456"] = [httpx.Response(502)]
    with pytest.raises(ProviderHttpError) as second:
        adapter.submit_billing_unit_setup(
            config=ISTA_CONFIG,
            secrets=ISTA_SECRETS,
            environment="test",
            external_billing_unit="000123456",
            residential_units=[],
            customer_number="C1",
        )
    assert second.value.unclear is False and "502" in second.value.message  # noqa: PT018
    assert sum(1 for r in rec.requests if r.method == "POST" and "setup" in r.url.path) == 2


def test_billing_input_validate_send_and_rejection_are_distinct_calls() -> None:
    """Section 12 / Q11: VALIDATE (204) stores nothing, SEND (200) returns the transaction id,
    a 400 carries the provider messages, a 409 means the input was already received."""
    period = "2025-12-31"
    path = f"/billinginput/v1/billingunits/000123456/billingperiods/{period}"
    rec = Recorder(
        {
            "POST /oauth/token": _token,
            f"GET {path}": _bearer(
                {
                    "currency": "EUR",
                    "expectedvat": "GROSS",
                    "energysources": [],
                    "billingrecipients": [],
                }
            ),
            f"POST {path}": [
                httpx.Response(204),
                httpx.Response(200, json={"transactionid": "BI-1"}),
                httpx.Response(
                    400,
                    json={
                        "messages": [
                            {
                                "type": "ERROR",
                                "message": "Kostenschlüssel fehlt",
                                "shortmessage": "E1",
                            },
                            {"type": "WARNING", "message": "Datum", "shortmessage": "W1"},
                        ]
                    },
                ),
                httpx.Response(409),
            ],
        }
    )
    adapter = rec.attach(IstaAdapter())
    template = adapter.fetch_billing_template(
        config=ISTA_CONFIG,
        secrets=ISTA_SECRETS,
        environment="test",
        external_billing_unit="000123456",
        period_to=date.fromisoformat(period),
    )
    assert template["currency"] == "EUR"
    body = {"currency": "EUR", "expectedvat": "GROSS"}
    common = {
        "config": ISTA_CONFIG,
        "secrets": ISTA_SECRETS,
        "environment": "test",
        "external_billing_unit": "000123456",
        "period_to": date.fromisoformat(period),
        "payload": body,
    }
    validated = adapter.send_billing_input(action="VALIDATE", **common)
    assert validated.outcome == "validated" and validated.transaction_id is None  # noqa: PT018
    sent = adapter.send_billing_input(action="SEND", **common)
    assert sent.outcome == "accepted" and sent.transaction_id == "BI-1"  # noqa: PT018
    rejected = adapter.send_billing_input(action="SEND", **common)
    assert rejected.outcome == "rejected"
    assert [m["type"] for m in rejected.messages] == ["error", "warning"]
    assert len(rejected.errors) == 1 and len(rejected.warnings) == 1  # noqa: PT018
    duplicate = adapter.send_billing_input(action="SEND", **common)
    assert duplicate.outcome == "rejected" and "409" in duplicate.messages[0]["message"]  # noqa: PT018
    posts = [r for r in rec.requests if r.method == "POST" and "billinginput" in r.url.path]
    assert [r.url.params["action"] for r in posts] == ["VALIDATE", "SEND", "SEND", "SEND"]
    assert all(r.headers["Authorization"] == f"Bearer {TOKEN}" for r in posts)
    with pytest.raises(ProviderHttpError):
        adapter.send_billing_input(action="DELETE_EVERYTHING", **common)


def test_roles_submission_timeout_is_unclear_and_sent_exactly_once() -> None:
    """Case 11 for On-Site Roles 2.0: one POST per residential unit, a timeout ends as
    ``unclear`` without any repetition, a 5xx is a failure that is not repeated either."""
    path = "/onsiteroles/v2/billingunits/000123456/residentialunits/0001/on-site-roles"
    rec = Recorder(
        {
            "POST /oauth/token": _token,
            f"POST {path}": [
                httpx.ReadTimeout("gone"),
                httpx.Response(200, json={"transactionid": "R-1"}),
                httpx.Response(502),
            ],
        }
    )
    adapter = rec.attach(IstaAdapter())
    common = {
        "config": ISTA_CONFIG,
        "secrets": ISTA_SECRETS,
        "environment": "test",
        "external_billing_unit": "000123456",
        "external_unit_number": "0001",
        "payload": {
            "billingunitMscnumber": "000123456",
            "residentialunitMscnumber": "0001",
            "partners": [],
        },
    }
    unclear = adapter.send_roles(**common)
    assert unclear.outcome == "unclear"
    assert sum(1 for r in rec.requests if r.method == "POST" and "on-site-roles" in r.url.path) == 1
    assert rec.sleeps == []
    accepted = adapter.send_roles(**common)
    assert accepted.outcome == "accepted" and accepted.transaction_id == "R-1"  # noqa: PT018
    with pytest.raises(ProviderHttpError) as excinfo:
        adapter.send_roles(**common)
    assert excinfo.value.unclear is False and "502" in excinfo.value.message  # noqa: PT018
    assert sum(1 for r in rec.requests if r.method == "POST" and "on-site-roles" in r.url.path) == 3
    # a configuration for the production environment never runs the test connection
    with pytest.raises(Exception, match="nicht für diese Umgebung"):
        adapter.send_roles(**{**common, "environment": "production"})


def test_write_sync_is_not_offered_by_the_service_layer() -> None:
    from mhvp.metering import routers, services

    assert Function.BILLING_UNIT_DATA in services.DATA_KIND_FUNCTION.values()
    from pathlib import Path

    assert "submit_billing_unit_setup" not in Path(routers.__file__).read_text(encoding="utf-8")


# Secrets never appear in errors (case 9) -------------------------------------------------


def test_sanitize_masks_authorization_headers_urls_and_token_fields() -> None:
    text = "Authorization: Bearer abc.def https://user:pw@host/x access_token=zzz client_secret: qq"
    cleaned = sanitize(text)
    assert "abc.def" not in cleaned and "user:pw" not in cleaned  # noqa: PT018
    assert "zzz" not in cleaned and "qq" not in cleaned  # noqa: PT018


def test_provider_http_pins_target_and_refuses_redirects_and_plain_http() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Host"] == "api.example.test"
        return httpx.Response(302, headers={"Location": "https://elsewhere.example.test/"})

    seen: list[str] = []

    def pin(url: str) -> PinnedTarget:
        seen.append(url)
        return PinnedTarget(
            url=url.replace("api.example.test", "192.0.2.10"),
            headers={"Host": "api.example.test"},
            extensions={"sni_hostname": "api.example.test"},
        )

    http = ProviderHttp(transport=httpx.MockTransport(handler), pin=pin, sleep=lambda _: None)
    with pytest.raises(ProviderHttpError, match="Weiterleitung"):
        http.request("GET", "https://api.example.test/x", auth=None)
    assert seen == ["https://api.example.test/x"]
    with pytest.raises(ProviderHttpError, match="Unzulässiges Ziel"):
        ProviderHttp(transport=httpx.MockTransport(handler), sleep=lambda _: None).request(
            "GET", "http://api.example.test/x", auth=None
        )
