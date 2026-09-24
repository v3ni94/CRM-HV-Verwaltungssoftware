"""Licence model, usage counters, price list, onboarding and G5 readiness (M27, 6.8, 18.0).

Platform tables without RLS (5.3): only platform administrators reach them. Usage counters
are operating metrics (counts and sums), never domain data. No price is seeded: prices are
an operator decision (M27-01). Readiness never opens a gate; G5 stays a per tenant flag."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from celery import shared_task
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    BigInteger,
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
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TimestampMixin
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
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

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    )
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_quota: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)
    price_per_unit: Mapped[Decimal] = mapped_column(MONEY, nullable=False)  # per unit and month
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


class UsageIn(LicensingBaseIn):
    month: date


@router.get("/price-list", summary="Preisliste")
async def price_list(
    request: Request, _: Principal = Depends(require_platform_admin)
) -> list[dict[str, Any]]:
    async with platform_transaction(sessions(request)) as session:
        rows = await session.scalars(
            select(PriceListEntry).order_by(PriceListEntry.module, PriceListEntry.valid_from)
        )
        return [
            {
                "module": r.module,
                "price_per_unit": r.price_per_unit,
                "valid_from": r.valid_from,
                "note": r.note,
            }
            for r in rows.all()
        ]


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
        return {"id": row.id, **body.model_dump()}


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
        if await session.get(Tenant, body.tenant_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        price = body.price_per_unit
        if price is None:
            price = await _price(session, body.module, body.valid_from)
        if price is None:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Kein Preis für Modul und Datum in der Preisliste."
            )
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
        "min_monthly_amount": r.min_monthly_amount,
    }


@router.get("/licenses", summary="Lizenzen eines Mandanten")
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
    from mhvp.platform.models import Membership, MembershipStatus
    from mhvp.properties.models import Unit

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


G5_EVIDENCE = (
    "Betriebsprüfung",
    "Datenschutzprüfung",
    "Sicherheitsprüfung mit Penetrationstest",
    "Leistungsumfang und Grenzen",
    "Verfahrensdokumentation",
    "Support- und Rückfallprozess",
)


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

    day = as_of or datetime.now(UTC).date()
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
    counter = await count_usage(factory, tenant_id, day)
    async with tenant_transaction(factory, tenant_id) as session:
        properties = int(await session.scalar(select(func.count(Property.id))) or 0)
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
        "g5_evidence": [{"item": e, "done": False} for e in G5_EVIDENCE],
        "g5_ready": False,
        "note": "G5-Nachweise sind manuell zu führen; der Status öffnet kein Gate.",
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
            ids = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            await count_usage(factory, tenant_id, month or datetime.now(UTC).date())
            counted += 1
    finally:
        await engine.dispose()
    return {"counted": counted}


@shared_task(name="mhvp.platform.usage_all")
def usage_all() -> dict[str, int]:
    import asyncio

    from mhvp.core.config import get_settings

    return asyncio.run(usage_all_once(get_settings()))


@router.get("/tenants/{tenant_id}/billing-preview", summary="Lizenzentgelt je Monat (Vorschau)")
async def billing_preview(
    tenant_id: uuid.UUID,
    month: date,
    request: Request,
    _: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    """Decided 24.09.2026 (M27-01): price per unit, module and month, optional minimum. Net
    only; VAT and invoicing of licence fees are open (M27-01). Units from the usage counter."""
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
    lines = []
    total = Decimal("0.00")
    for lic in sorted(licenses, key=lambda x: x.module):
        amount = (lic.price_per_unit * counter.units).quantize(Decimal("0.01"))
        minimum = lic.min_monthly_amount or Decimal("0.00")
        charged = max(amount, minimum)
        total += charged
        lines.append(
            {
                "module": lic.module,
                "units": counter.units,
                "price_per_unit": str(lic.price_per_unit),
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
        "note": "Nettovorschau ohne Umsatzsteuer; Rechnungsstellung offen (M27-01).",
    }
