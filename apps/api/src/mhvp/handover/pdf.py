"""PDF of a handover protocol on the tenant letterhead (reportlab, M30).

Every section is printed even when empty (greyed "Keine Angaben"), internal notes and
internal fields are never printed, signatures are printed with name, role, time and hash.
"""

import io
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from mhvp.documents.letters import Letterhead
from mhvp.handover import services as svc
from mhvp.handover.models import HandoverProtocol

uuid_str = str
PAGE_W, PAGE_H = A4
LEFT = RIGHT = 18 * mm
TOP, BOTTOM = 34 * mm, 22 * mm
TEXT, MUTED, LINE = "#1A1A1A", "#6B6C70", "#D7D8DA"
FONT, BOLD = "Helvetica", "Helvetica-Bold"

_body = ParagraphStyle("body", fontName=FONT, fontSize=9, leading=12, textColor=HexColor(TEXT))
_muted = ParagraphStyle("muted", parent=_body, textColor=HexColor(MUTED))
_h1 = ParagraphStyle("h1", fontName=BOLD, fontSize=15, leading=19, textColor=HexColor(TEXT))
_h2 = ParagraphStyle(
    "h2", fontName=BOLD, fontSize=10.5, leading=14, textColor=HexColor(TEXT), spaceBefore=8
)
_small = ParagraphStyle("small", parent=_body, fontSize=7.5, leading=10)

KIND_LABEL = {
    "rental": "Wohnungsübergabe (Vermietung)",
    "sale": "Wohnungsübergabe (Verkauf)",
    "general": "Allgemeines Übergabeprotokoll",
}
CONDITION = {
    "ok": "Mängelfrei",
    "defective": "Mängel vorhanden",
    "not_checked": "Nicht geprüft",
    "not_accessible": "Nicht zugänglich",
    "not_included": "Nicht Bestandteil der Übergabe",
}
PRIORITY = {
    "info": "Hinweis",
    "low": "Gering",
    "medium": "Mittel",
    "high": "Hoch",
    "urgent": "Dringend",
}
DEFECT_STATUS = {
    "pre_existing": "Bereits vorhanden",
    "new": "Neu festgestellt",
    "acknowledged": "Vom Übergebenden anerkannt",
    "rejected": "Anerkennung abgelehnt",
    "unclear": "Ungeklärt",
}
KEY_STATUS = {
    "handed_over": "Übergeben",
    "not_handed_over": "Nicht übergeben",
    "to_follow": "Nachzureichen",
}
NOTE_CATEGORY = {
    "agreement": "Vereinbarung",
    "hint": "Hinweis",
    "defect": "Mangel",
    "open_task": "Offene Aufgabe",
    "follow_up": "Nachreichung",
    "payment": "Zahlungsangelegenheit",
    "other": "Sonstiger Punkt",
}
METER_TYPE = {
    "electricity": "Strom",
    "gas": "Gas",
    "water": "Wasser",
    "cold_water": "Kaltwasser",
    "hot_water": "Warmwasser",
    "heating": "Heizungszähler",
    "heat_quantity": "Wärmemengenzähler",
    "common_electricity": "Allgemeinstrom",
    "sub_meter": "Zwischenzähler",
    "photovoltaic": "Photovoltaik",
    "other": "Sonstiger Zähler",
}
CONSENT = (
    "Mit ihrer Unterschrift bestätigen die Unterzeichnenden die Richtigkeit und Vollständigkeit "
    "der in diesem Protokoll festgehaltenen Angaben. Sie erklären sich zugleich damit "
    "einverstanden, "
    "dass dieses Protokoll einschließlich der zugehörigen Fotos und Unterlagen elektronisch "
    "verarbeitet und in digitaler Form für die Dauer der gesetzlichen Aufbewahrungs- und "
    "Verjährungsfristen gespeichert wird."
)


def _esc(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def fmt_time(value: time | None) -> str:
    return value.strftime("%H:%M") + " Uhr" if value else ""


def fmt_datetime(value: datetime | None) -> str:
    return value.strftime("%d.%m.%Y %H:%M") + " Uhr" if value else ""


def fmt_amount(value: Decimal | None) -> str:
    if value is None:
        return ""
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} EUR"


def _cell(value: Any, *, empty: str = "Keine Angabe") -> Paragraph:
    text = "" if value is None else str(value).strip()
    if text == "":
        return Paragraph(f"<font color='{MUTED}'>{_esc(empty)}</font>", _body)
    return Paragraph(_esc(text).replace("\n", "<br/>"), _body)


def _kv(rows: list[tuple[str, Any]]) -> Table:
    data = [[Paragraph(f"<b>{_esc(k)}</b>", _body), _cell(v)] for k, v in rows]
    table = Table(data, colWidths=[48 * mm, PAGE_W - LEFT - RIGHT - 48 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor(LINE)),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _grid(header: list[str], rows: list[list[Any]], widths: list[float]) -> Any:
    if not rows:
        return Paragraph(f"<font color='{MUTED}'>Keine Angaben</font>", _body)
    data = [[Paragraph(f"<b>{_esc(h)}</b>", _small) for h in header]]
    data += [[_cell(c, empty="") for c in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, HexColor(TEXT)),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, HexColor(LINE)),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _photos(images: list[bytes], per_row: int = 4) -> list[Any]:
    if not images:
        return []
    width = (PAGE_W - LEFT - RIGHT) / per_row - 3 * mm
    cells: list[Any] = []
    for raw in images:
        try:
            reader = ImageReader(io.BytesIO(raw))
            iw, ih = reader.getSize()
            cells.append(Image(io.BytesIO(raw), width=width, height=width * ih / iw))
        except Exception:
            cells.append(Paragraph("<font color='#6B6C70'>Bild nicht lesbar</font>", _small))
    rows = [cells[i : i + per_row] for i in range(0, len(cells), per_row)]
    for row in rows:
        row += [""] * (per_row - len(row))
    table = Table(rows, colWidths=[width + 3 * mm] * per_row)
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [Spacer(1, 2 * mm), table]


class _Pages:
    def __init__(self, head: Letterhead, protocol: HandoverProtocol, draft: bool, cancelled: bool):
        self.head, self.p, self.draft, self.cancelled = head, protocol, draft, cancelled
        self.logo = ImageReader(io.BytesIO(head.logo)) if head.logo else None

    def __call__(self, canvas: Any, doc: Any) -> None:
        c = canvas
        c.saveState()
        company = self.head.company
        branding = self.head.branding
        # colour band from branding (same source as letters.py), else a thin accent rule
        segments = branding.get("letter_band") or []
        y_band = PAGE_H - 8 * mm
        if segments:
            for seg in segments:
                c.setFillColor(HexColor(seg["color"]))
                x0, x1 = float(seg["from"]) * PAGE_W, float(seg["to"]) * PAGE_W
                c.rect(x0, y_band, x1 - x0, 2.2 * mm, stroke=0, fill=1)
        elif branding.get("accent_color"):
            c.setFillColor(HexColor(branding["accent_color"]))
            c.rect(0, y_band, PAGE_W, 1.5 * mm, stroke=0, fill=1)
        if self.logo:
            iw, ih = self.logo.getSize()
            h = 12 * mm
            c.drawImage(
                self.logo,
                PAGE_W - RIGHT - h * iw / ih,
                PAGE_H - 24 * mm,
                width=h * iw / ih,
                height=h,
                mask="auto",
            )
        c.setFillColor(HexColor(TEXT))
        c.setFont(BOLD, 9)
        c.drawString(LEFT, PAGE_H - 16 * mm, str(company.get("name") or ""))
        c.setFont(FONT, 8)
        c.setFillColor(HexColor(MUTED))
        c.drawString(LEFT, PAGE_H - 20.5 * mm, f"Übergabeprotokoll {self.p.number}")
        if self.draft or self.cancelled:
            c.setFillColor(HexColor("#B42318"))
            c.setFont(BOLD, 9)
            c.drawString(
                LEFT,
                PAGE_H - 25 * mm,
                "STORNIERT: Dieses Protokoll ist nicht wirksam"
                if self.cancelled
                else "ENTWURF: Protokoll noch nicht abgeschlossen",
            )
        # footer
        c.setStrokeColor(HexColor(LINE))
        c.setLineWidth(0.4)
        c.line(LEFT, BOTTOM - 4 * mm, PAGE_W - RIGHT, BOTTOM - 4 * mm)
        c.setFont(FONT, 7)
        c.setFillColor(HexColor(MUTED))
        place = " ".join(x for x in (company.get("postal_code"), company.get("city")) if x)
        first = " | ".join(x for x in (company.get("name"), company.get("street"), place) if x)
        second = []
        if company.get("register_court") and company.get("register_number"):
            second.append(f"{company['register_court']}, {company['register_number']}")
        management = company.get("management") or []
        if management:
            second.append(
                f"{company.get('management_title') or 'Geschäftsführung'}: {', '.join(management)}"
            )
        for key in ("website", "email", "phone"):
            if company.get(key):
                second.append(str(company[key]))
        c.drawString(LEFT, BOTTOM - 8 * mm, first)
        c.drawString(LEFT, BOTTOM - 11.5 * mm, " | ".join(second))
        c.drawRightString(PAGE_W - RIGHT, BOTTOM - 8 * mm, f"Seite {doc.page}")
        c.restoreState()


def render(
    full: dict[str, Any],
    head: Letterhead,
    *,
    photos: dict[uuid_str, list[bytes]] | None = None,
    signatures: dict[uuid_str, bytes] | None = None,
    draft: bool = False,
    change_reason: str | None = None,
) -> bytes:
    """Render the protocol. ``photos`` maps a sub record id (as string) to image bytes,
    ``signatures`` maps a signature id to its PNG. Internal data is filtered here."""
    p: HandoverProtocol = full["protocol"]
    photos = photos or {}
    signatures = signatures or {}
    cancelled = p.status == "cancelled"
    story: list[Any] = []
    kind = KIND_LABEL.get(p.kind, "Übergabeprotokoll")
    story.append(Paragraph(_esc(kind), _h1))
    story.append(
        Paragraph(
            f"Protokoll {_esc(p.number)}"
            + (f", Version {p.version}" if p.version > 1 else "")
            + (f" (Änderungsgrund: {_esc(change_reason)})" if change_reason else ""),
            _muted,
        )
    )
    story.append(Spacer(1, 3 * mm))

    # Object
    story.append(Paragraph("Objekt", _h2))
    rows: list[tuple[str, Any]] = [
        ("Adresse", svc.address_line(p)),
        ("Objekt", p.object_label),
        ("Einheit", " ".join(x for x in (p.unit_number, p.unit_label, p.unit_position) if x)),
        ("Gebäude / Etage", " ".join(x for x in (p.building, p.floor) if x)),
        ("Übergabedatum", fmt_date(p.handover_date)),
    ]
    if not p.hide_time_information:
        span = " bis ".join(x for x in (fmt_time(p.handover_start), fmt_time(p.handover_end)) if x)
        rows.append(("Uhrzeit", span))
    rows += [
        ("Ort der Übergabe", p.handover_location),
        ("Ticketnummer", p.ticket_number),
        ("Referenz", p.reference_number),
        ("Mietvertragsnummer", p.rental_contract_number),
    ]
    story.append(_kv(rows))

    # Participants
    story.append(Paragraph("Beteiligte", _h2))
    story.append(
        _grid(
            ["Rolle", "Name", "Anschrift", "Kontakt"],
            [
                [
                    svc.role_label(x.role, p.kind),
                    " ".join(v for v in (x.salutation, x.first_name, x.last_name) if v)
                    + (f" ({x.company})" if x.company else ""),
                    svc.address_line(x),
                    ", ".join(v for v in (x.email, x.phone) if v),
                ]
                for x in full["participants"]
            ],
            [38 * mm, 50 * mm, 50 * mm, 36 * mm],
        )
    )

    # Deposit
    story.append(Paragraph("Kaution und Bankverbindung", _h2))
    story.append(
        _kv(
            [
                ("Kautionsbetrag", fmt_amount(p.deposit_amount)),
                ("Kontoinhaber", p.deposit_account_holder),
                ("IBAN", p.deposit_iban),
                ("BIC", p.deposit_bic),
                ("Bank", p.deposit_bank_name),
                ("Bemerkung", p.deposit_note),
                (
                    "Hinweis",
                    "Kautionsabrechnung erfolgt separat" if p.deposit_separate_statement else None,
                ),
            ]
        )
    )

    # Meters
    story.append(Paragraph("Zählerstände", _h2))
    story.append(
        _grid(
            ["Zähler", "Nummer", "Stand", "Einheit", "Standort", "Abgelesen"],
            [
                [
                    x.custom_type or METER_TYPE.get(x.meter_type or "", x.meter_type),
                    x.number,
                    f"{x.value:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    if x.value is not None
                    else "",
                    x.unit,
                    x.location,
                    " ".join(v for v in (fmt_date(x.read_on), fmt_time(x.read_at)) if v),
                ]
                for x in full["meters"]
            ],
            [34 * mm, 30 * mm, 26 * mm, 18 * mm, 36 * mm, 30 * mm],
        )
    )
    for x in full["meters"]:
        story += _photos(photos.get(str(x.id), []))

    # Rooms and defects
    story.append(Paragraph("Räume und Zustand", _h2))
    defects_by_room: dict[Any, list[Any]] = {}
    for d in full["defects"]:
        defects_by_room.setdefault(d.room_id, []).append(d)
    if not full["rooms"]:
        story.append(Paragraph(f"<font color='{MUTED}'>Keine Angaben</font>", _body))
    for room in full["rooms"]:
        block: list[Any] = [
            Paragraph(
                f"<b>{_esc(room.name or room.room_type or 'Raum')}</b>: "
                f"{_esc(CONDITION.get(room.condition or '', 'Keine Angabe'))}"
                + (f", {_esc(room.comment)}" if room.comment else ""),
                _body,
            )
        ]
        rd = defects_by_room.get(room.id, [])
        if rd:
            block.append(
                _grid(
                    ["Mangel", "Beschreibung", "Priorität", "Status", "Verantwortlich"],
                    [
                        [
                            " ".join(v for v in (d.category, d.title) if v),
                            " ".join(v for v in (d.description, d.location) if v),
                            PRIORITY.get(d.priority or "", ""),
                            DEFECT_STATUS.get(d.defect_status or "", ""),
                            d.responsibility,
                        ]
                        for d in rd
                    ],
                    [36 * mm, 58 * mm, 20 * mm, 30 * mm, 30 * mm],
                )
            )
        block += _photos(photos.get(str(room.id), []))
        for d in rd:
            block += _photos(photos.get(str(d.id), []))
        story.append(KeepTogether(block))
        story.append(Spacer(1, 1.5 * mm))
    loose = [d for d in full["defects"] if d.room_id is None]
    if loose:
        story.append(Paragraph("Mängel ohne Raumzuordnung", _body))
        story.append(
            _grid(
                ["Mangel", "Beschreibung", "Priorität", "Status", "Verantwortlich"],
                [
                    [
                        " ".join(v for v in (d.category, d.title) if v),
                        " ".join(v for v in (d.description, d.location) if v),
                        PRIORITY.get(d.priority or "", ""),
                        DEFECT_STATUS.get(d.defect_status or "", ""),
                        d.responsibility,
                    ]
                    for d in loose
                ],
                [36 * mm, 58 * mm, 20 * mm, 30 * mm, 30 * mm],
            )
        )
        for d in loose:
            story += _photos(photos.get(str(d.id), []))

    # Keys and items
    story.append(Paragraph("Schlüssel", _h2))
    story.append(
        _grid(
            ["Schlüssel", "Anzahl", "Nummer", "Status", "Bemerkung"],
            [
                [
                    x.custom_name or x.key_type,
                    x.quantity,
                    x.key_number,
                    KEY_STATUS.get(x.status or "", ""),
                    x.comment,
                ]
                for x in full["keys"]
            ],
            [48 * mm, 18 * mm, 32 * mm, 32 * mm, 44 * mm],
        )
    )
    story.append(Paragraph("Gegenstände und Unterlagen", _h2))
    story.append(
        _grid(
            ["Gegenstand", "Anzahl", "Zustand", "Bemerkung"],
            [[x.name or x.item_type, x.quantity, x.condition, x.comment] for x in full["items"]],
            [60 * mm, 18 * mm, 40 * mm, 56 * mm],
        )
    )
    for x in full["items"]:
        story += _photos(photos.get(str(x.id), []))

    # Notes (never internal)
    story.append(Paragraph("Vereinbarungen und Bemerkungen", _h2))
    story.append(
        _grid(
            ["Art", "Text", "Verantwortlich", "Frist", "Status"],
            [
                [
                    NOTE_CATEGORY.get(x.category or "", x.category),
                    x.text,
                    x.responsible_party,
                    fmt_date(x.due_date),
                    x.status,
                ]
                for x in full["notes"]
                if not x.is_internal
            ],
            [28 * mm, 66 * mm, 30 * mm, 26 * mm, 24 * mm],
        )
    )
    if p.general_note:
        story.append(Paragraph(_esc(p.general_note).replace("\n", "<br/>"), _body))

    # Signatures
    story.append(Paragraph("Unterschriften", _h2))
    story.append(Paragraph(_esc(CONSENT), _small))
    story.append(Spacer(1, 2 * mm))
    if not full["signatures"]:
        story.append(Paragraph(f"<font color='{MUTED}'>Keine Unterschrift erfasst</font>", _body))
    cells: list[Any] = []
    for sig in full["signatures"]:
        column: list[Any] = []
        png = signatures.get(str(sig.id))
        if png:
            try:
                reader = ImageReader(io.BytesIO(png))
                iw, ih = reader.getSize()
                w = 60 * mm
                column.append(Image(io.BytesIO(png), width=w, height=w * ih / iw))
            except Exception:
                column.append(Paragraph("<font color='#6B6C70'>Bild nicht lesbar</font>", _small))
        column.append(
            Paragraph(
                f"<b>{_esc(sig.signer_name or 'Ohne Namen')}</b><br/>"
                f"{_esc(svc.role_label(sig.signer_role, p.kind))}<br/>"
                f"{_esc(fmt_datetime(sig.signed_at))}"
                + (f", {_esc(sig.signed_location)}" if sig.signed_location else "")
                + f"<br/><font color='{MUTED}'>SHA-256 {_esc(sig.sha256[:16])}…</font>",
                _small,
            )
        )
        cells.append(column)
    if cells:
        rows2 = [cells[i : i + 2] for i in range(0, len(cells), 2)]
        for row in rows2:
            while len(row) < 2:
                row.append(Spacer(0, 0))
        table = Table(rows2, colWidths=[(PAGE_W - LEFT - RIGHT) / 2] * 2)
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(table)
    if p.completed_at:
        story.append(Spacer(1, 3 * mm))
        story.append(
            Paragraph(
                f"Abgeschlossen und festgeschrieben am {_esc(fmt_datetime(p.completed_at))}.",
                _muted,
            )
        )

    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=LEFT,
        rightMargin=RIGHT,
        topMargin=TOP,
        bottomMargin=BOTTOM,
        title=f"Übergabeprotokoll {p.number}",
        author=str(head.company.get("name") or ""),
    )
    frame = Frame(LEFT, BOTTOM, PAGE_W - LEFT - RIGHT, PAGE_H - TOP - BOTTOM, id="body")
    pages = _Pages(head, p, draft, cancelled)
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=pages)])
    doc.build(story)
    return buffer.getvalue()
