"""Special acquisitions in the statement year as a release step (GA07-03, 7.8 W07 sentence 5 to 7).

An ownership contract that starts (or whose title transfer falls) in the statement year and was
acquired other than by purchase (first acquisition, inheritance, forced sale, gift, other) or
carries a special succession liability flag needs a documented release before the statement
package can be approved: a first person requests, a second person releases (four eyes).

The allocation of the statement result per acquisition kind is only a proposal text. The
software applies no legal rule: who owes the result, advance arrears or special levies in these
cases is open (docs/OPEN_QUESTIONS.md AA07-01, gate G4) and stays with legal advice.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import HoaAcquisitionRelease, HoaStatement
from mhvp.hoa.property_scope import HOA_GUARD

router = APIRouter(prefix="/hoa", tags=["hoa"], dependencies=[Depends(HOA_GUARD)])
READ = require_permission("accounting:read")
REQUEST = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")

# Kinds that need the release; purchase and missing information do not (the regular case).
SPECIAL_KINDS = ("first_acquisition", "inheritance", "foreclosure", "gift", "other")
# German labels of the special cases (GA07-03): shown in findings and in the CRM list.
KIND_LABELS: dict[str, str] = {
    "first_acquisition": "Ersterwerb",
    "inheritance": "Erbfall",
    "foreclosure": "Zwangsversteigerung",
    "gift": "Schenkung",
    "other": "Sonstiger Erwerb",
}
SUCCESSION_LABEL = "Sonderrechtsnachfolge"
PROPOSAL_NOTE = (
    "Vorschlag zur fachlichen Prüfung, keine Rechtsregel. Maßgeblich sind Beschluss, "
    "Gemeinschaftsordnung und Rechtslage; im Zweifel Rechtsanwalt einbeziehen."
)
# Proposal texts per acquisition kind. They state the standing assumption (M24-01) and name what
# must be checked; none of them decides a liability.
PROPOSALS: dict[str, str] = {
    "first_acquisition": (
        "Ersterwerb: Zuordnung des Abrechnungsergebnisses nach der Annahme M24-01 (Eigentümer "
        "zum Beschlussdatum). Prüfen, ob Bauträger oder Ersterwerber für Zeiträume vor dem "
        "Übergang abweichend belastet werden."
    ),
    "inheritance": (
        "Erbfall: Zuordnung nach der Annahme M24-01 (Eigentümer zum Beschlussdatum). Prüfen, "
        "wer für Rückstände des Erblassers einzustehen hat und ab wann der Erbe als Eigentümer "
        "gilt (Erbschein, Grundbuch)."
    ),
    "foreclosure": (
        "Zwangsversteigerung: Zuordnung nach der Annahme M24-01 (Eigentümer zum Beschlussdatum). "
        "Prüfen, welche Rückstände beim bisherigen Eigentümer verbleiben und ob Forderungen "
        "anzumelden sind (Zuschlagsbeschluss, Verteilungstermin)."
    ),
    "gift": (
        "Schenkung: Zuordnung nach der Annahme M24-01 (Eigentümer zum Beschlussdatum). Prüfen, "
        "ob Vereinbarungen zwischen Schenker und Beschenktem die Zuordnung abweichend regeln."
    ),
    "other": (
        "Sonstiger Erwerb: Zuordnung nach der Annahme M24-01 (Eigentümer zum Beschlussdatum). "
        "Erwerbsgrund und abweichende Regelungen im Einzelfall prüfen."
    ),
}
SUCCESSION_PROPOSAL = (
    "Sondernachfolgehaftung gekennzeichnet: Rückstände bleiben nach der Annahme M24-01 beim "
    "ursprünglichen Schuldner; ob und in welchem Umfang der Erwerber haftet, ist fachlich und "
    "rechtlich zu prüfen."
)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AcquisitionRequestIn(_In):
    note: str | None = Field(default=None, max_length=2000)


class AcquisitionReleaseIn(_In):
    note: str = Field(min_length=3, max_length=2000)


def proposal_for(kind: str | None, succession: bool) -> str:
    parts = [PROPOSALS[kind]] if kind in PROPOSALS else []
    if succession:
        parts.append(SUCCESSION_PROPOSAL)
    return " ".join(parts)


def label_for(kind: str | None, succession: bool) -> str:
    parts = [KIND_LABELS[kind]] if kind in KIND_LABELS else []
    if succession:
        parts.append(SUCCESSION_LABEL)
    return ", ".join(parts) or "Sonderfall"


async def special_contracts(session: AsyncSession, st: HoaStatement) -> list[Any]:
    """Ownership contracts of the statement year with a special acquisition (see module doc)."""
    from mhvp.accounting.models import Ledger
    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.properties.models import Unit

    ledger = await session.get(Ledger, st.ledger_id)
    if ledger is None or ledger.property_id is None:
        return []
    start, end = date(st.year, 1, 1), date(st.year, 12, 31)
    in_year = or_(
        Contract.start_date.between(start, end),
        Contract.title_transfer_date.between(start, end),
    )
    rows = await session.execute(
        select(Contract, Unit.number)
        .join(Unit, Unit.id == Contract.unit_id)
        .where(
            Unit.property_id == ledger.property_id,
            Contract.kind == ContractKind.OWNERSHIP,
            Contract.start_date <= end,
            in_year,
            or_(
                Contract.acquisition_kind.in_(SPECIAL_KINDS),
                Contract.special_succession_liability.is_(True),
            ),
        )
        .order_by(Unit.number, Contract.start_date)
    )
    return [(c, number) for c, number in rows.all()]


async def _releases(session: AsyncSession, statement_id: uuid.UUID) -> dict[uuid.UUID, Any]:
    rows = await session.scalars(
        select(HoaAcquisitionRelease).where(HoaAcquisitionRelease.statement_id == statement_id)
    )
    return {r.contract_id: r for r in rows.all()}


def _item(
    contract: Any, number: str, release: Any, variant: str = "manual_release"
) -> dict[str, Any]:
    kind = contract.acquisition_kind.value if contract.acquisition_kind else None
    status = "open"
    if release is not None:
        status = "released" if release.released_at is not None else "requested"
    return {
        "contract_id": contract.id,
        "contract_number": contract.number,
        "unit_number": number,
        "acquisition_kind": kind,
        "case_label": label_for(kind, contract.special_succession_liability),
        "special_succession_liability": contract.special_succession_liability,
        "start_date": contract.start_date,
        "title_transfer_date": contract.title_transfer_date,
        "allocation_proposal": proposal_for(kind, contract.special_succession_liability),
        "status": status,
        "allocation_variant": variant,
        "requested_by": release.requested_by if release else None,
        "requested_at": release.requested_at if release else None,
        "released_by": release.released_by if release else None,
        "released_at": release.released_at if release else None,
        "release_note": release.release_note if release else None,
    }


async def blocking_findings(session: AsyncSession, st: HoaStatement) -> list[dict[str, str]]:
    """Package findings: one per special acquisition without a completed release."""
    special = await special_contracts(session, st)
    if not special:
        return []
    releases = await _releases(session, st.id)
    findings: list[dict[str, str]] = []
    for contract, number in special:
        release = releases.get(contract.id)
        if release is not None and release.released_at is not None:
            continue
        kind = label_for(
            contract.acquisition_kind.value if contract.acquisition_kind else None,
            contract.special_succession_liability,
        )
        step = "zweite Person muss freigeben" if release else "Freigabe beantragen"
        findings.append(
            {
                "code": "acquisition_unreleased",
                "detail": (
                    f"Einheit {number}: Erwerbsart {kind} im Abrechnungsjahr, {step} "
                    "(Eigentümerwechsel, Sonderfall W07)."
                ),
            }
        )
    return findings


async def _statement(session: AsyncSession, statement_id: uuid.UUID) -> HoaStatement:
    st = await session.get(HoaStatement, statement_id)
    if st is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return st


@router.get("/statements/{statement_id}/acquisitions", summary="Sondererwerbe der Abrechnung (W07)")
async def list_acquisitions(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        releases = await _releases(session, st.id)
        from mhvp.hoa.acquisition_rule import resolve_variant

        items = []
        for c, n in await special_contracts(session, st):
            kind = c.acquisition_kind.value if c.acquisition_kind else None
            items.append(_item(c, n, releases.get(c.id), await resolve_variant(session, kind)))
        return {"items": items, "note": PROPOSAL_NOTE}


@router.post(
    "/statements/{statement_id}/acquisitions/{contract_id}/request",
    status_code=201,
    summary="Freigabe eines Sondererwerbs beantragen (erste Person)",
)
async def request_release(
    statement_id: uuid.UUID,
    contract_id: uuid.UUID,
    body: AcquisitionRequestIn,
    request: Request,
    principal: TenantPrincipal = Depends(REQUEST),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        match = next(
            ((c, n) for c, n in await special_contracts(session, st) if c.id == contract_id), None
        )
        if match is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        contract, number = match
        existing = (await _releases(session, st.id)).get(contract_id)
        if existing is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Freigabe bereits beantragt.")
        kind = contract.acquisition_kind.value if contract.acquisition_kind else None
        row = HoaAcquisitionRelease(
            tenant_id=principal.tenant_id,
            statement_id=st.id,
            contract_id=contract.id,
            acquisition_kind=kind,
            special_succession_liability=contract.special_succession_liability,
            allocation_proposal=proposal_for(kind, contract.special_succession_liability),
            requested_by=principal.user_id,
            requested_at=datetime.now(UTC),
            request_note=body.note,
            created_by=principal.user_id,
            updated_by=principal.user_id,
        )
        session.add(row)
        await session.flush()
        return _item(contract, number, row)


@router.post(
    "/statements/{statement_id}/acquisitions/{contract_id}/release",
    summary="Sondererwerb freigeben (zweite Person)",
)
async def release(
    statement_id: uuid.UUID,
    contract_id: uuid.UUID,
    body: AcquisitionReleaseIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        match = next(
            ((c, n) for c, n in await special_contracts(session, st) if c.id == contract_id), None
        )
        row = (await _releases(session, st.id)).get(contract_id)
        if match is None or row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.released_at is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Bereits freigegeben.")
        if row.requested_by == principal.user_id:
            raise ProblemError(ErrorCodes.HOA_ACQUISITION_FOUR_EYES)
        row.released_by, row.released_at = principal.user_id, datetime.now(UTC)
        row.release_note, row.updated_by = body.note, principal.user_id
        await session.flush()
        return _item(match[0], match[1], row)
