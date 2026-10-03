"""Report types of historical statements and resolutions (13.1, GAJ-501, wave 23).

``historical_statement`` files the statements the old system sent (WEG annual statement, WEG
budget, operating and heating cost statements of rentals) with period, version, recipient
unit, stated result, dispatch date and resolution reference. ``resolution`` files the
collection of resolutions (date, agenda item, wording, result, form).

Same pipeline as the other report types: the user maps the export columns to the fields below
(real Immoware24 column names are not specified, AM09-01 stays open), a repeated run creates
nothing twice and nothing is overwritten (equal: ``unchanged``, different: ``conflict``). A new
version of a statement is a new row with its own version number, never a replacement.

Filing and checking only: no posting, no receivable from a stated result, no dispatch, no live
statement and no live resolution of the platform (G3, G4 closed). :func:`check_report` lists
the open points of the filed history (missing resolution, unknown unit, several versions).
"""

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.imports.fields import FIELDS, Field
from mhvp.imports.history_models import (
    RESOLUTION_FORMS,
    RESOLUTION_RESULTS,
    STATEMENT_KINDS,
    MigratedResolution,
    MigratedStatement,
)
from mhvp.imports.models import ReportType, RowStatus
from mhvp.imports.reconciliation import normalise_property_number
from mhvp.properties.models import Property, Unit

Result = tuple[RowStatus, str | None, uuid.UUID | None, list[str]]
CENT = Decimal("0.01")
HOA_KINDS = frozenset({"hoa_annual", "hoa_budget"})

STATEMENT_FIELDS: dict[ReportType, tuple[Field, ...]] = {
    ReportType.HISTORICAL_STATEMENT: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("kind", "choice", True, STATEMENT_KINDS, "Abrechnungsart"),
        Field("period_start", "date", True, label="Zeitraum von"),
        Field("period_end", "date", True, label="Zeitraum bis"),
        Field("version", "decimal", label="Version (1, 2, ...)"),
        Field("unit_number", "text", label="Einheitennummer (leer: Gesamtabrechnung)"),
        Field("recipient", "text", label="Empfänger"),
        Field("result_amount", "decimal", label="Ergebnis laut Abrechnung"),
        Field("sent_on", "date", label="Versandt am"),
        Field("resolution_ref", "text", label="Beschlussbezug"),
        Field("document_ref", "text", label="Dokumentverweis"),
        Field("note", "text", label="Bemerkung"),
    ),
    ReportType.RESOLUTION: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("resolved_on", "date", True, label="Beschlussdatum"),
        Field("item_number", "text", True, label="TOP"),
        Field("title", "text", True, label="Gegenstand"),
        Field("reference", "text", label="Beschlussnummer"),
        Field("wording", "text", label="Beschlusswortlaut"),
        Field("result", "choice", False, RESOLUTION_RESULTS, "Ergebnis"),
        Field("form", "choice", False, RESOLUTION_FORMS, "Versammlung oder Umlauf"),
        Field("note", "text", label="Bemerkung"),
    ),
}

FIELDS.update(STATEMENT_FIELDS)

UNDOABLE_ENTITY_TYPES = frozenset({"migrated_statement", "migrated_resolution"})


def handles(report_type: ReportType) -> bool:
    return report_type in STATEMENT_FIELDS


def _invalid(message: str) -> Result:
    return RowStatus.INVALID, None, None, [message]


def _text(v: dict[str, Any], key: str, limit: int) -> str | None:
    value = v.get(key)
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()[:limit]


async def _property(session: AsyncSession, number: Any) -> Property | None:
    row: Property | None = await session.scalar(
        select(Property).where(Property.number == (normalise_property_number(number) or ""))
    )
    return row


async def _statement(
    session: AsyncSession, principal: Any, v: dict[str, Any], ctx: dict[str, Any]
) -> Result:
    """Key: object, kind, period, unit and version. A different version is a new row."""
    prop = await _property(session, v["property_number"])
    if prop is None:
        return _invalid("Objekt nicht auf der Plattform")
    start = date.fromisoformat(v["period_start"])
    end = date.fromisoformat(v["period_end"])
    if end < start:
        return _invalid("Zeitraum bis liegt vor Zeitraum von")
    version = 1
    if v.get("version") is not None:
        try:
            number = Decimal(str(v["version"]))
        except InvalidOperation:
            return _invalid("Version muss eine ganze Zahl ab 1 sein")
        if number != number.to_integral_value() or not 1 <= number <= 99:
            return _invalid("Version muss eine ganze Zahl ab 1 sein")
        version = int(number)
    unit_number = _text(v, "unit_number", 50) or ""
    amount = (
        Decimal(str(v["result_amount"])).quantize(CENT)
        if v.get("result_amount") is not None
        else None
    )
    values: dict[str, Any] = {
        "recipient": _text(v, "recipient", 300),
        "result_amount": amount,
        "sent_on": date.fromisoformat(v["sent_on"]) if v.get("sent_on") else None,
        "resolution_ref": _text(v, "resolution_ref", 200),
        "document_ref": _text(v, "document_ref", 300),
        "note": _text(v, "note", 4000),
    }
    existing = await session.scalar(
        select(MigratedStatement).where(
            MigratedStatement.property_id == prop.id,
            MigratedStatement.kind == v["kind"],
            MigratedStatement.period_start == start,
            MigratedStatement.period_end == end,
            MigratedStatement.unit_number == unit_number,
            MigratedStatement.version == version,
        )
    )
    if existing is not None:
        same = all(getattr(existing, k) == val for k, val in values.items())
        return (
            RowStatus.UNCHANGED if same else RowStatus.CONFLICT,
            "migrated_statement",
            existing.id,
            [] if same else ["Abrechnungsversion vorhanden mit abweichenden Angaben"],
        )
    messages: list[str] = []
    unit_id = None
    if unit_number:
        unit_id = await session.scalar(
            select(Unit.id).where(Unit.property_id == prop.id, Unit.number == unit_number)
        )
        if unit_id is None:
            messages.append("Einheit nicht auf der Plattform; Abrechnung ohne Einheitenbezug")
    row = MigratedStatement(
        tenant_id=principal.tenant_id,
        property_id=prop.id,
        kind=v["kind"],
        period_start=start,
        period_end=end,
        version=version,
        unit_number=unit_number,
        unit_id=unit_id,
        source_file_id=ctx.get("source_file_id"),
        row_number=ctx.get("row_number"),
        **values,
    )
    session.add(row)
    await session.flush()
    return RowStatus.CREATED, "migrated_statement", row.id, messages


async def _resolution(
    session: AsyncSession, principal: Any, v: dict[str, Any], ctx: dict[str, Any]
) -> Result:
    """Key: object, date and agenda item."""
    prop = await _property(session, v["property_number"])
    if prop is None:
        return _invalid("Objekt nicht auf der Plattform")
    resolved_on = date.fromisoformat(v["resolved_on"])
    item = str(v["item_number"]).strip()[:50]
    if not item:
        return _invalid("TOP fehlt")
    values: dict[str, Any] = {
        "title": str(v["title"]).strip()[:300],
        "reference": _text(v, "reference", 200),
        "wording": _text(v, "wording", 20000),
        "result": v.get("result") or "unknown",
        "form": v.get("form") or "unknown",
        "note": _text(v, "note", 4000),
    }
    existing = await session.scalar(
        select(MigratedResolution).where(
            MigratedResolution.property_id == prop.id,
            MigratedResolution.resolved_on == resolved_on,
            MigratedResolution.item_number == item,
        )
    )
    if existing is not None:
        same = all(getattr(existing, k) == val for k, val in values.items())
        return (
            RowStatus.UNCHANGED if same else RowStatus.CONFLICT,
            "migrated_resolution",
            existing.id,
            [] if same else ["Beschluss vorhanden mit abweichenden Angaben"],
        )
    row = MigratedResolution(
        tenant_id=principal.tenant_id,
        property_id=prop.id,
        resolved_on=resolved_on,
        item_number=item,
        source_file_id=ctx.get("source_file_id"),
        row_number=ctx.get("row_number"),
        **values,
    )
    session.add(row)
    await session.flush()
    return RowStatus.CREATED, "migrated_resolution", row.id, []


HANDLERS: dict[ReportType, Any] = {
    ReportType.HISTORICAL_STATEMENT: _statement,
    ReportType.RESOLUTION: _resolution,
}


async def apply_row(
    session: AsyncSession,
    principal: Any,
    report_type: ReportType,
    values: dict[str, Any],
    ctx: dict[str, Any],
) -> Result:
    result: Result = await HANDLERS[report_type](session, principal, values, ctx)
    return result


# Undo (called by mhvp.ai.imports) ---------------------------------------------------------


async def referenced(session: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> str | None:
    """Filed history is referenced by nothing on the platform; undo is always possible."""
    return None


async def remove(session: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> None:
    model: Any = {
        "migrated_statement": MigratedStatement,
        "migrated_resolution": MigratedResolution,
    }[entity_type]
    row = await session.get(model, entity_id)
    if row is not None:
        await session.delete(row)
        await session.flush()


# Check report -----------------------------------------------------------------------------


def _finding(
    prop: Property, entity: str, entity_id: uuid.UUID, code: str, message: str
) -> dict[str, Any]:
    return {
        "property_id": str(prop.id),
        "property_number": prop.number,
        "entity": entity,
        "entity_id": str(entity_id),
        "code": code,
        "message": message,
    }


async def check_report(
    session: AsyncSession,
    property_id: uuid.UUID | None = None,
    allowed: frozenset[uuid.UUID] | None = None,
) -> dict[str, Any]:
    """Open points of the filed history per property. Reads only; corrects nothing.

    Codes: ``resolution_missing`` (reference not found in the filed resolutions of the
    property), ``resolution_ref_empty`` (WEG statement without resolution reference),
    ``unit_unknown`` (unit number without platform unit), ``several_versions`` (more than one
    version of the same statement; which one is binding is not decided by the platform).
    """
    sq = select(MigratedStatement)
    rq = select(MigratedResolution)
    if property_id is not None:
        sq = sq.where(MigratedStatement.property_id == property_id)
        rq = rq.where(MigratedResolution.property_id == property_id)
    if allowed is not None:
        sq = sq.where(MigratedStatement.property_id.in_(allowed))
        rq = rq.where(MigratedResolution.property_id.in_(allowed))
    statements = (await session.scalars(sq)).all()
    resolutions = (await session.scalars(rq)).all()
    prop_ids = {s.property_id for s in statements} | {r.property_id for r in resolutions}
    props = {
        p.id: p
        for p in (await session.scalars(select(Property).where(Property.id.in_(prop_ids)))).all()
    }
    refs: dict[uuid.UUID, set[str]] = defaultdict(set)
    for r in resolutions:
        if r.reference:
            refs[r.property_id].add(r.reference.strip().casefold())
        refs[r.property_id].add(f"{r.resolved_on.isoformat()} top {r.item_number}".casefold())
    versions: dict[tuple[Any, ...], list[MigratedStatement]] = defaultdict(list)
    findings: list[dict[str, Any]] = []
    for s in sorted(statements, key=lambda x: (x.period_end, x.kind, x.unit_number, x.version)):
        prop = props[s.property_id]
        versions[(s.property_id, s.kind, s.period_start, s.period_end, s.unit_number)].append(s)
        if s.resolution_ref:
            if s.resolution_ref.strip().casefold() not in refs[s.property_id]:
                findings.append(
                    _finding(
                        prop,
                        "statement",
                        s.id,
                        "resolution_missing",
                        f"Beschluss {s.resolution_ref} nicht in der Beschlusssammlung",
                    )
                )
        elif s.kind in HOA_KINDS:
            findings.append(
                _finding(prop, "statement", s.id, "resolution_ref_empty", "Kein Beschlussbezug")
            )
        if s.unit_number and s.unit_id is None:
            findings.append(
                _finding(
                    prop,
                    "statement",
                    s.id,
                    "unit_unknown",
                    f"Einheit {s.unit_number} nicht auf der Plattform",
                )
            )
    for group in versions.values():
        if len(group) > 1:
            latest = max(group, key=lambda x: x.version)
            findings.append(
                _finding(
                    props[latest.property_id],
                    "statement",
                    latest.id,
                    "several_versions",
                    f"{len(group)} Versionen; maßgebliche Version nicht festgelegt",
                )
            )
    per_property = []
    for pid, prop in sorted(props.items(), key=lambda item: item[1].number):
        per_property.append(
            {
                "property_id": str(pid),
                "property_number": prop.number,
                "statements": sum(1 for s in statements if s.property_id == pid),
                "resolutions": sum(1 for r in resolutions if r.property_id == pid),
                "findings": sum(1 for f in findings if f["property_id"] == str(pid)),
            }
        )
    return {
        "totals": {
            "statements": len(statements),
            "resolutions": len(resolutions),
            "findings": len(findings),
        },
        "properties": per_property,
        "findings": findings,
    }
