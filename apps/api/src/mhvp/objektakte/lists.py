"""M35 Stufe 4, part "Listengenerierung" (docs/plans/M35-objektakte-uebernahme.md section 4):
lists generated per property from the objektakte data (documents, classification,
completeness check). Two list kinds:

* "Anforderungsliste": the missing mandatory document classes of a property, derived from
  `mhvp.objektakte.completeness.check_completeness` (same rule, no second definition of
  "missing"), plus an overview of the same across all properties of the tenant.
* "Dokumentenübersicht je Kategorie": every document linked to the property
  (`DocumentLink(entity_type="property")`) grouped by its `DocumentCategory`; unclassified
  documents form their own group so that nothing is hidden.

Everything here is read only and computed on request: no list row is stored, no document is
created (the plan's "Ablage der erzeugten Liste als Dokument" is a later, separate step, see
the module README). CSV export uses semicolon separators, CRLF line ends and a UTF-8 BOM so
that Excel in a German locale opens the file directly.
"""

from __future__ import annotations

import csv
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from io import StringIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.documents.models import Document, DocumentCategory, DocumentLink
from mhvp.objektakte.completeness import check_completeness
from mhvp.properties.models import ManagementType, Property

UNCATEGORISED_CODE = ""
UNCATEGORISED_NAME = "Ohne Kategorie"


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
        writer.writerow(["" if v is None else v for v in row])
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
