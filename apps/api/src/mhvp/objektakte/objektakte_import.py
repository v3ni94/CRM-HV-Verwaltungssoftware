"""Data takeover from objektakte, Stufe 1 (docs/plans/M35-objektakte-uebernahme.md section 4,
operator decision 25.09.2026).

The productive objektakte application (Django/MariaDB) is replaced by this CRM in full (see the
plan); this module only takes over its master data (objects, units, owners, tenants, unit
assignments), the same way `mhvp.handover.uprotokoll_import` takes over U-Protokoll: a
`mysqldump` export is parsed without executing any SQL (`mhvp.core.sqldump`), always preview
first (counts, matched/new properties, duplicates), then an explicit apply that is idempotent by
source id (`source_system="objektakte"`, `source_id=<objektakte PK>` on every created row).

Tables understood here (objektakte apps `objects`, `parties`; see that repository's
`apps/objects/models.py` and `apps/parties/models.py`):

- `objects_managedobject` -> `mhvp.properties.models.Property` (matched by `object_number`,
  else created; `Property.number` is constrained to exactly three digits, so an object number
  outside 1..999 cannot become a `Property` in this stage and is reported as `unmatched`,
  never silently truncated or renumbered).
- `objects_unit` -> `mhvp.properties.models.Unit` (matched within the property by `unit_number`,
  else created).
- `parties_owner` / `parties_tenant` -> `mhvp.contacts.models.Contact` (matched by `source_id`
  for idempotency; otherwise always created, since a name based contact match risks merging two
  different people, which rule 0.1.3 treats as a data protection risk needing a released rule
  first, not an assumption here).
- `parties_ownerunitassignment` -> `mhvp.objektakte.models.ObjektakteAssignment` (staging table,
  M35 Stufe 1 note in the plan): the CRM has no unit level ownership/tenancy model yet that
  matches objektakte's time valid assignment row, so every row lands here, keyed by its
  objektakte id, until Stufe 2/3 decide the eventual target model.

IBAN (docs/rules/M35-01.md): the CRM's `mhvp.contacts.models.ContactBankAccount` stores only a
full, encrypted IBAN (`iban` is mandatory) plus a fingerprint of it, which objektakte's
`iban_encrypted` plaintext is not available for outside an explicitly authorized, separate
migration step (section 3.1 of the plan). Stufe 1 therefore imports no bank account for any
contact; `iban_last4`/`iban_hash` are read from the dump only to decide whether such a step
would be needed later, never written anywhere in the CRM.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Contact, ContactKind
from mhvp.core.auth.principal import TenantPrincipal
from mhvp.core.sqldump import field_str as _s
from mhvp.core.sqldump import parse_dump as parse_dump  # re-exported for the router/tests
from mhvp.core.sqldump import to_bool as _to_bool
from mhvp.core.sqldump import to_date as _to_date
from mhvp.core.sqldump import to_datetime as _to_datetime
from mhvp.core.sqldump import to_decimal as _to_decimal
from mhvp.documents.models import (
    Document,
    DocumentCategory,
    DocumentLink,
    DocumentSource,
    LinkRole,
    StorageKind,
    TextStatus,
)
from mhvp.objektakte.models import (
    DocumentReviewCase,
    DocumentReviewDecision,
    DriveListType,
    DriveNode,
    DriveNodeKind,
    DriveNodeStatus,
    ObjektakteAssignment,
    ObjektakteDocumentClass,
    PartyAssignmentRole,
    ReviewCaseStatus,
)
from mhvp.properties.models import Building, Property, Unit

# Tables of objektakte's `objects`/`parties`/`documents`/`drive`/`review` apps that this importer
# understands (see module docstring). Anything else in the dump is parsed (generic, table
# agnostic) and counted in the preview, but never applied.
KNOWN_TABLES = (
    "objects_managedobject",
    "objects_unit",
    "parties_owner",
    "parties_tenant",
    "parties_ownerunitassignment",
    "documents_documentcategory",
    "documents_documentsubfolder",
    "documents_documenttype",
    "drive_drivenode",
    "documents_document",
    "review_reviewcase",
    "review_reviewdecision",
)

SOURCE_SYSTEM = "objektakte"

# Document statuses (objektakte `documents.models.DocumentStatus`) that already carry a text
# layer or OCR result; a document import marks these `pending` so the OCR cache ZIP endpoint
# (Stufe 2 item 2) can turn them `extracted` once the matching cache file is uploaded, instead
# of claiming text is present before it actually is.
_STATUS_WITH_TEXT = frozenset({"ocr_done", "classified", "filed", "review"})
_REVIEW_CASE_STATUSES = frozenset({"open", "in_progress", "resolved", "dismissed"})


def _row_hash(row: dict[str, Any]) -> str:
    """Stable hash of a dump row, stored in `source_meta`/on the assignment row so a repeated
    apply of an unchanged dump touches nothing (plan section 4 item 4), while a corrected export
    (e.g. a document reclassified in objektakte before the cut-over) is picked up as an update."""
    return hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _source_id(row: dict[str, Any]) -> str:
    return str(row.get("id"))


async def _insert_or_get_by_source(
    session: AsyncSession,
    obj: Any,
    model: type[Any],
    *,
    tenant_id: uuid.UUID,
    source_id: str,
) -> Any:
    """Inserts ``obj`` under a savepoint; on a unique violation of (tenant_id, source_system,
    source_id) — a concurrent apply of the same objektakte export racing this one (rule
    0.1.12, Sicherheitsreview 2026-09-25, Befund 3) — rolls back only that savepoint and
    re-reads the row the other transaction committed instead of failing the whole import."""
    try:
        async with session.begin_nested():
            session.add(obj)
            await session.flush()
        return obj
    except IntegrityError:
        row = await session.scalar(
            select(model).where(
                model.tenant_id == tenant_id,
                model.source_system == SOURCE_SYSTEM,
                model.source_id == source_id,
            )
        )
        if row is None:
            raise
        return row


def _normalized_property_number(row: dict[str, Any]) -> str | None:
    """`Property.number` is exactly three digits (`number_format` check constraint); an
    objektakte `object_number` like "82" or "0623" is zero padded/left stripped to that shape.
    Returns `None` when the numeric value does not fit (0 or > 999): such an object cannot
    become a `Property` in this stage without weakening that constraint, so it is reported as
    unmatched rather than truncated or renumbered without a released rule."""
    raw = _s(row, "object_number")
    if raw is None or not raw.isdigit():
        return None
    value = int(raw)
    if not (1 <= value <= 999):
        return None
    return f"{value:03d}"


async def _match_property_by_number(
    session: AsyncSession, tenant_id: uuid.UUID, number: str
) -> uuid.UUID | None:
    matched: uuid.UUID | None = await session.scalar(
        select(Property.id).where(Property.tenant_id == tenant_id, Property.number == number)
    )
    return matched


def _contact_kind(row: dict[str, Any]) -> ContactKind:
    return ContactKind.COMPANY if _s(row, "type") == "legal_entity" else ContactKind.PERSON


def _display_name(row: dict[str, Any]) -> str:
    company = _s(row, "company_name")
    if company:
        return company
    parts = [p for p in (_s(row, "first_name"), _s(row, "last_name")) if p]
    return " ".join(parts) or _s(row, "search_name") or f"objektakte:{row.get('id')}"


@dataclass
class ImportPlan:
    counts: dict[str, int] = field(default_factory=dict)
    matched_properties: int = 0
    new_properties: int = 0
    unmatched_properties: int = 0
    duplicates: dict[str, int] = field(default_factory=dict)
    unknown_tables: list[str] = field(default_factory=list)
    # Stufe 2 additions (plan section 4 item 4).
    unmatched_drive_nodes: int = 0
    documents_without_property: int = 0
    documents_to_update: int = 0
    open_review_cases: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts,
            "matched_properties": self.matched_properties,
            "new_properties": self.new_properties,
            "unmatched_properties": self.unmatched_properties,
            "duplicates": self.duplicates,
            "unknown_tables": self.unknown_tables,
            "unmatched_drive_nodes": self.unmatched_drive_nodes,
            "documents_without_property": self.documents_without_property,
            "documents_to_update": self.documents_to_update,
            "open_review_cases": self.open_review_cases,
        }


async def _existing_source_ids(
    session: AsyncSession, tenant_id: uuid.UUID, model: type, table_name: str
) -> frozenset[str]:
    rows = await session.scalars(
        select(model.source_id).where(  # type: ignore[attr-defined]
            model.tenant_id == tenant_id,  # type: ignore[attr-defined]
            model.source_system == SOURCE_SYSTEM,  # type: ignore[attr-defined]
            model.source_id.is_not(None),  # type: ignore[attr-defined]
        )
    )
    return frozenset(str(r) for r in rows.all())


async def build_plan(
    session: AsyncSession, tenant_id: uuid.UUID, tables: dict[str, list[dict[str, Any]]]
) -> ImportPlan:
    plan = ImportPlan(counts={t: len(rows) for t, rows in tables.items()})
    plan.unknown_tables = sorted(set(tables) - set(KNOWN_TABLES))

    existing_properties = await _existing_source_ids(session, tenant_id, Property, "property")
    existing_contacts = await _existing_source_ids(session, tenant_id, Contact, "contact")
    existing_assignments = await _existing_source_ids(
        session, tenant_id, ObjektakteAssignment, "objektakte_party_assignment"
    )

    for row in tables.get("objects_managedobject", []):
        source_id = _source_id(row)
        if source_id in existing_properties:
            plan.duplicates["objects_managedobject"] = (
                plan.duplicates.get("objects_managedobject", 0) + 1
            )
            plan.matched_properties += 1
            continue
        number = _normalized_property_number(row)
        if number is None:
            plan.unmatched_properties += 1
            continue
        matched = await _match_property_by_number(session, tenant_id, number)
        if matched is not None:
            plan.matched_properties += 1
        else:
            plan.new_properties += 1

    for table, model in (
        ("parties_owner", Contact),
        ("parties_tenant", Contact),
        ("parties_ownerunitassignment", ObjektakteAssignment),
    ):
        existing = existing_contacts if model is Contact else existing_assignments
        dup = sum(1 for row in tables.get(table, []) if _source_id(row) in existing)
        if dup:
            plan.duplicates[table] = dup

    # Stufe 2: documents, drive nodes, review cases/decisions (plan section 4 item 4).
    available_properties = set(existing_properties)
    for row in tables.get("objects_managedobject", []):
        if _source_id(row) in existing_properties:
            continue
        number = _normalized_property_number(row)
        if number is not None:
            available_properties.add(_source_id(row))

    existing_drive_ids = frozenset(
        str(r)
        for r in (
            await session.scalars(
                select(DriveNode.source_id).where(
                    DriveNode.tenant_id == tenant_id, DriveNode.source_id.is_not(None)
                )
            )
        ).all()
    )
    dup_drive = sum(
        1 for row in tables.get("drive_drivenode", []) if _source_id(row) in existing_drive_ids
    )
    if dup_drive:
        plan.duplicates["drive_drivenode"] = dup_drive
    plan.unmatched_drive_nodes = sum(
        1
        for row in tables.get("drive_drivenode", [])
        if row.get("object_id") is not None
        and str(row.get("object_id")) not in available_properties
    )

    existing_documents: dict[str, str | None] = {
        row.source_id: (row.source_meta or {}).get("row_hash")
        for row in (
            await session.scalars(
                select(Document).where(
                    Document.tenant_id == tenant_id, Document.source_system == SOURCE_SYSTEM
                )
            )
        ).all()
        if row.source_id is not None
    }
    dup_documents = 0
    for row in tables.get("documents_document", []):
        source_id = _source_id(row)
        if source_id not in existing_documents:
            if (
                row.get("object_id") is not None
                and str(row.get("object_id")) not in available_properties
            ):
                plan.documents_without_property += 1
            continue
        dup_documents += 1
        if existing_documents[source_id] != _row_hash(row):
            plan.documents_to_update += 1
    if dup_documents:
        plan.duplicates["documents_document"] = dup_documents

    plan.open_review_cases = sum(
        1
        for row in tables.get("review_reviewcase", [])
        if _s(row, "status") in ("open", "in_progress")
    )

    return plan


@dataclass
class ImportResult:
    created: dict[str, int] = field(default_factory=dict)
    skipped_duplicates: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)
    id_map: dict[str, dict[str, str]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "skipped_duplicates": self.skipped_duplicates,
            "updated": self.updated,
            "id_map": self.id_map,
        }


async def apply_import(
    session: AsyncSession,
    principal: TenantPrincipal,
    tables: dict[str, list[dict[str, Any]]],
) -> ImportResult:
    """Creates properties, units, contacts and staged assignments. Idempotent: a row whose
    `source_id` is already present under `source_system="objektakte"` is skipped (rule 0.1.12);
    a repeated apply of the same dump therefore changes nothing."""
    tenant_id = principal.tenant_id
    result = ImportResult()
    property_map: dict[str, uuid.UUID] = {}
    unit_map: dict[str, uuid.UUID] = {}
    contact_map: dict[str, uuid.UUID] = {}
    default_building: dict[uuid.UUID, uuid.UUID] = {}

    async def _default_building_id(property_id: uuid.UUID) -> uuid.UUID:
        if property_id in default_building:
            return default_building[property_id]
        existing = await session.scalar(
            select(Building.id).where(
                Building.tenant_id == tenant_id, Building.property_id == property_id
            )
        )
        if existing is not None:
            default_building[property_id] = existing
            return existing
        building = Building(
            tenant_id=tenant_id,
            property_id=property_id,
            name="Hauptgebäude (objektakte-Übernahme)",
        )
        session.add(building)
        await session.flush()
        default_building[property_id] = building.id
        return building.id

    def _created(kind: str) -> None:
        result.created[kind] = result.created.get(kind, 0) + 1

    def _skipped(kind: str) -> None:
        result.skipped_duplicates[kind] = result.skipped_duplicates.get(kind, 0) + 1

    existing_properties: dict[str, uuid.UUID] = {
        row.source_id: row.id
        for row in (
            await session.scalars(
                select(Property).where(
                    Property.tenant_id == tenant_id, Property.source_system == SOURCE_SYSTEM
                )
            )
        ).all()
        if row.source_id is not None
    }
    for row in tables.get("objects_managedobject", []):
        source_id = _source_id(row)
        if source_id in existing_properties:
            property_map[source_id] = existing_properties[source_id]
            _skipped("objects_managedobject")
            continue
        number = _normalized_property_number(row)
        if number is None:
            continue
        matched_id = await _match_property_by_number(session, tenant_id, number)
        if matched_id is not None:
            prop = await session.get(Property, matched_id)
            if prop is not None and prop.source_system is None:
                prop.source_system = SOURCE_SYSTEM
                prop.source_id = source_id
            property_map[source_id] = matched_id
            continue
        prop = Property(
            tenant_id=tenant_id,
            number=number,
            name=_s(row, "name", 200) or f"Objekt {number}",
            management_type=(
                "hoa" if _s(row, "management_type") in ("weg", "weg_with_se") else "rental"
            ),
            street=_s(row, "street", 200),
            house_number=_s(row, "house_number", 20),
            postal_code=_s(row, "postal_code", 20),
            city=_s(row, "city", 100),
            source_system=SOURCE_SYSTEM,
            source_id=source_id,
        )
        session.add(prop)
        await session.flush()
        property_map[source_id] = prop.id
        _created("property")
        # Units need a building (mhvp.properties.models.Unit.building_id is mandatory); objektakte
        # has no building level model of its own, so one default building per taken over property
        # stands in until a real building takeover exists (Stufe 2+).
        await _default_building_id(prop.id)

    existing_units: dict[str, uuid.UUID] = {
        row.source_id: row.id
        for row in (
            await session.scalars(
                select(Unit).where(Unit.tenant_id == tenant_id, Unit.source_system == SOURCE_SYSTEM)
            )
        ).all()
        if row.source_id is not None
    }
    for row in tables.get("objects_unit", []):
        source_id = _source_id(row)
        if source_id in existing_units:
            unit_map[source_id] = existing_units[source_id]
            _skipped("objects_unit")
            continue
        property_id = property_map.get(str(row.get("object_id")))
        if property_id is None:
            continue
        building_id = await _default_building_id(property_id)
        unit = Unit(
            tenant_id=tenant_id,
            property_id=property_id,
            building_id=building_id,
            number=_s(row, "unit_number", 20) or _s(row, "unit_label", 20) or source_id,
            label=_s(row, "unit_label", 50),
            unit_type=_s(row, "unit_type", 24) or "other",
            source_system=SOURCE_SYSTEM,
            source_id=source_id,
        )
        session.add(unit)
        await session.flush()
        unit_map[source_id] = unit.id
        _created("unit")

    existing_contacts: dict[str, uuid.UUID] = {
        row.source_id: row.id
        for row in (
            await session.scalars(
                select(Contact).where(
                    Contact.tenant_id == tenant_id, Contact.source_system == SOURCE_SYSTEM
                )
            )
        ).all()
        if row.source_id is not None
    }
    for table, role in (("parties_owner", "eigentuemer"), ("parties_tenant", "mieter")):
        for row in tables.get(table, []):
            source_id = _source_id(row)
            if source_id in existing_contacts:
                contact_map[source_id] = existing_contacts[source_id]
                _skipped(table)
                continue
            contact = Contact(
                tenant_id=tenant_id,
                kind=_contact_kind(row),
                salutation=_s(row, "salutation", 50),
                first_name=_s(row, "first_name", 100),
                last_name=_s(row, "last_name", 100),
                company_name=_s(row, "company_name", 200),
                display_name=_display_name(row),
                roles=[role],
                source_system=SOURCE_SYSTEM,
                source_id=source_id,
            )
            session.add(contact)
            await session.flush()
            # IBAN (docs/rules/M35-01.md): `iban_last4`/`iban_hash` are read only to decide
            # later whether an authorized, separate migration step is needed; the CRM's
            # ContactBankAccount requires a full encrypted IBAN, which is never available here,
            # so no bank account is created in Stufe 1.
            contact_map[source_id] = contact.id
            _created("contact")

    existing_assignments = await _existing_source_ids(
        session, tenant_id, ObjektakteAssignment, "objektakte_party_assignment"
    )
    for row in tables.get("parties_ownerunitassignment", []):
        source_id = _source_id(row)
        if source_id in existing_assignments:
            _skipped("parties_ownerunitassignment")
            continue
        await _insert_or_get_by_source(
            session,
            ObjektakteAssignment(
                tenant_id=tenant_id,
                unit_id=unit_map.get(str(row.get("unit_id"))),
                contact_id=contact_map.get(str(row.get("owner_id"))),
                role=PartyAssignmentRole.OWNER,
                valid_from=_to_date(row.get("valid_from")),
                valid_to=_to_date(row.get("valid_to")),
                share=_to_decimal(row.get("share")),
                source_system=SOURCE_SYSTEM,
                source_id=source_id,
                source_unit_id=_s(row, "unit_id", 64),
                source_contact_id=_s(row, "owner_id", 64),
            ),
            ObjektakteAssignment,
            tenant_id=tenant_id,
            source_id=source_id,
        )
        _created("parties_ownerunitassignment")

    category_map = await _import_categories(
        session, tenant_id, tables.get("documents_documentcategory", []), _created, _skipped
    )
    class_map = await _import_document_classes(
        session,
        tenant_id,
        tables.get("documents_documenttype", []),
        tables.get("documents_documentsubfolder", []),
        category_map,
        _created,
        _skipped,
    )
    drive_node_map = await _import_drive_nodes(
        session, tenant_id, tables.get("drive_drivenode", []), property_map, _created, _skipped
    )
    document_map = await _import_documents(
        session,
        tenant_id,
        tables.get("documents_document", []),
        property_map,
        category_map,
        class_map,
        drive_node_map,
        _created,
        _skipped,
        result,
    )
    review_case_map = await _import_review_cases(
        session, tenant_id, tables.get("review_reviewcase", []), document_map, _created, _skipped
    )
    await _import_review_decisions(
        session,
        tenant_id,
        tables.get("review_reviewdecision", []),
        review_case_map,
        document_map,
        _created,
        _skipped,
    )

    await session.flush()
    result.id_map = {
        "objects_managedobject": {k: str(v) for k, v in property_map.items()},
        "objects_unit": {k: str(v) for k, v in unit_map.items()},
        "contacts": {k: str(v) for k, v in contact_map.items()},
        "documents_document": {k: str(v) for k, v in document_map.items()},
    }
    return result


async def _import_categories(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rows: list[dict[str, Any]],
    created: Any,
    skipped: Any,
) -> dict[str, uuid.UUID]:
    """`documents_documentcategory` -> `mhvp.documents.models.DocumentCategory`, matched by
    `source_id` (idempotent), else by name within the tenant (no duplicate category for a
    catalog entry a user may already have created by hand), else newly created (plan section 4
    item 1)."""
    existing_by_source: dict[str, uuid.UUID] = {
        row.source_id: row.id
        for row in (
            await session.scalars(
                select(DocumentCategory).where(
                    DocumentCategory.tenant_id == tenant_id,
                    DocumentCategory.source_system == SOURCE_SYSTEM,
                )
            )
        ).all()
        if row.source_id is not None
    }
    existing_by_name: dict[str, uuid.UUID] = {
        row.name.strip().lower(): row.id
        for row in (
            await session.scalars(
                select(DocumentCategory).where(DocumentCategory.tenant_id == tenant_id)
            )
        ).all()
    }
    existing_codes: set[str] = {
        row.code
        for row in (
            await session.scalars(
                select(DocumentCategory).where(DocumentCategory.tenant_id == tenant_id)
            )
        ).all()
    }
    mapping: dict[str, uuid.UUID] = {}
    for row in rows:
        source_id = _s(row, "code") or _source_id(row)
        if source_id in existing_by_source:
            mapping[source_id] = existing_by_source[source_id]
            skipped("documents_documentcategory")
            continue
        name = _s(row, "display_name", 200) or _s(row, "folder_name", 200) or source_id
        matched = existing_by_name.get(name.strip().lower())
        if matched is not None:
            mapping[source_id] = matched
            skipped("documents_documentcategory")
            continue
        code = f"oa-{source_id}"[:63]
        suffix = 1
        while code in existing_codes:
            code = f"oa-{source_id}-{suffix}"[:63]
            suffix += 1
        category = DocumentCategory(
            tenant_id=tenant_id,
            code=code,
            name=name[:200],
            sort_order=int(row.get("sort_order") or 0),
            source_system=SOURCE_SYSTEM,
            source_id=source_id,
        )
        session.add(category)
        await session.flush()
        existing_codes.add(code)
        mapping[source_id] = category.id
        created("documents_documentcategory")
    return mapping


async def _import_document_classes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    type_rows: list[dict[str, Any]],
    subfolder_rows: list[dict[str, Any]],
    category_map: dict[str, uuid.UUID],
    created: Any,
    skipped: Any,
) -> dict[str, ObjektakteDocumentClass]:
    """`documents_documenttype` (with its `documents_documentsubfolder`) -> `objektakte_document_
    class` (plan section 4 item 1): the CRM category catalog is flat, so the subfolder/type level
    is kept here rather than modelled again in `DocumentCategory` (rule 0.1.4.2, no fields "auf
    Vorrat" beyond what the document importer itself needs)."""
    subfolders_by_id = {str(r.get("id")): r for r in subfolder_rows}
    existing: dict[str, ObjektakteDocumentClass] = {
        row.source_id: row
        for row in (
            await session.scalars(
                select(ObjektakteDocumentClass).where(
                    ObjektakteDocumentClass.tenant_id == tenant_id,
                    ObjektakteDocumentClass.source_system == SOURCE_SYSTEM,
                )
            )
        ).all()
        if row.source_id is not None
    }
    mapping: dict[str, ObjektakteDocumentClass] = {}
    for row in type_rows:
        source_id = _source_id(row)
        if source_id in existing:
            mapping[source_id] = existing[source_id]
            skipped("documents_documenttype")
            continue
        subfolder = (
            subfolders_by_id.get(str(row.get("subfolder_id"))) if row.get("subfolder_id") else None
        )
        entry = ObjektakteDocumentClass(
            tenant_id=tenant_id,
            category_id=category_map.get(str(row.get("category_id"))),
            subfolder_source_id=_s(row, "subfolder_id", 64),
            subfolder_name=_s(subfolder, "display_name", 200) if subfolder else None,
            type_code=_s(row, "code", 64),
            type_name=_s(row, "name", 200),
            requires_period=_to_bool(row.get("requires_period")),
            requires_owner=_to_bool(row.get("requires_owner")),
            requires_tenant=_to_bool(row.get("requires_tenant")),
            source_system=SOURCE_SYSTEM,
            source_id=source_id,
        )
        entry = await _insert_or_get_by_source(
            session, entry, ObjektakteDocumentClass, tenant_id=tenant_id, source_id=source_id
        )
        mapping[source_id] = entry
        created("documents_documenttype")
    return mapping


async def _import_drive_nodes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rows: list[dict[str, Any]],
    property_map: dict[str, uuid.UUID],
    created: Any,
    skipped: Any,
) -> dict[str, uuid.UUID]:
    """`drive_drivenode` -> `objektakte_drive_node` (Stufe 1 tree, filled here, plan section 4
    item 1). Parent links are resolved in a second pass since a child row can precede its parent
    in the dump."""
    existing: dict[str, uuid.UUID] = {
        row.source_id: row.id
        for row in (
            await session.scalars(
                select(DriveNode).where(
                    DriveNode.tenant_id == tenant_id, DriveNode.source_id.is_not(None)
                )
            )
        ).all()
        if row.source_id is not None
    }
    mapping: dict[str, uuid.UUID] = dict(existing)
    for row in rows:
        source_id = _source_id(row)
        if source_id in existing:
            skipped("drive_drivenode")
            continue
        try:
            node_kind = DriveNodeKind(_s(row, "node_kind") or "subfolder")
        except ValueError:
            node_kind = DriveNodeKind.SUBFOLDER
        list_type_raw = _s(row, "list_type")
        try:
            status_enum = DriveNodeStatus(_s(row, "status") or "active")
        except ValueError:
            status_enum = DriveNodeStatus.ACTIVE
        node = DriveNode(
            tenant_id=tenant_id,
            property_id=property_map.get(str(row.get("object_id"))),
            node_kind=node_kind,
            list_type=DriveListType(list_type_raw)
            if list_type_raw in ("owner_list", "tenant_list")
            else None,
            year=row.get("year"),
            name=_s(row, "drive_name", 255) or _s(row, "expected_name", 255) or source_id,
            position=0,
            drive_file_id=_s(row, "drive_file_id", 128) or f"objektakte:{source_id}",
            drive_parent_id=_s(row, "drive_parent_id", 128),
            status=status_enum,
            source_system=SOURCE_SYSTEM,
            source_id=source_id,
        )
        node = await _insert_or_get_by_source(
            session, node, DriveNode, tenant_id=tenant_id, source_id=source_id
        )
        mapping[source_id] = node.id
        created("drive_drivenode")

    for row in rows:
        source_id = _source_id(row)
        parent_source = row.get("parent_node_id")
        if parent_source is None:
            continue
        node_id = mapping.get(source_id)
        parent_id = mapping.get(str(parent_source))
        if node_id is None or parent_id is None:
            continue
        existing_node = await session.get(DriveNode, node_id)
        if existing_node is not None and existing_node.parent_node_id is None:
            existing_node.parent_node_id = parent_id
    return mapping


def _document_text_status(row: dict[str, Any]) -> TextStatus:
    """objektakte's own OCR result is not copied here (only its cache key, see module docstring
    of the OCR endpoint): a status that implies recognised text starts `pending` until the
    matching OCR cache ZIP is uploaded (Stufe 2 item 2), so search never claims text that is not
    actually indexed yet."""
    status = _s(row, "status")
    if status in _STATUS_WITH_TEXT:
        return TextStatus.PENDING
    if str(row.get("mime_type") or "").startswith("image/"):
        return TextStatus.PENDING
    return TextStatus.NONE


async def _import_documents(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rows: list[dict[str, Any]],
    property_map: dict[str, uuid.UUID],
    category_map: dict[str, uuid.UUID],
    class_map: dict[str, ObjektakteDocumentClass],
    drive_node_map: dict[str, uuid.UUID],
    created: Any,
    skipped: Any,
    result: ImportResult,
) -> dict[str, uuid.UUID]:
    """`documents_document` -> `mhvp.documents.models.Document` (plan section 4 item 1): no
    binary copy, `storage_ref` carries the Drive file id the same way a mirrored Drive document
    does (`mhvp.documents.dms.GoogleDriveStore.put`/`resolve` both treat the file id itself as
    the ref), so the existing download path and Drive mirror machinery both work unchanged.

    Idempotent by `source_id`; a repeated apply of an unchanged row (`source_meta["row_hash"]`
    unchanged) updates nothing, a changed row (e.g. reclassified before the cut-over) updates
    the mapped fields in place (plan section 4 item 4). `sha256` is mandatory on `Document`; a row
    not yet hashed in objektakte (`status == "registered"`) gets a deterministic placeholder
    derived from its source id, flagged in `source_meta`, never a real content hash.
    """
    existing: dict[str, Document] = {
        row.source_id: row
        for row in (
            await session.scalars(
                select(Document).where(
                    Document.tenant_id == tenant_id, Document.source_system == SOURCE_SYSTEM
                )
            )
        ).all()
        if row.source_id is not None
    }
    mapping: dict[str, uuid.UUID] = {k: v.id for k, v in existing.items()}

    def _category_for(row: dict[str, Any]) -> uuid.UUID | None:
        cls = (
            class_map.get(str(row.get("document_type_id"))) if row.get("document_type_id") else None
        )
        if cls is not None and cls.category_id is not None:
            return cls.category_id
        return category_map.get(_s(row, "category_code") or "")

    def _fields(row: dict[str, Any], row_hash: str) -> dict[str, Any]:
        source_id = _source_id(row)
        sha256 = _s(row, "sha256")
        drive_node_id = (
            drive_node_map.get(str(row.get("drive_node_id"))) if row.get("drive_node_id") else None
        )
        meta: dict[str, Any] = {
            "objektakte_status": _s(row, "status"),
            "row_hash": row_hash,
            "category_code": _s(row, "category_code"),
            "subfolder_id": _s(row, "subfolder_id"),
            "document_type_id": _s(row, "document_type_id"),
            "ocr_cache_key": _s(row, "ocr_cache_key"),
            "drive_node_source_id": _s(row, "drive_node_id"),
            "drive_node_id": str(drive_node_id) if drive_node_id else None,
        }
        if not sha256:
            sha256 = hashlib.sha256(f"objektakte-pending:{source_id}".encode()).hexdigest()
            meta["sha256_placeholder"] = True
        return {
            "title": _s(row, "current_name", 300) or _s(row, "original_name", 300) or source_id,
            "filename": _s(row, "current_name", 255) or _s(row, "original_name", 255) or source_id,
            "mime_type": _s(row, "mime_type", 127) or "application/octet-stream",
            "size": int(row.get("size_bytes") or 0),
            "sha256": sha256,
            "storage_ref": _s(row, "drive_file_id", 512) or f"objektakte:{source_id}",
            "category_id": _category_for(row),
            "text_status": _document_text_status(row),
            "source_meta": meta,
        }

    for row in rows:
        source_id = _source_id(row)
        row_hash = _row_hash(row)
        doc = existing.get(source_id)
        if doc is not None:
            if (doc.source_meta or {}).get("row_hash") == row_hash:
                skipped("documents_document")
                continue
            for key, value in _fields(row, row_hash).items():
                setattr(doc, key, value)
            result.updated["documents_document"] = result.updated.get("documents_document", 0) + 1
            mapping[source_id] = doc.id
            continue
        fields = _fields(row, row_hash)
        document = Document(
            tenant_id=tenant_id,
            storage=StorageKind.GOOGLE_DRIVE,
            source=DocumentSource.IMPORT,
            visibility=["tenant"],
            source_system=SOURCE_SYSTEM,
            source_id=source_id,
            **fields,
        )
        session.add(document)
        await session.flush()
        mapping[source_id] = document.id
        created("documents_document")

    # Second pass: duplicate links and the property/drive-node linkage that needs every
    # document's id resolved first.
    for row in rows:
        source_id = _source_id(row)
        doc_id = mapping.get(source_id)
        if doc_id is None:
            continue
        duplicate_source = row.get("duplicate_of_document_id")
        if duplicate_source is not None:
            duplicate_id = mapping.get(str(duplicate_source))
            if duplicate_id is not None:
                doc = await session.get(Document, doc_id)
                if doc is not None:
                    doc.duplicate_of_id = duplicate_id
        property_id = property_map.get(str(row.get("object_id")))
        if property_id is None:
            continue
        link_exists = await session.scalar(
            select(DocumentLink.id).where(
                DocumentLink.tenant_id == tenant_id,
                DocumentLink.document_id == doc_id,
                DocumentLink.entity_type == "property",
                DocumentLink.entity_id == property_id,
            )
        )
        if link_exists is None:
            session.add(
                DocumentLink(
                    tenant_id=tenant_id,
                    document_id=doc_id,
                    entity_type="property",
                    entity_id=property_id,
                    role=LinkRole.ORIGINAL,
                )
            )
    return mapping


async def _import_review_cases(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rows: list[dict[str, Any]],
    document_map: dict[str, uuid.UUID],
    created: Any,
    skipped: Any,
) -> dict[str, uuid.UUID]:
    """`review_reviewcase` -> `objektakte_document_review_case` (Stufe 1 table, filled here):
    open cases become the Stufe 3 review center's start set (plan section 4 item 3)."""
    existing: dict[str, uuid.UUID] = {
        row.source_id: row.id
        for row in (
            await session.scalars(
                select(DocumentReviewCase).where(
                    DocumentReviewCase.tenant_id == tenant_id,
                    DocumentReviewCase.source_id.is_not(None),
                )
            )
        ).all()
        if row.source_id is not None
    }
    mapping = dict(existing)
    for row in rows:
        source_id = _source_id(row)
        if source_id in existing:
            skipped("review_reviewcase")
            continue
        status = _s(row, "status")
        case = DocumentReviewCase(
            tenant_id=tenant_id,
            document_id=document_map.get(str(row.get("document_id"))),
            stage=_s(row, "case_type", 32) or _s(row, "case_subtype", 32) or "unknown",
            candidates=row.get("candidates") if isinstance(row.get("candidates"), dict) else None,
            proposed_action=(
                row.get("proposed_action") if isinstance(row.get("proposed_action"), dict) else None
            ),
            priority=int(row.get("priority") or 100),
            status=ReviewCaseStatus(status)
            if status in _REVIEW_CASE_STATUSES
            else ReviewCaseStatus.OPEN,
            snoozed_until=_to_datetime(row.get("snoozed_until")),
            source_system=SOURCE_SYSTEM,
            source_id=source_id,
        )
        case = await _insert_or_get_by_source(
            session, case, DocumentReviewCase, tenant_id=tenant_id, source_id=source_id
        )
        mapping[source_id] = case.id
        created("review_reviewcase")
    return mapping


async def _import_review_decisions(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rows: list[dict[str, Any]],
    review_case_map: dict[str, uuid.UUID],
    document_map: dict[str, uuid.UUID],
    created: Any,
    skipped: Any,
) -> None:
    """`review_reviewdecision` -> `objektakte_document_review_decision`: read-only history, kept
    only when its case was taken over (plan section 4 item 3); `decided_by` is not mapped across
    systems in this stage (objektakte user ids do not resolve to CRM user ids without a released
    user/role takeover, Stufe 4), so it stays unset rather than pointing at the wrong person."""
    existing_ids = frozenset(
        str(r)
        for r in (
            await session.scalars(
                select(DocumentReviewDecision.source_id).where(
                    DocumentReviewDecision.tenant_id == tenant_id,
                    DocumentReviewDecision.source_id.is_not(None),
                )
            )
        ).all()
    )
    for row in rows:
        source_id = _source_id(row)
        if source_id in existing_ids:
            skipped("review_reviewdecision")
            continue
        case_id = review_case_map.get(str(row.get("review_case_id")))
        if case_id is None:
            continue
        await _insert_or_get_by_source(
            session,
            DocumentReviewDecision(
                tenant_id=tenant_id,
                review_case_id=case_id,
                before_state=row.get("before_state")
                if isinstance(row.get("before_state"), dict)
                else None,
                after_state=row.get("after_state")
                if isinstance(row.get("after_state"), dict)
                else None,
                source_system=SOURCE_SYSTEM,
                source_id=source_id,
            ),
            DocumentReviewDecision,
            tenant_id=tenant_id,
            source_id=source_id,
        )
        created("review_reviewdecision")
