"""HOA statement package (W12): everything a resolution and a board review need, with the
blocking checks that stop the internal approval (missing units, ownership gaps, cost items
without an account reference, partial scope without a documented basis, unresolved bank
transactions of the year)."""

import uuid
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing.status import RESOLUTION_STATUSES_FOR_POSTING
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import (
    AuditEngagement,
    AuditReport,
    EconomicPlan,
    HoaCostItem,
    HoaStatement,
    Resolution,
)

router = APIRouter(prefix="/hoa", tags=["hoa"])
NOTE = "Information zur Beschlussvorlage; Rückstände bleiben eigene Forderungen."


def _key(k: Any) -> dict[str, str] | None:
    return {"code": k.code, "name": k.name} if k is not None else None


READ = require_permission("accounting:read")
# W03 / D18: a cost item that reaches only part of the community (sub community, entrance, user
# group) needs a documented basis. The basis text must name its source; a free filter is none.
# Product protection: term check on the free text until a structured source link exists (A18).
SCOPE_SOURCE_TERMS = ("beschluss", "teilungserklärung", "gemeinschaftsordnung")
# D54: validity state of a resolution and the follow up steps are shown apart (assessment for
# the reviewer, no legal statement); the software never derives a deletion or reversal from
# the status, and the result is posted only with a binding status.
RESOLUTION_VALIDITY: dict[str, tuple[str, str]] = {
    "positive": ("gefasst, Anfechtungsfrist läuft", "Anfechtungsfrist beobachten."),
    "final": ("bestandskräftig", "Keine."),
    "legally_binding": ("bestandskräftig", "Keine."),
    "contested": (
        "angefochten, Wirksamkeit gerichtlich zu klären",
        "Verfahren verfolgen; Ergebnisbuchung bis zur Bestandskraft gesperrt; bereits "
        "gebuchte Ergebnisse bleiben bestehen, keine automatische Stornierung.",
    ),
    "annulled": (
        "aufgehoben",
        "Aufhebung prüfen; erforderliche Stornierungen nur als eigener, belegter Buchungsschritt.",
    ),
    "void": ("nichtig", "Nichtigkeit prüfen; keine automatische Ausbuchung."),
    "negative": ("abgelehnt", "Keine."),
}


def resolution_validity(status: str) -> dict[str, Any]:
    state, follow_up = RESOLUTION_VALIDITY.get(status, ("unbekannt", "Status prüfen."))
    return {
        "status": status,
        "state": state,
        "posting_allowed": status in RESOLUTION_STATUSES_FOR_POSTING,
        "follow_up": follow_up,
    }


def has_documented_basis(basis: str) -> bool:
    text = basis.lower()
    return any(term in text for term in SCOPE_SOURCE_TERMS)


async def blocking_checks(session: AsyncSession, st: HoaStatement) -> list[dict[str, str]]:
    """Findings that block the internal approval of the statement (W12)."""
    from mhvp.accounting.models import Ledger
    from mhvp.banking.models import BankTransaction, TransactionStatus
    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.properties.models import Unit, UnitAllocationValue

    findings: list[dict[str, str]] = []
    ledger = await session.get(Ledger, st.ledger_id)
    if ledger is None or ledger.property_id is None:
        return [{"code": "ledger", "detail": "Buchungskreis ohne Objekt."}]
    start, end = date(st.year, 1, 1), date(st.year, 12, 31)
    units = (
        await session.scalars(
            select(Unit)
            .where(Unit.property_id == ledger.property_id, Unit.is_fictional.is_(False))
            .order_by(Unit.number)
        )
    ).all()
    in_snapshot = {u["unit_id"] for u in (st.snapshot or {}).get("units", [])}
    for unit in units:
        if st.snapshot is not None and str(unit.id) not in in_snapshot:
            findings.append(
                {
                    "code": "missing_unit",
                    "detail": f"Einheit {unit.number} fehlt in der Abrechnung.",
                }
            )
        periods = sorted(
            (c.start_date, c.end_date or end)
            for c in (
                await session.scalars(
                    select(Contract).where(
                        Contract.unit_id == unit.id,
                        Contract.kind == ContractKind.OWNERSHIP,
                        Contract.start_date <= end,
                        or_(Contract.end_date.is_(None), Contract.end_date >= start),
                    )
                )
            ).all()
        )
        cursor = start
        for s, e in periods:
            if s > cursor:
                findings.append(
                    {
                        "code": "owner_gap",
                        "detail": f"Einheit {unit.number}: kein Eigentümer ab {cursor:%d.%m.%Y}.",
                    }
                )
            if s < cursor and cursor != start:
                findings.append(
                    {"code": "owner_overlap", "detail": f"Einheit {unit.number}: Überschneidung."}
                )
            cursor = max(cursor, e + timedelta(days=1))
        if cursor <= end:
            findings.append(
                {
                    "code": "owner_gap",
                    "detail": f"Einheit {unit.number}: kein Eigentümer ab {cursor:%d.%m.%Y}.",
                }
            )
    items = (
        await session.scalars(select(HoaCostItem).where(HoaCostItem.statement_id == st.id))
    ).all()
    all_units = {u.id for u in units}
    for item in items:
        if item.account_id is None:
            findings.append(
                {
                    "code": "no_account",
                    "detail": f"{item.label}: kein Kontenbezug, Beleg nicht verknüpft.",
                }
            )
        covered = set(
            (
                await session.scalars(
                    select(UnitAllocationValue.unit_id).where(
                        UnitAllocationValue.allocation_key_id == item.allocation_key_id,
                        UnitAllocationValue.unit_id.in_(all_units or [uuid.uuid4()]),
                        UnitAllocationValue.valid_from <= end,
                        or_(
                            UnitAllocationValue.valid_to.is_(None),
                            UnitAllocationValue.valid_to >= start,
                        ),
                    )
                )
            ).all()
        )
        if covered and covered < all_units and not has_documented_basis(item.basis):
            findings.append(
                {
                    "code": "scope_unfounded",
                    "detail": (
                        f"{item.label}: Verteilung auf {len(covered)} von {len(all_units)} "
                        "Einheiten ohne belegte Grundlage (Beschluss oder Teilungserklärung "
                        "als Quelle nennen); ein Filter schafft keine Beschlusskompetenz (W03)."
                    ),
                }
            )
    open_tx = (
        await session.scalars(
            select(BankTransaction.id).where(
                BankTransaction.legal_entity_id == ledger.legal_entity_id,
                BankTransaction.booking_date.between(start, end),
                BankTransaction.status.in_(
                    [
                        TransactionStatus.NEW,
                        TransactionStatus.NEEDS_REVIEW,
                        TransactionStatus.PROPOSED,
                    ]
                ),
            )
        )
    ).all()
    if open_tx:
        findings.append(
            {
                "code": "open_bank",
                "detail": f"{len(open_tx)} ungeklärte Bankumsätze im Abrechnungsjahr.",
            }
        )
    return findings


@router.get("/statements/{statement_id}/package", summary="Abrechnungspaket (W12)")
async def statement_package(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from mhvp.properties.models import AllocationKey

    async with tenant_tx(request, principal) as session:
        st = await session.get(HoaStatement, statement_id)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        items = (
            await session.scalars(select(HoaCostItem).where(HoaCostItem.statement_id == st.id))
        ).all()
        keys = {
            k.id: k
            for k in (
                await session.scalars(
                    select(AllocationKey).where(
                        AllocationKey.id.in_([i.allocation_key_id for i in items] or [uuid.uuid4()])
                    )
                )
            ).all()
        }
        resolution = await session.get(Resolution, st.resolution_id) if st.resolution_id else None
        plan = await session.scalar(
            select(EconomicPlan)
            .where(
                EconomicPlan.ledger_id == st.ledger_id,
                EconomicPlan.year == st.year,
                EconomicPlan.resolution_id.is_not(None),
            )
            .order_by(EconomicPlan.version.desc())
        )
        reports = []
        for eng in (
            await session.scalars(
                select(AuditEngagement).where(AuditEngagement.statement_id == st.id)
            )
        ).all():
            latest = await session.scalar(
                select(AuditReport)
                .where(AuditReport.engagement_id == eng.id)
                .order_by(AuditReport.version.desc())
            )
            if latest:
                reports.append(
                    {"engagement_id": eng.id, "version": latest.version, **latest.content}
                )
        findings = await blocking_checks(session, st)
        positions = {p["label"]: p for p in (st.snapshot or {}).get("positions", [])}
        return {
            "statement": {
                "id": st.id,
                "year": st.year,
                "version": st.version,
                "status": st.status.value,
                "snapshot_hash": st.snapshot_hash,
            },
            "cost_items": [
                {
                    "label": i.label,
                    "amount": str(i.amount),
                    "basis": i.basis,
                    "key": {
                        "code": keys[i.allocation_key_id].code,
                        "name": keys[i.allocation_key_id].name,
                    }
                    if i.allocation_key_id in keys
                    else None,
                    "account_id": i.account_id,
                    "split": positions.get(i.label, {}).get("split"),
                }
                for i in items
            ],
            "units": (st.snapshot or {}).get("units", []),
            "reserve": (st.snapshot or {}).get("reserve"),
            "asset_report": (st.snapshot or {}).get("asset_report"),
            "plan": {"id": plan.id, "version": plan.version, "resolution_id": plan.resolution_id}
            if plan
            else None,
            "resolution": {
                "id": resolution.id,
                "number": resolution.number,
                "decided_on": resolution.decided_on,
                "status": resolution.status,
                "wording": resolution.wording,
                "validity": resolution_validity(resolution.status),
            }
            if resolution
            else None,
            "audit_reports": reports,
            "blocking": findings,
            "releasable": not findings and st.snapshot is not None,
            "note": NOTE,
        }
