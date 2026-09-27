"""Owner statement (rental and SEV) as a PDF draft on the tenant's letterhead (M17-05, A06).

Output per property for the owner with the blocks income, expenses, management fee and the
payout amount, all read from the stored snapshot of :mod:`mhvp.billing.owner_statement`
(nothing is recalculated). The payout amount is derived here as a pure function:

    payout = income total - expenses total - management fee (gross) - payouts already made

A negative payout is shown as a shortfall of the owner ("Nachschuss"), never as a claim: the
amount is an accounting figure of the period and no payment instruction (G2); free liquidity
and deposits are named apart (A06). The PDF uses the letter blocks of
``mhvp.documents.letters`` (DIN 5008) and is marked as a draft; issuing needs G3.
"""

import html
from datetime import date
from decimal import Decimal
from typing import Any

from mhvp.billing.letters import fmt_date, fmt_eur
from mhvp.billing.owner_statement import OwnerStatement, OwnerStatementKind
from mhvp.documents import letters

DRAFT_LABEL = "Entwurf, kein Versand"
ZERO = Decimal("0.00")


def _d(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def settlement(results: dict[str, Any]) -> dict[str, Any]:
    """Payout block from the snapshot results (hand computable, rule 0.1.8).

    Example: income 12.000,00, expenses 3.000,00, fee gross 357,00, payouts made 6.000,00
    -> operating result 8.643,00, payout amount 2.643,00.
    """
    income = _d(results["income"]["total"])
    expenses = _d(results["expenses"]["total"])
    fee = _d(results["admin_fee"]["gross"])
    paid_out = _d(results["payouts"]["total"])
    operating_result = income - expenses - fee
    payout = operating_result - paid_out
    return {
        "income": str(income),
        "expenses": str(expenses),
        "admin_fee_gross": str(fee),
        "operating_result": str(operating_result),
        "payouts_made": str(paid_out),
        "payout_amount": str(payout),
        "kind": "auszahlung" if payout > 0 else ("nachschuss" if payout < 0 else "ausgeglichen"),
        "free_liquidity": str(_d(results["liquidity"]["free"])),
        "formula": "Einnahmen minus Ausgaben minus Verwaltervergütung (brutto) minus bereits "
        "geleistete Auszahlungen; kein Zahlungsauftrag (Entwurf, G2/G3).",
    }


def _rows(lines: list[dict[str, Any]], key: str = "account_number") -> list[list[str]]:
    return [
        [
            f"{line.get(key, '')} {line.get('account_name', line.get('name', ''))}".strip(),
            fmt_eur(_d(line["amount"])),
        ]
        for line in lines
    ]


def build_letter(
    st: OwnerStatement,
    *,
    recipient_lines: list[str],
    property_line: str,
    letter_date: date,
    signatory: list[str],
) -> letters.Letter:
    results = (st.snapshot or {}).get("results") or {}
    block = settlement(results)
    kind = (
        "Eigentümerabrechnung Sondereigentumsverwaltung"
        if (st.kind is OwnerStatementKind.SEV_OWNER)
        else "Eigentümerabrechnung Mietverwaltung"
    )
    subject = f"{kind} {property_line}, {fmt_date(st.period_from)} bis {fmt_date(st.period_to)}"
    tables = {
        "einnahmen": letters.LetterTable(
            header=["Einnahmen", "Betrag"],
            rows=[
                ["Mieten", fmt_eur(_d(results["income"]["rent"]))],
                ["Vorauszahlungen", fmt_eur(_d(results["income"]["advances"]))],
                ["Sonstige Erträge", fmt_eur(_d(results["income"]["other"]))],
                ["Summe Einnahmen", fmt_eur(_d(results["income"]["total"]))],
            ],
            right_aligned=(1,),
            total_row=True,
            widths=(0.7, 0.3),
        ),
        "ausgaben": letters.LetterTable(
            header=["Ausgaben", "Betrag"],
            rows=[
                *_rows(results["expenses"]["lines"]),
                ["Summe Ausgaben", fmt_eur(_d(results["expenses"]["total"]))],
            ],
            right_aligned=(1,),
            total_row=True,
            widths=(0.7, 0.3),
        ),
        "verguetung": letters.LetterTable(
            header=["Verwaltervergütung", "Betrag"],
            rows=[
                ["Netto", fmt_eur(_d(results["admin_fee"]["net"]))],
                ["Umsatzsteuer", fmt_eur(_d(results["admin_fee"]["vat"]))],
                ["Brutto", fmt_eur(_d(results["admin_fee"]["gross"]))],
            ],
            right_aligned=(1,),
            total_row=True,
            widths=(0.7, 0.3),
        ),
        "auszahlung": letters.LetterTable(
            header=["Ermittlung des Auszahlungsbetrags", "Betrag"],
            rows=[
                ["Einnahmen", fmt_eur(_d(block["income"]))],
                ["abzüglich Ausgaben", fmt_eur(-_d(block["expenses"]))],
                ["abzüglich Verwaltervergütung (brutto)", fmt_eur(-_d(block["admin_fee_gross"]))],
                ["Betriebsergebnis", fmt_eur(_d(block["operating_result"]))],
                ["abzüglich bereits geleisteter Auszahlungen", fmt_eur(-_d(block["payouts_made"]))],
                [
                    "Auszahlungsbetrag"
                    if block["kind"] != "nachschuss"
                    else "Nachschuss des Eigentümers",
                    fmt_eur(abs(_d(block["payout_amount"]))),
                ],
            ],
            right_aligned=(1,),
            total_row=True,
            widths=(0.7, 0.3),
        ),
    }
    paragraphs = [
        "Sehr geehrte Damen und Herren,",
        f"für das Objekt {property_line} erhalten Sie die Abrechnung für den Zeitraum "
        f"{fmt_date(st.period_from)} bis {fmt_date(st.period_to)}. Grundlage sind die "
        "gebuchten Belege des Buchungskreises; Kautionen sind Fremdgeld und nicht enthalten.",
        letters.TABLE_MARKER.format(name="einnahmen"),
        letters.TABLE_MARKER.format(name="ausgaben"),
        letters.TABLE_MARKER.format(name="verguetung"),
        letters.TABLE_MARKER.format(name="auszahlung"),
        f"Freie Liquidität zum {fmt_date(st.period_to)}: {fmt_eur(_d(block['free_liquidity']))} "
        "(Bank abzüglich Kautionen und offener Verbindlichkeiten). Der Auszahlungsbetrag ist "
        "ein Rechenergebnis der Abrechnung und kein Zahlungsauftrag.",
    ]
    if "sev_reconciliation" in results:
        sev = results["sev_reconciliation"]
        paragraphs.append(
            "Überleitung aus der WEG-Einzelabrechnung: Kostenanteil laut WEG "
            f"{fmt_eur(_d(sev['hoa_cost_share']))}, Hausgeld-Soll "
            f"{fmt_eur(_d(sev['hausgeld_resolved']))}, Abrechnungsspitze "
            f"{fmt_eur(_d(sev['hoa_result']))}, auf Mieter umgelegt "
            f"{fmt_eur(_d(sev['tenant_allocable_costs']))}, Eigentümerbelastung "
            f"{fmt_eur(_d(sev['owner_burden']))}."
        )
    paragraphs.append(
        "Dieses Schreiben ist ein Entwurf; die Ausgabe erfolgt nach Prüfung und Freigabe."
    )
    return letters.Letter(
        recipient_lines=recipient_lines,
        subject=subject,
        body="\n\n".join(p if p.startswith("[[table:") else html.escape(p) for p in paragraphs),
        letter_date=letter_date,
        info=[("Regelversion", st.rule_version), ("Ergebnis", (st.snapshot_hash or "")[:12])],
        signatory=signatory,
        tables=tables,
        draft_notice=DRAFT_LABEL,
    )
