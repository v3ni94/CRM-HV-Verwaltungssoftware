"""Outgoing invoice numbering (operator decision 25.09.2026, docs/OPEN_QUESTIONS.md M13-04):
format ``PREFIX-JJJJ-000001``, gapless and per tenant and calendar year.

Only the Verwalterhonorar (admin fee) path in this module calls ``allocate_invoice_number``.
The dunning fee invoice path (``mhvp.accounting.dunning``) is developed concurrently by another
agent and wires its own call to this function; see the note in ``docs/plans/M13.md``.
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import InvoiceNumberCounter, TenantBillingSettings, VatStatus


def format_invoice_number(prefix: str, year: int, number: int) -> str:
    return f"{prefix}-{year:04d}-{number:06d}"


async def allocate_invoice_number(session: AsyncSession, tenant_id: object, year: int) -> str:
    """Allocate the next gapless invoice number for the tenant and year.

    Locks the per tenant/prefix/year counter row (mirroring
    ``mhvp.accounting.models.JournalNumberCounter``), so concurrent callers serialize on it
    instead of colliding. Raises MHVP-BILL-0001 when no ``invoice_prefix`` is configured yet.
    """
    settings = await session.scalar(
        select(TenantBillingSettings).where(TenantBillingSettings.tenant_id == tenant_id)
    )
    if settings is None or not settings.invoice_prefix:
        raise ProblemError(
            ErrorCodes.BILLING_PREFIX_MISSING,
            detail="Rechnungskürzel ist für diesen Mandanten nicht eingerichtet.",
        )
    prefix = settings.invoice_prefix
    await session.execute(
        insert(InvoiceNumberCounter)
        .values(tenant_id=tenant_id, prefix=prefix, year=year, last_number=0)
        .on_conflict_do_nothing()
    )
    counter = await session.scalar(
        select(InvoiceNumberCounter)
        .where(
            InvoiceNumberCounter.tenant_id == tenant_id,
            InvoiceNumberCounter.prefix == prefix,
            InvoiceNumberCounter.year == year,
        )
        .with_for_update()
    )
    if counter is None:  # pragma: no cover - inserted above
        raise ProblemError(ErrorCodes.CONFLICT)
    counter.last_number += 1
    await session.flush()
    return format_invoice_number(prefix, year, counter.last_number)


def assert_xrechnung_allowed(settings: TenantBillingSettings | None) -> None:
    """Blocks XRechnung generation when the tax data required by M13-04 is missing."""
    if settings is None or settings.vat_status is VatStatus.UNSET:
        raise ProblemError(
            ErrorCodes.BILLING_VAT_STATUS_MISSING,
            detail=(
                "Umsatzsteuerstatus des Mandanten ist nicht eingetragen "
                "(regelbesteuert oder Kleinunternehmer)."
            ),
        )
    if settings.vat_status is VatStatus.REGELBESTEUERT and not (
        settings.vat_id or settings.tax_number
    ):
        raise ProblemError(
            ErrorCodes.BILLING_TAX_DATA_MISSING,
            detail="Für regelbesteuerte Mandanten fehlt USt-IdNr. oder Steuernummer.",
        )
    if settings.vat_status is VatStatus.KLEINUNTERNEHMER and not settings.kleinunternehmer_note:
        raise ProblemError(
            ErrorCodes.BILLING_TAX_DATA_MISSING,
            detail="Pflichthinweistext für Kleinunternehmer-Rechnungen ist nicht hinterlegt.",
        )
