"""Procedure documentation as a draft generated from the operation (7.7 Absatz 3, M18-07).

Fills a Markdown text per legal entity with facts that the database proves: ledger settings,
chart of accounts, numbering, posting volume, reversals, receipt links, approvals, exports,
DATEV mapping state and the release gates of the tenant. Everything else stays marked
``[zu ergänzen]``. The text is a working basis for the tax advisor, not a release and no
statement about conformity with GoBD (docs/handbuch/verfahrensdokumentation.md holds the
static system description).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import (
    DatevAccountMapping,
    EntryKind,
    EntryStatus,
    ExportRun,
    JournalEntry,
    Ledger,
    LedgerAccount,
)
from mhvp.core.release_gates import GATE_LABELS, ReleaseGate, ReleaseGateResolver
from mhvp.workspace.services import local_today

TODO = "[zu ergänzen]"


def _d(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else "nicht gesetzt"


async def collect_facts(
    session: AsyncSession, ledger: Ledger, resolver: ReleaseGateResolver
) -> dict[str, Any]:
    from mhvp.properties.models import LegalEntity

    entity = await session.get(LegalEntity, ledger.legal_entity_id)
    posted = (
        await session.execute(
            select(
                func.count(JournalEntry.id),
                func.min(JournalEntry.booking_date),
                func.max(JournalEntry.booking_date),
                func.count(JournalEntry.document_id),
                func.count(JournalEntry.approved_by),
            ).where(JournalEntry.ledger_id == ledger.id, JournalEntry.status == EntryStatus.POSTED)
        )
    ).one()
    drafts = await session.scalar(
        select(func.count(JournalEntry.id)).where(
            JournalEntry.ledger_id == ledger.id, JournalEntry.status == EntryStatus.DRAFT
        )
    )
    reversals = await session.scalar(
        select(func.count(JournalEntry.id)).where(
            JournalEntry.ledger_id == ledger.id,
            JournalEntry.status == EntryStatus.POSTED,
            JournalEntry.kind == EntryKind.REVERSAL,
        )
    )
    years = (
        await session.execute(
            select(JournalEntry.fiscal_year, func.max(JournalEntry.number), func.count())
            .where(JournalEntry.ledger_id == ledger.id, JournalEntry.status == EntryStatus.POSTED)
            .group_by(JournalEntry.fiscal_year)
            .order_by(JournalEntry.fiscal_year)
        )
    ).all()
    categories = (
        await session.execute(
            select(LedgerAccount.category, func.count())
            .where(LedgerAccount.ledger_id == ledger.id)
            .group_by(LedgerAccount.category)
            .order_by(LedgerAccount.category)
        )
    ).all()
    exports = (
        await session.execute(
            select(ExportRun.format, func.count(), func.max(ExportRun.created_at))
            .where(ExportRun.ledger_id == ledger.id)
            .group_by(ExportRun.format)
            .order_by(ExportRun.format)
        )
    ).all()
    mappings = await session.scalar(select(func.count(DatevAccountMapping.id)))
    gates: dict[str, bool] = {}
    for gate in ReleaseGate:
        gates[gate.value] = await resolver.is_open(ledger.tenant_id, gate)
    return {
        "entity": entity,
        "posted": posted,
        "drafts": int(drafts or 0),
        "reversals": int(reversals or 0),
        "years": years,
        "categories": categories,
        "exports": exports,
        "mappings": int(mappings or 0),
        "gates": gates,
    }


def render(ledger: Ledger, facts: dict[str, Any], generated: datetime | None = None) -> str:
    entity = facts["entity"]
    count, first, last, with_document, approved = facts["posted"]
    lines: list[str] = []
    add = lines.append
    add(f"# Verfahrensdokumentation Buchführung, Entwurf ({ledger.name})")
    add("")
    stamp = generated.strftime("%d.%m.%Y %H:%M UTC") if generated else _d(local_today())
    add(
        f"Datenstand: {stamp}. Entwurf, aus dem Betrieb erzeugt. Keine steuerliche oder "
        "rechtliche Freigabe und keine Aussage zur Konformität mit den GoBD. Die statische "
        "Systembeschreibung steht in `docs/handbuch/verfahrensdokumentation.md`. Angaben, "
        f"die das System nicht belegt, sind mit {TODO} gekennzeichnet."
    )
    add("")
    add("## 1. Rechtsträger und Buchungskreis")
    add("")
    add(f"* Rechtsträger: {entity.name if entity else TODO}")
    if entity is not None:
        kind = entity.kind.value if hasattr(entity.kind, "value") else str(entity.kind)
        add(f"* Art des Rechtsträgers: {kind}")
    add(f"* Buchungskreis: {ledger.name} (ein Buchungskreis je Rechtsträger)")
    add(f"* Geschäftsjahr beginnt im Monat: {ledger.fiscal_year_start_month}")
    add(f"* Umsatzsteuermodus des Buchungskreises: {ledger.vat_mode.value}")
    add(f"* Festgeschrieben bis: {_d(ledger.locked_until)}")
    add(f"* Führendes System: {ledger.leading_system.value}")
    add(f"* Stichtag der Systemumstellung: {_d(ledger.migration_cutoff)}")
    add("")
    add("## 2. Kontenrahmen")
    add("")
    if ledger.template_id:
        add(f"* Vorlage: Version {ledger.template_version}, Freigabe durch Steuerberater {TODO}")
    else:
        add(f"* Vorlage: keine zugeordnet, Herkunft des Kontenrahmens {TODO}")
    for category, number in facts["categories"]:
        add(f"* Konten der Kategorie {category.value}: {number}")
    add("")
    add("## 3. Buchungen und Nummernvergabe")
    add("")
    add(f"* Gebuchte Sätze: {count}, Buchungstage von {_d(first)} bis {_d(last)}")
    add(f"* Entwürfe (keine Buchung): {facts['drafts']}")
    add(f"* Stornobuchungen: {facts['reversals']}")
    add(
        "* Nummernvergabe: lückenlos je Buchungskreis und Geschäftsjahr, Sperre der Zählerzeile "
        "beim Buchen (Regel B04)."
    )
    for year, last_number, n in facts["years"]:
        add(f"  * Geschäftsjahr {year}: höchste Nummer {last_number}, {n} Sätze")
    add(
        "* Änderung: Gebuchte Sätze werden weder überschrieben noch gelöscht, Korrektur nur durch "
        "Storno und gegebenenfalls Neubuchung (Regeln B02, B03)."
    )
    add("")
    add("## 4. Belege und Freigaben")
    add("")
    add(f"* Gebuchte Sätze mit verknüpftem Originalbeleg: {with_document} von {count}")
    add(f"* Gebuchte Sätze mit zweiter Person als Freigabe: {approved}")
    add(f"* Freigabeverfahren je Belegart und Betragsgrenzen: {TODO}")
    add("")
    add("## 5. Auswertungen und Exporte")
    add("")
    if facts["exports"]:
        for fmt, n, latest in facts["exports"]:
            add(f"* Export {fmt}: {n} Läufe, letzter am {_d(latest.date() if latest else None)}")
    else:
        add("* Bisher keine Exporte für diesen Buchungskreis.")
    add(f"* DATEV-Kontenzuordnungen des Mandanten: {facts['mappings']}")
    add(
        "* Datenträgerformat für die Datenüberlassung an die Finanzverwaltung: nicht festgelegt, "
        f"Entscheidung des Steuerberaters {TODO}"
    )
    add("")
    add("## 6. Freigabestufen des Mandanten")
    add("")
    for gate, is_open in facts["gates"].items():
        label = GATE_LABELS[ReleaseGate(gate)]
        add(f"* {gate} {label}: {'freigegeben' if is_open else 'gesperrt'}")
    add("")
    add("## 7. Offene Punkte")
    add("")
    for item in (
        "Aufbewahrungsfristen und Löschkonzept je Belegart",
        "Zugriffsberechtigungen und Rollenkonzept für diesen Rechtsträger",
        "Datensicherung, Wiederherstellungstest und Protokollierung",
        "Abstimmung mit dem Steuerberater und Freigabe der Verfahrensdokumentation",
    ):
        add(f"* {item}: {TODO}")
    add("")
    return "\n".join(lines)
