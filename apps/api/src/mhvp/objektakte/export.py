"""Objektakte export for the successor manager (M12 gaps, 29.09.2026; handbook page
anleitung-verwalterwechsel.md, section Abgabe eines Objekts).

One ZIP per run, built by the Celery job ``mhvp.objektakte.export_property`` and filed as a
generated document of the property (``ObjektakteExport.document_id``):

* ``01_Dokumente/<Kategorie>/<Dateiname>``: every document linked to the property, grouped by
  its category (folder name from the category code and name). Documents that only exist in
  Google Drive (takeover documents without a local blob) are listed in the log, not copied.
* ``02_Stammdaten/*.csv``: units, owners, tenants (current contracts, contact data as shown in
  the CRM: name, address, e-mail, phone; no bank data), contracts with their standing amounts
  on the export day, meters.
* ``03_Offene_Posten/offene_posten.csv``: open items of the property's ledgers on the export
  day (``mhvp.accounting.services.open_items``), amounts as recorded; the list is a copy of
  the CRM state, it settles nothing.
* ``04_Uebergabe/uebergabeprotokoll.txt``: termination record, checklist of the manager
  change, export metadata and the personal data note.

Data protection (rule 0.1.3 and 0.1.13): only what the successor needs to continue the
management. Excluded on purpose: internal notes of the property (``Property.notes``),
internal ticket comments and tickets altogether, bank accounts and IBANs, portal accounts,
AI proposals, the notice document's internal remarks, and every document of another
property. The person who requests the export confirms this note.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Party
from mhvp.contracts.models import Contract, ContractPayment
from mhvp.core.escaping import sanitize_filename
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import (
    Document,
    DocumentCategory,
    DocumentLink,
    DocumentSource,
    LinkRole,
    StorageKind,
)
from mhvp.documents.services import store_document
from mhvp.objektakte.lists import persons_csv, persons_list, to_csv
from mhvp.objektakte.models import ObjektakteExport, ObjektakteExportStatus
from mhvp.properties.models import Meter, Property, PropertyTermination, Unit
from mhvp.workspace.models import PropertyChecklist

_LOCAL = ZoneInfo("Europe/Berlin")
EXPORT_CATEGORY_CODE = "objektakte_export"
EXPORT_CATEGORY_NAME = "Objektakte-Export"
PERSONAL_DATA_NOTE = (
    "Datenschutzhinweis: Der Export enthält personenbezogene Daten der Eigentümer und Mieter "
    "(Name, Anschrift, E-Mail, Telefon, Vertragsdaten) und die Unterlagen der Objektakte. Er "
    "ist nur für die Weitergabe an den nachfolgenden Verwalter bestimmt und auf das "
    "beschränkt, was dieser zur Fortführung der Verwaltung benötigt. Nicht enthalten sind "
    "interne Notizen, Tickets und Kommentare, Bankverbindungen, Portalzugänge und "
    "KI-Vorschläge. Weitergabe nur über einen gesicherten Weg; Empfang dokumentieren."
)

UNITS_HEADER = (
    "Einheit",
    "Bezeichnung",
    "Art",
    "Gebäude",
    "Lage",
    "Etage",
    "Zimmer",
    "Wohnfläche m²",
    "Gesamtfläche m²",
)
CONTRACTS_HEADER = (
    "Vertragsnummer",
    "Art",
    "Einheit",
    "Partei",
    "Beginn",
    "Ende",
    "Zahlungsart",
    "Netto",
    "USt %",
    "Brutto",
    "Gültig ab",
    "Gültig bis",
)
METERS_HEADER = (
    "Zählernummer",
    "Zählerart",
    "Einheit",
    "Bezeichnung",
    "Lage",
    "Eichung fällig",
    "Fernablesbar",
    "Gültig ab",
    "Gültig bis",
)
OPEN_ITEMS_HEADER = (
    "Buchungskreis",
    "Konto",
    "Art",
    "Buchungsdatum",
    "Fälligkeit",
    "Betrag",
    "Offen",
    "Vertragsnummer",
)


@dataclass
class ExportResult:
    data: bytes
    counts: dict[str, int] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)


def _d(value: Any) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def _folder(code: str | None, name: str | None) -> str:
    raw = " ".join(p for p in (code, name) if p) or "Ohne Kategorie"
    cleaned, _ = sanitize_filename(raw.replace("/", "_"))
    return cleaned[:80]


async def _documents(
    session: AsyncSession, blobs: BlobStore, property_row: Property, result: ExportResult
) -> list[tuple[str, bytes]]:
    stmt = (
        select(Document, DocumentCategory)
        .join(DocumentLink, DocumentLink.document_id == Document.id)
        .outerjoin(DocumentCategory, DocumentCategory.id == Document.category_id)
        .where(
            DocumentLink.entity_type == "property",
            DocumentLink.entity_id == property_row.id,
        )
        .order_by(DocumentCategory.sort_order.nulls_last(), Document.title, Document.id)
    )
    files: list[tuple[str, bytes]] = []
    seen: set[uuid.UUID] = set()
    used: set[str] = set()
    for document, category in (await session.execute(stmt)).all():
        if document.id in seen:
            continue
        seen.add(document.id)
        if category is not None and category.code == EXPORT_CATEGORY_CODE:
            continue  # earlier exports are not nested into the next one
        if document.storage is not StorageKind.MINIO:
            result.log.append(
                f"Nicht enthalten (nur in Google Drive): {document.title} ({document.filename})"
            )
            result.counts["documents_skipped"] = result.counts.get("documents_skipped", 0) + 1
            continue
        try:
            data = blobs.get(document.storage_ref)
        except Exception as exc:
            result.log.append(f"Nicht lesbar: {document.title} ({type(exc).__name__})")
            result.counts["documents_skipped"] = result.counts.get("documents_skipped", 0) + 1
            continue
        folder = _folder(category.code if category else None, category.name if category else None)
        name, _ = sanitize_filename(document.filename)
        path = f"01_Dokumente/{folder}/{name}"
        if path in used:
            stem, dot, ext = name.rpartition(".")
            suffix = str(document.id)[-8:]
            path = f"01_Dokumente/{folder}/{stem or ext}_{suffix}{dot}{ext if stem else ''}"
        used.add(path)
        files.append((path, data))
    result.counts["documents"] = len(files)
    return files


async def _units_csv(session: AsyncSession, property_row: Property, result: ExportResult) -> str:
    from mhvp.properties.models import Building

    rows = []
    stmt = (
        select(Unit, Building)
        .outerjoin(Building, Building.id == Unit.building_id)
        .where(Unit.property_id == property_row.id)
        .order_by(Unit.number)
    )
    for unit, building in (await session.execute(stmt)).all():
        rows.append(
            (
                unit.number,
                unit.label,
                unit.unit_type.value,
                building.name if building else "",
                unit.location,
                unit.floor,
                unit.rooms,
                unit.living_area_sqm,
                unit.total_area_sqm,
            )
        )
    result.counts["units"] = len(rows)
    return to_csv(UNITS_HEADER, rows)


async def _contracts_csv(
    session: AsyncSession, property_row: Property, today: Any, result: ExportResult
) -> str:
    rows: list[tuple[Any, ...]] = []
    stmt = (
        select(Contract, Unit, Party)
        .join(Unit, Unit.id == Contract.unit_id)
        .join(Party, Party.id == Contract.party_id)
        .where(
            Contract.property_id == property_row.id,
            or_(Contract.end_date.is_(None), Contract.end_date >= today),
        )
        .order_by(Unit.number, Contract.start_date, Contract.id)
    )
    for contract, unit, party in (await session.execute(stmt)).all():
        payments = list(
            await session.scalars(
                select(ContractPayment)
                .where(
                    ContractPayment.contract_id == contract.id,
                    ContractPayment.valid_from <= today,
                    or_(ContractPayment.valid_to.is_(None), ContractPayment.valid_to >= today),
                )
                .order_by(ContractPayment.payment_type_code)
            )
        )
        base = (
            contract.number,
            contract.kind.value,
            unit.number,
            party.name,
            _d(contract.start_date),
            _d(contract.end_date),
        )
        if not payments:
            rows.append((*base, "", "", "", "", "", ""))
        for p in payments:
            rows.append(
                (
                    *base,
                    p.payment_type_code,
                    p.net,
                    p.vat_percent,
                    p.gross,
                    _d(p.valid_from),
                    _d(p.valid_to),
                )
            )
    result.counts["contracts"] = len({r[0] for r in rows})
    return to_csv(CONTRACTS_HEADER, rows)


async def _meters_csv(session: AsyncSession, property_row: Property, result: ExportResult) -> str:
    rows = []
    stmt = (
        select(Meter, Unit)
        .outerjoin(Unit, Unit.id == Meter.unit_id)
        .where(Meter.property_id == property_row.id)
        .order_by(Meter.number)
    )
    for meter, unit in (await session.execute(stmt)).all():
        rows.append(
            (
                meter.number,
                meter.meter_type_code,
                unit.number if unit else "",
                meter.name,
                meter.location,
                _d(meter.calibration_due_date),
                "ja" if meter.remote_readable else "nein",
                _d(meter.valid_from),
                _d(meter.valid_to),
            )
        )
    result.counts["meters"] = len(rows)
    return to_csv(METERS_HEADER, rows)


async def _open_items_csv(
    session: AsyncSession, property_row: Property, today: Any, result: ExportResult
) -> str:
    from mhvp.accounting import services as acc
    from mhvp.accounting.models import Ledger
    from mhvp.properties.models import LegalEntity

    rows = []
    entity_ids = list(
        await session.scalars(
            select(LegalEntity.id).where(LegalEntity.property_id == property_row.id)
        )
    )
    ledgers = list(
        await session.scalars(
            select(Ledger).where(
                or_(Ledger.property_id == property_row.id, Ledger.legal_entity_id.in_(entity_ids))
            )
        )
    )
    contract_numbers: dict[uuid.UUID, str] = {
        row[0]: row[1]
        for row in (await session.execute(select(Contract.id, Contract.number))).all()
    }
    for ledger in ledgers:
        for item in await acc.open_items(session, ledger, today):
            rows.append(
                (
                    ledger.name,
                    item["account_number"],
                    item["kind"],
                    _d(item["booking_date"]),
                    _d(item["due_date"]),
                    item["amount"],
                    item["remaining"],
                    contract_numbers.get(item["contract_id"], ""),
                )
            )
    result.counts["open_items"] = len(rows)
    result.counts["ledgers"] = len(ledgers)
    return to_csv(OPEN_ITEMS_HEADER, rows)


async def _handover_log(
    session: AsyncSession,
    property_row: Property,
    export: ObjektakteExport,
    requested_by_name: str | None,
    result: ExportResult,
) -> str:
    termination = await session.scalar(
        select(PropertyTermination)
        .where(PropertyTermination.property_id == property_row.id)
        .order_by(PropertyTermination.created_at.desc())
        .limit(1)
    )
    lines = [
        f"Übergabeprotokoll Objektakte {property_row.number} {property_row.name}",
        f"Erstellt am {datetime.now(_LOCAL).strftime('%d.%m.%Y %H:%M')} durch "
        f"{requested_by_name or 'unbekannt'} (Export {export.id})",
        "",
        "Verwaltung:",
        f"  Verwaltungsart: {property_row.management_type.value}",
        f"  Verwaltung von {_d(property_row.managed_from)} bis {_d(property_row.managed_to)}",
    ]
    if termination is not None:
        lines += [
            "",
            "Beendigung:",
            f"  Gekündigt von: {termination.terminated_by.value}",
            f"  Kündigungsdatum: {_d(termination.notice_date)}",
            f"  Ende der Verwaltung: {_d(termination.effective_date)}",
        ]
        for label, contact_id in (
            ("Nachfolgender Verwalter", termination.successor_manager_contact_id),
            ("Nachfolgender Eigentümer", termination.successor_owner_contact_id),
        ):
            if contact_id is not None:
                from mhvp.contacts.models import Contact

                contact = await session.get(Contact, contact_id)
                lines.append(f"  {label}: {contact.display_name if contact else contact_id}")
    else:
        lines += ["", "Beendigung: keine Beendigung erfasst."]
    checklists = list(
        await session.scalars(
            select(PropertyChecklist)
            .where(PropertyChecklist.property_id == property_row.id)
            .order_by(PropertyChecklist.created_at)
        )
    )
    if checklists:
        lines += ["", "Checklisten:"]
        for checklist in checklists:
            lines.append(f"  {checklist.kind}, Status {checklist.status}")
            for item in checklist.items:
                done = item.get("done_at")
                mark = "x" if done else " "
                who = f" ({item.get('done_by_name') or ''}, {str(done)[:10]})" if done else ""
                lines.append(f"    [{mark}] {item.get('label')}{who}")
    lines += ["", "Inhalt des Exports:"]
    for key, value in sorted(result.counts.items()):
        lines.append(f"  {key}: {value}")
    if result.log:
        lines += ["", "Hinweise:"] + [f"  {entry}" for entry in result.log]
    lines += ["", PERSONAL_DATA_NOTE, ""]
    return "\n".join(lines)


async def build_export(
    session: AsyncSession,
    blobs: BlobStore,
    *,
    property_row: Property,
    export: ObjektakteExport,
    requested_by_name: str | None,
) -> ExportResult:
    """Assemble the ZIP in memory (see module docstring)."""
    result = ExportResult(data=b"")
    today = datetime.now(_LOCAL).date()
    files = await _documents(session, blobs, property_row, result)
    sheets = {
        "02_Stammdaten/einheiten.csv": await _units_csv(session, property_row, result),
        "02_Stammdaten/vertraege.csv": await _contracts_csv(session, property_row, today, result),
        "02_Stammdaten/zaehler.csv": await _meters_csv(session, property_row, result),
    }
    for kind, name in (("owners", "eigentuemer"), ("tenants", "mieter")):
        listing = await persons_list(session, export.tenant_id, property_row, kind)  # type: ignore[arg-type]
        result.counts[kind] = int(listing["total"])
        sheets[f"02_Stammdaten/{name}.csv"] = persons_csv(listing)
    sheets["03_Offene_Posten/offene_posten.csv"] = await _open_items_csv(
        session, property_row, today, result
    )
    log = await _handover_log(session, property_row, export, requested_by_name, result)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, data in files:
            archive.writestr(path, data)
        for path, text in sheets.items():
            archive.writestr(path, text.encode("utf-8"))
        archive.writestr("04_Uebergabe/uebergabeprotokoll.txt", log.encode("utf-8"))
        archive.writestr("04_Uebergabe/datenschutzhinweis.txt", PERSONAL_DATA_NOTE.encode("utf-8"))
    result.data = buffer.getvalue()
    return result


async def export_category(session: AsyncSession, tenant_id: uuid.UUID) -> DocumentCategory:
    category = await session.scalar(
        select(DocumentCategory).where(DocumentCategory.code == EXPORT_CATEGORY_CODE)
    )
    if category is None:
        category = DocumentCategory(
            tenant_id=tenant_id,
            code=EXPORT_CATEGORY_CODE,
            name=EXPORT_CATEGORY_NAME,
            paperless_document_type=EXPORT_CATEGORY_NAME,
            drive_folder="06_Sonstiges",
            sort_order=98,
        )
        session.add(category)
        await session.flush()
    return category


async def run_export(
    session: AsyncSession, blobs: BlobStore, export: ObjektakteExport
) -> ObjektakteExport:
    """Build the ZIP for one export row inside the caller's tenant transaction and file it
    as a document of the property. Status ``failed`` with the error text on any failure."""
    from mhvp.platform.models import User

    export.status = ObjektakteExportStatus.RUNNING
    export.started_at = datetime.now(UTC)
    await session.flush()
    property_row = await session.get(Property, export.property_id)
    if property_row is None:
        export.status = ObjektakteExportStatus.FAILED
        export.error = "Objekt nicht gefunden."
        export.finished_at = datetime.now(UTC)
        return export
    name = (
        await session.scalar(select(User.display_name).where(User.id == export.requested_by))
        if export.requested_by
        else None
    )
    try:
        result = await build_export(
            session, blobs, property_row=property_row, export=export, requested_by_name=name
        )
        day = datetime.now(_LOCAL).date()
        category = await export_category(session, export.tenant_id)
        document = await store_document(
            session,
            blobs,
            tenant_id=export.tenant_id,
            data=result.data,
            title=f"Objektakte-Export {property_row.number} {property_row.name} {day:%d.%m.%Y}",
            filename=f"objektakte-export-{property_row.number}-{day.isoformat()}.zip",
            mime_type="application/zip",
            source=DocumentSource.GENERATED,
            category_id=category.id,
            links=[("property", property_row.id, LinkRole.GENERATED)],
            created_by=export.requested_by,
        )
        export.document_id = document.id
        export.counts = result.counts
        export.status = ObjektakteExportStatus.DONE
    except Exception as exc:
        export.status = ObjektakteExportStatus.FAILED
        export.error = f"{type(exc).__name__}: {exc}"[:1000]
    export.finished_at = datetime.now(UTC)
    await session.flush()
    return export
