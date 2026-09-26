"""Owner statement for rental management and SEV (7.6 A06, M17, task A25).

Draft only: the statement is calculated from the posted ledger of the owner's legal entity
(``rental_owner`` or ``sev_owner``) and stored as an immutable snapshot with rule version and
hash (6.9.3). Nothing is posted; issuing (PDF, delivery) needs release gate G3.

Blocks (A06, all shown apart, never mixed):

* income: rents and operating cost advances from posted revenue entries (Sollstellung), other
  revenue apart;
* expenses per cost account;
* management fee only from the stored fee settings (``admin_fee_draft``), never guessed;
* payouts to the owner (accounts of the ledger assigned to the owner's party or contact);
* open rent receivables at the cut-off date;
* deposits from the recorded deposit accounts, never counted as liquidity;
* free liquidity = bank and cash balances minus deposits held minus open payables;
* SEV only: reconciliation from the WEG individual statement (Hausgeld, Abrechnungsspitze,
  ``mhvp.hoa``) to the rental operating cost statement and the owner's burden.

The pure part (:func:`build_results`) works on plain inputs so that expected values can be
computed by hand (rule 0.1.8); :func:`collect_inputs` reads the ledger.
"""

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, DateTime, Enum, Index, String, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.billing.models import _fk
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

RULE_VERSION = "A06-owner-statement-v1"
ZERO = Decimal("0.00")

# Payment type codes (annex A.3, mhvp.properties.defaults.PAYMENT_TYPES) grouped for the
# income block. Advances are shown apart from rents (A06: no mixing).
RENT_CODES = frozenset({"rent", "garage", "parking", "rent_reduction", "other"})
ADVANCE_CODES = frozenset({"operating_cost_advance", "heating_cost_advance"})
# Fee intervals of admin_fee_setting.interval in months; unknown values raise a finding.
FEE_INTERVAL_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}


class OwnerStatementKind(StrEnum):
    RENTAL_OWNER = "rental_owner"
    SEV_OWNER = "sev_owner"


class OwnerStatementStatus(StrEnum):
    DRAFT = "draft"
    CALCULATED = "calculated"
    INTERNALLY_APPROVED = "internally_approved"


class OwnerStatement(IdMixin, TimestampMixin, TenantMixin, Base):
    """Owner statement (A06) with its current snapshot. Legal entity separation (6.9.1): the
    ledger belongs to the owner's legal entity, never to the management company."""

    __tablename__ = "owner_statement"
    __table_args__ = (
        Index("ix_owner_statement_tenant_id", "tenant_id"),
        Index("ix_owner_statement_ledger_id", "ledger_id"),
    )

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id")
    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    property_id: Mapped[uuid.UUID] = _fk("property.id")
    kind: Mapped[OwnerStatementKind] = mapped_column(
        Enum(
            OwnerStatementKind,
            name="owner_statement_kind",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[OwnerStatementStatus] = mapped_column(
        Enum(
            OwnerStatementStatus,
            name="owner_statement_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=OwnerStatementStatus.DRAFT,
        server_default="draft",
    )
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False, default=RULE_VERSION)
    # Immutable result of the last calculation: {"inputs": ..., "results": ..., "findings": ...}
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    calculated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


# Pure calculation ---------------------------------------------------------------------------


def _d(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _finding(code: str, level: str, message: str) -> dict[str, str]:
    return {"code": code, "level": level, "message": message}


def _months_overlap(a_from: date, a_to: date, b_from: date, b_to: date | None) -> int:
    """Calendar months whose first day lies in both periods (fee intervals, A06)."""
    start = max(a_from, b_from)
    end = a_to if b_to is None else min(a_to, b_to)
    if end < start:
        return 0
    first = date(start.year, start.month, 1)
    if first < start:
        first = date(start.year + (start.month // 12), start.month % 12 + 1, 1)
    count = 0
    cursor = first
    while cursor <= end:
        count += 1
        cursor = date(cursor.year + (cursor.month // 12), cursor.month % 12 + 1, 1)
    return count


def fee_intervals(period_from: date, period_to: date, setting: dict[str, Any]) -> int | None:
    """Number of fee intervals of a setting inside the statement period, None if unknown."""
    months = FEE_INTERVAL_MONTHS.get(str(setting.get("interval", "monthly")))
    if months is None:
        return None
    overlap = _months_overlap(
        period_from,
        period_to,
        date.fromisoformat(str(setting["start_date"])),
        date.fromisoformat(str(setting["end_date"])) if setting.get("end_date") else None,
    )
    return overlap // months


def build_results(inputs: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Blocks of the owner statement from plain inputs (see module docstring).

    ``inputs`` carries decimals as strings; every amount of the result is a string of a
    ``Decimal`` with two places. Sum checks are returned as findings (level ``error`` when a
    block does not add up, ``warning`` for differences to explain, ``info`` for notes).
    """
    findings: list[dict[str, str]] = []
    period_from = date.fromisoformat(inputs["period"][0])
    period_to = date.fromisoformat(inputs["period"][1])

    # Income: rents and advances apart (A06), other revenue named as such.
    rent = advances = other = ZERO
    income_lines = []
    for line in inputs.get("income", []):
        amount = _d(line["amount"])
        codes = set(line.get("payment_type_codes", []))
        if codes and codes <= RENT_CODES:
            group = "rent"
            rent += amount
        elif codes and codes <= ADVANCE_CODES:
            group = "advances"
            advances += amount
        else:
            group = "other"
            other += amount
            if codes:
                findings.append(
                    _finding(
                        "INCOME-MIXED-ACCOUNT",
                        "warning",
                        f"Konto {line['account_number']} bündelt Mieten und Vorauszahlungen; "
                        "Zahlungsarten getrennten Konten zuordnen.",
                    )
                )
        income_lines.append({**line, "amount": str(amount), "group": group})
    income_total = rent + advances + other
    if sum((_d(line["amount"]) for line in income_lines), ZERO) != income_total:
        findings.append(_finding("SUM-INCOME", "error", "Einnahmen ergeben nicht die Summe."))

    # Expenses per cost account.
    expense_lines = [
        {**line, "amount": str(_d(line["amount"]))} for line in inputs.get("expenses", [])
    ]
    expenses_total = sum((_d(line["amount"]) for line in expense_lines), ZERO)

    # Management fee only from the stored settings (draft per interval times intervals).
    fee_lines = []
    fee_net = fee_vat = fee_gross = ZERO
    for setting in inputs.get("admin_fee", []):
        intervals = fee_intervals(period_from, period_to, setting)
        if intervals is None:
            findings.append(
                _finding(
                    "FEE-INTERVAL-UNKNOWN",
                    "warning",
                    f"Honorareinstellung {setting['setting_id']}: Intervall "
                    f"{setting.get('interval')} unbekannt, Honorar nicht berechnet.",
                )
            )
            intervals = 0
        net = _d(setting["net"]) * intervals
        vat = _d(setting["vat"]) * intervals
        fee_lines.append(
            {
                "setting_id": setting["setting_id"],
                "interval": setting.get("interval", "monthly"),
                "intervals": intervals,
                "unit_counts": setting.get("unit_counts", {}),
                "net_per_interval": str(_d(setting["net"])),
                "vat_percent": str(setting.get("vat_percent", "0")),
                "net": str(net),
                "vat": str(vat),
                "gross": str(net + vat),
            }
        )
        fee_net += net
        fee_vat += vat
        fee_gross += net + vat
    if not fee_lines:
        findings.append(
            _finding(
                "FEE-NOT-CONFIGURED",
                "info",
                "Keine Honorareinstellung für diesen Eigentümer hinterlegt; Verwalterhonorar 0,00.",
            )
        )
    if fee_net + fee_vat != fee_gross:
        findings.append(_finding("SUM-FEE", "error", "Honorar ergibt nicht die Summe."))

    # Payouts to the owner.
    payout_lines = [
        {**line, "amount": str(_d(line["amount"]))} for line in inputs.get("payouts", [])
    ]
    payouts_total = sum((_d(line["amount"]) for line in payout_lines), ZERO)
    if inputs.get("owner_party_id") is None:
        findings.append(
            _finding(
                "OWNER-PARTY-MISSING",
                "warning",
                "Dem Rechtsträger ist keine Person zugeordnet; Auszahlungen an den Eigentümer "
                "können nicht ermittelt werden.",
            )
        )
    elif not payout_lines:
        findings.append(
            _finding(
                "OWNER-ACCOUNT-MISSING",
                "info",
                "Kein Konto des Buchungskreises ist dem Eigentümer zugeordnet; Auszahlungen 0,00.",
            )
        )

    # Open rent receivables at the cut-off date.
    receivable_items = [
        {**item, "remaining": str(_d(item["remaining"]))}
        for item in inputs.get("open_receivables", [])
    ]
    receivables_total = sum((_d(item["remaining"]) for item in receivable_items), ZERO)
    payable_items = [
        {**item, "remaining": str(_d(item["remaining"]))}
        for item in inputs.get("open_payables", [])
    ]
    payables_total = sum((_d(item["remaining"]) for item in payable_items), ZERO)

    # Deposits: from the recorded deposit accounts, never liquidity (6.9.1, D56).
    deposit_items = [
        {**item, "balance": str(_d(item["balance"])), "amount_due": str(_d(item["amount_due"]))}
        for item in inputs.get("deposits", [])
    ]
    deposits_held = sum((_d(item["balance"]) for item in deposit_items), ZERO)
    bank_lines = [{**line, "balance": str(_d(line["balance"]))} for line in inputs.get("bank", [])]
    bank_total = sum((_d(line["balance"]) for line in bank_lines), ZERO)
    bank_segregated = sum(
        (_d(line["balance"]) for line in bank_lines if line.get("kind") == "deposit"), ZERO
    )
    if deposits_held != bank_segregated:
        findings.append(
            _finding(
                "DEPOSIT-BANK-DIFFERENCE",
                "warning",
                f"Kautionsbestand {deposits_held} EUR und Guthaben der getrennten Kautionskonten "
                f"{bank_segregated} EUR weichen ab; Differenz erklären, keine Ausgleichsbuchung.",
            )
        )

    # Free liquidity = bank minus deposits minus open payables (A06).
    free = bank_total - deposits_held - payables_total

    operating_result = income_total - expenses_total - fee_gross
    if int(inputs.get("draft_entries_in_period", 0)) > 0:
        findings.append(
            _finding(
                "DRAFT-ENTRIES",
                "info",
                f"{inputs['draft_entries_in_period']} Buchungsentwürfe im Zeitraum sind nicht "
                "enthalten (nur gebuchte Belege).",
            )
        )

    results: dict[str, Any] = {
        "period": inputs["period"],
        "income": {
            "rent": str(rent),
            "advances": str(advances),
            "other": str(other),
            "total": str(income_total),
            "lines": income_lines,
            "basis": "Gebuchte Sollstellungen der Ertragskonten im Zeitraum.",
        },
        "expenses": {"lines": expense_lines, "total": str(expenses_total)},
        "admin_fee": {
            "lines": fee_lines,
            "net": str(fee_net),
            "vat": str(fee_vat),
            "gross": str(fee_gross),
            "basis": "Entwurf aus den Honorareinstellungen, keine gebuchte Rechnung.",
        },
        "payouts": {"lines": payout_lines, "total": str(payouts_total)},
        "open_receivables": {
            "as_of": inputs["period"][1],
            "items": receivable_items,
            "total": str(receivables_total),
        },
        "open_payables": {"items": payable_items, "total": str(payables_total)},
        "deposits": {
            "items": deposit_items,
            "held": str(deposits_held),
            "bank_segregated": str(bank_segregated),
            "difference": str(bank_segregated - deposits_held),
            "note": "Kautionen sind Fremdgeld und keine Liquidität des Eigentümers.",
        },
        "liquidity": {
            "as_of": inputs["period"][1],
            "bank_total": str(bank_total),
            "accounts": bank_lines,
            "deposits_held": str(deposits_held),
            "open_payables": str(payables_total),
            "free": str(free),
            "formula": "Bank minus Kautionen minus offene Verbindlichkeiten.",
        },
        "operating_result": {
            "income": str(income_total),
            "expenses": str(expenses_total),
            "admin_fee_gross": str(fee_gross),
            "result": str(operating_result),
            "formula": "Einnahmen minus Ausgaben minus Verwalterhonorar (brutto).",
        },
    }
    if inputs.get("kind") == OwnerStatementKind.SEV_OWNER.value:
        results["sev_reconciliation"], sev_findings = _sev_reconciliation(inputs)
        findings.extend(sev_findings)
    return results, findings


def _sev_reconciliation(inputs: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Reconciliation WEG individual statement -> rental statement -> owner burden (A06).

    The Hausgeld the owner pays to the GdWE is not the same as the operating costs that may be
    allocated to the tenant; the difference is the owner's own burden (plus rounding and direct
    costs of the rental ledger, which are named apart)."""
    findings: list[dict[str, str]] = []
    hoa = inputs.get("hoa_statement")
    units = [
        {
            "unit_id": u["unit_id"],
            "unit_number": u.get("unit_number"),
            "cost_share": str(_d(u["cost_share"])),
            "advances_resolved": str(_d(u["advances_resolved"])),
            "advances_paid": str(_d(u["advances_paid"])),
            "result": str(_d(u["result"])),
            "arrears": str(_d(u.get("arrears", "0"))),
        }
        for u in (hoa or {}).get("units", [])
    ]
    hoa_cost_share = sum((_d(u["cost_share"]) for u in units), ZERO)
    hausgeld_resolved = sum((_d(u["advances_resolved"]) for u in units), ZERO)
    hausgeld_paid = sum((_d(u["advances_paid"]) for u in units), ZERO)
    hoa_result = sum((_d(u["result"]) for u in units), ZERO)
    if hoa_cost_share - hausgeld_resolved != hoa_result:
        findings.append(
            _finding(
                "SUM-HOA-RESULT",
                "error",
                "WEG-Einzelabrechnung: Kostenanteil minus Hausgeld ergibt nicht die "
                "Abrechnungsspitze.",
            )
        )
    tenant_costs = ZERO
    vacancy = ZERO
    tenant_advances_due = ZERO
    statements = []
    for st in inputs.get("operating_cost_statements", []):
        tenant_costs += _d(st["tenant_costs"])
        vacancy += _d(st["vacancy_owner_share"])
        tenant_advances_due += _d(st["advances_due"])
        statements.append(
            {
                "statement_id": st["statement_id"],
                "version": st.get("version"),
                "status": st.get("status"),
                "tenant_costs": str(_d(st["tenant_costs"])),
                "vacancy_owner_share": str(_d(st["vacancy_owner_share"])),
                "advances_due": str(_d(st["advances_due"])),
            }
        )
    if hoa is None:
        findings.append(
            _finding(
                "SEV-HOA-STATEMENT-MISSING",
                "warning",
                "Keine berechnete WEG-Einzelabrechnung für den Zeitraum vorhanden; die "
                "Überleitung zeigt nur die Mietabrechnung.",
            )
        )
    elif not units:
        findings.append(
            _finding(
                "SEV-UNITS-MISSING",
                "warning",
                "Die WEG-Einzelabrechnung enthält keine Einheit dieses Eigentümers.",
            )
        )
    if not statements:
        findings.append(
            _finding(
                "SEV-OPERATING-COST-STATEMENT-MISSING",
                "info",
                "Keine berechnete Betriebskostenabrechnung des Mietverhältnisses im Zeitraum; "
                "umlagefähiger Anteil 0,00.",
            )
        )
    owner_burden = hoa_cost_share - tenant_costs
    reconciliation = {
        "hoa_statement": (
            {k: hoa[k] for k in ("statement_id", "year", "version", "status") if k in hoa}
            if hoa
            else None
        ),
        "units": units,
        "hausgeld_resolved": str(hausgeld_resolved),
        "hausgeld_paid": str(hausgeld_paid),
        "hausgeld_open": str(hausgeld_resolved - hausgeld_paid),
        "hoa_cost_share": str(hoa_cost_share),
        "hoa_result": str(hoa_result),  # > 0 Nachschuss (Abrechnungsspitze), < 0 Guthaben
        "operating_cost_statements": statements,
        "tenant_allocable_costs": str(tenant_costs),
        "vacancy_owner_share": str(vacancy),
        "tenant_advances_due": str(tenant_advances_due),
        "owner_burden": str(owner_burden),
        "steps": [
            "1. Kostenanteil laut WEG-Einzelabrechnung (Hausgeld-Soll plus Abrechnungsspitze).",
            "2. Davon auf Mieter umgelegt laut Betriebskostenabrechnung (nur mit Grundlage).",
            "3. Rest trägt der Eigentümer (nicht umlagefähig, Leerstand, Direktkosten).",
        ],
        "note": (
            "Hausgeldzahlungen an die GdWE sind keine mietrechtlich umlagefähigen Betriebskosten; "
            "GdWE-Vorschüsse und Mieteinnahmen werden nicht vermischt."
        ),
    }
    return reconciliation, findings


def digest(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()


# Ledger access --------------------------------------------------------------------------------


async def _turnover(
    session: AsyncSession, account_id: uuid.UUID, start: date, end: date
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
                JournalLine.account_id == account_id,
                JournalEntry.status == EntryStatus.POSTED,
                JournalEntry.booking_date.between(start, end),
            )
        )
    ).one()
    return Decimal(d), Decimal(c)


async def _hoa_statement(
    session: AsyncSession, statement: OwnerStatement, entity: Any
) -> dict[str, Any] | None:
    """Latest calculated WEG statement of the property for the year of the period, reduced to
    the units the SEV owner holds (ownership contracts with SEV)."""
    from mhvp.accounting.models import Ledger
    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.hoa.models import HoaStatement
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    if statement.period_from.year != statement.period_to.year or entity.party_id is None:
        return None
    hoa_entity = await session.scalar(
        select(LegalEntity).where(
            LegalEntity.property_id == statement.property_id,
            LegalEntity.kind == LegalEntityKind.HOA,
        )
    )
    if hoa_entity is None:
        return None
    unit_ids = {
        str(u)
        for u in (
            await session.scalars(
                select(Contract.unit_id).where(
                    Contract.property_id == statement.property_id,
                    Contract.kind == ContractKind.OWNERSHIP,
                    Contract.party_id == entity.party_id,
                    Contract.sev_enabled.is_(True),
                    Contract.start_date <= statement.period_to,
                    or_(Contract.end_date.is_(None), Contract.end_date >= statement.period_from),
                )
            )
        ).all()
    }
    hoa_st = await session.scalar(
        select(HoaStatement)
        .join(Ledger, Ledger.id == HoaStatement.ledger_id)
        .where(
            Ledger.legal_entity_id == hoa_entity.id,
            HoaStatement.year == statement.period_from.year,
            HoaStatement.snapshot.is_not(None),
        )
        .order_by(HoaStatement.version.desc())
        .limit(1)
    )
    if hoa_st is None or hoa_st.snapshot is None:
        return None
    return {
        "statement_id": str(hoa_st.id),
        "year": hoa_st.year,
        "version": hoa_st.version,
        "status": hoa_st.status.value,
        "units": [u for u in hoa_st.snapshot.get("units", []) if u["unit_id"] in unit_ids],
    }


async def _operating_cost_statements(
    session: AsyncSession, statement: OwnerStatement
) -> list[dict[str, Any]]:
    from mhvp.billing.models import Statement, StatementSnapshot

    out = []
    rows = (
        await session.scalars(
            select(Statement).where(
                Statement.ledger_id == statement.ledger_id,
                Statement.period_from == statement.period_from,
                Statement.period_to == statement.period_to,
                Statement.snapshot_id.is_not(None),
            )
        )
    ).all()
    # Only the newest version of a chain counts (supersedes_id).
    superseded = {r.supersedes_id for r in rows if r.supersedes_id}
    for st in rows:
        if st.id in superseded:
            continue
        snap = await session.get(StatementSnapshot, st.snapshot_id)
        if snap is None:
            continue
        results = snap.results
        out.append(
            {
                "statement_id": str(st.id),
                "version": st.version,
                "status": st.status.value,
                "tenant_costs": str(
                    sum((Decimal(r["costs"]) for r in results.get("results", [])), ZERO)
                ),
                "vacancy_owner_share": results.get("vacancy_owner_share", "0.00"),
                "advances_due": str(
                    sum((Decimal(r["advances_due"]) for r in results.get("results", [])), ZERO)
                ),
            }
        )
    return out


async def collect_inputs(
    session: AsyncSession, statement: OwnerStatement, ledger: Any, entity: Any
) -> dict[str, Any]:
    """Read every input of the statement from the posted ledger and the master data."""
    from mhvp.accounting import receivables
    from mhvp.accounting import services as acc
    from mhvp.accounting.models import (
        AccountCategory,
        AdminFeeSetting,
        EntryStatus,
        JournalEntry,
        LedgerAccount,
        PaymentTypeAccount,
        ReceivableItem,
    )
    from mhvp.accounting.reports import _balance
    from mhvp.contacts.models import PartyMember
    from mhvp.contracts.models import Contract, Deposit, DepositMovement
    from mhvp.contracts.services import deposit_totals
    from mhvp.properties.models import PropertyBankAccount

    start, end = statement.period_from, statement.period_to
    accounts = (
        await session.scalars(
            select(LedgerAccount)
            .where(LedgerAccount.ledger_id == ledger.id)
            .order_by(LedgerAccount.number)
        )
    ).all()
    # Accounts of the owner (payouts): assigned to the owner's party or to one of its contacts.
    owner_contacts: set[uuid.UUID] = set()
    if entity.party_id is not None:
        owner_contacts = set(
            (
                await session.scalars(
                    select(PartyMember.contact_id).where(PartyMember.party_id == entity.party_id)
                )
            ).all()
        )
    codes_by_account: dict[uuid.UUID, list[str]] = {}
    for pta in (
        await session.scalars(
            select(PaymentTypeAccount).where(PaymentTypeAccount.ledger_id == ledger.id)
        )
    ).all():
        codes_by_account.setdefault(pta.account_id, []).append(pta.payment_type_code)

    income, expenses, payouts, bank = [], [], [], []
    for account in accounts:
        if account.category is AccountCategory.REVENUE:
            d, c = await _turnover(session, account.id, start, end)
            if d or c:
                income.append(
                    {
                        "account_id": str(account.id),
                        "account_number": account.number,
                        "account_name": account.name,
                        "payment_type_codes": sorted(codes_by_account.get(account.id, [])),
                        "amount": str(c - d),
                    }
                )
        elif account.category is AccountCategory.COST:
            d, c = await _turnover(session, account.id, start, end)
            if d or c:
                expenses.append(
                    {
                        "account_id": str(account.id),
                        "account_number": account.number,
                        "account_name": account.name,
                        "allocation_category": account.allocation_category.value,
                        "amount": str(d - c),
                    }
                )
        elif account.category in (AccountCategory.BANK, AccountCategory.CASH):
            kind = "free"
            if account.property_bank_account_id:
                pba = await session.get(PropertyBankAccount, account.property_bank_account_id)
                if pba is not None and pba.segregated:
                    kind = "deposit"
            bank.append(
                {
                    "account_id": str(account.id),
                    "number": account.number,
                    "name": account.name,
                    "kind": kind,
                    "balance": str(await _balance(session, account.id, end)),
                }
            )
        is_owner_account = entity.party_id is not None and (
            account.party_id == entity.party_id
            or (account.contact_id is not None and account.contact_id in owner_contacts)
        )
        if is_owner_account and account.category not in (
            AccountCategory.BANK,
            AccountCategory.CASH,
        ):
            d, c = await _turnover(session, account.id, start, end)
            if d or c:
                payouts.append(
                    {
                        "account_id": str(account.id),
                        "account_number": account.number,
                        "account_name": account.name,
                        "amount": str(d - c),
                    }
                )

    fee_settings = []
    fee_query = select(AdminFeeSetting).where(
        AdminFeeSetting.property_id == statement.property_id,
        AdminFeeSetting.start_date <= end,
        or_(AdminFeeSetting.end_date.is_(None), AdminFeeSetting.end_date >= start),
    )
    if statement.kind is OwnerStatementKind.SEV_OWNER:
        fee_query = fee_query.where(AdminFeeSetting.invoice_debtor_party_id == entity.party_id)
    else:
        fee_query = fee_query.where(
            or_(
                AdminFeeSetting.invoice_debtor_party_id.is_(None),
                AdminFeeSetting.invoice_debtor_party_id == entity.party_id,
            )
        )
    for setting in (await session.scalars(fee_query.order_by(AdminFeeSetting.start_date))).all():
        counts = await receivables.fee_unit_counts(session, setting, end)
        draft = receivables.admin_fee(setting, counts)
        fee_settings.append(
            {
                "setting_id": str(setting.id),
                "interval": setting.interval,
                "start_date": setting.start_date.isoformat(),
                "end_date": setting.end_date.isoformat() if setting.end_date else None,
                "unit_counts": counts,
                "net": draft["net"],
                "vat_percent": draft["vat_percent"],
                "vat": draft["vat"],
                "gross": draft["gross"],
            }
        )

    items = await acc.open_items(session, ledger, end)
    # Payment type of each receivable item (rent, advance, ...) from the posted receivable run.
    entry_ids = [i["journal_entry_id"] for i in items if i["kind"] == "receivable"]
    components: dict[uuid.UUID, str] = {}
    if entry_ids:
        for entry_id, code in (
            await session.execute(
                select(ReceivableItem.journal_entry_id, ReceivableItem.payment_type_code).where(
                    ReceivableItem.journal_entry_id.in_(entry_ids)
                )
            )
        ).all():
            components[entry_id] = code
    open_receivables = [
        {
            "open_item_id": str(i["id"]),
            "account_number": i["account_number"],
            "contract_id": str(i["contract_id"]) if i.get("contract_id") else None,
            "component": components.get(i["journal_entry_id"]),
            "due_date": i["due_date"].isoformat() if i.get("due_date") else None,
            "remaining": str(i["remaining"]),
        }
        for i in items
        if i["kind"] == "receivable" and i["remaining"] > 0
    ]
    open_payables = [
        {
            "open_item_id": str(i["id"]),
            "account_number": i["account_number"],
            "due_date": i["due_date"].isoformat() if i.get("due_date") else None,
            "remaining": str(i["remaining"]),
        }
        for i in items
        if i["kind"] == "payable" and i["remaining"] > 0
    ]

    deposits = []
    for deposit, contract_number in (
        await session.execute(
            select(Deposit, Contract.number)
            .join(Contract, Contract.id == Deposit.contract_id)
            .where(Contract.legal_entity_id == entity.id, Deposit.valid_from <= end)
            .order_by(Contract.number)
        )
    ).all():
        movements = (
            await session.scalars(
                select(DepositMovement).where(
                    DepositMovement.deposit_id == deposit.id, DepositMovement.date <= end
                )
            )
        ).all()
        received, balance = deposit_totals(deposit, list(movements))
        deposits.append(
            {
                "deposit_id": str(deposit.id),
                "contract_id": str(deposit.contract_id),
                "contract_number": contract_number,
                "kind": deposit.kind.value,
                "amount_due": str(deposit.amount_due),
                "received": str(received),
                "balance": str(balance),
            }
        )

    drafts = await session.scalar(
        select(func.count())
        .select_from(JournalEntry)
        .where(
            JournalEntry.ledger_id == ledger.id,
            JournalEntry.status == EntryStatus.DRAFT,
            JournalEntry.booking_date.between(start, end),
        )
    )
    inputs: dict[str, Any] = {
        "period": [start.isoformat(), end.isoformat()],
        "kind": statement.kind.value,
        "ledger_id": str(ledger.id),
        "legal_entity_id": str(entity.id),
        "owner_party_id": str(entity.party_id) if entity.party_id else None,
        "income": income,
        "expenses": expenses,
        "admin_fee": fee_settings,
        "payouts": payouts,
        "open_receivables": open_receivables,
        "open_payables": open_payables,
        "bank": bank,
        "deposits": deposits,
        "draft_entries_in_period": int(drafts or 0),
    }
    if statement.kind is OwnerStatementKind.SEV_OWNER:
        inputs["hoa_statement"] = await _hoa_statement(session, statement, entity)
        inputs["operating_cost_statements"] = await _operating_cost_statements(session, statement)
    return inputs


async def calculate(
    session: AsyncSession, statement: OwnerStatement, user_id: uuid.UUID | None
) -> dict[str, Any]:
    """Calculate and store the snapshot; returns it. Allowed until internal approval."""
    from mhvp.accounting.models import Ledger
    from mhvp.core.problems import ErrorCodes, ProblemError
    from mhvp.properties.models import LegalEntity

    ledger = await session.get(Ledger, statement.ledger_id)
    entity = await session.get(LegalEntity, statement.legal_entity_id)
    if ledger is None or entity is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    inputs = await collect_inputs(session, statement, ledger, entity)
    results, findings = build_results(inputs)
    snapshot = {
        "rule_version": RULE_VERSION,
        "inputs": inputs,
        "results": results,
        "findings": findings,
    }
    statement.snapshot = snapshot
    statement.snapshot_hash = digest(snapshot)
    statement.rule_version = RULE_VERSION
    statement.calculated_at = datetime.now(tz=UTC)
    statement.calculated_by = user_id
    statement.status = OwnerStatementStatus.CALCULATED
    return snapshot
