"""Tax endpoints of the invoice intake (/api/v1/accounting/tax, M14-02, M14-03, M14-04).

Tenant settings (switches, input tax account, withholding percent, approval limits per role)
need ``tenant_settings:update``; profiles of properties and suppliers and the tax data of an
invoice need ``accounting:update``; approvals (withholding, second approval) need
``accounting:approve`` by another person. Every value is a draft with the source status
"zu prüfen durch Steuerberater" (docs/rules/M14-02.md, M14-03.md, M14-04.md); nothing is
posted, withheld or sent here. The § 35a certificate is a PDF draft with the watermark
"ENTWURF" (A83) and is filed as a generated document only on request.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import tax
from mhvp.accounting.models import Invoice, InvoiceLine
from mhvp.accounting.tax_models import (
    InvoiceLineSection35a,
    InvoiceTaxData,
    PropertyTaxProfile,
    Section35aCertificateLog,
    SupplierTaxProfile,
)
from mhvp.contacts.models import Contact, Party, PartyMember
from mhvp.contracts.models import Contract
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_path_guard
from mhvp.core.events import diff, emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import letters
from mhvp.documents.models import Document, DocumentSource, LinkRole
from mhvp.properties.models import Property, Unit
from mhvp.workspace.services import local_today

# M2-02/S16-02: path ids outside the property assignment answer 404.
router = APIRouter(
    prefix="/accounting/tax", tags=["Buchhaltung"], dependencies=[Depends(property_path_guard)]
)
READ = require_permission("accounting:read")
UPDATE = require_permission("accounting:update")
APPROVE = require_permission("accounting:approve")
SETTINGS_READ = require_permission("tenant_settings:read")
SETTINGS_UPDATE = require_permission("tenant_settings:update")

DRAFT_NOTICE = "Entwurf, zu prüfen durch Steuerberater, keine steuerliche Bescheinigung"
# AI18 (GAH-101): notice only, no lock (the criterion is an open decision, G3/G4).
REPEAT_NOTICE = (
    "Für diesen Vertrag und dieses Jahr wurde bereits ein Ausweis erzeugt. "
    "Bitte prüfen, ob dieselben Aufwendungen erneut ausgewiesen werden."
)


async def _log_certificate(
    session: AsyncSession,
    principal: TenantPrincipal,
    cert: "CertificateOut",
    output: str,
    document_id: uuid.UUID | None = None,
) -> None:
    session.add(
        Section35aCertificateLog(
            tenant_id=principal.tenant_id,
            contract_id=cert.contract_id,
            year=cert.year,
            basis=cert.basis,
            output=output,
            document_id=document_id,
            labor_total=cert.labor_total,
            created_by=principal.user_id,
        )
    )
    await session.flush()


# Schemas ----------------------------------------------------------------------------------------


class ApprovalLimitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_code: str = Field(min_length=1, max_length=64)
    limit_amount: Decimal = Field(ge=0)


class TaxSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    input_tax_enabled: bool
    input_tax_account_number: str | None
    construction_withholding_enabled: bool
    construction_withholding_percent: Decimal
    section_35a_enabled: bool
    approval_limits_enabled: bool
    approval_limits: list[dict[str, Any]]
    subledger_exclude_written_off: bool = True
    section_35a_basis: str = "invoice_date"


class TaxSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_tax_enabled: bool = False
    input_tax_account_number: str | None = Field(default=None, pattern=r"^[0-9]{6}$")
    construction_withholding_enabled: bool = False
    construction_withholding_percent: Decimal = Field(default=Decimal("15.00"), ge=0, le=100)
    section_35a_enabled: bool = False
    approval_limits_enabled: bool = False
    approval_limits: list[ApprovalLimitIn] = Field(default_factory=list, max_length=50)
    subledger_exclude_written_off: bool = True
    # AI18 (GAH-101): selection basis of the § 35a certificate, default unchanged.
    section_35a_basis: Literal["invoice_date", "payment_date"] = "invoice_date"


class PropertyProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    property_id: uuid.UUID
    vat_opted: bool
    revenue_key_percent: Decimal | None
    note: str | None


class PropertyProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vat_opted: bool = False
    revenue_key_percent: Decimal | None = Field(default=None, ge=0, le=100)
    note: str | None = Field(default=None, max_length=500)


class SupplierProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    contact_id: uuid.UUID
    construction_services: bool
    reverse_charge: bool
    exemption_number: str | None
    exemption_valid_from: date | None
    exemption_valid_to: date | None
    exemption_document_id: uuid.UUID | None
    note: str | None
    exemption_valid_today: bool = False


class SupplierProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    construction_services: bool = False
    reverse_charge: bool = False
    exemption_number: str | None = Field(default=None, max_length=100)
    exemption_valid_from: date | None = None
    exemption_valid_to: date | None = None
    exemption_document_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)


class InvoiceTaxOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    invoice_id: uuid.UUID
    vat_rate: Decimal | None
    input_tax_amount: Decimal | None
    reverse_charge: bool
    construction_service: bool
    deductible_percent: Decimal | None
    deductible_input_tax: Decimal | None
    withholding_percent: Decimal | None
    withholding_proposal: Decimal | None
    withholding_approved_by: uuid.UUID | None
    withholding_approved_amount: Decimal | None
    warnings: list[str]


class InvoiceTaxIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vat_rate: Decimal | None = Field(default=None, ge=0, le=100)
    input_tax_amount: Decimal | None = Field(default=None, ge=0)
    reverse_charge: bool = False
    construction_service: bool = False


class Section35aIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern="^(household_service|craftsman)$")
    labor_amount: Decimal = Field(ge=0)
    material_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    text: str | None = Field(default=None, max_length=500)


class Section35aOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    invoice_id: uuid.UUID
    invoice_line_id: uuid.UUID
    kind: str
    labor_amount: Decimal
    material_amount: Decimal
    text: str | None


class ApprovalStateOut(BaseModel):
    enabled: bool
    limit_amount: Decimal | None
    second_approval_required: bool
    second_approval_valid: bool
    second_approved_by: uuid.UUID | None


class CertificateLineOut(BaseModel):
    invoice_number: str
    invoice_date: date
    kind: str
    labor_amount: Decimal
    material_amount: Decimal
    text: str | None
    paid: bool = False
    paid_on: date | None = None


class CertificatePreviousOut(BaseModel):
    created_at: datetime
    output: str
    basis: str
    document_id: uuid.UUID | None
    labor_total: Decimal


class CertificateOut(BaseModel):
    contract_id: uuid.UUID
    year: int
    share_percent: Decimal
    basis: str = "invoice_date"
    unpaid_lines: int = 0
    previous: list[CertificatePreviousOut] = Field(default_factory=list)
    repeat_notice: str | None = None
    lines: list[CertificateLineOut]
    labor_by_kind: dict[str, Decimal]
    labor_total: Decimal
    material_total: Decimal
    notice: str


# Helpers ----------------------------------------------------------------------------------------


async def _invoice(session: AsyncSession, invoice_id: uuid.UUID) -> Invoice:
    inv = await session.get(Invoice, invoice_id, with_for_update=True)
    if inv is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return inv


def _person(principal: TenantPrincipal) -> uuid.UUID:
    """Approvals need a natural person; an API key without user cannot approve."""
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.GATE_FOUR_EYES, detail="Freigabe nur durch eine Person.")
    return principal.user_id


def _tax_out(data: InvoiceTaxData) -> InvoiceTaxOut:
    return InvoiceTaxOut.model_validate(data)


def _supplier_out(profile: SupplierTaxProfile) -> SupplierProfileOut:
    out = SupplierProfileOut.model_validate(profile)
    out.exemption_valid_today = tax.exemption_valid_on(
        local_today(),
        profile.exemption_valid_from,
        profile.exemption_valid_to,
        profile.exemption_document_id is not None,
    )
    return out


async def _refresh_invoices_of_supplier(session: AsyncSession, contact_id: uuid.UUID) -> None:
    rows = await session.execute(
        select(Invoice, InvoiceTaxData)
        .join(InvoiceTaxData, InvoiceTaxData.invoice_id == Invoice.id)
        .where(Invoice.provider_contact_id == contact_id)
    )
    for invoice, data in rows.all():
        await tax.refresh_proposals(session, invoice, data)


# Settings ----------------------------------------------------------------------------------------


@router.get("/settings", summary="Steuereinstellungen des Mandanten (Entwurf)")
async def get_settings(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> TaxSettingsOut:
    async with tenant_tx(request, principal) as session:
        return TaxSettingsOut.model_validate(await tax.settings_of(session, principal.tenant_id))


@router.put("/settings", summary="Steuereinstellungen setzen (Schalter je Mandant, Standard aus)")
async def put_settings(
    body: TaxSettingsIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS_UPDATE)
) -> TaxSettingsOut:
    async with tenant_tx(request, principal) as session:
        row = await tax.settings_of(session, principal.tenant_id)
        row.input_tax_enabled = body.input_tax_enabled
        row.input_tax_account_number = body.input_tax_account_number
        row.construction_withholding_enabled = body.construction_withholding_enabled
        row.construction_withholding_percent = body.construction_withholding_percent
        row.section_35a_enabled = body.section_35a_enabled
        row.approval_limits_enabled = body.approval_limits_enabled
        row.subledger_exclude_written_off = body.subledger_exclude_written_off
        row.section_35a_basis = body.section_35a_basis
        row.approval_limits = [
            {"role_code": lim.role_code, "limit_amount": str(lim.limit_amount)}
            for lim in body.approval_limits
        ]
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="accounting_tax_settings.updated",
            entity_type="accounting_tax_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload=TaxSettingsOut.model_validate(row).model_dump(mode="json"),
        )
        return TaxSettingsOut.model_validate(row)


def _jsonable(value: Any) -> Any:
    """Decimal and dates as strings for event payloads."""
    if isinstance(value, Decimal | date | datetime | uuid.UUID):
        return str(value)
    return value


# Property and supplier profiles ------------------------------------------------------------------


@router.get("/properties/{property_id}/profile", summary="Umsatzsteueroption und Umsatzschlüssel")
async def get_property_profile(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> PropertyProfileOut:
    async with tenant_tx(request, principal) as session:
        if await session.get(Property, property_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = await session.scalar(
            select(PropertyTaxProfile).where(PropertyTaxProfile.property_id == property_id)
        )
        if row is None:
            return PropertyProfileOut(
                property_id=property_id, vat_opted=False, revenue_key_percent=None, note=None
            )
        return PropertyProfileOut.model_validate(row)


@router.put("/properties/{property_id}/profile", summary="Umsatzsteueroption je Objekt setzen")
async def put_property_profile(
    property_id: uuid.UUID,
    body: PropertyProfileIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> PropertyProfileOut:
    async with tenant_tx(request, principal) as session:
        if await session.get(Property, property_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = await session.scalar(
            select(PropertyTaxProfile).where(PropertyTaxProfile.property_id == property_id)
        )
        if row is None:
            before: dict[str, Any] = {}
            row = PropertyTaxProfile(tenant_id=principal.tenant_id, property_id=property_id)
            session.add(row)
        else:
            before = PropertyProfileOut.model_validate(row).model_dump(mode="json")
        row.vat_opted = body.vat_opted
        row.revenue_key_percent = body.revenue_key_percent
        row.note = body.note
        row.updated_by = principal.user_id
        await session.flush()
        await session.refresh(row)
        out = PropertyProfileOut.model_validate(row)
        after = out.model_dump(mode="json")
        # GAI-307: tax classification stays traceable (rule 6, B07).
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property_tax_profile.updated",
            entity_type="property",
            entity_id=property_id,
            actor_user_id=principal.user_id,
            payload=after,
            changes=diff(before, after),
        )
        return out


@router.get("/suppliers/{contact_id}/profile", summary="Steuerkennzeichen des Lieferanten")
async def get_supplier_profile(
    contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> SupplierProfileOut:
    async with tenant_tx(request, principal) as session:
        if await session.get(Contact, contact_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = await session.scalar(
            select(SupplierTaxProfile).where(SupplierTaxProfile.contact_id == contact_id)
        )
        if row is None:
            return SupplierProfileOut(
                contact_id=contact_id,
                construction_services=False,
                reverse_charge=False,
                exemption_number=None,
                exemption_valid_from=None,
                exemption_valid_to=None,
                exemption_document_id=None,
                note=None,
            )
        return _supplier_out(row)


@router.put("/suppliers/{contact_id}/profile", summary="Steuerkennzeichen des Lieferanten setzen")
async def put_supplier_profile(
    contact_id: uuid.UUID,
    body: SupplierProfileIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> SupplierProfileOut:
    async with tenant_tx(request, principal) as session:
        if await session.get(Contact, contact_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if (
            body.exemption_valid_from
            and body.exemption_valid_to
            and body.exemption_valid_to < body.exemption_valid_from
        ):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Gültig bis liegt vor Gültig ab.")
        # M14-04: an exemption only counts with a stored document of this tenant. The foreign
        # key alone bypasses row level security, so the id is resolved through the RLS bound
        # session (review 27.09.2026: a foreign or invented id lifted the withholding block).
        if (
            body.exemption_document_id is not None
            and await session.get(Document, body.exemption_document_id) is None
        ):
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Freistellungsbescheinigung nicht gefunden."
            )
        row = await session.scalar(
            select(SupplierTaxProfile).where(SupplierTaxProfile.contact_id == contact_id)
        )
        if row is None:
            before_s: dict[str, Any] = {}
            row = SupplierTaxProfile(tenant_id=principal.tenant_id, contact_id=contact_id)
            session.add(row)
        else:
            before_s = _supplier_out(row).model_dump(mode="json")
        for name in (
            "construction_services",
            "reverse_charge",
            "exemption_number",
            "exemption_valid_from",
            "exemption_valid_to",
            "exemption_document_id",
            "note",
        ):
            setattr(row, name, getattr(body, name))
        row.updated_by = principal.user_id
        await session.flush()
        await _refresh_invoices_of_supplier(session, contact_id)
        out_s = _supplier_out(row)
        after_s = out_s.model_dump(mode="json")
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="supplier_tax_profile.updated",
            entity_type="contact",
            entity_id=contact_id,
            actor_user_id=principal.user_id,
            payload=after_s,
            changes=diff(before_s, after_s),
        )
        return out_s


# Invoice tax data --------------------------------------------------------------------------------


@router.get("/invoices/{invoice_id}", summary="Steuerdaten und Vorschläge einer Rechnung")
async def get_invoice_tax(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> InvoiceTaxOut:
    async with tenant_tx(request, principal) as session:
        inv = await _invoice(session, invoice_id)
        data = await tax.refresh_proposals(session, inv, await tax.tax_data_of(session, inv))
        return _tax_out(data)


@router.put("/invoices/{invoice_id}", summary="Steuersatz, Vorsteuer, Reverse Charge, Bauleistung")
async def put_invoice_tax(
    invoice_id: uuid.UUID,
    body: InvoiceTaxIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> InvoiceTaxOut:
    async with tenant_tx(request, principal) as session:
        inv = await _invoice(session, invoice_id)
        data = await tax.tax_data_of(session, inv)
        tax_keys = ("vat_rate", "input_tax_amount", "reverse_charge", "construction_service")
        before_t = {k: _jsonable(getattr(data, k)) for k in tax_keys}
        data.vat_rate = body.vat_rate
        data.input_tax_amount = body.input_tax_amount
        data.reverse_charge = body.reverse_charge
        data.construction_service = body.construction_service
        data.updated_by = principal.user_id
        data = await tax.refresh_proposals(session, inv, data)
        after_t = {k: _jsonable(getattr(data, k)) for k in tax_keys}
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice_tax_data.updated",
            entity_type="invoice",
            entity_id=inv.id,
            actor_user_id=principal.user_id,
            payload=after_t,
            changes=diff(before_t, after_t),
        )
        return _tax_out(data)


@router.post(
    "/invoices/{invoice_id}/withholding/approve",
    summary="Einbehalt Bauabzugsteuer bestätigen (zweite Person, Entwurf)",
)
async def approve_withholding(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> InvoiceTaxOut:
    async with tenant_tx(request, principal) as session:
        inv = await _invoice(session, invoice_id)
        data = await tax.approve_withholding(session, inv, _person(principal))
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice.withholding_approved",
            entity_type="invoice",
            entity_id=inv.id,
            actor_user_id=principal.user_id,
            payload={"amount": str(data.withholding_approved_amount)},
        )
        return _tax_out(data)


# § 35a markers per line --------------------------------------------------------------------------


@router.get(
    "/invoices/{invoice_id}/section35a",
    summary="§-35a-Kennzeichen der Positionen",
    dependencies=[Depends(strict_query)],
)
async def list_section35a(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[Section35aOut]:
    async with tenant_tx(request, principal) as session:
        await _invoice(session, invoice_id)
        rows = await tax.section35a_lines_of_invoice(session, invoice_id)
        return [Section35aOut.model_validate(r) for r in rows]


@router.put(
    "/invoice-lines/{line_id}/section35a",
    summary="§-35a-Kennzeichen setzen (Lohnanteil, Materialanteil, Einschätzung)",
)
async def put_section35a(
    line_id: uuid.UUID,
    body: Section35aIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> Section35aOut:
    async with tenant_tx(request, principal) as session:
        line = await session.get(InvoiceLine, line_id)
        if line is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if body.labor_amount + body.material_amount > line.net + line.vat:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Lohn- und Materialanteil übersteigen den Bruttobetrag der Position.",
            )
        row = await session.scalar(
            select(InvoiceLineSection35a).where(InvoiceLineSection35a.invoice_line_id == line_id)
        )
        if row is None:
            before_a: dict[str, Any] = {}
            row = InvoiceLineSection35a(
                tenant_id=principal.tenant_id, invoice_id=line.invoice_id, invoice_line_id=line_id
            )
            session.add(row)
        else:
            before_a = Section35aOut.model_validate(row).model_dump(mode="json")
        row.kind = body.kind
        row.labor_amount = body.labor_amount
        row.material_amount = body.material_amount
        row.text = body.text
        row.updated_by = principal.user_id
        await session.flush()
        await session.refresh(row)
        out_a = Section35aOut.model_validate(row)
        after_a = out_a.model_dump(mode="json")
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice_line_section35a.updated",
            entity_type="invoice_line",
            entity_id=line_id,
            actor_user_id=principal.user_id,
            payload=after_a,
            changes=diff(before_a, after_a),
        )
        return out_a


@router.delete(
    "/invoice-lines/{line_id}/section35a", status_code=204, summary="Kennzeichen entfernen"
)
async def delete_section35a(
    line_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> Response:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(
            select(InvoiceLineSection35a).where(InvoiceLineSection35a.invoice_line_id == line_id)
        )
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        before_d = Section35aOut.model_validate(row).model_dump(mode="json")
        await session.delete(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice_line_section35a.deleted",
            entity_type="invoice_line",
            entity_id=line_id,
            actor_user_id=principal.user_id,
            payload={"invoice_id": before_d.get("invoice_id")},
            changes=diff(before_d, {}),
        )
        return Response(status_code=204)


# Approval limits (M14-03) ------------------------------------------------------------------------


@router.get("/invoices/{invoice_id}/approval", summary="Freigabegrenze für die anfragende Person")
async def approval_state(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> ApprovalStateOut:
    async with tenant_tx(request, principal) as session:
        inv = await _invoice(session, invoice_id)
        return ApprovalStateOut(**await tax.second_approval_state(session, inv, principal.roles))


@router.post(
    "/invoices/{invoice_id}/second-approval",
    summary="Zweite Freigabe über der Betragsgrenze (dritte Person)",
)
async def second_approval(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> ApprovalStateOut:
    async with tenant_tx(request, principal) as session:
        inv = await _invoice(session, invoice_id)
        if principal.is_platform_admin:
            raise ProblemError(
                ErrorCodes.GATE_FOUR_EYES, detail="Die Freigabe muss eine andere Person erteilen."
            )
        await tax.add_second_approval(session, inv, _person(principal))
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice.second_approved",
            entity_type="invoice",
            entity_id=inv.id,
            actor_user_id=principal.user_id,
            payload={"version": inv.version},
        )
        return ApprovalStateOut(**await tax.second_approval_state(session, inv, principal.roles))


# § 35a certificate per tenant contract (M14-04) --------------------------------------------------


async def _certificate(
    session: AsyncSession,
    contract_id: uuid.UUID,
    year: int,
    share_percent: Decimal,
    tenant_id: uuid.UUID,
) -> tuple[Contract, CertificateOut]:
    contract = await session.get(Contract, contract_id)
    if contract is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    settings = await tax.settings_of(session, tenant_id)
    if not settings.section_35a_enabled:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="§-35a-Ausweis ist für diesen Mandanten nicht aktiviert."
        )
    summary = await tax.section35a_summary(
        session,
        property_id=contract.property_id,
        year=year,
        unit_id=contract.unit_id,
        share_percent=share_percent,
        basis=settings.section_35a_basis,
    )
    previous = [
        CertificatePreviousOut(
            created_at=log.created_at,
            output=log.output,
            basis=log.basis,
            document_id=log.document_id,
            labor_total=log.labor_total,
        )
        for log in (
            await session.scalars(
                select(Section35aCertificateLog)
                .where(
                    Section35aCertificateLog.contract_id == contract_id,
                    Section35aCertificateLog.year == year,
                )
                .order_by(Section35aCertificateLog.created_at)
            )
        ).all()
    ]
    return contract, CertificateOut(
        contract_id=contract_id,
        year=year,
        share_percent=share_percent,
        basis=settings.section_35a_basis,
        unpaid_lines=sum(1 for ln in summary.lines if not ln.paid),
        previous=previous,
        repeat_notice=REPEAT_NOTICE if previous else None,
        lines=[CertificateLineOut(**vars(ln)) for ln in summary.lines],
        labor_by_kind=summary.share_by_kind(),
        labor_total=summary.labor_total,
        material_total=summary.material_total,
        notice=DRAFT_NOTICE,
    )


def _eur(value: Decimal) -> str:
    whole, frac = f"{value:,.2f}".split(".")
    return f"{whole.replace(',', '.')},{frac} EUR"


def _de_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


KIND_LABELS = {
    "household_service": "Haushaltsnahe Dienstleistungen",
    "craftsman": "Handwerkerleistungen",
}


async def _recipient_lines(session: AsyncSession, contract: Contract) -> list[str]:
    from mhvp.documents import services as doc_services

    party = await session.get(Party, contract.party_id)
    member = await session.scalar(
        select(PartyMember)
        .where(PartyMember.party_id == contract.party_id)
        .order_by(PartyMember.created_at)
        .limit(1)
    )
    if member is not None:
        try:
            _, lines, _ = await doc_services.recipient(session, member.contact_id)
            return lines
        except ProblemError:
            pass
    return [party.name if party is not None else "Mieter"]


async def _certificate_pdf(
    session: AsyncSession, request: Request, contract: Contract, cert: CertificateOut
) -> bytes:
    from mhvp.documents import services as doc_services
    from mhvp.documents.blobs import BlobStore

    head = await doc_services.letterhead(session, BlobStore(request.app.state.settings))
    unit = await session.get(Unit, contract.unit_id)
    prop = await session.get(Property, contract.property_id)
    rows = [
        [
            _de_date(ln.invoice_date),
            ln.invoice_number,
            KIND_LABELS.get(ln.kind, ln.kind),
            (ln.text or "")[:48],
            _de_date(ln.paid_on) if ln.paid and ln.paid_on else "nein",
            _eur(ln.labor_amount),
            _eur(ln.material_amount),
        ]
        for ln in cert.lines
    ]
    rows.append(["", "", "Summe", "", "", _eur(cert.labor_total), _eur(cert.material_total)])
    table = letters.LetterTable(
        header=["Datum", "Rechnung", "Art", "Leistung", "Bezahlt", "Lohnanteil", "Materialanteil"],
        rows=rows,
        right_aligned=(5, 6),
        total_row=True,
        widths=(0.12, 0.13, 0.19, 0.18, 0.12, 0.13, 0.13),
    )
    kinds = (
        ", ".join(f"{KIND_LABELS[k]} {_eur(v)}" for k, v in cert.labor_by_kind.items() if v)
        or "keine Positionen"
    )
    body = "\n\n".join(
        [
            f"für das Kalenderjahr {cert.year} werden die in der Betriebskostenabrechnung "
            "enthaltenen Positionen mit Lohnanteil nachrichtlich wie folgt ausgewiesen:",
            "[[table:positions]]",
            f"Auf die Einheit entfallender Lohnanteil nach Verteilungsanteil: {kinds}.",
            "Die Aufstellung ist eine Einschätzung auf Grundlage der erfassten Belege "
            "(Lohnanteil laut Rechnung oder Schätzung). Ob und in welcher Höhe eine "
            "Steuerermäßigung in Betracht kommt, entscheidet das Finanzamt; die Angaben "
            "sind mit dem Steuerberater abzustimmen.",
        ]
    )
    letter = letters.Letter(
        recipient_lines=await _recipient_lines(session, contract),
        subject=(
            f"Ausweis haushaltsnaher Dienstleistungen und Handwerkerleistungen {cert.year}, "
            f"{prop.name if prop is not None else ''} "
            f"{('Einheit ' + str(unit.number)) if unit is not None and unit.number else ''}"
        ).strip(),
        body=body,
        letter_date=local_today(),
        info=[("Vertrag", contract.number), ("Jahr", str(cert.year))],
        tables={"positions": table},
        notice=DRAFT_NOTICE,
        draft_notice="ENTWURF",
    )
    return letters.render_pdf(head, letter)


@router.get(
    "/section35a/certificate",
    summary="§-35a-Ausweis je Mietvertrag berechnen (Einschätzung, Entwurf)",
)
async def certificate(
    request: Request,
    contract_id: uuid.UUID,
    year: int = Query(ge=2000, le=2100),
    share_percent: Decimal = Query(default=Decimal(100), ge=0, le=100),
    principal: TenantPrincipal = Depends(READ),
) -> CertificateOut:
    async with tenant_tx(request, principal) as session:
        _, cert = await _certificate(session, contract_id, year, share_percent, principal.tenant_id)
        return cert


@router.get("/section35a/certificate.pdf", summary="§-35a-Ausweis als PDF-Entwurf")
async def certificate_pdf(
    request: Request,
    contract_id: uuid.UUID,
    year: int = Query(ge=2000, le=2100),
    share_percent: Decimal = Query(default=Decimal(100), ge=0, le=100),
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    async with tenant_tx(request, principal) as session:
        contract, cert = await _certificate(
            session, contract_id, year, share_percent, principal.tenant_id
        )
        pdf = await _certificate_pdf(session, request, contract, cert)
        await _log_certificate(session, principal, cert, "pdf")
        filename = f"35a-{cert.year}-{contract.number}-entwurf.pdf"
        return Response(
            pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )


@router.post(
    "/section35a/certificate/document",
    status_code=201,
    summary="§-35a-Ausweis als Entwurf im Dokumentenindex ablegen",
)
async def certificate_document(
    request: Request,
    contract_id: uuid.UUID,
    year: int = Query(ge=2000, le=2100),
    share_percent: Decimal = Query(default=Decimal(100), ge=0, le=100),
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    from mhvp.documents import services as doc_services
    from mhvp.documents.blobs import BlobStore

    async with tenant_tx(request, principal) as session:
        contract, cert = await _certificate(
            session, contract_id, year, share_percent, principal.tenant_id
        )
        pdf = await _certificate_pdf(session, request, contract, cert)
        document = await doc_services.store_document(
            session,
            BlobStore(request.app.state.settings),
            tenant_id=principal.tenant_id,
            data=pdf,
            title=f"§-35a-Ausweis {cert.year} (Entwurf), Vertrag {contract.number}",
            filename=f"35a-{cert.year}-{contract.number}-entwurf.pdf",
            mime_type="application/pdf",
            source=DocumentSource.GENERATED,
            category_id=None,
            links=[("contract", contract.id, LinkRole.GENERATED)],
            created_by=principal.user_id,
            scan_for_malware=False,
            settings=request.app.state.settings,
        )
        await _log_certificate(session, principal, cert, "document", document.id)
        return {
            "document_id": str(document.id),
            "contract_id": str(contract.id),
            "year": year,
            "repeat_notice": cert.repeat_notice,
        }
