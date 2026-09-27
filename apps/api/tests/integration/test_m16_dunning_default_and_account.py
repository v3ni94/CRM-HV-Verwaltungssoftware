"""M16-13 payment account in the dunning letter (default account of the legal entity that owns
the receivable, full IBAN and holder, letter refused without one) and M16-03 start of default
kept apart from the due date (tenant setting with three modes, derived only from recorded
facts, interest only from a derivable default start). Tenant separation: accounts, settings
and cases of tenant A are invisible to tenant B."""

import asyncio
import io
from collections.abc import Iterator
from datetime import date
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pypdf import PdfReader

from mhvp.accounting import dunning
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m16_dunning_letters import (
    BUCKET,
    OpenG1,
    _debtor_contract,
    _ok,
    _settings,
)

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
HOA_IBAN = "DE89370400440532013000"
OTHER_IBAN = "DE02120300000000202051"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"dv-{RUN}", name=f"Verzug {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"dw-{RUN}", name=f"Fremd2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("dvadmin", a, "tenant_admin"),
            ("dvacc", a, "accountant_no_banking"),
            ("dvother", b, "tenant_admin"),
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


@pytest.fixture
def s3() -> Iterator[None]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield


@pytest.fixture
def clients(
    database: Database, redis_url: str, s3: None
) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with (
        TestClient(create_app(settings)) as closed,
        TestClient(create_app(settings, release_gate_resolver=OpenG1())) as open_,
    ):
        yield closed, open_


def _hoa_property_without_account(
    c: TestClient, h: dict[str, str], number: str, name: str
) -> tuple[str, str, str]:
    """HOA property with ledger and payment type accounts but without any bank account (the
    letters test helper flags a default account right away; this one starts without)."""
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": name, "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    accounts = {
        a["number"]: a["id"] for a in _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    for code, acc_no in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            c.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": accounts[acc_no]},
                headers=h,
            )
        )
    return str(prop["id"]), str(ledger), str(hoa)


def _pdf_text(response: Any) -> str:
    assert response.status_code == 200, response.text
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)


def test_default_start_derivation_only_from_recorded_facts() -> None:
    """Pure derivation (docs/rules/M16-03.md): no mode, no start; calendar mode starts the day
    after the oldest due date; the 30 day mode needs a recorded receipt per item and takes the
    later of due date and receipt; the reminder mode needs a recorded receipt of a letter."""
    items: list[dict[str, Any]] = [
        {"due_date": date(2026, 3, 3), "notice_received_on": None},
        {"due_date": date(2026, 4, 3), "notice_received_on": date(2026, 4, 10)},
    ]
    none = dunning.default_start(None, items=items, reminder_received_on=None)
    assert none.start is None
    assert "nicht festgelegt" in none.note
    calendar = dunning.default_start(
        dunning.DEFAULT_MODE_CALENDAR, items=items, reminder_received_on=None
    )
    assert calendar.start == date(2026, 3, 4)
    notice = dunning.default_start(
        dunning.DEFAULT_MODE_AFTER_NOTICE, items=items, reminder_received_on=None
    )
    assert notice.start == date(2026, 5, 11)  # 10.04. plus 30 days, default from the day after
    assert "1 Posten ohne erfasstes Zugangsdatum" in notice.note
    no_receipt = dunning.default_start(
        dunning.DEFAULT_MODE_AFTER_NOTICE, items=items[:1], reminder_received_on=None
    )
    assert no_receipt.start is None
    assert "Zugangsdatum" in no_receipt.note
    reminder = dunning.default_start(
        dunning.DEFAULT_MODE_AFTER_REMINDER, items=items, reminder_received_on=None
    )
    assert reminder.start is None
    assert "Zugang einer Mahnung" in reminder.note
    reminder_known = dunning.default_start(
        dunning.DEFAULT_MODE_AFTER_REMINDER, items=items, reminder_received_on=date(2026, 3, 25)
    )
    assert reminder_known.start == date(2026, 3, 26)


def test_letter_names_claim_holder_account_and_default_modes(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, gated = clients
    h = bearer(login(gated, world, "dvadmin"))
    acc_user = bearer(login(gated, world, "dvacc"))
    other = bearer(login(gated, world, "dvother"))
    prop, ledger, hoa = _hoa_property_without_account(gated, h, "781", "Mahnhaus Konto")
    contract = _debtor_contract(gated, h, prop, "01")
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=h))
    run = _ok(
        gated.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201
    )
    _ok(gated.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    _ok(gated.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    settings_body: dict[str, Any] = {
        "levels": [
            {"level": 1, "min_days_overdue": 5, "text": "Zahlungserinnerung"},
            {"level": 2, "min_days_overdue": 5, "text": "Mahnung", "payment_days": 10},
        ],
        "threshold_amount": "20.00",
        "fee_from_level": 2,
        "interest_enabled": False,
    }
    saved = _ok(gated.put(f"{A}/dunning-settings", json=settings_body, headers=h))
    assert saved["default_start_mode"] is None
    assert set(saved["default_start_modes"]) == set(dunning.DEFAULT_MODES)
    bad_mode = gated.put(
        f"{A}/dunning-settings", json={**settings_body, "default_start_mode": "sofort"}, headers=h
    )
    assert bad_mode.status_code == 422

    # No default account of the WEG yet: the preview warns, the letter is refused (M16-13).
    first = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-03-20"}, headers=h), 201)
    case = next(c for c in first["cases"] if c["contract_id"] == contract["id"])
    assert case["status"] == "proposed"
    assert case["bank_account"] is None
    # M16-15: the case names its ledger, legal entity and property so the CRM can link to
    # the object's bank accounts when the default account is missing.
    assert case["ledger_id"] == ledger
    assert case["legal_entity_id"] == hoa
    assert case["property_id"] == prop
    assert case["property_number"] == "781"
    assert case["bank_warning"] == dunning.NO_BANK_ACCOUNT_WARNING
    assert dunning.NO_BANK_ACCOUNT_WARNING in case["warnings"]
    assert case["due_date"] == "2026-03-03"
    assert case["default_start"] is None  # no mode decided: due date only, no default
    assert first["totals"]["bank_account_missing"] == 1
    refused = gated.post(f"{A}/dunning-cases/{case['id']}/letter-preview", headers=h)
    assert refused.status_code == 422, refused.text
    assert "Standardkonto" in refused.json()["detail"]

    # A deposit account can never be the default; a non default account does not count.
    deposit = gated.post(
        f"/api/v1/properties/{prop}/bank-accounts",
        json={
            "legal_entity_id": hoa,
            "kind": "deposit",
            "iban": OTHER_IBAN,
            "holder": "WEG Kaution",
            "valid_from": "2020-01-01",
            "is_default": True,
        },
        headers=h,
    )
    assert deposit.status_code == 422, deposit.text
    reserve = _ok(
        gated.post(
            f"/api/v1/properties/{prop}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "reserve",
                "iban": OTHER_IBAN,
                "holder": "WEG Rücklage",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )
    assert reserve["is_default"] is False
    still_refused = gated.post(f"{A}/dunning-cases/{case['id']}/letter-preview", headers=h)
    assert still_refused.status_code == 422

    # Default account of the WEG (the legal entity that owns the Hausgeld receivable).
    account = _ok(
        gated.post(
            f"/api/v1/properties/{prop}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": HOA_IBAN,
                "bic": "COBADEFFXXX",
                "holder": "WEG Mahnhaus Konto",
                "valid_from": "2020-01-01",
                "is_default": True,
            },
            headers=h,
        ),
        201,
    )
    assert account["is_default"] is True
    assert account["iban_masked"].endswith("3000")
    assert "****" in account["iban_masked"]
    # Tenant B can neither see nor flag the account of tenant A.
    assert (
        gated.post(
            f"/api/v1/properties/{prop}/bank-accounts/{account['id']}/default", headers=other
        ).status_code
        == 404
    )
    assert gated.get(f"{A}/dunning-runs/{first['id']}", headers=other).status_code == 404
    assert _ok(gated.get(f"{A}/dunning-settings", headers=other))["default_start_mode"] is None

    # The existing case resolves the account at letter time; the letter prints holder and the
    # full IBAN of the WEG, never the reserve account, and the API keeps the IBAN masked.
    text = _pdf_text(
        gated.post(
            f"{A}/dunning-cases/{case['id']}/letter-preview",
            json={"letter_date": "2026-03-21"},
            headers=h,
        )
    )
    assert "WEG Mahnhaus Konto" in text
    assert "DE89 3704 0044 0532 0130 00" in text
    assert "COBADEFFXXX" in text
    assert "0000 2020 51" not in text  # reserve account is not the payment target
    assert "Ihnen bekannte Konto" not in text
    filed = _ok(gated.post(f"{A}/dunning-cases/{case['id']}/letter", headers=h), 201)
    assert filed["bank_account"]["id"] == account["id"]
    assert filed["bank_account"]["iban_masked"].endswith("3000")
    assert HOA_IBAN not in str(filed)
    assert filed["bank_warning"] is None

    # Flagging the reserve account as default moves the flag (at most one per legal entity).
    moved = _ok(
        gated.post(f"/api/v1/properties/{prop}/bank-accounts/{reserve['id']}/default", headers=h)
    )
    assert moved["is_default"] is True
    accounts = _ok(gated.get(f"/api/v1/properties/{prop}/bank-accounts", headers=h))
    assert [a["id"] for a in accounts if a["is_default"]] == [reserve["id"]]
    _ok(gated.post(f"/api/v1/properties/{prop}/bank-accounts/{account['id']}/default", headers=h))

    # Default modes (M16-03): calendar mode starts the day after the contractual due date.
    _ok(
        gated.put(
            f"{A}/dunning-settings",
            json={**settings_body, "default_start_mode": "calendar_due_date"},
            headers=h,
        )
    )
    calendar = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-03-20"}, headers=h), 201)
    c_case = next(c for c in calendar["cases"] if c["contract_id"] == contract["id"])
    assert c_case["due_date"] == "2026-03-03"
    assert c_case["default_start"] == "2026-03-04"
    assert c_case["default_mode"] == "calendar_due_date"
    assert c_case["bank_account"]["id"] == account["id"]
    assert "Tag nach kalendermäßiger Fälligkeit" in c_case["reason"]

    # 30 day mode: no start until a person records the receipt of the demand per open item.
    _ok(
        gated.put(
            f"{A}/dunning-settings",
            json={**settings_body, "default_start_mode": "after_notice_30_days"},
            headers=h,
        )
    )
    notice = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-05-20"}, headers=h), 201)
    n_case = next(c for c in notice["cases"] if c["contract_id"] == contract["id"])
    assert n_case["default_start"] is None
    assert "Zugangsdatum" in n_case["reason"]
    for item in n_case["open_items"]:
        _ok(
            gated.patch(
                f"{A}/open-items/{item['open_item_id']}/notice-received",
                json={"notice_received_on": "2026-03-05"},
                headers=h,
            )
        )
    assert (
        gated.patch(
            f"{A}/open-items/{n_case['open_items'][0]['open_item_id']}/notice-received",
            json={"notice_received_on": "2026-03-05"},
            headers=other,
        ).status_code
        == 404
    )
    notice2 = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-05-20"}, headers=h), 201)
    n2 = next(c for c in notice2["cases"] if c["contract_id"] == contract["id"])
    assert n2["default_start"] == "2026-04-05"  # 05.03. plus 30 days, from the day after

    # Reminder mode: default starts only from a recorded receipt of a sent letter; the
    # receipt is entered with "als versendet markieren", never derived from the send date.
    _ok(
        gated.put(
            f"{A}/dunning-settings",
            json={**settings_body, "default_start_mode": "after_reminder"},
            headers=h,
        )
    )
    run1 = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-03-20"}, headers=h), 201)
    r1 = next(c for c in run1["cases"] if c["contract_id"] == contract["id"])
    assert r1["level"] == 1
    assert r1["default_start"] is None
    approved = _ok(gated.post(f"{A}/dunning-runs/{run1['id']}/approve", headers=acc_user))
    r1a = next(c for c in approved["cases"] if c["contract_id"] == contract["id"])
    sent = _ok(
        gated.post(
            f"{A}/dunning-cases/{r1a['id']}/mark-sent",
            json={"channel": "post", "received_on": "2026-03-24"},
            headers=h,
        )
    )
    assert sent["received_on"] == "2026-03-24"
    run2 = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-04-10"}, headers=h), 201)
    r2 = next(c for c in run2["cases"] if c["contract_id"] == contract["id"])
    assert r2["level"] == 2
    assert r2["default_start"] == "2026-03-25"
    assert r2["default_mode_label"] == dunning.DEFAULT_MODE_LABELS["after_reminder"]
    # Interest stays 0,00 while it is not configured (draft behind the gate, M16-01).
    assert r2["interest_amount"] == "0.00"
    letter2 = _pdf_text(
        gated.post(
            f"{A}/dunning-cases/{r2['id']}/letter-preview",
            json={"letter_date": "2026-04-11"},
            headers=h,
        )
    )
    assert "DE89 3704 0044 0532 0130 00" in letter2
    assert "Verzug" not in letter2  # the letter never asserts default

    # Consumer flag on the contact (M16-03): a plain marker, null means not assessed.
    contact = _ok(
        gated.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Karl", "last_name": f"Verbraucher{RUN}"},
            headers=h,
        ),
        201,
    )
    assert contact["is_consumer"] is None
    patched = _ok(
        gated.patch(f"/api/v1/contacts/{contact['id']}", json={"is_consumer": True}, headers=h)
    )
    assert patched["is_consumer"] is True
    assert gated.get(f"/api/v1/contacts/{contact['id']}", headers=other).status_code == 404
    # G1 closed: the preview still works, nothing here posts (client without gates).
    assert (
        client.get(f"{A}/dunning-runs", headers=bearer(login(client, world, "dvadmin"))).status_code
        == 200
    )
