"""``python -m mhvp.platform.demo_seed``: synthetic demo tenant (GA12-04, section 17 ``make seed``).

Creates the tenant ``demo-muster`` with purely invented data: 3 properties (WEG), 40 units,
60 contacts (40 owners, 20 other), 12 months of journal entries as drafts and 200 bank
transactions. Names are invented (Max Beispiel, Musterstrasse), the three own bank accounts use
the documented test IBANs of the test suite, counterparty IBANs are generated for a fictitious
bank code. No real person, no real account.

Safety rules: runs only in the environments ``dev``, ``test`` and ``staging`` and only with
``MHVP_DEMO_SEED=1``; the demo administrator password comes from ``MHVP_DEMO_ADMIN_PASSWORD``
(never from the repository). Nothing is posted: the journal entries stay drafts, no release gate
(G1 to G5) is opened and no platform flag is switched on. The data is created through the public
API (properties, units, contacts, contracts, ledger, drafts) and, for the bank rows, through the
import service of the banking module with an in-memory statement. A second run does nothing
(the tenant already exists). Open decision: docs/OPEN_QUESTIONS.md AA15-01.
"""

import asyncio
import os
import sys
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Protocol

import mhvp.models  # noqa: F401  (registers every mapped table so cross-module FKs resolve)
from mhvp.core.config import Environment, get_settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.logging import configure_logging, get_logger

DEMO_SLUG = "demo-muster"
DEMO_NAME = "Demo Musterverwaltung (Testdaten)"
DEMO_ADMIN_EMAIL = "demo-admin@example.org"
ALLOWED_ENVIRONMENTS = frozenset({Environment.DEV, Environment.TEST, Environment.STAGING})
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

PROPERTIES = 3
UNITS = 40
CONTACTS = 60
BANK_TRANSACTIONS = 200
MONTHS = 12
# Documented test IBANs of the test suite (one per property).
TEST_IBANS = ("DE02120300000000202051", "DE02100500000054540402", "DE02500105170137075030")
FIRST_NAMES = ("Max", "Erika", "Paul", "Anna", "Jonas", "Lena", "Felix", "Marie", "Tom", "Eva")
COMPANIES = ("Muster Hausmeisterdienst", "Beispiel Heizungsbau", "Muster Gartenpflege")


class ApiClient(Protocol):
    """The part of ``httpx.Client`` and the Starlette ``TestClient`` that the seed uses."""

    def post(self, url: str, **kwargs: Any) -> Any: ...

    def get(self, url: str, **kwargs: Any) -> Any: ...


def synthetic_iban(index: int) -> str:
    """DE IBAN for the fictitious bank code 10000000 with valid check digits (ISO 13616)."""
    bban = f"10000000{index:010d}"
    check = 98 - int(bban + "131400") % 97
    return f"DE{check:02d}{bban}"


def unit_split(units: int = UNITS, properties: int = PROPERTIES) -> list[int]:
    base, extra = divmod(units, properties)
    return [base + (1 if i < extra else 0) for i in range(properties)]


def month_starts(end: date, months: int = MONTHS) -> list[date]:
    """First days of the ``months`` months up to and including the month of ``end``."""
    year, month = end.year, end.month
    out: list[date] = []
    for _ in range(months):
        out.append(date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return sorted(out)


def _post(c: ApiClient, h: dict[str, str], url: str, body: dict[str, Any]) -> dict[str, Any]:
    response = c.post(url, json=body, headers=h)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"POST {url} -> {response.status_code}: {response.text[:300]}")
    return dict(response.json())


def seed_via_api(c: ApiClient, h: dict[str, str], end: date) -> dict[str, Any]:
    """Properties, units, contacts, owner contracts, ledgers and draft entries."""
    a = "/api/v1/accounting"
    template = _post(c, h, f"{a}/templates/default", {})
    result: dict[str, Any] = {"properties": [], "units": 0, "contacts": 0, "entries": 0}
    contact_no = 0
    for p_index, unit_count in enumerate(unit_split()):
        prop = _post(
            c,
            h,
            "/api/v1/properties",
            {
                "number": f"9{p_index + 1:02d}",
                "name": f"Musterstraße {10 + p_index * 10} (Demo WEG)",
                "management_type": "hoa",
            },
        )
        entity = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
        building = _post(c, h, f"/api/v1/properties/{prop['id']}/buildings", {"name": "Haus"})
        account = _post(
            c,
            h,
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            {
                "legal_entity_id": entity,
                "kind": "hoa",
                "iban": TEST_IBANS[p_index],
                "holder": f"GdWE Musterstraße {10 + p_index * 10}",
                "valid_from": "2020-01-01",
            },
        )
        keys = {
            k["code"]: k["id"]
            for k in c.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h).json()
        }
        for n in range(1, unit_count + 1):
            unit = _post(
                c,
                h,
                f"/api/v1/properties/{prop['id']}/units",
                {
                    "building_id": building["id"],
                    "number": f"{n:03d}",
                    "label": f"WE {n:03d}",
                    "unit_type": "apartment",
                },
            )
            _post(
                c,
                h,
                f"/api/v1/units/{unit['id']}/allocation-values",
                {"allocation_key_id": keys["MEA"], "value": "100", "valid_from": "2020-01-01"},
            )
            contact_no += 1
            contact = _post(
                c,
                h,
                "/api/v1/contacts",
                {
                    "kind": "person",
                    "first_name": FIRST_NAMES[contact_no % len(FIRST_NAMES)],
                    "last_name": f"Beispiel{contact_no:03d}",
                },
            )
            party = _post(c, h, "/api/v1/parties", {"members": [{"contact_id": contact["id"]}]})
            _post(
                c,
                h,
                "/api/v1/contracts",
                {
                    "kind": "ownership",
                    "unit_id": unit["id"],
                    "party_id": party["id"],
                    "start_date": "2020-01-01",
                    "title_transfer_date": "2020-01-01",
                    "acquisition_kind": "first_acquisition",
                },
            )
            result["units"] += 1
        ledger = _post(
            c, h, f"{a}/ledgers", {"legal_entity_id": entity, "template_id": template["id"]}
        )["id"]
        numbers = {
            x["number"]: x["id"] for x in c.get(f"{a}/ledgers/{ledger}/accounts", headers=h).json()
        }
        for month in month_starts(end):
            amount = f"{Decimal(1500 + 40 * p_index + month.month * 10):.2f}"
            _post(
                c,
                h,
                f"{a}/ledgers/{ledger}/entries",
                {
                    "kind": "custom",
                    "booking_date": (month + timedelta(days=14)).isoformat(),
                    "text": f"Bewirtschaftungskosten {month.strftime('%m/%Y')} (Demo)",
                    "lines": [
                        {"account_id": numbers["043000"], "debit": amount},
                        {"account_id": numbers["001200"], "credit": amount},
                    ],
                },
            )
            result["entries"] += 1
        result["properties"].append(
            {"id": prop["id"], "bank_account_id": account["id"], "iban": TEST_IBANS[p_index]}
        )
    # Remaining contacts: service providers and further persons (60 in total).
    while contact_no < CONTACTS:
        contact_no += 1
        body: dict[str, Any] = (
            {"kind": "company", "company_name": f"{COMPANIES[contact_no % 3]} {contact_no:03d}"}
            if contact_no % 3 == 0
            else {
                "kind": "person",
                "first_name": FIRST_NAMES[contact_no % len(FIRST_NAMES)],
                "last_name": f"Beispiel{contact_no:03d}",
            }
        )
        _post(c, h, "/api/v1/contacts", body)
    result["contacts"] = contact_no
    return result


def build_statements(ibans: list[str], end: date, total: int = BANK_TRANSACTIONS) -> Any:
    """Deterministic CAMT-like statement data: ``total`` transactions over 12 months."""
    from mhvp.banking.camt import ParsedFile, RawStatement, RawTransaction

    months = month_starts(end)
    first, last = months[0], end
    per_account = [total // len(ibans) + (1 if i < total % len(ibans) else 0) for i in range(3)]
    statements = []
    counter = 0
    for a_index, iban in enumerate(ibans):
        rows: list[Any] = []
        span = (last - first).days
        for n in range(per_account[a_index]):
            counter += 1
            booked = first + timedelta(days=(n * span) // max(per_account[a_index] - 1, 1))
            credit = n % 4 != 3
            amount = Decimal(300 + (n % 5) * 25) if credit else -Decimal(80 + (n % 7) * 35)
            rows.append(
                RawTransaction(
                    bank_reference=f"DEMO-{counter:04d}",
                    booking_date=booked,
                    value_date=booked,
                    amount=amount.quantize(Decimal("0.01")),
                    currency="EUR",
                    counterpart_name=f"Max Beispiel {counter:03d}" if credit else "Muster Dienst",
                    counterpart_iban=synthetic_iban(counter),
                    counterpart_bic=None,
                    purpose=(
                        f"Hausgeld {booked.strftime('%m/%Y')} WE {n % 14 + 1:03d}"
                        if credit
                        else f"Rechnung Musterstraße {booked.strftime('%m/%Y')}"
                    ),
                    end_to_end_id=None,
                    mandate_reference=None,
                    creditor_id=None,
                    transaction_code=None,
                )
            )
        closing = sum((r.amount for r in rows), Decimal("0.00"))
        statements.append(
            RawStatement(
                statement_ref=f"DEMO-{a_index + 1}",
                iban=iban,
                currency="EUR",
                from_date=first,
                to_date=last,
                opening_balance=Decimal("0.00"),
                closing_balance=closing,
                closing_date=last,
                transactions=rows,
            )
        )
    return ParsedFile(version="demo", statements=statements)


async def run(client: ApiClient | None = None, today: date | None = None) -> int:
    settings = get_settings()
    configure_logging(settings)
    log = get_logger("mhvp.demo_seed")
    if settings.env not in ALLOWED_ENVIRONMENTS:
        log.error("demo_seed_refused", reason="environment", env=str(settings.env))
        return 2
    if os.environ.get("MHVP_DEMO_SEED", "").strip().lower() not in TRUE_VALUES:
        log.error("demo_seed_refused", reason="MHVP_DEMO_SEED=1 missing")
        return 2
    password = os.environ.get("MHVP_DEMO_ADMIN_PASSWORD")
    if not password:
        log.error("demo_seed_refused", reason="MHVP_DEMO_ADMIN_PASSWORD missing")
        return 2
    from mhvp.core import crypto
    from mhvp.platform import services

    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    from mhvp.workspace.services import local_today

    end = today or local_today()
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        tenant_id, created = await services.provision_tenant(
            factory, slug=DEMO_SLUG, name=DEMO_NAME
        )
        if not created:
            log.info("demo_seed_skipped", reason="tenant exists", tenant=DEMO_SLUG)
            return 0
        user_id = await services.create_user(
            factory, email=DEMO_ADMIN_EMAIL, display_name="Demo Admin", password=password
        )
        await services.add_member(
            factory,
            tenant_id=tenant_id,
            user_id=user_id,
            role_codes=["tenant_admin"],
            actor_user_id=None,
        )
        http: ApiClient
        owned: Any = None
        if client is not None:
            http = client
        else:
            import httpx

            owned = httpx.Client(
                base_url=os.environ.get("MHVP_DEMO_API_URL", "http://localhost:8000"), timeout=60
            )
            http = owned
        try:
            login = http.post(
                "/api/v1/auth/login", json={"email": DEMO_ADMIN_EMAIL, "password": password}
            )
            if login.status_code != 200 or login.json().get("status") != "ok":
                raise RuntimeError(f"Demo login failed: {login.status_code}")
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            seeded = seed_via_api(http, headers, end)
        finally:
            if owned is not None:
                owned.close()
        parsed = build_statements([p["iban"] for p in seeded["properties"]], end)
        from mhvp.banking import services as bank_services

        async with tenant_transaction(factory, tenant_id) as session:
            await bank_services.import_file(
                session, tenant_id=tenant_id, user_id=user_id, parsed=parsed, document_id=None
            )
        log.info(
            "demo_seeded",
            tenant=DEMO_SLUG,
            properties=len(seeded["properties"]),
            units=seeded["units"],
            contacts=seeded["contacts"],
            draft_entries=seeded["entries"],
            bank_transactions=BANK_TRANSACTIONS,
        )
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(asyncio.run(run()))
