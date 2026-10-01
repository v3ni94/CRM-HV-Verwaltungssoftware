"""Generated draft of the Verarbeitungsverzeichnis and the processor register (S16-04, S711-10).

The text is assembled only from the register entries the operator maintains and, for the
section "Anbieter laut Konfiguration", from ``mhvp.privacy.config_sources``. It contains no
legal finding of its own: roles of GdWE, Verwalter and Betreiber, the legal basis and the
third country status are printed as entered and as "offen" while empty. The notice that a
lawyer has to review it (V13) is part of the document and cannot be switched off.

``blocks`` builds one structure; ``render`` (Markdown) and ``render_pdf`` (reportlab) print it,
so both exports always carry the same content (AE32).
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any
from xml.sax.saxutils import escape

from mhvp.privacy.config_sources import DetectedSource
from mhvp.privacy.models import RESPONSIBILITY_ACTORS, PrivacyRegisterEntry

REVIEW_NOTICE = (
    "ENTWURF. Der Inhalt ist vor Verwendung durch einen Rechtsanwalt zu prüfen "
    "(offener Punkt V13). "
    "Er ersetzt keine rechtliche Bewertung."
)
MAINTENANCE_NOTICE = (
    "Rollen, Rechtsgrundlagen und Drittlandübermittlungen sind Pflegefelder des Betreibers. "
    'Die Plattform belegt sie nicht vor; "offen" bedeutet, dass noch kein Eintrag vorliegt.'
)
_AVV = {
    "none": "kein Nachweis",
    "requested": "angefordert",
    "confirmed": "bestätigt",
    "not_required": "nicht erforderlich",
}
ACTOR_LABELS = {
    "gdwe": "GdWE (Gemeinschaft der Wohnungseigentümer)",
    "verwalter": "Verwalter",
    "betreiber": "Betreiber der Plattform",
}
ROLE_LABELS = {
    "open": "offen",
    "controller": "Verantwortlicher",
    "joint_controller": "gemeinsam Verantwortlicher",
    "processor": "Auftragsverarbeiter",
    "not_involved": "nicht beteiligt",
}


@dataclass(frozen=True)
class Block:
    kind: str  # title, notice, text, h2, h3, item
    text: str


def _join(values: Iterable[str]) -> str:
    items = list(values)
    return ", ".join(items) if items else "nicht erfasst"


def _fmt(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "offen"


def third_country_status(e: PrivacyRegisterEntry) -> str:
    status = getattr(e, "third_country_status", None) or ("yes" if e.third_country else "open")
    return str(status)


def _third(e: PrivacyRegisterEntry) -> str:
    status = third_country_status(e)
    if status == "open":
        return "offen, nicht erfasst"
    if status == "no":
        return "nein (laut Eintrag)"
    text = "ja"
    if getattr(e, "third_country_countries", None):
        text += f", Länder: {e.third_country_countries}"
    return text + ", Garantien: " + (e.third_country_note or "nicht erfasst")


def _review(e: PrivacyRegisterEntry) -> str:
    if e.legal_review_status == "reviewed":
        return "geprüft am " + _fmt(e.legal_reviewed_on)
    return "offen"


def roles_of(e: PrivacyRegisterEntry) -> dict[str, str]:
    stored = dict(getattr(e, "responsibilities", None) or {})
    return {actor: str(stored.get(actor) or "open") for actor in RESPONSIBILITY_ACTORS}


def _activity(e: PrivacyRegisterEntry, names: dict[Any, str]) -> list[Block]:
    used = [names.get(pid, "Eintrag nicht mehr aktiv") for pid in (e.processor_ids or [])]
    out = [
        Block("h3", e.name),
        Block("item", f"Zweck: {e.purpose or 'nicht erfasst'}"),
        Block("item", f"Rechtsgrundlage (Eintrag des Betreibers): {e.legal_basis or 'offen'}"),
    ]
    out += [
        Block("item", f"Rolle {ACTOR_LABELS[actor]}: {ROLE_LABELS.get(role, role)}")
        for actor, role in roles_of(e).items()
    ]
    if e.responsibility_note:
        out.append(Block("item", f"Hinweis zur Verantwortlichkeit: {e.responsibility_note}"))
    out += [
        Block("item", f"Kategorien personenbezogener Daten: {_join(e.data_categories or [])}"),
        Block("item", f"Kategorien betroffener Personen: {_join(e.data_subjects or [])}"),
        Block("item", f"Empfänger: {e.recipients or 'nicht erfasst'}"),
        Block("item", f"Eingesetzte Auftragsverarbeiter: {_join(used)}"),
        Block("item", f"Drittlandübermittlung: {_third(e)}"),
        Block("item", f"Löschfristen: {e.retention_note or 'nicht erfasst'}"),
        Block("item", f"Prüfstatus Rechtsanwalt: {_review(e)}"),
    ]
    return out


def _origin(e: PrivacyRegisterEntry, detected_keys: set[str] | None) -> str:
    if not e.source_key:
        return "manuell erfasst"
    if detected_keys is not None and e.source_key not in detected_keys:
        return "aus Konfiguration übernommen, in der aktuellen Konfiguration nicht mehr gefunden"
    return "aus Konfiguration übernommen"


def blocks(
    tenant_name: str,
    entries: list[PrivacyRegisterEntry],
    today: date,
    detected: list[DetectedSource] | None = None,
) -> list[Block]:
    active = [e for e in entries if e.active]
    names = {e.id: e.name for e in active}
    detected_keys = {d.key for d in detected} if detected is not None else None
    out = [
        Block("title", "Verzeichnis von Verarbeitungstätigkeiten (Entwurf)"),
        Block("text", f"Erstellt für Mandant: {tenant_name}"),
        Block("text", f"Stand: {_fmt(today)}"),
        Block("notice", REVIEW_NOTICE),
        Block("text", MAINTENANCE_NOTICE),
        Block("h2", "1. Verarbeitungstätigkeiten"),
    ]
    acts = [e for e in active if e.kind == "processing_activity"]
    for e in acts:
        out += _activity(e, names)
    if not acts:
        out.append(Block("text", "Keine Verarbeitungstätigkeit erfasst."))
    out.append(Block("h2", "2. Verantwortlichkeiten"))
    resp = [e for e in active if e.kind == "responsibility"]
    out += [
        Block("item", f"{e.name} ({e.role or 'Rolle offen'}): {e.purpose or 'nicht erfasst'}")
        for e in resp
    ] or [Block("text", "Keine Verantwortlichkeit erfasst.")]
    out.append(Block("h2", "3. Auftragsverarbeiter und Unterauftragnehmer"))
    procs = [e for e in active if e.kind in ("processor", "sub_processor")]
    for e in procs:
        kind = "Unterauftragnehmer" if e.kind == "sub_processor" else "Auftragsverarbeiter"
        avv = _AVV[e.avv_status] + (f" am {_fmt(e.avv_confirmed_on)}" if e.avv_confirmed_on else "")
        out.append(
            Block(
                "item",
                f"{e.name} ({kind}), Zweck: {e.purpose or 'nicht erfasst'}, AVV: {avv}, "
                f"Drittland: {_third(e)}, Herkunft: {_origin(e, detected_keys)}",
            )
        )
        if e.source_detail:
            out.append(Block("item", f"Technische Angaben zu {e.name}: {e.source_detail}"))
    if not procs:
        out.append(Block("text", "Kein Auftragsverarbeiter erfasst."))
    missing: list[DetectedSource] = []
    if detected is not None:
        out.append(Block("h2", "4. Anbieter laut Konfiguration ohne Registereintrag"))
        known = {e.source_key for e in entries if e.source_key}
        missing = [d for d in detected if d.key not in known]
        out += [Block("item", f"{d.name}: {d.service}. {d.detail_text}") for d in missing] or [
            Block("text", "Alle erkannten Anbieter sind im Register erfasst.")
        ]
    out.append(Block("h2", "5. Offene Punkte" if detected is not None else "4. Offene Punkte"))
    gaps = [f"{e.name}: AVV-Nachweis fehlt" for e in procs if e.avv_status in ("none", "requested")]
    gaps += [
        f"{e.name}: Drittlandübermittlung ungeklärt"
        for e in procs + acts
        if third_country_status(e) == "open"
    ]
    gaps += [
        f"{e.name}: Drittlandübermittlung ohne dokumentierte Garantie"
        for e in active
        if third_country_status(e) == "yes" and not e.third_country_note
    ]
    gaps += [f"{e.name}: Rechtsgrundlage nicht erfasst" for e in acts if not e.legal_basis]
    for e in acts:
        open_roles = [ACTOR_LABELS[a] for a, r in roles_of(e).items() if r == "open"]
        if open_roles:
            gaps.append(f"{e.name}: Rolle offen für {', '.join(open_roles)}")
    gaps += [f"{d.name}: laut Konfiguration genutzt, kein Registereintrag" for d in missing]
    unreviewed = sum(1 for e in active if e.legal_review_status != "reviewed")
    if unreviewed:
        gaps.append(f"{unreviewed} Einträge ohne rechtliche Prüfung")
    out += [Block("item", g) for g in gaps] or [
        Block("text", "Keine offenen Punkte aus dem Register erkennbar.")
    ]
    return out


def to_markdown(items: list[Block]) -> str:
    lines: list[str] = []
    prefix = {"title": "# ", "h2": "## ", "h3": "### ", "item": "- "}
    for b in items:
        if b.kind == "item":
            lines.append(f"- {b.text}")
            continue
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"**{b.text}**" if b.kind == "notice" else prefix.get(b.kind, "") + b.text)
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def render(
    tenant_name: str,
    entries: list[PrivacyRegisterEntry],
    today: date,
    detected: list[DetectedSource] | None = None,
) -> str:
    return to_markdown(blocks(tenant_name, entries, today, detected))


def render_pdf(
    tenant_name: str,
    entries: list[PrivacyRegisterEntry],
    today: date,
    detected: list[DetectedSource] | None = None,
) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Verzeichnis von Verarbeitungstätigkeiten (Entwurf)",
        author=tenant_name,
    )
    styles = {
        "title": ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=14, leading=18),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, leading=14),
        "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=9.5, leading=12),
        "notice": ParagraphStyle("n", fontName="Helvetica-Bold", fontSize=9, leading=11),
        "text": ParagraphStyle("p", fontName="Helvetica", fontSize=8.5, leading=11),
        "item": ParagraphStyle(
            "i", fontName="Helvetica", fontSize=8.5, leading=11, leftIndent=8, bulletIndent=0
        ),
    }
    story: list[Any] = []
    for b in blocks(tenant_name, entries, today, detected):
        if b.kind in ("h2", "h3"):
            story.append(Spacer(1, 3 * mm))
        style = styles.get(b.kind, styles["text"])
        bullet = "-" if b.kind == "item" else None
        story.append(Paragraph(escape(b.text), style, bulletText=bullet))

    def _footer(canvas: Canvas, _doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(18 * mm, 10 * mm, f"ENTWURF, zu prüfen (V13). Stand {_fmt(today)}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Seite {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
