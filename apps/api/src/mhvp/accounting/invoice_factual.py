"""Factual review of the incoming invoice as findings (7.9.1 PÜ02, M14-02, PU02-SACHLICH).

The invoice is compared against its work order (structured link instead of free text; the free
text ``order_reference`` stays), the service contract, the WEG resolution, the budget (economic
plan item), the recurring invoice plan (issuer, amount, rhythm) and the line arithmetic of
quantity and unit price. The responsible person (property manager of the property) is a
proposal only. Every result is a finding: nothing here sets a review status, releases, posts
or pays (PÜ05). Tolerances are a tenant setting in percent, default 0 (exact match).
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import (
    Invoice,
    InvoiceCheckSetting,
    InvoiceKind,
    InvoiceLine,
    Ledger,
    PostingStatus,
    RecurringInvoicePlan,
)

CENT = Decimal("0.01")
ZERO = Decimal("0")
# Resolution states that carry a decision in favour of the measure (hoa.models.Resolution).
EFFECTIVE_RESOLUTION = {"positive", "final", "legally_binding"}
# Work order states before the order was placed: an invoice on them is unusual.
ORDER_NOT_PLACED = {"draft", "requested", "quoted"}
ORDER_CLOSED = {"rejected", "cancelled"}


@dataclass
class Tolerances:
    price_percent: Decimal = ZERO
    quantity_percent: Decimal = ZERO


@dataclass
class FactualResult:
    findings: list[dict[str, str]] = field(default_factory=list)
    suggested_reviewer_user_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    # P03-03 (AE14): structured budget comparison and resolution coverage, hints only.
    budget: dict[str, Any] | None = None
    resolution: dict[str, Any] | None = None

    def add(self, area: str, code: str, message: str) -> None:
        self.findings.append({"area": area, "code": code, "message": message})

    def messages(self) -> list[str]:
        return [f["message"] for f in self.findings]


def within(actual: Decimal, expected: Decimal, percent: Decimal) -> bool:
    """|actual - expected| <= expected * percent / 100, rounded to the cent."""
    allowed = (abs(expected) * percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    return abs(actual - expected) <= allowed


def months_between(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + later.month - earlier.month


def _eur(value: Decimal) -> str:
    q = value.quantize(CENT, rounding=ROUND_HALF_UP)
    whole, frac = f"{abs(q):.2f}".split(".")
    groups = f"{int(whole):,}".replace(",", ".")
    return f"{'-' if q < 0 else ''}{groups},{frac} EUR"


def line_findings(lines: list[InvoiceLine], tol: Tolerances, out: FactualResult) -> None:
    """Quantity times unit price against the line net (quantity tolerance)."""
    for idx, ln in enumerate(lines, start=1):
        if ln.quantity is None and ln.unit_price is None:
            continue
        if ln.quantity is None or ln.unit_price is None:
            out.add("quantity", "line_incomplete", f"Position {idx}: Menge oder Einzelpreis fehlt")
            continue
        if ln.quantity <= 0:
            out.add("quantity", "line_quantity", f"Position {idx}: Menge ist nicht positiv")
        expected = (ln.quantity * ln.unit_price).quantize(CENT, rounding=ROUND_HALF_UP)
        if not within(ln.net, expected, tol.quantity_percent):
            out.add(
                "quantity",
                "line_mismatch",
                f"Position {idx}: Menge mal Einzelpreis ergibt {_eur(expected)},"
                f" ausgewiesen {_eur(ln.net)}",
            )


async def load_tolerances(session: AsyncSession) -> Tolerances:
    row = await session.scalar(select(InvoiceCheckSetting))
    if row is None:
        return Tolerances()
    return Tolerances(row.price_tolerance_percent, row.quantity_tolerance_percent)


async def _work_order(session: AsyncSession, invoice: Invoice) -> Any:
    from mhvp.tickets.models import WorkOrder

    if invoice.work_order_id is not None:
        return await session.get(WorkOrder, invoice.work_order_id)
    # Reverse link kept by the tickets domain (WorkOrder.invoice_id).
    return await session.scalar(
        select(WorkOrder).where(WorkOrder.invoice_id == invoice.id).limit(1)
    )


async def order_findings(
    session: AsyncSession,
    invoice: Invoice,
    ledger: Ledger | None,
    tol: Tolerances,
    out: FactualResult,
) -> Any:
    order = await _work_order(session, invoice)
    if order is None:
        if invoice.work_order_id is not None:
            out.add("order", "order_missing", "Verknüpfter Auftrag nicht gefunden")
        elif invoice.order_reference and invoice.service_contract_id is None:
            out.add(
                "order",
                "order_free_text",
                "Auftragsbezug nur als Freitext: Auftrag verknüpfen (sachliche Prüfung)",
            )
        return None
    if order.provider_contact_id != invoice.provider_contact_id:
        out.add("order", "order_provider", "Auftrag wurde an einen anderen Dienstleister erteilt")
    if ledger is not None and ledger.property_id and order.property_id != ledger.property_id:
        out.add("order", "order_property", "Auftrag gehört zu einem anderen Objekt")
    status = str(getattr(order.status, "value", order.status))
    if status in ORDER_NOT_PLACED:
        out.add(
            "order", "order_not_placed", "Auftrag ist noch nicht erteilt (Status " + status + ")"
        )
    elif status in ORDER_CLOSED:
        out.add("order", "order_closed", "Auftrag ist abgelehnt oder storniert")
    if order.invoice_id is not None and order.invoice_id != invoice.id:
        out.add("order", "order_invoiced", "Auftrag ist bereits einer anderen Rechnung zugeordnet")
    if order.quote_amount is not None and not within(
        invoice.gross, order.quote_amount, tol.price_percent
    ):
        out.add(
            "price",
            "price_quote",
            f"Rechnungsbetrag {_eur(invoice.gross)} weicht vom Angebot"
            f" {_eur(order.quote_amount)} ab (Toleranz {tol.price_percent} %)",
        )
    if order.budget_limit is not None and invoice.gross > order.budget_limit:
        out.add(
            "price",
            "price_budget_limit",
            "Rechnungsbetrag übersteigt die Kostengrenze des Auftrags"
            f" ({_eur(order.budget_limit)})",
        )
    if order.requires_board_approval and order.approved_by is None:
        out.add("order", "order_board", "Auftrag erfordert eine Zustimmung, die nicht erfasst ist")
    return order


async def resolution_findings(
    session: AsyncSession, invoice: Invoice, ledger: Ledger | None, out: FactualResult
) -> None:
    if invoice.resolution_id is None:
        return
    from mhvp.hoa.models import Resolution

    res = await session.get(Resolution, invoice.resolution_id)
    if res is None:
        out.add("resolution", "resolution_missing", "Verknüpfter Beschluss nicht gefunden")
        return
    if ledger is not None and res.legal_entity_id != ledger.legal_entity_id:
        out.add(
            "resolution",
            "resolution_entity",
            "Beschluss gehört zu einer anderen Gemeinschaft als der Buchungskreis",
        )
    if res.status not in EFFECTIVE_RESOLUTION:
        out.add(
            "resolution",
            "resolution_status",
            f"Beschluss Nr. {res.number} hat den Status {res.status}: Grundlage prüfen",
        )
    if (invoice.service_from or invoice.invoice_date) < res.decided_on:
        out.add("resolution", "resolution_before", "Leistung beginnt vor dem Beschlussdatum")
    plan_id = None
    if invoice.plan_item_id is not None:
        from mhvp.hoa.models import PlanItem

        item = await session.get(PlanItem, invoice.plan_item_id)
        plan_id = item.plan_id if item is not None else None
    subject_match: bool | None = None
    if res.subject_type == "economic_plan" and res.subject_id is not None and plan_id is not None:
        subject_match = res.subject_id == plan_id
        if not subject_match:
            out.add(
                "resolution",
                "resolution_subject_mismatch",
                f"Beschluss Nr. {res.number} betrifft einen anderen Wirtschaftsplan als die"
                " verknüpfte Planposition",
            )
    out.resolution = {
        "resolution_id": res.id,
        "number": res.number,
        "decided_on": res.decided_on,
        "status": res.status,
        "subject": res.subject,
        "subject_type": res.subject_type,
        "effective": res.status in EFFECTIVE_RESOLUTION,
        "subject_matches_plan": subject_match,
    }


async def budget_findings(
    session: AsyncSession,
    invoice: Invoice,
    ledger: Ledger | None,
    lines: list[InvoiceLine],
    tol: Tolerances,
    out: FactualResult,
) -> None:
    if invoice.plan_item_id is None:
        return
    from mhvp.hoa.models import EconomicPlan, PlanItem

    item = await session.get(PlanItem, invoice.plan_item_id)
    plan = await session.get(EconomicPlan, item.plan_id) if item else None
    if item is None or plan is None:
        out.add("budget", "budget_missing", "Verknüpfte Wirtschaftsplanposition nicht gefunden")
        return
    if plan.ledger_id != invoice.ledger_id:
        out.add("budget", "budget_ledger", "Wirtschaftsplan gehört zu einem anderen Buchungskreis")
    if (invoice.service_from or invoice.invoice_date).year != plan.year:
        out.add("budget", "budget_year", f"Leistung liegt nicht im Wirtschaftsjahr {plan.year}")
    if (
        item.account_id is not None
        and lines
        and all(ln.account_id != item.account_id for ln in lines)
    ):
        out.add(
            "budget", "budget_account", "Kein Rechnungskonto entspricht dem Konto der Planposition"
        )
    used = await session.scalar(
        select(func.coalesce(func.sum(Invoice.gross), 0)).where(
            Invoice.plan_item_id == item.id,
            Invoice.id != invoice.id,
            Invoice.kind != InvoiceKind.CREDIT_NOTE,
            Invoice.posting_status != PostingStatus.REVERSED,
        )
    )
    credited = await session.scalar(
        select(func.coalesce(func.sum(Invoice.gross), 0)).where(
            Invoice.plan_item_id == item.id,
            Invoice.id != invoice.id,
            Invoice.kind == InvoiceKind.CREDIT_NOTE,
            Invoice.posting_status != PostingStatus.REVERSED,
        )
    )
    own = -invoice.gross if invoice.kind is InvoiceKind.CREDIT_NOTE else invoice.gross
    total = Decimal(used or 0) - Decimal(credited or 0) + own
    limit = item.amount + (item.amount * tol.price_percent / 100).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
    booked_before = (Decimal(used or 0) - Decimal(credited or 0)).quantize(CENT)
    out.budget = {
        "plan_item_id": item.id,
        "label": item.label,
        "year": plan.year,
        "planned": item.amount,
        "booked_before": booked_before,
        "invoice": own,
        "remaining": (item.amount - booked_before - own).quantize(CENT),
        "tolerance_limit": limit,
        "exceeded": total > limit,
    }
    if total > limit:
        out.add(
            "budget",
            "budget_exceeded",
            f"Planansatz {item.label} {_eur(item.amount)} überschritten: mit dieser Rechnung"
            f" {_eur(total)}",
        )


async def recurring_findings(
    session: AsyncSession, invoice: Invoice, tol: Tolerances, out: FactualResult
) -> None:
    plan: RecurringInvoicePlan | None = None
    if invoice.recurring_plan_id is not None:
        plan = await session.get(RecurringInvoicePlan, invoice.recurring_plan_id)
        if plan is None:
            out.add("recurring", "recurring_missing", "Verknüpfter Rechnungsplan nicht gefunden")
            return
    else:
        candidates = (
            await session.scalars(
                select(RecurringInvoicePlan).where(
                    RecurringInvoicePlan.ledger_id == invoice.ledger_id,
                    RecurringInvoicePlan.provider_contact_id == invoice.provider_contact_id,
                    RecurringInvoicePlan.ended_at.is_(None),
                )
            )
        ).all()
        match = next((p for p in candidates if p.gross == invoice.gross), None)
        if match is not None:
            out.add(
                "recurring",
                "recurring_unlinked",
                f"Betrag entspricht dem Rechnungsplan {match.text}:"
                " Wiederkehr prüfen und verknüpfen",
            )
        elif invoice.kind is InvoiceKind.RECURRING:
            out.add("recurring", "recurring_no_plan", "Dauerrechnung ohne Rechnungsplan")
        return
    if plan.provider_contact_id != invoice.provider_contact_id:
        out.add(
            "recurring", "recurring_provider", "Rechnungsplan gehört zu einem anderen Aussteller"
        )
    if not within(invoice.gross, plan.gross, tol.price_percent):
        out.add(
            "recurring",
            "recurring_amount",
            f"Betrag {_eur(invoice.gross)} weicht vom Rechnungsplan {_eur(plan.gross)} ab",
        )
    if invoice.invoice_date < plan.start_date or (
        (plan.ended_at or plan.end_date) is not None
        and invoice.invoice_date > (plan.ended_at or plan.end_date)  # type: ignore[operator]
    ):
        out.add(
            "recurring", "recurring_period", "Rechnungsdatum liegt außerhalb des Rechnungsplans"
        )
    previous = await session.scalar(
        select(Invoice.invoice_date)
        .where(
            Invoice.recurring_plan_id == plan.id,
            Invoice.id != invoice.id,
            Invoice.invoice_date < invoice.invoice_date,
            Invoice.posting_status != PostingStatus.REVERSED,
        )
        .order_by(Invoice.invoice_date.desc())
        .limit(1)
    )
    if previous is not None:
        gap = months_between(previous, invoice.invoice_date)
        if gap != plan.interval_months:
            out.add(
                "recurring",
                "recurring_rhythm",
                f"Abstand zur Vorrechnung {gap} Monat(e), Rechnungsplan sieht"
                f" {plan.interval_months} vor",
            )
    same_month = await session.scalar(
        select(func.count())
        .select_from(Invoice)
        .where(
            Invoice.recurring_plan_id == plan.id,
            Invoice.id != invoice.id,
            func.date_trunc("month", Invoice.invoice_date)
            == func.date_trunc("month", invoice.invoice_date),
            Invoice.posting_status != PostingStatus.REVERSED,
        )
    )
    if same_month:
        out.add(
            "recurring", "recurring_twice", "Rechnungsplan hat in diesem Monat schon eine Rechnung"
        )


async def responsibility(
    session: AsyncSession, invoice: Invoice, ledger: Ledger | None, order: Any, out: FactualResult
) -> None:
    """Proposal of the responsible reviewer: property manager of the property."""
    from mhvp.properties.models import Property

    property_id = ledger.property_id if ledger is not None else None
    if property_id is None and order is not None:
        property_id = order.property_id
    if property_id is None and invoice.service_contract_id is not None:
        from mhvp.contracts.service_contracts import ServiceContract

        contract = await session.get(ServiceContract, invoice.service_contract_id)
        property_id = contract.property_id if contract else None
    out.property_id = property_id
    prop = await session.get(Property, property_id) if property_id else None
    if prop is None:
        out.add("responsibility", "no_property", "Kein Objekt zuordenbar: Zuständigkeit klären")
        return
    if prop.manager_user_id is None:
        out.add(
            "responsibility",
            "no_manager",
            "Am Objekt ist kein Objektverwalter hinterlegt: Zuständigkeit klären",
        )
        return
    out.suggested_reviewer_user_id = prop.manager_user_id


async def factual_check(session: AsyncSession, invoice: Invoice) -> FactualResult:
    out = FactualResult()
    tol = await load_tolerances(session)
    ledger = await session.get(Ledger, invoice.ledger_id)
    lines = list(
        (
            await session.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))
        ).all()
    )
    order = await order_findings(session, invoice, ledger, tol, out)
    await resolution_findings(session, invoice, ledger, out)
    await budget_findings(session, invoice, ledger, lines, tol, out)
    if (
        invoice.resolution_id is None
        and order is not None
        and getattr(order, "requires_board_approval", False)
    ):
        out.add(
            "resolution",
            "resolution_none_with_order",
            "Auftrag verlangt eine Zustimmung, die Rechnung ist keinem Beschluss zugeordnet",
        )
    await recurring_findings(session, invoice, tol, out)
    line_findings(lines, tol, out)
    await responsibility(session, invoice, ledger, order, out)
    return out


def result_payload(result: FactualResult, tol: Tolerances) -> dict[str, Any]:
    return {
        "findings": result.findings,
        "suggested_reviewer_user_id": result.suggested_reviewer_user_id,
        "property_id": result.property_id,
        "price_tolerance_percent": tol.price_percent,
        "quantity_tolerance_percent": tol.quantity_percent,
        "automatic_release": False,
        "budget": result.budget,
        "resolution": result.resolution,
    }
