"""In-process fake of the Lexware Office public API (docs/integrations/lexoffice.md), plugged
in via ``mhvp.integrations.lexoffice_async.TRANSPORT`` as an ``httpx.MockTransport``.

Contacts carry a ``version`` that increments on every PUT (409 when the sent version is
stale) and answer the legacy ``IssueList`` format on 406; the voucher list needs
``voucherType`` and ``voucherStatus`` (400 regular ``details[]`` otherwise) and filters
``voucherNumber`` as a substring, so the platform's exact post filter is observable.
``fail_next`` injects status codes (429 with ``Retry-After``, 401, 503, 504 with "processed
anyway" mode); ``requests`` logs method, path, time and body for assertions."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs

import httpx

BASE = "https://lexoffice.example.test"
PDF = b"%PDF-1.4\n%fake invoice\n%%EOF\n"
XML = b'<?xml version="1.0"?><Invoice>fake</Invoice>'


@dataclass
class FakeLexoffice:
    api_key: str = "key-" + uuid.uuid4().hex
    organization_id: str = "org-" + uuid.uuid4().hex[:8]
    company_name: str = "Testorganisation GmbH"
    business_features: list[str] = field(default_factory=lambda: ["INVOICING"])
    contacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    invoices: dict[str, dict[str, Any]] = field(default_factory=dict)
    requests: list[dict[str, Any]] = field(default_factory=list)
    fail_next: list[tuple[int, dict[str, str]]] = field(default_factory=list)
    process_on_504: bool = False
    # Number of PUTs answered with 409 after bumping the version (concurrent remote edit).
    conflict_puts: int = 0
    # (remote row before the PUT, sent body) for the forbidden field assertion.
    put_log: list[tuple[dict[str, Any], dict[str, Any]]] = field(default_factory=list)
    page_size: int = 250

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    # Helpers ------------------------------------------------------------------------------

    def add_contact(
        self,
        *,
        person: dict[str, Any] | None = None,
        company: dict[str, Any] | None = None,
        customer_number: int | None = 10001,
        vendor_number: int | None = None,
        billing: dict[str, Any] | None = None,
        emails: dict[str, list[str]] | None = None,
        phones: dict[str, list[str]] | None = None,
        archived: bool = False,
        **extra: Any,
    ) -> dict[str, Any]:
        contact_id = str(uuid.uuid4())
        roles: dict[str, Any] = {}
        if customer_number is not None:
            roles["customer"] = {"number": customer_number}
        if vendor_number is not None:
            roles["vendor"] = {"number": vendor_number}
        row: dict[str, Any] = {
            "id": contact_id,
            "organizationId": self.organization_id,
            "version": 7,
            "roles": roles,
            "addresses": {"billing": [billing] if billing else []},
            "emailAddresses": emails or {},
            "phoneNumbers": phones or {},
            "archived": archived,
            "createdDate": "2026-01-01T00:00:00.000+01:00",
            "updatedDate": "2026-09-01T00:00:00.000+02:00",
            **extra,
        }
        if person is not None:
            row["person"] = person
        if company is not None:
            row["company"] = company
        self.contacts[contact_id] = row
        return row

    def add_invoice(
        self,
        *,
        voucher_number: str,
        status: str = "open",
        contact_id: str | None = None,
        contact_name: str = "Hardy Harter",
        total_gross: str = "119.00",
        voucher_type: str = "invoice",
        xrechnung: bool = False,
    ) -> dict[str, Any]:
        invoice_id = str(uuid.uuid4())
        row: dict[str, Any] = {
            "id": invoice_id,
            "organizationId": self.organization_id,
            "version": 1,
            "voucherType": voucher_type,
            "voucherStatus": status,
            "voucherNumber": voucher_number,
            "voucherDate": "2026-09-15T00:00:00.000+02:00",
            "address": {"contactId": contact_id, "name": contact_name},
            "totalPrice": {"currency": "EUR", "totalGrossAmount": float(total_gross)},
            "contactId": contact_id,
            "contactName": contact_name,
            "totalAmount": float(total_gross),
        }
        if xrechnung:
            row["xRechnung"] = {"profile": "XRechnung"}
        self.invoices[invoice_id] = row
        return row

    def bodies(self, method: str, path_prefix: str = "") -> list[dict[str, Any]]:
        return [
            r["body"]
            for r in self.requests
            if r["method"] == method and r["path"].startswith(path_prefix) and r["body"] is not None
        ]

    def count(self, method: str, path_prefix: str = "") -> int:
        return len(
            [
                r
                for r in self.requests
                if r["method"] == method and r["path"].startswith(path_prefix)
            ]
        )

    # Handler ------------------------------------------------------------------------------

    def handle(self, request: httpx.Request) -> httpx.Response:
        body: Any = None
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError:
                body = None
        self.requests.append(
            {
                "method": request.method,
                "path": request.url.path,
                "query": dict(parse_qs(request.url.query.decode())),
                "at": time.monotonic(),
                "body": body,
                "accept": request.headers.get("Accept"),
            }
        )
        if request.headers.get("Authorization") != f"Bearer {self.api_key}":
            return httpx.Response(401, json={"message": "Unauthorized"})
        if self.fail_next:
            status, headers = self.fail_next.pop(0)
            if status == 504 and self.process_on_504 and request.method == "POST":
                self._process(request, body)
            return httpx.Response(status, headers=headers, json={"message": "injected"})
        path = request.url.path
        method = request.method
        if path == "/v1/profile":
            return httpx.Response(
                200,
                json={
                    "organizationId": self.organization_id,
                    "companyName": self.company_name,
                    "taxType": "net",
                    "smallBusiness": False,
                    "businessFeatures": self.business_features,
                },
            )
        if path == "/v1/contacts" and method == "GET":
            return self._list_contacts(request)
        if path == "/v1/contacts" and method == "POST":
            return self._create_contact(body)
        if path.startswith("/v1/contacts/"):
            contact_id = path.split("/")[3]
            row = self.contacts.get(contact_id)
            if row is None:
                return httpx.Response(404, json={"message": "not found", "traceId": "t-404"})
            if method == "GET":
                return httpx.Response(200, json=row)
            if method == "PUT":
                return self._update_contact(row, body)
        if path == "/v1/voucherlist":
            return self._voucherlist(request)
        if path == "/v1/invoices" and method == "POST":
            assert "finalize" not in request.url.params, "finalize must never be sent"
            return self._create_invoice(body)
        if path.startswith("/v1/invoices/"):
            parts = path.split("/")
            invoice = self.invoices.get(parts[3])
            if invoice is None:
                return httpx.Response(404, json={"message": "not found"})
            if len(parts) == 4:
                return httpx.Response(200, json=invoice)
            if parts[4] == "file":
                if invoice["voucherStatus"] == "draft":
                    return httpx.Response(409, json={"message": "draft"})
                accept = request.headers.get("Accept", "")
                if accept == "*/*" and invoice.get("xRechnung"):
                    return httpx.Response(
                        200,
                        content=XML,
                        headers={
                            "Content-Type": "application/xml",
                            "Content-Disposition": (
                                f'attachment; filename="{invoice["voucherNumber"]}.xml"'
                            ),
                        },
                    )
                return httpx.Response(
                    200,
                    content=PDF,
                    headers={
                        "Content-Type": "application/pdf",
                        "Content-Disposition": (
                            f'attachment; filename="Rechnung-{invoice["voucherNumber"]}.pdf"'
                        ),
                    },
                )
        return httpx.Response(404, json={"message": "unknown route"})

    def _process(self, request: httpx.Request, body: Any) -> None:
        if request.url.path == "/v1/contacts":
            self._create_contact(body)
        elif request.url.path == "/v1/invoices":
            self._create_invoice(body)

    def _list_contacts(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        rows = list(self.contacts.values())
        if params.get("customer") == "true":
            rows = [r for r in rows if "customer" in r["roles"]]
        if params.get("vendor") == "true":
            rows = [r for r in rows if "vendor" in r["roles"]]
        email = params.get("email")
        if email:
            rows = [
                r
                for r in rows
                if any(
                    email.lower() in v.lower() for vs in r["emailAddresses"].values() for v in vs
                )
            ]
        name = params.get("name")
        if name:
            needle = name.lower().replace("&amp;", "&")
            rows = [r for r in rows if needle in _name(r).lower()]
        page = int(params.get("page", "0"))
        size = min(int(params.get("size", "25")), self.page_size)
        total_pages = max(1, (len(rows) + size - 1) // size)
        chunk = rows[page * size : (page + 1) * size]
        return httpx.Response(
            200,
            json={
                "content": chunk,
                "totalPages": total_pages,
                "totalElements": len(rows),
                "last": page >= total_pages - 1,
                "first": page == 0,
                "number": page,
                "size": size,
            },
        )

    def _issues(self, body: Any) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        if not isinstance(body, dict):
            return [{"i18nKey": "invalid", "source": "body", "type": "validation_failure"}]
        if "company" in body and not (body["company"] or {}).get("name"):
            issues.append(
                {
                    "i18nKey": "missing_entity",
                    "source": "company.name",
                    "type": "validation_failure",
                }
            )
        if "person" in body and not (body["person"] or {}).get("lastName"):
            issues.append(
                {
                    "i18nKey": "missing_entity",
                    "source": "person.lastName",
                    "type": "validation_failure",
                }
            )
        for entry in (body.get("addresses") or {}).get("billing") or []:
            if not entry.get("countryCode"):
                issues.append(
                    {
                        "i18nKey": "missing_entity",
                        "source": "addresses.billing[0].countryCode",
                        "type": "validation_failure",
                    }
                )
        for parent in ("emailAddresses", "phoneNumbers"):
            for key, values in (body.get(parent) or {}).items():
                if isinstance(values, list) and len(values) > 1:
                    issues.append(
                        {
                            "i18nKey": "too_many",
                            "source": f"{parent}.{key}",
                            "type": "validation_failure",
                        }
                    )
        return issues

    def _create_contact(self, body: Any) -> httpx.Response:
        issues = self._issues(body)
        if issues:
            return httpx.Response(406, json={"IssueList": issues, "traceId": "t-406"})
        contact_id = str(uuid.uuid4())
        roles = {r: {"number": 20000 + len(self.contacts)} for r in (body.get("roles") or {})}
        row = {
            **body,
            "id": contact_id,
            "organizationId": self.organization_id,
            "version": 1,
            "roles": roles,
        }
        row.setdefault("archived", False)
        self.contacts[contact_id] = row
        return httpx.Response(
            201,
            json={
                "id": contact_id,
                "resourceUri": f"{BASE}/v1/contacts/{contact_id}",
                "createdDate": "2026-09-29T00:00:00.000+02:00",
                "updatedDate": "2026-09-29T00:00:00.000+02:00",
                "version": 1,
            },
        )

    def _update_contact(self, row: dict[str, Any], body: Any) -> httpx.Response:
        if self.conflict_puts > 0:
            self.conflict_puts -= 1
            row["version"] += 1
            return httpx.Response(409, json={"message": "version conflict", "traceId": "t-409"})
        if not isinstance(body, dict) or body.get("version") != row["version"]:
            return httpx.Response(409, json={"message": "version conflict", "traceId": "t-409"})
        issues = self._issues(body)
        if issues:
            return httpx.Response(406, json={"IssueList": issues, "traceId": "t-406"})
        self.put_log.append((json.loads(json.dumps(row)), body))
        keep = {k: row[k] for k in ("id", "organizationId", "createdDate", "archived", "roles")}
        row.clear()
        row.update(body)
        row.update(keep)
        row["version"] = body["version"] + 1
        row["updatedDate"] = "2026-09-29T10:00:00.000+02:00"
        return httpx.Response(
            200,
            json={
                "id": row["id"],
                "resourceUri": f"{BASE}/v1/contacts/{row['id']}",
                "version": row["version"],
            },
        )

    def _voucherlist(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        details = []
        if not params.get("voucherType"):
            details.append(
                {"violation": "NOTNULL", "field": "voucherType", "message": "must not be null"}
            )
        if not params.get("voucherStatus"):
            details.append(
                {"violation": "NOTNULL", "field": "voucherStatus", "message": "must not be null"}
            )
        if "updatedAtFrom" in params:
            details.append({"violation": "UNKNOWN", "field": "updatedAtFrom", "message": "unknown"})
        if details:
            return httpx.Response(400, json={"status": 400, "details": details, "traceId": "t-400"})
        types = set(params["voucherType"].split(","))
        status = params["voucherStatus"]
        rows = [r for r in self.invoices.values() if r["voucherType"] in types]
        if status != "any":
            rows = [r for r in rows if r["voucherStatus"] in status.split(",")]
        number = params.get("voucherNumber")
        if number:
            rows = [r for r in rows if number in r["voucherNumber"]]
        contact_id = params.get("contactId")
        if contact_id:
            rows = [r for r in rows if r.get("contactId") == contact_id]
        content = [
            {
                "id": r["id"],
                "voucherType": r["voucherType"],
                "voucherStatus": r["voucherStatus"],
                "voucherNumber": r["voucherNumber"],
                "voucherDate": r["voucherDate"],
                "contactId": r.get("contactId"),
                "contactName": r.get("contactName"),
                "totalAmount": r["totalAmount"],
                "currency": "EUR",
            }
            for r in rows
        ]
        return httpx.Response(200, json={"content": content, "totalPages": 1, "last": True})

    def _create_invoice(self, body: Any) -> httpx.Response:
        if not isinstance(body, dict) or not body.get("lineItems"):
            return httpx.Response(
                406,
                json={
                    "status": 406,
                    "details": [
                        {
                            "violation": "NOTNULL",
                            "field": "lineItems",
                            "message": "must not be empty",
                        }
                    ],
                    "traceId": "t-406",
                },
            )
        invoice_id = str(uuid.uuid4())
        total = 0.0
        for item in body["lineItems"]:
            price = item["unitPrice"]
            amount = price.get("grossAmount", price.get("netAmount", 0)) * item["quantity"]
            if "netAmount" in price:
                amount *= 1 + price["taxRatePercentage"] / 100
            total += amount
        self.invoices[invoice_id] = {
            "id": invoice_id,
            "organizationId": self.organization_id,
            "version": 1,
            "voucherType": "invoice",
            "voucherStatus": "draft",
            "voucherNumber": "",
            "voucherDate": body["voucherDate"],
            "address": body["address"],
            "contactId": body["address"].get("contactId"),
            "contactName": body["address"].get("name"),
            "totalAmount": round(total, 2),
            "totalPrice": {"currency": "EUR", "totalGrossAmount": round(total, 2)},
        }
        return httpx.Response(
            201,
            json={
                "id": invoice_id,
                "resourceUri": f"{BASE}/v1/invoices/{invoice_id}",
                "createdDate": "2026-09-29T00:00:00.000+02:00",
                "updatedDate": "2026-09-29T00:00:00.000+02:00",
                "version": 1,
            },
        )


def _name(row: dict[str, Any]) -> str:
    if row.get("company"):
        return str(row["company"].get("name") or "")
    person = row.get("person") or {}
    return " ".join(p for p in (person.get("firstName"), person.get("lastName")) if p)
