"""Register of independent expected results and acceptance protocol per annex D case
(V16, AE01, docs/rules/AE01-ACCEPTANCE.md).

Workflow: a person with ``acceptance:manage`` records a draft version (inputs, expected
values, source, calculation) and submits it; a second person with ``acceptance:approve``
releases or rejects it (never the author). A released version is frozen (DB guard); a newer
released version supersedes it. Acceptance outcomes are recorded per released version and
are append only. The markdown export mirrors ``docs/acceptance/abnahme-anhang-d.md``.

Who the expert person is stays the operator's decision (V16 open). Nothing here opens a gate,
posts, pays or replaces a domain check (ADR 0003); ``g1_acceptance`` stays its own path.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.acceptance_models import (
    AcceptanceExpected,
    AcceptanceExpectedStatus,
    AcceptanceOutcome,
    AcceptanceResult,
)
from mhvp.accounting.g1_opening import CASE_KEYS as G1_CASE_KEYS
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

CASE_PATTERN = re.compile(r"^D(0[1-9]|[1-4][0-9]|5[0-8])$")
ALL_CASE_IDS: list[str] = [f"D{n:02d}" for n in range(1, 59)]
S = AcceptanceExpectedStatus


def _reject_floats(value: Any, path: str = "") -> None:
    """Money stays exact (6.9.8): numbers in inputs and expected values are given as strings
    (``"1234.56"``); a JSON float would be read with binary rounding."""
    if isinstance(value, float):
        raise ValueError(f"Zahl an {path or 'Wurzel'} als Zeichenkette angeben (kein float)")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_floats(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_floats(item, f"{path}[{index}]")


class AcceptanceExpectedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    inputs: dict[str, Any]
    expected: dict[str, Any] = Field(min_length=1)
    source: str = Field(min_length=3, max_length=4000)
    calculation: str | None = Field(default=None, max_length=8000)

    @field_validator("inputs", "expected")
    @classmethod
    def _exact(cls, value: dict[str, Any]) -> dict[str, Any]:
        _reject_floats(value)
        return value


class AcceptanceDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(approve|reject)$")
    name: str = Field(min_length=2, max_length=200)
    note: str | None = Field(default=None, max_length=4000)


class AcceptanceResultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: AcceptanceOutcome
    software_version: str = Field(min_length=1, max_length=40)
    commit_ref: str | None = Field(default=None, max_length=64)
    actual: dict[str, Any] | None = None
    note: str | None = Field(default=None, max_length=4000)
    name: str = Field(min_length=2, max_length=200)

    @field_validator("actual")
    @classmethod
    def _exact(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None:
            _reject_floats(value)
        return value


class AcceptanceResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    expected_id: uuid.UUID
    outcome: str
    software_version: str
    commit_ref: str | None
    actual: dict[str, Any] | None
    note: str | None
    decided_by_user_id: uuid.UUID
    decided_by_name: str
    decided_at: datetime


class AcceptanceExpectedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: str
    version: int
    title: str
    inputs: dict[str, Any]
    expected: dict[str, Any]
    source: str
    calculation: str | None
    status: str
    author_user_id: uuid.UUID
    submitted_at: datetime | None
    approved_by_user_id: uuid.UUID | None
    approved_by_name: str | None
    approved_at: datetime | None
    decision_note: str | None
    created_at: datetime


class AcceptanceCaseRow(BaseModel):
    case_id: str
    g1_scope: bool
    current: AcceptanceExpectedOut | None
    released: AcceptanceExpectedOut | None
    last_result: AcceptanceResultOut | None


class AcceptanceCaseList(BaseModel):
    note: str
    cases_total: int
    released_total: int
    passed_total: int
    items: list[AcceptanceCaseRow]


class AcceptanceCaseDetail(BaseModel):
    case_id: str
    versions: list[AcceptanceExpectedOut]
    results: list[AcceptanceResultOut]


NOTE_V16 = (
    "Die Benennung der fachkundigen Person ist eine Entscheidung des Betreibers (V16, offen). "
    "Das Register öffnet keine Freigabestufe."
)


def check_case(case_id: str) -> str:
    if not CASE_PATTERN.match(case_id):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            developer_message=f"Unknown annex D case {case_id!r} (D01 to D58).",
        )
    return case_id


async def _get(session: AsyncSession, expected_id: uuid.UUID) -> AcceptanceExpected:
    row = await session.get(AcceptanceExpected, expected_id, with_for_update=True)
    if row is None:
        raise ProblemError(ErrorCodes.ACCEPT_NOT_FOUND)
    return row


async def list_cases(session: AsyncSession, status: str | None = None) -> AcceptanceCaseList:
    rows = list(
        await session.scalars(
            select(AcceptanceExpected).order_by(
                AcceptanceExpected.case_id, AcceptanceExpected.version
            )
        )
    )
    results = list(
        await session.scalars(select(AcceptanceResult).order_by(AcceptanceResult.decided_at))
    )
    by_expected: dict[uuid.UUID, AcceptanceResult] = {r.expected_id: r for r in results}
    current: dict[str, AcceptanceExpected] = {}
    released: dict[str, AcceptanceExpected] = {}
    for row in rows:
        current[row.case_id] = row
        if row.status == S.APPROVED.value:
            released[row.case_id] = row
    items: list[AcceptanceCaseRow] = []
    for case_id in ALL_CASE_IDS:
        cur = current.get(case_id)
        rel = released.get(case_id)
        last = by_expected.get(rel.id) if rel is not None else None
        if status is not None and (cur is None or cur.status != status):
            continue
        items.append(
            AcceptanceCaseRow(
                case_id=case_id,
                g1_scope=case_id in G1_CASE_KEYS,
                current=AcceptanceExpectedOut.model_validate(cur) if cur else None,
                released=AcceptanceExpectedOut.model_validate(rel) if rel else None,
                last_result=AcceptanceResultOut.model_validate(last) if last else None,
            )
        )
    passed = 0
    for rel in released.values():
        last = by_expected.get(rel.id)
        if last is not None and last.outcome == AcceptanceOutcome.PASSED.value:
            passed += 1
    return AcceptanceCaseList(
        note=NOTE_V16,
        cases_total=len(ALL_CASE_IDS),
        released_total=len(released),
        passed_total=passed,
        items=items,
    )


async def case_detail(session: AsyncSession, case_id: str) -> AcceptanceCaseDetail:
    check_case(case_id)
    versions = list(
        await session.scalars(
            select(AcceptanceExpected)
            .where(AcceptanceExpected.case_id == case_id)
            .order_by(AcceptanceExpected.version)
        )
    )
    ids = [v.id for v in versions]
    results = (
        list(
            await session.scalars(
                select(AcceptanceResult)
                .where(AcceptanceResult.expected_id.in_(ids))
                .order_by(AcceptanceResult.decided_at)
            )
        )
        if ids
        else []
    )
    return AcceptanceCaseDetail(
        case_id=case_id,
        versions=[AcceptanceExpectedOut.model_validate(v) for v in versions],
        results=[AcceptanceResultOut.model_validate(r) for r in results],
    )


async def create_draft(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    case_id: str,
    body: AcceptanceExpectedIn,
) -> AcceptanceExpectedOut:
    check_case(case_id)
    latest = await session.scalar(
        select(func.max(AcceptanceExpected.version)).where(AcceptanceExpected.case_id == case_id)
    )
    row = AcceptanceExpected(
        tenant_id=tenant_id,
        case_id=case_id,
        version=(latest or 0) + 1,
        title=body.title,
        inputs=body.inputs,
        expected=body.expected,
        source=body.source,
        calculation=body.calculation,
        status=S.DRAFT.value,
        author_user_id=user_id,
        created_by=user_id,
    )
    session.add(row)
    await session.flush()
    await _event(session, row, user_id, "acceptance_expected.created")
    await session.refresh(row)
    return AcceptanceExpectedOut.model_validate(row)


async def update_draft(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    expected_id: uuid.UUID,
    body: AcceptanceExpectedIn,
) -> AcceptanceExpectedOut:
    row = await _get(session, expected_id)
    if row.status != S.DRAFT.value:
        raise ProblemError(ErrorCodes.ACCEPT_STATE)
    row.title = body.title
    row.inputs = body.inputs
    row.expected = body.expected
    row.source = body.source
    row.calculation = body.calculation
    row.updated_by = user_id
    await session.flush()
    await session.refresh(row)
    return AcceptanceExpectedOut.model_validate(row)


async def submit(
    session: AsyncSession, *, user_id: uuid.UUID, expected_id: uuid.UUID
) -> AcceptanceExpectedOut:
    row = await _get(session, expected_id)
    if row.status != S.DRAFT.value:
        raise ProblemError(ErrorCodes.ACCEPT_STATE)
    row.status = S.SUBMITTED.value
    row.submitted_at = datetime.now(UTC)
    row.updated_by = user_id
    await session.flush()
    await _event(session, row, user_id, "acceptance_expected.submitted")
    await session.refresh(row)
    return AcceptanceExpectedOut.model_validate(row)


async def decide(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    expected_id: uuid.UUID,
    body: AcceptanceDecisionIn,
) -> AcceptanceExpectedOut:
    row = await _get(session, expected_id)
    if row.status != S.SUBMITTED.value:
        raise ProblemError(ErrorCodes.ACCEPT_STATE)
    if row.author_user_id == user_id:
        raise ProblemError(ErrorCodes.ACCEPT_SAME_PERSON)
    now = datetime.now(UTC)
    if body.decision == "approve":
        previous = await session.scalar(
            select(AcceptanceExpected)
            .where(
                AcceptanceExpected.case_id == row.case_id,
                AcceptanceExpected.status == S.APPROVED.value,
            )
            .with_for_update()
        )
        if previous is not None:
            previous.status = S.SUPERSEDED.value
            await session.flush()
        row.status = S.APPROVED.value
        row.approved_by_user_id = user_id
        row.approved_by_name = body.name
        row.approved_at = now
    else:
        row.status = S.REJECTED.value
    row.decision_note = body.note
    row.updated_by = user_id
    await session.flush()
    await _event(session, row, user_id, f"acceptance_expected.{row.status}")
    await session.refresh(row)
    return AcceptanceExpectedOut.model_validate(row)


async def record_result(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    expected_id: uuid.UUID,
    body: AcceptanceResultIn,
) -> AcceptanceResultOut:
    row = await _get(session, expected_id)
    if row.status != S.APPROVED.value:
        raise ProblemError(ErrorCodes.ACCEPT_STATE)
    result = AcceptanceResult(
        tenant_id=tenant_id,
        expected_id=row.id,
        outcome=body.outcome.value,
        software_version=body.software_version,
        commit_ref=body.commit_ref,
        actual=body.actual,
        note=body.note,
        decided_by_user_id=user_id,
        decided_by_name=body.name,
    )
    session.add(result)
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="acceptance_result.recorded",
        entity_type="acceptance_result",
        entity_id=result.id,
        actor_user_id=user_id,
        payload={"case_id": row.case_id, "version": row.version, "outcome": result.outcome},
    )
    await session.refresh(result)
    return AcceptanceResultOut.model_validate(result)


async def _event(
    session: AsyncSession, row: AcceptanceExpected, user_id: uuid.UUID, type_: str
) -> None:
    await emit(
        session,
        tenant_id=row.tenant_id,
        type=type_,
        entity_type="acceptance_expected",
        entity_id=row.id,
        actor_user_id=user_id,
        payload={"case_id": row.case_id, "version": row.version, "status": row.status},
    )


def _cell(value: str | None) -> str:
    return (value or "").replace("|", "/").replace("\n", " ")


def _fmt_date(value: datetime | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


async def export_markdown(session: AsyncSession) -> str:
    """Acceptance protocol as markdown (same columns as docs/acceptance/abnahme-anhang-d.md
    plus source and release of the expected value)."""
    state = await list_cases(session)
    lines = [
        "# Abnahmeprotokoll Anhang D (Export aus dem Abnahmeregister)",
        "",
        f"Stand: {datetime.now(UTC).strftime('%d.%m.%Y')}. {NOTE_V16}",
        "Ein Sollwert darf nicht nachträglich an das Ist-Ergebnis angepasst werden (D.3).",
        "",
        f"Fälle: {state.cases_total}, freigegebene Sollwerte: {state.released_total}, "
        f"abgenommen: {state.passed_total}.",
        "",
        "| Kennung | Bezeichnung | Fassung | Quelle | Sollwert freigegeben durch | Datum "
        "| Ergebnis | Version | Abgenommen durch | Datum |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    outcome_de = {"passed": "bestanden", "failed": "nicht bestanden"}
    for item in state.items:
        rel = item.released
        res = item.last_result
        lines.append(
            "| "
            + " | ".join(
                [
                    item.case_id,
                    _cell(rel.title if rel else (item.current.title if item.current else "")),
                    str(rel.version) if rel else "",
                    _cell(rel.source if rel else ""),
                    _cell(rel.approved_by_name if rel else ""),
                    _fmt_date(rel.approved_at if rel else None),
                    outcome_de.get(res.outcome, "") if res else "",
                    _cell(res.software_version if res else ""),
                    _cell(res.decided_by_name if res else ""),
                    _fmt_date(res.decided_at if res else None),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"
