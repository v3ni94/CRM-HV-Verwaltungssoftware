"""M35 Stufe 4, part "Listengenerierung" (docs/plans/M35-objektakte-uebernahme.md section 4):
lists generated per property from the objektakte data (documents, classification,
completeness check). Two list kinds:

* "Anforderungsliste": the missing mandatory document classes of a property, derived from
  `mhvp.objektakte.completeness.check_completeness` (same rule, no second definition of
  "missing"), plus an overview of the same across all properties of the tenant.
* "Dokumentenübersicht je Kategorie": every document linked to the property
  (`DocumentLink(entity_type="property")`) grouped by its `DocumentCategory`; unclassified
  documents form their own group so that nothing is hidden.

* Personenlisten (Stufe 4, Rest): "Eigentümerliste" and "Mieterliste" per property, derived
  from the contracts of the property (`Contract.kind` ownership or tenancy, current on the
  reference date) and the contacts behind the contract party. Only contact fields the CRM
  shows anyway (name, postal address, e-mail, phone), never bank data (rule 0.1.13,
  data minimisation).

Lists are computed on request; nothing is stored unless `store_list` is called explicitly.
`store_list` files the CSV as a `Document` (source generated, category "Liste", linked to the
property) through the regular document service, so retention, mirrors and the document
search apply unchanged. CSV export uses semicolon separators, CRLF line ends and a UTF-8 BOM
so that Excel in a German locale opens the file directly.
"""

from __future__ import annotations

import csv
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from io import StringIO
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import (
    Contact,
    ContactAddress,
    ContactEmail,
    ContactPhone,
    Party,
    PartyMember,
    PartyRole,
)
from mhvp.contracts.models import Contract, ContractKind
from mhvp.core.escaping import csv_safe_cell
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import (
    Document,
    DocumentCategory,
    DocumentLink,
    DocumentSource,
    LinkRole,
)
from mhvp.documents.services import store_document
from mhvp.objektakte.completeness import check_completeness
from mhvp.properties.models import ManagementType, Property, Unit

_LOCAL = ZoneInfo("Europe/Berlin")  # list dates, same choice as the letter date (M1-09 open)
UNCATEGORISED_CODE = ""
UNCATEGORISED_NAME = "Ohne Kategorie"
PersonListKind = Literal["owners", "tenants"]
PERSON_LIST_CONTRACT_KIND: dict[str, ContractKind] = {
    "owners": ContractKind.OWNERSHIP,
    "tenants": ContractKind.TENANCY,
}
# Party roles listed as persons of the contract; guarantors and legal representatives are
# not the owner or tenant themselves and stay out of the list.
PERSON_ROLES = (PartyRole.PRIMARY, PartyRole.CO_PARTY)
# Category the stored list documents are filed under (created on first use per tenant).
LIST_CATEGORY_CODE = "list"
LIST_CATEGORY_NAME = "Liste"


def _property_head(property_row: Property) -> dict[str, Any]:
    return {
        "property_id": str(property_row.id),
        "property_number": property_row.number,
        "property_name": property_row.name,
        "management_type": property_row.management_type.value,
    }


@dataclass
class DocumentRow:
    document_id: str
    title: str
    filename: str
    mime_type: str
    created_at: str
    source_system: str | None
    duplicate: bool


@dataclass
class CategoryGroup:
    category_id: str | None
    code: str
    name: str
    documents: list[DocumentRow] = field(default_factory=list)


async def missing_documents_list(
    session: AsyncSession, tenant_id: uuid.UUID, property_row: Property
) -> dict[str, Any]:
    """Anforderungsliste of one property: the missing mandatory classes (and, for context, the
    satisfied ones) as reported by the completeness check."""
    result = await check_completeness(session, tenant_id, property_row)
    return {
        **_property_head(property_row),
        "missing": [vars(m) for m in result.missing],
        "satisfied_count": len(result.satisfied),
        "complete": not result.missing,
    }


async def missing_documents_overview(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    management_type: ManagementType | None = None,
    only_incomplete: bool = False,
) -> list[dict[str, Any]]:
    """Anforderungsliste across all properties of the tenant (RLS limits the rows), ordered by
    property number. `only_incomplete` drops properties without missing classes."""
    stmt = select(Property).order_by(Property.number)
    if management_type is not None:
        stmt = stmt.where(Property.management_type == management_type)
    properties = (await session.execute(stmt)).scalars().all()
    rows: list[dict[str, Any]] = []
    for property_row in properties:
        entry = await missing_documents_list(session, tenant_id, property_row)
        if only_incomplete and entry["complete"]:
            continue
        rows.append(entry)
    return rows


async def documents_by_category(
    session: AsyncSession, tenant_id: uuid.UUID, property_row: Property
) -> dict[str, Any]:
    """Dokumentenübersicht: all documents linked to the property grouped by category, groups in
    category sort order, documents by title. Duplicates (`duplicate_of_id`) stay listed and are
    flagged, never dropped (rule 0.1.7)."""
    stmt = (
        select(Document, DocumentCategory)
        .join(DocumentLink, DocumentLink.document_id == Document.id)
        .outerjoin(DocumentCategory, DocumentCategory.id == Document.category_id)
        .where(
            Document.tenant_id == tenant_id,
            DocumentLink.entity_type == "property",
            DocumentLink.entity_id == property_row.id,
        )
        .order_by(
            DocumentCategory.sort_order.nulls_last(),
            DocumentCategory.code.nulls_last(),
            Document.title,
            Document.id,
        )
    )
    groups: dict[str | None, CategoryGroup] = {}
    seen: set[uuid.UUID] = set()
    for document, category in (await session.execute(stmt)).all():
        if document.id in seen:  # several links (roles) to the same property
            continue
        seen.add(document.id)
        key = str(category.id) if category is not None else None
        group = groups.get(key)
        if group is None:
            group = CategoryGroup(
                category_id=key,
                code=category.code if category is not None else UNCATEGORISED_CODE,
                name=category.name if category is not None else UNCATEGORISED_NAME,
            )
            groups[key] = group
        group.documents.append(
            DocumentRow(
                document_id=str(document.id),
                title=document.title,
                filename=document.filename,
                mime_type=document.mime_type,
                created_at=document.created_at.isoformat(),
                source_system=document.source_system,
                duplicate=document.duplicate_of_id is not None,
            )
        )
    ordered = sorted(groups.values(), key=lambda g: (g.category_id is None, g.code, g.name))
    return {
        **_property_head(property_row),
        "total": len(seen),
        "groups": [
            {
                "category_id": g.category_id,
                "code": g.code,
                "name": g.name,
                "count": len(g.documents),
                "documents": [vars(d) for d in g.documents],
            }
            for g in ordered
        ],
    }


# CSV -------------------------------------------------------------------------------------


def to_csv(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    buffer = StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if v is None else csv_safe_cell(v) for v in row])
    return buffer.getvalue()


MISSING_HEADER = ("Objektnummer", "Objekt", "Verwaltungsart", "Kategorie", "Fehlende Unterlage")


def missing_documents_csv(entries: Iterable[dict[str, Any]]) -> str:
    def rows() -> Iterable[Sequence[Any]]:
        for entry in entries:
            for m in entry["missing"]:
                yield (
                    entry["property_number"],
                    entry["property_name"],
                    entry["management_type"],
                    m["code"],
                    m["name"],
                )

    return to_csv(MISSING_HEADER, rows())


DOCUMENTS_HEADER = (
    "Objektnummer",
    "Objekt",
    "Kategorie",
    "Kategoriename",
    "Titel",
    "Dateiname",
    "Typ",
    "Erstellt am",
    "Herkunft",
    "Dublette",
)


def documents_csv(overview: dict[str, Any]) -> str:
    def rows() -> Iterable[Sequence[Any]]:
        for group in overview["groups"]:
            for d in group["documents"]:
                yield (
                    overview["property_number"],
                    overview["property_name"],
                    group["code"],
                    group["name"],
                    d["title"],
                    d["filename"],
                    d["mime_type"],
                    d["created_at"],
                    d["source_system"],
                    "ja" if d["duplicate"] else "nein",
                )

    return to_csv(DOCUMENTS_HEADER, rows())


# Personenlisten ---------------------------------------------------------------------------


@dataclass
class PersonRow:
    unit_id: str
    unit_number: str
    unit_label: str | None
    contract_id: str
    contract_number: str
    contract_start: str
    contract_end: str | None
    party_name: str
    contact_id: str | None
    name: str
    street: str
    postal_code: str
    city: str
    email: str
    phone: str


def _address_line(address: ContactAddress | None) -> tuple[str, str, str]:
    if address is None:
        return "", "", ""
    street = " ".join(p for p in (address.street, address.house_number) if p)
    return street, address.postal_code or "", address.city or ""


async def persons_list(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    property_row: Property,
    kind: PersonListKind,
    *,
    reference_date: date | None = None,
) -> dict[str, Any]:
    """Eigentümerliste (`kind="owners"`) or Mieterliste (`kind="tenants"`) of one property:
    one row per unit, contract and party member (primary and co-party). Contracts count when
    they are current on the reference date (default today): `start_date <= date` and
    `end_date` unset or `>= date`. A party without members yields one row with the party
    name only, so nothing is silently dropped. Contact data: primary address, primary e-mail
    and primary phone, all as shown in the CRM; no bank data."""
    today = reference_date or datetime.now(_LOCAL).date()
    contract_kind = PERSON_LIST_CONTRACT_KIND[kind]
    stmt = (
        select(Contract, Unit, Party)
        .join(Unit, Unit.id == Contract.unit_id)
        .join(Party, Party.id == Contract.party_id)
        .where(
            Contract.tenant_id == tenant_id,
            Contract.property_id == property_row.id,
            Contract.kind == contract_kind,
            Contract.start_date <= today,
            or_(Contract.end_date.is_(None), Contract.end_date >= today),
        )
        .order_by(Unit.number, Contract.start_date, Contract.id)
    )
    rows: list[PersonRow] = []
    for contract, unit, party in (await session.execute(stmt)).all():
        members = (
            await session.execute(
                select(Contact, PartyMember)
                .join(PartyMember, PartyMember.contact_id == Contact.id)
                .where(
                    PartyMember.party_id == party.id,
                    PartyMember.role.in_(PERSON_ROLES),
                    Contact.deleted_at.is_(None),
                )
                .order_by(PartyMember.role, Contact.display_name, Contact.id)
            )
        ).all()
        base = {
            "unit_id": str(unit.id),
            "unit_number": unit.number,
            "unit_label": unit.label,
            "contract_id": str(contract.id),
            "contract_number": contract.number,
            "contract_start": contract.start_date.isoformat(),
            "contract_end": contract.end_date.isoformat() if contract.end_date else None,
            "party_name": party.name,
        }
        if not members:
            rows.append(
                PersonRow(
                    **base,
                    contact_id=None,
                    name=party.name,
                    street="",
                    postal_code="",
                    city="",
                    email="",
                    phone="",
                )
            )
            continue
        for contact, _member in members:
            address = await session.scalar(
                select(ContactAddress)
                .where(ContactAddress.contact_id == contact.id)
                .order_by(ContactAddress.is_primary.desc(), ContactAddress.created_at)
                .limit(1)
            )
            email = await session.scalar(
                select(ContactEmail.email)
                .where(ContactEmail.contact_id == contact.id)
                .order_by(ContactEmail.is_primary.desc(), ContactEmail.created_at)
                .limit(1)
            )
            phone = await session.scalar(
                select(ContactPhone.number)
                .where(ContactPhone.contact_id == contact.id)
                .order_by(ContactPhone.is_primary.desc(), ContactPhone.created_at)
                .limit(1)
            )
            street, postal_code, city = _address_line(address)
            rows.append(
                PersonRow(
                    **base,
                    contact_id=str(contact.id),
                    name=contact.display_name,
                    street=street,
                    postal_code=postal_code,
                    city=city,
                    email=email or "",
                    phone=phone or "",
                )
            )
    return {
        **_property_head(property_row),
        "kind": kind,
        "reference_date": today.isoformat(),
        "total": len(rows),
        "rows": [vars(r) for r in rows],
    }


PERSONS_HEADER = (
    "Objektnummer",
    "Objekt",
    "Einheit",
    "Bezeichnung",
    "Name",
    "Straße",
    "PLZ",
    "Ort",
    "E-Mail",
    "Telefon",
    "Vertragsnummer",
    "Vertragsbeginn",
    "Vertragsende",
)


def _fmt_iso_date(value: str | None) -> str:
    if not value:
        return ""
    return date.fromisoformat(value).strftime("%d.%m.%Y")


def persons_csv(listing: dict[str, Any]) -> str:
    def rows() -> Iterable[Sequence[Any]]:
        for r in listing["rows"]:
            yield (
                listing["property_number"],
                listing["property_name"],
                r["unit_number"],
                r["unit_label"],
                r["name"],
                r["street"],
                r["postal_code"],
                r["city"],
                r["email"],
                r["phone"],
                r["contract_number"],
                _fmt_iso_date(r["contract_start"]),
                _fmt_iso_date(r["contract_end"]),
            )

    return to_csv(PERSONS_HEADER, rows())


# Ablage als Dokument ------------------------------------------------------------------------

ListKind = Literal["missing-documents", "documents", "owners", "tenants"]
LIST_TITLES: dict[str, str] = {
    "missing-documents": "Anforderungsliste",
    "documents": "Dokumentenübersicht",
    "owners": "Eigentümerliste",
    "tenants": "Mieterliste",
}
LIST_FILE_STEMS: dict[str, str] = {
    "missing-documents": "anforderungsliste",
    "documents": "dokumentenuebersicht",
    "owners": "eigentuemerliste",
    "tenants": "mieterliste",
}


async def render_list(
    session: AsyncSession, tenant_id: uuid.UUID, property_row: Property, kind: str
) -> tuple[dict[str, Any], str]:
    """JSON body and CSV of one list kind of a property (one place for the four kinds)."""
    if kind == "missing-documents":
        entry = await missing_documents_list(session, tenant_id, property_row)
        return entry, missing_documents_csv([entry])
    if kind == "documents":
        overview = await documents_by_category(session, tenant_id, property_row)
        return overview, documents_csv(overview)
    if kind in PERSON_LIST_CONTRACT_KIND:
        listing = await persons_list(session, tenant_id, property_row, kind)  # type: ignore[arg-type]
        return listing, persons_csv(listing)
    raise KeyError(kind)


async def list_category(session: AsyncSession, tenant_id: uuid.UUID) -> DocumentCategory:
    """Category "Liste" of the tenant, created on first use (RLS limits the lookup)."""
    category = await session.scalar(
        select(DocumentCategory).where(DocumentCategory.code == LIST_CATEGORY_CODE)
    )
    if category is None:
        category = DocumentCategory(
            tenant_id=tenant_id,
            code=LIST_CATEGORY_CODE,
            name=LIST_CATEGORY_NAME,
            paperless_document_type=LIST_CATEGORY_NAME,
            drive_folder="06_Sonstiges",
            sort_order=99,
        )
        session.add(category)
        await session.flush()
    return category


async def store_list(
    session: AsyncSession,
    blobs: BlobStore,
    *,
    tenant_id: uuid.UUID,
    property_row: Property,
    kind: str,
    created_by: uuid.UUID | None,
    today: date | None = None,
) -> Document:
    """Generate the CSV of `kind` and file it as a document of the property: title
    "<Liste> <Objekt> <TT.MM.JJJJ>", filename "<stem>-<nummer>-<JJJJ-MM-TT>.csv", category
    "Liste", source generated, link to the property with role generated (never removable by
    the unlink endpoint, rule 0.1.7). Each call stores a new snapshot; nothing is overwritten."""
    day = today or datetime.now(_LOCAL).date()
    _, csv_text = await render_list(session, tenant_id, property_row, kind)
    category = await list_category(session, tenant_id)
    title = f"{LIST_TITLES[kind]} {property_row.number} {property_row.name} {day:%d.%m.%Y}"
    filename = f"{LIST_FILE_STEMS[kind]}-{property_row.number}-{day.isoformat()}.csv"
    return await store_document(
        session,
        blobs,
        tenant_id=tenant_id,
        data=csv_text.encode("utf-8"),
        title=title,
        filename=filename,
        mime_type="text/csv",
        source=DocumentSource.GENERATED,
        category_id=category.id,
        links=[("property", property_row.id, LinkRole.GENERATED)],
        created_by=created_by,
    )
