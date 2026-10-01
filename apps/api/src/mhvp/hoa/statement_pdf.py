"""Einzelabrechnung of the annual WEG statement as a PDF draft (M24-03, 7.8 W12).

Everything is read from the stored snapshot of the statement (nothing is recalculated): cost
positions with key and the unit's share, resolved and paid advances, the result against the
resolved advances, arrears apart, reserve development, key figures and the § 35a block. The
document is marked as a draft; issuing to owners stays behind G4 and the resolution (W06).
"""

import html
import io
from datetime import date
from decimal import Decimal
from typing import Any

from mhvp.billing.letters import fmt_date, fmt_eur
from mhvp.documents import letters

DRAFT_LABEL = "Entwurf, kein Versand"


def _eur(value: Any) -> str:
    return fmt_eur(Decimal(str(value or "0")))


def rows(snapshot: dict[str, Any], unit: dict[str, Any]) -> dict[str, list[list[str]]]:
    """Table rows of the unit statement (pure function, testable without rendering)."""
    uid = unit["unit_id"]
    positions = [
        [p["label"], p.get("basis", ""), _eur(p["amount"]), _eur(p.get("split", {}).get(uid))]
        for p in snapshot.get("positions", [])
    ]
    positions.append(["Summe Kostenanteil", "", "", _eur(unit["cost_share"])])
    result = Decimal(unit["result"])
    settlement = [
        ["Kostenanteil", _eur(unit["cost_share"])],
        [
            "abzüglich beschlossene Hausgeldvorschüsse (Soll)",
            _eur(-Decimal(unit["advances_resolved"])),
        ],
        [
            "Abrechnungsspitze (Nachschuss)" if result > 0 else "Anpassung der Vorschüsse",
            _eur(abs(result)),
        ],
        ["gezahlte Vorschüsse (Ist, Information)", _eur(unit["advances_paid"])],
        ["Zahlungsrückstand (eigene Forderung)", _eur(unit["arrears"])],
    ]
    reserve = snapshot.get("reserve") or {}
    reserve_rows = [
        ["Anfangsbestand", _eur(reserve.get("opening"))],
        ["Zuführungen gezahlt", _eur(reserve.get("contributions_paid"))],
        ["Entnahmen", _eur(reserve.get("withdrawals"))],
        ["Zinsen", _eur(reserve.get("interest"))],
        ["Endbestand", _eur(reserve.get("closing"))],
        [
            "Ihre Zuführung Soll / Ist",
            f"{_eur(unit['reserve_due'])} / {_eur(unit['reserve_paid'])}",
        ],
    ]
    for pos in reserve.get("positions", []):
        reserve_rows.append(
            [f"Rücklage {pos['name']}: Veränderung Plan", _eur(pos["planned_change"])]
        )
        if pos.get("contributions_paid_bound"):
            reserve_rows.append(
                [f"Rücklage {pos['name']}: Veränderung nach Zahlungen", _eur(pos["paid_change"])]
            )
    s35a = snapshot.get("section_35a") or {}
    labour = (s35a.get("per_unit") or {}).get(uid)
    tax_rows = (
        [["Anteil belegter Lohnkosten § 35a EStG (Information)", _eur(labour)]] if labour else []
    )
    return {
        "positions": positions,
        "settlement": settlement,
        "reserve": reserve_rows,
        "section_35a": tax_rows,
    }


def render(year: int, snapshot: dict[str, Any], unit: dict[str, Any], snapshot_hash: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    data = rows(snapshot, unit)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=25 * mm, rightMargin=20 * mm)

    def table(header: list[str], body: list[list[str]]) -> Table:
        t = Table([header, *body], repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
                    ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
                ]
            )
        )
        return t

    story: list[Any] = [
        Paragraph(DRAFT_LABEL, styles["Normal"]),
        Paragraph(f"Einzelabrechnung {year}, Einheit {unit['unit_number']}", styles["Title"]),
        Paragraph(
            "Das Ergebnis ist gegen die beschlossenen Vorschüsse berechnet; Rückstände bleiben "
            "eigene Forderungen und sind keine neue Forderung aus dieser Abrechnung.",
            styles["Normal"],
        ),
        Spacer(1, 6 * mm),
        table(["Kostenposition", "Grundlage", "Gesamt", "Ihr Anteil"], data["positions"]),
        Spacer(1, 6 * mm),
        table(["Ergebnis", "Betrag"], data["settlement"]),
        Spacer(1, 6 * mm),
        table(["Erhaltungsrücklage", "Betrag"], data["reserve"]),
    ]
    if data["section_35a"]:
        story += [Spacer(1, 6 * mm), table(["Steuerlicher Ausweis", "Betrag"], data["section_35a"])]
    story += [
        Spacer(1, 6 * mm),
        Paragraph(f"Stand der Berechnung: {snapshot_hash[:12]}", styles["Normal"]),
    ]
    doc.build(story)
    return buffer.getvalue()


def total_rows(snapshot: dict[str, Any]) -> dict[str, list[list[str]]]:
    """Table rows of the Gesamtabrechnung (pure function, read from the stored snapshot)."""
    positions = [
        [p["label"], p.get("basis", ""), _eur(p["amount"])] for p in snapshot.get("positions", [])
    ]
    positions.append(["Gesamtkosten", "", _eur(snapshot.get("total_costs"))])
    units = [
        [
            u["unit_number"],
            _eur(u["cost_share"]),
            _eur(u["advances_resolved"]),
            _eur(u["result"]),
            _eur(u["advances_paid"]),
            _eur(u["arrears"]),
        ]
        for u in snapshot.get("units", [])
    ]
    sums = {
        k: sum((Decimal(str(u[k])) for u in snapshot.get("units", [])), Decimal(0))
        for k in ("cost_share", "advances_resolved", "result", "advances_paid", "arrears")
    }
    if units:
        units.append(["Summe", *(_eur(sums[k]) for k in sums)])
    reserve = snapshot.get("reserve") or {}
    development = [
        ["Anfangsbestand", _eur(reserve.get("opening"))],
        ["Beschlossene Zuführungen (Soll)", _eur(reserve.get("contributions_resolved"))],
        ["Gezahlte Zuführungen (Ist)", _eur(reserve.get("contributions_paid"))],
        ["Entnahmen", _eur(reserve.get("withdrawals"))],
        ["Zinsen", _eur(reserve.get("interest"))],
        ["Endbestand", _eur(reserve.get("closing"))],
        ["Bankbestand der Rücklagenkonten", _eur(reserve.get("bank_balance"))],
        ["Differenz Bank zu Endbestand", _eur(reserve.get("bank_difference"))],
    ]
    per_reserve = [
        [
            pos["name"],
            _eur(pos["contributions_planned"]),
            _eur(pos.get("contributions_paid")),
            _eur(pos["withdrawals"]),
            _eur(pos["taxes"]),
            _eur(pos["fees"]),
            _eur(pos["interest"]),
        ]
        for pos in reserve.get("positions", [])
    ]
    return {
        "positions": positions,
        "units": units,
        "reserve": development,
        "per_reserve": per_reserve,
    }


def build_total_letter(
    year: int,
    snapshot: dict[str, Any],
    snapshot_hash: str,
    *,
    recipient_lines: list[str],
    property_line: str,
    letter_date: date,
    signatory: list[str],
) -> letters.Letter:
    """Gesamtabrechnung on the letter blocks of the tenant (DIN 5008), marked as a draft."""
    data = total_rows(snapshot)
    marker = letters.TABLE_MARKER
    tables = {
        "kosten": letters.LetterTable(
            header=["Kostenposition", "Verteilerschlüssel", "Gesamt"],
            rows=data["positions"],
            right_aligned=(2,),
            total_row=True,
            widths=(0.5, 0.3, 0.2),
        ),
        "einheiten": letters.LetterTable(
            header=["Einheit", "Kostenanteil", "Soll", "Ergebnis", "Gezahlt", "Rückstand"],
            rows=data["units"],
            right_aligned=(1, 2, 3, 4, 5),
            total_row=bool(snapshot.get("units")),
            widths=(0.14, 0.17, 0.17, 0.17, 0.17, 0.18),
        ),
        "ruecklage": letters.LetterTable(
            header=["Entwicklung der Erhaltungsrücklage", "Betrag"],
            rows=data["reserve"],
            right_aligned=(1,),
            total_row=False,
            widths=(0.7, 0.3),
        ),
    }
    paragraphs = [
        "Sehr geehrte Damen und Herren,",
        f"für das Wirtschaftsjahr {year} der Gemeinschaft {property_line} erhalten Sie die "
        "Gesamtabrechnung. Alle Werte sind dem gespeicherten Berechnungsstand entnommen. Das "
        "Ergebnis je Einheit ist gegen die beschlossenen Vorschüsse berechnet, Rückstände "
        "bleiben eigene Forderungen und sind keine neue Forderung aus dieser Abrechnung.",
        marker.format(name="kosten"),
        marker.format(name="einheiten"),
        marker.format(name="ruecklage"),
    ]
    if data["per_reserve"]:
        tables["je_ruecklage"] = letters.LetterTable(
            header=["Rücklage", "Soll", "Gezahlt", "Entnahme", "Steuer", "Gebühr", "Zins"],
            rows=data["per_reserve"],
            right_aligned=(1, 2, 3, 4, 5, 6),
            widths=(0.25, 0.125, 0.125, 0.125, 0.125, 0.125, 0.125),
        )
        paragraphs.append(marker.format(name="je_ruecklage"))
    paragraphs.append(
        "Dieses Schreiben ist ein Entwurf; die Ausgabe an die Eigentümer erfolgt nach "
        "Beschluss und Freigabe."
    )
    return letters.Letter(
        recipient_lines=recipient_lines,
        subject=f"Gesamtabrechnung {year}, {property_line}, Stand {fmt_date(letter_date)}",
        body="\n\n".join(p if p.startswith("[[table:") else html.escape(p) for p in paragraphs),
        letter_date=letter_date,
        info=[("Wirtschaftsjahr", str(year)), ("Berechnungsstand", snapshot_hash[:12])],
        signatory=signatory,
        tables=tables,
        draft_notice=DRAFT_LABEL,
    )
