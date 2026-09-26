"""Own legal entity and ledger of the managing company (``LegalEntityKind.MANAGER``, A32).

The managing company (for the first tenant Hausverwaltung Müller GmbH) is a legal entity of
its own next to the GdWE, rental owners and SEV owners it manages (6.9.1, E01): its own
receivables (management fees, dunning fee invoices to the claim holders, M16) and its own
funds never mix with managed funds. The property flow only creates HOA, rental owner and
SEV owner entities, so this module offers the one-off setup step under Einstellungen,
Mandant: one MANAGER entity per tenant, one ledger with the default chart of accounts
(the template rows that apply to ``manager``), idempotent. The name comes from the tenant's
company master data (``tenant_settings.company.name``), never from a default.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.accounting.models import AccountCategory, AccountType, Ledger, LedgerAccount
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import Tenant, TenantSettings
from mhvp.properties.models import LegalEntity, LegalEntityKind

STATUS_SET_UP = "eingerichtet"
STATUS_NOT_SET_UP = "nicht_eingerichtet"


@dataclass
class ManagerEntityStatus:
    status: str
    name: str | None
    legal_entity_id: uuid.UUID | None
    ledger_id: uuid.UUID | None
    accounts_count: int
    created: bool = False


async def _manager_entity(session: AsyncSession) -> LegalEntity | None:
    row: LegalEntity | None = await session.scalar(
        select(LegalEntity)
        .where(LegalEntity.kind == LegalEntityKind.MANAGER)
        .order_by(LegalEntity.created_at)
        .limit(1)
    )
    return row


async def _status(session: AsyncSession, entity: LegalEntity | None) -> ManagerEntityStatus:
    if entity is None:
        return ManagerEntityStatus(STATUS_NOT_SET_UP, None, None, None, 0)
    ledger = await session.scalar(select(Ledger).where(Ledger.legal_entity_id == entity.id))
    count = 0
    if ledger is not None:
        count = int(
            await session.scalar(
                select(func.count())
                .select_from(LedgerAccount)
                .where(LedgerAccount.ledger_id == ledger.id)
            )
            or 0
        )
    return ManagerEntityStatus(
        STATUS_SET_UP if ledger is not None else STATUS_NOT_SET_UP,
        entity.name,
        entity.id,
        ledger.id if ledger is not None else None,
        count,
    )


async def status(session: AsyncSession) -> ManagerEntityStatus:
    return await _status(session, await _manager_entity(session))


async def company_name(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    """Name from the tenant master data: company name of the tenant settings, else the
    tenant name from provisioning. Nothing is invented; an empty name is refused."""
    settings = await session.scalar(select(TenantSettings))
    name = str((settings.company or {}).get("name") or "").strip() if settings else ""
    if not name:
        tenant = await session.get(Tenant, tenant_id)
        name = tenant.name.strip() if tenant is not None else ""
    if not name:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Der Name der verwaltenden Gesellschaft fehlt in den Mandantenstammdaten.",
        )
    return name[:400]


async def ensure(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID | None
) -> ManagerEntityStatus:
    """Create the MANAGER legal entity and its ledger once; repeated calls return the existing
    state (idempotent). A legal entity without ledger (older seed) only gets the ledger."""
    entity = await _manager_entity(session)
    created = False
    if entity is None:
        entity = LegalEntity(
            tenant_id=tenant_id,
            kind=LegalEntityKind.MANAGER,
            name=await company_name(session, tenant_id),
            property_id=None,
        )
        session.add(entity)
        await session.flush()
        created = True
    ledger = await session.scalar(select(Ledger).where(Ledger.legal_entity_id == entity.id))
    if ledger is None:
        template = await acc.default_template(session, tenant_id)
        ledger = await acc.create_ledger(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            legal_entity_id=entity.id,
            template=template,
            fiscal_year_start_month=1,
            migration_cutoff=None,
        )
        created = True
    elif not await session.scalar(
        select(LedgerAccount.id).where(LedgerAccount.ledger_id == ledger.id).limit(1)
    ):
        # An empty ledger from an earlier direct seed (no accounts, hence no postings) gets
        # the default chart of accounts once, so that the set up state is the same either way.
        template = await acc.default_template(session, tenant_id)
        for spec in template.accounts:
            if LegalEntityKind.MANAGER.value not in spec.get("applies_to", []):
                continue
            session.add(
                LedgerAccount(
                    tenant_id=tenant_id,
                    ledger_id=ledger.id,
                    number=spec["number"],
                    name=spec["name"],
                    category=AccountCategory(spec["category"]),
                    type=AccountType(spec["type"]),
                    statement_kind=spec.get("statement_kind", "none"),
                    allocation_category=spec.get("allocation_category", "none"),
                    vat_option=spec.get("vat_option", "none"),
                    relevant_for_cash_report=bool(spec.get("relevant_for_cash_report")),
                    is_system=True,
                )
            )
        ledger.template_id, ledger.template_version = template.id, template.version
        await session.flush()
        created = True
    if created:
        await emit(
            session,
            tenant_id=tenant_id,
            type="manager_entity.created",
            entity_type="legal_entity",
            entity_id=entity.id,
            actor_user_id=user_id,
            payload={"ledger_id": str(ledger.id), "name": entity.name},
        )
    result = await _status(session, entity)
    result.created = created
    return result
