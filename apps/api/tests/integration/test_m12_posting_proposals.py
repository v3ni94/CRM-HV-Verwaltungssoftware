"""M12-01 two stage posting proposal over the API: stage 1 (rule, match) always answers with
source, confidence and reasoning; the AI stage is blocked by default (tenant switch off) and
its proposals list stays empty; nothing is posted by reading proposals."""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _property, _unit
from tests.integration.test_m8_import import _settings
from tests.integration.test_m11_banking import _camt, _ntry, _upload
from tests.integration.test_m12_matching import (
    BANK,
    PAYERS,
    STRANGER,
    A,
    B,
    _ok,
    client,  # noqa: F401 - fixture
)

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    """Own tenant and users (distinct slug/emails from test_m12_matching's ``_world``):
    both modules import the ``world`` fixture as ``scope="module"``, which pytest caches
    per requesting module, so reusing test_m12_matching's slug/emails here would attempt
    to create the same tenant and users twice and fail with E-mail already registered."""
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"mtp-{RUN}", name=f"MatchProp {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("m12padmin", "tenant_admin"), ("m12pacc", "accountant_no_banking")]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


def _hoa_with_open_items(
    c: TestClient, h: dict[str, str], number: str = "722"
) -> tuple[str, list[dict[str, Any]]]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": "Vorschlaghaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    bank_id = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": BANK,
                "holder": "GdWE V",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    contracts = []
    for i, iban in enumerate(PAYERS[:2], start=1):
        contact = _ok(
            c.post(
                "/api/v1/contacts",
                json={
                    "kind": "person",
                    "first_name": f"Eig{i}",
                    "last_name": f"P{RUN}",
                    "bank_accounts": [{"iban": iban, "valid_from": "2020-01-01"}],
                },
                headers=h,
            ),
            201,
        )
        party = _ok(
            c.post("/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h),
            201,
        )
        unit = _unit(c, h, prop["id"], f"1{i}")
        contracts.append(
            _ok(
                c.post(
                    "/api/v1/contracts",
                    json={
                        "kind": "ownership",
                        "unit_id": unit,
                        "party_id": party["id"],
                        "start_date": "2020-01-01",
                        "title_transfer_date": "2020-01-01",
                        "acquisition_kind": "first_acquisition",
                    },
                    headers=h,
                ),
                201,
            )
        )
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    accounts = {a["number"]: a for a in _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
    _ok(
        c.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "001211",
                "name": "WEG-Bank",
                "category": "bank",
                "type": "asset",
                "property_bank_account_id": bank_id,
            },
            headers=h,
        ),
        201,
    )
    debtors = {a["unit_id"]: a["id"] for a in accounts.values() if a["category"] == "debtor"}
    for contract, amount in zip(contracts, ["250.00", "250.00"], strict=True):
        draft = _ok(
            c.post(
                f"{A}/ledgers/{ledger}/entries",
                json={
                    "kind": "receivable",
                    "booking_date": "2026-01-01",
                    "text": "Hausgeld Januar",
                    "contract_id": contract["id"],
                    "lines": [
                        {"account_id": debtors[contract["unit_id"]], "debit": amount},
                        {"account_id": accounts["060100"]["id"], "credit": amount},
                    ],
                },
                headers=h,
            ),
            201,
        )
        _ok(c.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    return hoa, contracts


def test_two_stage_posting_proposals(client: TestClient, world: World) -> None:  # noqa: F811
    h = bearer(login(client, world, "m12padmin"))
    hoa, contracts = _hoa_with_open_items(client, h)
    n1 = contracts[0]["number"]
    statement = _camt(
        "P-1",
        BANK,
        "0.00",
        "600.00",
        [
            _ntry("P1", "250.00", "CRDT", "2026-01-05", PAYERS[0], f"Hausgeld {n1}"),
            _ntry("P2", "250.00", "CRDT", "2026-01-05", PAYERS[1], "Ueberweisung"),
            _ntry("P3", "100.00", "CRDT", "2026-01-06", STRANGER, "Spende"),
        ],
    )
    _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "p.xml", statement)}, headers=h
        ),
        201,
    )
    txs = {t["bank_reference"]: t for t in _ok(client.get(f"{B}/transactions", headers=h))}

    def proposals(ref: str) -> Any:
        return _ok(client.get(f"{B}/transactions/{txs[ref]['id']}/posting-proposals", headers=h))

    p1 = proposals("P1")
    assert p1["ai_stage"]["enabled"] is False
    assert "ai_posting_enabled" in p1["ai_stage"]["blocked_reason"]
    assert p1["ai"] == []
    (match,) = p1["stage1"]
    assert (match["source"], match["kind"], match["unambiguous"], match["postable"]) == (
        "match",
        "full",
        True,
        False,
    )
    assert match["confidence"] >= 0.5
    assert "Vertragsnummer im Verwendungszweck" in match["reasoning"]
    assert "IBAN des Zahlers beim Vertragspartner hinterlegt" in match["reasoning"]

    (weak,) = proposals("P2")["stage1"]
    assert (weak["kind"], weak["unambiguous"]) == ("weak", False)  # IBAN and amount are no proof
    (unclear,) = proposals("P3")["stage1"]
    assert unclear["kind"] == "unclear"
    assert unclear["confidence"] == 0.0

    # An approved (not yet active) rule appears as source "rule" with lower confidence.
    acc_user = bearer(login(client, world, "m12pacc"))
    rule = _ok(
        client.post(
            f"{B}/rules",
            json={"name": "Hausgeld", "legal_entity_id": hoa, "purpose_regex": "Hausgeld"},
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{B}/rules/{rule['id']}/approve", headers=acc_user))
    stage1 = proposals("P1")["stage1"]
    assert [p["source"] for p in stage1] == ["rule", "match"]
    assert stage1[0]["rule_id"] == rule["id"]
    assert stage1[0]["confidence"] == 0.6
    assert stage1[0]["splits"] == [match["splits"][0]]

    # Reading proposals posts nothing.
    assert _ok(client.get(f"{B}/transactions", params={"status": "booked"}, headers=h)) == []
    assert (
        client.get(
            f"{B}/transactions/00000000-0000-7000-8000-000000000000/posting-proposals", headers=h
        ).status_code
        == 404
    )


def _tenancy_with_open_item(
    c: TestClient, h: dict[str, str], number: str, iban: str, amount: str = "250.00"
) -> tuple[dict[str, Any], str]:
    """A rental contract (tenancy) with an open receivable of ``amount`` on its own ledger.
    Deposits (Kaution) are only allowed on tenancy contracts (4.5, ``check_deposit_account``)."""
    prop = _property(c, h, number, "rental")
    owner, _ = _party(c, h, f"Verm{number}", "company")
    entity = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]
    bank_id = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": entity,
                "kind": "rent",
                "iban": iban,
                "holder": "Vermieter V",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    tenant, _contact = _party(c, h, f"Mieter{number}", iban=PAYERS[0])
    unit = _unit(c, h, prop["id"], "01")
    contract = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant,
                "start_date": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers",
            json={"legal_entity_id": entity, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )["id"]
    accounts = {a["number"]: a for a in _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
    _ok(
        c.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "001211",
                "name": "Mietkonto",
                "category": "bank",
                "type": "asset",
                "property_bank_account_id": bank_id,
            },
            headers=h,
        ),
        201,
    )
    debtor = next(
        a["id"] for a in accounts.values() if a["category"] == "debtor" and a["unit_id"] == unit
    )
    draft = _ok(
        c.post(
            f"{A}/ledgers/{ledger}/entries",
            json={
                "kind": "receivable",
                "booking_date": "2026-01-01",
                "text": "Kaution",
                "contract_id": contract["id"],
                "lines": [
                    {"account_id": debtor, "debit": amount},
                    {"account_id": accounts["060300"]["id"], "credit": amount},
                ],
            },
            headers=h,
        ),
        201,
    )
    _ok(c.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    return contract, contract["number"]


def test_deposit_derivation_from_contract_deposit(client: TestClient, world: World) -> None:  # noqa: F811
    """OpenItem carries no Forderungsart distinguishing a deposit demand (M12-01 remainder,
    operator 22.09.2026 Kontierungsagent finding); ``is_deposit`` is derived instead over the
    contract's own open ``Deposit`` (mhvp.contracts.models.Deposit) of the same amount."""
    h = bearer(login(client, world, "m12padmin"))
    bank1 = "DE23120300000000202061"
    contract, n1 = _tenancy_with_open_item(client, h, "801", bank1)
    _ok(
        client.post(
            f"/api/v1/contracts/{contract['id']}/deposits",
            json={"kind": "cash", "amount_due": "250.00", "valid_from": "2026-01-01"},
            headers=h,
        ),
        201,
    )
    statement = _camt(
        "P-2",
        bank1,
        "0.00",
        "250.00",
        [_ntry("D1", "250.00", "CRDT", "2026-01-05", PAYERS[0], f"Kaution {n1}")],
    )
    _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "d.xml", statement)}, headers=h
        ),
        201,
    )
    tx = next(
        t for t in _ok(client.get(f"{B}/transactions", headers=h)) if t["bank_reference"] == "D1"
    )
    proposal = _ok(client.get(f"{B}/transactions/{tx['id']}/posting-proposals", headers=h))
    (match,) = proposal["stage1"]
    assert match["kind"] == "deposit"
    assert match["splits"][0]["amount"] == "250.00"

    # A second tenancy with the same due amount but no deposit demand: the purpose still names
    # a Kaution, but nothing has ``is_deposit`` true, so the amount stays an unmatched hint.
    bank2 = "DE93120300000000202062"
    _contract2, n2 = _tenancy_with_open_item(client, h, "802", bank2)
    statement2 = _camt(
        "P-3",
        bank2,
        "0.00",
        "250.00",
        [_ntry("D2", "250.00", "CRDT", "2026-01-06", PAYERS[0], f"Kaution {n2}")],
    )
    _ok(
        client.post(
            f"{B}/imports",
            json={"document_id": _upload(client, h, "d2.xml", statement2)},
            headers=h,
        ),
        201,
    )
    tx2 = next(
        t for t in _ok(client.get(f"{B}/transactions", headers=h)) if t["bank_reference"] == "D2"
    )
    proposal2 = _ok(client.get(f"{B}/transactions/{tx2['id']}/posting-proposals", headers=h))
    (unmatched,) = proposal2["stage1"]
    assert unmatched["kind"] == "deposit"
    assert unmatched["confidence"] == 0.3
    assert unmatched["splits"] == []
