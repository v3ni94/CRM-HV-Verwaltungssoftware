"""Reserve statement per GdWE and year (6.9.3, E03, 7.8 W08, S69-01).

An own statement object with the shared status model. Its content is derived from the reserve
data of the calculated Hausgeldabrechnung of the same year (reserve block and the positions per
earmarked reserve, M24-01); it never computes reserve figures of its own and posts nothing.
Rights: accounting:read, accounting:create, accounting:approve; RLS through ``tenant_tx``;
issued, due and posted need release gate G4 (WEG statements, 18.0).
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Index, Integer, String, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.accounting.models import Ledger
from mhvp.billing import statement_lifecycle as lifecycle
from mhvp.billing.status import (
    RESOLUTION_STATUSES_FOR_POSTING,
    StatementStatus,
    TransitionError,
    check_transition,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_column_guard, session_allowed_property_ids
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.hoa.models import HoaStatement, Resolution, _fk, _status

RULE_VERSION = "W08-reserve-statement-v1"


class ReserveStatement(IdMixin, TimestampMixin, TenantMixin, Base):
    """Rücklagenabrechnung of one GdWE ledger and year (S69-01, migration 0295)."""

    __tablename__ = "reserve_statement"
    __table_args__ = (
        Index("ix_reserve_statement_ledger", "tenant_id", "ledger_id", "year"),
        Index("ix_reserve_statement_hoa_statement_id", "hoa_statement_id"),
    )

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", nullable=False)
    hoa_statement_id: Mapped[uuid.UUID] = _fk("hoa_statement.id", nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[StatementStatus] = _status()
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False, default=RULE_VERSION)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    # Hash of the Hausgeldabrechnung snapshot the reserve data was taken from.
    source_snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    calculated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resolution_id: Mapped[uuid.UUID | None] = _fk("resolution.id")
    posted_entry_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    status_log: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )


def digest(snapshot: dict[str, Any]) -> str:
    raw = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def reserve_master(reserves: list[Any]) -> list[dict[str, Any]]:
    """Master data per earmarked reserve (M24-01 wave 5, migration 0294): entered opening
    balance, its year and the bank account of the investment; shown, never recomputed."""
    return [
        {
            "reserve_id": str(r.id),
            "name": r.name,
            "active": bool(r.active),
            "opening_balance": str(getattr(r, "opening_balance", None) or "0.00"),
            "opening_year": getattr(r, "opening_year", None),
            "bank_account_id": str(r.bank_account_id)
            if getattr(r, "bank_account_id", None)
            else None,
        }
        for r in reserves
    ]


def build_snapshot(hoa: HoaStatement, reserves: list[Any] | None = None) -> dict[str, Any]:
    """Pure: the reserve part of the calculated Hausgeldabrechnung (W08)."""
    snap = hoa.snapshot or {}
    reserve = dict(snap.get("reserve") or {})
    positions = reserve.pop("positions", [])
    return {
        "rule_version": RULE_VERSION,
        "year": hoa.year,
        "hoa_statement_id": str(hoa.id),
        "hoa_statement_version": hoa.version,
        "source_snapshot_hash": hoa.snapshot_hash,
        "reserve": reserve,
        "positions": positions,
        "per_position_reserve": reserve_master(reserves or []),
    }


router = APIRouter(
    prefix="/hoa/reserve-statements",
    tags=["WEG"],
    dependencies=[
        Depends(
            property_column_guard(
                {
                    "reserve_statement_id": ReserveStatement.ledger_id,
                    "ledger_id": Ledger.property_id,
                }
            )
        )
    ],
)
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")


class HoaReserveStatementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hoa_statement_id: uuid.UUID


class HoaReserveStatementTransitionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: StatementStatus
    resolution_id: uuid.UUID | None = None
    entry_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


def _out(st: ReserveStatement) -> dict[str, Any]:
    return {
        "id": st.id,
        "ledger_id": st.ledger_id,
        "hoa_statement_id": st.hoa_statement_id,
        "year": st.year,
        "status": st.status.value,
        "rule_version": st.rule_version,
        "snapshot": st.snapshot,
        "snapshot_hash": st.snapshot_hash,
        "source_snapshot_hash": st.source_snapshot_hash,
        "calculated_at": st.calculated_at,
        "approved_at": st.approved_at,
        "approved_by": st.approved_by,
        "resolution_id": st.resolution_id,
        "posted_entry_ids": list(st.posted_entry_ids or []),
        "status_log": list(st.status_log or []),
        "created_by": st.created_by,
    }


async def _get(session: AsyncSession, statement_id: uuid.UUID) -> ReserveStatement:
    row = await session.get(ReserveStatement, statement_id, with_for_update=True)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def _hoa(session: AsyncSession, hoa_statement_id: uuid.UUID) -> HoaStatement:
    from mhvp.core.auth.scope import ensure_session_property_allowed

    hoa = await session.get(HoaStatement, hoa_statement_id)
    ledger = await session.get(Ledger, hoa.ledger_id) if hoa else None
    if hoa is None or ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if ledger.property_id is not None:
        ensure_session_property_allowed(session, ledger.property_id)
    return hoa


@router.post("", status_code=201, summary="Rücklagenabrechnung anlegen (Entwurf)")
async def create(
    body: HoaReserveStatementIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        hoa = await _hoa(session, body.hoa_statement_id)
        st = ReserveStatement(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            ledger_id=hoa.ledger_id,
            hoa_statement_id=hoa.id,
            year=hoa.year,
        )
        session.add(st)
        await session.flush()
        return _out(st)


@router.get("", summary="Rücklagenabrechnungen")
async def list_statements(
    request: Request,
    ledger_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(ReserveStatement).order_by(
            ReserveStatement.year.desc(), ReserveStatement.created_at.desc()
        )
        if ledger_id is not None:
            query = query.where(ReserveStatement.ledger_id == ledger_id)
        allowed = session_allowed_property_ids(session)
        if allowed is not None:
            query = query.join(Ledger, Ledger.id == ReserveStatement.ledger_id).where(
                Ledger.property_id.in_(allowed)
            )
        return [_out(r) for r in (await session.scalars(query.limit(200))).all()]


@router.get("/{reserve_statement_id}", summary="Rücklagenabrechnung")
async def get(
    reserve_statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return _out(await _get(session, reserve_statement_id))


@router.post(
    "/{reserve_statement_id}/calculate",
    summary="Aus den Rücklagendaten der Hausgeldabrechnung erzeugen",
)
async def calculate(
    reserve_statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _get(session, reserve_statement_id)
        if st.status not in lifecycle.RECALCULABLE:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Nach der internen Freigabe wird nicht neu berechnet; neue Abrechnung "
                "anlegen.",
            )
        hoa = await _hoa(session, st.hoa_statement_id)
        if hoa.snapshot is None or hoa.snapshot_hash is None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Hausgeldabrechnung ist noch nicht berechnet."
            )
        from mhvp.hoa.models import HoaReserve

        reserves = list(
            (
                await session.scalars(
                    select(HoaReserve)
                    .where(HoaReserve.ledger_id == st.ledger_id)
                    .order_by(HoaReserve.name)
                )
            ).all()
        )
        snapshot = build_snapshot(hoa, reserves)
        st.snapshot = snapshot
        st.snapshot_hash = digest(snapshot)
        st.source_snapshot_hash = hoa.snapshot_hash
        st.rule_version = RULE_VERSION
        st.calculated_at = datetime.now(tz=UTC)
        st.calculated_by = principal.user_id
        if st.status is StatementStatus.DRAFT:
            st.status_log = [
                *(st.status_log or []),
                lifecycle.log_entry(st.status, StatementStatus.CALCULATED, principal.user_id, None),
            ]
        st.status = StatementStatus.CALCULATED
        st.updated_by = principal.user_id
        await session.flush()
        return _out(st)


@router.post("/{reserve_statement_id}/transition", summary="Statuswechsel (6.9.3, S69-01)")
async def transition(
    reserve_statement_id: uuid.UUID,
    body: HoaReserveStatementTransitionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    """Same rules as the Hausgeldabrechnung: four eyes on the internal approval, resolved only
    with a binding resolution on this or the source snapshot (D14), issued only after resolved
    (W06), posted only from due with a binding resolution (D13) and posted entries of the
    ledger. issued, due and posted need release gate G4."""
    target = body.target
    if target in lifecycle.GATED_TARGETS:
        await ensure_release_gate_open(
            ReleaseGate.G4, principal.tenant_id, request.app.state.release_gate_resolver
        )
    if target in (StatementStatus.DRAFT, StatementStatus.CALCULATED):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Berechnung über den Berechnungsendpunkt.")
    if target is not StatementStatus.POSTED and body.entry_ids:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Buchungen nur beim Status gebucht.")
    async with tenant_tx(request, principal) as session:
        st = await _get(session, reserve_statement_id)
        current = st.status
        resolution_id = body.resolution_id if target is StatementStatus.RESOLVED else None
        if target is StatementStatus.POSTED:
            resolution_id = st.resolution_id
        resolution = await session.get(Resolution, resolution_id) if resolution_id else None
        if target is StatementStatus.RESOLVED:
            if resolution is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Beschluss fehlt (W06).")
            if resolution.status not in RESOLUTION_STATUSES_FOR_POSTING:
                raise ProblemError(
                    ErrorCodes.CONFLICT, detail="Beschluss ist nicht positiv gefasst."
                )
        matches = bool(
            resolution
            and resolution.snapshot_hash
            and resolution.snapshot_hash in {st.snapshot_hash, st.source_snapshot_hash}
        )
        try:
            check_transition(
                current,
                target,
                is_hoa=True,
                resolution_status=resolution.status if resolution is not None else None,
                resolution_snapshot_matches=matches,
            )
        except TransitionError as exc:
            raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from None
        if target is StatementStatus.INTERNALLY_APPROVED:
            if lifecycle.four_eyes_violated(principal.user_id, st.created_by, st.calculated_by):
                raise ProblemError(
                    ErrorCodes.GATE_FOUR_EYES,
                    detail="Die interne Freigabe muss eine andere Person erteilen.",
                )
            hoa = await session.get(HoaStatement, st.hoa_statement_id)
            if hoa is None or hoa.snapshot_hash != st.source_snapshot_hash:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail="Hausgeldabrechnung wurde neu berechnet; Rücklagenabrechnung neu "
                    "erzeugen.",
                )
            st.approved_at = datetime.now(tz=UTC)
            st.approved_by = principal.user_id
        if target is StatementStatus.RESOLVED and resolution is not None:
            st.resolution_id = resolution.id
        if target is StatementStatus.POSTED:
            entries = await lifecycle.posted_entries_of_ledger(
                session, st.ledger_id, body.entry_ids
            )
            if entries is None:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail="Gebucht nur mit gebuchten Buchungen dieses Buchungskreises.",
                )
            st.posted_entry_ids = entries
        st.status_log = [
            *(st.status_log or []),
            lifecycle.log_entry(current, target, principal.user_id, body.note),
        ]
        st.status = target
        st.updated_by = principal.user_id
        await session.flush()
        return _out(st)
