"""Market readiness for third party tenants (M27-01 to M27-03, 18 market readiness, gate G5).

Three product safeguards (Produktschutz, no legal duty claimed):

* M27-01 pricing structure: tiers by units, modules as add-ons and a trial phase are a
  configurable structure. No amount is seeded; every amount stays empty until the operator
  maintains it (``docs/OPEN_QUESTIONS.md`` M27-01). An offer is rendered as a PDF draft from the
  structure and carries "ENTWURF" and the list of missing amounts.
* M27-02 G5 evidence list: one checklist row per evidence item and tenant with a document link.
  Gate G5 can only be approved when every item is done and the approver is the superadmin
  (hook in ``mhvp.platform.routers._decide``). The list never opens a gate by itself.
* M27-03 onboarding and export: a platform administrator creates a third party tenant with legal
  entities, first administrator, CI settings, system roles and feature flags off, and receives
  a welcome mail draft (never sent). The tenant export (GDPR access and portability) is a ZIP
  with one JSON file per entity, produced under the tenant's RLS context after a four eyes
  approval by a second platform administrator.

``pricing_plan_item`` is a platform table without RLS (5.3). ``g5_evidence`` and
``tenant_export_request`` carry ``tenant_id`` and are tenant tables with RLS (ADR 0002): they
are read and written under ``tenant_transaction`` of the tenant in the path; only platform
administrators reach the endpoints.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    select,
    text,
)
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.auth.principal import Principal, require_platform_admin, sessions
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TimestampMixin
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate
from mhvp.platform import gates

MONEY = Numeric(14, 2)
router = APIRouter(prefix="/platform", tags=["platform"])

# ---------------------------------------------------------------------------------------
# M27-01 pricing structure
# ---------------------------------------------------------------------------------------

PRICING_KINDS = ("tier", "module", "trial")
PRICING_UNITS = ("unit_month", "month", "once", "days")

# Default structure (labels and unit ranges are an editable draft, ASSUMPTIONS M27-01);
# amounts are None on purpose and never seeded (rule 0.1.3).
DEFAULT_PRICING: tuple[dict[str, Any], ...] = (
    {"kind": "tier", "code": "tier_s", "label": "Stufe S", "min_units": 1, "max_units": 100},
    {"kind": "tier", "code": "tier_m", "label": "Stufe M", "min_units": 101, "max_units": 500},
    {"kind": "tier", "code": "tier_l", "label": "Stufe L", "min_units": 501, "max_units": 2000},
    {"kind": "tier", "code": "tier_xl", "label": "Stufe XL", "min_units": 2001, "max_units": None},
    {"kind": "module", "code": "module_rental", "label": "Zusatzmodul Vermietung"},
    {"kind": "module", "code": "module_hoa", "label": "Zusatzmodul WEG"},
    {"kind": "module", "code": "module_accounting", "label": "Zusatzmodul Buchhaltung"},
    {"kind": "module", "code": "module_banking", "label": "Zusatzmodul Banking"},
    {"kind": "module", "code": "module_portal", "label": "Zusatzmodul Portal"},
    {"kind": "module", "code": "module_ai", "label": "Zusatzmodul KI"},
    {"kind": "trial", "code": "trial", "label": "Testphase", "unit": "days"},
)


class PricingPlanItem(IdMixin, TimestampMixin, Base):
    """One row of the pricing structure: tier by units, module add-on or trial phase."""

    __tablename__ = "pricing_plan_item"

    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    min_units: Mapped[int | None] = mapped_column(Integer)
    max_units: Mapped[int | None] = mapped_column(Integer)
    # Net amount; None until the operator maintains it (M27-01). Never seeded.
    amount: Mapped[Decimal | None] = mapped_column(MONEY)
    unit: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unit_month", server_default="unit_month"
    )
    trial_days: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class PricingItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(pattern="^(" + "|".join(PRICING_KINDS) + ")$")
    code: str = Field(pattern=r"^[a-z0-9_]{2,32}$")
    label: str = Field(min_length=2, max_length=200)
    min_units: int | None = Field(default=None, ge=0)
    max_units: int | None = Field(default=None, ge=0)
    amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    unit: str = Field(default="unit_month", pattern="^(" + "|".join(PRICING_UNITS) + ")$")
    trial_days: int | None = Field(default=None, ge=0, le=3650)
    sort_order: int = 0


class PricingItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=2, max_length=200)
    min_units: int | None = Field(default=None, ge=0)
    max_units: int | None = Field(default=None, ge=0)
    amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    clear_amount: bool = False
    unit: str | None = Field(default=None, pattern="^(" + "|".join(PRICING_UNITS) + ")$")
    trial_days: int | None = Field(default=None, ge=0, le=3650)
    sort_order: int | None = None
    active: bool | None = None


def _pricing_out(row: PricingPlanItem) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "code": row.code,
        "label": row.label,
        "min_units": row.min_units,
        "max_units": row.max_units,
        "amount": str(row.amount) if row.amount is not None else None,
        "unit": row.unit,
        "trial_days": row.trial_days,
        "sort_order": row.sort_order,
        "active": row.active,
        "amount_missing": row.amount is None,
    }


async def ensure_pricing_structure(session: AsyncSession) -> list[PricingPlanItem]:
    """Create the default structure once (labels only, no amounts) and return all rows."""
    existing = {r.code: r for r in (await session.scalars(select(PricingPlanItem))).all()}
    for index, spec in enumerate(DEFAULT_PRICING):
        if spec["code"] not in existing:
            row = PricingPlanItem(
                kind=spec["kind"],
                code=spec["code"],
                label=spec["label"],
                min_units=spec.get("min_units"),
                max_units=spec.get("max_units"),
                unit=spec.get("unit", "unit_month"),
                sort_order=index * 10,
            )
            session.add(row)
            existing[row.code] = row
    await session.flush()
    rows = (
        await session.scalars(
            select(PricingPlanItem).order_by(PricingPlanItem.sort_order, PricingPlanItem.code)
        )
    ).all()
    return list(rows)


def _pricing_summary(rows: list[PricingPlanItem]) -> dict[str, Any]:
    missing = [r.code for r in rows if r.active and r.amount is None]
    return {
        "items": [_pricing_out(r) for r in rows],
        "complete": not missing,
        "missing_amounts": missing,
        "note": "Beträge sind vom Betreiber zu pflegen (M27-01); ohne Beträge nur Entwurf.",
    }


@router.get("/pricing", summary="Preisstruktur (Stufen, Zusatzmodule, Testphase)")
async def get_pricing(
    request: Request, _: Principal = Depends(require_platform_admin)
) -> dict[str, Any]:
    async with platform_transaction(sessions(request)) as session:
        return _pricing_summary(await ensure_pricing_structure(session))


@router.post("/pricing/items", status_code=201, summary="Preisstrukturzeile anlegen")
async def add_pricing_item(
    body: PricingItemIn, request: Request, principal: Principal = Depends(require_platform_admin)
) -> dict[str, Any]:
    _check_range(body.min_units, body.max_units)
    async with platform_transaction(sessions(request)) as session:
        await ensure_pricing_structure(session)
        dup = select(PricingPlanItem.id).where(PricingPlanItem.code == body.code)
        if await session.scalar(dup):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Code bereits vorhanden.")
        row = PricingPlanItem(**body.model_dump(), created_by=principal.user_id)
        session.add(row)
        await session.flush()
        return _pricing_out(row)


@router.patch("/pricing/items/{item_id}", summary="Preisstrukturzeile pflegen (Betrag)")
async def patch_pricing_item(
    item_id: uuid.UUID,
    body: PricingItemPatch,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    async with platform_transaction(sessions(request)) as session:
        row = await session.get(PricingPlanItem, item_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = body.model_dump(exclude_unset=True, exclude={"clear_amount"})
        for key, value in data.items():
            setattr(row, key, value)
        if body.clear_amount:
            row.amount = None
        _check_range(row.min_units, row.max_units)
        row.updated_by = principal.user_id
        await session.flush()
        return _pricing_out(row)


def _check_range(min_units: int | None, max_units: int | None) -> None:
    if min_units is not None and max_units is not None and max_units < min_units:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Einheitenbereich ungültig.")


def _fmt_amount(value: Decimal | None) -> str:
    if value is None:
        return "offen"
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} EUR"


UNIT_LABELS = {
    "unit_month": "je Einheit und Monat",
    "month": "je Monat",
    "once": "einmalig",
    "days": "Tage",
}


def render_offer_pdf(
    rows: list[PricingPlanItem], *, customer_name: str, issued_on: date, units: int | None
) -> bytes:
    """Offer draft from the structure (reportlab). Missing amounts print as "offen"."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    pdf.setTitle("Angebot Entwurf")
    pdf.saveState()
    pdf.setFont("Helvetica-Bold", 60)
    pdf.setFillGray(0.85)
    pdf.translate(width / 2, height / 2)
    pdf.rotate(45)
    pdf.drawCentredString(0, 0, "ENTWURF")
    pdf.restoreState()
    y = height - 25 * mm
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(20 * mm, y, "Angebot MH Verwaltungsplattform (Entwurf)")
    y -= 8 * mm
    pdf.setFont("Helvetica", 10)
    pdf.drawString(20 * mm, y, f"Für: {customer_name}")
    y -= 5 * mm
    pdf.drawString(20 * mm, y, f"Stand: {issued_on.strftime('%d.%m.%Y')}")
    if units is not None:
        y -= 5 * mm
        pdf.drawString(20 * mm, y, f"Einheiten laut Angabe: {units}")
    y -= 10 * mm
    for kind, heading in (
        ("tier", "Stufen nach Einheiten"),
        ("module", "Zusatzmodule"),
        ("trial", "Testphase"),
    ):
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(20 * mm, y, heading)
        y -= 6 * mm
        pdf.setFont("Helvetica", 10)
        for row in rows:
            if row.kind != kind or not row.active:
                continue
            span = ""
            if row.kind == "tier":
                upper = f"bis {row.max_units}" if row.max_units is not None else "und mehr"
                span = f" ({row.min_units or 0} {upper} Einheiten)"
            if row.kind == "trial":
                days = f"{row.trial_days} Tage" if row.trial_days is not None else "Dauer offen"
                line = f"{row.label}: {days}, {_fmt_amount(row.amount)}"
            else:
                line = f"{row.label}{span}: {_fmt_amount(row.amount)} {UNIT_LABELS[row.unit]}"
            pdf.drawString(24 * mm, y, line)
            y -= 5 * mm
            if y < 30 * mm:
                pdf.showPage()
                y = height - 25 * mm
                pdf.setFont("Helvetica", 10)
        y -= 4 * mm
    missing = [r.label for r in rows if r.active and r.amount is None]
    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawString(20 * mm, y, "Alle Beträge netto, ohne Umsatzsteuer. Unverbindlicher Entwurf.")
    y -= 5 * mm
    if missing:
        pdf.drawString(20 * mm, y, "Noch nicht gepflegte Beträge: " + ", ".join(missing))
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


@router.get("/pricing/offer.pdf", summary="Angebot als PDF-Entwurf aus der Preisstruktur")
async def offer_pdf(
    request: Request,
    customer_name: str = "Interessent",
    units: int | None = None,
    _: Principal = Depends(require_platform_admin),
) -> Response:
    async with platform_transaction(sessions(request)) as session:
        rows = await ensure_pricing_structure(session)
        pdf = render_offer_pdf(
            rows,
            customer_name=customer_name[:200],
            issued_on=datetime.now(UTC).date(),
            units=units,
        )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="angebot-entwurf.pdf"'},
    )


# ---------------------------------------------------------------------------------------
# M27-02 G5 evidence list
# ---------------------------------------------------------------------------------------

G5_EVIDENCE_ITEMS: tuple[tuple[str, str], ...] = (
    ("pentest_report", "Pentest-Bericht (Dokument)"),
    ("procedure_documentation", "Verfahrensdokumentation"),
    ("dpa_template", "AVV-Vorlage"),
    ("retention_matrix", "Aufbewahrungsmatrix freigegeben"),
    ("restore_drill", "Restore-Übung protokolliert"),
    ("accessibility_statement", "Barrierefreiheitserklärung"),
    ("portal_privacy_notice", "Datenschutzinformation Portal"),
    ("role_matrix_export", "Rollen- und Rechtematrix (Export)"),
)
G5_CODES = frozenset(code for code, _ in G5_EVIDENCE_ITEMS)
EVIDENCE_STATUS = ("open", "done")


class G5Evidence(IdMixin, TimestampMixin, Base):
    __tablename__ = "g5_evidence"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_g5_evidence_tenant_code"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default="open"
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class G5EvidenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^(" + "|".join(EVIDENCE_STATUS) + ")$")
    document_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


def _evidence_out(code: str, label: str, row: G5Evidence | None) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "status": row.status if row else "open",
        "done": bool(row and row.status == "done"),
        "document_id": row.document_id if row else None,
        "note": row.note if row else None,
        "decided_by": row.decided_by if row else None,
        "decided_at": row.decided_at if row else None,
    }


async def evidence_rows(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, G5Evidence]:
    rows = await session.scalars(select(G5Evidence).where(G5Evidence.tenant_id == tenant_id))
    return {r.code: r for r in rows.all()}


async def evidence_checklist(session: AsyncSession, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = await evidence_rows(session, tenant_id)
    return [_evidence_out(code, label, rows.get(code)) for code, label in G5_EVIDENCE_ITEMS]


async def missing_g5_evidence(session: AsyncSession, tenant_id: uuid.UUID) -> list[str]:
    rows = await evidence_rows(session, tenant_id)
    return [
        code
        for code, _ in G5_EVIDENCE_ITEMS
        if code not in rows or rows[code].status != "done" or rows[code].document_id is None
    ]


async def ensure_g5_release_allowed(
    session: AsyncSession, tenant_id: uuid.UUID, principal: Principal
) -> None:
    """Hook for ``_decide`` (M27-02): every evidence item done with a document, approver is
    the superadmin. Raises ``MHVP-GATE-0005`` otherwise; never opens a gate."""
    missing = await missing_g5_evidence(session, tenant_id)
    if missing:
        raise ProblemError(
            ErrorCodes.GATE_G5_EVIDENCE_MISSING, detail="Offene Nachweise: " + ", ".join(missing)
        )
    if not principal.is_superadmin:
        raise ProblemError(
            ErrorCodes.GATE_G5_EVIDENCE_MISSING,
            detail="G5 gibt nur der Superadmin frei (M27-02).",
        )


@router.get("/tenants/{tenant_id}/g5-evidence", summary="Freigabe G5: Nachweisliste")
async def get_g5_evidence(
    tenant_id: uuid.UUID, request: Request, _: Principal = Depends(require_platform_admin)
) -> dict[str, Any]:
    from mhvp.platform.models import Tenant

    factory = sessions(request)
    async with platform_transaction(factory) as session:
        if await session.get(Tenant, tenant_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    async with tenant_transaction(factory, tenant_id) as session:
        items = await evidence_checklist(session, tenant_id)
        missing = await missing_g5_evidence(session, tenant_id)
    resolver = request.app.state.release_gate_resolver
    return {
        "tenant_id": tenant_id,
        "items": items,
        "complete": not missing,
        "missing": missing,
        "gate_open": await resolver.is_open(tenant_id, ReleaseGate.G5),
        "note": (
            "Das Gate bleibt geschlossen, bis alle Nachweise erledigt sind und der Superadmin "
            "den Freigabeantrag G5 genehmigt (M27-02)."
        ),
    }


@router.put("/tenants/{tenant_id}/g5-evidence/{code}", summary="Freigabe G5: Nachweis pflegen")
async def put_g5_evidence(
    tenant_id: uuid.UUID,
    code: str,
    body: G5EvidenceIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    from mhvp.documents.models import Document
    from mhvp.platform.models import Tenant

    if code not in G5_CODES:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if body.status == "done" and body.document_id is None:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Erledigt nur mit verknüpftem Dokument (M27-02)."
        )
    factory = sessions(request)
    async with platform_transaction(factory) as session:
        if await session.get(Tenant, tenant_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if body.document_id is not None:
        async with tenant_transaction(factory, tenant_id) as session:
            doc = await session.get(Document, body.document_id)
            if doc is None or doc.tenant_id != tenant_id:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Dokument nicht im Mandanten gefunden."
                )
    async with tenant_transaction(factory, tenant_id) as session:
        rows = await evidence_rows(session, tenant_id)
        row = rows.get(code)
        old = row.status if row else "open"
        if row is None:
            row = G5Evidence(tenant_id=tenant_id, code=code, created_by=principal.user_id)
            session.add(row)
        row.status = body.status
        row.document_id = body.document_id
        row.note = body.note
        row.decided_by = principal.user_id
        row.decided_at = gates.now()
        row.updated_by = principal.user_id
        await session.flush()
        label = dict(G5_EVIDENCE_ITEMS)[code]
        out = _evidence_out(code, label, row)
    async with tenant_transaction(factory, tenant_id) as session:
        await emit(
            session,
            tenant_id=tenant_id,
            type="g5_evidence.updated",
            entity_type="g5_evidence",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"code": code, "document_id": str(body.document_id or "")},
            changes={"status": {"old": old, "new": body.status}},
        )
    return out


# ---------------------------------------------------------------------------------------
# M27-03 onboarding of third party tenants
# ---------------------------------------------------------------------------------------

ONBOARDING_ENTITY_KINDS = ("manager", "rental_owner", "sev_owner")
# Feature flags of a new tenant that stay off (rule 0.1.1): reported, never switched on here.
FEATURE_FLAGS_DEFAULT_OFF = ("auto_posting_enabled",)


class OnboardingLegalEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(pattern="^(" + "|".join(ONBOARDING_ENTITY_KINDS) + ")$")
    name: str = Field(min_length=2, max_length=400)


class OnboardingAdmin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    display_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=12, max_length=200)


class OnboardingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    name: str = Field(min_length=2, max_length=200)
    company: dict[str, Any] = Field(default_factory=dict)
    branding: dict[str, Any] = Field(default_factory=dict)
    domains: list[str] = Field(default_factory=list, max_length=10)
    legal_entities: list[OnboardingLegalEntity] = Field(default_factory=list, max_length=50)
    admin: OnboardingAdmin
    admin_role_codes: list[str] = Field(default_factory=lambda: ["tenant_admin"], max_length=10)


def welcome_email_draft(*, tenant_name: str, admin_name: str, admin_email: str) -> dict[str, str]:
    body = (
        f"Guten Tag {admin_name},\n\n"
        f"für {tenant_name} wurde ein Mandant auf der MH Verwaltungsplattform angelegt. "
        f"Ihr Zugang lautet {admin_email}. Bitte melden Sie sich an, ändern Sie Ihr Passwort "
        "und richten Sie nach Wunsch den zweiten Faktor ein.\n\n"
        "Produktive Buchführung, Zahlungen und Abrechnungen sind bis zur Freigabe der "
        "jeweiligen Freigabestufe gesperrt. Der Auftragsverarbeitungsvertrag wird Ihnen "
        "gesondert zur Verfügung gestellt.\n\n"
        "Mit freundlichen Grüßen\nMüller Holding AG\n"
    )
    return {
        "to": admin_email,
        "subject": f"Ihr Zugang zur MH Verwaltungsplattform ({tenant_name})",
        "body": body,
        "status": "draft",
    }


@router.post("/onboarding", status_code=201, summary="Drittmandant anlegen (Assistent)")
async def onboard_tenant(
    body: OnboardingIn, request: Request, principal: Principal = Depends(require_platform_admin)
) -> dict[str, Any]:
    """Creates tenant, settings (company, CI), system roles, legal entities and the first
    administrator; feature flags stay off and no gate is opened. The welcome mail is a draft."""
    from mhvp.platform.models import TenantSettings
    from mhvp.platform.schemas import Branding, CompanyData
    from mhvp.platform.services import (
        add_member,
        create_user,
        provision_tenant,
        user_id_by_email,
    )
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    company_name = body.company.get("name") or body.name
    company = CompanyData.model_validate(body.company | {"name": company_name})
    branding = Branding.model_validate(body.branding)
    factory = sessions(request)
    tenant_id, created = await provision_tenant(
        factory,
        slug=body.slug,
        name=body.name,
        company=company.model_dump(mode="json"),
        branding=branding.model_dump(mode="json", by_alias=True),
        domains=body.domains,
        actor_user_id=principal.user_id,
    )
    if not created:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Mandant mit diesem Kürzel vorhanden.")
    entity_ids: list[dict[str, Any]] = []
    async with tenant_transaction(factory, tenant_id) as session:
        for spec in body.legal_entities:
            entity = LegalEntity(
                tenant_id=tenant_id,
                kind=LegalEntityKind(spec.kind),
                name=spec.name,
                created_by=principal.user_id,
            )
            session.add(entity)
            await session.flush()
            entity_ids.append({"id": entity.id, "kind": spec.kind, "name": spec.name})
        settings = await session.scalar(
            select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
        )
        flags = {flag: bool(getattr(settings, flag)) for flag in FEATURE_FLAGS_DEFAULT_OFF}
    try:
        admin_id = await create_user(
            factory,
            email=body.admin.email,
            display_name=body.admin.display_name,
            password=body.admin.password,
            is_platform_admin=False,
        )
        admin_existed = False
    except ProblemError as exc:
        if exc.error is not ErrorCodes.CONFLICT:
            raise
        found = await user_id_by_email(factory, body.admin.email)
        if found is None:
            raise
        admin_id, admin_existed = found, True
    membership_id = await add_member(
        factory,
        tenant_id=tenant_id,
        user_id=admin_id,
        role_codes=body.admin_role_codes,
        actor_user_id=principal.user_id,
    )
    async with tenant_transaction(factory, tenant_id) as session:
        await emit(
            session,
            tenant_id=tenant_id,
            type="tenant.onboarded",
            entity_type="tenant",
            entity_id=tenant_id,
            actor_user_id=principal.user_id,
            payload={"legal_entities": len(entity_ids), "admin_user_id": str(admin_id)},
        )
    resolver = request.app.state.release_gate_resolver
    return {
        "tenant_id": tenant_id,
        "slug": body.slug,
        "name": body.name,
        "legal_entities": entity_ids,
        "admin": {
            "user_id": admin_id,
            "membership_id": membership_id,
            "email": body.admin.email.lower(),
            "existed": admin_existed,
            "roles": body.admin_role_codes,
        },
        "feature_flags": flags,
        "gates": {g.value: await resolver.is_open(tenant_id, g) for g in ReleaseGate},
        "welcome_email": welcome_email_draft(
            tenant_name=body.name,
            admin_name=body.admin.display_name,
            admin_email=body.admin.email.lower(),
        ),
    }


# ---------------------------------------------------------------------------------------
# M27-03 tenant export (GDPR access and portability), four eyes
# ---------------------------------------------------------------------------------------

EXPORT_PURPOSES = ("access", "portability")
EXPORT_STATUS = ("requested", "approved", "rejected")
_SECRET_MARKERS = ("secret", "password", "token", "hash", "key")


class TenantExportRequest(IdMixin, TimestampMixin, Base):
    __tablename__ = "tenant_export_request"
    __table_args__ = (Index("ix_tenant_export_request_tenant", "tenant_id", "created_at"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="requested", server_default="requested"
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)
    downloads: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Background job of the full export (M27-01); NULL job_status: no job started.
    job_status: Mapped[str | None] = mapped_column(String(16))
    job_object_key: Mapped[str | None] = mapped_column(String(512))
    job_size: Mapped[int | None] = mapped_column(BigInteger)
    job_sha256: Mapped[str | None] = mapped_column(String(64))
    job_error: Mapped[str | None] = mapped_column(Text)
    job_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExportRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(pattern="^(" + "|".join(EXPORT_PURPOSES) + ")$")
    comment: str | None = Field(default=None, max_length=2000)


class ExportDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=2000)


def _export_out(row: TenantExportRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "purpose": row.purpose,
        "status": row.status,
        "requested_by": row.requested_by,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at,
        "comment": row.comment,
        "downloads": row.downloads,
        "created_at": row.created_at,
        "job_status": row.job_status,
        "job_size": row.job_size,
        "job_sha256": row.job_sha256,
        "job_error": row.job_error,
        "job_finished_at": row.job_finished_at,
    }


@router.get("/tenants/{tenant_id}/export-requests", summary="Mandanten-Export: Anträge")
async def list_export_requests(
    tenant_id: uuid.UUID, request: Request, _: Principal = Depends(require_platform_admin)
) -> list[dict[str, Any]]:
    async with tenant_transaction(sessions(request), tenant_id) as session:
        rows = await session.scalars(
            select(TenantExportRequest)
            .where(TenantExportRequest.tenant_id == tenant_id)
            .order_by(TenantExportRequest.created_at.desc())
        )
        return [_export_out(r) for r in rows.all()]


@router.post(
    "/tenants/{tenant_id}/export-requests",
    status_code=201,
    summary="Mandanten-Export beantragen (DSGVO Auskunft oder Portabilität)",
)
async def request_export(
    tenant_id: uuid.UUID,
    body: ExportRequestIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    from mhvp.platform.models import Tenant

    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN)
    factory = sessions(request)
    async with platform_transaction(factory) as session:
        if await session.get(Tenant, tenant_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    async with tenant_transaction(factory, tenant_id) as session:
        row = TenantExportRequest(
            tenant_id=tenant_id,
            purpose=body.purpose,
            comment=body.comment,
            requested_by=principal.user_id,
            created_by=principal.user_id,
        )
        session.add(row)
        await session.flush()
        return _export_out(row)


async def _decide_export(
    request: Request,
    principal: Principal,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    approve: bool,
    comment: str | None,
) -> dict[str, Any]:
    async with tenant_transaction(sessions(request), tenant_id) as session:
        row = await session.get(TenantExportRequest, request_id)
        if row is None or row.tenant_id != tenant_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.status != "requested":
            raise ProblemError(ErrorCodes.GATE_STATE)
        if row.requested_by == principal.user_id:
            raise ProblemError(ErrorCodes.GATE_FOUR_EYES)
        row.status = "approved" if approve else "rejected"
        row.decided_by = principal.user_id
        row.decided_at = gates.now()
        row.comment = comment or row.comment
        row.updated_by = principal.user_id
        await session.flush()
        return _export_out(row)


@router.post(
    "/tenants/{tenant_id}/export-requests/{request_id}/approve",
    summary="Mandanten-Export freigeben (zweite Person)",
)
async def approve_export(
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    body: ExportDecisionIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    return await _decide_export(request, principal, tenant_id, request_id, True, body.comment)


@router.post(
    "/tenants/{tenant_id}/export-requests/{request_id}/reject",
    summary="Mandanten-Export ablehnen",
)
async def reject_export(
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    body: ExportDecisionIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    return await _decide_export(request, principal, tenant_id, request_id, False, body.comment)


def _json_value(value: Any) -> Any:
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def row_to_dict(row: Any) -> dict[str, Any]:
    """Column values of a mapped row without secrets (names containing a secret marker)."""
    out: dict[str, Any] = {}
    for column in sa_inspect(row).mapper.column_attrs:
        name = column.key
        if any(marker in name.lower() for marker in _SECRET_MARKERS):
            continue
        out[name] = _json_value(getattr(row, name))
    return out


async def build_tenant_export(
    factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID, purpose: str
) -> bytes:
    """ZIP with one JSON per entity, read under the tenant's RLS context (only own data)."""
    from mhvp.contacts.models import Contact
    from mhvp.platform.models import Membership, Tenant, TenantSettings
    from mhvp.properties.models import LegalEntity, Property, Unit

    files: dict[str, Any] = {}
    async with platform_transaction(factory) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        files["tenant.json"] = row_to_dict(tenant)
        members = await session.scalars(select(Membership).where(Membership.tenant_id == tenant_id))
        files["memberships.json"] = [row_to_dict(m) for m in members.all()]
    async with tenant_transaction(factory, tenant_id) as session:
        settings = await session.scalar(
            select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
        )
        files["tenant_settings.json"] = (
            {
                "company": settings.company,
                "branding": settings.branding,
                "sources": settings.sources,
                "auto_posting_enabled": settings.auto_posting_enabled,
            }
            if settings
            else None
        )
        for name, model in (
            ("legal_entities.json", LegalEntity),
            ("properties.json", Property),
            ("units.json", Unit),
            ("contacts.json", Contact),
        ):
            rows = await session.scalars(select(model).where(model.tenant_id == tenant_id))
            files[name] = [row_to_dict(r) for r in rows.all()]
    manifest = {
        "tenant_id": str(tenant_id),
        "purpose": purpose,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "draft",
        "entities": {k: (len(v) if isinstance(v, list) else 1) for k, v in files.items()},
        "note": "Entwurf; Vollständigkeit und Rechtsgrundlage der Auskunft prüft der Betreiber.",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for name, content in files.items():
            archive.writestr(name, json.dumps(content, ensure_ascii=False, indent=2))
    return buffer.getvalue()


@router.post(
    "/tenants/{tenant_id}/export-requests/{request_id}/run",
    status_code=202,
    summary="Vollständigen Mandanten-Export als Hintergrundjob starten (nur nach Freigabe)",
)
async def run_export(
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    """Queues the job (M27-01): JSON lines plus document originals. Only an approved request
    runs; a running or finished job is not started twice, a failed one may be retried."""
    from mhvp.platform import export_job

    async with tenant_transaction(sessions(request), tenant_id) as session:
        row = await session.get(TenantExportRequest, request_id)
        if row is None or row.tenant_id != tenant_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.status != "approved":
            raise ProblemError(ErrorCodes.GATE_STATE)
        if row.job_status in (
            export_job.JOB_QUEUED,
            export_job.JOB_RUNNING,
            export_job.JOB_READY,
        ):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Export-Job bereits gestartet.")
        row.job_status = export_job.JOB_QUEUED
        row.job_error = None
        row.updated_by = principal.user_id
        await session.flush()
        out = _export_out(row)
    export_job.dispatch_export_job(str(request_id), str(tenant_id))
    return out


@router.get(
    "/tenants/{tenant_id}/export-requests/{request_id}/download",
    summary="Mandanten-Export herunterladen (ZIP, nur nach Freigabe)",
)
async def download_export(
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> Response:
    factory = sessions(request)
    async with tenant_transaction(factory, tenant_id) as session:
        row = await session.get(TenantExportRequest, request_id)
        if row is None or row.tenant_id != tenant_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.status != "approved":
            raise ProblemError(ErrorCodes.GATE_STATE)
        purpose = row.purpose
        job_status, job_key = row.job_status, row.job_object_key
        if job_status in ("queued", "running"):
            raise ProblemError(ErrorCodes.GATE_STATE, detail="Export-Job läuft noch.")
        if job_status == "failed":
            raise ProblemError(ErrorCodes.GATE_STATE, detail="Export-Job fehlgeschlagen.")
        row.downloads += 1
        row.updated_by = principal.user_id
    if job_status == "ready" and job_key:
        from mhvp.documents.blobs import BlobStore

        data = BlobStore(request.app.state.settings).get(job_key)
    else:
        data = await build_tenant_export(factory, tenant_id, purpose)
    async with tenant_transaction(factory, tenant_id) as session:
        await emit(
            session,
            tenant_id=tenant_id,
            type="tenant.exported",
            entity_type="tenant_export_request",
            entity_id=request_id,
            actor_user_id=principal.user_id,
            payload={"purpose": purpose, "size": len(data)},
        )
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="mandant-{tenant_id}.zip"'},
    )
