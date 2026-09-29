"""Payload builders (rule INT-LEXO-01, spec 3.1 and 8.1): create payload, merge keeps every
unmanaged field, list selection by label, blockers, local validation, forbidden field check,
invoice draft schema with DST edge and Decimal serialisation."""

from __future__ import annotations

import copy
import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from mhvp.integrations.lexoffice_ext import payloads as p


def _contact(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": "person",
        "salutation": "Herr",
        "first_name": "Hardy",
        "last_name": "Harter",
        "company_name": None,
        "addresses": [
            {
                "label": "private",
                "street": "Nebenweg",
                "house_number": "2",
                "postal_code": "11111",
                "city": "Anderswo",
                "country": "DE",
                "addition": None,
                "is_primary": True,
            },
            {
                "label": "postal",
                "street": "Hauptstraße",
                "house_number": "5",
                "postal_code": "40721",
                "city": "Hilden",
                "country": "de",
                "addition": "Hinterhaus",
                "is_primary": False,
            },
        ],
        "emails": [{"label": "work", "email": "hardy@example.org", "is_primary": True}],
        "phones": [{"label": "mobile", "number": "+491701234567", "is_primary": True}],
        "bank_accounts": [{"iban": "DE00", "bic": "X"}],
    }
    base.update(overrides)
    return base


def test_snapshot_prefers_postal_label_and_maps_lists() -> None:
    snap = p.snapshot_from_contact(_contact())
    assert snap["kind"] == "person"
    assert snap["billing_address"] == {
        "street": "Hauptstraße 5",
        "supplement": "Hinterhaus",
        "zip": "40721",
        "city": "Hilden",
        "countryCode": "DE",
    }
    assert snap["email"] == {"list": "business", "value": "hardy@example.org"}
    assert snap["phone"] == {"list": "mobile", "value": "+491701234567"}
    assert "iban" not in json.dumps(snap).lower()


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("work", "business"),
        ("mobile", "mobile"),
        ("fax", "fax"),
        ("private", "private"),
        ("other", "other"),
        ("weird", "other"),
    ],
)
def test_phone_list_by_label(label: str, expected: str) -> None:
    snap = p.snapshot_from_contact(
        _contact(phones=[{"label": label, "number": "+49", "is_primary": True}])
    )
    assert snap["phone"]["list"] == expected


def test_kind_company_when_company_name_without_last_name() -> None:
    snap = p.snapshot_from_contact(
        _contact(company_name="Harter GmbH", last_name=None, first_name=None)
    )
    assert snap["kind"] == "company"
    create = p.build_contact_create(snap, ["customer"])
    assert create["company"] == {"name": "Harter GmbH"}
    assert "person" not in create


def test_create_payload_shape() -> None:
    create = p.build_contact_create(p.snapshot_from_contact(_contact()), ["customer", "vendor"])
    assert create["version"] == 0
    assert create["roles"] == {"customer": {}, "vendor": {}}
    assert create["person"] == {"salutation": "Herr", "firstName": "Hardy", "lastName": "Harter"}
    assert create["addresses"] == {
        "billing": [
            {
                "street": "Hauptstraße 5",
                "zip": "40721",
                "city": "Hilden",
                "countryCode": "DE",
                "supplement": "Hinterhaus",
            }
        ]
    }
    assert create["emailAddresses"] == {"business": ["hardy@example.org"]}
    assert create["phoneNumbers"] == {"mobile": ["+491701234567"]}


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"last_name": None, "first_name": "Hardy"}, "Nachname"),
        ({"addresses": []}, "Anschrift"),
        (
            {
                "addresses": [
                    {
                        "label": "postal",
                        "street": None,
                        "house_number": None,
                        "postal_code": "1",
                        "city": "X",
                        "country": "DE",
                        "is_primary": True,
                    }
                ]
            },
            "Straße",
        ),
        (
            {
                "addresses": [
                    {
                        "label": "postal",
                        "street": "A",
                        "house_number": None,
                        "postal_code": "1",
                        "city": None,
                        "country": "DE",
                        "is_primary": True,
                    }
                ]
            },
            "Ort",
        ),
        (
            {
                "addresses": [
                    {
                        "label": "postal",
                        "street": "A",
                        "house_number": None,
                        "postal_code": "1",
                        "city": "X",
                        "country": "deu",
                        "is_primary": True,
                    }
                ]
            },
            "Land",
        ),
    ],
)
def test_local_validation(overrides: dict[str, Any], expected: str) -> None:
    assert p.validate_snapshot(p.snapshot_from_contact(_contact(**overrides))) == expected


def _remote() -> dict[str, Any]:
    return {
        "id": "c-1",
        "organizationId": "org",
        "version": 7,
        "roles": {"customer": {"number": 10001}},
        "person": {"salutation": "Herr", "firstName": "Hardy", "lastName": "Harter"},
        "addresses": {
            "billing": [{"street": "Alt 1", "zip": "00000", "city": "Alt", "countryCode": "DE"}],
            "shipping": [],
        },
        "emailAddresses": {"private": ["old@example.org"]},
        "phoneNumbers": {"business": ["+4900"]},
        "note": "internal note stays",
        "xRechnung": {"buyerReference": "X"},
        "taxNumber": "123",
        "vatRegistrationId": "DE999",
        "archived": False,
        "createdDate": "x",
        "updatedDate": "y",
    }


def test_merge_replaces_only_named_fields_and_keeps_the_rest() -> None:
    remote = _remote()
    before = copy.deepcopy(remote)
    result = p.merge_contact_update(
        remote, p.snapshot_from_contact(_contact()), {"address", "email"}
    )
    assert result.blocker is None
    body = result.payload
    assert body is not None
    assert body["addresses"]["billing"] == [
        {
            "street": "Hauptstraße 5",
            "zip": "40721",
            "city": "Hilden",
            "countryCode": "DE",
            "supplement": "Hinterhaus",
        }
    ]
    # E mail replaces the one list that holds the entry (private), not the CRM label list.
    assert body["emailAddresses"] == {"private": ["hardy@example.org"]}
    assert body["phoneNumbers"] == {"business": ["+4900"]}
    for key in ("roles", "note", "xRechnung", "taxNumber", "vatRegistrationId"):
        assert body[key] == before[key]
    assert body["version"] == 7
    for key in ("id", "organizationId", "createdDate", "updatedDate", "archived"):
        assert key not in body
    assert remote == before  # input untouched


def test_merge_name_only_with_field() -> None:
    snap = p.snapshot_from_contact(_contact(first_name="Harald"))
    without = p.merge_contact_update(_remote(), snap, {"email"})
    assert without.payload is not None
    assert without.payload["person"]["firstName"] == "Hardy"
    with_name = p.merge_contact_update(_remote(), snap, {"name"})
    assert with_name.payload is not None
    assert with_name.payload["person"] == {
        "salutation": "Herr",
        "firstName": "Harald",
        "lastName": "Harter",
    }


@pytest.mark.parametrize(
    ("change", "blocker"),
    [
        ({"archived": True}, "remote_archived"),
        ({"emailAddresses": {"private": ["a@x.de", "b@x.de"]}}, "multi_entry"),
        ({"addresses": {"billing": [{"street": "a"}, {"street": "b"}]}}, "multi_entry"),
        ({"company": {"name": "Firma"}, "person": None}, "kind_changed"),
    ],
)
def test_merge_blockers(change: dict[str, Any], blocker: str) -> None:
    remote = _remote()
    remote.update(change)
    if change.get("person", "keep") is None:
        remote.pop("person")
    assert (
        p.merge_contact_update(remote, p.snapshot_from_contact(_contact()), {"address"}).blocker
        == blocker
    )


def test_forbidden_field_detected() -> None:
    remote = _remote()
    remote["bankAccount"] = {"iban": "DE1"}
    snap = p.snapshot_from_contact(_contact())
    # Unchanged forbidden values pass through untouched.
    ok = p.merge_contact_update(remote, snap, {"email"})
    assert ok.payload is not None
    assert ok.payload["bankAccount"] == {"iban": "DE1"}
    with pytest.raises(p.ForbiddenFieldError):
        p._check_forbidden(remote, {**ok.payload, "taxNumber": "changed"})


# Invoice drafts ------------------------------------------------------------------------------


def _items() -> list[dict[str, Any]]:
    return [
        {
            "name": "Beratung",
            "quantity": Decimal("2"),
            "unit_name": "Stunde",
            "unit_price": Decimal("12.50"),
            "tax_rate_percent": 19,
        }
    ]


def test_invoice_draft_exact_keys_and_dst_dates() -> None:
    body = p.build_invoice_draft(
        voucher_date=date(2026, 3, 29),
        tax_type="net",
        line_items=_items(),
        shipping={
            "type": "serviceperiod",
            "date": date(2026, 3, 29),
            "end_date": date(2026, 3, 30),
        },
        address_contact_id="c-1",
        address_fallback=None,
        title="Beratung",
    )
    assert set(body) == {
        "voucherDate",
        "address",
        "lineItems",
        "totalPrice",
        "taxConditions",
        "shippingConditions",
        "language",
        "title",
    }
    assert body["voucherDate"] == "2026-03-29T00:00:00.000+01:00"
    assert body["shippingConditions"]["shippingEndDate"] == "2026-03-30T00:00:00.000+02:00"
    assert body["address"] == {"contactId": "c-1"}
    item = body["lineItems"][0]
    assert item["unitPrice"] == {
        "currency": "EUR",
        "netAmount": Decimal("12.50"),
        "taxRatePercentage": 19,
    }
    assert item["type"] == "custom"
    assert item["discountPercentage"] == 0
    assert "finalize" not in json.dumps(p.json_ready(body))
    assert (
        json.loads(json.dumps(p.json_ready(body)))["lineItems"][0]["unitPrice"]["netAmount"] == 12.5
    )


def test_invoice_draft_gross_and_vatfree_and_fallback_address() -> None:
    snap = p.snapshot_from_contact(_contact())
    gross = p.build_invoice_draft(
        voucher_date=date(2026, 9, 29),
        tax_type="gross",
        line_items=_items(),
        shipping={"type": "none"},
        address_contact_id=None,
        address_fallback=snap,
    )
    assert "grossAmount" in gross["lineItems"][0]["unitPrice"]
    assert gross["address"]["name"] == "Hardy Harter"
    assert gross["address"]["street"] == "Hauptstraße 5"
    with pytest.raises(ValueError, match="0 Prozent"):
        p.build_invoice_draft(
            voucher_date=date(2026, 9, 29),
            tax_type="vatfree",
            line_items=_items(),
            shipping={"type": "none"},
            address_contact_id="c",
            address_fallback=None,
        )
    with pytest.raises(ValueError, match="Adresse"):
        p.build_invoice_draft(
            voucher_date=date(2026, 9, 29),
            tax_type="net",
            line_items=_items(),
            shipping={"type": "none"},
            address_contact_id=None,
            address_fallback=None,
        )


def test_invoice_totals_rounding() -> None:
    totals = p.invoice_totals("net", _items())
    assert totals == {"net": Decimal("25.00"), "tax": Decimal("4.75"), "gross": Decimal("29.75")}
    gross = p.invoice_totals(
        "gross", [{"unit_price": Decimal("119.00"), "quantity": 1, "tax_rate_percent": 19}]
    )
    assert gross == {"net": Decimal("100.00"), "tax": Decimal("19.00"), "gross": Decimal("119.00")}
