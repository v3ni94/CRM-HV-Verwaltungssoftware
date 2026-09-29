"""Prozessflows für Tickets (Regel M19-11, Betreiberauftrag 29.09.2026).

Ein fester Katalog von zwölf Vorgangsarten (``PROCESS_CATALOGUE``): Kündigung, Vermietung,
Versicherungsschaden, Reparaturanfrage, Beschwerde, Buchhaltung, Übergabe, Mieterhöhung,
Gericht, Übernahme neues Objekt, Abgabe altes Objekt, Kaution. Jede Art beschreibt Checkliste,
zuständige Rolle, erforderliche Verknüpfungen (Kontakt, Einheit, Objekt, Vertrag), verknüpfte
Fristtypen (nur Codes aus ``mhvp.workspace.jobs.DEADLINE_KINDS``, nie eine Dauer) und die zu
sammelnden Unterlagen. Die Schritte stammen aus den Handlungsanweisungen in
``docs/handbuch/anleitung-*.md``; wo es keine gibt, aus einer kurzen sachlichen Liste ohne
rechtliche Aussagen.

Der Katalog wird je Mandant als ``TicketTemplate`` mit ``process_code`` eingespielt
(``seed_process_templates``, idempotent) und dort in der bestehenden Vorlagenverwaltung
bearbeitet. ``apply_flow`` überträgt den Flow der Vorlage auf ein Ticket: Kategorie, Checkliste
(einmalig), zuständige Rolle, Verknüpfungsstatus, Fristvorschläge (nur Vorschlag, keine
Frist wird angelegt, die Dauer trägt der Bearbeiter ein) und Unterlagenliste. Nichts wird
abgeschlossen, nichts gebucht (Regeln 0.1.6 und 0.1.7).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.tickets.models import Ticket, TicketEvent, TicketTemplate

PROCESS_CODES: tuple[str, ...] = (
    "kuendigung",
    "vermietung",
    "versicherungsschaden",
    "reparaturanfrage",
    "beschwerde",
    "buchhaltung",
    "uebergabe",
    "mieterhoehung",
    "gericht",
    "objektuebernahme",
    "objektabgabe",
    "kaution",
)
LINK_KINDS: tuple[str, ...] = ("contact", "unit", "property", "contract")
FLOW_EVENT = "flow_applied"


class ProcessDefinition(TypedDict):
    code: str
    label: str
    title: str
    description: str
    checklist: list[str]
    responsible_role: str
    required_links: list[str]
    deadline_type_codes: list[str]
    document_kinds: list[str]


def _p(
    code: str,
    label: str,
    description: str,
    checklist: list[str],
    *,
    role: str,
    links: list[str],
    deadlines: list[str],
    documents: list[str],
) -> ProcessDefinition:
    return {
        "code": code,
        "label": label,
        "title": label,
        "description": description,
        "checklist": checklist,
        "responsible_role": role,
        "required_links": links,
        "deadline_type_codes": deadlines,
        "document_kinds": documents,
    }


# Schritte nach docs/handbuch/anleitung-mieterwechsel.md (Kündigung, Übergabe, Kaution,
# Vermietung), anleitung-mieterhoehung.md, anleitung-verwalterwechsel.md (Übernahme, Abgabe).
# Fristtypen nur als Codes der Fristenliste; Dauern trägt der Bearbeiter ein (M1-09).
PROCESS_CATALOGUE: tuple[ProcessDefinition, ...] = (
    _p(
        "kuendigung",
        "Kündigung",
        "Kündigung eines Mietverhältnisses durch Mieter oder Vermieter.",
        [
            "Kündigungsschreiben in der Mieterakte ablegen",
            "Kontakt des Mieters und Einheit am Ticket verknüpfen",
            "Vertrag beenden: Vertragsende, Datum der Kündigungserklärung, Grund, Auszug",
            "Kündigungsfrist durch Rechtsanwalt prüfen lassen, Ergebnis im Ticket vermerken",
            "Kündigung der Vermieterseite vor Abgabe durch die Geschäftsführung freigeben",
            "Rückgabetermin abstimmen und Übergabe vorbereiten",
            "Messdienstleister informieren, Leerstand und Portalzugang prüfen",
        ],
        role="standard",
        links=["contact", "unit", "property", "contract"],
        deadlines=["contract_termination", "contract_end", "move_out"],
        documents=["Kündigungsschreiben", "Zugangsnachweis", "Kündigungsbestätigung"],
    ),
    _p(
        "vermietung",
        "Vermietung",
        "Neuvermietung einer Einheit und Anlage des neuen Mieters.",
        [
            "Kontakt des neuen Mieters anlegen, Rolle Mieter",
            "Bankverbindung nur mit Nachweis erfassen, Freigabe durch zweite Person",
            "Mietvertrag anlegen: Beginn, Zahlungsplan, Kaution, Umsatzsteuer, Lastschrift",
            "Umlagewerte der Einheit erfassen, zum Beispiel Personenzahl",
            "Unterschriebenen Mietvertrag in der Mieterakte ablegen",
            "Portaleinladung erzeugen",
            "Übergabe an den neuen Mieter mit Protokoll durchführen",
        ],
        role="standard",
        links=["contact", "unit", "property", "contract"],
        deadlines=["move_in"],
        documents=["Mietvertrag unterschrieben", "Selbstauskunft", "SEPA-Mandat"],
    ),
    _p(
        "versicherungsschaden",
        "Versicherungsschaden",
        "Schaden am Gebäude oder in einer Einheit mit Meldung an den Versicherer.",
        [
            "Schadensmeldung mit Datum, Ort und Hergang aufnehmen",
            "Fotos und Belege am Ticket ablegen",
            "Objekt und Einheit verknüpfen",
            "Versicherer und Vertragsnummer aus der Objektakte ermitteln",
            "Schaden beim Versicherer melden, Schadennummer vermerken",
            "Sofortmaßnahmen veranlassen, Arbeitsauftrag anlegen",
            "Kostenvoranschläge und Rechnungen sammeln",
            "Regulierung nachhalten",
        ],
        role="technical_clerk",
        links=["property", "unit", "contact"],
        deadlines=["note_follow_up"],
        documents=[
            "Schadensmeldung",
            "Fotos",
            "Kostenvoranschlag",
            "Rechnung",
            "Schreiben des Versicherers",
        ],
    ),
    _p(
        "reparaturanfrage",
        "Reparaturanfrage",
        "Mangel oder Reparaturwunsch eines Bewohners oder Eigentümers.",
        [
            "Mangel, Ort und Dringlichkeit erfassen",
            "Objekt, Einheit und Kontakt verknüpfen",
            "Zuständigkeit klären: Gemeinschaft, Eigentümer oder Mieter",
            "Dienstleister auswählen und Arbeitsauftrag anlegen",
            "Termin mit dem Bewohner abstimmen",
            "Ausführung und Rechnung prüfen",
            "Rückmeldung an den Melder",
        ],
        role="technical_clerk",
        links=["property", "unit", "contact"],
        deadlines=["note_follow_up"],
        documents=["Fotos", "Angebot", "Rechnung"],
    ),
    _p(
        "beschwerde",
        "Beschwerde",
        "Beschwerde über Nachbarn, Hausordnung, Dienstleister oder die Verwaltung.",
        [
            "Beschwerde und Beteiligte erfassen",
            "Objekt, Einheit und Kontakt verknüpfen",
            "Sachverhalt bei der Gegenseite abfragen",
            "Hausordnung und Vertrag prüfen",
            "Antwort an den Beschwerdeführer als Entwurf mit Freigabe",
            "Wiedervorlage setzen",
        ],
        role="standard",
        links=["contact", "property", "unit"],
        deadlines=["note_follow_up"],
        documents=["Beschwerdeschreiben", "Stellungnahme der Gegenseite"],
    ),
    _p(
        "buchhaltung",
        "Buchhaltung",
        "Rückfrage zu Zahlungen, Kontostand, Abrechnung oder Mahnung.",
        [
            "Anliegen einordnen: Zahlung, Kontostand, Abrechnung, Mahnung",
            "Kontakt, Objekt und Vertrag verknüpfen",
            "Kontostand und Buchungen prüfen",
            "Rückfrage an die Buchhaltung",
            "Antwort als Entwurf mit Freigabe",
            "Keine Buchung und keine Zahlung aus dem Ticket heraus",
        ],
        role="accountant_no_banking",
        links=["contact", "property", "contract"],
        deadlines=[],
        documents=["Kontoauszug des Kunden", "Rechnung", "Zahlungsbeleg"],
    ),
    _p(
        "uebergabe",
        "Übergabe",
        "Wohnungsübergabe bei Rückgabe oder Einzug mit Protokoll.",
        [
            "Übergabeprotokoll anlegen, Protokollart Wohnungsübergabe",
            "Termin anlegen, Kalendertermin Übergabe",
            "Beteiligte, Kaution, Zähler, Räume, Mängel, Schlüssel, Gegenstände erfassen",
            "Unterschriften aller Beteiligten einholen",
            "Protokoll verbindlich abschließen und als Dokument ablegen",
            "Zustellung vorbereiten, Versand über den Postausgang mit Freigabe",
            "Zählerstände zusätzlich am Vertrag erfassen",
            "Protokollnummer im Ticket vermerken",
        ],
        role="standard",
        links=["unit", "property", "contact", "contract"],
        deadlines=["move_out", "move_in"],
        documents=["Übergabeprotokoll", "Fotos", "Zählerstände"],
    ),
    _p(
        "mieterhoehung",
        "Mieterhöhung",
        "Mieterhöhungsfall mit Prüfung, Freigabe und Übernahme in die Miethistorie.",
        [
            "Fall anlegen: Mietvertrag, Grundlage, Zielmiete, Wirksam ab",
            "Ausgangsmiete, Kappungsgrenze und Vergleichsmiete erfassen",
            "Begründungsmittel erfassen: Mietspiegel, Gutachten oder Vergleichswohnungen",
            "Rechnerisch prüfen",
            "Schreiben vorbereiten und rechtlich prüfen lassen, Prüfung ablegen",
            "Freigabe durch zweite Person",
            "Versand erfassen (Freigabestufe G3 erforderlich)",
            "Zustimmung oder Ablehnung erfassen",
            "In Miethistorie übernehmen",
        ],
        role="tenant_admin",
        links=["contract", "unit", "property", "contact"],
        deadlines=["note_follow_up"],
        documents=[
            "Mietspiegel oder Gutachten",
            "Mieterhöhungsschreiben",
            "Rechtliche Prüfung",
            "Zustimmung des Mieters",
        ],
    ),
    _p(
        "gericht",
        "Gericht",
        "Gerichtliches oder anwaltliches Schreiben mit Aktenzeichen.",
        [
            "Schreiben, Aktenzeichen und Zustelldatum erfassen",
            "Dokument ablegen und Löschsperre am Vorgang setzen",
            "Fristen mit dem Rechtsanwalt bestimmen und mit Vorfrist eintragen",
            "Rechtsanwalt beauftragen und Unterlagen übermitteln",
            "Verfahrenshandlungen nur nach Freigabe der Geschäftsführung",
            "Wiedervorlage setzen",
        ],
        role="tenant_admin",
        links=["contact", "property", "unit", "contract"],
        deadlines=["note_follow_up"],
        documents=["Gerichtliches Schreiben", "Zustellnachweis", "Vollmacht"],
    ),
    _p(
        "objektuebernahme",
        "Übernahme neues Objekt",
        "Übernahme eines Objekts von einer Vorverwaltung.",
        [
            "Verwaltungsart klären und Objekt anlegen, Verwaltungsbeginn eintragen",
            "Gebäude, Einheiten und Schlüsselwerte per Import anlegen und prüfen",
            "Kontakte anlegen, Dubletten prüfen, Rollen setzen",
            "Verträge anlegen, Importverträge durch die Geschäftsführung freigeben",
            "Bankkonten zuordnen, Standardkonto setzen, neue IBAN freigeben lassen",
            "Unterlagen der Vorverwaltung hochladen und im Objektordner ablegen",
            "Vollständigkeit prüfen, Nachforderungsschreiben freigeben und versenden",
            "Ticket mit Fälligkeit für die Herausgabe der Unterlagen führen",
            "Rechtliche Punkte durch Rechtsanwalt prüfen lassen",
        ],
        role="tenant_admin",
        links=["property", "contact"],
        deadlines=["ticket_due"],
        documents=[
            "Verwaltervertrag",
            "Bestellungsbeschluss",
            "Teilungserklärung",
            "Unterlagen der Vorverwaltung",
            "Nachforderungsschreiben",
        ],
    ),
    _p(
        "objektabgabe",
        "Abgabe altes Objekt",
        "Beendigung der Verwaltung eines Objekts und Übergabe an den Nachfolger.",
        [
            "Kündigung durch die Geschäftsführung freigeben",
            "Verwaltung beenden: Gekündigt von, Kündigungsdatum, Ende der Verwaltung, Nachfolger",
            "Kündigungsschreiben am Objekt ablegen",
            "Umfang und Frist der Herausgabe durch Rechtsanwalt prüfen lassen",
            "Unterlagen für den Nachfolger zusammenstellen",
            "Übergabe an den Nachfolger dokumentieren",
        ],
        role="tenant_admin",
        links=["property", "contact"],
        deadlines=["ticket_due"],
        documents=["Kündigungsschreiben", "Übergabeprotokoll Verwaltung", "Unterlagenliste"],
    ),
    _p(
        "kaution",
        "Kaution",
        "Kaution erfassen, prüfen oder abrechnen.",
        [
            "Kaution am Vertrag erfassen: Kautionsart, Betrag, Raten, Fällig ab",
            "Zahlungseingang der Kaution prüfen",
            "Bei Auszug Kautionsabrechnung erstellen: Abrechnungsdatum, Zinsart, Einbehalte",
            "Abrechnung als PDF erzeugen und am Vertrag ablegen",
            "Referenzzinssatz unter Einstellungen pflegen lassen, falls er fehlt",
            "Keine Auszahlung aus dem Ticket heraus (Freigabestufe G3)",
        ],
        role="accountant_no_banking",
        links=["contract", "contact", "unit"],
        deadlines=[],
        documents=["Kautionsnachweis", "Kautionsabrechnung"],
    ),
)
PROCESS_BY_CODE: dict[str, ProcessDefinition] = {p["code"]: p for p in PROCESS_CATALOGUE}
PROCESS_LABELS: dict[str, str] = {p["code"]: p["label"] for p in PROCESS_CATALOGUE}


def checklist_key(index: int, label: str) -> str:
    slug = "".join(ch if ch.isalnum() else "_" for ch in label.lower())
    slug = "_".join(part for part in slug.split("_") if part)[:40]
    return f"s{index + 1:02d}_{slug}"


def catalogue_checklist(process: ProcessDefinition) -> list[dict[str, Any]]:
    return [
        {"key": checklist_key(i, label), "label": label, "required": False}
        for i, label in enumerate(process["checklist"])
    ]


def template_values(process: ProcessDefinition) -> dict[str, Any]:
    """Field values of the seeded ``TicketTemplate`` for one catalogue entry."""
    return {
        "category": process["code"],
        "process_code": process["code"],
        "title": process["title"],
        "description": process["description"],
        "checklist": catalogue_checklist(process),
        "responsible_role": process["responsible_role"],
        "required_links": list(process["required_links"]),
        "deadline_type_codes": list(process["deadline_type_codes"]),
        "document_kinds": list(process["document_kinds"]),
    }


async def seed_process_templates(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, int]:
    """Idempotent per tenant: a template with the process code is kept as edited by the
    tenant; a template whose category equals the code but has no process code gets the code
    and the missing flow fields; otherwise the template is created."""
    created = updated = kept = 0
    for process in PROCESS_CATALOGUE:
        code = process["code"]
        existing = await session.scalar(
            select(TicketTemplate).where(
                TicketTemplate.tenant_id == tenant_id, TicketTemplate.process_code == code
            )
        )
        if existing is not None:
            kept += 1
            continue
        by_category = await session.scalar(
            select(TicketTemplate).where(
                TicketTemplate.tenant_id == tenant_id, TicketTemplate.category == code
            )
        )
        values = template_values(process)
        if by_category is not None:
            by_category.process_code = code
            if not by_category.checklist:
                by_category.checklist = values["checklist"]
            if not by_category.responsible_role:
                by_category.responsible_role = values["responsible_role"]
            if not by_category.required_links:
                by_category.required_links = values["required_links"]
            if not by_category.deadline_type_codes:
                by_category.deadline_type_codes = values["deadline_type_codes"]
            if not by_category.document_kinds:
                by_category.document_kinds = values["document_kinds"]
            updated += 1
            continue
        session.add(TicketTemplate(tenant_id=tenant_id, **values))
        created += 1
    await session.flush()
    return {"created": created, "updated": updated, "kept": kept}


async def template_for_process(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> TicketTemplate | None:
    tpl: TicketTemplate | None = await session.scalar(
        select(TicketTemplate).where(
            TicketTemplate.tenant_id == tenant_id,
            TicketTemplate.process_code == code,
            TicketTemplate.active.is_(True),
        )
    )
    return tpl


def link_status(ticket: Ticket, required: list[str], *, contract_id: Any = None) -> dict[str, bool]:
    """Which required links the ticket already carries. The ticket has no contract field of
    its own; a contract counts as present only when the caller resolved one."""
    present = {
        "contact": ticket.contact_id is not None,
        "unit": ticket.unit_id is not None,
        "property": ticket.property_id is not None,
        "contract": contract_id is not None,
    }
    return {kind: present.get(kind, False) for kind in required if kind in LINK_KINDS}


def instantiate_checklist(
    existing: list[dict[str, Any]], template_items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Existing items stay (with their done marks); template items are appended once by key."""
    keys = {str(item.get("key")) for item in existing}
    out = list(existing)
    for item in template_items:
        if str(item.get("key")) in keys:
            continue
        out.append(
            {
                "key": item["key"],
                "label": item["label"],
                "required": bool(item.get("required", False)),
                "done": False,
                "done_by": None,
                "done_at": None,
            }
        )
    return out


def build_flow(
    ticket: Ticket, tpl: TicketTemplate, *, source: str, contract_id: Any = None
) -> dict[str, Any]:
    required = [k for k in (tpl.required_links or []) if k in LINK_KINDS]
    return {
        "process_code": tpl.process_code,
        "label": PROCESS_LABELS.get(str(tpl.process_code), tpl.title),
        "template_id": str(tpl.id),
        "responsible_role": tpl.responsible_role,
        "required_links": required,
        "links": link_status(ticket, required, contract_id=contract_id),
        # Only proposals (M1-09): the type is fixed, date and duration are entered by the
        # member; nothing is written to the deadline list here.
        "deadline_proposals": [
            {"type": code, "status": "proposed", "due_on": None}
            for code in (tpl.deadline_type_codes or [])
        ],
        "document_kinds": list(tpl.document_kinds or []),
        "applied_at": datetime.now(UTC).isoformat(),
        "source": source,
    }


async def apply_flow(
    session: AsyncSession,
    ticket: Ticket,
    tpl: TicketTemplate,
    *,
    actor_user_id: uuid.UUID | None,
    source: str,
    contract_id: Any = None,
) -> bool:
    """Applies the template's flow to the ticket. Idempotent: a ticket that already carries
    this process code keeps its checklist marks and flow; only the link status is refreshed.
    Returns whether the flow was newly applied. Never changes the status, never posts."""
    if not tpl.process_code:
        raise ValueError("Vorlage ohne Prozesscode")
    if ticket.process_code == tpl.process_code and ticket.flow:
        flow = dict(ticket.flow)
        flow["links"] = link_status(ticket, flow.get("required_links", []), contract_id=contract_id)
        ticket.flow = flow
        return False
    ticket.process_code = tpl.process_code
    ticket.category = tpl.category
    if ticket.template_id is None:
        ticket.template_id = tpl.id
    if ticket.topic is None and tpl.topic:
        ticket.topic = tpl.topic
    if ticket.team_id is None and tpl.default_team_id is not None:
        ticket.team_id = tpl.default_team_id
    ticket.checklist = instantiate_checklist(list(ticket.checklist or []), list(tpl.checklist))
    ticket.flow = build_flow(ticket, tpl, source=source, contract_id=contract_id)
    session.add(
        TicketEvent(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            kind=FLOW_EVENT,
            user_id=actor_user_id,
            data={
                "process_code": tpl.process_code,
                "label": ticket.flow["label"],
                "responsible_role": tpl.responsible_role,
                "deadline_types": list(tpl.deadline_type_codes or []),
                "source": source,
            },
        )
    )
    await session.flush()
    return True
