"""M29 Stufe 4 (docs/plans/M29-dms.md): domain logic of the objektakte service connection.

* :func:`link_filed_document`: a document filed by objektakte (webhook ``document.filed`` or the
  backfill of one object) becomes a CRM document (M6) linked to the property with the same
  number. Matching order: the objektakte id (``source_system = "objektakte"``, the same key the
  M35 dump import uses, so both paths meet on one row), then the Drive file id
  (``storage = google_drive``, ``storage_ref``), then the content hash ``sha256``. A match is
  linked, never duplicated; the original stays in Google Drive (no binary copy).
* :func:`reconcile_persons`: test run of an owner or tenant list from objektakte against the
  current contracts of the property (``mhvp.objektakte.lists.persons_list``). Read only.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.events import emit
from mhvp.documents.models import (
    Document,
    DocumentLink,
    DocumentSource,
    LinkRole,
    StorageKind,
    TextStatus,
)
from mhvp.objektakte import lists
from mhvp.objektakte.dms_models import ObjektakteUpload
from mhvp.properties.models import Property, Unit

SOURCE_SYSTEM = "objektakte"  # same as mhvp.objektakte.objektakte_import.SOURCE_SYSTEM
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def normalize_number(raw: object) -> str | None:
    """objektakte object number ("523", "82", "0623") to the CRM form (exactly three digits).
    ``None`` when it does not fit; nothing is truncated or renumbered (same rule as the M35
    import)."""
    value = str(raw or "").strip()
    if not value.isdigit():
        return None
    number = int(value)
    return f"{number:03d}" if 1 <= number <= 999 else None


async def property_by_number(
    session: AsyncSession, tenant_id: uuid.UUID, raw_number: object
) -> Property | None:
    number = normalize_number(raw_number)
    if number is None:
        return None
    row: Property | None = await session.scalar(
        select(Property).where(Property.tenant_id == tenant_id, Property.number == number)
    )
    return row


async def property_ids_by_number(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, str]:
    rows = (
        await session.execute(
            select(Property.number, Property.id).where(Property.tenant_id == tenant_id)
        )
    ).all()
    return {number: str(pid) for number, pid in rows}


@dataclass(frozen=True)
class FiledDocument:
    """One document as described in contract endpoint 3 (and the webhook payload)."""

    id: int
    title: str
    sha256: str
    drive_file_id: str | None
    drive_url: str | None
    doc_type: str | None
    category: str | None
    subfolder: str | None
    status: str | None
    filed_at: str | None
    mime_type: str | None
    size_bytes: int | None
    # Contract extension 26.09.2026 (upload from the CRM): CRM document id and Paperless id
    crm_document_id: str | None = None
    paperless_id: int | None = None

    @property
    def source_id(self) -> str:
        return str(self.id)


def _opt_str(raw: dict[str, Any], key: str, limit: int) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} ist kein Text.")
    value = value.strip()
    return value[:limit] or None


def parse_document(raw: object) -> FiledDocument:
    """Validates one document object; raises ``ValueError`` with a German message."""
    if not isinstance(raw, dict):
        raise ValueError("Dokument fehlt.")
    doc_id = raw.get("id")
    if not isinstance(doc_id, int) or isinstance(doc_id, bool) or doc_id <= 0:
        raise ValueError("Dokument-ID fehlt oder ist ungültig.")
    sha256 = raw.get("sha256")
    if not isinstance(sha256, str) or not _SHA256.match(sha256.strip().lower()):
        raise ValueError("sha256 fehlt oder ist ungültig.")
    size = raw.get("size_bytes")
    if size is not None and (not isinstance(size, int) or isinstance(size, bool) or size < 0):
        raise ValueError("size_bytes ist ungültig.")
    paperless = raw.get("paperless_id")
    if isinstance(paperless, bool):
        paperless = None
    return FiledDocument(
        id=doc_id,
        title=_opt_str(raw, "title", 300) or f"objektakte-{doc_id}",
        sha256=sha256.strip().lower(),
        drive_file_id=_opt_str(raw, "drive_file_id", 512),
        drive_url=_opt_str(raw, "drive_url", 1000),
        doc_type=_opt_str(raw, "doc_type", 200),
        category=_opt_str(raw, "category", 200),
        subfolder=_opt_str(raw, "subfolder", 200),
        status=_opt_str(raw, "status", 64),
        filed_at=_opt_str(raw, "filed_at", 64),
        mime_type=_opt_str(raw, "mime_type", 127),
        size_bytes=size,
        crm_document_id=_opt_str(raw, "crm_document_id", 64),
        paperless_id=paperless if isinstance(paperless, int) and paperless > 0 else None,
    )


def _remote_meta(doc: FiledDocument) -> dict[str, Any]:
    return {
        "objektakte_document_id": doc.id,
        "objektakte_status": doc.status,
        "category": doc.category,
        "subfolder": doc.subfolder,
        "doc_type": doc.doc_type,
        "drive_url": doc.drive_url,
        "drive_file_id": doc.drive_file_id,
        "paperless_id": doc.paperless_id,
        "filed_at": doc.filed_at,
    }


async def crm_document_for(
    session: AsyncSession, tenant_id: uuid.UUID, doc: FiledDocument
) -> Document | None:
    """The CRM document an objektakte document came from (upload from the CRM), or None."""
    if not doc.crm_document_id:
        return None
    try:
        crm_id = uuid.UUID(doc.crm_document_id)
    except ValueError:
        return None
    found: Document | None = await session.scalar(
        select(Document).where(Document.tenant_id == tenant_id, Document.id == crm_id)
    )
    return found


async def _mark_upload_done(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID, doc: FiledDocument
) -> None:
    upload = await session.scalar(
        select(ObjektakteUpload).where(
            ObjektakteUpload.tenant_id == tenant_id, ObjektakteUpload.document_id == document_id
        )
    )
    if upload is None:
        return
    upload.objektakte_document_id = upload.objektakte_document_id or doc.id
    upload.remote = {k: v for k, v in _remote_meta(doc).items() if v is not None}
    if upload.status != "done":
        upload.status = "done"
        upload.done_at = datetime.now(UTC)
        upload.next_attempt_at = None
        upload.last_error = None


async def matching_documents(
    session: AsyncSession, tenant_id: uuid.UUID, docs: list[FiledDocument]
) -> dict[int, Document]:
    """CRM document per objektakte document id, by id, Drive file id or sha256 (in this order)."""
    if not docs:
        return {}
    source_ids = [d.source_id for d in docs]
    drive_ids = [d.drive_file_id for d in docs if d.drive_file_id]
    hashes = [d.sha256 for d in docs]
    conditions = [
        (Document.source_system == SOURCE_SYSTEM) & Document.source_id.in_(source_ids),
        Document.sha256.in_(hashes),
    ]
    if drive_ids:
        conditions.append(
            (Document.storage == StorageKind.GOOGLE_DRIVE) & Document.storage_ref.in_(drive_ids)
        )
    candidates = (
        await session.scalars(
            select(Document)
            .where(Document.tenant_id == tenant_id, or_(*conditions))
            .order_by(Document.created_at, Document.id)
        )
    ).all()
    by_source = {
        c.source_id: c for c in candidates if c.source_system == SOURCE_SYSTEM and c.source_id
    }
    by_drive: dict[str, Document] = {}
    by_hash: dict[str, Document] = {}
    for c in candidates:
        if c.storage == StorageKind.GOOGLE_DRIVE:
            by_drive.setdefault(c.storage_ref, c)
        by_hash.setdefault(c.sha256, c)
    result: dict[int, Document] = {}
    for d in docs:
        match = (
            by_source.get(d.source_id)
            or (by_drive.get(d.drive_file_id) if d.drive_file_id else None)
            or by_hash.get(d.sha256)
        )
        if match is not None:
            result[d.id] = match
    return result


async def _ensure_property_link(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID, property_id: uuid.UUID
) -> bool:
    exists = await session.scalar(
        select(DocumentLink.id).where(
            DocumentLink.tenant_id == tenant_id,
            DocumentLink.document_id == document_id,
            DocumentLink.entity_type == "property",
            DocumentLink.entity_id == property_id,
        )
    )
    if exists is not None:
        return False
    session.add(
        DocumentLink(
            tenant_id=tenant_id,
            document_id=document_id,
            entity_type="property",
            entity_id=property_id,
            role=LinkRole.ORIGINAL,
        )
    )
    return True


@dataclass(frozen=True)
class LinkResult:
    document_id: uuid.UUID
    property_id: uuid.UUID | None
    outcome: str  # created | linked | updated | unchanged


async def link_filed_document(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    object_number: str,
    doc: FiledDocument,
    actor_user_id: uuid.UUID | None,
    existing: Document | None = None,
) -> LinkResult:
    """Creates or links the CRM document of one filed objektakte document (module docstring)."""
    prop = await property_by_number(session, tenant_id, object_number)
    property_id = prop.id if prop is not None else None
    if existing is None:
        existing = await crm_document_for(session, tenant_id, doc)
    if existing is None:
        existing = (await matching_documents(session, tenant_id, [doc])).get(doc.id)
    if existing is not None and doc.status == "filed":
        await _mark_upload_done(session, tenant_id, existing.id, doc)
    remote = _remote_meta(doc)

    if existing is None:
        document = Document(
            tenant_id=tenant_id,
            title=doc.title,
            filename=doc.title[:255],
            mime_type=doc.mime_type or "application/octet-stream",
            size=doc.size_bytes or 0,
            sha256=doc.sha256,
            storage=StorageKind.GOOGLE_DRIVE,
            storage_ref=doc.drive_file_id or f"objektakte:{doc.id}",
            text_status=TextStatus.NONE,
            source=DocumentSource.IMPORT,
            visibility=["tenant"],
            created_by=actor_user_id,
            source_system=SOURCE_SYSTEM,
            source_id=doc.source_id,
            source_meta={"origin": "objektakte_api", **remote},
        )
        session.add(document)
        await session.flush()
        outcome = "created"
    else:
        document = existing
        changed = False
        meta = dict(document.source_meta or {})
        if document.source_system == SOURCE_SYSTEM:
            # A row of objektakte origin (this connection or the M35 dump import): keep its
            # Drive reference and hash current; a placeholder hash of the dump import is
            # replaced by the real one.
            if doc.drive_file_id and document.storage_ref != doc.drive_file_id:
                document.storage = StorageKind.GOOGLE_DRIVE
                document.storage_ref = doc.drive_file_id
                changed = True
            if document.sha256 != doc.sha256:
                document.sha256 = doc.sha256
                meta.pop("sha256_placeholder", None)
                changed = True
            merged = {**meta, **{k: v for k, v in remote.items() if v is not None}}
        else:
            # A CRM document of another origin (upload, mirror): provenance stays untouched,
            # the objektakte reference is only noted next to it.
            merged = {**meta, "objektakte": {k: v for k, v in remote.items() if v is not None}}
        if merged != meta:
            document.source_meta = merged
            changed = True
        linked = False
        if property_id is not None:
            linked = await _ensure_property_link(session, tenant_id, document.id, property_id)
        if linked:
            outcome = "linked"
        elif changed:
            outcome = "updated"
        else:
            outcome = "unchanged"
        await session.flush()
        if outcome == "unchanged":
            return LinkResult(document.id, property_id, outcome)
    if outcome == "created" and property_id is not None:
        await _ensure_property_link(session, tenant_id, document.id, property_id)
        await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="objektakte.document_linked",
        entity_type="document",
        entity_id=document.id,
        actor_user_id=actor_user_id,
        payload={
            "objektakte_document_id": doc.id,
            "object_number": object_number,
            "property_id": str(property_id) if property_id else None,
            "outcome": outcome,
        },
    )
    return LinkResult(document.id, property_id, outcome)


# --- owner and tenant lists: test run against the CRM ------------------------------------


def _norm_name(value: object) -> str:
    return " ".join(str(value or "").replace(",", " ").split()).casefold()


def _name_key(value: object) -> frozenset[str]:
    """Order independent name comparison ("Müller, Anna" equals "Anna Müller")."""
    return frozenset(_norm_name(value).split())


def _norm_label(value: object) -> str:
    text = "".join(str(value or "").split()).casefold()
    if text.isdigit():
        return text.lstrip("0") or "0"
    return text


async def _unit_index(session: AsyncSession, property_id: uuid.UUID) -> dict[str, Unit]:
    units = (await session.scalars(select(Unit).where(Unit.property_id == property_id))).all()
    index: dict[str, Unit] = {}
    for unit in units:
        for label in (unit.number, unit.label):
            if label:
                index.setdefault(_norm_label(label), unit)
    return index


def _remote_person(kind: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Only the fields the reconciliation needs; e-mail and IBAN (even masked) are dropped."""
    labels = raw.get("unit_labels")
    row: dict[str, Any] = {
        "source_id": str(raw.get("id") or ""),
        "display_name": str(raw.get("display_name") or "").strip()[:300],
        "unit_labels": [str(x).strip()[:50] for x in labels if str(x).strip()]
        if isinstance(labels, list)
        else [],
    }
    if kind == "owners":
        share = raw.get("share")
        row["share"] = str(share)[:50] if share is not None else None
    else:
        row["lease_start"] = (
            raw.get("lease_start") if isinstance(raw.get("lease_start"), str) else None
        )
        row["lease_end"] = raw.get("lease_end") if isinstance(raw.get("lease_end"), str) else None
    return row


STATUS_LABELS = {
    "unchanged": "übereinstimmend",
    "new": "neu, im CRM kein laufender Vertrag",
    "conflict": "abweichend",
    "unit_unknown": "Einheit im CRM unbekannt",
    "no_unit": "ohne Einheit",
    "crm_only": "nur im CRM",
}


async def reconcile_persons(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    property_row: Property,
    kind: str,
    remote_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Test run: compares each objektakte row with the current contracts (same kind) of every
    unit it names. Status per row: ``unchanged`` (every unit known and the name is a party of a
    current contract there), ``conflict`` (unit known, current contract with another name),
    ``new`` (unit known, no current contract), ``unit_unknown`` (a unit label is not found),
    ``no_unit`` (the row names no unit). CRM persons that objektakte does not list are added as
    ``crm_only``. Nothing is written."""
    crm = await lists.persons_list(session, tenant_id, property_row, kind)  # type: ignore[arg-type]
    by_unit: dict[str, list[dict[str, Any]]] = {}
    for row in crm["rows"]:
        by_unit.setdefault(row["unit_id"], []).append(row)
    units = await _unit_index(session, property_row.id)
    matched_crm: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for raw in remote_rows:
        person = _remote_person(kind, raw)
        key = _name_key(person["display_name"])
        details: list[dict[str, Any]] = []
        statuses: set[str] = set()
        for label in person["unit_labels"]:
            unit = units.get(_norm_label(label))
            if unit is None:
                statuses.add("unit_unknown")
                details.append({"unit_label": label, "status": "unit_unknown"})
                continue
            current = by_unit.get(str(unit.id), [])
            same = [r for r in current if _name_key(r["name"]) == key]
            if same:
                statuses.add("unchanged")
                for r in same:
                    matched_crm.add((r["unit_id"], r["name"]))
                details.append(
                    {"unit_label": label, "unit_id": str(unit.id), "status": "unchanged"}
                )
            elif current:
                statuses.add("conflict")
                details.append(
                    {
                        "unit_label": label,
                        "unit_id": str(unit.id),
                        "status": "conflict",
                        "crm_names": sorted({r["name"] for r in current}),
                    }
                )
            else:
                statuses.add("new")
                details.append({"unit_label": label, "unit_id": str(unit.id), "status": "new"})
        if not person["unit_labels"]:
            status = "no_unit"
        else:
            status = next(
                s for s in ("unit_unknown", "conflict", "new", "unchanged") if s in statuses
            )
        out.append({**person, "status": status, "units": details})
    for row in crm["rows"]:
        if (row["unit_id"], row["name"]) in matched_crm:
            continue
        out.append(
            {
                "source_id": None,
                "display_name": row["name"],
                "unit_labels": [row["unit_label"] or row["unit_number"]],
                "status": "crm_only",
                "units": [
                    {
                        "unit_label": row["unit_label"] or row["unit_number"],
                        "unit_id": row["unit_id"],
                        "status": "crm_only",
                        "contract_id": row["contract_id"],
                    }
                ],
            }
        )
    counts: dict[str, int] = dict.fromkeys(STATUS_LABELS, 0)
    for row in out:
        counts[row["status"]] += 1
    summary = {
        "reference_date": crm["reference_date"],
        "remote_total": len(remote_rows),
        "crm_total": len(crm["rows"]),
        "counts": counts,
    }
    return out, summary


def now_utc() -> datetime:
    return datetime.now(UTC)
