"""Letters from templates on the tenant letterhead (DIN 5008 form B), rendered as PDF (M6).

Placeholders use Jinja2 in a sandbox with ``StrictUndefined``: a missing value is an error, never
an empty or invented text. Values are escaped because reportlab paragraphs interpret markup.
The letterhead only uses tenant settings (company, branding); nothing is filled in from defaults.
"""

import html
import io
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

PAGE_W, PAGE_H = A4
LEFT, RIGHT = 25 * mm, 20 * mm
BOTTOM = 28 * mm
TEXT = "#1A1A1A"
MUTED = "#6B6C70"

_env = SandboxedEnvironment(undefined=StrictUndefined, autoescape=True, keep_trailing_newline=False)


class PlaceholderError(ValueError):
    """A placeholder is unknown or the template is malformed."""


@dataclass
class Letterhead:
    company: dict[str, Any]
    branding: dict[str, Any]
    logo: bytes | None = None

    def missing_mandatory(self) -> list[str]:
        """Company fields a business letter needs (tenant data, section 5.2; V14 for values)."""
        required = ["name", "street", "postal_code", "city"]
        if self.company.get("legal_form") in ("GmbH", "AG", "UG"):
            required += ["register_court", "register_number", "management"]
        return [k for k in required if not self.company.get(k)]


@dataclass
class LetterTable:
    """A table inside the body (for example a Forderungsaufstellung). Cells are plain text
    (escaped on rendering); ``right_aligned`` lists column indexes with amounts; the optional
    last row is rendered bold as a total when ``total_row`` is set."""

    header: list[str]
    rows: list[list[str]]
    right_aligned: tuple[int, ...] = ()
    total_row: bool = False
    widths: tuple[float, ...] | None = None  # fractions of the text width, sums to 1


TABLE_MARKER = "[[table:{name}]]"


@dataclass
class Letter:
    recipient_lines: list[str]
    subject: str
    body: str
    letter_date: date
    info: list[tuple[str, str]] = field(default_factory=list)
    closing: str = "Mit freundlichen Grüßen"
    signatory: list[str] = field(default_factory=list)
    # Tables referenced from ``body`` by a paragraph that only holds ``[[table:<name>]]``.
    tables: dict[str, LetterTable] = field(default_factory=dict)
    # Optional prominent note above the subject (plain text, escaped on rendering), for
    # example "Vorbereitung, Prüfung durch Rechtsanwalt erforderlich, kein Antrag".
    notice: str | None = None
    # Optional draft marking (A83): printed as a red header line on every page and as a light
    # diagonal watermark "ENTWURF"; off for every caller unless set explicitly.
    draft_notice: str | None = None


def render_text(source: str, context: dict[str, Any]) -> str:
    try:
        return _env.from_string(source).render(**context)
    except TemplateError as exc:
        raise PlaceholderError(str(exc)) from None


def check_template(source: str) -> None:
    try:
        _env.parse(source)
    except TemplateError as exc:
        raise PlaceholderError(str(exc)) from None


def _sender_line(company: dict[str, Any]) -> str:
    place = " ".join(p for p in (company.get("postal_code"), company.get("city")) if p)
    return ", ".join(p for p in (company.get("name"), company.get("street"), place) if p)


def _footer_lines(company: dict[str, Any]) -> list[str]:
    place = " ".join(p for p in (company.get("postal_code"), company.get("city")) if p)
    first = [company.get("name"), company.get("street"), place]
    second: list[str] = []
    if company.get("register_court") and company.get("register_number"):
        second.append(f"{company['register_court']}, {company['register_number']}")
    management = company.get("management") or []
    if management:
        title = company.get("management_title") or "Geschäftsführung"
        second.append(f"{title}: {', '.join(management)}")
    for key in ("website", "email", "phone", "vat_id"):
        if company.get(key):
            second.append(str(company[key]))
    return [" | ".join(p for p in first if p), " | ".join(second)]


def _band(c: Canvas, branding: dict[str, Any], y_top: float, height: float) -> None:
    """Colour band from ``branding.letter_band`` (segments of the page width), else a rule."""
    segments = branding.get("letter_band") or []
    if segments:
        for seg in segments:
            c.setFillColor(HexColor(seg["color"]))
            x0, x1 = float(seg["from"]) * PAGE_W, float(seg["to"]) * PAGE_W
            c.rect(x0, y_top - height, x1 - x0, height, stroke=0, fill=1)
        return
    accent = branding.get("accent_color")
    if accent:
        c.setStrokeColor(HexColor(accent))
        c.setLineWidth(0.8)
        c.line(LEFT, y_top - height, PAGE_W - RIGHT, y_top - height)


class _Pages:
    def __init__(self, head: Letterhead, letter: Letter) -> None:
        self.head, self.letter = head, letter

    def _footer(self, c: Canvas) -> None:
        c.setFillColor(HexColor(MUTED))
        c.setFont("Helvetica", 7.5)
        y = 18 * mm
        for line in _footer_lines(self.head.company):
            if line:
                c.drawCentredString(PAGE_W / 2, y, line)
                y -= 3.4 * mm

    def _draft(self, c: Canvas) -> None:
        notice = self.letter.draft_notice
        if not notice:
            return
        c.saveState()
        c.setFillColor(HexColor("#D9D9DC"))
        c.setFont("Helvetica-Bold", 90)
        c.translate(PAGE_W / 2, PAGE_H / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, "ENTWURF")
        c.restoreState()
        c.setFillColor(HexColor("#8A1C1C"))
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(LEFT, PAGE_H - 7.5 * mm, notice[:160])

    def first(self, c: Canvas, _doc: Any) -> None:
        head, letter = self.head, self.letter
        self._draft(c)
        _band(c, head.branding, PAGE_H, 3 * mm)
        # Fold and hole marks (DIN 5008 form B).
        c.setStrokeColor(HexColor("#9C9D9F"))
        c.setLineWidth(0.4)
        for y_mm, length in ((105, 4.5), (148.5, 7), (210, 4.5)):
            c.line(2 * mm, PAGE_H - y_mm * mm, (2 + length) * mm, PAGE_H - y_mm * mm)
        if head.logo:
            image = ImageReader(io.BytesIO(head.logo))
            w, h = image.getSize()
            width = 40 * mm
            c.drawImage(
                image,
                PAGE_W - RIGHT - width,
                PAGE_H - 10 * mm - width * h / w,
                width=width,
                height=width * h / w,
                mask="auto",
            )
        else:
            c.setFillColor(HexColor(TEXT))
            c.setFont("Helvetica-Bold", 15)
            c.drawString(LEFT, PAGE_H - 22 * mm, head.company.get("name", ""))
        c.setFillColor(HexColor(MUTED))
        c.setFont("Helvetica", 7.5)
        c.drawString(LEFT, PAGE_H - 45 * mm, _sender_line(head.company))
        c.setFillColor(HexColor(TEXT))
        c.setFont("Helvetica", 11)
        y = PAGE_H - 53 * mm
        for line in letter.recipient_lines[:6]:
            c.drawString(LEFT, y, line)
            y -= 4.8 * mm
        y = PAGE_H - 53 * mm
        for label, value in [*letter.info, ("Datum", letter.letter_date.strftime("%d.%m.%Y"))]:
            c.setFillColor(HexColor(MUTED))
            c.setFont("Helvetica", 8)
            c.drawString(125 * mm, y, label)
            c.setFillColor(HexColor(TEXT))
            c.setFont("Helvetica", 9.5)
            c.drawString(125 * mm, y - 4 * mm, value)
            y -= 10 * mm
        self._footer(c)

    def later(self, c: Canvas, doc: Any) -> None:
        self._draft(c)
        _band(c, self.head.branding, PAGE_H, 1.2 * mm)
        c.setFillColor(HexColor(MUTED))
        c.setFont("Helvetica", 8)
        c.drawRightString(PAGE_W - RIGHT, 12 * mm, f"Seite {doc.page}")
        self._footer(c)


def _table(table: LetterTable, width: float, style: ParagraphStyle) -> Table:
    cell = ParagraphStyle("cell", parent=style, spaceAfter=0, fontSize=9.5, leading=12)
    cell_right = ParagraphStyle("cell_right", parent=cell, alignment=2)
    head = ParagraphStyle("cell_head", parent=cell, fontName="Helvetica-Bold")
    head_right = ParagraphStyle("cell_head_right", parent=head, alignment=2)

    def row(values: list[str], base: ParagraphStyle, right: ParagraphStyle) -> list[Any]:
        return [
            Paragraph(html.escape(v), right if i in table.right_aligned else base)
            for i, v in enumerate(values)
        ]

    data = [row(table.header, head, head_right)]
    for index, values in enumerate(table.rows):
        bold = table.total_row and index == len(table.rows) - 1
        data.append(row(values, head if bold else cell, head_right if bold else cell_right))
    columns = len(table.header)
    fractions = table.widths or tuple(1 / columns for _ in range(columns))
    flow = Table(data, colWidths=[width * f for f in fractions], repeatRows=1)
    commands: list[Any] = [
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, HexColor(TEXT)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if table.total_row and table.rows:
        commands.append(("LINEABOVE", (0, -1), (-1, -1), 0.6, HexColor(TEXT)))
    flow.setStyle(TableStyle(commands))
    return flow


def _paragraphs(
    text: str,
    style: ParagraphStyle,
    tables: dict[str, LetterTable] | None = None,
    width: float = PAGE_W - LEFT - RIGHT,
) -> list[Any]:
    blocks = [b.strip() for b in text.replace("\r\n", "\n").split("\n\n")]
    out: list[Any] = []
    for block in blocks:
        if not block:
            continue
        if block.startswith("[[table:") and block.endswith("]]"):
            table = (tables or {}).get(block[len("[[table:") : -2])
            if table is None:
                raise PlaceholderError(f"Unbekannte Tabelle {block}.")
            out += [_table(table, width, style), Spacer(1, 4 * mm)]
            continue
        out.append(Paragraph(block.replace("\n", "<br/>"), style))
    return out


def render_pdf(head: Letterhead, letter: Letter) -> bytes:
    """Render an escaped letter. ``subject`` and ``body`` must come from :func:`render_text`."""
    buffer = io.BytesIO()
    pages = _Pages(head, letter)
    width = PAGE_W - LEFT - RIGHT
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=LEFT,
        rightMargin=RIGHT,
        topMargin=20 * mm,
        bottomMargin=BOTTOM,
        title=letter.subject,
        author=head.company.get("name", ""),
    )
    pad = {"leftPadding": 0, "rightPadding": 0, "topPadding": 0, "bottomPadding": 0}
    first = Frame(LEFT, BOTTOM, width, PAGE_H - 97 * mm - BOTTOM, id="first", **pad)
    later = Frame(LEFT, BOTTOM, width, PAGE_H - 25 * mm - BOTTOM, id="later", **pad)
    doc.addPageTemplates(
        [
            PageTemplate("first", [first], onPage=pages.first, autoNextPageTemplate="later"),
            PageTemplate("later", [later], onPage=pages.later),
        ]
    )
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=10.5, leading=14, spaceAfter=7)
    subject = ParagraphStyle("subject", fontName="Helvetica-Bold", fontSize=11.5, leading=15)
    story: list[Any] = []
    if letter.notice:
        notice = ParagraphStyle(
            "notice", parent=body, fontName="Helvetica-Bold", textColor=HexColor("#8A1C1C")
        )
        story += [Paragraph(html.escape(letter.notice), notice), Spacer(1, 3 * mm)]
    story += [Paragraph(letter.subject, subject), Spacer(1, 8 * mm)]
    story += _paragraphs(letter.body, body, letter.tables, width)
    story += [Spacer(1, 4 * mm), Paragraph(html.escape(letter.closing), body), Spacer(1, 14 * mm)]
    story += [Paragraph(html.escape(line), body) for line in letter.signatory]
    doc.build(story)
    return buffer.getvalue()
