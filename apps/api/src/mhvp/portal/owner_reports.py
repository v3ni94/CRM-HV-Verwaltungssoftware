"""Owner portal reports (AF15: GAC-01, GAC-03, GAF-33), read only.

* ``GET /portal/owner/rental-statements`` lists the owner statements (rental or special
  property administration, ``billing.owner_statement``) of the account's own legal entities
  that were issued (status issued, due, posted or locked); ``.../{id}/pdf`` serves the same
  letter as the CRM. Release gate G3 and the tenant switch ``owner_rental_statements_enabled``
  (default off) apply: closed or off answers an empty list with a note, the PDF 403.
* ``GET /portal/owner/statement-explanations`` explains the issued hoa fee statements of the
  own units from their snapshot (debit, paid advances, result, reserve); release gate G4.
* ``GET /portal/owner/plans`` lists the resolved economic plans of the own community with the
  amounts of the own units from the plan snapshot; release gate G4.

Scope (5.3, 6.9.1): only grants from ``access_grant`` count. A legal entity is the account's
own when it is granted directly or when its party holds an own ownership contract in the
statement's property. Foreign or unreleased objects answer 404 without a hint. The texts are
explanations of the figures (Produktschutz), approved text blocks replace the defaults; none
of the endpoints posts, sends or opens a gate.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select

from mhvp.billing.status import StatementStatus
from mhvp.core.auth.principal import tenant_tx
from mhvp.core.escaping import content_disposition
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import (
    ReleaseGate,
    ReleaseGateClosedError,
    ensure_release_gate_open,
)
from mhvp.portal.owner import _owner_scope
from mhvp.portal.routers import Portal, portal_user
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal/owner", tags=["Portal"])

PLAN_STATUSES = (
    StatementStatus.RESOLVED,
    StatementStatus.ISSUED,
    StatementStatus.DUE,
    StatementStatus.POSTED,
    StatementStatus.LOCKED,
)
NOTE_RENTAL = (
    "Eigentümerabrechnung Ihrer Mietverwaltung oder Sondereigentumsverwaltung nach Ausgabe "
    "durch die Verwaltung."
)
NOTE_RENTAL_OFF = (
    "Die Eigentümerabrechnungen sind im Portal für diesen Mandanten nicht freigegeben. "
    "Bitte wenden Sie sich an die Verwaltung."
)
NOTE_GATE = (
    "Die Ausgabe im Portal ist für diesen Mandanten noch nicht freigegeben "
    "(Freigabestufe {gate}). Bitte wenden Sie sich an die Verwaltung."
)
NOTE_PLANS = (
    "Beschlossene Wirtschaftspläne Ihrer Gemeinschaft mit den Beträgen Ihrer Einheiten. "
    "Maßgeblich ist der Beschluss der Eigentümerversammlung."
)
# Default explanations of the figures; an approved text block with the same code replaces it.
TEXT_DEFAULTS: dict[str, str] = {
    "portal_owner_explain_debit": (
        "Kostenanteil: Ihr Anteil an den Kosten der Gemeinschaft nach dem beschlossenen "
        "Verteilerschlüssel."
    ),
    "portal_owner_explain_advances": (
        "Vorschüsse: beschlossene Hausgeldvorschüsse laut Wirtschaftsplan (Soll) und die im "
        "Abrechnungsjahr gezahlten Beträge (Ist)."
    ),
    "portal_owner_explain_result": (
        "Abrechnungsspitze: Kostenanteil abzüglich der beschlossenen Vorschüsse. Ein positiver "
        "Betrag ist eine Nachzahlung, ein negativer Betrag eine Anpassung zu Ihren Gunsten."
    ),
    "portal_owner_explain_arrears": (
        "Rückstände aus Vorschüssen sind gesondert ausgewiesen und keine neue Forderung aus der "
        "Abrechnung."
    ),
    "portal_owner_explain_reserve": (
        "Erhaltungsrücklage: beschlossene und gezahlte Zuführungen Ihrer Einheit sowie Anfangs- "
        "und Endbestand der Rücklage der Gemeinschaft."
    ),
    "portal_owner_explain_plan": (
        "Wirtschaftsplan: Jahresbetrag und monatlicher Vorschuss Ihrer Einheit für Hausgeld und "
        "Erhaltungsrücklage nach dem Beschluss. Rundungsdifferenzen sind ausgewiesen."
    ),
}


async def _texts(session: Any) -> tuple[dict[str, str], dict[str, str]]:
    from mhvp.documents import text_blocks

    approved = await text_blocks.approved_texts(session, tuple(TEXT_DEFAULTS))
    texts = {code: approved.get(code, default) for code, default in TEXT_DEFAULTS.items()}
    status = {code: ("released" if code in approved else "default") for code in TEXT_DEFAULTS}
    return texts, status


async def _gate_open(request: Request, tenant_id: uuid.UUID | None, gate: ReleaseGate) -> bool:
    try:
        await ensure_release_gate_open(gate, tenant_id, request.app.state.release_gate_resolver)
    except ReleaseGateClosedError:
        return False
    return True


async def _own_contracts(session: Any, ownership: set[uuid.UUID]) -> list[Any]:
    from mhvp.contracts.models import Contract

    if not ownership:
        return []
    return list((await session.scalars(select(Contract).where(Contract.id.in_(ownership)))).all())


async def _rental_scope(
    session: Any, account: Any, include_hoa: bool
) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    """(legal entity ids, ownership contract ids) for the owner statements (AG12, AF25-02).

    Own legal entities are the ``rental_owner`` entities granted to a pure rental owner
    (``access.RENTAL_OWNER_BASIS``) and, through the ownership contracts, the owner's own
    entities in the statement's property (see ``_rental_statements``). The community itself
    (hoa grant) counts only with the switch ``owner_hoa_rental_statements_enabled`` (default
    off, decision AF25-02 open). 403 without any owner grant."""
    from mhvp.portal import access
    from mhvp.portal.owner import OWNER_BASES

    today = local_today()
    active = await access.grants(session, account, today)
    rental_ids = {
        g.scope_id
        for g in active
        if g.legal_basis == access.RENTAL_OWNER_BASIS and g.scope_type == "legal_entity"
    }
    has_hoa = any(g.legal_basis in OWNER_BASES and g.scope_type == "legal_entity" for g in active)
    if not has_hoa:
        if not rental_ids:
            raise ProblemError(ErrorCodes.FORBIDDEN, detail="Nur für Eigentümer verfügbar.")
        return rental_ids, set()
    hoa_ids, ownership = await _owner_scope(session, account, today)
    return rental_ids | (hoa_ids if include_hoa else set()), ownership


async def _rental_statements(
    session: Any, entity_ids: set[uuid.UUID], ownership: set[uuid.UUID]
) -> list[Any]:
    """Issued owner statements of the account's own legal entities (see module doc)."""
    from mhvp.billing.owner_statement import OwnerStatement, OwnerStatementStatus
    from mhvp.properties.models import LegalEntity

    contracts = await _own_contracts(session, ownership)
    pairs = {(c.party_id, c.property_id) for c in contracts}
    rows = (
        await session.execute(
            select(OwnerStatement, LegalEntity.party_id)
            .join(LegalEntity, LegalEntity.id == OwnerStatement.legal_entity_id)
            .where(
                OwnerStatement.status.in_(
                    (
                        OwnerStatementStatus.ISSUED,
                        OwnerStatementStatus.DUE,
                        OwnerStatementStatus.POSTED,
                        OwnerStatementStatus.LOCKED,
                    )
                )
            )
            .order_by(OwnerStatement.period_to.desc(), OwnerStatement.id)
        )
    ).all()
    return [
        st
        for st, party_id in rows
        if st.legal_entity_id in entity_ids or (party_id, st.property_id) in pairs
    ]


def _rental_item(st: Any, prop: Any) -> dict[str, Any]:
    results = (st.snapshot or {}).get("results") or {}

    def amount(*keys: str) -> str | None:
        node: Any = results
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return None
            node = node[key]
        return str(node)

    return {
        "statement_id": st.id,
        "kind": st.kind.value,
        "period_from": st.period_from,
        "period_to": st.period_to,
        "status": st.status.value,
        "property_id": st.property_id,
        "property_name": f"{prop.number} {prop.name}" if prop is not None else None,
        "income_total": amount("income", "total"),
        "expenses_total": amount("expenses", "total"),
        "payouts_total": amount("payouts", "total"),
    }


@router.get(
    "/rental-statements",
    summary="Ausgegebene Eigentümerabrechnungen Miete/SEV",
    dependencies=[Depends(strict_query)],
)
async def owner_rental_statements(
    request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    from mhvp.portal import features as portal_features
    from mhvp.properties.models import Property

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        flags = await portal_features.get_or_default(session)
        entity_ids, ownership = await _rental_scope(
            session, account, bool(flags.owner_hoa_rental_statements_enabled)
        )
        if not flags.owner_rental_statements_enabled:
            return {"items": [], "note": NOTE_RENTAL_OFF, "enabled": False}
        if not await _gate_open(request, principal.tenant_id, ReleaseGate.G3):
            return {"items": [], "note": NOTE_GATE.format(gate="G3"), "enabled": False}
        items = []
        for st in await _rental_statements(session, entity_ids, ownership):
            items.append(_rental_item(st, await session.get(Property, st.property_id)))
        return {"items": items, "note": NOTE_RENTAL, "enabled": True}


@router.get(
    "/rental-statements/{statement_id}/pdf",
    summary="Eigentümerabrechnung Miete/SEV als PDF (nach Ausgabe)",
)
async def owner_rental_statement_pdf(
    statement_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> Response:
    from mhvp.billing.owner_statement_routers import render_letter_pdf
    from mhvp.portal import features as portal_features

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        flags = await portal_features.get_or_default(session)
        entity_ids, ownership = await _rental_scope(
            session, account, bool(flags.owner_hoa_rental_statements_enabled)
        )
        if not flags.owner_rental_statements_enabled:
            raise ProblemError(ErrorCodes.FORBIDDEN, detail=NOTE_RENTAL_OFF)
        await ensure_release_gate_open(
            ReleaseGate.G3, principal.tenant_id, request.app.state.release_gate_resolver
        )
        st = next(
            (
                s
                for s in await _rental_statements(session, entity_ids, ownership)
                if s.id == statement_id
            ),
            None,
        )
        if st is None or st.snapshot is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        content = await render_letter_pdf(session, request, st)
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": content_disposition(
                    "attachment", f"Eigentuemerabrechnung-{st.period_to:%Y}.pdf"
                ),
                "X-Content-Type-Options": "nosniff",
            },
        )


@router.get(
    "/statement-explanations",
    summary="Erläuterung der Einzelabrechnungen (Eigentümer)",
    dependencies=[Depends(strict_query)],
)
async def owner_statement_explanations(
    request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    from mhvp.portal.owner_statements import _own_units, _provided

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        hoa_ids, ownership = await _owner_scope(session, account, local_today())
        if not await _gate_open(request, principal.tenant_id, ReleaseGate.G4):
            return {"items": [], "texts": {}, "note": NOTE_GATE.format(gate="G4")}
        texts, status = await _texts(session)
        own = await _own_units(session, ownership)
        items: list[dict[str, Any]] = []
        for st in await _provided(session, hoa_ids):
            snap = st.snapshot or {}
            reserve = snap.get("reserve") or {}
            for unit in snap.get("units", []):
                if unit.get("unit_id") not in own:
                    continue
                items.append(
                    {
                        "statement_id": st.id,
                        "year": st.year,
                        "version": st.version,
                        "unit_id": uuid.UUID(unit["unit_id"]),
                        "unit_number": unit.get("unit_number"),
                        "cost_share": unit.get("cost_share"),
                        "advances_resolved": unit.get("advances_resolved"),
                        "advances_paid": unit.get("advances_paid"),
                        "result": unit.get("result"),
                        "arrears": unit.get("arrears"),
                        "reserve_due": unit.get("reserve_due"),
                        "reserve_paid": unit.get("reserve_paid"),
                        "reserve_opening": reserve.get("opening"),
                        "reserve_closing": reserve.get("closing"),
                    }
                )
        return {"items": items, "texts": texts, "text_status": status, "note": ""}


@router.get(
    "/plans",
    summary="Beschlossene Wirtschaftspläne (Eigentümer)",
    dependencies=[Depends(strict_query)],
)
async def owner_plans(request: Request, ctx: Portal = Depends(portal_user)) -> dict[str, Any]:
    from mhvp.accounting.models import Ledger
    from mhvp.hoa.models import EconomicPlan
    from mhvp.portal.owner_statements import _own_units

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        hoa_ids, ownership = await _owner_scope(session, account, local_today())
        if not await _gate_open(request, principal.tenant_id, ReleaseGate.G4):
            return {"items": [], "texts": {}, "note": NOTE_GATE.format(gate="G4")}
        texts, status = await _texts(session)
        own = await _own_units(session, ownership)
        plans = (
            await session.scalars(
                select(EconomicPlan)
                .join(Ledger, Ledger.id == EconomicPlan.ledger_id)
                .where(
                    Ledger.legal_entity_id.in_(hoa_ids),
                    EconomicPlan.status.in_(PLAN_STATUSES),
                    EconomicPlan.resolution_id.is_not(None),
                    EconomicPlan.obsolete_at.is_(None),
                )
                .order_by(EconomicPlan.year.desc(), EconomicPlan.version.desc())
            )
        ).all()
        items: list[dict[str, Any]] = []
        for plan in plans:
            snap = plan.snapshot or {}
            units = [
                {
                    "unit_id": uuid.UUID(u["unit_id"]),
                    "unit_number": u.get("unit_number"),
                    "annual": u.get("annual") or {},
                    "monthly": u.get("monthly") or {},
                    "rounding_difference": u.get("rounding_difference") or {},
                }
                for u in snap.get("units", [])
                if u.get("unit_id") in own
            ]
            if not units:
                continue
            items.append(
                {
                    "plan_id": plan.id,
                    "year": plan.year,
                    "version": plan.version,
                    "title": plan.title,
                    "valid_from": plan.valid_from,
                    "status": plan.status.value,
                    "payment_rhythm": plan.payment_rhythm,
                    "due_day": plan.due_day,
                    "continues_until_new_plan": plan.continues_until_new_plan,
                    "totals": snap.get("totals") or {},
                    "units": units,
                }
            )
        return {"items": items, "texts": texts, "text_status": status, "note": NOTE_PLANS}
