"""Owner portal additions, read only (A.5 Eigentümeransicht, M21-06, M21-07, SA-05).

* ``/portal/owner/tickets``: tickets of the own properties that the management released for
  owners (``visible_for`` contains ``owner``); a ticket of a tenant is never listed otherwise.
* ``/portal/owner/payment-resolutions``: announced resolutions on a economic plan or special
  levy of the own community with validity, due rhythm and the community's default account for
  payments (SEPA information: the payee is the GdWE, never a private account). Information
  only: no payment is initiated; ``own_share`` shows the own amounts taken from the calculated
  snapshot of the plan or levy (never recomputed here, never other owners' units).
* ``/portal/owner/consumption-info``: monthly consumption information for own units under the
  owner's own ownership contract (self use). Months of a tenancy are tenants' data and stay
  hidden. Locked by the same tenant switches as the tenant view (rule H03).

Scope comes from the active owner grants only (``mhvp.portal.owner``), RLS applies through
``tenant_tx``; tenants, providers and staff accounts get 403."""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select

from mhvp.core.auth.principal import tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.portal.owner import _owner_scope
from mhvp.portal.routers import Portal, portal_user
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal/owner", tags=["Portal"])
PAYMENT_NOTE = (
    "Information zu beschlossenen Zahlungen der Gemeinschaft. Maßgeblich sind Beschluss, "
    "Wirtschaftsplan und Ihre individuelle Sollstellung. Es wird keine Zahlung ausgelöst."
)
PAYMENT_SUBJECTS = ("economic_plan", "special_levy")
ANNOUNCED = ("positive", "final", "legally_binding")


async def _own_properties(session: Any, ownership: set[uuid.UUID]) -> set[uuid.UUID]:
    from mhvp.contracts.models import Contract

    if not ownership:
        return set()
    return set(
        await session.scalars(select(Contract.property_id).where(Contract.id.in_(ownership)))
    )


@router.get("/tickets", summary="Meldungen zu den eigenen Objekten (für Eigentümer freigegeben)")
async def owner_tickets(
    request: Request, ctx: Portal = Depends(portal_user)
) -> list[dict[str, Any]]:
    from mhvp.tickets.models import Ticket

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        _, ownership = await _owner_scope(session, account, local_today())
        property_ids = await _own_properties(session, ownership)
        if not property_ids:
            return []
        rows = (
            await session.scalars(
                select(Ticket)
                .where(
                    Ticket.property_id.in_(property_ids),
                    Ticket.visible_for.contains(["owner"]),
                )
                .order_by(Ticket.number.desc())
                .limit(200)
            )
        ).all()
        return [
            {
                "id": t.id,
                "number": t.number,
                "title": t.title,
                "status": t.status.value,
                "property_id": t.property_id,
                "created_at": t.created_at,
            }
            for t in rows
        ]


async def _sepa(session: Any, legal_entity_id: uuid.UUID, today: date) -> dict[str, Any] | None:
    from mhvp.properties.models import PropertyBankAccount

    account = await session.scalar(
        select(PropertyBankAccount)
        .where(
            PropertyBankAccount.legal_entity_id == legal_entity_id,
            PropertyBankAccount.valid_from <= today,
            or_(PropertyBankAccount.valid_to.is_(None), PropertyBankAccount.valid_to >= today),
        )
        .order_by(PropertyBankAccount.is_default.desc(), PropertyBankAccount.created_at)
        .limit(1)
    )
    if account is None:
        return None
    return {
        "holder": account.holder,
        "iban": account.iban,
        "bic": account.bic,
        "bank_name": account.bank_name,
    }


async def _own_unit_ids(session: Any, ownership: set[uuid.UUID]) -> list[uuid.UUID]:
    from mhvp.contracts.models import Contract

    if not ownership:
        return []
    rows = await session.scalars(select(Contract.unit_id).where(Contract.id.in_(ownership)))
    return [u for u in rows if u is not None]


def _own_plan_share(snapshot: dict[str, Any] | None, own: set[str]) -> list[dict[str, Any]] | None:
    """Own annual and monthly amounts from the calculated plan (M21-06, SA-05); None while the
    plan has no calculation. Other owners' units never appear."""
    if not snapshot:
        return None
    return [
        {"unit_number": u["unit_number"], "annual": u["annual"], "monthly": u["monthly"]}
        for u in snapshot.get("units", [])
        if u["unit_id"] in own
    ]


def _own_levy_share(snapshot: dict[str, Any] | None, own: set[str]) -> list[dict[str, Any]] | None:
    """Own amount of the special levy from its calculation; None while not calculated."""
    if not snapshot:
        return None
    return [
        {
            "unit_number": u["unit_number"],
            "amount": u["amount"],
            "instalments": u.get("instalments"),
        }
        for u in snapshot.get("units", [])
        if u["unit_id"] in own
    ]


@router.get("/payment-resolutions", summary="Beschlossene Zahlungen der Gemeinschaft")
async def payment_resolutions(
    request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    from mhvp.hoa.models import EconomicPlan, Resolution, SpecialLevy
    from mhvp.properties.models import LegalEntity

    principal, account = ctx
    today = local_today()
    async with tenant_tx(request, principal) as session:
        hoa_ids, ownership = await _owner_scope(session, account, today)
        own_units = {str(u) for u in await _own_unit_ids(session, ownership)}
        name_rows = await session.execute(
            select(LegalEntity.id, LegalEntity.name).where(LegalEntity.id.in_(hoa_ids))
        )
        names: dict[uuid.UUID, str] = {r[0]: r[1] for r in name_rows.all()}
        resolutions = (
            await session.scalars(
                select(Resolution)
                .where(
                    Resolution.legal_entity_id.in_(hoa_ids),
                    Resolution.subject_type.in_(PAYMENT_SUBJECTS),
                    Resolution.status.in_(ANNOUNCED),
                )
                .order_by(Resolution.decided_on.desc(), Resolution.number.desc())
            )
        ).all()
        items: list[dict[str, Any]] = []
        for r in resolutions:
            entry: dict[str, Any] = {
                "resolution_id": r.id,
                "number": r.number,
                "decided_on": r.decided_on,
                "subject": r.subject,
                "status": r.status,
                "kind": r.subject_type,
                "legal_entity_name": names.get(r.legal_entity_id),
                "valid_from": None,
                "valid_to": None,
                "rhythm": None,
                "due_day": None,
                "instalments": None,
                "total": None,
                "purpose": None,
                "own_share": None,
            }
            if r.subject_type == "economic_plan" and r.subject_id is not None:
                plan = await session.get(EconomicPlan, r.subject_id)
                if plan is not None:
                    entry.update(
                        valid_from=plan.valid_from,
                        valid_to=None if plan.continues_until_new_plan else date(plan.year, 12, 31),
                        rhythm=plan.payment_rhythm,
                        due_day=plan.due_day,
                        own_share=_own_plan_share(plan.snapshot, own_units),
                    )
            elif r.subject_type == "special_levy" and r.subject_id is not None:
                levy = await session.get(SpecialLevy, r.subject_id)
                if levy is not None:
                    entry.update(
                        valid_from=levy.first_due,
                        instalments=levy.instalments,
                        total=levy.total,
                        purpose=levy.purpose,
                        own_share=_own_levy_share(levy.snapshot, own_units),
                    )
            entry["sepa"] = await _sepa(session, r.legal_entity_id, today)
            items.append(entry)
        return {"items": items, "note": PAYMENT_NOTE}


async def _consumption_scope(session: Any, account: Any, today: date) -> set[uuid.UUID]:
    """Ids of the owner's own (self used) ownership contracts; 403 while the feature is locked
    or the account is no owner."""
    from mhvp.platform.models import TenantSettings
    from mhvp.portal.consumption_info import LOCKED

    _, ownership = await _owner_scope(session, account, today)
    settings_row = await session.scalar(select(TenantSettings))
    if (
        settings_row is None
        or not settings_row.consumption_info_enabled
        or not settings_row.consumption_info_template_verified
    ):
        raise ProblemError(ErrorCodes.FORBIDDEN, detail=LOCKED)
    return ownership


@router.get("/consumption-info", summary="Verbrauchsinformation der selbst genutzten Einheiten")
async def owner_consumption(
    request: Request, ctx: Portal = Depends(portal_user)
) -> list[dict[str, Any]]:
    from mhvp.billing import consumption_info
    from mhvp.billing.models import ConsumptionInfo

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        ownership = await _consumption_scope(session, account, local_today())
        if not ownership:
            return []
        rows = (
            await session.scalars(
                select(ConsumptionInfo)
                .where(ConsumptionInfo.contract_id.in_(ownership))
                .order_by(ConsumptionInfo.month.desc())
            )
        ).all()
        return [consumption_info.tenant_view(r, with_snapshot=False) for r in rows]


@router.get(
    "/consumption-info/{info_id}", summary="Verbrauchsinformation eines Monats (Eigentümer)"
)
async def owner_consumption_one(
    info_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    from mhvp.billing import consumption_info
    from mhvp.billing.models import ConsumptionInfo

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        ownership = await _consumption_scope(session, account, local_today())
        row = await session.get(ConsumptionInfo, info_id)
        if row is None or row.contract_id not in ownership:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return consumption_info.tenant_view(row, with_snapshot=True)
