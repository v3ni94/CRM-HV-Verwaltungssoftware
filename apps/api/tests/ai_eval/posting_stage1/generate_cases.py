"""Generator of the independent stage 1 test set (M12-02): 200 synthetic bank transactions
with expected postings, written by class. Deterministic (seeded), no real data. Run with
``python -m tests.ai_eval.posting_stage1.generate_cases`` from ``apps/api``; the JSON is
committed so the expectations stay fixed and reviewable."""

from __future__ import annotations

import json
import random
from decimal import Decimal
from pathlib import Path
from typing import Any

OUT = Path(__file__).with_name("cases.json")
FP = [f"fp-{i:03d}" for i in range(1, 60)]  # payer IBAN fingerprints on file
STRANGER = "fp-stranger"
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September"]
CREDITORS = ["Stadtwerke", "Gebäudereinigung Nord", "Aufzugtechnik Meyer", "Gärtnerei Grün"]


def _item(
    n: int,
    remaining: str,
    *,
    contract: str,
    fp: str,
    mandate: str | None = None,
    debtor: str | None = None,
    due: str = "2026-03-01",
    account: str | None = None,
    deposit: bool = False,
) -> dict[str, Any]:
    return {
        "id": f"oi-{n}",
        "kind": "receivable",
        "remaining": remaining,
        "due_date": due,
        "reference": None,
        "contract_number": contract,
        "mandate_reference": mandate,
        "party_iban_fingerprints": [fp],
        "account_number": account or f"1{n:04d}",
        "debtor_key": debtor or f"d-{n}",
        "is_deposit": deposit,
    }


def _payable(n: int, remaining: str, number: str, fp: str) -> dict[str, Any]:
    return {
        "id": f"inv-{n}",
        "remaining": remaining,
        "number": number,
        "payee_iban_fingerprint": fp,
        "account_number": f"6{n:04d}",
    }


def _tx(amount: str, purpose: str | None, fp: str, **extra: Any) -> dict[str, Any]:
    return {
        "amount": amount,
        "purpose": purpose,
        "counterpart_name": extra.pop("name", "Zahler"),
        "counterpart_iban_fingerprint": fp,
        "mandate_reference": extra.pop("mandate", None),
        "end_to_end_id": None,
        "transaction_code": extra.pop("code", None),
    }


def _case(
    cid: str, cls: str, tx: dict[str, Any], expected: dict[str, Any], **data: Any
) -> dict[str, Any]:
    return {
        "id": cid,
        "class": cls,
        "tx": tx,
        "rules": data.get("rules", []),
        "open_items": data.get("open_items", []),
        "payables": data.get("payables", []),
        "expected": expected,
    }


def _exp(source: str, kind: str, ids: list[str] | None = None, **more: Any) -> dict[str, Any]:
    return {"source": source, "kind": kind, "open_item_ids": ids or [], **more}


def build() -> list[dict[str, Any]]:
    rng = random.Random(20260927)  # noqa: S311 - synthetic test data
    cases: list[dict[str, Any]] = []
    purpose: str | None

    def amt(lo: int, hi: int) -> str:
        return str(Decimal(rng.randint(lo * 100, hi * 100)) / 100)

    # 32 rent payments with a usable purpose (contract number, month)
    for i in range(32):
        c = f"MV-{1000 + i}"
        a = amt(400, 1400)
        fp = FP[i % len(FP)]
        month = MONTHS[i % len(MONTHS)]
        items = [
            _item(1, a, contract=c, fp=fp, due=f"2026-0{(i % 9) + 1}-01"),
            _item(2, amt(400, 1400), contract=f"MV-{2000 + i}", fp=FP[(i + 7) % len(FP)]),
        ]
        purpose = rng.choice([f"Miete {month} {c}", f"{c} Miete {month} 2026", f"Miete {c}"])
        cases.append(
            _case(
                f"miete-zweck-{i:02d}",
                "rent_with_purpose",
                _tx(a, purpose, fp),
                _exp("match", "full", ["oi-1"], unambiguous=True),
                open_items=items,
            )
        )

    # 30 rent payments without purpose: 15 with mandate reference (full), 15 IBAN+amount only (weak)
    for i in range(30):
        c = f"MV-{3000 + i}"
        a = amt(300, 1200)
        fp = FP[(i + 11) % len(FP)]
        mandate = f"MREF-{i:04d}" if i < 15 else None
        items = [
            _item(1, a, contract=c, fp=fp, mandate=mandate),
            _item(2, amt(300, 1200), contract=f"MV-{4000 + i}", fp=FP[(i + 23) % len(FP)]),
        ]
        tx = _tx(a, rng.choice([None, "", "Ueberweisung", "Dauerauftrag"]), fp, mandate=mandate)
        expected = (
            _exp("match", "full", ["oi-1"], unambiguous=True)
            if mandate
            else _exp("match", "weak", ["oi-1"])
        )
        cases.append(
            _case(
                f"miete-ohne-zweck-{i:02d}", "rent_without_purpose", tx, expected, open_items=items
            )
        )

    # 25 partial payments
    for i in range(25):
        c = f"MV-{5000 + i}"
        full = Decimal(amt(600, 1500))
        part = (full * Decimal(rng.choice(["0.5", "0.25", "0.8"]))).quantize(Decimal("0.01"))
        fp = FP[(i + 31) % len(FP)]
        items = [
            _item(1, str(full), contract=c, fp=fp),
            _item(2, amt(300, 900), contract=f"MV-{6000 + i}", fp=FP[(i + 5) % len(FP)]),
        ]
        payer = fp if i % 3 else STRANGER  # every third from a third party account
        cases.append(
            _case(
                f"teilzahlung-{i:02d}",
                "partial",
                _tx(str(part), f"Teilzahlung Miete {c}", payer),
                _exp("match", "partial", ["oi-1"]),
                open_items=items,
            )
        )

    # 25 collective transfers: two or three open items of one debtor, sum equals the payment
    for i in range(25):
        c = f"MV-{7000 + i}"
        fp = FP[(i + 41) % len(FP)]
        n = 2 if i % 2 else 3
        parts = [Decimal(amt(200, 900)) for _ in range(n)]
        items = [
            _item(k + 1, str(parts[k]), contract=c, fp=fp, debtor="d-x", due=f"2026-0{k + 1}-01")
            for k in range(n)
        ]
        items.append(_item(9, amt(100, 999), contract=f"MV-{8000 + i}", fp=FP[(i + 3) % len(FP)]))
        purpose = f"Miete {' '.join(MONTHS[:n])} {c}" if i % 3 else f"{c} Nachzahlung"
        cases.append(
            _case(
                f"sammel-{i:02d}",
                "collective",
                _tx(str(sum(parts)), purpose, fp),
                _exp("match", "collective", [f"oi-{k + 1}" for k in range(n)]),
                open_items=items,
            )
        )

    # 15 returns (direct debit returns, chargebacks)
    for i in range(15):
        a = "-" + amt(200, 1100)
        purpose, code = rng.choice(
            [
                ("Rücklastschrift MV-9001 Miete", None),
                ("RETOURE SEPA LASTSCHRIFT", None),
                ("Miete MV-9002", "RTRN"),
                ("Rückgabe Lastschrift Kontonummer falsch", None),
                ("Storno Zahlung", None),
            ]
        )
        items = [_item(1, amt(200, 1100), contract="MV-9001", fp=FP[i])]
        cases.append(
            _case(
                f"ruecklaeufer-{i:02d}",
                "return",
                _tx(a, purpose, FP[i], code=code),
                _exp("match", "return"),
                open_items=items,
            )
        )

    # 25 supplier invoices (outgoing): 15 with invoice number, 10 IBAN plus amount only
    for i in range(25):
        number = f"RE-2026-{100 + i}"
        a = amt(50, 3000)
        fp = f"cred-{i}"
        payables = [
            _payable(1, a, number, fp),
            _payable(2, amt(50, 3000), f"RE-2026-{300 + i}", f"cred-{i + 50}"),
        ]
        if i < 15:
            purpose = rng.choice(
                [
                    f"{number} {CREDITORS[i % 4]}",
                    f"Rechnung {number}",
                    f"Zahlung {number} Objekt 12",
                ]
            )
            expected = _exp("match", "invoice", ["inv-1"], unambiguous=True)
        else:
            purpose = rng.choice([f"{CREDITORS[i % 4]} Abschlag", "Rechnung", None])
            expected = _exp("match", "weak", ["inv-1"])
        cases.append(
            _case(
                f"rechnung-{i:02d}",
                "invoice",
                _tx("-" + a, purpose, fp, name=CREDITORS[i % 4]),
                expected,
                payables=payables,
            )
        )

    # 15 deposits: 10 matching a deposit claim, 5 without one (review)
    for i in range(15):
        a = amt(1000, 3000)
        fp = FP[(i + 17) % len(FP)]
        c = f"MV-{9100 + i}"
        items = [_item(1, amt(400, 1200), contract=c, fp=fp)]
        if i < 10:
            items.append(_item(2, a, contract=c, fp=fp, account="1700", deposit=True))
            expected = _exp("match", "deposit", ["oi-2"])
        else:
            expected = _exp("match", "deposit")
        cases.append(
            _case(
                f"kaution-{i:02d}",
                "deposit",
                _tx(a, f"Mietkaution {c}", fp),
                expected,
                open_items=items,
            )
        )

    # 25 unclear cases
    for i in range(25):
        variant = i % 5
        fp = FP[(i + 29) % len(FP)]
        if variant == 0:  # stranger, no hint at all
            items = [_item(1, amt(100, 900), contract="MV-1", fp=FP[0])]
            tx = _tx(amt(100, 900), "Ueberweisung", STRANGER)
        elif variant == 1:  # purpose names two contracts, amounts do not add up
            items = [
                _item(1, "500.00", contract="MV-21", fp=fp),
                _item(2, "500.00", contract="MV-22", fp=fp),
            ]
            tx = _tx("700.00", "Miete MV-21 und MV-22", fp)
        elif variant == 2:  # same IBAN, two debtors, same amount, no purpose
            items = [
                _item(1, "650.00", contract="MV-31", fp=fp, debtor="a"),
                _item(2, "650.00", contract="MV-32", fp=fp, debtor="b"),
            ]
            tx = _tx("650.00", None, fp)
        elif variant == 3:  # amount matches nothing, weak IBAN only, several items
            items = [
                _item(1, "400.00", contract="MV-41", fp=fp),
                _item(2, "410.00", contract="MV-42", fp=fp),
            ]
            tx = _tx("123.45", "Gutschrift", fp)
        else:  # outgoing without any open payable
            items = []
            tx = _tx("-" + amt(10, 500), "Gebühren", STRANGER)
        cases.append(
            _case(f"unklar-{i:02d}", "unclear", tx, _exp("match", "unclear"), open_items=items)
        )

    # 8 hits of an active bank rule
    rule = {
        "id": "rule-1",
        "name": "Hausgeld Objekt 12",
        "match": {"purpose_regex": "Hausgeld"},
        "action": {"kind": "debtor_payment", "account_number": "1400"},
        "priority": 10,
        "approval_state": "active",
        "max_amount": "2000.00",
    }
    for i in range(8):
        a = amt(150, 600)
        items = [_item(1, a, contract=f"WE-{i}", fp=FP[i])]
        cases.append(
            _case(
                f"regel-{i:02d}",
                "rule",
                _tx(a, f"Hausgeld WE-{i}", FP[i]),
                _exp("rule", "debtor_payment", ["oi-1"], rule_id="rule-1"),
                rules=[rule],
                open_items=items,
            )
        )
    assert len(cases) == 200, len(cases)
    assert len({c["id"] for c in cases}) == 200
    return cases


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"{len(build())} cases -> {OUT}")  # noqa: T201
