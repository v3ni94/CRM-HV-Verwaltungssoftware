"""Reconciliation report objektakte vs. CRM for the parallel operation (M35 Stufe 5 acceptance,
docs/plans/M35-objektakte-uebernahme.md: "an mindestens fünf aufeinanderfolgenden Werktagen
keine ungeklärte Differenz zwischen objektakte- und CRM-Dokumentenzahl je Objekt").

Per object number: number of documents in objektakte (read API, endpoint 3 of
docs/integrations/objektakte.md) and in the CRM (`Document.source_system == "objektakte"`,
object via the `DocumentLink` of type `property`), documents missing on either side (by
objektakte id, which the CRM keeps as `source_id`), and documents whose `sha256` differs. A CRM
document whose hash is the Stufe 2 placeholder (`source_meta["sha256_placeholder"]`) is
reported separately, not as a mismatch: objektakte had not hashed it at import time.

The comparison is pure (`reconcile`), the endpoint only gathers both sides. Nothing is
changed by the report; a difference is resolved by the differential import
(`/objektakte/sync/runs`) or by hand.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.documents.models import Document, DocumentLink
from mhvp.properties.models import Property

SOURCE_SYSTEM = "objektakte"
NO_OBJECT = "ohne_objekt"
MAX_LISTED_IDS = 50


@dataclass(frozen=True)
class CrmDoc:
    source_id: str
    sha256: str
    object_number: str | None
    placeholder: bool = False


@dataclass(frozen=True)
class RemoteDoc:
    source_id: str
    sha256: str | None
    object_number: str


@dataclass
class ObjectReport:
    object_number: str
    objektakte_count: int = 0
    crm_count: int = 0
    missing_in_crm: list[str] = field(default_factory=list)
    missing_in_objektakte: list[str] = field(default_factory=list)
    hash_mismatches: list[dict[str, str]] = field(default_factory=list)
    placeholders: int = 0
    missing_in_crm_total: int = 0
    missing_in_objektakte_total: int = 0
    hash_mismatch_total: int = 0

    @property
    def ok(self) -> bool:
        return not (
            self.missing_in_crm_total
            or self.missing_in_objektakte_total
            or self.hash_mismatch_total
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "object_number": self.object_number,
            "objektakte_count": self.objektakte_count,
            "crm_count": self.crm_count,
            "missing_in_crm": self.missing_in_crm,
            "missing_in_crm_total": self.missing_in_crm_total,
            "missing_in_objektakte": self.missing_in_objektakte,
            "missing_in_objektakte_total": self.missing_in_objektakte_total,
            "hash_mismatches": self.hash_mismatches,
            "hash_mismatch_total": self.hash_mismatch_total,
            "placeholders": self.placeholders,
            "ok": self.ok,
        }


def _sorted_ids(ids: set[str]) -> list[str]:
    return sorted(ids, key=lambda value: (len(value), value))


def reconcile(crm_docs: list[CrmDoc], remote_docs: list[RemoteDoc]) -> dict[str, Any]:
    """Pure comparison. Object numbers are compared as strings the way the CRM stores
    `Property.number` (three digits); the endpoint normalises both sides before calling."""
    by_object: dict[str, ObjectReport] = {}

    def report_for(number: str | None) -> ObjectReport:
        key = number or NO_OBJECT
        if key not in by_object:
            by_object[key] = ObjectReport(object_number=key)
        return by_object[key]

    crm_index: dict[str, CrmDoc] = {}
    for doc in crm_docs:
        crm_index[doc.source_id] = doc
        report = report_for(doc.object_number)
        report.crm_count += 1
        if doc.placeholder:
            report.placeholders += 1
    remote_index: dict[str, RemoteDoc] = {}
    for remote_doc in remote_docs:
        remote_index[remote_doc.source_id] = remote_doc
        report_for(remote_doc.object_number).objektakte_count += 1

    missing_in_crm: dict[str, set[str]] = {}
    for source_id, remote in remote_index.items():
        crm = crm_index.get(source_id)
        report = report_for(remote.object_number)
        if crm is None:
            missing_in_crm.setdefault(report.object_number, set()).add(source_id)
            continue
        if crm.placeholder or not remote.sha256:
            continue
        if crm.sha256.lower() != remote.sha256.lower():
            report.hash_mismatch_total += 1
            if len(report.hash_mismatches) < MAX_LISTED_IDS:
                report.hash_mismatches.append(
                    {"source_id": source_id, "crm": crm.sha256, "objektakte": remote.sha256}
                )
    missing_in_objektakte: dict[str, set[str]] = {}
    for source_id, crm in crm_index.items():
        if source_id not in remote_index:
            key = crm.object_number or NO_OBJECT
            missing_in_objektakte.setdefault(key, set()).add(source_id)

    for number, ids in missing_in_crm.items():
        report = by_object[number]
        report.missing_in_crm_total = len(ids)
        report.missing_in_crm = _sorted_ids(ids)[:MAX_LISTED_IDS]
    for number, ids in missing_in_objektakte.items():
        report = by_object[number]
        report.missing_in_objektakte_total = len(ids)
        report.missing_in_objektakte = _sorted_ids(ids)[:MAX_LISTED_IDS]

    objects = [by_object[k].as_dict() for k in sorted(by_object)]
    totals = {
        "objects": len(objects),
        "objektakte_documents": len(remote_index),
        "crm_documents": len(crm_index),
        "missing_in_crm": sum(o["missing_in_crm_total"] for o in objects),
        "missing_in_objektakte": sum(o["missing_in_objektakte_total"] for o in objects),
        "hash_mismatches": sum(o["hash_mismatch_total"] for o in objects),
        "placeholders": sum(o["placeholders"] for o in objects),
        "objects_with_differences": sum(1 for o in objects if not o["ok"]),
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "ok": totals["objects_with_differences"] == 0,
        "totals": totals,
        "objects": objects,
    }


async def crm_documents(session: AsyncSession, tenant_id: uuid.UUID) -> list[CrmDoc]:
    """Every taken over document of the tenant with the number of its linked property."""
    links = (
        await session.execute(
            select(DocumentLink.document_id, Property.number)
            .join(Property, Property.id == DocumentLink.entity_id)
            .where(
                DocumentLink.tenant_id == tenant_id,
                DocumentLink.entity_type == "property",
            )
        )
    ).all()
    number_by_document: dict[uuid.UUID, str] = {}
    for document_id, number in links:
        number_by_document[document_id] = number
    rows = (
        await session.scalars(
            select(Document).where(
                Document.tenant_id == tenant_id, Document.source_system == SOURCE_SYSTEM
            )
        )
    ).all()
    return [
        CrmDoc(
            source_id=str(row.source_id),
            sha256=row.sha256,
            object_number=number_by_document.get(row.id),
            placeholder=bool((row.source_meta or {}).get("sha256_placeholder")),
        )
        for row in rows
        if row.source_id
    ]


def remote_documents(number: str, rows: list[dict[str, Any]]) -> list[RemoteDoc]:
    """Endpoint 3 rows of one object as `RemoteDoc`s (ids as strings, hash lower case)."""
    out: list[RemoteDoc] = []
    for row in rows:
        source_id = row.get("id")
        if source_id is None:
            continue
        sha = row.get("sha256")
        out.append(
            RemoteDoc(
                source_id=str(source_id),
                sha256=str(sha).lower() if sha else None,
                object_number=number,
            )
        )
    return out
