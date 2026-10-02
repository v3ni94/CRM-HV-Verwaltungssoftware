"""Ledger endpoints (/api/v1/accounting, M10).

Postings are allowed in ledgers that are not leading (parallel operation with Immoware24).
Declaring the platform as leading system requires release gate G1 (18.0, 6.9.10).
"""

import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal, Self
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import (
    chart_release,
    control_routers,
    creditor_routers,
    dunning,
    dunning_letters,
    invoice_checks,
    invoices,
    ledger_ops,
    numbering,
    receivables,
    reports,
    settlement,
    tax,
    xrechnung,
    xrechnung_credit,
)
from mhvp.accounting import services as svc
from mhvp.accounting.chart_rules import account_range_problem
from mhvp.accounting.models import (
    AccountCategory,
    AdminFeeSetting,
    ChartTemplate,
    DunningCase,
    DunningMahnbescheidPrep,
    DunningRun,
    DunningSettings,
    EntryKind,
    EntrySource,
    EntryStatus,
    ExportRun,
    Invoice,
    InvoiceKind,
    InvoiceLine,
    InvoiceReview,
    JournalEntry,
    JournalEntryNote,
    JournalLine,
    LeadingSystem,
    Ledger,
    LedgerAccount,
    LedgerInterestTaxConfig,
    OpenItem,
    PaymentTypeAccount,
    PostingStatus,
    ReceivableItem,
    ReceivableRun,
    RecurringInvoicePlan,
    ReviewStatus,
)
from mhvp.accounting.schemas import (
    AccountIn,
    AccountingAllocationIn,
    AccountingAllocationItemOut,
    AccountingAllocationOut,
    AccountingCostTransferIn,
    AccountingCreditorSyncOut,
    AccountingInterestIn,
    AccountingInterestTaxConfigIn,
    AccountingInterestTaxConfigOut,
    AccountingInterestTaxOut,
    AccountOut,
    AccountPatch,
    ChartTemplateOut,
    EntryOut,
    JournalEntryIn,
    LeadingIn,
    LedgerIn,
    LedgerOut,
    LineOut,
    LockIn,
    ReverseIn,
    SettlementConfirmIn,
    SettlementProposalIn,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import (
    ensure_session_legal_entity_allowed,
    ensure_session_property_allowed,
    session_allowed_legal_entity_ids,
    session_allowed_property_ids,
)
from mhvp.core.etag import check_if_match, etag_of
from mhvp.core.events import diff, emit
from mhvp.core.ids import uuid7
from mhvp.core.listparams import (
    LIST_PARAMS_DOC,
    ListParams,
    ListSpec,
    apply_filters,
    apply_sort,
    check_include,
    embed,
    list_params,
    strict_query,
)
from mhvp.core.pagination import PAGE_HEADERS, paginate
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ReleaseGateResolver, ensure_release_gate_open
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/accounting", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
UPDATE = require_permission("accounting:update")
APPROVE = require_permission("accounting:approve")


async def _get(session: Any, model: Any, entity_id: uuid.UUID) -> Any:
    row = await session.get(model, entity_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def _ensure_gate_for_ledger(
    request: Request, principal: TenantPrincipal, session: AsyncSession, ledger_id: uuid.UUID
) -> None:
    """G1 check with the object context of the ledger (GA14-02): a restricted approval opens
    only its pilot property or legal entity. Unknown ledgers are checked without context,
    so a closed gate still answers 403 before 404."""
    from mhvp.core.release_gates import ensure_release_gate_open_for

    row = (
        await session.execute(
            select(Ledger.property_id, Ledger.legal_entity_id).where(Ledger.id == ledger_id)
        )
    ).first()
    await ensure_release_gate_open_for(
        ReleaseGate.G1,
        principal.tenant_id,
        request.app.state.release_gate_resolver,
        property_id=row[0] if row else None,
        legal_entity_id=row[1] if row else None,
    )


async def _ledger(session: AsyncSession, ledger_id: uuid.UUID, *, lock: bool = False) -> Ledger:
    query = select(Ledger).where(Ledger.id == ledger_id)
    if lock:
        query = query.with_for_update()
    ledger = await session.scalar(query)
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    # A37: legal entity scope of the membership (tax advisor); foreign ledgers answer 404.
    ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)
    return ledger


async def _entry(
    session: AsyncSession, ledger: Ledger, entry_id: uuid.UUID, *, lock: bool = False
) -> JournalEntry:
    query = select(JournalEntry).where(
        JournalEntry.id == entry_id, JournalEntry.ledger_id == ledger.id
    )
    if lock:
        query = query.with_for_update()
    entry = await session.scalar(query)
    if entry is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return entry


async def _out(session: Any, entry: JournalEntry) -> EntryOut:
    return (await _outs(session, [entry]))[0]


async def _outs(session: Any, entries: Sequence[JournalEntry]) -> list[EntryOut]:
    """Lines of all entries in one query (performance review 26.09.2026)."""
    if not entries:
        return []
    lines: dict[uuid.UUID, list[LineOut]] = {}
    for line in await svc.entry_lines_of(session, [e.id for e in entries]):
        lines.setdefault(line.journal_entry_id, []).append(LineOut.model_validate(line))
    out = []
    for entry in entries:
        row = EntryOut.model_validate(entry)
        row.lines = lines.get(entry.id, [])
        out.append(row)
    return out


def _lines(body: JournalEntryIn) -> list[svc.LineIn]:
    return [
        svc.LineIn(
            account_id=line.account_id,
            debit=line.debit,
            credit=line.credit,
            text=line.text,
            vat_percent=line.vat_percent,
            vat_amount=line.vat_amount,
            net_amount=line.net_amount,
            unit_id=line.unit_id,
            cost_center=line.cost_center,
            property_id=line.property_id,
        )
        for line in body.lines
    ]


# Templates ----------------------------------------------------------------------------


@router.get("/templates", summary="Kontenrahmen-Vorlagen", dependencies=[Depends(strict_query)])
async def templates(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[ChartTemplateOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(ChartTemplate).order_by(ChartTemplate.code, ChartTemplate.version)
        )
        return [ChartTemplateOut.model_validate(t) for t in rows.all()]


@router.post("/templates/default", status_code=201, summary="Entwurf nach Anhang A.1 anlegen")
async def create_default_template(
    request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> ChartTemplateOut:
    async with tenant_tx(request, principal) as session:
        return ChartTemplateOut.model_validate(
            await svc.default_template(session, principal.tenant_id)
        )


@router.post(
    "/templates/{template_id}/release", summary="Vorlage freigeben (Betreiberentscheidung V8)"
)
async def release_template(
    template_id: uuid.UUID,
    request: Request,
    body: chart_release.ReleaseIn | None = None,
    principal: TenantPrincipal = Depends(APPROVE),
) -> ChartTemplateOut:
    """Release with date, releaser, comment and optional tax advisor document (M10-01/M10-02,
    V8). The workflow (draft, in_review, released, new version after a change) lives in
    ``mhvp.accounting.chart_release``; a released version is never changed again."""
    async with tenant_tx(request, principal) as session:
        template = await _get(session, ChartTemplate, template_id)
        template = await chart_release.release(
            session,
            template,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            comment=body.comment if body else None,
            document_id=body.document_id if body else None,
        )
        return ChartTemplateOut.model_validate(template)


# Ledgers ------------------------------------------------------------------------------


@router.post("/ledgers", status_code=201, summary="Buchungskreis je Rechtsträger anlegen")
async def create_ledger(
    body: LedgerIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> LedgerOut:
    async with tenant_tx(request, principal) as session:
        template = (
            await _get(session, ChartTemplate, body.template_id) if body.template_id else None
        )
        ledger = await svc.create_ledger(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            legal_entity_id=body.legal_entity_id,
            template=template,
            fiscal_year_start_month=body.fiscal_year_start_month,
            migration_cutoff=body.migration_cutoff,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ledger.created",
            entity_type="ledger",
            entity_id=ledger.id,
            actor_user_id=principal.user_id,
            payload={"legal_entity_id": str(ledger.legal_entity_id)},
        )
        return LedgerOut.model_validate(ledger)


@router.get("/ledgers", summary="Buchungskreise", dependencies=[Depends(strict_query)])
async def list_ledgers(
    request: Request,
    property_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[LedgerOut]:
    async with tenant_tx(request, principal) as session:
        query = select(Ledger).order_by(Ledger.name)
        if property_id:
            query = query.where(Ledger.property_id == property_id)
        # A37: a scoped membership (tax advisor) only lists its assigned legal entities.
        allowed = session_allowed_legal_entity_ids(session)
        if allowed is not None:
            query = query.where(Ledger.legal_entity_id.in_(list(allowed)))
        return [LedgerOut.model_validate(x) for x in (await session.scalars(query)).all()]


@router.get("/ledgers/{ledger_id}", summary="Buchungskreis")
async def get_ledger(
    ledger_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> LedgerOut:
    async with tenant_tx(request, principal) as session:
        return LedgerOut.model_validate(await _ledger(session, ledger_id))


@router.post(
    "/ledgers/{ledger_id}/sync-debtors", summary="Debitorenkonten aus Verträgen übernehmen"
)
async def sync_debtors(
    ledger_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, int]:
    async with tenant_tx(request, principal) as session:
        return {
            "created": await svc.sync_debtor_accounts(session, await _ledger(session, ledger_id))
        }


@router.post("/ledgers/{ledger_id}/lock", summary="Festschreiben bis Datum")
async def lock(
    ledger_id: uuid.UUID,
    body: LockIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id, lock=True)
        drafts = await svc.lock_period(session, ledger, body.until)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ledger.locked",
            entity_type="ledger",
            entity_id=ledger.id,
            actor_user_id=principal.user_id,
            payload={"locked_until": body.until.isoformat()},
        )
        # B05: unposted bank movements with open clarification up to the lock date are
        # reported with the lock (list "Buchungen ohne Beleg"); the lock itself is not
        # refused, the count is the visible warning of the audit trail.
        from mhvp.banking import clarifications

        unclarified = await clarifications.list_rows(
            session, ledger_id=ledger.id, until=body.until, open_only=True
        )
        return {
            "locked_until": body.until,
            "drafts_in_locked_period": drafts,
            "unclarified_bank_movements": len(unclarified),
        }


@router.post("/ledgers/{ledger_id}/leading", summary="Führendes System festlegen (G1)")
async def set_leading(
    ledger_id: uuid.UUID,
    body: LeadingIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> LedgerOut:
    async with tenant_tx(request, principal) as session:
        if body.leading_system is LeadingSystem.MHVP:
            await _ensure_gate_for_ledger(request, principal, session, ledger_id)
        ledger = await _ledger(session, ledger_id, lock=True)
        ledger.leading_system = body.leading_system
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ledger.leading_system_changed",
            entity_type="ledger",
            entity_id=ledger.id,
            actor_user_id=principal.user_id,
            payload={"leading_system": body.leading_system.value},
        )
        await session.flush()
        return LedgerOut.model_validate(ledger)


class AccountingLeadingSwitchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["receivable_posting", "dunning", "direct_debit", "payment_order"]
    leading_system: LeadingSystem
    valid_from: date
    property_id: uuid.UUID | None = None
    comment: str | None = Field(default=None, max_length=2000)


class AccountingLeadingSwitchDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approve: bool
    comment: str | None = Field(default=None, max_length=2000)


class AccountingLeadingSwitchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ledger_id: uuid.UUID
    property_id: uuid.UUID | None
    kind: str
    leading_system: str
    valid_from: date
    status: str
    comment: str | None
    requested_by: uuid.UUID
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_comment: str | None


class AccountingLeadingEffectiveOut(BaseModel):
    kind: str
    leading_system: str
    source: Literal["switch", "ledger"]


class AccountingLeadingSwitchListOut(BaseModel):
    items: list[AccountingLeadingSwitchOut]
    effective: list[AccountingLeadingEffectiveOut]
    ledger_leading_system: str


@router.get(
    "/ledgers/{ledger_id}/leading-switches",
    summary="Führendes System je Vorgangstyp (Umschaltungen, GAC-05)",
    dependencies=[Depends(strict_query)],
)
async def leading_switches(
    ledger_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> AccountingLeadingSwitchListOut:
    from mhvp.accounting import leading as lead
    from mhvp.accounting.models import LedgerLeadingSwitch

    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        rows = (
            await session.scalars(
                select(LedgerLeadingSwitch)
                .where(LedgerLeadingSwitch.ledger_id == ledger.id)
                .order_by(LedgerLeadingSwitch.valid_from.desc(), LedgerLeadingSwitch.created_at)
            )
        ).all()
        today = local_today()
        effective = []
        for kind in lead.LeadingKind:
            found = await lead.explicit(session, ledger, kind, today)
            effective.append(
                AccountingLeadingEffectiveOut(
                    kind=kind.value,
                    leading_system=(found or ledger.leading_system).value,
                    source="switch" if found is not None else "ledger",
                )
            )
        return AccountingLeadingSwitchListOut(
            items=[AccountingLeadingSwitchOut.model_validate(r) for r in rows],
            effective=effective,
            ledger_leading_system=ledger.leading_system.value,
        )


@router.post(
    "/ledgers/{ledger_id}/leading-switches",
    status_code=201,
    summary="Umschaltung des führenden Systems beantragen (zweite Person, GAC-05)",
)
async def request_leading_switch(
    ledger_id: uuid.UUID,
    body: AccountingLeadingSwitchIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> AccountingLeadingSwitchOut:
    from mhvp.accounting import leading as lead
    from mhvp.properties.models import Property

    if principal.user_id is None:
        raise ProblemError(ErrorCodes.GATE_FOUR_EYES, detail="Antrag nur durch eine Person.")
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        if body.property_id is not None:
            prop = await session.get(Property, body.property_id)
            if prop is None:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
            if ledger.property_id is not None and ledger.property_id != prop.id:
                raise ProblemError(
                    ErrorCodes.CONFLICT, detail="Das Objekt gehört nicht zu diesem Buchungskreis."
                )
        row = lead.request_switch(
            ledger,
            kind=lead.LeadingKind(body.kind),
            leading=body.leading_system,
            valid_from=body.valid_from,
            property_id=body.property_id,
            comment=body.comment,
            user_id=principal.user_id,
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ledger.leading_switch_requested",
            entity_type="ledger_leading_switch",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"kind": row.kind, "leading_system": row.leading_system},
        )
        await session.refresh(row)
        return AccountingLeadingSwitchOut.model_validate(row)


@router.post(
    "/ledgers/{ledger_id}/leading-switches/{switch_id}/decide",
    summary="Umschaltung freigeben oder ablehnen (andere Person, G1 bei Plattform)",
)
async def decide_leading_switch(
    ledger_id: uuid.UUID,
    switch_id: uuid.UUID,
    body: AccountingLeadingSwitchDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> AccountingLeadingSwitchOut:
    from mhvp.accounting import leading as lead
    from mhvp.accounting.models import LedgerLeadingSwitch

    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        row = await session.scalar(
            select(LedgerLeadingSwitch)
            .where(LedgerLeadingSwitch.id == switch_id, LedgerLeadingSwitch.ledger_id == ledger.id)
            .with_for_update()
        )
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if body.approve and lead.needs_g1(row):
            await _ensure_gate_for_ledger(request, principal, session, ledger.id)
        lead.decide(
            row,
            approve=body.approve,
            user_id=principal.user_id,
            is_platform_admin=principal.is_platform_admin,
            comment=body.comment,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ledger.leading_switch_" + row.status,
            entity_type="ledger_leading_switch",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"kind": row.kind, "leading_system": row.leading_system},
        )
        await session.flush()
        await session.refresh(row)
        return AccountingLeadingSwitchOut.model_validate(row)


# Accounts -----------------------------------------------------------------------------


@router.get("/ledgers/{ledger_id}/accounts", summary="Konten", dependencies=[Depends(strict_query)])
async def accounts(
    ledger_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[AccountOut]:
    async with tenant_tx(request, principal) as session:
        await _ledger(session, ledger_id)
        rows = await session.scalars(
            select(LedgerAccount)
            .where(LedgerAccount.ledger_id == ledger_id)
            .order_by(LedgerAccount.number)
        )
        return [AccountOut.model_validate(a) for a in rows.all()]


@router.post("/ledgers/{ledger_id}/accounts", status_code=201, summary="Konto ergänzen")
async def create_account(
    ledger_id: uuid.UUID,
    body: AccountIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> AccountOut:
    from mhvp.properties.models import PropertyBankAccount

    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        range_problem = account_range_problem(
            body.number, body.category, body.property_bank_account_id
        )
        if range_problem:
            raise ProblemError(ErrorCodes.ACC_ACCOUNT_RANGE_CATEGORY, detail=range_problem)
        if body.property_bank_account_id:
            bank = await _get(session, PropertyBankAccount, body.property_bank_account_id)
            if bank.legal_entity_id != ledger.legal_entity_id:
                raise ProblemError(
                    ErrorCodes.ACC_WRONG_ENTITY,
                    detail="Das Bankkonto gehört einem anderen Rechtsträger.",
                )
        account = LedgerAccount(
            tenant_id=principal.tenant_id,
            ledger_id=ledger.id,
            created_by=principal.user_id,
            **body.model_dump(),
        )
        session.add(account)
        try:
            await session.flush()
        except IntegrityError:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Kontonummer bereits vergeben."
            ) from None
        return AccountOut.model_validate(account)


@router.patch(
    "/ledgers/{ledger_id}/accounts/{account_id}", summary="Konto ändern oder deaktivieren"
)
async def patch_account(
    ledger_id: uuid.UUID,
    account_id: uuid.UUID,
    body: AccountPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> AccountOut:
    async with tenant_tx(request, principal) as session:
        account = await _get(session, LedgerAccount, account_id)
        if account.ledger_id != ledger_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(account, key, value)
        account.updated_by = principal.user_id
        await session.flush()
        return AccountOut.model_validate(account)


@router.delete(
    "/ledgers/{ledger_id}/accounts/{account_id}",
    status_code=204,
    summary="Konto ohne Buchungen löschen",
)
async def delete_account(
    ledger_id: uuid.UUID,
    account_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> None:
    async with tenant_tx(request, principal) as session:
        account = await _get(session, LedgerAccount, account_id)
        if account.ledger_id != ledger_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        used = await session.scalar(
            select(func.count())
            .select_from(JournalLine)
            .where(JournalLine.account_id == account_id)
        )
        if used:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Konten mit Buchungen können nur deaktiviert werden."
            )
        await session.delete(account)


# Entries ------------------------------------------------------------------------------


@router.post("/ledgers/{ledger_id}/entries", status_code=201, summary="Buchungssatz als Entwurf")
async def create_entry(
    ledger_id: uuid.UUID,
    body: JournalEntryIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> EntryOut:
    if body.kind is EntryKind.REVERSAL:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Stornos entstehen nur über die Stornofunktion."
        )
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        if body.idempotency_key:
            # D48: two concurrent calls with the same key are serialised so that the second
            # one finds the first draft instead of failing on the unique index (B08).
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": f"entry_idempotency:{ledger.id}:{body.idempotency_key}"},
            )
            existing = await session.scalar(
                select(JournalEntry).where(
                    JournalEntry.ledger_id == ledger.id,
                    JournalEntry.idempotency_key == body.idempotency_key,
                )
            )
            if existing is not None:
                return await _out(session, existing)  # repeated request: same draft (B08)
        entry = JournalEntry(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            ledger_id=ledger.id,
            source=EntrySource.MANUAL,
            **body.model_dump(exclude={"lines", "settlements"}),
        )
        await svc.write_draft(
            session, ledger, entry, _lines(body), [s.model_dump() for s in body.settlements]
        )
        return await _out(session, entry)


@router.put("/ledgers/{ledger_id}/entries/{entry_id}", summary="Entwurf ersetzen")
async def update_entry(
    ledger_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: JournalEntryIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> EntryOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        entry = await _entry(session, ledger, entry_id, lock=True)
        if entry.status is EntryStatus.POSTED:
            raise ProblemError(ErrorCodes.ACC_POSTED_IMMUTABLE)
        if body.kind is EntryKind.REVERSAL:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Stornos entstehen nur über die Stornofunktion."
            )
        for key, value in body.model_dump(
            exclude={"lines", "settlements", "idempotency_key"}
        ).items():
            setattr(entry, key, value)
        entry.approved_by, entry.updated_by = None, principal.user_id  # a change voids the check
        await svc.write_draft(
            session, ledger, entry, _lines(body), [s.model_dump() for s in body.settlements]
        )
        return await _out(session, entry)


@router.delete(
    "/ledgers/{ledger_id}/entries/{entry_id}", status_code=204, summary="Entwurf löschen"
)
async def delete_entry(
    ledger_id: uuid.UUID,
    entry_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> None:
    async with tenant_tx(request, principal) as session:
        entry = await _entry(session, await _ledger(session, ledger_id), entry_id, lock=True)
        if entry.status is EntryStatus.POSTED:
            raise ProblemError(ErrorCodes.ACC_POSTED_IMMUTABLE)
        # GAE-07 (AE40-05): a reclass draft of a released credit payable is withdrawn through
        # the payable, never deleted behind its back (the release would stay dangling).
        from mhvp.accounting.credit_payable_models import CreditPayable

        if await session.scalar(
            select(CreditPayable.id).where(CreditPayable.reclass_entry_id == entry.id).limit(1)
        ):
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail=(
                    "Der Entwurf gehört zu einem freigegebenen Guthabenposten. Bitte den Posten "
                    "über /credit-payables/{id}/withdraw zurücknehmen."
                ),
            )
        # AE40: withholdings recorded with an interest draft (P01-01, AE05) belong to the draft;
        # the foreign key is RESTRICT, so they go first (drafts are no postings, 0.1.7).
        from sqlalchemy import delete as sa_delete

        from mhvp.accounting.models import InterestTaxWithholding

        await session.execute(
            sa_delete(InterestTaxWithholding).where(
                InterestTaxWithholding.journal_entry_id == entry.id
            )
        )
        await session.delete(entry)


@router.get(
    "/ledgers/{ledger_id}/entries",
    summary="Journal",
    responses=PAGE_HEADERS,
    dependencies=[Depends(strict_query)],
)
async def journal(
    ledger_id: uuid.UUID,
    request: Request,
    response: Response,
    status: EntryStatus | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    page: int = Query(default=1, ge=1, description="Seite (ab 1), zusammen mit page_size"),
    page_size: int | None = Query(
        default=None,
        ge=1,
        le=1000,
        description="Einträge je Seite; ohne Angabe gilt limit (erste Seite)",
    ),
    property_id: uuid.UUID | None = Query(
        default=None, description="Nur Sätze mit mindestens einer Zeile dieses Objekts (Q15-01)"
    ),
    principal: TenantPrincipal = Depends(READ),
) -> list[EntryOut]:
    """Journal des Buchungskreises. Paginierung wie ``GET /tickets``: die Antwort bleibt eine
    Liste, Gesamtzahl und Seite stehen in ``X-Total-Count``, ``X-Page`` und ``X-Page-Size``;
    ``offset`` bleibt für bestehende Aufrufer erhalten. ``property_id`` filtert auf Sätze mit
    einer Zeile dieses Objekts (``journal_line.property_id``, Q15-01)."""
    async with tenant_tx(request, principal) as session:
        await _ledger(session, ledger_id)
        query = select(JournalEntry).where(JournalEntry.ledger_id == ledger_id)
        if status:
            query = query.where(JournalEntry.status == status)
        if start:
            query = query.where(JournalEntry.booking_date >= start)
        if end:
            query = query.where(JournalEntry.booking_date <= end)
        if property_id is not None:
            query = query.where(
                select(JournalLine.id)
                .where(
                    JournalLine.journal_entry_id == JournalEntry.id,
                    JournalLine.property_id == property_id,
                )
                .exists()
            )
        query = query.order_by(
            JournalEntry.fiscal_year.nulls_last(),
            JournalEntry.number.nulls_last(),
            JournalEntry.created_at,
        )
        rows = await paginate(
            session, query, response, page=page, page_size=page_size, limit=limit, offset=offset
        )
        return await _outs(session, rows)


@router.get("/ledgers/{ledger_id}/entries/{entry_id}", summary="Buchungssatz")
async def get_entry(
    ledger_id: uuid.UUID,
    entry_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> EntryOut:
    async with tenant_tx(request, principal) as session:
        return await _out(
            session, await _entry(session, await _ledger(session, ledger_id), entry_id)
        )


class AccountingEntryNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=4000)
    supersedes_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _not_blank(self) -> Self:
        if not self.body.strip():
            raise ValueError("body must not be blank")
        return self


class AccountingEntryNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    journal_entry_id: uuid.UUID
    note_key: uuid.UUID
    version: int
    supersedes_id: uuid.UUID | None
    body: str
    created_at: Any
    created_by: uuid.UUID | None
    is_current: bool = True


@router.get(
    "/ledgers/{ledger_id}/entries/{entry_id}/notes",
    summary="Vermerke zum Buchungssatz (alle Versionen)",
    dependencies=[Depends(strict_query)],
)
async def list_entry_notes(
    ledger_id: uuid.UUID,
    entry_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> list[AccountingEntryNoteOut]:
    async with tenant_tx(request, principal) as session:
        entry = await _entry(session, await _ledger(session, ledger_id), entry_id)
        notes = list(
            await session.scalars(
                select(JournalEntryNote)
                .where(JournalEntryNote.journal_entry_id == entry.id)
                .order_by(JournalEntryNote.created_at, JournalEntryNote.version)
            )
        )
        superseded = {n.supersedes_id for n in notes if n.supersedes_id is not None}
        out = []
        for note in notes:
            row = AccountingEntryNoteOut.model_validate(note)
            row.is_current = note.id not in superseded
            out.append(row)
        return out


@router.post(
    "/ledgers/{ledger_id}/entries/{entry_id}/notes",
    status_code=201,
    summary="Vermerk ergänzen oder als neue Version fortschreiben",
)
async def add_entry_note(
    ledger_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: AccountingEntryNoteIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> AccountingEntryNoteOut:
    """Notes never change the financial content of the entry (B03); every change is a new
    version, earlier versions stay readable (GA05-02). No release gate: a note is no posting."""
    async with tenant_tx(request, principal) as session:
        entry = await _entry(session, await _ledger(session, ledger_id), entry_id)
        if entry.status is not EntryStatus.POSTED:
            raise ProblemError(ErrorCodes.ACC_NOTE_ENTRY_NOT_POSTED)
        note_key, version = uuid7(), 1
        if body.supersedes_id is not None:
            prev = await session.scalar(
                select(JournalEntryNote)
                .where(JournalEntryNote.id == body.supersedes_id)
                .with_for_update()
            )
            if prev is None or prev.journal_entry_id != entry.id:
                raise ProblemError(ErrorCodes.ACC_NOTE_VERSION_CONFLICT)
            successor = await session.scalar(
                select(JournalEntryNote.id).where(JournalEntryNote.supersedes_id == prev.id)
            )
            if successor is not None:
                raise ProblemError(ErrorCodes.ACC_NOTE_VERSION_CONFLICT)
            note_key, version = prev.note_key, prev.version + 1
        note = JournalEntryNote(
            tenant_id=principal.tenant_id,
            journal_entry_id=entry.id,
            note_key=note_key,
            version=version,
            supersedes_id=body.supersedes_id,
            body=body.body,
            created_by=principal.user_id,
        )
        session.add(note)
        try:
            await session.flush()
        except IntegrityError:
            raise ProblemError(ErrorCodes.ACC_NOTE_VERSION_CONFLICT) from None
        await session.refresh(note)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="journal_entry.note_added",
            entity_type="journal_entry",
            entity_id=entry.id,
            actor_user_id=principal.user_id,
            payload={"note_id": str(note.id), "version": note.version},
        )
        return AccountingEntryNoteOut.model_validate(note)


@router.post(
    "/ledgers/{ledger_id}/entries/{entry_id}/approve",
    summary="Anfangsbestand prüfen (zweite Person)",
)
async def approve_entry(
    ledger_id: uuid.UUID,
    entry_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> EntryOut:
    async with tenant_tx(request, principal) as session:
        entry = await _entry(session, await _ledger(session, ledger_id), entry_id, lock=True)
        if entry.status is EntryStatus.POSTED:
            raise ProblemError(ErrorCodes.ACC_POSTED_IMMUTABLE)
        if entry.created_by == principal.user_id or principal.is_platform_admin:
            raise ProblemError(
                ErrorCodes.GATE_FOUR_EYES, detail="Die Prüfung muss eine andere Person vornehmen."
            )
        entry.approved_by = principal.user_id
        await session.flush()
        return await _out(session, entry)


@router.post(
    "/ledgers/{ledger_id}/entries/{entry_id}/post", summary="Buchen (festgeschriebene Nummer)"
)
async def post_entry(
    ledger_id: uuid.UUID,
    entry_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> EntryOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        entry = await _entry(session, ledger, entry_id, lock=True)
        already = entry.status is EntryStatus.POSTED
        await svc.post(session, ledger, entry, principal.user_id)
        if not already:
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="journal_entry.posted",
                entity_type="journal_entry",
                entity_id=entry.id,
                actor_user_id=principal.user_id,
                payload={"number": f"{entry.fiscal_year}-{entry.number}", "kind": entry.kind.value},
            )
        return await _out(session, entry)


@router.post(
    "/ledgers/{ledger_id}/entries/{entry_id}/reverse", status_code=201, summary="Stornieren"
)
async def reverse_entry(
    ledger_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: ReverseIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> EntryOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        entry = await _entry(session, ledger, entry_id, lock=True)
        booking_date = body.booking_date or svc.default_reversal_date(ledger, local_today())
        reversal = await svc.reverse(
            session,
            ledger,
            entry,
            user_id=principal.user_id,
            reason=body.reason,
            booking_date=booking_date,
            reason_code=body.reason_code,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="journal_entry.reversed",
            entity_type="journal_entry",
            entity_id=entry.id,
            actor_user_id=principal.user_id,
            payload={
                "reversal_id": str(reversal.id),
                "reason": body.reason,
                "reason_code": body.reason_code.value,
                "bank_transaction_id": (
                    str(entry.bank_transaction_id) if entry.bank_transaction_id else None
                ),
            },
        )
        return await _out(session, reversal)


# M10-01 allocation, M10-05 creditors, M10-06 cost transfer and interest -----------------


async def _allocation_out(session: AsyncSession, account: LedgerAccount) -> AccountingAllocationOut:
    rows = await ledger_ops.allocations(session, account)
    items = [
        AccountingAllocationItemOut(
            allocation_key_id=row.allocation_key_id,
            code=code,
            name=name,
            share_percent=row.share_percent,
        )
        for row, code, name in rows
    ]
    return AccountingAllocationOut(
        ledger_account_id=account.id,
        items=items,
        total_percent=sum((i.share_percent for i in items), Decimal("0")),
    )


@router.get(
    "/ledgers/{ledger_id}/accounts/{account_id}/allocations",
    summary="Verteilung eines Kostenkontos auf Umlageschlüssel",
    dependencies=[Depends(strict_query)],
)
async def get_allocations(
    ledger_id: uuid.UUID,
    account_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> AccountingAllocationOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        account = await ledger_ops.ledger_account(session, ledger, account_id)
        return await _allocation_out(session, account)


@router.put(
    "/ledgers/{ledger_id}/accounts/{account_id}/allocations",
    summary="Verteilung festlegen (Summe genau 100 %)",
)
async def put_allocations(
    ledger_id: uuid.UUID,
    account_id: uuid.UUID,
    body: AccountingAllocationIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> AccountingAllocationOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        account = await ledger_ops.ledger_account(session, ledger, account_id)
        await ledger_ops.replace_allocations(
            session,
            ledger,
            account,
            [(i.allocation_key_id, i.share_percent) for i in body.items],
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ledger_account.allocation_changed",
            entity_type="ledger_account",
            entity_id=account.id,
            actor_user_id=principal.user_id,
            payload={
                "items": [
                    {"allocation_key_id": str(i.allocation_key_id), "share": str(i.share_percent)}
                    for i in body.items
                ]
            },
        )
        return await _allocation_out(session, account)


@router.post(
    "/ledgers/{ledger_id}/sync-creditors",
    summary="Kreditorenkonten aus Dienstleisterverhältnissen anlegen",
)
async def sync_creditors(
    ledger_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> AccountingCreditorSyncOut:
    async with tenant_tx(request, principal) as session:
        created, linked = await ledger_ops.sync_creditor_accounts(
            session, await _ledger(session, ledger_id)
        )
        return AccountingCreditorSyncOut(created=created, linked=linked)


@router.post(
    "/ledgers/{ledger_id}/entries/cost-transfer",
    status_code=201,
    summary="Kostenkorrektur als Entwurf",
)
async def create_cost_transfer(
    ledger_id: uuid.UUID,
    body: AccountingCostTransferIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> EntryOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        entry = await ledger_ops.cost_transfer_draft(
            session,
            ledger,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            **body.model_dump(),
        )
        return await _out(session, entry)


@router.post(
    "/ledgers/{ledger_id}/entries/interest",
    status_code=201,
    summary="Zinsbuchung als Entwurf",
)
async def create_interest(
    ledger_id: uuid.UUID,
    body: AccountingInterestIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> EntryOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        entry = await ledger_ops.interest_draft(
            session,
            ledger,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            **body.model_dump(),
        )
        return await _out(session, entry)


# P01-01 withholding taxes on credit interest (AE05) -------------------------------------


def _tax_config_out(ledger_id: uuid.UUID, config: Any | None) -> AccountingInterestTaxConfigOut:
    out = AccountingInterestTaxConfigOut(ledger_id=ledger_id)
    if config is not None:
        for field in ledger_ops.TAX_ACCOUNT_FIELDS:
            setattr(out, field, getattr(config, field))
    return out


@router.get(
    "/ledgers/{ledger_id}/interest-tax-config",
    summary="Steuerkonten für Abzüge auf Habenzinsen",
    dependencies=[Depends(strict_query)],
)
async def get_interest_tax_config(
    ledger_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> AccountingInterestTaxConfigOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        return _tax_config_out(ledger.id, await ledger_ops.interest_tax_config(session, ledger))


class AccountingInterestTaxSummaryOut(BaseModel):
    """Tenant wide state of the tax accounts for withholdings on credit interest (GAE-38)."""

    ledgers_total: int
    ledgers_configured: int


@router.get(
    "/interest-tax-config",
    summary="Steuerkonten für Abzüge auf Habenzinsen: Stand über alle Buchungskreise",
    dependencies=[Depends(strict_query)],
)
async def get_interest_tax_summary(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> AccountingInterestTaxSummaryOut:
    """Read only: how many ledgers have at least one tax account set. Changes nothing."""
    async with tenant_tx(request, principal) as session:
        total = int(await session.scalar(select(func.count()).select_from(Ledger)) or 0)
        configured = int(
            await session.scalar(
                select(func.count())
                .select_from(LedgerInterestTaxConfig)
                .where(
                    or_(
                        LedgerInterestTaxConfig.capital_gains_tax_account_id.is_not(None),
                        LedgerInterestTaxConfig.solidarity_tax_account_id.is_not(None),
                        LedgerInterestTaxConfig.church_tax_account_id.is_not(None),
                    )
                )
            )
            or 0
        )
        return AccountingInterestTaxSummaryOut(ledgers_total=total, ledgers_configured=configured)


@router.put(
    "/ledgers/{ledger_id}/interest-tax-config",
    summary="Steuerkonten für Abzüge auf Habenzinsen festlegen",
)
async def put_interest_tax_config(
    ledger_id: uuid.UUID,
    body: AccountingInterestTaxConfigIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> AccountingInterestTaxConfigOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        before = _tax_config_out(
            ledger.id, await ledger_ops.interest_tax_config(session, ledger)
        ).model_dump(mode="json")
        config = await ledger_ops.set_interest_tax_config(
            session,
            ledger,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            values=body.model_dump(),
        )
        out = _tax_config_out(ledger.id, config)
        after = out.model_dump(mode="json")
        # GAI-307: tax accounts for interest withholdings stay traceable (rule 6).
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ledger_interest_tax_config.updated",
            entity_type="ledger",
            entity_id=ledger.id,
            actor_user_id=principal.user_id,
            payload=after,
            changes=diff(before, after),
        )
        return out


@router.get(
    "/ledgers/{ledger_id}/entries/{entry_id}/interest-tax",
    summary="Steuerabzüge einer Zinsbuchung",
    dependencies=[Depends(strict_query)],
)
async def get_interest_tax(
    ledger_id: uuid.UUID,
    entry_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> AccountingInterestTaxOut:
    async with tenant_tx(request, principal) as session:
        entry = await _get(session, JournalEntry, entry_id)
        if entry.ledger_id != ledger_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = await ledger_ops.withholding_for(session, entry)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        withheld = row.capital_gains_tax + row.solidarity_tax + row.church_tax
        return AccountingInterestTaxOut(
            journal_entry_id=entry.id,
            gross_amount=row.gross_amount,
            capital_gains_tax=row.capital_gains_tax,
            solidarity_tax=row.solidarity_tax,
            church_tax=row.church_tax,
            net_amount=row.gross_amount - withheld,
        )


# Reports ------------------------------------------------------------------------------


@router.get("/ledgers/{ledger_id}/accounts/{account_id}/sheet", summary="Kontenblatt")
async def account_sheet(
    ledger_id: uuid.UUID,
    account_id: uuid.UUID,
    request: Request,
    start: date,
    end: date,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        account = await _get(session, LedgerAccount, account_id)
        if account.ledger_id != ledger_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return await svc.account_sheet(session, account, start, end)


@router.get("/ledgers/{ledger_id}/trial-balance", summary="Saldenliste zum Stichtag")
async def trial_balance(
    ledger_id: uuid.UUID,
    request: Request,
    as_of: date,
    start: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return await svc.trial_balance(session, await _ledger(session, ledger_id), as_of, start)


@router.get(
    "/ledgers/{ledger_id}/open-items",
    summary="Offene Posten zum Stichtag",
    dependencies=[Depends(strict_query)],
)
async def open_items(
    ledger_id: uuid.UUID,
    request: Request,
    as_of: date,
    account_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        return await svc.open_items(session, await _ledger(session, ledger_id), as_of, account_id)


# Settlement proposal in the statutory order (M10-03, 7.4 Nr. 5, D39) -------------------


async def _proposal(
    session: AsyncSession, ledger: Ledger, body: SettlementProposalIn
) -> settlement.Proposal:
    items = await settlement.items_for(session, ledger, body.account_id, body.as_of)
    determination = [
        settlement.Determination(d.open_item_id, d.amount) for d in body.determination
    ] or settlement.determination_from_purpose(items, body.purpose)
    return settlement.propose(items, body.amount, body.as_of, determination)


@router.post(
    "/ledgers/{ledger_id}/open-items/settlement-proposal",
    summary="Ausgleichsvorschlag nach gesetzlicher Reihenfolge (nur Vorschlag, M10-03)",
)
async def settlement_proposal(
    ledger_id: uuid.UUID,
    body: SettlementProposalIn,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """Deterministic proposal, nothing is written. An explicit determination of the payer
    (``determination`` or a purpose naming the items) wins over the statutory order (D39)."""
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        return (await _proposal(session, ledger, body)).to_dict()


@router.post(
    "/ledgers/{ledger_id}/open-items/settlement-proposal/confirm",
    status_code=201,
    summary="Ausgleichsvorschlag bestätigen (Entwurf, Buchung nur mit G1)",
)
async def settlement_confirm(
    ledger_id: uuid.UUID,
    body: SettlementConfirmIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> EntryOut:
    """A staff member confirms the recomputed proposal (fingerprint), which becomes a draft
    debtor payment with an explicit settlement plan; the confirmation is audited with the rule
    version. ``post_immediately`` posts the draft and requires release gate G1."""
    async with tenant_tx(request, principal) as session:
        if body.post_immediately:
            await _ensure_gate_for_ledger(request, principal, session, ledger_id)
        ledger = await _ledger(session, ledger_id)
        proposal = await _proposal(session, ledger, body)
        settlement.verify_fingerprint(proposal, body.fingerprint)
        if not proposal.allocations:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Der Vorschlag enthält keinen Ausgleich."
            )
        bank = await _get(session, LedgerAccount, body.bank_account_id)
        if bank.ledger_id != ledger.id or bank.category not in (
            AccountCategory.BANK,
            AccountCategory.CASH,
        ):
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Gegenkonto muss ein Bank- oder Kassenkonto sein."
            )
        entry = JournalEntry(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            ledger_id=ledger.id,
            booking_date=body.booking_date,
            text=(body.text or f"Zahlungseingang, Ausgleich nach Vorschlag {settlement.RULE_ID}")[
                :500
            ],
            kind=EntryKind.DEBTOR_PAYMENT,
            reference=body.reference,
            source=EntrySource.MANUAL,
        )
        # Overpayment stays as credit on the debtor account, never income (D07, 7.4 Nr. 5).
        lines = [
            svc.LineIn(bank.id, body.amount, Decimal("0")),
            svc.LineIn(body.account_id, Decimal("0"), body.amount),
        ]
        plan = [{"open_item_id": a.open_item_id, "amount": a.amount} for a in proposal.allocations]
        await svc.write_draft(session, ledger, entry, lines, plan)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="open_item_settlement.proposal_confirmed",
            entity_type="journal_entry",
            entity_id=entry.id,
            actor_user_id=principal.user_id,
            payload={
                "rule": settlement.RULE_ID,
                "rule_version": settlement.RULE_VERSION,
                "fingerprint": proposal.fingerprint,
                "basis": proposal.basis,
                "note": settlement.PROPOSAL_NOTE,
                "account_id": str(body.account_id),
                "amount": str(body.amount),
                "unallocated": str(proposal.unallocated),
                "allocations": [
                    {
                        "open_item_id": str(a.open_item_id),
                        "amount": str(a.amount),
                        "reason": a.reason,
                        "rank": a.rank,
                    }
                    for a in proposal.allocations
                ],
                "post_immediately": body.post_immediately,
            },
        )
        if body.post_immediately:
            await svc.post(session, ledger, entry, principal.user_id)
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="journal_entry.posted",
                entity_type="journal_entry",
                entity_id=entry.id,
                actor_user_id=principal.user_id,
                payload={"number": f"{entry.fiscal_year}-{entry.number}", "kind": entry.kind.value},
            )
        return await _out(session, entry)


@router.get(
    "/ledgers/{ledger_id}/checks",
    summary="Konsistenzprüfung B02, B07, B09",
    dependencies=[Depends(strict_query)],
)
async def checks(
    ledger_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    as_of: date | None = None,
    exclude_written_off: bool | None = None,
) -> dict[str, Any]:
    """``findings`` are hard violations (B02, B04 numbering, B07, B09); ``subledger`` lists
    per debtor and creditor account the open items against the ledger balance as of
    ``as_of`` (GA05-03). A difference there is shown for review, it does not set ``ok``.
    AC01-02: written off items and items of reversed entries are hidden by the tenant switch
    (default) or ``exclude_written_off``; ``excluded`` counts them separately. GAI-604:
    ``bank_findings`` lists breaks in the statement chain of the linked bank accounts
    (opening balance, sums, period gaps); they are shown for review and do not set ``ok``
    because they concern the imported statements, not the postings (``bank_ok``)."""
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        findings = await svc.checks(session, ledger)
        bank_findings = await svc.bank_statement_chain_findings(session, ledger)
        exclude = (
            exclude_written_off
            if exclude_written_off is not None
            else await svc.subledger_exclude_switch(session)
        )
        subledger = await svc.subledger_reconciliation(session, ledger, as_of, exclude)
        excluded = {
            "written_off": {
                "count": sum(r["excluded_written_off_count"] for r in subledger),
                "amount": str(
                    sum((Decimal(r["excluded_written_off"]) for r in subledger), Decimal(0))
                ),
            },
            "reversed": {
                "count": sum(r["excluded_reversed_count"] for r in subledger),
                "amount": str(
                    sum((Decimal(r["excluded_reversed"]) for r in subledger), Decimal(0))
                ),
            },
        }
        return {
            "ok": not findings,
            "findings": findings,
            "bank_ok": not bank_findings,
            "bank_findings": bank_findings,
            "exclude_written_off": exclude,
            "excluded": excluded,
            "subledger": subledger,
            "subledger_differences": [r for r in subledger if Decimal(r["difference"]) != 0],
        }


# Receivable runs and management fee (M13, 7.5) ----------------------------------------


class PaymentTypeMappingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_type_code: str = Field(min_length=1, max_length=63)
    account_id: uuid.UUID


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_month: date
    scope: str = Field(default="all", pattern="^(all|property|contract)$")
    scope_id: uuid.UUID | None = None


class RunReverseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=2000)
    booking_date: date | None = None


class FeeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: uuid.UUID
    start_date: date
    end_date: date | None = None
    vat_percent: Decimal = Decimal(0)
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    amounts_per_unit_type: dict[str, Decimal]
    invoice_debtor_party_id: uuid.UUID | None = None
    contract_document_id: uuid.UUID | None = None
    # GA03-06
    manager_contact_id: uuid.UUID | None = None
    termination_date: date | None = None
    due_day_rule: Literal["day", "last_day", "day_next_month"] | None = None
    due_day: int | None = Field(default=None, ge=1, le=31)
    account_id: uuid.UUID | None = None
    sev_fee_amount: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _due_rule(self) -> Self:
        if self.due_day_rule in ("day", "day_next_month") and self.due_day is None:
            raise ValueError("Für diese Fälligkeitsregel ist ein Tag anzugeben.")
        if self.termination_date is not None and self.termination_date < self.start_date:
            raise ValueError("Das Kündigungsdatum liegt vor dem Beginn.")
        return self


def _run_out(run: ReceivableRun, items: list[ReceivableItem]) -> dict[str, Any]:
    return {
        "id": run.id,
        "period_month": run.period_month,
        "scope": run.scope,
        "status": run.status.value,
        "totals": run.totals,
        "posted_at": run.posted_at,
        "items": [
            {
                "id": i.id,
                "contract_id": i.contract_id,
                "payment_type_code": i.payment_type_code,
                "amount": i.amount,
                "net_amount": i.net_amount,
                "vat_percent": i.vat_percent,
                "vat_amount": i.vat_amount,
                "period_start": i.period_start,
                "period_end": i.period_end,
                "due_date": i.due_date,
                "status": i.status.value,
                "message": i.message,
                "journal_entry_id": i.journal_entry_id,
                "contract_payment_id": i.contract_payment_id,
                "contract_version": i.contract_version,
                "payment_schedule_id": i.payment_schedule_id,
                "basis_valid_from": i.basis_valid_from,
                "basis_reason": i.basis_reason,
                "basis_document_id": i.basis_document_id,
                "difference_of_item_id": i.difference_of_item_id,
                "difference_amount": i.difference_amount,
            }
            for i in items
        ],
        "calculation": run.calculation,
    }


async def _items(session: AsyncSession, run_id: uuid.UUID) -> list[ReceivableItem]:
    return list(
        (
            await session.scalars(
                select(ReceivableItem)
                .where(ReceivableItem.run_id == run_id)
                .order_by(ReceivableItem.created_at)
            )
        ).all()
    )


@router.put("/ledgers/{ledger_id}/payment-type-accounts", summary="Erlöskonto je Zahlungsart")
async def set_mapping(
    ledger_id: uuid.UUID,
    body: PaymentTypeMappingIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        account = await _get(session, LedgerAccount, body.account_id)
        if account.ledger_id != ledger.id:
            raise ProblemError(ErrorCodes.ACC_WRONG_ENTITY)
        # M13-03: the output tax of receivables is mapped under the reserved code
        # ``vat_output`` to a tax account; every other code needs a revenue account.
        if body.payment_type_code == receivables.VAT_OUTPUT_CODE:
            if account.category.value != "tax":
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Die Umsatzsteuer der Sollstellung wird auf ein Steuerkonto gebucht.",
                )
        elif account.category.value != "revenue":
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Sollstellungen werden auf Erlöskonten gebucht."
            )
        row = await session.scalar(
            select(PaymentTypeAccount).where(
                PaymentTypeAccount.ledger_id == ledger.id,
                PaymentTypeAccount.payment_type_code == body.payment_type_code,
            )
        )
        if row is None:
            row = PaymentTypeAccount(
                tenant_id=principal.tenant_id, ledger_id=ledger.id, **body.model_dump()
            )
            session.add(row)
        else:
            row.account_id = body.account_id
        await session.flush()
        return {"payment_type_code": row.payment_type_code, "account_id": row.account_id}


class PaymentTypeMappingOut(BaseModel):
    payment_type_code: str
    account_id: uuid.UUID
    account_number: str
    account_name: str


@router.get(
    "/ledgers/{ledger_id}/payment-type-accounts",
    summary="Bestehende Zuordnungen Zahlungsart zu Konto",
    response_model=list[PaymentTypeMappingOut],
    dependencies=[Depends(strict_query)],
)
async def list_mappings(
    ledger_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> list[PaymentTypeMappingOut]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        rows = (
            await session.execute(
                select(PaymentTypeAccount, LedgerAccount)
                .join(LedgerAccount, LedgerAccount.id == PaymentTypeAccount.account_id)
                .where(PaymentTypeAccount.ledger_id == ledger.id)
                .order_by(PaymentTypeAccount.payment_type_code)
            )
        ).all()
        return [
            PaymentTypeMappingOut(
                payment_type_code=m.payment_type_code,
                account_id=a.id,
                account_number=a.number,
                account_name=a.name,
            )
            for m, a in rows
        ]


@router.post("/receivable-runs", status_code=201, summary="Sollstellungslauf: Vorschau")
async def preview_run(
    body: RunIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        run = await receivables.create_preview(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            period=body.period_month,
            scope=body.scope,
            scope_id=body.scope_id,
        )
        return _run_out(run, await _items(session, run.id))


@router.get(
    "/receivable-runs",
    summary="Sollstellungsläufe",
    responses=PAGE_HEADERS,
    dependencies=[Depends(strict_query)],
)
async def list_runs(
    request: Request,
    response: Response,
    period_month: date | None = None,
    scope: str | None = Query(default=None, pattern="^(all|property|contract)$"),
    scope_id: uuid.UUID | None = None,
    status: str | None = Query(default=None, pattern="^(preview|posted|reversed)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    """M13-08: earlier runs per month and scope, newest first, without items."""
    async with tenant_tx(request, principal) as session:
        query = select(ReceivableRun)
        if period_month is not None:
            query = query.where(ReceivableRun.period_month == period_month.replace(day=1))
        if scope is not None:
            query = query.where(ReceivableRun.scope == scope)
        if scope_id is not None:
            query = query.where(ReceivableRun.scope_id == scope_id)
        if status is not None:
            query = query.where(ReceivableRun.status == status)
        query = query.order_by(ReceivableRun.period_month.desc(), ReceivableRun.created_at.desc())
        rows = await paginate(
            session, query, response, page=page, page_size=page_size, limit=page_size
        )
        return [
            {
                "id": r.id,
                "period_month": r.period_month,
                "scope": r.scope,
                "scope_id": r.scope_id,
                "status": r.status.value,
                "totals": r.totals,
                "created_at": r.created_at,
                "created_by": r.created_by,
                "posted_at": r.posted_at,
            }
            for r in rows
        ]


@router.get("/receivable-runs/{run_id}", summary="Sollstellungslauf")
async def get_run(
    run_id: uuid.UUID,
    request: Request,
    item_status: str | None = Query(
        default=None, pattern="^(ready|manual|blocked|posted|reversed)$"
    ),
    contract_id: uuid.UUID | None = None,
    payment_type_code: str | None = Query(default=None, max_length=63),
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """Items can be filtered by status, contract and payment type (M13-08)."""
    async with tenant_tx(request, principal) as session:
        run = await _get(session, ReceivableRun, run_id)
        items = [
            i
            for i in await _items(session, run.id)
            if (item_status is None or i.status.value == item_status)
            and (contract_id is None or i.contract_id == contract_id)
            and (payment_type_code is None or i.payment_type_code == payment_type_code)
        ]
        return _run_out(run, items)


@router.post("/receivable-runs/{run_id}/post", summary="Sollstellungslauf buchen")
async def post_run(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        run = await session.get(ReceivableRun, run_id, with_for_update=True)
        if run is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if receivables.rules_applied(run):
            # M13-01 to M13-03: computed pro rata, instalment or VAT items are drafts behind
            # release gate G1 (tax adviser review of the rules is open).
            resolver: ReleaseGateResolver = request.app.state.release_gate_resolver
            await ensure_release_gate_open(ReleaseGate.G1, principal.tenant_id, resolver)
        try:
            await receivables.post_run(session, run, principal.user_id)
        except IntegrityError:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Sollstellung für diesen Zeitraum wurde bereits gebucht.",
            ) from None
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="receivable_run.posted",
            entity_type="receivable_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload={"period": run.period_month.isoformat(), "totals": run.totals},
        )
        return _run_out(run, await _items(session, run.id))


@router.post("/receivable-runs/{run_id}/reverse", summary="Sollstellungslauf stornieren")
async def reverse_run(
    run_id: uuid.UUID,
    body: RunReverseIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        run = await session.get(ReceivableRun, run_id, with_for_update=True)
        if run is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        count = await receivables.reverse_run(
            session, run, principal.user_id, body.reason, body.booking_date or local_today()
        )
        return {"reversed": count, "status": run.status.value}


@router.post("/admin-fees", status_code=201, summary="Verwalterhonorar einrichten")
async def create_fee(
    body: FeeIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    from mhvp.accounting import admin_fees
    from mhvp.contacts.models import Party

    async with tenant_tx(request, principal) as session:
        if body.invoice_debtor_party_id is not None:
            await _get(session, Party, body.invoice_debtor_party_id)  # D58: debtor must exist
        await admin_fees.check_fee_refs(
            session, body.property_id, body.manager_contact_id, body.account_id
        )
        data = body.model_dump()
        data["amounts_per_unit_type"] = {k: str(v) for k, v in body.amounts_per_unit_type.items()}
        row = AdminFeeSetting(tenant_id=principal.tenant_id, created_by=principal.user_id, **data)
        session.add(row)
        await session.flush()
        # Lexware Office (INT-LEXO-01): prepare the recurring invoice (API is read only for
        # recurring templates, so a checklist for the manual creation); never fails the fee.
        from mhvp.integrations.lexoffice_ext import invoice_drafts as lexoffice_drafts

        try:
            prep = await lexoffice_drafts.prepare_recurring(
                session, principal.tenant_id, row, principal.user_id
            )
        except Exception:  # pragma: no cover - defensive
            prep = None
        return {"id": row.id, "lexoffice_recurring_prep_id": prep.id if prep else None}


@router.get("/admin-fees/{fee_id}/invoice-preview", summary="Honorarrechnung als Entwurf berechnen")
async def fee_preview(
    fee_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """Draft only: issuing an invoice (XRechnung) needs the tax data of the tenant (M13-04)."""
    async with tenant_tx(request, principal) as session:
        fee = await _get(session, AdminFeeSetting, fee_id)
        counts = await receivables.fee_unit_counts(session, fee, local_today())
        return await receivables.admin_fee_draft(session, fee, counts)


@router.post(
    "/admin-fees/{fee_id}/invoice-issue",
    summary="Honorarrechnung als XRechnung ausstellen (Rechnungsnummer, USt-Prüfung)",
)
async def fee_issue(
    fee_id: uuid.UUID,
    request: Request,
    invoice_date: date | None = None,
    period_start: date | None = None,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    """Allocates the gapless PREFIX-JJJJ-000001 invoice number (M13-04) and blocks when the
    tenant's VAT status or tax data required for XRechnung is missing. With ``period_start``
    the invoice covers the service period of the fee interval containing that day (M13-06);
    a period is invoiced once while the invoice is not cancelled (409)."""
    from mhvp.accounting import admin_fees
    from mhvp.platform.models import TenantBillingSettings

    async with tenant_tx(request, principal) as session:
        fee = await session.get(AdminFeeSetting, fee_id, with_for_update=True)
        if fee is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        issue_date = invoice_date or local_today()
        period: tuple[date, date] | None = None
        if period_start is not None:
            period = admin_fees.period_for(fee.interval, period_start)
            admin_fees.check_period(fee, *period)
            if await admin_fees.issued_for_period(session, fee.id, period[0]) is not None:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail="Für diesen Leistungszeitraum ist bereits eine Rechnung ausgestellt.",
                )
        counts = await receivables.fee_unit_counts(session, fee, issue_date)
        draft = await receivables.admin_fee_draft(session, fee, counts)
        billing_settings = await session.scalar(
            select(TenantBillingSettings).where(
                TenantBillingSettings.tenant_id == principal.tenant_id
            )
        )
        numbering.assert_xrechnung_allowed(billing_settings)
        number = await numbering.allocate_invoice_number(
            session, principal.tenant_id, issue_date.year
        )
        # A12: the issued invoice is frozen for the XRechnung XML
        # (GET /accounting/invoices/{id}/xrechnung.xml, mhvp.accounting.xrechnung).
        issued = await xrechnung.issue(
            session,
            fee=fee,
            draft=draft,
            number=number,
            issue_date=issue_date,
            billing=billing_settings,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            period=period,
        )
        draft["id"] = str(issued.id)
        draft["period_start"] = period[0] if period else None
        draft["period_end"] = period[1] if period else None
        draft["number"] = number
        draft["invoice_date"] = issue_date
        draft["due_date"] = admin_fees.fee_due_date(fee, period[0] if period else issue_date)
        draft["status"] = issued.status.value
        draft["xrechnung_url"] = f"/api/v1/accounting/invoices/{issued.id}/xrechnung.xml"
        # A69: outgoing event for subscribers (section 12, docs/integrations/webhooks.md).
        # Identifiers and amounts only; the debtor's name, address and IBAN stay out.
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice.issued",
            entity_type="admin_fee_invoice",
            entity_id=issued.id,
            actor_user_id=principal.user_id,
            payload={
                "invoice_id": str(issued.id),
                "number": number,
                "invoice_date": issue_date.isoformat(),
                "kind": "admin_fee",
                "fee_setting_id": str(fee.id),
                "property_id": str(fee.property_id),
                "debtor_legal_entity_id": (
                    str(issued.debtor_legal_entity_id) if issued.debtor_legal_entity_id else None
                ),
                "net": str(issued.net),
                "vat": str(issued.vat),
                "gross": str(issued.gross),
                "currency": "EUR",
                "xrechnung_url": draft["xrechnung_url"],
            },
        )
        return draft


# Incoming invoices (M14, 7.9.1) --------------------------------------------------------


class InvoiceLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: uuid.UUID
    net: Decimal
    vat_percent: Decimal = Decimal(0)
    vat: Decimal = Decimal(0)
    accrual_date: date | None = None
    section_35a_amount: Decimal | None = None
    unit_id: uuid.UUID | None = None
    text: str | None = Field(default=None, max_length=500)
    # M14-02: quantity and unit price for the price and quantity comparison (findings only).
    quantity: Decimal | None = Field(default=None, gt=0)
    unit_price: Decimal | None = None


class InvoiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ledger_id: uuid.UUID
    provider_contact_id: uuid.UUID
    kind: InvoiceKind = InvoiceKind.INVOICE
    number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    due_date: date | None = None
    service_from: date | None = None
    service_to: date | None = None
    net: Decimal
    vat: Decimal
    gross: Decimal
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    discount_until: date | None = None
    payee_iban: str | None = Field(default=None, max_length=34)
    document_id: uuid.UUID | None = None
    e_invoice_format: str = Field(default="none", pattern="^(none|xrechnung|zugferd)$")
    order_reference: str | None = Field(default=None, max_length=100)
    recipient_name: str | None = Field(default=None, max_length=400)
    deductions: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    supersedes_id: uuid.UUID | None = None
    lines: list[InvoiceLineIn] = Field(min_length=1, max_length=200)
    # M14-01 to M14-09 (migration 0252, docs/rules/M14-PU.md)
    service_contract_id: uuid.UUID | None = None
    reference_invoice_id: uuid.UUID | None = Field(
        default=None, description="Pflicht bei kind=credit_note: Ursprungsrechnung"
    )
    service_place: str | None = Field(default=None, max_length=200)
    issuer_vat_id: str | None = Field(default=None, max_length=20)
    issuer_tax_number: str | None = Field(default=None, max_length=30)
    attachment_document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    discount_amount: Decimal | None = Field(default=None, ge=0)
    prepaid_amount: Decimal | None = Field(default=None, ge=0)
    retention_amount: Decimal | None = Field(default=None, ge=0)
    reverse_charge: bool = False
    construction_withholding: bool = False
    input_tax_deductible: bool | None = None
    # M14-02 (migration 0291): structured links of the factual review.
    work_order_id: uuid.UUID | None = Field(default=None, description="Auftrag (Arbeitsauftrag)")
    resolution_id: uuid.UUID | None = Field(default=None, description="WEG Beschluss")
    plan_item_id: uuid.UUID | None = Field(
        default=None, description="Wirtschaftsplanposition (Budget)"
    )
    recurring_plan_id: uuid.UUID | None = Field(
        default=None, description="Rechnungsplan (Wiederkehr-Prüfung); leer lässt ihn unverändert"
    )


class InvoiceReviewedItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern="^(page|line|attachment)$")
    ref: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)


class InvoiceReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step: str = Field(pattern="^(completeness|factual|arithmetic_tax)$")
    result: str = Field(pattern="^(ok|query|objected|reservation)$")
    reason: str = Field(min_length=3, max_length=4000)
    scope: str | None = Field(default=None, max_length=2000)
    # M14-07: delegation proof (who delegated the step and why) and structured scope.
    delegated_by: uuid.UUID | None = None
    delegation_reason: str | None = Field(default=None, min_length=3, max_length=2000)
    reviewed_items: list[InvoiceReviewedItemIn] = Field(default_factory=list, max_length=500)


def _invoice_payload(body: InvoiceIn) -> dict[str, Any]:
    """Column values of the body; a credit note needs its original (M14-09, S711-02)."""
    if body.kind is InvoiceKind.CREDIT_NOTE and body.reference_invoice_id is None:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Eine Gutschrift braucht den Bezug zur Ursprungsrechnung.",
        )
    if body.service_from and body.service_to and body.service_to < body.service_from:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Leistungszeitraum: Ende liegt vor dem Beginn."
        )
    data = body.model_dump(exclude={"lines", "payee_iban"})
    data["attachment_document_ids"] = [str(d) for d in body.attachment_document_ids]
    if data.get("recurring_plan_id") is None:
        data.pop("recurring_plan_id", None)  # keeps the link of a generated invoice (M14-02)
    return data


def _invoice_out(
    inv: Invoice, lines: list[InvoiceLine], reviews: list[InvoiceReview]
) -> dict[str, Any]:
    return {
        "id": inv.id,
        "ledger_id": inv.ledger_id,
        "provider_contact_id": inv.provider_contact_id,
        "creditor_account_id": inv.creditor_account_id,
        "kind": inv.kind.value,
        "number": inv.number,
        "invoice_date": inv.invoice_date,
        "due_date": inv.due_date,
        "net": inv.net,
        "vat": inv.vat,
        "gross": inv.gross,
        "discount_percent": inv.discount_percent,
        "discount_until": inv.discount_until,
        "payee_iban_suffix": inv.payee_iban[-4:] if inv.payee_iban else None,
        "iban_confirmed": inv.iban_confirmed_by is not None,
        "document_id": inv.document_id,
        "deductions": inv.deductions,
        "review_status": inv.review_status.value,
        "posting_status": inv.posting_status.value,
        "released": inv.released_by is not None and inv.released_hash == invoices.payment_hash(inv),
        "duplicate_of_id": inv.duplicate_of_id,
        "supersedes_id": inv.supersedes_id,
        "journal_entry_id": inv.journal_entry_id,
        "version": inv.version,
        "findings": inv.findings,
        "service_from": inv.service_from,
        "service_to": inv.service_to,
        "order_reference": inv.order_reference,
        "service_contract_id": inv.service_contract_id,
        "work_order_id": inv.work_order_id,
        "resolution_id": inv.resolution_id,
        "plan_item_id": inv.plan_item_id,
        "recurring_plan_id": inv.recurring_plan_id,
        "reference_invoice_id": inv.reference_invoice_id,
        "service_place": inv.service_place,
        "issuer_vat_id": inv.issuer_vat_id,
        "issuer_tax_number": inv.issuer_tax_number,
        "attachment_document_ids": inv.attachment_document_ids,
        "discount_amount": inv.discount_amount,
        "discount_expected": invoice_checks.stated_discount(inv),
        "prepaid_amount": inv.prepaid_amount,
        "retention_amount": inv.retention_amount,
        "payable_amount": invoice_checks.payable_amount(
            inv, sum((Decimal(str(d.get("gross", "0"))) for d in inv.deductions), Decimal("0.00"))
        ),
        "reverse_charge": inv.reverse_charge,
        "construction_withholding": inv.construction_withholding,
        "input_tax_deductible": inv.input_tax_deductible,
        "mandatory_checklist": invoice_checks.mandatory_checklist(inv),
        "lines": [
            {
                "id": ln.id,  # M14-04: § 35a markers are set per line (tax_routers)
                "account_id": ln.account_id,
                "net": ln.net,
                "vat_percent": ln.vat_percent,
                "vat": ln.vat,
                "text": ln.text,
                "quantity": ln.quantity,
                "unit_price": ln.unit_price,
            }
            for ln in lines
        ],
        "reviews": [
            {
                "step": r.step,
                "result": r.result,
                "reason": r.reason,
                "user_id": r.user_id,
                "version": r.invoice_version,
                "decided_at": r.decided_at,
                "scope": r.scope,
                "delegated_by": r.delegated_by,
                "delegation_reason": r.delegation_reason,
                "reviewed_items": r.reviewed_items,
            }
            for r in reviews
        ],
    }


async def _invoice_full(session: AsyncSession, inv: Invoice) -> dict[str, Any]:
    return (await _invoices_full(session, [inv]))[0]


async def _invoices_full(session: AsyncSession, rows: Sequence[Invoice]) -> list[dict[str, Any]]:
    """Lines and reviews of all invoices in two queries (performance review 26.09.2026)."""
    if not rows:
        return []
    ids = [i.id for i in rows]
    lines: dict[uuid.UUID, list[InvoiceLine]] = {}
    for ln in (
        await session.scalars(
            select(InvoiceLine).where(InvoiceLine.invoice_id.in_(ids)).order_by(InvoiceLine.id)
        )
    ).all():
        lines.setdefault(ln.invoice_id, []).append(ln)
    reviews: dict[uuid.UUID, list[InvoiceReview]] = {}
    for r in (
        await session.scalars(
            select(InvoiceReview)
            .where(InvoiceReview.invoice_id.in_(ids))
            .order_by(InvoiceReview.decided_at)
        )
    ).all():
        reviews.setdefault(r.invoice_id, []).append(r)
    return [_invoice_out(i, lines.get(i.id, []), reviews.get(i.id, [])) for i in rows]


async def _invoice(session: AsyncSession, invoice_id: uuid.UUID) -> Invoice:
    inv = await session.get(Invoice, invoice_id, with_for_update=True)
    if inv is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    await _ensure_invoice_property_allowed(session, inv)
    return inv


async def _ensure_invoice_property_allowed(session: AsyncSession, inv: Invoice) -> None:
    """M2-02/S16-02: an invoice belongs to the property of its ledger; with a property
    assignment, invoices of other ledgers (or of ledgers without property) answer 404."""
    from mhvp.core.auth.scope import (
        ensure_session_legal_entity_allowed,
        session_allowed_legal_entity_ids,
    )

    # U15: the legal entity scope (tax advisor, A37) applies to invoices as well.
    if session_allowed_property_ids(session) is None and (
        session_allowed_legal_entity_ids(session) is None
    ):
        return
    ledger = await session.get(Ledger, inv.ledger_id)
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    ensure_session_property_allowed(session, ledger.property_id)
    ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)


async def _check_factual_links(session: AsyncSession, body: InvoiceIn) -> None:
    """M14-02: linked work order, resolution and plan item must exist in this tenant (RLS).
    U15-02: each link must also belong to the object of the invoice ledger: the work order
    to its property, the resolution to its community (legal entity), the plan item and the
    invoice plan to its ledger. Otherwise 422 ``MHVP-ACC-0008``."""
    from mhvp.hoa.models import EconomicPlan, PlanItem, Resolution
    from mhvp.tickets.models import WorkOrder

    ledger = await session.get(Ledger, body.ledger_id)
    for value, model, label in (
        (body.work_order_id, WorkOrder, "Auftrag"),
        (body.resolution_id, Resolution, "Beschluss"),
        (body.plan_item_id, PlanItem, "Wirtschaftsplanposition"),
        (body.recurring_plan_id, RecurringInvoicePlan, "Rechnungsplan"),
    ):
        if value is None:
            continue
        row = await session.get(model, value)
        if row is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"{label} nicht gefunden.")
        if ledger is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Buchungskreis nicht gefunden.")
        if isinstance(row, WorkOrder):
            same = ledger.property_id is not None and row.property_id == ledger.property_id
        elif isinstance(row, Resolution):
            same = row.legal_entity_id == ledger.legal_entity_id
        elif isinstance(row, PlanItem):
            plan = await session.get(EconomicPlan, row.plan_id)
            same = plan is not None and plan.ledger_id == ledger.id
        elif isinstance(row, RecurringInvoicePlan):
            same = row.ledger_id == ledger.id
        else:  # pragma: no cover - the tuple above lists every model
            same = False
        if not same:
            raise ProblemError(
                ErrorCodes.ACC_INVOICE_LINK_FOREIGN_OBJECT,
                detail=f"{label} gehört nicht zum Objekt der Rechnung.",
            )


class InvoiceFactualFindingOut(BaseModel):
    area: str
    code: str
    message: str


class InvoiceFactualBudgetOut(BaseModel):
    plan_item_id: uuid.UUID
    label: str
    year: int
    planned: Decimal
    booked_before: Decimal
    invoices_before: Decimal | None = None
    credit_notes_before: Decimal | None = None
    journal_lines_net: Decimal | None = None
    invoice: Decimal
    remaining: Decimal
    tolerance_limit: Decimal
    exceeded: bool


class InvoiceFactualResolutionOut(BaseModel):
    resolution_id: uuid.UUID
    number: int
    decided_on: date
    status: str
    subject: str
    subject_type: str | None = None
    effective: bool
    subject_matches_plan: bool | None = None


class InvoiceFactualCheckOut(BaseModel):
    invoice_id: uuid.UUID
    version: int
    findings: list[InvoiceFactualFindingOut]
    suggested_reviewer_user_id: uuid.UUID | None
    property_id: uuid.UUID | None
    price_tolerance_percent: Decimal
    quantity_tolerance_percent: Decimal
    automatic_release: bool = False
    budget: InvoiceFactualBudgetOut | None = None
    resolution: InvoiceFactualResolutionOut | None = None


class InvoiceCheckSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    price_tolerance_percent: Decimal = Field(ge=0, le=100, decimal_places=4)
    quantity_tolerance_percent: Decimal = Field(ge=0, le=100, decimal_places=4)


class InvoiceCheckSettingOut(BaseModel):
    price_tolerance_percent: Decimal
    quantity_tolerance_percent: Decimal


SETTINGS_UPDATE = require_permission("tenant_settings:update")


@router.get(
    "/invoices/{invoice_id}/factual-check",
    summary="Sachliche Prüfung als Befunde (Auftrag, Vertrag, Beschluss, Budget, Wiederkehr)",
    response_model=InvoiceFactualCheckOut,
)
async def invoice_factual_check(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """M14-02 (PÜ02): findings and the proposed responsible reviewer; never a release."""
    from mhvp.accounting import invoice_factual

    async with tenant_tx(request, principal) as session:
        inv = await session.get(Invoice, invoice_id)
        if inv is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await _ensure_invoice_property_allowed(session, inv)
        tol = await invoice_factual.load_tolerances(session)
        result = await invoice_factual.factual_check(session, inv)
        contract = await invoice_checks.contract_findings(session, inv)
        payload = invoice_factual.result_payload(result, tol)
        payload["findings"] = [
            *({"area": "contract", "code": "contract", "message": m} for m in contract),
            *payload["findings"],
        ]
        return {"invoice_id": inv.id, "version": inv.version, **payload}


@router.get(
    "/invoice-check-settings",
    summary="Toleranzen der sachlichen Rechnungsprüfung",
    response_model=InvoiceCheckSettingOut,
)
async def get_invoice_check_settings(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from mhvp.accounting import invoice_factual

    async with tenant_tx(request, principal) as session:
        tol = await invoice_factual.load_tolerances(session)
        return {
            "price_tolerance_percent": tol.price_percent,
            "quantity_tolerance_percent": tol.quantity_percent,
        }


@router.put(
    "/invoice-check-settings",
    summary="Toleranzen der sachlichen Rechnungsprüfung setzen",
    response_model=InvoiceCheckSettingOut,
)
async def put_invoice_check_settings(
    body: InvoiceCheckSettingIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_UPDATE),
) -> dict[str, Any]:
    from mhvp.accounting.models import InvoiceCheckSetting

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(InvoiceCheckSetting).with_for_update())
        if row is None:
            row = InvoiceCheckSetting(tenant_id=principal.tenant_id, created_by=principal.user_id)
            session.add(row)
        row.price_tolerance_percent = body.price_tolerance_percent
        row.quantity_tolerance_percent = body.quantity_tolerance_percent
        row.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice_check_setting.updated",
            entity_type="tenant_settings",
            entity_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            payload={
                "price_tolerance_percent": str(body.price_tolerance_percent),
                "quantity_tolerance_percent": str(body.quantity_tolerance_percent),
            },
        )
        await session.flush()
        return {
            "price_tolerance_percent": row.price_tolerance_percent,
            "quantity_tolerance_percent": row.quantity_tolerance_percent,
        }


@router.post("/invoices", status_code=201, summary="Eingangsrechnung erfassen")
async def create_invoice(
    body: InvoiceIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _ledger(session, body.ledger_id)
        await _check_factual_links(session, body)
        inv = Invoice(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            **_invoice_payload(body),
        )
        await invoices.write(session, inv, [ln.model_dump() for ln in body.lines], body.payee_iban)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice.received",
            entity_type="invoice",
            entity_id=inv.id,
            actor_user_id=principal.user_id,
            payload={"ledger_id": str(inv.ledger_id), "number": inv.number},
        )
        return await _invoice_full(session, inv)


@router.put("/invoices/{invoice_id}", summary="Rechnung ändern (neue Version, Freigaben entfallen)")
async def update_invoice(
    invoice_id: uuid.UUID,
    body: InvoiceIn,
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        inv = await _invoice(session, invoice_id)
        check_if_match(if_match, inv.version)  # S12-04, optional
        if inv.posting_status is not PostingStatus.UNPOSTED:
            raise ProblemError(
                ErrorCodes.ACC_POSTED_IMMUTABLE,
                detail="Gebuchte Rechnungen werden per Storno korrigiert.",
            )
        before_iban = inv.payee_iban_fingerprint
        await _check_factual_links(session, body)
        for key, value in _invoice_payload(body).items():
            setattr(inv, key, value)
        inv.version += 1
        inv.review_status = ReviewStatus.OPEN  # reviews refer to the old version (PÜ05)
        await invoices.write(session, inv, [ln.model_dump() for ln in body.lines], body.payee_iban)
        if inv.payee_iban_fingerprint != before_iban:
            inv.iban_confirmed_by = None
            await invoices.evaluate(session, inv)
        # S69-02: a changed payment hash persists the fall back of the decisions.
        from mhvp.accounting import approval_decisions

        await approval_decisions.invalidate(
            session,
            "invoice",
            inv.id,
            current_hash=invoices.payment_hash(inv),
            reason="Rechnung geändert",
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice.updated",
            entity_type="invoice",
            entity_id=inv.id,
            actor_user_id=principal.user_id,
            payload={
                "version": inv.version,
                "payee_iban_changed": before_iban != inv.payee_iban_fingerprint,
            },
        )
        await session.flush()
        response.headers["ETag"] = etag_of(inv.version)
        return await _invoice_full(session, inv)


@router.get("/invoices/{invoice_id}", summary="Rechnung mit Prüfschritten")
async def get_invoice(
    invoice_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        inv = await session.get(Invoice, invoice_id)
        if inv is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await _ensure_invoice_property_allowed(session, inv)
        response.headers["ETag"] = etag_of(inv.version)
        return await _invoice_full(session, inv)


_INVOICE_FILTERS = {
    "ledger_id": Invoice.ledger_id,
    "provider_contact_id": Invoice.provider_contact_id,
    "creditor_account_id": Invoice.creditor_account_id,
    "kind": Invoice.kind,
    "review_status": Invoice.review_status,
    "posting_status": Invoice.posting_status,
    "payment_method": Invoice.payment_method,
    "e_invoice_format": Invoice.e_invoice_format,
    "service_contract_id": Invoice.service_contract_id,
    "invoice_date": Invoice.invoice_date,
    "due_date": Invoice.due_date,
}
_INVOICE_SORT = {
    "invoice_date": Invoice.invoice_date,
    "due_date": Invoice.due_date,
    "number": Invoice.number,
    "gross": Invoice.gross,
    "review_status": Invoice.review_status,
    "created_at": Invoice.created_at,
}


@router.get(
    "/invoices",
    summary="Rechnungseingang",
    responses=PAGE_HEADERS,
    response_model=list[dict[str, Any]],
    description=LIST_PARAMS_DOC + " include: creditor (Kreditor, Kontakt des Rechnungsstellers).",
    dependencies=[Depends(strict_query)],
)
async def list_invoices(
    request: Request,
    response: Response,
    ledger_id: uuid.UUID | None = None,
    review_status: ReviewStatus | None = None,
    limit: int = Query(default=500, ge=1, le=1000),
    page: int = Query(default=1, ge=1, description="Seite (ab 1), zusammen mit page_size"),
    page_size: int | None = Query(
        default=None,
        ge=1,
        le=1000,
        description="Einträge je Seite; ohne Angabe gilt limit (erste Seite)",
    ),
    params: ListParams = Depends(list_params),
    principal: TenantPrincipal = Depends(READ),
) -> Any:
    """Rechnungen, neueste zuerst. Paginierung wie ``GET /tickets`` (Kopfzeilen
    ``X-Total-Count``, ``X-Page``, ``X-Page-Size``), Antwort bleibt eine Liste."""
    includes = check_include(params, ("creditor",))
    async with tenant_tx(request, principal) as session:
        query = apply_sort(
            apply_filters(select(Invoice), params, _INVOICE_FILTERS),
            params,
            _INVOICE_SORT,
            (Invoice.invoice_date.desc(), Invoice.id.desc()),
        )
        if ledger_id:
            query = query.where(Invoice.ledger_id == ledger_id)
        if review_status:
            query = query.where(Invoice.review_status == review_status)
        allowed = session_allowed_property_ids(session)  # M2-02/S16-02
        if allowed is not None:
            query = query.where(
                Invoice.ledger_id.in_(
                    select(Ledger.id).where(Ledger.property_id.in_(list(allowed)))
                )
            )
        rows = await paginate(session, query, response, page=page, page_size=page_size, limit=limit)
        embedded: dict[str, Any] = {}
        if "creditor" in includes:
            from mhvp.contacts.models import Contact

            creditor_ids = {i.provider_contact_id for i in rows}
            creditors = (
                {
                    c.id: {"id": c.id, "display_name": c.display_name, "kind": c.kind}
                    for c in (
                        await session.scalars(select(Contact).where(Contact.id.in_(creditor_ids)))
                    ).all()
                }
                if creditor_ids
                else {}
            )
            embedded["creditor"] = lambda item: creditors.get(
                uuid.UUID(str(item["provider_contact_id"]))
            )
        return embed(await _invoices_full(session, rows), params, None, embedded, response=response)


@router.post(
    "/invoices/{invoice_id}/reviews", status_code=201, summary="Prüfschritt erfassen (PÜ05)"
)
async def review_invoice(
    invoice_id: uuid.UUID,
    body: InvoiceReviewIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        inv = await _invoice(session, invoice_id)
        if inv.posting_status is not PostingStatus.UNPOSTED:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Die Rechnung ist bereits gebucht.")
        if principal.user_id is None:
            raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Reviews need a person.")
        if (body.delegated_by is None) != (body.delegation_reason is None):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Delegation braucht delegierende Person und Vertretungsgrund.",
            )
        if body.delegated_by is not None and body.delegated_by == principal.user_id:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Eine Person kann nicht an sich selbst delegieren."
            )
        session.add(
            InvoiceReview(
                tenant_id=principal.tenant_id,
                invoice_id=inv.id,
                invoice_version=inv.version,
                user_id=principal.user_id,
                **body.model_dump(exclude={"reviewed_items"}),
                reviewed_items=[i.model_dump() for i in body.reviewed_items],
            )
        )
        await session.flush()
        reviews = list(
            (
                await session.scalars(
                    select(InvoiceReview).where(InvoiceReview.invoice_id == inv.id)
                )
            ).all()
        )
        before_status = inv.review_status
        inv.review_status = invoices.aggregate(reviews, inv.version)
        await session.flush()
        closed = (ReviewStatus.CLOSED_OK, ReviewStatus.CLOSED_WITH_RESERVATION)
        if inv.review_status in closed and before_status not in closed:
            # S12-01: factual review completed; posting and payment release stay separate.
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="invoice.approved",
                entity_type="invoice",
                entity_id=inv.id,
                actor_user_id=principal.user_id,
                payload={"version": inv.version, "review_status": inv.review_status.value},
            )
        return await _invoice_full(session, inv)


@router.post("/invoices/{invoice_id}/confirm-iban", summary="Abweichende IBAN gesondert bestätigen")
async def confirm_iban(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    """A changed IBAN is confirmed by a person other than the one who entered the invoice (PÜ04)."""
    async with tenant_tx(request, principal) as session:
        inv = await _invoice(session, invoice_id)
        if inv.payee_iban is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Keine IBAN auf der Rechnung.")
        if inv.created_by == principal.user_id or principal.is_platform_admin:
            raise ProblemError(
                ErrorCodes.GATE_FOUR_EYES,
                detail="Die Bestätigung muss eine andere Person vornehmen.",
            )
        inv.iban_confirmed_by = principal.user_id
        await invoices.evaluate(session, inv)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice.iban_confirmed",
            entity_type="invoice",
            entity_id=inv.id,
            actor_user_id=principal.user_id,
            payload={"iban_suffix": inv.payee_iban[-4:]},
        )
        await session.flush()
        return await _invoice_full(session, inv)


@router.post(
    "/invoices/{invoice_id}/release", summary="Rechnungsfreigabe (zweite Person, versionsgebunden)"
)
async def release_invoice(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        inv = await _invoice(session, invoice_id)
        if inv.review_status not in (ReviewStatus.CLOSED_OK, ReviewStatus.CLOSED_WITH_RESERVATION):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Die Prüfung ist nicht abgeschlossen.")
        if inv.created_by == principal.user_id or principal.is_platform_admin:
            raise ProblemError(
                ErrorCodes.GATE_FOUR_EYES, detail="Die Freigabe muss eine andere Person erteilen."
            )
        if any("IBAN weicht" in f for f in inv.findings):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Abweichende IBAN ist nicht bestätigt.")
        release_hash = invoices.payment_hash(inv)
        inv.released_by, inv.released_hash = principal.user_id, release_hash
        # S69-02: central decision bound to the payment hash; older ones fall back.
        from mhvp.accounting import approval_decisions

        await approval_decisions.invalidate(
            session, "invoice", inv.id, current_hash=release_hash, reason="Rechnung geändert"
        )
        if principal.user_id is not None:
            await approval_decisions.record(
                session,
                tenant_id=inv.tenant_id,
                subject_type="invoice",
                subject_id=inv.id,
                step="release",
                user_id=principal.user_id,
                snapshot_hash=release_hash,
            )
        # M14-03 (mhvp.accounting.tax): records whether the releaser's role limit is exceeded;
        # the posting then needs a second approval by a third person. Off by default.
        exceeded = await tax.second_approval_required_for_release(session, inv, principal.roles)
        await tax.mark_second_approval_required(session, inv, exceeded)
        await session.flush()
        return await _invoice_full(session, inv)


@router.post("/invoices/{invoice_id}/post", summary="Rechnung buchen (Kreditor, offener Posten)")
async def post_invoice(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        inv = await _invoice(session, invoice_id)
        entry = await invoices.post(session, inv, principal.user_id)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice.posted",
            entity_type="invoice",
            entity_id=inv.id,
            actor_user_id=principal.user_id,
            payload={"journal_entry_id": str(entry.id)},
        )
        return await _invoice_full(session, inv)


@router.get("/invoices/{invoice_id}/discount", summary="Skonto zum Zahltag")
async def invoice_discount(
    invoice_id: uuid.UUID,
    pay_date: date,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        inv = await session.get(Invoice, invoice_id)
        if inv is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        value = invoices.discount(inv, pay_date)
        # PÜ03: prepayments and the security retention reduce the amount to pay (M14-04).
        base = invoice_checks.payable_amount(inv, Decimal("0.00"))
        return {"discount": value, "payable": base - value}


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ledger_id: uuid.UUID
    provider_contact_id: uuid.UUID
    account_id: uuid.UUID
    gross: Decimal = Field(gt=0)
    interval_months: int = Field(default=1, ge=1, le=12)
    start_date: date
    end_date: date | None = None
    text: str = Field(min_length=1, max_length=300)
    # M14-01 (migration 0252): contract link, order reference and VAT rate of the plan.
    service_contract_id: uuid.UUID | None = None
    order_reference: str | None = Field(default=None, max_length=100)
    vat_percent: Decimal = Field(default=Decimal(0), ge=0, le=100)
    # GA03-07: request for automatic posting; default off, needs the tenant switch.
    auto_post: bool = False


@router.post("/recurring-invoices", status_code=201, summary="Rechnungsplan anlegen")
async def create_plan(
    body: PlanIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, body.ledger_id)
        account = await _get(session, LedgerAccount, body.account_id)
        if account.ledger_id != ledger.id:
            raise ProblemError(ErrorCodes.ACC_WRONG_ENTITY)
        await creditor_routers.check_contract(
            session, body.service_contract_id, body.provider_contact_id
        )
        await creditor_routers.check_auto_post(session, body.auto_post)
        plan = RecurringInvoicePlan(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            next_due=body.start_date,
            anchor_day=body.start_date.day,
            **body.model_dump(),
        )
        session.add(plan)
        await session.flush()
        return {"id": plan.id, "next_due": plan.next_due}


@router.post(
    "/recurring-invoices/{plan_id}/generate",
    status_code=201,
    summary="Fällige Dauerrechnung als Entwurf erzeugen",
)
async def generate_plan(
    plan_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """Next due recurring invoice as unreviewed draft; nothing is posted automatically.

    GAA-06 (rule 0.1.4): conservative gate behaviour like the rent invoices. The number is a
    plan draft number (``PLAN-...``) and never comes from a ledger or MR number range. While
    G1 is closed the result is flagged as draft; in the tenant numbering mode
    ``reject_when_g1_closed`` (AC03-01, open question AC03-01) the route refuses (G1).
    """
    from mhvp.accounting import rent_invoice as ri

    async with tenant_tx(request, principal) as session:
        resolver = request.app.state.release_gate_resolver
        try:
            g1_open = (await resolver.is_open(principal.tenant_id, ReleaseGate.G1)) is True
        except Exception:
            g1_open = False
        if not g1_open and await ri.numbering_mode(session) == "reject_when_g1_closed":
            await ensure_release_gate_open(ReleaseGate.G1, principal.tenant_id, resolver)
        plan = await session.get(RecurringInvoicePlan, plan_id, with_for_update=True)
        if plan is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if plan.ended_at is not None or (
            plan.end_date is not None and plan.next_due > plan.end_date
        ):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Der Rechnungsplan ist beendet.")
        following = creditor_routers.next_due(plan)
        net, vat = creditor_routers.split_gross(plan.gross, plan.vat_percent)
        inv = Invoice(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            ledger_id=plan.ledger_id,
            provider_contact_id=plan.provider_contact_id,
            kind=InvoiceKind.RECURRING,
            # UUID v7: the leading hex digits are the creation time, the tail is random.
            number=f"PLAN-{plan.id.hex[-8:]}-{plan.next_due:%Y%m%d}",
            recurring_plan_id=plan.id,
            invoice_date=plan.next_due,
            due_date=plan.next_due,
            service_from=plan.next_due,
            service_to=following - timedelta(days=1),  # M14-01: full service period
            net=net,
            vat=vat,
            gross=plan.gross,
            order_reference=plan.order_reference,
            service_contract_id=plan.service_contract_id,
        )
        await invoices.write(
            session,
            inv,
            [
                {
                    "account_id": plan.account_id,
                    "net": net,
                    "vat_percent": plan.vat_percent,
                    "vat": vat,
                    "text": plan.text,
                }
            ],
            None,
        )
        plan.next_due = following
        await session.flush()
        out = await _invoice_full(session, inv)
        # GA03-07: the flag decides what the run may do. Off: draft only. On: the request is
        # recorded, but nothing is posted here (G1 and the 7.4 automatic switch decide later).
        out["draft_number"] = True
        out["g1_open"] = g1_open
        out["auto_post_requested"] = bool(plan.auto_post)
        out["auto_post_state"] = await creditor_routers.auto_post_state(
            session, request, principal, bool(plan.auto_post)
        )
        return out


# Dunning (M16, 7.5); only the leading system may dun ------------------------------------


class DunningSettingsIn(BaseModel):
    """Tenant default (``property_id`` None): ``levels`` required, an omitted
    ``threshold_amount`` means 0 and an omitted ``interest_enabled`` means off. Object
    override: every field may be ``null`` and then inherits the tenant default (M16-11); a
    level entry may leave out ``text``, ``fee_amount``, ``payment_days`` and ``letter_text``
    to inherit them from the tenant level of the same number."""

    model_config = ConfigDict(extra="forbid")
    property_id: uuid.UUID | None = None
    levels: list[dict[str, Any]] | None = Field(default=None, min_length=1, max_length=5)
    threshold_amount: Decimal | None = Field(default=None, ge=0)
    fee_from_level: int | None = Field(default=None, ge=1)
    interest_enabled: bool | None = None
    interest_base_rate: Decimal | None = Field(default=None, ge=0)
    interest_spread: Decimal | None = Field(default=None, ge=0)
    # Verzugsbeginn (M16-03): after_notice_30_days, calendar_due_date, after_reminder; null
    # means not decided (no default start shown, no interest computed).
    default_start_mode: str | None = Field(
        default=None, pattern="^(after_notice_30_days|calendar_due_date|after_reminder)$"
    )


class DunningSettingsPresetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: uuid.UUID | None = None
    interest_profile: str | None = Field(default=None, pattern="^(verbraucher|unternehmer)$")


class DunningRunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_date: date


class DunningLetterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    letter_date: date | None = None


class DunningLetterTextPreviewIn(BaseModel):
    """Text of one level with sample items for the settings form (A33). Only values given
    here are used: no fee without ``fee_amount``, no deadline without ``payment_days``."""

    model_config = ConfigDict(extra="forbid")
    level: int = Field(ge=1, le=9)
    text: str | None = Field(default=None, max_length=200)
    letter_text: str | None = Field(default=None, max_length=4000)
    fee_amount: Decimal | None = Field(default=None, ge=0)
    payment_days: int | None = Field(default=None, ge=0)
    letter_date: date | None = None


def _settings_status(eff: dunning.EffectiveSettings | None) -> str:
    if eff is None or not eff.levels:
        return "nicht eingerichtet"
    fees_configured = eff.fee_from_level is not None and any(
        lv.get("fee_amount") is not None for lv in eff.levels
    )
    interest_configured = eff.interest_enabled and eff.interest_base_rate is not None
    if fees_configured and interest_configured:
        return "gebuehr_und_zins_hinterlegt"
    if fees_configured:
        return "nur_gebuehr_hinterlegt"
    if interest_configured:
        return "nur_zins_hinterlegt"
    return "kein_betrag_hinterlegt"


async def _dunning_out(
    session: AsyncSession, run: DunningRun, cases: list[DunningCase]
) -> dict[str, Any]:
    """Each case carries ``highest_level`` of the ladder that applies to its ledger's property
    (object override or tenant default, M16-10), so clients never compare against the wrong
    ceiling."""
    ceiling: dict[uuid.UUID, int | None] = {}
    out = []
    for case in cases:
        if case.ledger_id not in ceiling:
            ledger = await session.get(Ledger, case.ledger_id)
            eff = await dunning.settings_for(session, ledger.property_id if ledger else None)
            ceiling[case.ledger_id] = (
                max((int(lv["level"]) for lv in eff.levels), default=None) if eff else None
            )
        out.append({**await _case_out(session, case), "highest_level": ceiling[case.ledger_id]})
    return {
        "id": run.id,
        "run_date": run.run_date,
        "status": run.status,
        "totals": run.totals,
        "cases": out,
    }


def _own_out(row: DunningSettings | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "levels": row.levels,
        "threshold_amount": row.threshold_amount,
        "fee_from_level": row.fee_from_level,
        "interest_enabled": row.interest_enabled,
        "interest_base_rate": row.interest_base_rate,
        "interest_spread": row.interest_spread,
        "default_start_mode": row.default_start_mode,
    }


def _dunning_settings_out(
    eff: dunning.EffectiveSettings | None, property_id: uuid.UUID | None
) -> dict[str, Any]:
    """Effective values (after inheritance) plus ``own`` (the stored row of this scope, or
    ``null``) and ``sources`` per field (``objekt`` or ``mandant``)."""
    if eff is None:
        return {
            "id": None,
            "property_id": property_id,
            "levels": [],
            "threshold_amount": Decimal("0.00"),
            "fee_from_level": None,
            "interest_enabled": False,
            "interest_base_rate": None,
            "interest_spread": None,
            "default_start_mode": None,
            "default_start_modes": dunning.DEFAULT_MODE_LABELS,
            "status": "nicht eingerichtet",
            "sources": {},
            "own": None,
            "tenant_default_exists": False,
        }
    own = eff.property_row if property_id is not None else eff.tenant_row
    return {
        "id": own.id if own is not None else None,
        "property_id": property_id,
        "levels": eff.levels,
        "threshold_amount": eff.threshold_amount,
        "fee_from_level": eff.fee_from_level,
        "interest_enabled": eff.interest_enabled,
        "interest_base_rate": eff.interest_base_rate,
        "interest_spread": eff.interest_spread,
        "default_start_mode": eff.default_start_mode,
        "default_start_modes": dunning.DEFAULT_MODE_LABELS,
        "status": _settings_status(eff),
        "sources": eff.sources,
        "own": _own_out(own),
        "tenant_default_exists": eff.tenant_row is not None,
    }


REMINDER_FEE_DETAIL = (
    "Die Zahlungserinnerung (Stufe 1) ist immer ohne Gebühr und ohne Zinsen: "
    "Gebühr ab Stufe muss mindestens 2 sein, die Gebühr der Stufe 1 muss leer oder 0,00 EUR sein."
)


def _check_levels(levels: list[dict[str, Any]], *, override: bool) -> None:
    for level in levels:
        if (
            set(level) - dunning.LEVEL_KEYS
            or "level" not in level
            or "min_days_overdue" not in level
            or (not override and "text" not in level)
        ):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    "Stufe: level, min_days_overdue, text, optional fee_amount, payment_days, "
                    "letter_text."
                ),
            )
        fee = level.get("fee_amount")
        if fee is not None and Decimal(str(fee)) < 0:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Mahngebühr darf nicht negativ sein.")
        if (
            int(level["level"]) == dunning.REMINDER_LEVEL
            and fee is not None
            and Decimal(str(fee)) != 0
        ):
            raise ProblemError(ErrorCodes.VALIDATION, detail=REMINDER_FEE_DETAIL)
        days = level.get("payment_days")
        if days is not None and int(days) < 0:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Zahlungsfrist darf nicht negativ sein."
            )
        if level.get("letter_text"):
            dunning_letters.check_letter_text(str(level["letter_text"]))
    numbers = [int(lv["level"]) for lv in levels]
    if len(numbers) != len(set(numbers)):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Jede Mahnstufe nur einmal.")


@router.get(
    "/dunning-settings", summary="Mahnstufen, Gebühren und Zins lesen (Mandant oder Objekt)"
)
async def get_dunning_settings(
    request: Request,
    property_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        eff = await dunning.settings_for(session, property_id)
        return _dunning_settings_out(eff, property_id)


@router.get(
    "/dunning-settings/overrides",
    summary="Objekte mit eigener Mahnstufen-Überschreibung",
    dependencies=[Depends(strict_query)],
)
async def list_dunning_overrides(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(DunningSettings)
                .where(DunningSettings.property_id.is_not(None))
                .order_by(DunningSettings.created_at)
            )
        ).all()
        return [
            {
                "id": r.id,
                "property_id": r.property_id,
                "overridden_fields": [
                    name for name in dunning.INHERITABLE_FIELDS if getattr(r, name) is not None
                ],
            }
            for r in rows
        ]


@router.put("/dunning-settings", summary="Mahnstufen, Gebühren (je Stufe, nur mit Betrag) und Zins")
async def put_dunning_settings(
    body: DunningSettingsIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    override = body.property_id is not None
    if not override and body.levels is None:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Mandantenvorgabe: Mahnstufen (levels) sind Pflicht."
        )
    if body.fee_from_level is not None and body.fee_from_level <= dunning.REMINDER_LEVEL:
        raise ProblemError(ErrorCodes.VALIDATION, detail=REMINDER_FEE_DETAIL)
    if body.levels is not None:
        _check_levels(body.levels, override=override)
    async with tenant_tx(request, principal) as session:
        tenant_row = await dunning.settings_row(session, None)
        if override and tenant_row is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Zuerst die Mandantenvorgabe anlegen, dann Objekte überschreiben.",
            )
        if override and all(getattr(body, name) is None for name in dunning.INHERITABLE_FIELDS):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Eine Objektüberschreibung braucht mindestens einen eigenen Wert.",
            )
        row = await dunning.settings_row(session, body.property_id)
        if row is None:
            row = DunningSettings(tenant_id=principal.tenant_id, property_id=body.property_id)
            session.add(row)
        row.levels = body.levels
        row.fee_from_level = body.fee_from_level
        row.interest_base_rate = body.interest_base_rate
        row.interest_spread = body.interest_spread
        row.default_start_mode = body.default_start_mode
        if override:
            row.threshold_amount = body.threshold_amount
            row.interest_enabled = body.interest_enabled
        else:  # the tenant default is always complete; omitted means 0 / off, never inherit
            row.threshold_amount = body.threshold_amount or Decimal("0")
            row.interest_enabled = bool(body.interest_enabled)
        await session.flush()
        eff = dunning.resolve(
            row if not override else tenant_row, row if override else None, body.property_id
        )
        if eff is not None and eff.interest_enabled and eff.interest_base_rate is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    "Verzugszins kann erst mit hinterlegtem Basiszinssatz aktiviert werden "
                    "(halbjährlich zu pflegen, kein Wert hinterlegt bis Eingabe)."
                ),
            )
        return _dunning_settings_out(eff, body.property_id)


@router.delete(
    "/dunning-settings",
    status_code=204,
    summary="Objektüberschreibung entfernen (Objekt erbt wieder die Mandantenvorgabe)",
)
async def delete_dunning_override(
    request: Request, property_id: uuid.UUID, principal: TenantPrincipal = Depends(APPROVE)
) -> Response:
    async with tenant_tx(request, principal) as session:
        row = await dunning.settings_row(session, property_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await session.delete(row)
        await session.flush()
    return Response(status_code=204)


@router.post(
    "/dunning-settings/presets",
    status_code=201,
    summary="Vorschlagswerte laden (Betreiberentscheidung 25.09.2026, V7)",
)
async def post_dunning_settings_presets(
    body: DunningSettingsPresetIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        tenant_row = await dunning.settings_row(session, None)
        if body.property_id is not None and tenant_row is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Zuerst die Mandantenvorgabe anlegen, dann Objekte überschreiben.",
            )
        row = await dunning.settings_row(session, body.property_id)
        if row is None:
            row = DunningSettings(tenant_id=principal.tenant_id, property_id=body.property_id)
            session.add(row)
        row.levels = dunning.preset_levels()
        row.fee_from_level = 2  # ab der 1. Mahnung (V7)
        row.interest_enabled = False if body.property_id is None else None
        row.interest_base_rate = None
        if body.property_id is None and row.threshold_amount is None:
            row.threshold_amount = Decimal("0")
        if body.interest_profile:
            row.interest_spread = Decimal(dunning.interest_spread_presets()[body.interest_profile])
        await session.flush()
        eff = dunning.resolve(
            tenant_row if body.property_id is not None else row,
            row if body.property_id is not None else None,
            body.property_id,
        )
        return {
            **_dunning_settings_out(eff, body.property_id),
            "note": (
                "Vorschlagswerte laut Betreiberentscheidung 25.09.2026 (V7, teilweise "
                "entschieden). Gebührenbeträge und Basiszinssatz bleiben leer, bis der "
                "Betreiber sie einträgt; rechtliche Prüfung der Gebührenhöhe und Grundlage "
                "steht aus."
            ),
        }


@router.post(
    "/dunning-settings/letter-preview",
    summary="Textbaustein einer Mahnstufe mit Beispielposten (A33, nur Text, kein Versand)",
)
async def dunning_letter_text_preview(
    body: DunningLetterTextPreviewIn,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """Standard text or the given ``letter_text`` of a level, rendered with sample items;
    placeholders are checked (422 on unknown ones). No bank account is passed: which account
    may appear in a letter is an open operator decision (M16-13)."""
    if body.letter_text:
        dunning_letters.check_letter_text(body.letter_text)
    return dunning_letters.sample_preview(
        level=body.level,
        level_text=body.text,
        letter_text=body.letter_text,
        fee_amount=body.fee_amount,
        payment_days=body.payment_days,
        letter_date=body.letter_date or local_today(),
    )


@router.post("/dunning-runs", status_code=201, summary="Mahnlauf: Vorschau")
async def dunning_preview(
    body: DunningRunIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        run = await dunning.preview(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            run_date=body.run_date,
        )
        cases = list(
            (await session.scalars(select(DunningCase).where(DunningCase.run_id == run.id))).all()
        )
        return await _dunning_out(session, run, cases)


_DUNNING_RUN_LIST = ListSpec(
    filters={"status": DunningRun.status, "run_date": DunningRun.run_date},
    sort={"run_date": DunningRun.run_date, "created_at": DunningRun.created_at},
)


@router.get("/dunning-runs", summary="Mahnläufe (neueste zuerst)")
async def dunning_runs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
    params: ListParams = Depends(_DUNNING_RUN_LIST.dependency),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        runs = (
            await session.scalars(
                _DUNNING_RUN_LIST.apply(
                    select(DunningRun),
                    params,
                    (DunningRun.run_date.desc(), DunningRun.created_at.desc(), DunningRun.id),
                ).limit(limit)
            )
        ).all()
        return [
            {"id": r.id, "run_date": r.run_date, "status": r.status, "totals": r.totals}
            for r in runs
        ]


@router.get("/dunning-runs/{run_id}", summary="Mahnlauf")
async def dunning_run(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        run = await session.get(DunningRun, run_id)
        if run is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        cases = list(
            (await session.scalars(select(DunningCase).where(DunningCase.run_id == run.id))).all()
        )
        return await _dunning_out(session, run, cases)


@router.post(
    "/dunning-runs/{run_id}/approve", summary="Mahnlauf freigeben (zweite Person, führendes System)"
)
async def dunning_approve(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Approvals need a person.")
    async with tenant_tx(request, principal) as session:
        run = await session.get(DunningRun, run_id, with_for_update=True)
        if run is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await dunning.approve(session, run, principal.user_id, principal.is_platform_admin)
        cases = list(
            (await session.scalars(select(DunningCase).where(DunningCase.run_id == run.id))).all()
        )
        return await _dunning_out(session, run, cases)


class DunningMarkSentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: str = Field(pattern="^(post|email|portal)$")
    # Zugang der Mahnung beim Schuldner, nur wenn bekannt (M16-03, Modus "erst nach Mahnung").
    received_on: date | None = None


class OpenItemNoticeIn(BaseModel):
    """Zugang der Zahlungsaufforderung (Rechnung, Abrechnung) beim Schuldner, von einer Person
    erfasst; Grundlage des Verzugsmodus "30 Tage nach Fälligkeit und Zugang" (M16-03)."""

    model_config = ConfigDict(extra="forbid")
    notice_received_on: date | None


async def _case_bank_out(session: AsyncSession, case: DunningCase) -> dict[str, Any] | None:
    """Payment account of the letter, masked in the API (the full IBAN is printed only in
    the letter itself, M16-13)."""
    from mhvp.contacts.validation import mask_iban
    from mhvp.properties.models import PropertyBankAccount

    if case.bank_account_id is None:
        return None
    row = await session.get(PropertyBankAccount, case.bank_account_id)
    if row is None:
        return None
    return {
        "id": row.id,
        "holder": row.holder,
        "iban_masked": mask_iban(row.iban),
        "legal_entity_id": row.legal_entity_id,
    }


async def _case_ledger_out(session: AsyncSession, case: DunningCase) -> dict[str, Any]:
    """Ledger, legal entity and property of the case, derived from ``ledger_id``
    (M16-15). ``property_id``/``property_number`` are ``null`` when the ledger has no
    property assigned (e.g. a legal entity level ledger without a single object)."""
    from mhvp.properties.models import Property

    property_id: uuid.UUID | None = None
    property_number: str | None = None
    ledger = await session.get(Ledger, case.ledger_id)
    legal_entity_id = ledger.legal_entity_id if ledger is not None else None
    if ledger is not None and ledger.property_id is not None:
        property_id = ledger.property_id
        prop = await session.get(Property, property_id)
        if prop is not None:
            property_number = prop.number
    return {
        "ledger_id": case.ledger_id,
        "legal_entity_id": legal_entity_id,
        "property_id": property_id,
        "property_number": property_number,
    }


async def _case_out(session: AsyncSession, case: DunningCase) -> dict[str, Any]:
    return {
        **await _case_ledger_out(session, case),
        "due_date": case.due_date,
        "default_start": case.default_start,
        "default_mode": case.default_mode,
        "default_mode_label": (
            dunning.DEFAULT_MODE_LABELS.get(case.default_mode) if case.default_mode else None
        ),
        "received_on": case.received_on,
        "bank_account": await _case_bank_out(session, case),
        "bank_warning": case.bank_warning,
        "id": case.id,
        "contract_id": case.contract_id,
        "debtor_account_id": case.debtor_account_id,
        "level": case.level,
        "total": case.total,
        "fee_amount": case.fee_amount,
        "interest_amount": case.interest_amount,
        "status": case.status,
        "reason": case.reason,
        "open_items": case.open_items,
        "fee_entry_id": case.fee_entry_id,
        "fee_invoice_draft_id": case.fee_invoice_draft_id,
        "delivery_channel": case.delivery_channel,
        "delivered_at": case.delivered_at,
        "letter_document_id": case.letter_document_id,
        "warnings": dunning.case_warnings(case),
        "interest_detail": case.interest_detail,
        "interest_entry_id": case.interest_entry_id,
        "interest_spread_suggestion": await _case_spread_suggestion(session, case),
        "check_hints": dunning.case_check_hints(case, local_today()),
        "delivery_proofs": [_proof_out(p) for p in await dunning.delivery_proofs(session, case.id)],
    }


async def _case_spread_suggestion(session: AsyncSession, case: DunningCase) -> dict[str, Any]:
    """Zinsaufschlag proposal from the debtor's consumer flag (M16-06), never applied."""
    from mhvp.contacts import recipients
    from mhvp.contacts.models import Contact
    from mhvp.contracts.models import Contract

    is_consumer: bool | None = None
    contract = await session.get(Contract, case.contract_id) if case.contract_id else None
    if contract is not None:
        debtor_id = await recipients.debtor_contact_id(session, contract.party_id)
        contact = await session.get(Contact, debtor_id) if debtor_id else None
        is_consumer = contact.is_consumer if contact is not None else None
    return dunning.spread_suggestion(is_consumer)


def _proof_out(proof: Any) -> dict[str, Any]:
    return {
        "id": proof.id,
        "case_id": proof.case_id,
        "kind": proof.kind,
        "proof_date": proof.proof_date,
        "reference": proof.reference,
        "document_id": proof.document_id,
        "note": proof.note,
        "created_by": proof.created_by,
        "created_at": proof.created_at,
    }


class DunningDeliveryProofIn(BaseModel):
    """Zustellnachweis zu einem versendeten Mahnfall (M16-01)."""

    model_config = ConfigDict(extra="forbid")
    kind: str = Field(
        pattern="^(registered_mail|postal_receipt|email_receipt|portal_receipt|other)$"
    )
    proof_date: date
    reference: str | None = Field(default=None, max_length=200)
    document_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


class DunningItemBlockIn(BaseModel):
    """Strukturierte Mahnsperre je Posten (M16-03)."""

    model_config = ConfigDict(extra="forbid")
    reason_code: str = Field(pattern="^(installment_plan|disputed|set_off|litigation|insolvency)$")
    note: str | None = Field(default=None, max_length=2000)


class DunningInterestRateIn(BaseModel):
    """Basiszinssatz mit Gültigkeitsbeginn und Quelle (M16-02)."""

    model_config = ConfigDict(extra="forbid")
    valid_from: date
    base_rate: Decimal = Field(ge=Decimal("-100"), le=Decimal("100"), decimal_places=8)
    source: str = Field(min_length=3, max_length=400)


@router.post(
    "/dunning-cases/{case_id}/delivery-proofs",
    status_code=201,
    summary="Zustellnachweis zum Mahnfall erfassen (Einschreiben, Post, E-Mail, Portal)",
)
async def dunning_add_delivery_proof(
    case_id: uuid.UUID,
    body: DunningDeliveryProofIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        case = await session.get(DunningCase, case_id, with_for_update=True)
        if case is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        proof = await dunning.add_delivery_proof(
            session,
            case,
            kind=body.kind,
            proof_date=body.proof_date,
            reference=body.reference,
            document_id=body.document_id,
            note=body.note,
            user_id=principal.user_id,
        )
        return _proof_out(proof)


@router.get(
    "/dunning-cases/{case_id}/delivery-proofs",
    summary="Zustellnachweise eines Mahnfalls",
    dependencies=[Depends(strict_query)],
)
async def dunning_list_delivery_proofs(
    case_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        if await session.get(DunningCase, case_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return [_proof_out(p) for p in await dunning.delivery_proofs(session, case_id)]


@router.post(
    "/dunning-cases/{case_id}/interest-draft",
    status_code=201,
    summary="Verzugszinsen als Sollstellungsentwurf anlegen (Freigabe über Vier-Augen-Buchung)",
)
async def dunning_interest_draft(
    case_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Needs a person.")
    async with tenant_tx(request, principal) as session:
        case = await session.get(DunningCase, case_id, with_for_update=True)
        if case is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        entry = await dunning.create_interest_draft(session, case, principal.user_id)
        return {
            "case_id": case.id,
            "entry_id": entry.id,
            "status": entry.status,
            "amount": case.interest_amount,
            "interest_detail": case.interest_detail,
            "hinweis": (
                "Entwurf, keine Buchung. Freigabe über die Vier-Augen-Buchung, nur mit "
                "geöffnetem G1; Zinssatz und Anspruchsgrundlage durch Rechtsanwalt prüfen."
            ),
        }


def _block_out(block: Any) -> dict[str, Any]:
    return {
        "id": block.id,
        "open_item_id": block.open_item_id,
        "reason_code": block.reason_code,
        "reason_label": dunning.BLOCK_REASON_LABELS.get(block.reason_code),
        "note": block.note,
        "active": block.released_at is None,
        "created_by": block.created_by,
        "created_at": block.created_at,
        "released_at": block.released_at,
        "released_by": block.released_by,
    }


@router.post(
    "/open-items/{open_item_id}/dunning-blocks",
    status_code=201,
    summary="Mahnsperre je Posten setzen (Ratenplan, bestritten, Aufrechnung, Prozess, Insolvenz)",
)
async def dunning_block_create(
    open_item_id: uuid.UUID,
    body: DunningItemBlockIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    from mhvp.accounting.models import DunningItemBlock

    async with tenant_tx(request, principal) as session:
        if await session.get(OpenItem, open_item_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        block = DunningItemBlock(
            tenant_id=principal.tenant_id,
            open_item_id=open_item_id,
            reason_code=body.reason_code,
            note=body.note,
            created_by=principal.user_id,
        )
        session.add(block)
        await session.flush()
        return _block_out(block)


@router.get(
    "/dunning-blocks", summary="Mahnsperren je Posten", dependencies=[Depends(strict_query)]
)
async def dunning_block_list(
    request: Request,
    open_item_id: uuid.UUID | None = None,
    active: bool | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    from mhvp.accounting.models import DunningItemBlock

    async with tenant_tx(request, principal) as session:
        query = select(DunningItemBlock).order_by(DunningItemBlock.created_at.desc())
        if open_item_id is not None:
            query = query.where(DunningItemBlock.open_item_id == open_item_id)
        if active is not None:
            query = query.where(
                DunningItemBlock.released_at.is_(None)
                if active
                else DunningItemBlock.released_at.is_not(None)
            )
        return [_block_out(b) for b in (await session.scalars(query.limit(500))).all()]


@router.post("/dunning-blocks/{block_id}/release", summary="Mahnsperre je Posten aufheben")
async def dunning_block_release(
    block_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    from datetime import UTC, datetime

    from mhvp.accounting.models import DunningItemBlock

    async with tenant_tx(request, principal) as session:
        block = await session.get(DunningItemBlock, block_id, with_for_update=True)
        if block is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if block.released_at is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Die Sperre ist bereits aufgehoben.")
        block.released_at = datetime.now(UTC)
        block.released_by = principal.user_id
        block.updated_by = principal.user_id
        await session.flush()
        return _block_out(block)


def _rate_out(rate: Any) -> dict[str, Any]:
    return {
        "id": rate.id,
        "valid_from": rate.valid_from,
        "base_rate": rate.base_rate,
        "source": rate.source,
        "created_by": rate.created_by,
        "created_at": rate.created_at,
    }


@router.get(
    "/dunning-interest-rates",
    summary="Basiszinssätze mit Gültigkeitszeitraum",
    dependencies=[Depends(strict_query)],
)
async def dunning_interest_rates(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    from mhvp.accounting.models import DunningInterestRate

    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(DunningInterestRate).order_by(DunningInterestRate.valid_from)
            )
        ).all()
        out = [_rate_out(r) for r in rows]
        for idx, item in enumerate(out):
            nxt = rows[idx + 1].valid_from if idx + 1 < len(rows) else None
            item["valid_to"] = nxt - timedelta(days=1) if nxt else None
        return out


@router.post(
    "/dunning-interest-rates",
    status_code=201,
    summary="Basiszinssatz ab Gültigkeitsbeginn mit Quelle erfassen",
)
async def dunning_interest_rate_create(
    body: DunningInterestRateIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    from mhvp.accounting.models import DunningInterestRate

    async with tenant_tx(request, principal) as session:
        exists = await session.scalar(
            select(DunningInterestRate).where(DunningInterestRate.valid_from == body.valid_from)
        )
        if exists is not None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Für diesen Gültigkeitsbeginn ist bereits ein Satz erfasst.",
            )
        rate = DunningInterestRate(
            tenant_id=principal.tenant_id,
            valid_from=body.valid_from,
            base_rate=body.base_rate,
            source=body.source,
            created_by=principal.user_id,
        )
        session.add(rate)
        await session.flush()
        return _rate_out(rate)


@router.post(
    "/dunning-cases/{case_id}/mark-sent",
    summary="Mahnung als versendet markieren (M16-09: nur so kann die Stufe steigen)",
)
async def dunning_mark_sent(
    case_id: uuid.UUID,
    body: DunningMarkSentIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Needs a person.")
    async with tenant_tx(request, principal) as session:
        case = await session.get(DunningCase, case_id, with_for_update=True)
        if case is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await dunning.mark_sent(
            session, case, body.channel, principal.user_id, received_on=body.received_on
        )
        return await _case_out(session, case)


@router.patch(
    "/open-items/{open_item_id}/notice-received",
    summary="Zugang der Zahlungsaufforderung beim Schuldner erfassen (Verzugsmodus M16-03)",
)
async def open_item_notice_received(
    open_item_id: uuid.UUID,
    body: OpenItemNoticeIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        item = await session.get(OpenItem, open_item_id, with_for_update=True)
        if item is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        item.notice_received_on = body.notice_received_on
        await session.flush()
        return {
            "id": item.id,
            "due_date": item.due_date,
            "notice_received_on": item.notice_received_on,
        }


async def _letter_pdf(
    session: AsyncSession, request: Request, case_id: uuid.UUID, letter_date: date | None
) -> tuple[DunningCase, dunning_letters.LetterDraft, bytes]:
    from mhvp.documents import services as doc_services
    from mhvp.documents.blobs import BlobStore

    case = await session.get(DunningCase, case_id)
    if case is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    head = await doc_services.letterhead(session, BlobStore(request.app.state.settings))
    draft = await dunning_letters.build(session, case, head, letter_date or local_today())
    return case, draft, dunning_letters.render(head, draft)


@router.post(
    "/dunning-cases/{case_id}/letter-preview",
    summary="Mahnschreiben als PDF-Entwurf (Vorschau, nicht abgelegt, kein Versand)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def dunning_letter_preview(
    case_id: uuid.UUID,
    request: Request,
    body: DunningLetterIn | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    async with tenant_tx(request, principal) as session:
        _, draft, pdf = await _letter_pdf(
            session, request, case_id, body.letter_date if body else None
        )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{quote(draft.filename)}"',
        },
    )


@router.post(
    "/dunning-cases/{case_id}/letter",
    status_code=201,
    summary="Mahnschreiben als PDF-Entwurf erzeugen und ablegen (kein Versand)",
)
async def dunning_letter_create(
    case_id: uuid.UUID,
    request: Request,
    body: DunningLetterIn | None = None,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        case, draft, pdf = await _letter_pdf(
            session, request, case_id, body.letter_date if body else None
        )
        from mhvp.documents.blobs import BlobStore

        document_id = await dunning_letters.store(
            session,
            BlobStore(request.app.state.settings),
            case=case,
            draft=draft,
            pdf=pdf,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
        )
        return {
            **await _case_out(session, case),
            "letter_document_id": document_id,
            "hinweis": dunning_letters.DRAFT_LABEL,
            "letter_warnings": draft.warnings,
        }


@router.post(
    "/dunning-cases/{case_id}/letter/send",
    summary="Mahnschreiben versenden (gesperrt: G1 geschlossen, Versand nicht umgesetzt, M16-02)",
)
async def dunning_letter_send(
    case_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    """Locked on purpose (0.1.1, API first 0.1.4): the endpoint exists so that clients and
    jobs hit the same lock. G1 must be open for the tenant, and even then the dispatch path
    (postal or e-mail evidence, M16-02) is not released, so the request is always refused."""
    resolver: ReleaseGateResolver = request.app.state.release_gate_resolver
    await ensure_release_gate_open(ReleaseGate.G1, principal.tenant_id, resolver)
    raise ProblemError(
        ErrorCodes.CONFLICT,
        detail=(
            "Der Versand von Mahnschreiben ist nicht freigegeben (M16-02). Das Schreiben "
            "bleibt Entwurf; der Versand erfolgt außerhalb der Plattform und wird mit "
            '"Als versendet markieren" dokumentiert.'
        ),
        extensions={"locked": "dunning_letter_send", "case_id": str(case_id)},
    )


def _mahnbescheid_out(prep: Any) -> dict[str, Any]:
    return {
        "id": prep.id,
        "case_id": prep.case_id,
        "antragsteller_legal_entity_id": prep.antragsteller_legal_entity_id,
        "antragsgegner": prep.antragsgegner_snapshot,
        "hauptforderung": prep.hauptforderung,
        "nebenforderungen": prep.nebenforderungen,
        "zustelladresse": prep.zustelladresse,
        "aktenzeichen_intern": prep.aktenzeichen_intern,
        "status": prep.status,
        "hinweis": (
            "Vorbereitung, Prüfung durch Rechtsanwalt. Fristen sind nur Hinweise und zu prüfen; "
            "keine rechtliche Vollständigkeitsprüfung, keine Antragstellung durch die Plattform."
        ),
    }


@router.post(
    "/dunning-cases/{case_id}/mahnbescheid-vorbereitung",
    status_code=201,
    summary="Mahnbescheid vorbereiten (nach letzter Stufe)",
)
async def dunning_prepare_mahnbescheid(
    case_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        case = await session.get(DunningCase, case_id)
        if case is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        case_ledger = await session.get(Ledger, case.ledger_id)
        if case_ledger is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        settings = await dunning.settings_for(session, case_ledger.property_id)
        highest = max((int(lv["level"]) for lv in settings.levels), default=0) if settings else 0
        if case.level < highest:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Mahnbescheid nur nach der letzten Mahnstufe vorzubereiten.",
            )
        prep = await dunning.prepare_mahnbescheid(session, case, principal.user_id)
        return _mahnbescheid_out(prep)


@router.get(
    "/dunning-cases/{case_id}/mahnbescheid-vorbereitung",
    summary="Mahnbescheid-Vorbereitung (Export für Anwalt oder Online-Mahnantrag)",
)
async def dunning_get_mahnbescheid(
    case_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        prep = await session.scalar(
            select(DunningMahnbescheidPrep).where(DunningMahnbescheidPrep.case_id == case_id)
        )
        if prep is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return _mahnbescheid_out(prep)


async def _mahnbescheid_pdf(
    session: AsyncSession, request: Request, case_id: uuid.UUID, letter_date: date | None
) -> tuple[DunningCase, DunningMahnbescheidPrep, dunning_letters.LetterDraft, bytes]:
    """PDF of the stored preparation record (A31): it must exist first (POST
    ``mahnbescheid-vorbereitung``), so the export never precedes the data set."""
    from mhvp.documents import services as doc_services
    from mhvp.documents.blobs import BlobStore

    case = await session.get(DunningCase, case_id)
    if case is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    prep = await session.scalar(
        select(DunningMahnbescheidPrep).where(DunningMahnbescheidPrep.case_id == case.id)
    )
    if prep is None:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Zuerst die Mahnbescheid-Vorbereitung anlegen, dann den PDF-Export erzeugen.",
        )
    head = await doc_services.letterhead(session, BlobStore(request.app.state.settings))
    draft = await dunning_letters.build_mahnbescheid(
        session, case, prep, head, letter_date or local_today()
    )
    return case, prep, draft, dunning_letters.render(head, draft)


@router.post(
    "/dunning-cases/{case_id}/mahnbescheid-preview",
    summary="Mahnbescheid-Vorbereitung als PDF (Vorschau, nicht abgelegt, kein Antrag)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def dunning_mahnbescheid_preview(
    case_id: uuid.UUID,
    request: Request,
    body: DunningLetterIn | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    async with tenant_tx(request, principal) as session:
        _, _, draft, pdf = await _mahnbescheid_pdf(
            session, request, case_id, body.letter_date if body else None
        )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{quote(draft.filename)}"',
        },
    )


@router.post(
    "/dunning-cases/{case_id}/mahnbescheid",
    status_code=201,
    summary="Mahnbescheid-Vorbereitung als PDF erzeugen und ablegen (kein Antrag)",
)
async def dunning_mahnbescheid_create(
    case_id: uuid.UUID,
    request: Request,
    body: DunningLetterIn | None = None,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    from mhvp.documents.blobs import BlobStore

    async with tenant_tx(request, principal) as session:
        _, prep, draft, pdf = await _mahnbescheid_pdf(
            session, request, case_id, body.letter_date if body else None
        )
        document_id = await dunning_letters.store_mahnbescheid(
            session,
            BlobStore(request.app.state.settings),
            draft=draft,
            pdf=pdf,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
        )
        return {
            **_mahnbescheid_out(prep),
            "document_id": document_id,
            "hinweis": dunning_letters.MAHNBESCHEID_NOTICE,
        }


# Evaluations and exports (M18, 7.5, 7.7) -----------------------------------------------

EXPORT = require_permission("accounting:export")


@router.get("/ledgers/{ledger_id}/liquidity", summary="Liquiditätsvorschau 90 Tage")
async def liquidity(
    ledger_id: uuid.UUID,
    request: Request,
    as_of: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        # GAI-601: same property scope check as /reports/liquidity.
        reports.ensure_ledger_in_scope(session, ledger)
        return await reports.liquidity(session, ledger, as_of or local_today())


@router.get(
    "/ledgers/{ledger_id}/payments-by-debtor",
    summary="Zahlungen je Debitor",
    dependencies=[Depends(strict_query)],
)
async def payments_by_debtor(
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        return await reports.payments_by_debtor(
            session, await _ledger(session, ledger_id), start, end
        )


@router.get(
    "/ledgers/{ledger_id}/revenue",
    summary="Erträge je Erlöskonto",
    dependencies=[Depends(strict_query)],
)
async def revenue(
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        return await reports.revenue(session, await _ledger(session, ledger_id), start, end)


async def _ensure_not_demo_export(
    session: AsyncSession, principal: TenantPrincipal, what: str
) -> None:
    """AE36 (rule AE36-DEMO): a demo tenant takes no part in journal and DATEV exports."""
    from mhvp.platform.demo import ensure_not_demo

    await ensure_not_demo(session, principal.tenant_id, what)


@router.post(
    "/ledgers/{ledger_id}/exports/journal",
    status_code=201,
    summary="Journal-Export (CSV) mit Prüfsumme",
)
async def export_journal(
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    principal: TenantPrincipal = Depends(EXPORT),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _ensure_not_demo_export(session, principal, "Der Journal-Export")  # AE36
        ledger = await _ledger(session, ledger_id)
        data, rows = await reports.journal_csv(session, ledger, start, end)
        run = ExportRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            ledger_id=ledger.id,
            format="journal_csv",
            period_from=start,
            period_to=end,
            rows=rows,
            sha256=reports.checksum(data),
        )
        session.add(run)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="export_run.created",
            entity_type="export_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload={"format": run.format, "rows": rows},
        )
        await session.flush()
        return {"id": run.id, "rows": rows, "sha256": run.sha256, "content": data.decode("utf-8")}


@router.post(
    "/ledgers/{ledger_id}/exports/datev",
    status_code=201,
    summary="DATEV-Buchungsstapel (nur mit hinterlegten Beraterdaten)",
)
async def export_datev(
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    principal: TenantPrincipal = Depends(EXPORT),
) -> dict[str, Any]:
    """Emits the DATEV EXTF Buchungsstapel header only once consultant_number, client_number
    and chart_of_accounts are set (operator decision 25.09.2026, M18-01). Otherwise rejects with
    the existing message. Account numbers come from the operator's DATEV mapping (A36);
    missing mappings answer 409 MHVP-BILL-0008 with the list of accounts."""
    from mhvp.platform.models import ChartOfAccountsKind, TenantBillingSettings

    async with tenant_tx(request, principal) as session:
        await _ensure_not_demo_export(session, principal, "Der DATEV-Export")  # AE36
        ledger = await _ledger(session, ledger_id)
        settings = await session.scalar(
            select(TenantBillingSettings).where(
                TenantBillingSettings.tenant_id == principal.tenant_id
            )
        )
        if (
            settings is None
            or not settings.datev_consultant_number
            or not settings.datev_client_number
            or settings.datev_chart_of_accounts is ChartOfAccountsKind.UNSET
        ):
            raise ProblemError(
                ErrorCodes.DATEV_NOT_CONFIGURED,
                detail=(
                    "DATEV-Format und Berater-/Mandantennummern sind noch nicht "
                    "festgelegt (M18-01)."
                ),
            )
        data, rows, skipped = await reports.datev_csv(
            session,
            ledger,
            start,
            end,
            consultant_number=settings.datev_consultant_number,
            client_number=settings.datev_client_number,
            chart_of_accounts=settings.datev_chart_of_accounts.value,
            account_length=settings.datev_account_length,
            fiscal_year_start_month=settings.datev_fiscal_year_start_month,
        )
        # M18-01 Folgepunkt: Splitbuchungen ohne eindeutige Summenseite werden nicht still
        # weggelassen, sondern im Exportlog vermerkt (docs/rules/M18-06, zu prüfen durch
        # Steuerberater).
        note = "Kontenzuordnung angewendet"
        if skipped:
            note += (
                f"; {len(skipped)} Splitbuchung(en) nicht abbildbar und ausgelassen, "
                "siehe params.skipped_split_bookings"
            )
        run = ExportRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            ledger_id=ledger.id,
            format="datev_buchungsstapel",
            period_from=start,
            period_to=end,
            rows=rows,
            sha256=reports.checksum(data),
            # A36: the Konto field carries the operator's mapping (datev_account_mapping);
            # unmapped accounts stopped the export before this point (MHVP-BILL-0008).
            note=note,
            params={"skipped_split_bookings": skipped} if skipped else {},
            # M18-01: the written file is kept for the formal self check
            # (POST /accounting/datev/exports/{id}/check, mhvp.accounting.datev_check).
            content=data.decode("utf-8"),
        )
        session.add(run)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="export_run.created",
            entity_type="export_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload={"format": run.format, "rows": rows, "skipped": len(skipped)},
        )
        await session.flush()
        return {
            "id": run.id,
            "rows": rows,
            "sha256": run.sha256,
            "content": data.decode("utf-8"),
            "skipped_split_bookings": skipped,
        }


# Invoice intake (M14, manual actions only; no automatic polling, see docs/OPEN_QUESTIONS.md
# M14-05) -------------------------------------------------------------------------------------

intake_router = APIRouter(prefix="/invoices/intake", tags=["Buchhaltung"])


class PaperlessIntakeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paperless_document_id: int


@intake_router.post(
    "/paperless", status_code=202, summary="Beleg aus Paperless holen und Rechnung erfassen"
)
async def paperless_intake(
    body: PaperlessIntakeIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """Pulls one document by id from Paperless-ngx into the document store (read only client
    already used for the ticket/property DMS panels, M31) and starts extract_invoice on it. No
    automatic polling: this is a manual action per document (M14-05)."""
    from mhvp.ai.models import AiTask
    from mhvp.ai.routers import start_extraction_run
    from mhvp.documents import services as doc_services
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import DocumentSource
    from mhvp.documents.paperless_search import PaperlessSearchError

    async with tenant_tx(request, principal) as session:
        from mhvp.documents.routers import _paperless_client

        client = await _paperless_client(session)
        try:
            file = await client.fetch_file(body.paperless_document_id, "download")
        except PaperlessSearchError as exc:
            raise ProblemError(ErrorCodes.DMS_UNAVAILABLE, detail=str(exc)) from None
        finally:
            await client.aclose()
        filename = file.filename or f"paperless-{body.paperless_document_id}.pdf"
        document = await doc_services.store_document(
            session,
            BlobStore(request.app.state.settings),
            tenant_id=principal.tenant_id,
            data=file.content,
            title=filename,
            filename=filename,
            mime_type=file.content_type,
            source=DocumentSource.IMPORT,
            category_id=None,
            links=[],
            created_by=principal.user_id,
        )
        document_id = document.id
    run = await start_extraction_run(
        request,
        principal,
        AiTask.EXTRACT_INVOICE,
        [document_id],
        "Rechnung aus Paperless erfassen",
        "invoice",
        None,
    )
    return {"document_id": str(document_id), "run_id": str(run.id), "proposal_id": run.proposal_id}


# M14-01, M14-08: creditors and the rest of the plan lifecycle (mhvp.accounting.creditor_routers).
router.include_router(creditor_routers.router)
# S69-02, S69-04: approval decisions and open item balances (mhvp.accounting.control_routers).
router.include_router(control_routers.router)
# S711-02: credit note XRechnung with reference to the original (mhvp.accounting.xrechnung_credit).
router.include_router(xrechnung_credit.router)
# M13-05/M13-06: PDF invoice document and batch issue (mhvp.accounting.fee_documents).
from mhvp.accounting import fee_documents  # noqa: E402

router.include_router(fee_documents.router)
# M10-07: year end carry over as drafts (mhvp.accounting.year_carryover).
from mhvp.accounting import year_carryover  # noqa: E402

router.include_router(year_carryover.router)
# S13-03: ZUGFeRD / Factur-X hybrid of fee invoices (mhvp.accounting.zugferd).
from mhvp.accounting import zugferd  # noqa: E402

router.include_router(zugferd.router)
# AI03 (GAH-110, GAH-113): day count switch and Basiszinssatz hint of the default interest.
from mhvp.accounting import dunning_interest_routers  # noqa: E402

router.include_router(dunning_interest_routers.router)
