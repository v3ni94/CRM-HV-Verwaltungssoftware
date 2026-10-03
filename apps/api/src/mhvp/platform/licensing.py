"""Licence model, usage counters, price list, onboarding and G5 readiness (M27, 6.8, 18.0).

Platform tables without RLS (5.3): only platform administrators reach them. Usage counters
are operating metrics (counts and sums), never domain data. No price is seeded: prices are
an operator decision (M27-01). Readiness never opens a gate; G5 stays a per tenant flag."""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from celery import shared_task
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.auth.principal import Principal, require_platform_admin, sessions
from mhvp.core.clock import local_today
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TimestampMixin
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate

MONEY = Numeric(14, 2)
RATE = Numeric(20, 8)
MODULES = ("core", "rental", "hoa", "accounting", "banking", "portal", "ai")


class PriceListEntry(IdMixin, TimestampMixin, Base):
    __tablename__ = "price_list_entry"
    __table_args__ = (UniqueConstraint("module", "valid_from"),)

    module: Mapped[str] = mapped_column(String(32), nullable=False)
    price_per_unit: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))


class License(IdMixin, TimestampMixin, Base):
    """Tenant, module, unit quota, validity, price per unit (6.8 license)."""

    __tablename__ = "license"
    # AP05 / GAL-106: period order (0462).
    __table_args__ = (
        CheckConstraint("valid_until IS NULL OR valid_until >= valid_from", name="period_order"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    )
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_quota: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)
    # Agreed price per unit and month; NULL means "from the pricing structure" (M27-04).
    price_per_unit: Mapped[Decimal | None] = mapped_column(MONEY)
    min_monthly_amount: Mapped[Decimal | None] = mapped_column(MONEY)


class UsageCounter(IdMixin, TimestampMixin, Base):
    """Units, users, AI cost, storage per tenant and month (6.8 usage_counter)."""

    __tablename__ = "usage_counter"
    __table_args__ = (UniqueConstraint("tenant_id", "month"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    users: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_cost_eur: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    storage_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)


class UsageCounterDaily(IdMixin, TimestampMixin, Base):
    """Daily snapshot of the usage counter for the history per tenant (M27-05)."""

    __tablename__ = "usage_counter_daily"
    __table_args__ = (UniqueConstraint("tenant_id", "day"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    users: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_cost_eur: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    storage_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)


router = APIRouter(prefix="/platform", tags=["platform"])


class LicensingBaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PriceIn(LicensingBaseIn):
    module: str = Field(pattern="^(" + "|".join(MODULES) + ")$")
    price_per_unit: Decimal = Field(ge=0, decimal_places=2)
    valid_from: date
    note: str | None = Field(default=None, max_length=500)


class LicenseIn(LicensingBaseIn):
    tenant_id: uuid.UUID
    module: str = Field(pattern="^(" + "|".join(MODULES) + ")$")
    unit_quota: int = Field(ge=0)
    valid_from: date
    valid_until: date | None = None
    price_per_unit: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    min_monthly_amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)


class LicensingPricePatch(LicensingBaseIn):
    price_per_unit: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    note: str | None = Field(default=None, max_length=500)


class LicensingLicensePatch(LicensingBaseIn):
    unit_quota: int | None = Field(default=None, ge=0)
    valid_until: date | None = None
    clear_valid_until: bool = False
    price_per_unit: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    use_structure_price: bool = False
    min_monthly_amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    clear_min_monthly_amount: bool = False


class LicensingLicenseEndIn(LicensingBaseIn):
    valid_until: date


class UsageIn(LicensingBaseIn):
    month: date


@router.get("/price-list", summary="Preisliste", dependencies=[Depends(strict_query)])
async def price_list(
    request: Request, _: Principal = Depends(require_platform_admin)
) -> list[dict[str, Any]]:
    async with platform_transaction(sessions(request)) as session:
        rows = await session.scalars(
            select(PriceListEntry).order_by(PriceListEntry.module, PriceListEntry.valid_from)
        )
        return [_price_out(r) for r in rows.all()]


def _price_out(r: PriceListEntry) -> dict[str, Any]:
    return {
        "id": r.id,
        "module": r.module,
        "price_per_unit": r.price_per_unit,
        "valid_from": r.valid_from,
        "note": r.note,
    }


async def sync_price_to_structure(session: AsyncSession, module: str) -> None:
    """Price history feeds the pricing structure (M27-04): the entry valid today sets the
    amount of the module add-on row. Core is priced by tier, never overwritten here."""
    from mhvp.platform.market_readiness import PricingPlanItem, ensure_pricing_structure

    if module == "core":
        return
    await ensure_pricing_structure(session)
    item = await session.scalar(
        select(PricingPlanItem).where(PricingPlanItem.code == f"module_{module}")
    )
    if item is None:
        return
    price = await _price(session, module, local_today())
    if price is not None:
        item.amount = price


@router.post("/price-list", status_code=201, summary="Preis je Modul und Einheit erfassen")
async def add_price(
    body: PriceIn, request: Request, _: Principal = Depends(require_platform_admin)
) -> dict[str, Any]:
    async with platform_transaction(sessions(request)) as session:
        exists = await session.scalar(
            select(PriceListEntry.id).where(
                PriceListEntry.module == body.module, PriceListEntry.valid_from == body.valid_from
            )
        )
        if exists:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Preis ab diesem Datum vorhanden.")
        row = PriceListEntry(**body.model_dump())
        session.add(row)
        await session.flush()
        await sync_price_to_structure(session, row.module)
        return {"id": row.id, **body.model_dump()}


@router.patch("/price-list/{entry_id}", summary="Preislisteneintrag ändern")
async def patch_price(
    entry_id: uuid.UUID,
    body: LicensingPricePatch,
    request: Request,
    _: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    """Only the price and note change; module and start date identify the entry (delete and
    recreate to move it). Existing licences keep their agreed price."""
    async with platform_transaction(sessions(request)) as session:
        row = await session.get(PriceListEntry, entry_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = body.model_dump(exclude_unset=True)
        if "price_per_unit" in data and data["price_per_unit"] is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Preis darf nicht leer sein.")
        for key, value in data.items():
            setattr(row, key, value)
        await session.flush()
        await sync_price_to_structure(session, row.module)
        return _price_out(row)


@router.delete("/price-list/{entry_id}", status_code=204, summary="Preislisteneintrag löschen")
async def delete_price(
    entry_id: uuid.UUID, request: Request, _: Principal = Depends(require_platform_admin)
) -> Response:
    async with platform_transaction(sessions(request)) as session:
        row = await session.get(PriceListEntry, entry_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        module = row.module
        await session.delete(row)
        await session.flush()
        await sync_price_to_structure(session, module)
    return Response(status_code=204)


async def _price(session: AsyncSession, module: str, day: date) -> Decimal | None:
    value = await session.scalar(
        select(PriceListEntry.price_per_unit)
        .where(PriceListEntry.module == module, PriceListEntry.valid_from <= day)
        .order_by(PriceListEntry.valid_from.desc())
        .limit(1)
    )
    return Decimal(value) if value is not None else None


@router.post("/licenses", status_code=201, summary="Lizenz anlegen")
async def create_license(
    body: LicenseIn, request: Request, _: Principal = Depends(require_platform_admin)
) -> dict[str, Any]:
    from mhvp.platform.models import Tenant

    if body.valid_until is not None and body.valid_until < body.valid_from:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Gültigkeit ungültig.")
    async with platform_transaction(sessions(request)) as session:
        licensed = await session.get(Tenant, body.tenant_id)
        if licensed is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if licensed.is_demo:  # AE36: demo tenants take no part in platform billing
            raise ProblemError(
                ErrorCodes.DEMO_TENANT_EXCLUDED,
                detail="Eine Lizenz ist für einen Demo-Mandanten ausgeschlossen (AE36).",
            )
        # Explicit price, else the price list entry valid at the start (agreed price). Without
        # both the licence follows the pricing structure (M27-04, price NULL).
        price = body.price_per_unit
        if price is None:
            price = await _price(session, body.module, body.valid_from)
        overlap = await session.scalar(
            select(License.id).where(
                License.tenant_id == body.tenant_id,
                License.module == body.module,
                or_(License.valid_until.is_(None), License.valid_until >= body.valid_from),
                *([License.valid_from <= body.valid_until] if body.valid_until else []),
            )
        )
        if overlap:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Überschneidende Lizenz vorhanden.")
        row = License(**(body.model_dump() | {"price_per_unit": price}))
        session.add(row)
        await session.flush()
        return _license_out(row)


def _license_out(r: License) -> dict[str, Any]:
    return {
        "id": r.id,
        "tenant_id": r.tenant_id,
        "module": r.module,
        "unit_quota": r.unit_quota,
        "valid_from": r.valid_from,
        "valid_until": r.valid_until,
        "price_per_unit": r.price_per_unit,
        "price_source": "license" if r.price_per_unit is not None else "structure",
        "min_monthly_amount": r.min_monthly_amount,
    }


async def _overlaps(session: AsyncSession, lic: License, valid_until: date | None) -> bool:
    found = await session.scalar(
        select(License.id).where(
            License.id != lic.id,
            License.tenant_id == lic.tenant_id,
            License.module == lic.module,
            or_(License.valid_until.is_(None), License.valid_until >= lic.valid_from),
            *([License.valid_from <= valid_until] if valid_until else []),
        )
    )
    return found is not None


@router.patch("/licenses/{license_id}", summary="Lizenz ändern")
async def patch_license(
    license_id: uuid.UUID,
    body: LicensingLicensePatch,
    request: Request,
    _: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    async with platform_transaction(sessions(request)) as session:
        lic = await session.get(License, license_id)
        if lic is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = body.model_dump(exclude_unset=True)
        valid_until = lic.valid_until
        if body.clear_valid_until:
            valid_until = None
        elif "valid_until" in data and body.valid_until is not None:
            valid_until = body.valid_until
        if valid_until is not None and valid_until < lic.valid_from:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Gültigkeit ungültig.")
        if await _overlaps(session, lic, valid_until):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Überschneidende Lizenz vorhanden.")
        lic.valid_until = valid_until
        if body.unit_quota is not None:
            lic.unit_quota = body.unit_quota
        if body.use_structure_price:
            lic.price_per_unit = None
        elif body.price_per_unit is not None:
            lic.price_per_unit = body.price_per_unit
        if body.clear_min_monthly_amount:
            lic.min_monthly_amount = None
        elif body.min_monthly_amount is not None:
            lic.min_monthly_amount = body.min_monthly_amount
        await session.flush()
        return _license_out(lic)


@router.post("/licenses/{license_id}/end", summary="Lizenz beenden (Gültigkeit setzen)")
async def end_license(
    license_id: uuid.UUID,
    body: LicensingLicenseEndIn,
    request: Request,
    _: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    """Ends a licence via ``valid_until``; licences are never deleted (billing trail)."""
    async with platform_transaction(sessions(request)) as session:
        lic = await session.get(License, license_id)
        if lic is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if body.valid_until < lic.valid_from:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Gültigkeit ungültig.")
        lic.valid_until = body.valid_until
        await session.flush()
        return _license_out(lic)


@router.get("/licenses", summary="Lizenzen eines Mandanten", dependencies=[Depends(strict_query)])
async def list_licenses(
    tenant_id: uuid.UUID, request: Request, _: Principal = Depends(require_platform_admin)
) -> list[dict[str, Any]]:
    async with platform_transaction(sessions(request)) as session:
        rows = await session.scalars(
            select(License).where(License.tenant_id == tenant_id).order_by(License.valid_from)
        )
        return [_license_out(r) for r in rows.all()]


async def count_usage(
    factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID, month: date
) -> UsageCounter:
    """Counts for one tenant and month (upsert). Units: non fictional units; users: active
    memberships; AI cost and storage: sums of the month and the stock at counting time."""
    from mhvp.ai.models import AiTaskRun
    from mhvp.documents.models import Document
    from mhvp.platform.demo import ensure_not_demo
    from mhvp.platform.models import Membership, MembershipStatus
    from mhvp.properties.models import Unit

    async with platform_transaction(factory) as session:
        await ensure_not_demo(session, tenant_id, "Die Nutzungszählung")
    start = month.replace(day=1)
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    async with tenant_transaction(factory, tenant_id) as session:
        units = int(
            await session.scalar(select(func.count(Unit.id)).where(Unit.is_fictional.is_(False)))
            or 0
        )
        ai = Decimal(
            await session.scalar(
                select(func.coalesce(func.sum(AiTaskRun.cost_eur), 0)).where(
                    AiTaskRun.created_at >= start, AiTaskRun.created_at < end
                )
            )
            or 0
        )
        storage = int(await session.scalar(select(func.coalesce(func.sum(Document.size), 0))) or 0)
    async with platform_transaction(factory) as session:
        users = int(
            await session.scalar(
                select(func.count(Membership.id)).where(
                    Membership.tenant_id == tenant_id,
                    Membership.status == MembershipStatus.ACTIVE,
                )
            )
            or 0
        )
        row = await session.scalar(
            select(UsageCounter).where(
                UsageCounter.tenant_id == tenant_id, UsageCounter.month == start
            )
        )
        if row is None:
            row = UsageCounter(tenant_id=tenant_id, month=start)
            session.add(row)
        row.units, row.users, row.ai_cost_eur, row.storage_bytes = units, users, ai, storage
        # Daily history (M27-05): one snapshot per day, only for the running month.
        today = local_today()
        if start == today.replace(day=1):
            snap = await session.scalar(
                select(UsageCounterDaily).where(
                    UsageCounterDaily.tenant_id == tenant_id, UsageCounterDaily.day == today
                )
            )
            if snap is None:
                snap = UsageCounterDaily(tenant_id=tenant_id, day=today)
                session.add(snap)
            snap.units, snap.users, snap.ai_cost_eur, snap.storage_bytes = (
                units,
                users,
                ai,
                storage,
            )
        await session.flush()
        session.expunge(row)
        return row


@router.post("/tenants/{tenant_id}/usage", summary="Nutzung zählen (Monat)")
async def usage(
    tenant_id: uuid.UUID,
    body: UsageIn,
    request: Request,
    _: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    row = await count_usage(sessions(request), tenant_id, body.month)
    return {
        "month": row.month,
        "units": row.units,
        "users": row.users,
        "ai_cost_eur": str(row.ai_cost_eur),
        "storage_bytes": row.storage_bytes,
    }


@router.get("/tenants/{tenant_id}/usage/history", summary="Nutzungsverlauf (Tag und Monat)")
async def usage_history(
    tenant_id: uuid.UUID,
    request: Request,
    days: int = 90,
    months: int = 12,
    _: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    """Daily snapshots of the last ``days`` days and the monthly counters (M27-05)."""
    from mhvp.platform.models import Tenant

    days = min(max(days, 1), 731)
    months = min(max(months, 1), 60)
    since = local_today() - timedelta(days=days)
    async with platform_transaction(sessions(request)) as session:
        if await session.get(Tenant, tenant_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        daily = (
            await session.scalars(
                select(UsageCounterDaily)
                .where(UsageCounterDaily.tenant_id == tenant_id, UsageCounterDaily.day >= since)
                .order_by(UsageCounterDaily.day)
            )
        ).all()
        monthly = (
            await session.scalars(
                select(UsageCounter)
                .where(UsageCounter.tenant_id == tenant_id)
                .order_by(UsageCounter.month.desc())
                .limit(months)
            )
        ).all()

    def out(day_key: str, r: Any) -> dict[str, Any]:
        return {
            day_key: getattr(r, day_key),
            "units": r.units,
            "users": r.users,
            "ai_cost_eur": str(r.ai_cost_eur),
            "storage_bytes": r.storage_bytes,
        }

    return {
        "daily": [out("day", r) for r in daily],
        "monthly": [out("month", r) for r in reversed(monthly)],
    }


@router.get("/tenants/{tenant_id}/readiness", summary="Onboarding- und G5-Status")
async def readiness(
    tenant_id: uuid.UUID,
    request: Request,
    as_of: date | None = None,
    _: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    """Checklist from counts and flags; the G5 evidence items are manual and stay open until
    the operator documents them (M27-02). A gate is only reported, never changed."""
    from mhvp.platform.models import Tenant
    from mhvp.properties.models import Property

    day = as_of or local_today()
    factory = sessions(request)
    async with platform_transaction(factory) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        licenses = (
            await session.scalars(
                select(License).where(
                    License.tenant_id == tenant_id,
                    License.valid_from <= day,
                    or_(License.valid_until.is_(None), License.valid_until >= day),
                )
            )
        ).all()
    # AE36: a demo tenant is not counted (no usage row, no billing); the page shows zeros.
    counter: Any = (
        SimpleNamespace(units=0, users=0)
        if tenant.is_demo
        else await count_usage(factory, tenant_id, day)
    )
    from mhvp.platform.market_readiness import evidence_checklist, missing_g5_evidence

    async with tenant_transaction(factory, tenant_id) as session:
        properties = int(await session.scalar(select(func.count(Property.id))) or 0)
        g5_items = [
            {"item": e["label"], "done": e["done"], "code": e["code"]}
            for e in await evidence_checklist(session, tenant_id)
        ]
        g5_ready = not await missing_g5_evidence(session, tenant_id)
    quota = sum(lic.unit_quota for lic in licenses if lic.module == "core")
    resolver = request.app.state.release_gate_resolver
    gates = {g.value: await resolver.is_open(tenant_id, g) for g in ReleaseGate}
    checklist = [
        {"item": "Lizenz Kernmodul gültig", "done": any(lic.module == "core" for lic in licenses)},
        {"item": "Einheiten im Kontingent", "done": bool(quota) and counter.units <= quota},
        {"item": "Benutzer angelegt", "done": counter.users > 0},
        {"item": "Objekte erfasst", "done": properties > 0},
    ]
    return {
        "tenant_id": tenant_id,
        "as_of": day,
        "checklist": checklist,
        "usage": {"units": counter.units, "users": counter.users, "unit_quota": quota},
        "gates": gates,
        "g5_evidence": g5_items,
        "g5_ready": g5_ready,
        "demo": tenant.is_demo,
        "note": "G5-Nachweise (M27-02) öffnen kein Gate; Freigabe nur über den Antrag G5.",
    }


async def usage_all_once(settings: Any, month: date | None = None) -> dict[str, int]:
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from mhvp.core.db.engine import create_session_factory
    from mhvp.platform.models import Tenant, TenantStatus

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    counted = 0
    try:
        async with platform_transaction(factory) as session:
            # AE36: demo tenants are not counted (rule AE36-DEMO).
            ids = list(
                await session.scalars(
                    select(Tenant.id).where(
                        Tenant.status == TenantStatus.ACTIVE, Tenant.is_demo.is_(False)
                    )
                )
            )
        for tenant_id in ids:
            await count_usage(factory, tenant_id, month or local_today())
            counted += 1
    finally:
        await engine.dispose()
    return {"counted": counted}


@shared_task(name="mhvp.platform.usage_all")
def usage_all() -> dict[str, int]:
    import asyncio

    from mhvp.core.config import get_settings

    return asyncio.run(usage_all_once(get_settings()))


def _tier_for(structure: list[Any], units: int) -> Any:
    """Active tier whose unit range contains ``units`` (M27-04); None when none matches."""
    for row in structure:
        if row.kind != "tier" or not row.active:
            continue
        if (row.min_units or 0) <= units and (row.max_units is None or units <= row.max_units):
            return row
    return None


def _in_trial(lic: License, trial: Any, last_day: date) -> bool:
    """A month is free when it ends within the trial phase counted from the licence start
    (assumption, ASSUMPTIONS M27-04); no trial row or no duration means no free month."""
    if trial is None or trial.trial_days is None or trial.trial_days <= 0:
        return False
    return last_day < lic.valid_from + timedelta(days=trial.trial_days)


@router.get("/tenants/{tenant_id}/billing-preview", summary="Lizenzentgelt je Monat (Vorschau)")
async def billing_preview(
    tenant_id: uuid.UUID,
    month: date,
    request: Request,
    _: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    """Decided 24.09.2026 (M27-01): price per unit, module and month, optional minimum. Net
    only; VAT and invoicing of licence fees are open (M27-01). Units from the usage counter.
    Since M27-04 one structure: an agreed licence price wins, otherwise the tier (core) or
    the module add-on of the pricing structure; trial months are not charged."""
    first = month.replace(day=1)
    last = date(first.year + (first.month == 12), first.month % 12 + 1, 1) - timedelta(days=1)
    factory = sessions(request)
    counter = await count_usage(factory, tenant_id, first)
    async with platform_transaction(factory) as session:
        licenses = (
            await session.scalars(
                select(License).where(
                    License.tenant_id == tenant_id,
                    License.valid_from <= last,
                    or_(License.valid_until.is_(None), License.valid_until >= first),
                )
            )
        ).all()
    from mhvp.platform.market_readiness import PricingPlanItem, ensure_pricing_structure

    async with platform_transaction(factory) as session:
        structure = await ensure_pricing_structure(session)
        session.expunge_all()
    tier = _tier_for(structure, counter.units)
    trial = next((r for r in structure if r.kind == "trial" and r.active), None)
    by_code = {r.code: r for r in structure}
    lines = []
    total = Decimal("0.00")
    incomplete = False
    for lic in sorted(licenses, key=lambda x: x.module):
        item: PricingPlanItem | None = (
            tier if lic.module == "core" else by_code.get(f"module_{lic.module}")
        )
        if lic.price_per_unit is not None:
            price, source = lic.price_per_unit, "license"
        elif item is not None and item.amount is not None and item.unit == "unit_month":
            price, source = item.amount, "structure"
        else:
            price, source = None, "structure_missing"
        in_trial = _in_trial(lic, trial, last)
        minimum = lic.min_monthly_amount or Decimal("0.00")
        if price is None:
            incomplete = True
            amount, charged = Decimal("0.00"), Decimal("0.00")
        else:
            amount = (price * counter.units).quantize(Decimal("0.01"))
            charged = Decimal("0.00") if in_trial else max(amount, minimum)
        total += charged
        lines.append(
            {
                "module": lic.module,
                "units": counter.units,
                "price_per_unit": str(price) if price is not None else None,
                "price_source": source,
                "tier": tier.code if lic.module == "core" and tier is not None else None,
                "trial": in_trial,
                "amount": str(amount),
                "minimum": str(minimum),
                "charged": str(charged),
                "over_quota": counter.units > lic.unit_quota,
            }
        )
    return {
        "month": first,
        "lines": lines,
        "net_total": str(total),
        "complete": not incomplete,
        "note": "Nettovorschau ohne Umsatzsteuer; Rechnungsstellung offen (M27-01).",
    }
