"""Synthetic load data seed (S16-08): units and bank accounts through the public API.

No real data: names, numbers and IBANs are generated. IBANs carry a valid check digit
(ISO 13616 mod 97) for the fictitious bank code 10000000, so the API validation accepts them.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

UNITS = 100
ACCOUNTS = 100


def synthetic_iban(index: int) -> str:
    """DE IBAN with bank code 10000000 and a generated account number, valid check digits."""
    bban = f"10000000{index:010d}"
    check = 98 - int(bban + "131400") % 97  # "DE" -> 1314, digits "00" as placeholder
    return f"DE{check:02d}{bban}"


def _post(c: TestClient, h: dict[str, str], url: str, body: dict[str, Any]) -> dict[str, Any]:
    response = c.post(url, json=body, headers=h)
    assert response.status_code == 201, response.text
    return dict(response.json())


def seed_units(c: TestClient, h: dict[str, str], count: int = UNITS) -> str:
    """One WEG property with ``count`` units; returns the property id."""
    prop = _post(
        c,
        h,
        "/api/v1/properties",
        {"number": "901", "name": "Lastobjekt WEG", "management_type": "hoa"},
    )
    building = _post(c, h, f"/api/v1/properties/{prop['id']}/buildings", {"name": "Haus"})
    for n in range(1, count + 1):
        _post(
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
    return str(prop["id"])


def seed_bank_accounts(
    c: TestClient, h: dict[str, str], count: int = ACCOUNTS, start: int = 0
) -> list[str]:
    """``count`` HOA properties with one bank account each; returns the account ids."""
    ids: list[str] = []
    for n in range(start, start + count):
        prop = _post(
            c,
            h,
            "/api/v1/properties",
            {"number": f"{100 + n}", "name": f"Lastkonto {n:03d}", "management_type": "hoa"},
        )
        entity = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
        account = _post(
            c,
            h,
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            {
                "legal_entity_id": entity,
                "kind": "hoa",
                "iban": synthetic_iban(n),
                "holder": f"GdWE Last {n:03d}",
                "valid_from": "2020-01-01",
            },
        )
        ids.append(str(account["id"]))
    return ids


def seed_statement_data(
    c: TestClient, h: dict[str, str], count: int = UNITS, cost: str = "10000.00"
) -> dict[str, Any]:
    """Statement base data (S16-08): a WEG with ``count`` owned units (MEA 100 each), a ledger,
    one posted cost payment and a draft statement for 2025 with one cost position. Returns the
    statement id; the measurement then covers ``calculate`` only."""
    from tests.integration.test_m24_hoa import _book_cost, _owner

    accounting, hoa_api = "/api/v1/accounting", "/api/v1/hoa"
    prop = _post(
        c,
        h,
        "/api/v1/properties",
        {"number": "902", "name": "Lastobjekt Abrechnung", "management_type": "hoa"},
    )
    entity = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    keys = {
        k["code"]: k["id"]
        for k in c.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h).json()
    }
    for n in range(1, count + 1):
        _owner(c, h, prop["id"], f"{n:03d}", "100", keys["MEA"], {"hoa_fee": "300.00"})
    template = _post(c, h, f"{accounting}/templates/default", {})
    ledger = _post(
        c,
        h,
        f"{accounting}/ledgers",
        {"legal_entity_id": entity, "template_id": template["id"]},
    )["id"]
    accounts = {
        a["number"]: a["id"]
        for a in c.get(f"{accounting}/ledgers/{ledger}/accounts", headers=h).json()
    }
    _book_cost(c, h, ledger, accounts["001200"], accounts["043000"], cost, "2025-03-01")
    statement = _post(
        c,
        h,
        f"{hoa_api}/statements",
        {
            "ledger_id": ledger,
            "year": 2025,
            "reserve_opening": "0.00",
            "reserve_withdrawals": "0.00",
            "reserve_interest": "0.00",
        },
    )
    _post(
        c,
        h,
        f"{hoa_api}/statements/{statement['id']}/costs",
        {
            "label": "Bewirtschaftungskosten",
            "amount": cost,
            "allocation_key_id": keys["MEA"],
            "basis": "Lastdaten, Verteilung nach MEA",
            "account_id": accounts["043000"],
        },
    )
    return {"statement_id": statement["id"], "units": count, "ledger": ledger}


ROWS_LARGE = 100_000
_YEARS = 5  # booking dates 2022 to 2026, one fifth of the rows per year


def _sync_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def seed_journal_entries(
    app_url: str,
    migrator_url: str,
    tenant_id: str,
    ledger_id: str,
    debit_account: str,
    credit_account: str,
    count: int = ROWS_LARGE,
) -> None:
    """GA12-08: ``count`` posted two line entries in one ledger, set based in one transaction
    as the application role (RLS applies). Entries are inserted as posted with numbers per
    fiscal year; equal amounts per line pair so each entry balances.

    The line guard trigger ``journal_line_guard`` looks the entry up with
    ``COALESCE(NEW.journal_entry_id, OLD.journal_entry_id)``, which is not an index condition
    (measured: 3.4 ms per line at 20,000 entries, growing linearly with the table; ADR 0021).
    A bulk load of 200,000 lines is therefore impossible with the guard active. The seed
    disables only this trigger on the test database for the duration of the load (owner role,
    re-enabled in ``finally``); lines are constructed to satisfy what the guard checks (entry
    still a draft, account of the entry's ledger). Never use this on a productive database."""
    import psycopg

    with psycopg.connect(_sync_url(migrator_url), autocommit=True) as owner:
        owner.execute("ALTER TABLE journal_line DISABLE TRIGGER journal_line_guard")
        try:
            _load_journal(app_url, tenant_id, ledger_id, debit_account, credit_account, count)
        finally:
            owner.execute("ALTER TABLE journal_line ENABLE TRIGGER journal_line_guard")


def _load_journal(
    app_url: str,
    tenant_id: str,
    ledger_id: str,
    debit_account: str,
    credit_account: str,
    count: int,
) -> None:
    import psycopg

    with psycopg.connect(_sync_url(app_url)) as conn, conn.cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
        # Deterministic ids from the row counter (the application role may not create temp
        # tables); a second call for the same ledger would collide, which is intended.
        # Entries are inserted as posted right away (number per fiscal year, no later UPDATE);
        # the lines follow while the line guard is disabled. The deferred balance trigger still
        # checks every entry at commit.
        ids = (
            "(SELECT g, md5('perf-entry-' || %s || '-' || g)::uuid AS id, "
            "DATE '2022-01-01' + (g * 7 %% (365 * %s)) AS booking_date, "
            "EXTRACT(year FROM DATE '2022-01-01' + (g * 7 %% (365 * %s)))::int AS fy, "
            "row_number() OVER (PARTITION BY EXTRACT(year FROM DATE '2022-01-01' + "
            "(g * 7 %% (365 * %s))) ORDER BY g)::int AS rn "
            "FROM generate_series(1, %s) g) perf_ids"
        )
        id_args = (ledger_id, _YEARS, _YEARS, _YEARS, count)
        cur.execute(
            "INSERT INTO journal_entry (id, tenant_id, ledger_id, status, fiscal_year, number, "
            "booking_date, text, kind, source, settlement_plan, posted_at) "
            "SELECT id, %s, %s, 'posted', fy, rn, booking_date, 'Lastbuchung ' || g, 'custom', "
            "'manual', '[]'::jsonb, now() FROM " + ids,
            (tenant_id, ledger_id, *id_args),
        )
        for line_no, (account, side) in enumerate(
            ((debit_account, "debit"), (credit_account, "credit")), start=1
        ):
            other = "credit" if side == "debit" else "debit"
            cur.execute(
                "INSERT INTO journal_line (id, tenant_id, journal_entry_id, line_no, "
                f"account_id, {side}, {other}) SELECT gen_random_uuid(), %s, id, %s, %s, "
                "(10 + g %% 90)::numeric(14,2), 0 FROM " + ids,
                (tenant_id, line_no, account, *id_args),
            )
        conn.commit()


def seed_bank_transactions(
    app_url: str, tenant_id: str, account_id: str, count: int = ROWS_LARGE
) -> None:
    """GA12-08: ``count`` synthetic bank transactions of one account (RLS applies)."""
    import psycopg

    with psycopg.connect(_sync_url(app_url)) as conn, conn.cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
        cur.execute(
            "SELECT legal_entity_id FROM property_bank_account WHERE id = %s", (account_id,)
        )
        entity = cur.fetchone()
        assert entity is not None
        cur.execute(
            "INSERT INTO bank_transaction (id, tenant_id, property_bank_account_id, "
            "legal_entity_id, bank_reference, booking_date, amount, currency, counterpart_name, "
            "purpose, hash, raw, status, attempt) "
            "SELECT gen_random_uuid(), %s, %s, %s, 'LAST' || g, "
            "DATE '2022-01-01' + (g * 7 %% (365 * %s)), "
            "(CASE WHEN g %% 3 = 0 THEN -1 ELSE 1 END) * (10 + g %% 990)::numeric(14,2), 'EUR', "
            "'Gegenpartei ' || (g %% 500), 'Lastumsatz ' || g, md5(g::text), '{}'::jsonb, "
            "(CASE WHEN g %% 10 = 0 THEN 'new' ELSE 'booked' END)::bank_transaction_status, 0 "
            "FROM generate_series(1, %s) g",
            (tenant_id, account_id, entity[0], _YEARS, count),
        )
        conn.commit()
