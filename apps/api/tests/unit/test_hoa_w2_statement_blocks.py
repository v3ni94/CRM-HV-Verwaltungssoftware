"""M24-01, M24-03, M24-04, M24-07 (Lückenliste 30.09.2026): pure statement blocks with
hand computed expected values (rule 0.1.8).

Units 01 and 02: cost shares 3.000,00 / 2.500,00 (total costs 5.500,00), resolved advances
2.800,00 each, paid 2.500,00 each -> results +200,00 / -300,00, arrears 300,00 / 300,00.
Reserve Soll 3.000,00 each, paid 2.250,00 each -> reserve open 750,00 each."""

import uuid
from decimal import Decimal
from types import SimpleNamespace

from mhvp.hoa import calc, statement_pdf

U1, U2 = str(uuid.uuid4()), str(uuid.uuid4())


def _result() -> dict:
    unit = {
        "advances_resolved": "2800.00",
        "advances_paid": "2500.00",
        "arrears": "300.00",
        "reserve_due": "3000.00",
        "reserve_paid": "2250.00",
    }
    return {
        "total_costs": "5500.00",
        "positions": [
            {
                "label": "Versicherung",
                "amount": "5500.00",
                "basis": "GO",
                "split": {U1: "3000.00", U2: "2500.00"},
            }
        ],
        "units": [
            {
                "unit_id": U1,
                "unit_number": "01",
                "cost_share": "3000.00",
                "result": "200.00",
                **unit,
            },
            {
                "unit_id": U2,
                "unit_number": "02",
                "cost_share": "2500.00",
                "result": "-300.00",
                **unit,
            },
        ],
        "reserve": {
            "opening": "20000.00",
            "contributions_paid": "4500.00",
            "withdrawals": "3000.00",
            "interest": "100.00",
            "closing": "21600.00",
        },
    }


def test_key_figures_and_debtors() -> None:
    kf = calc.statement_key_figures(_result())
    assert kf["costs_distribution_relevant"] == "5500.00"
    assert kf["costs_distributed"] == "5500.00"
    assert kf["costs_not_distributed"] == "0.00"
    assert kf["advances_resolved"] == "5600.00"
    assert kf["advances_paid"] == "5000.00"
    assert kf["arrears"] == "600.00"
    assert kf["additional_payments"] == "200.00"
    assert kf["adjustments"] == "-300.00"
    assert [d["unit_number"] for d in kf["debtors"]] == ["01", "02"]
    assert kf["debtors"][0]["reserve_open"] == "750.00"


def test_reserve_positions_planned_development() -> None:
    r1 = SimpleNamespace(id=uuid.uuid4(), name="Dach", purpose="Dachsanierung", account_id=None)
    r2 = SimpleNamespace(id=uuid.uuid4(), name="Allgemein", purpose=None, account_id=None)
    items = [
        SimpleNamespace(amount=Decimal("4000.00"), reserve_id=r1.id),
        SimpleNamespace(amount=Decimal("2000.00"), reserve_id=r2.id),
        SimpleNamespace(amount=Decimal("1000.00"), reserve_id=None),
    ]
    moves = [
        SimpleNamespace(
            reserve_id=r1.id,
            kind="withdrawal",
            amount=Decimal("1500.00"),
            purpose="Rinne",
            document_id=uuid.uuid4(),
            journal_entry_id=None,
        ),
        SimpleNamespace(
            reserve_id=r1.id,
            kind="fee",
            amount=Decimal("10.00"),
            purpose="Kontogebühr",
            document_id=None,
            journal_entry_id=None,
        ),
        SimpleNamespace(
            reserve_id=r1.id,
            kind="interest",
            amount=Decimal("25.00"),
            purpose="Zins",
            document_id=None,
            journal_entry_id=None,
        ),
    ]
    dach, allg = calc.reserve_positions([r1, r2], items, moves)
    # 4.000,00 - 1.500,00 - 10,00 + 25,00 = 2.515,00
    assert dach["planned_change"] == "2515.00"
    assert [m["receipt_linked"] for m in dach["movements"]] == [True, False, False]
    assert allg["contributions_planned"] == "2000.00"
    assert allg["planned_change"] == "2000.00"


def test_plan_comparison_basis_amount_or_basis_plan() -> None:
    items = [
        SimpleNamespace(
            label="Versicherung", component="hoa_fee", amount=Decimal("5800.00"), basis_amount=None
        ),
        SimpleNamespace(
            label="Hausmeister",
            component="hoa_fee",
            amount=Decimal("3000.00"),
            basis_amount=Decimal("3200.00"),
        ),
        SimpleNamespace(
            label="Neu", component="reserve", amount=Decimal("100.00"), basis_amount=None
        ),
    ]
    basis = [SimpleNamespace(label="Versicherung", amount=Decimal("5500.00"))]
    rows = calc.plan_comparison(items, basis)
    assert [(r["basis_amount"], r["deviation"]) for r in rows] == [
        ("5500.00", "300.00"),
        ("3200.00", "-200.00"),
        (None, None),
    ]


def test_unit_pdf_rows_and_render() -> None:
    snap = _result()
    snap["section_35a"] = {"per_unit": {U1: "120.00"}}
    rows = statement_pdf.rows(snap, snap["units"][0])
    assert rows["positions"][0] == ["Versicherung", "GO", "5.500,00 EUR", "3.000,00 EUR"]
    assert rows["settlement"][2] == ["Abrechnungsspitze (Nachschuss)", "200,00 EUR"]
    assert rows["section_35a"][0][1] == "120,00 EUR"
    assert (
        statement_pdf.rows(snap, snap["units"][1])["settlement"][2][0] == "Anpassung der Vorschüsse"
    )
    pdf = statement_pdf.render(2025, snap, snap["units"][0], "abc123def456ghi")
    assert pdf.startswith(b"%PDF")
