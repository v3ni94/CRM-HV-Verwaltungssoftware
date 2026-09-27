"""Parsers and call sequences for the bved / ARGE web service families, written from the
OpenAPI files published by the bved (Q6, Q7; copies checked on 26.09.2026):

* ``bved-billing-unit-data-1-0.openapi.yaml`` 1.0.2 (Q6, Q8): ``GET /billingunitdata/v1/
  billingunits`` (``from``, ``status``, ``offset``, ``limit``), ``GET/POST /billingunitdata/v1/
  billingunits/setup/{billingunit}``; OAuth 2 client credentials.
* ``bved-billing-result-1-0.openapi.yaml`` 1.0.3 (Q6): ``GET /billingresult/v1/billingunits/
  {billingunit}/billingperiods`` and ``.../billingperiods/{to}/billingresult``; OAuth 2.
* ``arge-spec-consumption-data-1_2_1.yaml`` 1.2.1 (Q7, Q3): ``GET /billingunits/{billingunit}/
  consumptions/periods[/{period}]``; Basic or OAuth 2.
* ``bved-billing-input-1-0.openapi.yaml`` 1.0.3 (Q6, Q11; zip checked 27.09.2026): ``GET
  /billinginput/v1/billingunits/{billingunit}/billingperiods[/{to}]`` (periods, template) and
  ``POST .../billingperiods/{to}?action=VALIDATE|SEND|SEND_AND_IGNORE_WARNINGS`` (200 with
  ``transactionid`` for SEND, 204 for VALIDATE, 400 with ``Validation.messages``, 409 when
  input was already received); OAuth 2.
* ``bved-on-site-roles-2-0.openapi.yaml`` 2.0.2 (Q6, Q10; zip checked 27.09.2026): ``POST
  /onsiteroles/v2/billingunits/{billingunit}/residentialunits/{unit}/on-site-roles`` with the
  complete data set of the unit (200 ``transactionid``, 400 ``ValidationResponse``); OAuth 2.
* ``bved-documents-1-3.openapi.yaml`` 1.3 (Q7, Q3): ``GET /documents/out`` (``offset``,
  ``limit``, ``_links.next``), ``GET /documents/out/{id}/data``, ``PUT /documents/out/{id}/
  status``; Basic or OAuth 2.

Base URLs and token URLs are provider and customer specific ("The actual URLs are provided by
each MSC") and come from the connection configuration; nothing here invents a host. Values
are taken as delivered: a missing consumption stays ``missing`` (never zero), amounts are
``Decimal`` from the JSON text, units of measure are kept as documented enumerations.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from mhvp.metering.adapters import (
    BillingResultRecord,
    ConsumptionRecord,
    DocumentRecord,
    ExternalBillingUnitData,
    ExternalUnitData,
    WriteResult,
)
from mhvp.metering.http import (
    MAX_PAGE_LIMIT,
    Auth,
    ProviderHttp,
    ProviderHttpError,
    join,
    same_host,
)

__all__ = [
    "BvedPayloadError",
    "acknowledge_document",
    "billing_input_template",
    "billing_periods",
    "billing_result",
    "consumption_data",
    "consumption_periods",
    "decimal",
    "download_document",
    "join",
    "list_billing_units",
    "list_documents",
    "month_period",
    "paginate",
    "parse_billing_result",
    "parse_billing_unit",
    "parse_consumption",
    "parse_document",
    "run_bounded",
    "send_billing_input",
    "send_on_site_roles",
    "setup_result",
    "submit_setup",
]

MAX_PAGES = 200  # hard stop against endless ``_links.next`` loops

# bved consumption-data 1.2.1 ``Service`` enumeration to the module's consumption kinds.
SERVICE_KINDS: dict[str, str] = {
    "HEATING": "heating",
    "HOT_WATER": "hot_water",
    "COLD_WATER": "cold_water",
    "WASTE_WATER": "waste_water",
    "COOLING": "cooling",
    "ELECTRICITY": "electricity",
    "GAS": "gas",
}


class BvedPayloadError(ValueError):
    """The provider answer does not match the specification; the record goes to clearing."""


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date(value: Any) -> date | None:
    text = _str(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise BvedPayloadError(f"Ungültiges Datum: {text!r}") from exc


def _datetime(value: Any) -> datetime | None:
    text = _str(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BvedPayloadError(f"Ungültiger Zeitstempel: {text!r}") from exc


def decimal(value: Any) -> Decimal | None:
    """Exact decimal from the JSON text (``parse_float=Decimal`` upstream). ``None`` stays
    ``None``; a non numeric value is a payload error, never a silent zero."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise BvedPayloadError("Boolescher Wert statt Zahl.")
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise BvedPayloadError(f"Ungültige Zahl: {value!r}") from exc


def month_period(period: str) -> tuple[date, date]:
    """``YYYY-MM`` (consumption-data ``period``) to first and last day of the month."""
    try:
        year, month = (int(part) for part in period.split("-", 1))
        last = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last)
    except (ValueError, IndexError) as exc:
        raise BvedPayloadError(f"Ungültige Periode: {period!r}") from exc


def paginate(
    http: ProviderHttp,
    url: str,
    *,
    auth: Auth,
    params: Mapping[str, Any],
    items_key: str,
    total_key: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Offset/limit pagination (limit at most 100, Q8). A ``_links.next`` href (documents 1.3)
    is followed only on the configured host, otherwise offset arithmetic is used."""
    offset = int(params.get("offset", 0))
    limit = min(int(params.get("limit", MAX_PAGE_LIMIT)), MAX_PAGE_LIMIT)
    next_url: str | None = url
    query: dict[str, Any] | None = {**params, "offset": offset, "limit": limit}
    for _ in range(MAX_PAGES):
        if next_url is None:
            return
        body = http.get_json(next_url, auth=auth, params=query)
        if body is None:
            return
        if not isinstance(body, dict):
            raise BvedPayloadError("Listenantwort ist kein Objekt.")
        items = body.get(items_key) or []
        if not isinstance(items, list):
            raise BvedPayloadError(f"Feld {items_key!r} ist keine Liste.")
        yield from (item for item in items if isinstance(item, dict))
        if not items:
            return
        links = body.get("_links") if isinstance(body.get("_links"), dict) else {}
        href = (links.get("next") or {}).get("href") if isinstance(links, dict) else None
        if isinstance(href, str) and href:
            if not same_host(url, href):
                raise ProviderHttpError("Verweis auf fremden Host wird nicht gefolgt.")
            next_url, query = href, None
            continue
        offset += len(items)
        total = body.get(total_key) if total_key else None
        if (isinstance(total, int) and offset >= total) or len(items) < limit:
            return
        next_url, query = url, {**params, "offset": offset, "limit": limit}
    raise ProviderHttpError("Seitenlimit erreicht; Abruf abgebrochen.")


# Billing unit data 1.0.2 ------------------------------------------------------------------


def list_billing_units(
    http: ProviderHttp, base_url: str, *, auth: Auth, since: str | None
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": MAX_PAGE_LIMIT}
    if since:
        params["from"] = since
    return list(
        paginate(
            http,
            join(base_url, "/billingunitdata/v1/billingunits"),
            auth=auth,
            params=params,
            items_key="billingunits",
            total_key="totalentries",
        )
    )


def setup_result(
    http: ProviderHttp, base_url: str, *, auth: Auth, billing_unit: str
) -> dict[str, Any] | None:
    body = http.get_json(
        join(base_url, f"/billingunitdata/v1/billingunits/setup/{billing_unit}"), auth=auth
    )
    return body if isinstance(body, dict) else None


def parse_billing_unit(
    entry: Mapping[str, Any], result: Mapping[str, Any] | None
) -> ExternalBillingUnitData:
    number = _str(entry.get("billingunitMscnumber"))
    if number is None:
        raise BvedPayloadError("billingunitMscnumber fehlt.")
    raw_address = entry.get("address")
    address: dict[str, Any] = raw_address if isinstance(raw_address, dict) else {}
    address_text = " ".join(
        part
        for part in (address.get("street"), address.get("postalcode"), address.get("city"))
        if part
    )
    units = tuple(
        ExternalUnitData(
            external_unit_number=str(m["residentialunitMscnumber"]),
            label=_str(m.get("residentialunitPmnumber")),
            payload=dict(m),
        )
        for m in (result or {}).get("matched") or []
        if isinstance(m, dict) and _str(m.get("residentialunitMscnumber"))
    )
    return ExternalBillingUnitData(
        external_number=number,
        name=_str(entry.get("billingunitPmnumber")),
        address=address_text or None,
        units=units,
        payload={
            "setupstatus": _str(entry.get("setupstatus")),
            "lastupdate": _str(entry.get("lastupdate")),
            "customerMscnumber": _str(entry.get("customerMscnumber")),
            "billingunitPmnumber": _str(entry.get("billingunitPmnumber")),
            "additional": list((result or {}).get("additional") or []),
            "matched": list((result or {}).get("matched") or []),
        },
    )


def submit_setup(
    http: ProviderHttp,
    base_url: str,
    *,
    auth: Auth,
    billing_unit: str,
    customer_number: str,
    residential_units: Sequence[Mapping[str, Any]],
    pm_number: str | None,
) -> WriteResult:
    """``POST /billingunitdata/v1/billingunits/setup/{billingunit}`` (write, ``sendSetup``).
    ``ProviderHttp`` sends it exactly once; a timeout surfaces as ``unclear``. 200 with
    ``transactionid`` means accepted for processing (asynchronous, Q8), 400 carries the
    ``ValidationResponse`` messages."""
    body: dict[str, Any] = {
        "billingunitMscnumber": billing_unit,
        "customerMscnumber": customer_number,
        "residentialunits": [dict(u) for u in residential_units],
    }
    if pm_number:
        body["billingunitPmnumber"] = pm_number
    response = http.request(
        "POST",
        join(base_url, f"/billingunitdata/v1/billingunits/setup/{billing_unit}"),
        auth=auth,
        json=body,
    )
    return _write_result(response)


# Billing input 1.0.3 and on-site roles 2.0.2 (write, section 12) ---------------------------

WRITE_ACTIONS: tuple[str, ...] = ("VALIDATE", "SEND", "SEND_AND_IGNORE_WARNINGS")


def _messages(body: Any) -> tuple[dict[str, Any], ...]:
    """``Validation.messages`` / ``ValidationResponse.messages`` as plain dictionaries."""
    if not isinstance(body, Mapping):
        return ()
    items = body.get("messages")
    if not isinstance(items, list):
        return ()
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, Mapping):
            out.append(
                {
                    "type": str(item.get("type", "error")).lower(),
                    "message": str(item.get("message", "")),
                    "shortmessage": str(item.get("shortmessage", "")),
                }
            )
    return tuple(out)


def billing_input_template(
    http: ProviderHttp, base_url: str, *, auth: Auth, billing_unit: str, period_to: date
) -> dict[str, Any]:
    """``GET /billinginput/v1/billingunits/{billingunit}/billingperiods/{to}`` (read only)."""
    body = http.get_json(
        join(base_url, f"/billinginput/v1/billingunits/{billing_unit}/billingperiods/{period_to}"),
        auth=auth,
    )
    if not isinstance(body, Mapping):
        raise BvedPayloadError("Abrechnungsvorlage ist kein Objekt.")
    return dict(body)


def _write_result(response: Any) -> WriteResult:
    from mhvp.metering.adapters import WriteOutcome

    if response.status_code == 204:
        return WriteResult(
            WriteOutcome.VALIDATED, detail="Beim Anbieter geprüft, nichts gespeichert."
        )
    if response.status_code == 200:
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderHttpError("Antwort ist kein JSON.") from exc
        transaction = body.get("transactionid") if isinstance(body, Mapping) else None
        if not transaction:
            raise ProviderHttpError("Antwort ohne transactionid.")
        return WriteResult(
            WriteOutcome.ACCEPTED,
            transaction_id=str(transaction),
            messages=_messages(body),
            detail="Vom Anbieter angenommen.",
            raw={"transactionid": str(transaction)},
        )
    if response.status_code == 400:
        try:
            body = response.json()
        except ValueError:
            body = {}
        messages = _messages(body) or (
            {"type": "error", "message": "Abgewiesen (HTTP 400).", "shortmessage": ""},
        )
        return WriteResult(
            WriteOutcome.REJECTED, messages=messages, detail="Vom Anbieter abgewiesen."
        )
    if response.status_code == 409:
        return WriteResult(
            WriteOutcome.REJECTED,
            messages=(
                {
                    "type": "error",
                    "message": "Abrechnungsdaten für diesen Zeitraum wurden beim Anbieter "
                    "bereits angenommen (HTTP 409).",
                    "shortmessage": "ALREADY_RECEIVED",
                },
            ),
            detail="Bereits angenommen.",
        )
    raise ProviderHttpError(
        f"Übermittlung abgewiesen (HTTP {response.status_code}).", status=response.status_code
    )


def send_billing_input(
    http: ProviderHttp,
    base_url: str,
    *,
    auth: Auth,
    billing_unit: str,
    period_to: date,
    payload: Mapping[str, Any],
    action: str,
) -> WriteResult:
    """``POST /billinginput/v1/billingunits/{billingunit}/billingperiods/{to}?action=`` sent
    exactly once by ``ProviderHttp``; a timeout surfaces as ``unclear`` (case 11)."""
    from mhvp.metering.adapters import WriteOutcome

    if action not in WRITE_ACTIONS:
        raise ProviderHttpError(f"Unbekannte Aktion {action!r}.")
    try:
        response = http.request(
            "POST",
            join(
                base_url, f"/billinginput/v1/billingunits/{billing_unit}/billingperiods/{period_to}"
            ),
            auth=auth,
            params={"action": action},
            json=dict(payload),
        )
    except ProviderHttpError as exc:
        if exc.unclear:
            return WriteResult(WriteOutcome.UNCLEAR, detail=exc.message)
        raise
    return _write_result(response)


def send_on_site_roles(
    http: ProviderHttp,
    base_url: str,
    *,
    auth: Auth,
    billing_unit: str,
    residential_unit: str,
    payload: Mapping[str, Any],
) -> WriteResult:
    """``POST /onsiteroles/v2/billingunits/{billingunit}/residentialunits/{unit}/on-site-roles``
    with the complete data set of the unit; sent exactly once (case 11)."""
    from mhvp.metering.adapters import WriteOutcome

    try:
        response = http.request(
            "POST",
            join(
                base_url,
                f"/onsiteroles/v2/billingunits/{billing_unit}/residentialunits/{residential_unit}"
                "/on-site-roles",
            ),
            auth=auth,
            json=dict(payload),
        )
    except ProviderHttpError as exc:
        if exc.unclear:
            return WriteResult(WriteOutcome.UNCLEAR, detail=exc.message)
        raise
    return _write_result(response)


# Consumption data 1.2.1 -------------------------------------------------------------------


def consumption_periods(
    http: ProviderHttp, base_url: str, *, auth: Auth, billing_unit: str, year: int | None
) -> list[str]:
    params = {"year": year} if year else None
    body = http.get_json(
        join(base_url, f"/billingunits/{billing_unit}/consumptions/periods"),
        auth=auth,
        params=params,
    )
    if body is None:
        return []
    periods = ((body.get("billingunit") or {}).get("periods")) if isinstance(body, dict) else None
    if not isinstance(periods, list):
        raise BvedPayloadError("Periodenliste fehlt.")
    return [str(p["period"]) for p in periods if isinstance(p, dict) and p.get("period")]


def consumption_data(
    http: ProviderHttp, base_url: str, *, auth: Auth, billing_unit: str, period: str
) -> dict[str, Any] | None:
    body = http.get_json(
        join(base_url, f"/billingunits/{billing_unit}/consumptions/periods/{period}"), auth=auth
    )
    return body if isinstance(body, dict) else None


def parse_consumption(body: Mapping[str, Any]) -> list[ConsumptionRecord]:
    unit_block = body.get("billingunit")
    if not isinstance(unit_block, dict):
        raise BvedPayloadError("billingunit fehlt.")
    number = _str((unit_block.get("reference") or {}).get("mscnumber"))
    period = _str(unit_block.get("period"))
    if number is None or period is None:
        raise BvedPayloadError("mscnumber oder period fehlt.")
    period_from, period_to = month_period(period)
    records: list[ConsumptionRecord] = []
    for unit in unit_block.get("residentialunits") or []:
        if not isinstance(unit, dict):
            continue
        unit_number = _str((unit.get("reference") or {}).get("mscnumber"))
        for c in unit.get("consumptions") or []:
            if not isinstance(c, dict):
                continue
            service = _str(c.get("service"))
            if service is None:
                raise BvedPayloadError("service fehlt.")
            uom = _str(c.get("unitofmeasure")) or "UNKNOWN"
            if c.get("converted") is True:
                uom = f"{uom}_CONVERTED"  # converted kWh are not measured kWh (spec note)
            errors = c.get("errors") is True
            amount = None if errors else decimal(c.get("amount"))
            value_kind = (
                "missing" if amount is None else ("estimated" if c.get("estimated") else "actual")
            )
            records.append(
                ConsumptionRecord(
                    external_billing_unit=number,
                    external_unit_number=unit_number,
                    period_from=period_from,
                    period_to=period_to,
                    kind=SERVICE_KINDS.get(service, service.lower()),
                    unit_of_measure=uom,
                    reading_type="period_consumption",
                    value=amount,
                    value_kind=value_kind,
                    external_ref=f"{number}/{period}/{unit_number or '-'}/{service}",
                )
            )
    return records


# Billing result 1.0.3 ---------------------------------------------------------------------


def billing_periods(
    http: ProviderHttp, base_url: str, *, auth: Auth, billing_unit: str
) -> list[dict[str, Any]]:
    body = http.get_json(
        join(base_url, f"/billingresult/v1/billingunits/{billing_unit}/billingperiods"), auth=auth
    )
    if body is None:
        return []
    periods = body.get("periods") if isinstance(body, dict) else None
    return [p for p in (periods or []) if isinstance(p, dict)]


def billing_result(
    http: ProviderHttp, base_url: str, *, auth: Auth, billing_unit: str, period_to: str
) -> dict[str, Any] | None:
    body = http.get_json(
        join(
            base_url,
            f"/billingresult/v1/billingunits/{billing_unit}/billingperiods/{period_to}/billingresult",
        ),
        auth=auth,
    )
    return body if isinstance(body, dict) else None


def _amount(block: Any) -> Decimal | None:
    if not isinstance(block, dict):
        return None
    amounts = block.get("amounts")
    if not isinstance(amounts, dict):
        return None
    value = decimal(amounts.get("grossamount"))
    if value is None:
        return None
    if value != value.quantize(Decimal("0.01")):
        raise BvedPayloadError(f"Betrag mit mehr als zwei Nachkommastellen: {value}")
    return value


def parse_billing_result(
    body: Mapping[str, Any], *, currency: str = "EUR"
) -> list[BillingResultRecord]:
    """One reviewable record per billing recipient and cost block (total costs, balance,
    budget payments in the payload). The bved amounts carry no currency field; the
    connection's documented contract currency is used (default EUR)."""
    number = _str(body.get("billingunitMscnumber"))
    period = body.get("billingperiod") if isinstance(body.get("billingperiod"), dict) else None
    if number is None or period is None:
        raise BvedPayloadError("billingunitMscnumber oder billingperiod fehlt.")
    period_from, period_to = _date(period.get("from")), _date(period.get("to"))
    if period_from is None or period_to is None:
        raise BvedPayloadError("Abrechnungszeitraum unvollständig.")
    updated = _str(period.get("updated"))
    records: list[BillingResultRecord] = []
    for individual in body.get("individualbillingresults") or []:
        if not isinstance(individual, dict):
            continue
        unit_number = _str(individual.get("residentialunitMscnumber"))
        recipient = individual.get("billingrecipient") or {}
        for balance in individual.get("billingbalances") or []:
            if not isinstance(balance, dict):
                continue
            cost_block = _str(balance.get("costblock")) or "OVERALL"
            total = _amount(balance.get("totalcosts"))
            if total is None:
                raise BvedPayloadError("totalcosts.amounts.grossamount fehlt.")
            records.append(
                BillingResultRecord(
                    external_billing_unit=number,
                    external_unit_number=unit_number,
                    period_from=period_from,
                    period_to=period_to,
                    amount=total,
                    currency=currency,
                    external_document_ref=(
                        f"BR/{number}/{period_to.isoformat()}/{unit_number or '-'}/{cost_block}"
                    ),
                    payload={
                        "costblock": cost_block,
                        "totalcosts": str(total),
                        "balance": _text(_amount(balance.get("balances"))),
                        "budgetpayments": _text(_amount(balance.get("budgetpayments"))),
                        "riskallocation": _text(_amount(balance.get("riskallocation"))),
                        "billingdate": _str(body.get("billingdate")),
                        "billingperiod_updated": updated,
                        "billingrecipient": dict(recipient) if isinstance(recipient, dict) else {},
                        "usageperiod": dict(individual.get("usageperiod") or {}),
                        "newbudgetpayments": list(individual.get("newbudgetpayments") or []),
                        "billingdocuments": list(individual.get("billingdocuments") or []),
                        "consumptions": list(individual.get("consumptions") or []),
                    },
                )
            )
    return records


def _text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


# Documents 1.3 ----------------------------------------------------------------------------


def list_documents(http: ProviderHttp, base_url: str, *, auth: Auth) -> list[DocumentRecord]:
    records = []
    for item in paginate(
        http,
        join(base_url, "/documents/out"),
        auth=auth,
        params={"limit": MAX_PAGE_LIMIT},
        items_key="documents",
    ):
        records.append(parse_document(item))
    return records


def parse_document(item: Mapping[str, Any]) -> DocumentRecord:
    external_id = _str(item.get("documentid"))
    filename = _str(item.get("filename"))
    if external_id is None or filename is None:
        raise BvedPayloadError("documentid oder filename fehlt.")
    billing_unit: str | None = None
    unit_number: str | None = None
    period_from: date | None = None
    period_to: date | None = None
    references = [r for r in (item.get("metadata") or []) if isinstance(r, dict)]
    for ref in references:
        reftype = _str(ref.get("reftype"))
        msc = _str(ref.get("mscnumber"))
        if reftype == "billingunit" and msc:
            billing_unit = billing_unit or msc
        elif reftype == "residentialunit" and msc:
            unit_number = unit_number or msc
        if ref.get("from") and period_from is None:
            period_from = _date(ref.get("from"))
        if ref.get("to") and period_to is None:
            period_to = _date(ref.get("to"))
    version = _str(item.get("hashvalue")) or _str(item.get("doctypeversion"))
    return DocumentRecord(
        external_id=external_id,
        filename=filename,
        doctype=_str(item.get("doctype")) or "OTHER",
        mime_type=_str(item.get("mimetype")),
        version=version,
        file_date=_datetime(item.get("filedate")),
        external_billing_unit=billing_unit,
        external_unit_number=unit_number,
        period_from=period_from,
        period_to=period_to,
        payload={
            "doctypedetail": _str(item.get("doctypedetail")),
            "filesize": item.get("filesize"),
            "propertymanagement": _str(item.get("propertymanagement")),
            "metadata": references,
        },
    )


def download_document(http: ProviderHttp, base_url: str, *, auth: Auth, external_id: str) -> bytes:
    response = http.request(
        "GET", join(base_url, f"/documents/out/{external_id}/data"), auth=auth, accept="*/*"
    )
    if response.status_code != 200:
        raise ProviderHttpError(
            f"Download abgewiesen (HTTP {response.status_code}).", status=response.status_code
        )
    return bytes(response.content)


def acknowledge_document(
    http: ProviderHttp, base_url: str, *, auth: Auth, external_id: str
) -> None:
    """``PUT /documents/out/{id}/status`` with ``statustype=ok`` (documents 1.3). A write: sent
    once; a timeout is reported as unclear and the receipt is retried by a later job only
    after the local state confirms the stored document."""
    response = http.request(
        "PUT",
        join(base_url, f"/documents/out/{external_id}/status"),
        auth=auth,
        json={"code": 200, "statustype": "ok", "message": "received and stored"},
    )
    if response.status_code != 200:
        raise ProviderHttpError(
            f"Quittung abgewiesen (HTTP {response.status_code}).", status=response.status_code
        )


def run_bounded(
    tasks: Sequence[Callable[[], Any]], *, max_parallel: int
) -> list[tuple[Any | None, str | None]]:
    """Runs independent read calls with bounded parallelism (section 10). Each result is
    ``(value, error)``; an error never aborts the other parts."""
    from concurrent.futures import ThreadPoolExecutor

    def _one(task: Callable[[], Any]) -> tuple[Any | None, str | None]:
        try:
            return task(), None
        except (ProviderHttpError, BvedPayloadError) as exc:
            return None, str(exc)

    workers = max(1, min(int(max_parallel), 4))
    if workers == 1 or len(tasks) <= 1:
        return [_one(t) for t in tasks]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_one, tasks))
