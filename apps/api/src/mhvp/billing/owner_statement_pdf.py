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
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from mhvp.billing.letters import fmt_date, fmt_eur
from mhvp.billing.owner_statement import OwnerStatement, OwnerStatementKind
from mhvp.documents import letters

DRAFT_LABEL = "Entwurf, kein Versand"
ZERO = Decimal("0.00")
# GA06-03: the tax note of the letter and of the § 35a proof is a placeholder until the
# operator released a text with tax advice (OPEN_QUESTIONS AA11-02). Nothing is formulated here.
TEXT_NOT_RELEASED = "Text nicht freigegeben"
TEXT_CODES = ("owner_letter_tax_note", "owner_s35a_note")  # AE16 text blocks
TAX_TEXT_PENDING = f"{TEXT_NOT_RELEASED}: Steuerlicher Hinweis zu § 35a EStG ausstehend (AA11-02)"
NO_SOURCE_35A = (
    "Für diese Abrechnung liegt keine freigegebene Quelle für belegte Lohnanteile vor; es "
    "werden keine Beträge ausgewiesen."
)


def _d(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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
    texts: dict[str, str] | None = None,
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
    s35a = results.get("section_35a") or {}
    if s35a.get("per_unit"):
        # GA06-03: § 35a block taken over from the WEG individual statement (information only).
        tables["s35a"] = letters.LetterTable(
            header=["Belegte Lohnanteile § 35a EStG (Information)", "Betrag"],
            rows=[
                *[
                    [
                        f"Einheit {line['unit_number'] or line['unit_id'][:8]}",
                        fmt_eur(_d(line["amount"])),
                    ]
                    for line in s35a.get("lines", [])
                ],
                ["Summe", fmt_eur(_d(s35a["total"]))],
            ],
            right_aligned=(1,),
            total_row=True,
            widths=(0.7, 0.3),
        )
        paragraphs += [letters.TABLE_MARKER.format(name="s35a"), str(s35a["note"])]
    paragraphs.append((texts or {}).get("owner_letter_tax_note") or TAX_TEXT_PENDING + ".")
    receipts = results.get("receipts") or {}
    if st.attach_receipts and receipts.get("lines"):
        paragraphs.append(
            f"Anlage Belegmappe: {receipts['linked']} verknüpfte Belege"
            + (f", {receipts['missing']} Buchungen ohne Beleg" if receipts.get("missing") else "")
            + "."
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


def build_s35a_sheet(
    st: OwnerStatement,
    *,
    recipient_lines: list[str],
    property_line: str,
    letter_date: date,
    signatory: list[str],
    texts: dict[str, str] | None = None,
) -> letters.Letter:
    """GA06-03: separate § 35a proof of the owner statement, read from the snapshot only. The
    amounts are the documented labour shares of the WEG individual statement (SEV); a rental
    statement has no released source and shows no amount. The explanatory tax text is a
    placeholder marked "Text nicht freigegeben" until AA11-02 is decided."""
    results = (st.snapshot or {}).get("results") or {}
    s35a = results.get("section_35a") or {}
    tables: dict[str, letters.LetterTable] = {}
    paragraphs = [
        f"Nachweis belegter Lohnanteile für das Objekt {property_line}, Zeitraum "
        f"{fmt_date(st.period_from)} bis {fmt_date(st.period_to)}."
    ]
    if s35a.get("per_unit"):
        tables["s35a"] = letters.LetterTable(
            header=["Einheit", "Belegte Lohnanteile (Information)"],
            rows=[
                *[
                    [line["unit_number"] or line["unit_id"][:8], fmt_eur(_d(line["amount"]))]
                    for line in s35a.get("lines", [])
                ],
                ["Summe", fmt_eur(_d(s35a["total"]))],
            ],
            right_aligned=(1,),
            total_row=True,
            widths=(0.6, 0.4),
        )
        paragraphs += [
            letters.TABLE_MARKER.format(name="s35a"),
            "Quelle: WEG-Einzelabrechnung der Gemeinschaft.",
        ]
    else:
        paragraphs.append(NO_SOURCE_35A)
    if s35a.get("note"):
        paragraphs.append(str(s35a["note"]))
    paragraphs.append((texts or {}).get("owner_s35a_note") or TAX_TEXT_PENDING + ".")
    return letters.Letter(
        recipient_lines=recipient_lines,
        subject=(
            f"Nachweis § 35a EStG {property_line}, {fmt_date(st.period_from)} bis "
            f"{fmt_date(st.period_to)}"
        ),
        body="\n\n".join(p if p.startswith("[[table:") else html.escape(p) for p in paragraphs),
        letter_date=letter_date,
        info=[("Regelversion", st.rule_version), ("Ergebnis", (st.snapshot_hash or "")[:12])],
        signatory=signatory,
        tables=tables,
        draft_notice=DRAFT_LABEL,
    )
