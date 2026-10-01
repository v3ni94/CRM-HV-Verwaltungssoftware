"""WEG asset report per reporting date (M24-02, 7.8 W11, § 28 Abs. 4 WEG as estimate).

The report of a community (GdWE) as of a date lists the reserve (Soll, Ist, use), the bank
balances per account of the legal entity, the receivables against owners, the liabilities
(open payables, owner credits, loans with residual debt) and manually entered other community
assets. Every ledger figure is reconciled against the accounting (sum checks with a visible
difference); nothing is corrected silently and nothing is posted. The report is a draft with
no legal effect until gate G4 is open for the tenant; the PDF carries the draft marking.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import ensure_session_legal_entity_allowed
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.hoa import calc
from mhvp.hoa.models import HoaAssetReport, HoaLoan
from mhvp.hoa.property_scope import HOA_GUARD

# M2-02/S16-02: WEG records outside the property assignment answer 404.
router = APIRouter(prefix="/hoa", tags=["WEG"], dependencies=[Depends(HOA_GUARD)])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")
ZERO = Decimal("0.00")
STATUSES = ("draft", "calculated", "issued")
DRAFT_NOTICE = (
    "Entwurf ohne Rechtsfolge. Gliederung und Inhalt des Vermögensberichts sind mit der "
    "Rechtsberatung abzustimmen (M24-02); Ausgabe an Eigentümer erst mit Freigabestufe G4."
)
NOTE = (
    "Vermögensbericht zum Stichtag aus der Buchhaltung des Rechtsträgers. Bankbestände, "
    "Forderungen, Verbindlichkeiten und Darlehen stammen aus gebuchten Buchungen; sonstiges "
    "Gemeinschaftsvermögen ist manuell erfasst und gesondert ausgewiesen. Abweichungen "
    "zwischen Bericht und Buchhaltung werden angezeigt und nie stillschweigend ausgeglichen."
)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ManualItemIn(_In):
    label: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(decimal_places=2)
    note: str | None = Field(default=None, max_length=500)


class AssetReportIn(_In):
    ledger_id: uuid.UUID
    as_of: date
    reserve_opening: Decimal = Field(default=ZERO, decimal_places=2)
    reserve_withdrawals: Decimal = Field(default=ZERO, ge=0, decimal_places=2)
    reserve_interest: Decimal = Field(default=ZERO, decimal_places=2)
    manual_items: list[ManualItemIn] = Field(default_factory=list, max_length=100)
    note: str | None = Field(default=None, max_length=2000)


class AssetReportPatch(_In):
    as_of: date | None = None
    reserve_opening: Decimal | None = Field(default=None, decimal_places=2)
    reserve_withdrawals: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    reserve_interest: Decimal | None = Field(default=None, decimal_places=2)
    manual_items: list[ManualItemIn] | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=2000)


class AssetReportTransitionIn(_In):
    target: str = Field(pattern="^(issued)$")


# --- computation -----------------------------------------------------------------------------


async def _category_balance(
    session: AsyncSession, ledger_id: uuid.UUID, category: Any, end: date
) -> Decimal:
    """Debit minus credit of all posted lines of the accounts of a category up to `end`."""
    from mhvp.accounting.models import EntryStatus, JournalEntry, JournalLine, LedgerAccount

    d, c = (
        await session.execute(
            select(
                func.coalesce(func.sum(JournalLine.debit), 0),
                func.coalesce(func.sum(JournalLine.credit), 0),
            )
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .join(LedgerAccount, LedgerAccount.id == JournalLine.account_id)
            .where(
                LedgerAccount.ledger_id == ledger_id,
                LedgerAccount.category == category,
                JournalEntry.status == EntryStatus.POSTED,
                JournalEntry.booking_date <= end,
            )
        )
    ).one()
    return Decimal(d) - Decimal(c)


async def _journal_sums(
    session: AsyncSession, ledger_id: uuid.UUID, end: date
) -> tuple[Decimal, Decimal]:
    from mhvp.accounting.models import EntryStatus, JournalEntry, JournalLine

    d, c = (
        await session.execute(
            select(
                func.coalesce(func.sum(JournalLine.debit), 0),
                func.coalesce(func.sum(JournalLine.credit), 0),
            )
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .where(
                JournalEntry.ledger_id == ledger_id,
                JournalEntry.status == EntryStatus.POSTED,
                JournalEntry.booking_date <= end,
            )
        )
    ).one()
    return Decimal(d), Decimal(c)


async def _bank_accounts(session: AsyncSession, ledger: Any, end: date) -> list[dict[str, Any]]:
    from mhvp.accounting.models import AccountCategory, LedgerAccount
    from mhvp.accounting.reports import _balance
    from mhvp.properties.models import BankAccountKind, PropertyBankAccount

    out = []
    accounts = (
        await session.scalars(
            select(LedgerAccount)
            .where(
                LedgerAccount.ledger_id == ledger.id,
                LedgerAccount.category.in_([AccountCategory.BANK, AccountCategory.CASH]),
            )
            .order_by(LedgerAccount.number)
        )
    ).all()
    for account in accounts:
        kind, suffix, is_reserve = None, None, account.number == "001201"
        if account.property_bank_account_id:
            bank = await session.get(PropertyBankAccount, account.property_bank_account_id)
            if bank is not None:
                kind, suffix = bank.kind.value, bank.iban_suffix
                is_reserve = bank.kind is BankAccountKind.RESERVE
        out.append(
            {
                "account_id": str(account.id),
                "number": account.number,
                "name": account.name,
                "category": account.category.value,
                "bank_kind": kind,
                "iban_suffix": suffix,
                "reserve": is_reserve,
                "balance": str(await _balance(session, account.id, end)),
            }
        )
    return out


async def _unit_numbers(session: AsyncSession, contract_ids: set[Any]) -> dict[str, str]:
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import Unit

    if not contract_ids:
        return {}
    rows = (
        await session.execute(
            select(Contract.id, Unit.number)
            .join(Unit, Unit.id == Contract.unit_id)
            .where(Contract.id.in_(list(contract_ids)))
        )
    ).all()
    return {str(cid): number for cid, number in rows}


async def _reserve(session: AsyncSession, report: HoaAssetReport, ledger: Any) -> dict[str, Any]:
    """Reserve as of the date: Soll (opening + resolved contributions of the year up to the
    date - use + interest), Ist (same with paid contributions), use, open contributions and
    the reserve bank balance with the visible difference (W08, D19: never settled)."""
    from mhvp.properties.models import Unit

    start = date(report.as_of.year, 1, 1)
    due_total = paid_total = ZERO
    units = (
        await session.scalars(select(Unit).where(Unit.property_id == ledger.property_id))
    ).all()
    for unit in units:
        due, paid = await calc.advances(session, unit.id, "reserve", start, report.as_of)
        due_total += due
        paid_total += paid
    soll = report.reserve_opening + due_total - report.reserve_withdrawals + report.reserve_interest
    ist = report.reserve_opening + paid_total - report.reserve_withdrawals + report.reserve_interest
    bank = await calc.reserve_bank_balance(session, ledger, report.as_of)
    # M24-01: development per earmarked reserve up to the year of the report (information).
    from mhvp.hoa.models import HoaReserve
    from mhvp.hoa.reserves import reserve_development

    positions = []
    for r in (
        await session.scalars(
            select(HoaReserve).where(HoaReserve.ledger_id == ledger.id).order_by(HoaReserve.name)
        )
    ).all():
        rows = await reserve_development(session, r, report.as_of.year)
        positions.append(
            {
                "reserve_id": str(r.id),
                "name": r.name,
                "bank_account_id": str(r.bank_account_id) if r.bank_account_id else None,
                "year": rows[-1],
            }
        )
    return {
        "positions": positions,
        "opening": str(report.reserve_opening),
        "contributions_resolved": str(due_total),
        "contributions_paid": str(paid_total),
        "contributions_open": str(due_total - paid_total),
        "withdrawals": str(report.reserve_withdrawals),
        "interest": str(report.reserve_interest),
        "target": str(soll),  # Soll
        "actual": str(ist),  # Ist (available funds by the accounting)
        "bank_balance": str(bank),
        "bank_difference": str(bank - ist),
        "period_from": start.isoformat(),
    }


async def _loans(session: AsyncSession, ledger: Any, end: date) -> list[dict[str, Any]]:
    from mhvp.accounting.reports import _balance

    rows = (
        await session.scalars(
            select(HoaLoan)
            .where(HoaLoan.ledger_id == ledger.id, HoaLoan.status != "closed")
            .order_by(HoaLoan.start_date, HoaLoan.lender)
        )
    ).all()
    out = []
    for loan in rows:
        figures = await calc.loan_year_figures(session, loan, end.year)
        account_balance = None
        if loan.account_id is not None:
            account_balance = ZERO - await _balance(session, loan.account_id, end)
        out.append(
            {
                "loan_id": str(loan.id),
                "lender": loan.lender,
                "reference": loan.reference,
                "principal": str(loan.principal),
                "status": loan.status,
                "residual_booked": figures["residual_booked"],
                "residual_schedule": figures["residual_schedule"],
                "account_balance": str(account_balance) if account_balance is not None else None,
                "account_difference": str(account_balance - Decimal(figures["residual_booked"]))
                if account_balance is not None
                else None,
                "interest_year": figures["components"]["interest"],
                "repayment_year": figures["components"]["repayment"],
            }
        )
    return out


def _check(code: str, report_value: Decimal, ledger_value: Decimal, label: str) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "report": str(report_value),
        "ledger": str(ledger_value),
        "difference": str(report_value - ledger_value),
        "ok": report_value == ledger_value,
    }


async def compute(session: AsyncSession, report: HoaAssetReport, ledger: Any) -> dict[str, Any]:
    """Snapshot of the asset report (recomputable, hashed by the caller)."""
    from mhvp.accounting import services as acc
    from mhvp.accounting.models import AccountCategory

    end = report.as_of
    banks = await _bank_accounts(session, ledger, end)
    bank_total = sum((Decimal(b["balance"]) for b in banks), ZERO)
    items = await acc.open_items(session, ledger, end)
    receivable_items = [i for i in items if i["kind"] == "receivable"]
    payable_items = [i for i in items if i["kind"] == "payable"]
    numbers = await _unit_numbers(
        session, {i["contract_id"] for i in receivable_items if i["contract_id"] is not None}
    )

    def _item(i: dict[str, Any]) -> dict[str, Any]:
        return {
            "open_item_id": str(i["id"]),
            "account_number": i["account_number"],
            "unit_number": numbers.get(str(i["contract_id"])) if i["contract_id"] else None,
            "booking_date": i["booking_date"].isoformat(),
            "due_date": i["due_date"].isoformat() if i["due_date"] else None,
            "amount": str(i["amount"]),
            "remaining": str(i["remaining"]),
        }

    receivables = [_item(i) for i in receivable_items if i["remaining"] > 0]
    owner_credits = [_item(i) for i in receivable_items if i["remaining"] < 0]
    payables = [_item(i) for i in payable_items]
    receivables_total = sum((Decimal(r["remaining"]) for r in receivables), ZERO)
    owner_credits_total = ZERO - sum((Decimal(r["remaining"]) for r in owner_credits), ZERO)
    payables_total = sum((Decimal(p["remaining"]) for p in payables), ZERO)
    loans = await _loans(session, ledger, end)
    loans_total = sum((Decimal(loan["residual_booked"]) for loan in loans), ZERO)
    manual = [
        {
            "label": str(m.get("label", "")),
            "amount": str(Decimal(str(m.get("amount", "0")))),
            "note": m.get("note"),
        }
        for m in (report.manual_items or [])
    ]
    manual_total = sum((Decimal(str(m["amount"])) for m in manual), ZERO)
    reserve = await _reserve(session, report, ledger)

    # Reconciliation against the accounting: every report figure next to the ledger figure,
    # difference visible, no correction (rule M24-02).
    debit, credit = await _journal_sums(session, ledger.id, end)
    checks = [
        _check("journal_balanced", debit, credit, "Journal ausgeglichen (Soll gleich Haben)"),
        _check(
            "bank",
            bank_total,
            await _category_balance(session, ledger.id, AccountCategory.BANK, end)
            + await _category_balance(session, ledger.id, AccountCategory.CASH, end),
            "Bank- und Kassenbestände gegen Kontensalden",
        ),
        _check(
            "receivables",
            receivables_total - owner_credits_total,
            await _category_balance(session, ledger.id, AccountCategory.DEBTOR, end),
            "Offene Posten Eigentümer gegen Debitorensalden",
        ),
        _check(
            "payables",
            payables_total,
            ZERO - await _category_balance(session, ledger.id, AccountCategory.CREDITOR, end),
            "Offene Verbindlichkeiten gegen Kreditorensalden",
        ),
        _check(
            "loans",
            loans_total,
            ZERO - await _category_balance(session, ledger.id, AccountCategory.LOAN, end),
            "Restschuld aus Darlehenspositionen gegen Darlehenskonten",
        ),
        _check(
            "reserve_bank",
            Decimal(reserve["actual"]),
            Decimal(reserve["bank_balance"]),
            "Rücklage (Ist) gegen Bankanlage der Rücklage",
        ),
    ]
    assets_total = bank_total + receivables_total + manual_total
    liabilities_total = payables_total + owner_credits_total + loans_total
    return {
        "as_of": end.isoformat(),
        "legal_minimum": {
            "reserve": reserve,
            "note": "Rücklagenstand nach § 28 Abs. 4 WEG (Einschätzung, R04); "
            "übrige Blöcke sind ergänzende Projektangaben (W11).",
        },
        "bank_accounts": banks,
        "bank_total": str(bank_total),
        "receivables": receivables,
        "receivables_total": str(receivables_total),
        "owner_credits": owner_credits,
        "owner_credits_total": str(owner_credits_total),
        "payables": payables,
        "payables_total": str(payables_total),
        "loans": loans,
        "loans_total": str(loans_total),
        "manual_items": manual,
        "manual_total": str(manual_total),
        "assets_total": str(assets_total),
        "liabilities_total": str(liabilities_total),
        "net_assets": str(assets_total - liabilities_total),
        "reconciliation": {
            "checks": checks,
            "reconciled": all(c["ok"] for c in checks),
            "note": "Differenzen werden angezeigt und sind zu klären; keine Ausgleichsbuchung "
            "durch den Bericht.",
        },
        "note_text": NOTE,
    }


# --- endpoints -------------------------------------------------------------------------------


def _out(r: HoaAssetReport) -> dict[str, Any]:
    return {
        "id": r.id,
        "legal_entity_id": r.legal_entity_id,
        "ledger_id": r.ledger_id,
        "as_of": r.as_of,
        "status": r.status,
        "reserve_opening": str(r.reserve_opening),
        "reserve_withdrawals": str(r.reserve_withdrawals),
        "reserve_interest": str(r.reserve_interest),
        "manual_items": r.manual_items,
        "snapshot": r.snapshot,
        "snapshot_hash": r.snapshot_hash,
        "issued_at": r.issued_at,
        "note": r.note,
        "draft_notice": DRAFT_NOTICE if r.status != "issued" else None,
    }


async def _get(session: AsyncSession, report_id: uuid.UUID) -> HoaAssetReport:
    row = await session.get(HoaAssetReport, report_id, with_for_update=True)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    ensure_session_legal_entity_allowed(session, row.legal_entity_id)
    return row


def _manual(items: list[ManualItemIn]) -> list[dict[str, Any]]:
    return [{"label": m.label, "amount": str(m.amount), "note": m.note} for m in items]


@router.post(
    "/asset-reports", status_code=201, summary="Vermögensbericht zum Stichtag (W11, Entwurf)"
)
async def create_asset_report(
    body: AssetReportIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.hoa.finance import _ledger

    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, body.ledger_id)
        row = HoaAssetReport(
            tenant_id=principal.tenant_id,
            legal_entity_id=ledger.legal_entity_id,
            ledger_id=ledger.id,
            as_of=body.as_of,
            status="draft",
            reserve_opening=body.reserve_opening,
            reserve_withdrawals=body.reserve_withdrawals,
            reserve_interest=body.reserve_interest,
            manual_items=_manual(body.manual_items),
            note=body.note,
            created_by=principal.user_id,
            updated_by=principal.user_id,
        )
        session.add(row)
        await session.flush()
        return _out(row)


@router.get("/asset-reports", summary="Vermögensberichte einer GdWE")
async def list_asset_reports(
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    ledger_id: uuid.UUID | None = None,
    legal_entity_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    from mhvp.hoa.finance import _entity_visible

    async with tenant_tx(request, principal) as session:
        query = select(HoaAssetReport).order_by(HoaAssetReport.as_of.desc())
        if ledger_id is not None:
            query = query.where(HoaAssetReport.ledger_id == ledger_id)
        if legal_entity_id is not None:
            query = query.where(HoaAssetReport.legal_entity_id == legal_entity_id)
        rows = (await session.scalars(query)).all()
        return [
            _out(r) | {"snapshot": None}
            for r in rows
            if _entity_visible(session, r.legal_entity_id)
        ]


@router.get("/asset-reports/{report_id}", summary="Vermögensbericht mit Berechnung")
async def get_asset_report(
    report_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return _out(await _get(session, report_id))


@router.patch("/asset-reports/{report_id}", summary="Stichtag, Rücklagenwerte, manuelle Positionen")
async def patch_asset_report(
    report_id: uuid.UUID,
    body: AssetReportPatch,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    """Only before the issue; a change invalidates the calculated snapshot (back to draft)."""
    async with tenant_tx(request, principal) as session:
        row = await _get(session, report_id)
        if row.status == "issued":
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Ausgegebener Bericht ist unveränderlich."
            )
        for name in ("as_of", "reserve_opening", "reserve_withdrawals", "reserve_interest", "note"):
            value = getattr(body, name)
            if value is not None:
                setattr(row, name, value)
        if body.manual_items is not None:
            row.manual_items = _manual(body.manual_items)
        row.snapshot, row.snapshot_hash, row.status = None, None, "draft"
        row.updated_by = principal.user_id
        await session.flush()
        return _out(row)


@router.post(
    "/asset-reports/{report_id}/calculate", summary="Berechnen und gegen Buchhaltung abstimmen"
)
async def calculate_asset_report(
    report_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.hoa.finance import _ledger

    async with tenant_tx(request, principal) as session:
        row = await _get(session, report_id)
        if row.status == "issued":
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Ausgegebener Bericht ist unveränderlich."
            )
        ledger = await _ledger(session, row.ledger_id)
        snapshot = await compute(session, row, ledger)
        row.snapshot, row.snapshot_hash = snapshot, calc.digest(snapshot)
        row.status = "calculated"
        row.updated_by = principal.user_id
        await session.flush()
        return _out(row)


@router.post("/asset-reports/{report_id}/transition", summary="Ausgabe freigeben (G4)")
async def transition_asset_report(
    report_id: uuid.UUID,
    body: AssetReportTransitionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    """`issued` fixes the calculated snapshot for the owners; needs gate G4 of the tenant and
    a reconciled report (every check without difference). Nothing is posted."""
    await ensure_release_gate_open(
        ReleaseGate.G4, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        row = await _get(session, report_id)
        if row.status != "calculated" or row.snapshot is None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Erst berechnen.")
        if not row.snapshot["reconciliation"]["reconciled"]:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Abstimmung gegen die Buchhaltung weist Differenzen aus.",
            )
        row.status, row.issued_at = "issued", datetime.now(UTC)
        row.updated_by = principal.user_id
        await session.flush()
        return _out(row)


@router.get("/loans/{loan_id}/annual", summary="Zins, Tilgung und Restschuld eines Jahres (M24-03)")
async def loan_annual(
    loan_id: uuid.UUID,
    year: int,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """Year figures of a loan from the booked items (posted journal entries) or, without a
    booked item of the component, from the instalment schedule as orientation; residual debt
    at the year end from booked items and from the schedule. Display only."""
    from mhvp.hoa.finance import _get as _get_loan

    if not 2000 <= year <= 2100:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Jahr außerhalb 2000 bis 2100.")
    async with tenant_tx(request, principal) as session:
        loan = await _get_loan(session, HoaLoan, loan_id)
        return await calc.loan_year_figures(session, loan, year) | {
            "note_text": calc.LOAN_STATEMENT_NOTE
        }


# --- PDF -------------------------------------------------------------------------------------


def _eur(value: Any) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    sign = "-" if amount < 0 else ""
    whole, cents = f"{abs(amount):.2f}".split(".")
    groups = f"{int(whole):,}".replace(",", ".")
    return f"{sign}{groups},{cents} EUR"


def _d(value: str) -> str:
    y, m, d = value.split("-")
    return f"{d}.{m}.{y}"


def compose_pdf(
    report: HoaAssetReport, snapshot: dict[str, Any], entity_name: str, today: date
) -> Any:
    """Letter with the report blocks as tables; draft marking unless issued."""
    from mhvp.documents import letters

    reserve = snapshot["legal_minimum"]["reserve"]
    tables = {
        "ruecklage": letters.LetterTable(
            header=["Erhaltungsrücklage", "Betrag"],
            rows=[
                ["Anfangsbestand 01.01.", _eur(reserve["opening"])],
                ["Beschlossene Zuführungen (Soll)", _eur(reserve["contributions_resolved"])],
                ["Gezahlte Zuführungen (Ist)", _eur(reserve["contributions_paid"])],
                ["Offene Zuführungen", _eur(reserve["contributions_open"])],
                ["Verwendung (Entnahmen)", _eur(reserve["withdrawals"])],
                ["Zinsen", _eur(reserve["interest"])],
                ["Stand Soll", _eur(reserve["target"])],
                ["Stand Ist", _eur(reserve["actual"])],
                ["Bankanlage der Rücklage", _eur(reserve["bank_balance"])],
                ["Differenz Bankanlage zu Ist", _eur(reserve["bank_difference"])],
            ],
            right_aligned=(1,),
            widths=(0.7, 0.3),
        ),
        "bank": letters.LetterTable(
            header=["Konto", "Bezeichnung", "Bestand"],
            rows=[[b["number"], b["name"], _eur(b["balance"])] for b in snapshot["bank_accounts"]]
            + [["", "Summe", _eur(snapshot["bank_total"])]],
            right_aligned=(2,),
            total_row=True,
            widths=(0.2, 0.5, 0.3),
        ),
        "forderungen": letters.LetterTable(
            header=["Einheit", "Konto", "Fällig", "Offen"],
            rows=[
                [
                    r["unit_number"] or "",
                    r["account_number"],
                    _d(r["due_date"]) if r["due_date"] else "",
                    _eur(r["remaining"]),
                ]
                for r in snapshot["receivables"]
            ]
            + [["", "Summe", "", _eur(snapshot["receivables_total"])]],
            right_aligned=(3,),
            total_row=True,
            widths=(0.2, 0.3, 0.2, 0.3),
        ),
        "verbindlichkeiten": letters.LetterTable(
            header=["Position", "Betrag"],
            rows=[["Offene Verbindlichkeiten (Kreditoren)", _eur(snapshot["payables_total"])]]
            + [["Guthaben von Eigentümern", _eur(snapshot["owner_credits_total"])]]
            + [
                [
                    f"Darlehen {loan['lender']} {loan['reference'] or ''} Restschuld",
                    _eur(loan["residual_booked"]),
                ]
                for loan in snapshot["loans"]
            ]
            + [["Summe", _eur(snapshot["liabilities_total"])]],
            right_aligned=(1,),
            total_row=True,
            widths=(0.7, 0.3),
        ),
        "sonstiges": letters.LetterTable(
            header=["Sonstiges Gemeinschaftsvermögen (manuell)", "Betrag"],
            rows=[[m["label"], _eur(m["amount"])] for m in snapshot["manual_items"]]
            + [["Summe", _eur(snapshot["manual_total"])]],
            right_aligned=(1,),
            total_row=True,
            widths=(0.7, 0.3),
        ),
        "abstimmung": letters.LetterTable(
            header=["Prüfung", "Bericht", "Buchhaltung", "Differenz"],
            rows=[
                [c["label"], _eur(c["report"]), _eur(c["ledger"]), _eur(c["difference"])]
                for c in snapshot["reconciliation"]["checks"]
            ],
            right_aligned=(1, 2, 3),
            widths=(0.4, 0.2, 0.2, 0.2),
        ),
    }
    recon = snapshot["reconciliation"]
    body = "\n\n".join(
        [
            f"Vermögensbericht der {entity_name} zum Stichtag {_d(snapshot['as_of'])}.",
            "1. Erhaltungsrücklage (gesetzliche Mindestangabe, Einschätzung nach § 28 Abs. 4 WEG)",
            "[[table:ruecklage]]",
            "2. Bankbestände des Rechtsträgers",
            "[[table:bank]]",
            "3. Forderungen gegen Eigentümer",
            "[[table:forderungen]]",
            "4. Verbindlichkeiten und Darlehen",
            "[[table:verbindlichkeiten]]",
            "5. Sonstiges Gemeinschaftsvermögen",
            "[[table:sonstiges]]",
            f"Vermögen gesamt {_eur(snapshot['assets_total'])}, Verbindlichkeiten gesamt "
            f"{_eur(snapshot['liabilities_total'])}, Nettovermögen {_eur(snapshot['net_assets'])}.",
            "6. Abstimmung gegen die Buchhaltung",
            "[[table:abstimmung]]",
            (
                "Alle Prüfungen ohne Differenz."
                if recon["reconciled"]
                else "Differenzen vorhanden, zu klären; keine Ausgleichsbuchung."
            ),
            snapshot["note_text"],
        ]
    )
    return letters.Letter(
        recipient_lines=[entity_name],
        subject=f"Vermögensbericht zum {_d(snapshot['as_of'])}",
        body=body,
        letter_date=today,
        info=[
            ("Stichtag", _d(snapshot["as_of"])),
            ("Status", "Entwurf" if report.status != "issued" else "Ausgegeben"),
        ],
        closing="",
        signatory=[],
        tables=tables,
        notice=None if report.status == "issued" else DRAFT_NOTICE,
        draft_notice=None if report.status == "issued" else "ENTWURF",
    )


@router.get("/asset-reports/{report_id}/pdf", summary="Vermögensbericht als PDF (Entwurf bis G4)")
async def asset_report_pdf(
    report_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    from mhvp.documents import services as docs
    from mhvp.documents.blobs import BlobStore
    from mhvp.properties.models import LegalEntity

    async with tenant_tx(request, principal) as session:
        row = await _get(session, report_id)
        if row.snapshot is None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Erst berechnen.")
        head = await docs.letterhead(session, BlobStore(request.app.state.settings))
        entity = await session.get(LegalEntity, row.legal_entity_id)
        name = entity.name if entity is not None else "Gemeinschaft der Wohnungseigentümer"
        letter = compose_pdf(row, row.snapshot, name, datetime.now(UTC).date())
        from mhvp.documents import letters

        pdf = letters.render_pdf(head, letter)
        stamp = row.as_of.isoformat()
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="vermoegensbericht-{stamp}.pdf"'
            },
        )
