"""Pure payload builders for Lexware Office (rule INT-LEXO-01, section 3.1 and 8 of the
implementation spec). Only fields confirmed in the vendor documentation (verified 28.09.2026)
are produced; bank data, tax numbers, notes and roles are never built here, and a merge that
would change such a field raises :class:`ForbiddenFieldError` (MHVP-LEXO-0007).
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from mhvp.core.money import json_number, round_to

BERLIN = ZoneInfo("Europe/Berlin")
COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
FORBIDDEN_KEY_RE = re.compile(
    r"iban|bic|bank|mandate|taxNumber|vatRegistrationId|allowTaxFreeInvoices", re.IGNORECASE
)
READ_ONLY_KEYS = ("id", "organizationId", "createdDate", "updatedDate", "archived")
MANAGED_FIELDS = frozenset({"name", "address", "email", "phone"})
EMAIL_LISTS = ("business", "office", "private", "other")
PHONE_LISTS = ("business", "office", "mobile", "private", "fax", "other")
MULTI_ENTRY_LISTS = (
    ("addresses", "billing"),
    ("addresses", "shipping"),
    ("company", "contactPersons"),
)

ManagedSnapshot = dict[str, Any]


class ForbiddenFieldError(Exception):
    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


@dataclass(frozen=True)
class MergeResult:
    payload: dict[str, Any] | None
    blocker: str | None = None


# Snapshot ----------------------------------------------------------------------------------


def _email_list(label: str | None) -> str:
    return {"work": "business", "private": "private"}.get((label or "").lower(), "other")


def _phone_list(label: str | None) -> str:
    value = (label or "").lower()
    return {
        "work": "business",
        "mobile": "mobile",
        "private": "private",
        "fax": "fax",
        "other": "other",
    }.get(value, "other")


def snapshot_from_contact(contact: Any) -> ManagedSnapshot:
    """``contact`` is a ``ContactOut`` (pydantic) or a plain dict with the same keys; bank
    accounts are ignored even when present."""
    data = contact.model_dump(mode="json") if hasattr(contact, "model_dump") else dict(contact)
    addresses = list(data.get("addresses") or [])
    postal = next((a for a in addresses if str(a.get("label")) == "postal"), None)
    primary = next((a for a in addresses if a.get("is_primary")), None)
    address = postal or primary
    billing: dict[str, Any] | None = None
    if address is not None:
        street = " ".join(
            p for p in (address.get("street") or "", address.get("house_number") or "") if p
        ).strip()
        billing = {
            "street": street,
            "supplement": address.get("addition") or None,
            "zip": address.get("postal_code") or "",
            "city": address.get("city") or "",
            "countryCode": str(address.get("country") or "").upper(),
        }
    emails = list(data.get("emails") or [])
    primary_email = next((e for e in emails if e.get("is_primary")), None)
    phones = list(data.get("phones") or [])
    primary_phone = next((p for p in phones if p.get("is_primary")), None)
    company_name = (data.get("company_name") or "").strip() or None
    last_name = (data.get("last_name") or "").strip() or None
    kind = "company" if company_name and not last_name else "person"
    return {
        "kind": kind,
        "salutation": (data.get("salutation") or None),
        "first_name": (data.get("first_name") or "").strip() or None,
        "last_name": last_name,
        "company_name": company_name,
        "billing_address": billing,
        "email": (
            {"list": _email_list(primary_email.get("label")), "value": primary_email["email"]}
            if primary_email
            else None
        ),
        "phone": (
            {"list": _phone_list(str(primary_phone.get("label"))), "value": primary_phone["number"]}
            if primary_phone
            else None
        ),
    }


def validate_snapshot(
    snapshot: ManagedSnapshot, fields: set[str] | frozenset[str] | None = None
) -> str | None:
    """Local validation; returns the German field name that blocks a push, else None."""
    fields = fields or MANAGED_FIELDS
    if snapshot["kind"] == "person" and not snapshot.get("last_name"):
        return "Nachname"
    if snapshot["kind"] == "company" and not snapshot.get("company_name"):
        return "Firmenname"
    if "address" in fields:
        addr = snapshot.get("billing_address")
        if addr is None:
            return "Anschrift"
        if not addr.get("street"):
            return "Straße"
        if not addr.get("city"):
            return "Ort"
        if not addr.get("zip"):
            return "Postleitzahl"
        if not COUNTRY_RE.match(addr.get("countryCode") or ""):
            return "Land"
    return None


def display_name(snapshot: ManagedSnapshot) -> str:
    if snapshot["kind"] == "company":
        return str(snapshot.get("company_name") or "")
    return " ".join(p for p in (snapshot.get("first_name"), snapshot.get("last_name")) if p)


# Contact payloads --------------------------------------------------------------------------


def _party(snapshot: ManagedSnapshot) -> dict[str, Any]:
    if snapshot["kind"] == "company":
        return {"company": {"name": snapshot["company_name"]}}
    person: dict[str, Any] = {"lastName": snapshot["last_name"]}
    if snapshot.get("salutation"):
        person["salutation"] = snapshot["salutation"]
    if snapshot.get("first_name"):
        person["firstName"] = snapshot["first_name"]
    return {"person": person}


def _address_entry(addr: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "street": addr["street"],
        "zip": addr["zip"],
        "city": addr["city"],
        "countryCode": addr["countryCode"],
    }
    if addr.get("supplement"):
        entry["supplement"] = addr["supplement"]
    return entry


def build_contact_create(
    snapshot: ManagedSnapshot, roles: list[Literal["customer", "vendor"]]
) -> dict[str, Any]:
    payload: dict[str, Any] = {"version": 0, "roles": {r: {} for r in roles}}
    payload.update(_party(snapshot))
    addr = snapshot.get("billing_address")
    if addr and validate_snapshot(snapshot, {"address"}) is None:
        payload["addresses"] = {"billing": [_address_entry(addr)]}
    if snapshot.get("email"):
        payload["emailAddresses"] = {snapshot["email"]["list"]: [snapshot["email"]["value"]]}
    if snapshot.get("phone"):
        payload["phoneNumbers"] = {snapshot["phone"]["list"]: [snapshot["phone"]["value"]]}
    return payload


def remote_managed_values(remote: dict[str, Any]) -> ManagedSnapshot:
    """Managed fields as Lexware returned them (baseline and conflict comparison)."""
    person = remote.get("person") or {}
    company = remote.get("company") or {}
    billing = ((remote.get("addresses") or {}).get("billing") or [None])[0]
    email = _single_entry(remote.get("emailAddresses") or {})
    phone = _single_entry(remote.get("phoneNumbers") or {})
    return {
        "kind": "company" if company else "person",
        "salutation": person.get("salutation"),
        "first_name": person.get("firstName"),
        "last_name": person.get("lastName"),
        "company_name": company.get("name"),
        "billing_address": (
            {
                "street": billing.get("street") or "",
                "supplement": billing.get("supplement"),
                "zip": billing.get("zip") or "",
                "city": billing.get("city") or "",
                "countryCode": billing.get("countryCode") or "",
            }
            if isinstance(billing, dict)
            else None
        ),
        "email": email,
        "phone": phone,
    }


def _single_entry(lists: dict[str, Any]) -> dict[str, str] | None:
    for name, values in lists.items():
        if isinstance(values, list) and values:
            return {"list": name, "value": str(values[0])}
    return None


def field_value(snapshot: ManagedSnapshot, field: str) -> Any:
    """Comparable value of a managed field: the e mail and phone list names are not compared
    (the merge keeps the list Lexware uses), an empty supplement equals a missing one."""
    if field == "name":
        return {k: snapshot.get(k) for k in ("kind", "first_name", "last_name", "company_name")}
    if field == "address":
        addr = snapshot.get("billing_address")
        if not isinstance(addr, dict):
            return None
        return {k: v for k, v in addr.items() if not (k == "supplement" and not v)}
    entry = snapshot.get(field)
    return entry.get("value") if isinstance(entry, dict) else None


def multi_entry_lists(remote: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for parent, child in MULTI_ENTRY_LISTS:
        values = (remote.get(parent) or {}).get(child)
        if isinstance(values, list) and len(values) > 1:
            found.append(f"{parent}.{child}")
    for parent in ("emailAddresses", "phoneNumbers"):
        lists = remote.get(parent) or {}
        for name, values in lists.items():
            if isinstance(values, list) and len(values) > 1:
                found.append(f"{parent}.{name}")
    return found


def _check_forbidden(before: Any, after: Any, path: str = "") -> None:
    if isinstance(after, dict):
        for key, value in after.items():
            sub = f"{path}.{key}" if path else key
            old = before.get(key) if isinstance(before, dict) else None
            if FORBIDDEN_KEY_RE.search(key) and old != value:
                raise ForbiddenFieldError(sub)
            _check_forbidden(old, value, sub)
    elif isinstance(after, list):
        for index, item in enumerate(after):
            old = before[index] if isinstance(before, list) and index < len(before) else None
            _check_forbidden(old, item, f"{path}[{index}]")


def merge_contact_update(
    remote: dict[str, Any], snapshot: ManagedSnapshot, fields: set[str], *, force: bool = False
) -> MergeResult:
    """Full read object with only the named managed fields replaced (PUT replaces everything
    that is omitted, so nothing is dropped). ``force`` only concerns the caller's conflict
    check; blockers apply regardless."""
    if remote.get("archived"):
        return MergeResult(None, "remote_archived")
    if multi_entry_lists(remote):
        return MergeResult(None, "multi_entry")
    remote_kind = "company" if remote.get("company") else "person"
    if remote_kind != snapshot["kind"]:
        return MergeResult(None, "kind_changed")
    payload = copy.deepcopy(remote)
    for key in READ_ONLY_KEYS:
        payload.pop(key, None)
    if "address" in fields and snapshot.get("billing_address"):
        payload.setdefault("addresses", {})
        payload["addresses"]["billing"] = [_address_entry(snapshot["billing_address"])]
    if "email" in fields and snapshot.get("email"):
        lists = dict(payload.get("emailAddresses") or {})
        current = _single_entry(lists)
        target = current["list"] if current else snapshot["email"]["list"]
        lists = {k: v for k, v in lists.items() if not (isinstance(v, list) and v)}
        lists[target] = [snapshot["email"]["value"]]
        payload["emailAddresses"] = lists
    if "phone" in fields and snapshot.get("phone"):
        lists = dict(payload.get("phoneNumbers") or {})
        current = _single_entry(lists)
        target = current["list"] if current else snapshot["phone"]["list"]
        lists = {k: v for k, v in lists.items() if not (isinstance(v, list) and v)}
        lists[target] = [snapshot["phone"]["value"]]
        payload["phoneNumbers"] = lists
    if "name" in fields:
        if snapshot["kind"] == "company":
            payload.setdefault("company", {})["name"] = snapshot["company_name"]
        else:
            person = payload.setdefault("person", {})
            person["lastName"] = snapshot["last_name"]
            if snapshot.get("first_name"):
                person["firstName"] = snapshot["first_name"]
            else:
                person.pop("firstName", None)
    payload["version"] = remote.get("version")
    _check_forbidden(remote, payload)
    return MergeResult(payload, None)


# Invoice drafts ----------------------------------------------------------------------------


def berlin_voucher_date(day: date) -> str:
    """``yyyy-MM-ddT00:00:00.000+HH:MM`` with the Europe/Berlin offset of that day."""
    local = datetime(day.year, day.month, day.day, tzinfo=BERLIN)
    offset = local.strftime("%z")
    return f"{day.isoformat()}T00:00:00.000{offset[:3]}:{offset[3:]}"


def money(value: Decimal | str | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def quantity(value: Decimal | str | int) -> Decimal:
    return round_to(value, Decimal("0.0001"))


def build_invoice_draft(
    *,
    voucher_date: date,
    tax_type: Literal["net", "gross", "vatfree"],
    line_items: list[dict[str, Any]],
    shipping: dict[str, Any],
    address_contact_id: str | None,
    address_fallback: ManagedSnapshot | None,
    title: str | None = None,
    introduction: str | None = None,
    remark: str | None = None,
) -> dict[str, Any]:
    """Only documented fields; ``finalize`` and read only fields never appear."""
    if address_contact_id:
        address: dict[str, Any] = {"contactId": address_contact_id}
    elif address_fallback and address_fallback.get("billing_address"):
        addr = address_fallback["billing_address"]
        address = {"name": display_name(address_fallback), **_address_entry(addr)}
    else:
        raise ValueError("Adresse fehlt")
    price_key = "grossAmount" if tax_type == "gross" else "netAmount"
    items = []
    for item in line_items:
        rate = int(item["tax_rate_percent"])
        if tax_type == "vatfree" and rate != 0:
            raise ValueError("Steuerfreie Rechnungen erlauben nur 0 Prozent")
        entry: dict[str, Any] = {
            "type": "custom",
            "name": item["name"],
            "quantity": quantity(item["quantity"]),
            "unitName": item["unit_name"],
            "unitPrice": {
                "currency": "EUR",
                price_key: money(item["unit_price"]),
                "taxRatePercentage": rate,
            },
            "discountPercentage": 0,
        }
        if item.get("description"):
            entry["description"] = item["description"]
        items.append(entry)
    shipping_out: dict[str, Any] = {"shippingType": shipping["type"]}
    if shipping["type"] in ("service", "serviceperiod"):
        shipping_out["shippingDate"] = berlin_voucher_date(shipping["date"])
    if shipping["type"] == "serviceperiod":
        shipping_out["shippingEndDate"] = berlin_voucher_date(shipping["end_date"])
    payload: dict[str, Any] = {
        "voucherDate": berlin_voucher_date(voucher_date),
        "address": address,
        "lineItems": items,
        "totalPrice": {"currency": "EUR"},
        "taxConditions": {"taxType": tax_type},
        "shippingConditions": shipping_out,
        "language": "de",
    }
    for key, value in (("title", title), ("introduction", introduction), ("remark", remark)):
        if value:
            payload[key] = value
    return payload


def invoice_totals(tax_type: str, line_items: list[dict[str, Any]]) -> dict[str, Decimal]:
    """Local control sums (Decimal, ROUND_HALF_UP to cents); Lexware computes the binding
    totals."""
    net = Decimal("0")
    gross = Decimal("0")
    for item in line_items:
        amount = money(item["unit_price"]) * quantity(item["quantity"])
        rate = Decimal(int(item["tax_rate_percent"])) / Decimal(100)
        if tax_type == "gross":
            gross += amount
            net += amount / (1 + rate)
        else:
            net += amount
            gross += amount * (1 + rate)
    net = money(net)
    gross = money(gross)
    return {"net": net, "tax": money(gross - net), "gross": gross}


def json_ready(value: Any) -> Any:
    """Decimal as JSON number for the lexoffice body; lossless or ``ValueError`` (GAI-207).

    The domain keeps Decimal; only this boundary converts, via ``core.money.json_number``."""
    if isinstance(value, Decimal):
        return json_number(value)
    if isinstance(value, dict):
        return {k: json_ready(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_ready(v) for v in value]
    return value
