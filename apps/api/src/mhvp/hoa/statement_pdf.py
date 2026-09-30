"""Einzelabrechnung of the annual WEG statement as a PDF draft (M24-03, 7.8 W12).

Everything is read from the stored snapshot of the statement (nothing is recalculated): cost
positions with key and the unit's share, resolved and paid advances, the result against the
resolved advances, arrears apart, reserve development, key figures and the § 35a block. The
document is marked as a draft; issuing to owners stays behind G4 and the resolution (W06).
"""

import io
from decimal import Decimal
from typing import Any

from mhvp.billing.letters import fmt_eur

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
