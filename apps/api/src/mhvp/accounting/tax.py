"""Tax proposals for incoming invoices (M14-02, M14-03, M14-04): deterministic, recomputable
values with the source status "zu prüfen durch Steuerberater". Nothing here posts, withholds
or approves; every result is a draft that a person confirms (rule 0.1.6, 7.4).

Pure functions carry the arithmetic (unit tests with precomputed values); the async helpers
read the drafts of a tenant and refresh the proposals stored in ``InvoiceTaxData``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import Invoice, InvoiceLine, Ledger, LedgerAccount, VatMode
from mhvp.accounting.tax_models import (
    SECTION_35A_KINDS,
    AccountingTaxSettings,
    InvoiceLineSection35a,
    InvoiceSecondApproval,
    InvoiceTaxData,
    PropertyTaxProfile,
    SupplierTaxProfile,
)
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties.models import LegalEntity, UnitVatOption, VatOption

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
# Marker in ``invoice_tax_data.warnings`` set by the first release (M14-03); survives refreshes.
SECOND_APPROVAL_MARKER = "Zweite Freigabe erforderlich"


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


# Pure arithmetic ---------------------------------------------------------------------------


def deductible_input_tax(
    input_tax: Decimal, *, opted: bool, revenue_key_percent: Decimal | None
) -> tuple[Decimal | None, Decimal]:
    """Deductible share of the input tax as a proposal (M14-02).

    Returns ``(percent, amount)``. Without an option or without a determined revenue key the
    percent is ``None`` and the amount 0,00: an undetermined key never yields a deduction.
    Example: 190,00 with 60 % -> (60, 114,00)."""
    if not opted or revenue_key_percent is None:
        return None, ZERO
    if revenue_key_percent < 0 or revenue_key_percent > 100:
        raise ValueError("revenue key out of range")
    return revenue_key_percent, _money(input_tax * revenue_key_percent / Decimal(100))


def exemption_valid_on(
    day: date, valid_from: date | None, valid_to: date | None, has_document: bool
) -> bool:
    """A Freistellungsbescheinigung counts only with a start date, a filed document and a
    period covering ``day`` (an open end is accepted)."""
    if valid_from is None or not has_document:
        return False
    if day < valid_from:
        return False
    return valid_to is None or day <= valid_to


def withholding_proposal(
    gross: Decimal, *, construction_service: bool, exemption_valid: bool, percent: Decimal
) -> Decimal:
    """Construction withholding tax proposal (M14-04): ``percent`` of the gross amount when a
    construction service has no valid exemption, else 0,00. Example: 1.190,00 at 15 % ->
    178,50. The value is a proposal for a person; nothing is withheld by this function."""
    if not construction_service or exemption_valid:
        return ZERO
    if percent < 0 or percent > 100:
        raise ValueError("withholding percent out of range")
    return _money(gross * percent / Decimal(100))


def role_limit(roles: tuple[str, ...] | list[str], limits: list[dict[str, Any]]) -> Decimal | None:
    """Highest configured limit among the person's roles; ``None`` when no role has a limit
    (then no second approval is required by this rule)."""
    best: Decimal | None = None
    wanted = set(roles)
    for row in limits:
        code = str(row.get("role_code", ""))
        raw = row.get("limit_amount")
        if code not in wanted or raw is None:
            continue
        value = Decimal(str(raw))
        if best is None or value > best:
            best = value
    return best


def needs_second_approval(
    gross: Decimal, roles: tuple[str, ...] | list[str], limits: list[dict[str, Any]]
) -> tuple[bool, Decimal | None]:
    """True when the absolute gross exceeds the person's role limit (M14-03). A person whose
    roles carry no limit needs no second approval; the limit itself is returned for display."""
    limit = role_limit(roles, limits)
    if limit is None:
        return False, None
    return abs(gross) > limit, limit


@dataclass
class Section35aLine:
    invoice_number: str
    invoice_date: date
    kind: str
    labor_amount: Decimal
    material_amount: Decimal
    text: str | None = None


@dataclass
class Section35aSummary:
    lines: list[Section35aLine] = field(default_factory=list)
    share_percent: Decimal = Decimal(100)

    @property
    def labor_total(self) -> Decimal:
        return sum((ln.labor_amount for ln in self.lines), ZERO)

    @property
    def material_total(self) -> Decimal:
        return sum((ln.material_amount for ln in self.lines), ZERO)

    def totals_by_kind(self) -> dict[str, Decimal]:
        out = dict.fromkeys(SECTION_35A_KINDS, ZERO)
        for ln in self.lines:
            out[ln.kind] = out.get(ln.kind, ZERO) + ln.labor_amount
        return out

    def share_by_kind(self) -> dict[str, Decimal]:
        """Labour share per kind for one tenant after the allocation share (rounded per kind).
        Example: 1.000,00 craftsman labour at 12,5 % -> 125,00."""
        return {
            kind: _money(total * self.share_percent / Decimal(100))
            for kind, total in self.totals_by_kind().items()
        }


# Data access ---------------------------------------------------------------------------------


async def settings_of(session: AsyncSession, tenant_id: uuid.UUID) -> AccountingTaxSettings:
    row = await session.scalar(select(AccountingTaxSettings))
    if row is None:
        row = AccountingTaxSettings(tenant_id=tenant_id)
        session.add(row)
        await session.flush()
    return row


async def property_of_ledger(session: AsyncSession, ledger: Ledger) -> uuid.UUID | None:
    entity = await session.get(LegalEntity, ledger.legal_entity_id)
    return entity.property_id if entity is not None else None


async def property_opted(
    session: AsyncSession, property_id: uuid.UUID | None
) -> tuple[bool, Decimal | None]:
    if property_id is None:
        return False, None
    profile = await session.scalar(
        select(PropertyTaxProfile).where(PropertyTaxProfile.property_id == property_id)
    )
    if profile is None:
        return False, None
    return profile.vat_opted, profile.revenue_key_percent


async def unit_opted_on(session: AsyncSession, unit_id: uuid.UUID, day: date) -> bool:
    """Unit level VAT option valid on ``day`` (6.9, ``unit_vat_option``)."""
    rows = await session.scalars(select(UnitVatOption).where(UnitVatOption.unit_id == unit_id))
    for row in rows:
        if row.option is VatOption.NONE:
            continue
        if row.valid_from <= day and (row.valid_to is None or day <= row.valid_to):
            return True
    return False


async def input_tax_account_exists(
    session: AsyncSession, ledger_id: uuid.UUID, number: str
) -> bool:
    row = await session.scalar(
        select(LedgerAccount.id).where(
            LedgerAccount.ledger_id == ledger_id, LedgerAccount.number == number
        )
    )
    return row is not None


async def refresh_proposals(
    session: AsyncSession, invoice: Invoice, data: InvoiceTaxData
) -> InvoiceTaxData:
    """Recompute the proposals and warnings of ``data`` from the current drafts. Idempotent;
    an approved withholding amount is voided when the proposal changes."""
    settings = await settings_of(session, invoice.tenant_id)
    ledger = await session.get(Ledger, invoice.ledger_id)
    warnings: list[str] = [w for w in data.warnings if w == SECOND_APPROVAL_MARKER]
    property_id = await property_of_ledger(session, ledger) if ledger is not None else None
    opted, key = await property_opted(session, property_id)
    lines = list(
        (
            await session.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))
        ).all()
    )
    if not opted:
        # A unit level option (commercial unit with option, 6.9) counts as an opted object
        # for the lines assigned to that unit; the revenue key still comes from the property.
        for ln in lines:
            if ln.unit_id is not None and await unit_opted_on(
                session, ln.unit_id, invoice.invoice_date
            ):
                opted = True
                break
    input_tax = data.input_tax_amount if data.input_tax_amount is not None else invoice.vat
    if settings.input_tax_enabled:
        percent, amount = deductible_input_tax(input_tax, opted=opted, revenue_key_percent=key)
        data.deductible_percent, data.deductible_input_tax = percent, amount
        if opted and key is None:
            warnings.append("Umsatzschlüssel des Objekts fehlt, kein Vorsteuerabzug vorgeschlagen")
        if not opted and input_tax:
            warnings.append("Objekt ohne Umsatzsteueroption, Steuer bleibt Kostenbestandteil")
        number = settings.input_tax_account_number
        if number is None:
            warnings.append("Vorsteuerkonto ist in den Steuereinstellungen nicht hinterlegt")
        elif ledger is not None and not await input_tax_account_exists(session, ledger.id, number):
            warnings.append(f"Vorsteuerkonto {number} fehlt im Kontenrahmen des Buchungskreises")
        if ledger is not None and ledger.vat_mode is VatMode.NONE and opted:
            warnings.append("Buchungskreis ohne Umsatzsteueroption (vat_mode none), Widerspruch")
    else:
        data.deductible_percent, data.deductible_input_tax = None, None
    if data.reverse_charge:
        warnings.append(
            "Möglicher Fall des § 13b UStG: gesonderter Freigabepunkt, keine Automatik "
            "(Normzuordnung durch den Steuerberater, R23)"
        )
    if data.reverse_charge and invoice.vat:
        warnings.append("Reverse Charge gekennzeichnet, Rechnung weist dennoch Steuer aus")
    supplier = await session.scalar(
        select(SupplierTaxProfile).where(
            SupplierTaxProfile.contact_id == invoice.provider_contact_id
        )
    )
    exemption_valid = supplier is not None and exemption_valid_on(
        invoice.invoice_date,
        supplier.exemption_valid_from,
        supplier.exemption_valid_to,
        supplier.exemption_document_id is not None,
    )
    if settings.construction_withholding_enabled and data.construction_service:
        percent = settings.construction_withholding_percent
        proposal = withholding_proposal(
            invoice.gross,
            construction_service=True,
            exemption_valid=exemption_valid,
            percent=percent,
        )
        if not exemption_valid:
            warnings.append(
                "Freistellungsbescheinigung fehlt oder ist am Rechnungsdatum ungültig, "
                f"Einbehalt von {percent.normalize()} Prozent vorgeschlagen (Entwurf, keine "
                "automatische Kürzung)"
            )
        data.withholding_percent, data.withholding_proposal = percent, proposal
    else:
        if data.construction_service and not settings.construction_withholding_enabled:
            warnings.append(
                "Bauleistung gekennzeichnet, Prüfung Bauabzugsteuer ist nicht aktiviert"
            )
        data.withholding_percent, data.withholding_proposal = None, None
    if data.withholding_approved_amount is not None and data.withholding_approved_amount != (
        data.withholding_proposal or ZERO
    ):
        data.withholding_approved_by = None
        data.withholding_approved_at = None
        data.withholding_approved_amount = None
        warnings.append("Freigabe des Einbehalts entfällt, der Vorschlag hat sich geändert")
    data.warnings = warnings
    await session.flush()
    return data


async def tax_data_of(session: AsyncSession, invoice: Invoice) -> InvoiceTaxData:
    row = await session.scalar(
        select(InvoiceTaxData).where(InvoiceTaxData.invoice_id == invoice.id)
    )
    if row is None:
        row = InvoiceTaxData(tenant_id=invoice.tenant_id, invoice_id=invoice.id)
        session.add(row)
        await session.flush()
    return row


async def approve_withholding(
    session: AsyncSession, invoice: Invoice, user_id: uuid.UUID
) -> InvoiceTaxData:
    """A person other than the creator confirms the proposed withholding amount (draft)."""
    data = await refresh_proposals(session, invoice, await tax_data_of(session, invoice))
    if not data.withholding_proposal:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Kein Einbehalt vorgeschlagen.")
    if invoice.created_by == user_id:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES, detail="Die Freigabe muss eine andere Person erteilen."
        )
    data.withholding_approved_by = user_id
    data.withholding_approved_at = datetime.now(UTC)
    data.withholding_approved_amount = data.withholding_proposal
    await session.flush()
    return data


async def second_approval_state(
    session: AsyncSession, invoice: Invoice, roles: tuple[str, ...]
) -> dict[str, Any]:
    """Evaluation of the role limits for the releasing person (M14-03)."""
    from mhvp.accounting.invoices import payment_hash

    settings = await settings_of(session, invoice.tenant_id)
    required, limit = (
        needs_second_approval(invoice.gross, roles, settings.approval_limits)
        if settings.approval_limits_enabled
        else (False, None)
    )
    row = await session.scalar(
        select(InvoiceSecondApproval).where(InvoiceSecondApproval.invoice_id == invoice.id)
    )
    valid = (
        row is not None
        and row.invoice_version == invoice.version
        and row.payment_hash == payment_hash(invoice)
    )
    return {
        "enabled": settings.approval_limits_enabled,
        "limit_amount": limit,
        "second_approval_required": required,
        "second_approval_valid": valid,
        "second_approved_by": row.user_id if valid and row is not None else None,
    }


async def second_approval_required_for_release(
    session: AsyncSession, invoice: Invoice, roles: tuple[str, ...]
) -> bool:
    state = await second_approval_state(session, invoice, roles)
    return bool(state["second_approval_required"])


async def add_second_approval(
    session: AsyncSession, invoice: Invoice, user_id: uuid.UUID
) -> InvoiceSecondApproval:
    """Second approval by a third person: neither the creator nor the first releaser."""
    from mhvp.accounting.invoices import payment_hash

    settings = await settings_of(session, invoice.tenant_id)
    if not settings.approval_limits_enabled:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Betragsgrenzen sind nicht aktiviert.")
    if invoice.released_by is None or invoice.released_hash != payment_hash(invoice):
        raise ProblemError(ErrorCodes.CONFLICT, detail="Die erste Freigabe fehlt.")
    if user_id in (invoice.created_by, invoice.released_by):
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES,
            detail="Die zweite Freigabe muss eine dritte Person erteilen.",
        )
    row = await session.scalar(
        select(InvoiceSecondApproval).where(InvoiceSecondApproval.invoice_id == invoice.id)
    )
    if row is None:
        row = InvoiceSecondApproval(
            tenant_id=invoice.tenant_id, invoice_id=invoice.id, user_id=user_id
        )
        session.add(row)
    row.user_id = user_id
    row.invoice_version = invoice.version
    row.payment_hash = payment_hash(invoice)
    row.limit_amount = None
    await session.flush()
    # S69-02: central decision next to the legacy record.
    from mhvp.accounting import approval_decisions

    await approval_decisions.record(
        session,
        tenant_id=invoice.tenant_id,
        subject_type="invoice",
        subject_id=invoice.id,
        step="second_approval",
        user_id=user_id,
        snapshot_hash=row.payment_hash,
        legacy_ref_id=row.id,
    )
    return row


async def assert_posting_allowed(session: AsyncSession, invoice: Invoice) -> None:
    """Hook for ``invoices.post`` (M14-03, M14-04): a required second approval and an
    unapproved withholding proposal block the posting. Silent when the switches are off."""
    from mhvp.accounting.invoices import payment_hash

    settings = await session.scalar(select(AccountingTaxSettings))
    if settings is None:
        return
    if settings.approval_limits_enabled:
        row = await session.scalar(
            select(InvoiceSecondApproval).where(InvoiceSecondApproval.invoice_id == invoice.id)
        )
        # Not the roles of the poster but the recorded requirement decides: the release stored
        # ``limit_amount`` when the releaser's limit was exceeded (see routers).
        needed = await session.scalar(
            select(InvoiceTaxData.id).where(
                InvoiceTaxData.invoice_id == invoice.id,
                InvoiceTaxData.warnings.contains([SECOND_APPROVAL_MARKER]),
            )
        )
        if needed is not None and (
            row is None
            or row.invoice_version != invoice.version
            or row.payment_hash != payment_hash(invoice)
        ):
            raise ProblemError(
                ErrorCodes.ACC_APPROVAL_LIMIT,
                detail="Rechnung über der Freigabegrenze, zweite Freigabe fehlt (M14-03).",
            )
    if settings.construction_withholding_enabled:
        data = await session.scalar(
            select(InvoiceTaxData).where(InvoiceTaxData.invoice_id == invoice.id)
        )
        if data is not None and data.withholding_proposal and data.withholding_approved_by is None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Einbehalt Bauabzugsteuer ist vorgeschlagen und nicht entschieden (M14-04).",
            )


async def mark_second_approval_required(
    session: AsyncSession, invoice: Invoice, required: bool
) -> None:
    """Records in the invoice's tax data whether the first release exceeded the role limit."""
    data = await tax_data_of(session, invoice)
    warnings = [w for w in data.warnings if w != SECOND_APPROVAL_MARKER]
    if required:
        warnings.append(SECOND_APPROVAL_MARKER)
    data.warnings = warnings
    await session.flush()


async def section35a_lines_of_invoice(
    session: AsyncSession, invoice_id: uuid.UUID
) -> list[InvoiceLineSection35a]:
    return list(
        (
            await session.scalars(
                select(InvoiceLineSection35a).where(InvoiceLineSection35a.invoice_id == invoice_id)
            )
        ).all()
    )


async def section35a_summary(
    session: AsyncSession,
    *,
    property_id: uuid.UUID,
    year: int,
    unit_id: uuid.UUID | None,
    share_percent: Decimal,
) -> Section35aSummary:
    """Marked lines of the property's ledgers in ``year``. Lines assigned to a unit count only
    for that unit; unassigned lines are shared by ``share_percent`` (allocation share of the
    tenant, given by the caller, draft until the operating cost statement supplies it)."""
    ledger_ids = list(
        (
            await session.scalars(
                select(Ledger.id)
                .join(LegalEntity, LegalEntity.id == Ledger.legal_entity_id)
                .where(LegalEntity.property_id == property_id)
            )
        ).all()
    )
    summary = Section35aSummary(share_percent=share_percent)
    if not ledger_ids:
        return summary
    rows = (
        await session.execute(
            select(InvoiceLineSection35a, InvoiceLine, Invoice)
            .join(InvoiceLine, InvoiceLine.id == InvoiceLineSection35a.invoice_line_id)
            .join(Invoice, Invoice.id == InvoiceLineSection35a.invoice_id)
            .where(
                Invoice.ledger_id.in_(ledger_ids),
                Invoice.invoice_date >= date(year, 1, 1),
                Invoice.invoice_date <= date(year, 12, 31),
            )
            .order_by(Invoice.invoice_date, Invoice.number)
        )
    ).all()
    direct: list[Section35aLine] = []
    shared: list[Section35aLine] = []
    for marker, line, invoice in rows:
        item = Section35aLine(
            invoice.number,
            invoice.invoice_date,
            marker.kind,
            marker.labor_amount,
            marker.material_amount,
            marker.text or line.text,
        )
        if line.unit_id is not None:
            if unit_id is not None and line.unit_id == unit_id:
                direct.append(item)
            continue
        shared.append(item)
    # Direct lines belong to the unit in full: apply the share only to shared lines by
    # scaling them once here so ``share_by_kind`` stays a single formula.
    scaled = [
        Section35aLine(
            s.invoice_number,
            s.invoice_date,
            s.kind,
            _money(s.labor_amount * share_percent / Decimal(100)),
            _money(s.material_amount * share_percent / Decimal(100)),
            s.text,
        )
        for s in shared
    ]
    summary.lines = direct + scaled
    summary.share_percent = Decimal(100)
    return summary
