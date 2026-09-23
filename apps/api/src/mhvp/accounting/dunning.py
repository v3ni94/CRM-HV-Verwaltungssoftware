"""Dunning runs (7.5 Mahnwesen, 6.9.10 D52).

Preview only lists overdue open receivables per debtor with the next level; dunning blocks,
thresholds and non leading ledgers are excluded with a reason. Due date and default are kept
apart: the preview proposes a reminder, it does not assert default (Verzug). Fees and interest
are zero until V7 is decided. Approving and sending require a second person and a leading
ledger (only the leading system may dun, which needs G1).
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.accounting.models import (
    DunningCase,
    DunningRun,
    DunningSettings,
    LeadingSystem,
    Ledger,
    LedgerAccount,
)
from mhvp.core.problems import ErrorCodes, ProblemError


async def settings_for(
    session: AsyncSession, property_id: uuid.UUID | None
) -> DunningSettings | None:
    if property_id is not None:
        own = await session.scalar(
            select(DunningSettings).where(DunningSettings.property_id == property_id)
        )
        if own is not None:
            return own
    default: DunningSettings | None = await session.scalar(
        select(DunningSettings).where(DunningSettings.property_id.is_(None))
    )
    return default


async def last_level(session: AsyncSession, account_id: uuid.UUID) -> int:
    level = await session.scalar(
        select(DunningCase.level)
        .where(DunningCase.debtor_account_id == account_id, DunningCase.status == "sent")
        .order_by(DunningCase.level.desc())
        .limit(1)
    )
    return int(level or 0)


async def preview(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID | None, run_date: date
) -> DunningRun:
    from mhvp.contracts.models import Contract

    run = DunningRun(tenant_id=tenant_id, created_by=user_id, run_date=run_date)
    session.add(run)
    await session.flush()
    counts = {"proposed": 0, "excluded": 0}
    for ledger in (await session.scalars(select(Ledger).order_by(Ledger.name))).all():
        settings = await settings_for(session, ledger.property_id)
        items = [
            i
            for i in await acc.open_items(session, ledger, run_date)
            if i["kind"] == "receivable" and i["remaining"] > 0
        ]
        by_account: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for i in items:
            if i["due_date"] and i["due_date"] < run_date:
                by_account.setdefault(i["account_id"], []).append(i)
        for account_id, overdue in sorted(by_account.items(), key=lambda kv: str(kv[0])):
            account = await session.get(LedgerAccount, account_id)
            contract_id = next((i["contract_id"] for i in overdue if i["contract_id"]), None)
            contract = await session.get(Contract, contract_id) if contract_id else None
            total = sum((i["remaining"] for i in overdue), Decimal("0.00"))
            oldest = min(i["due_date"] for i in overdue)
            days = (run_date - oldest).days
            level = await last_level(session, account_id) + 1
            reason = None
            if settings is None or not settings.levels:
                reason = "Keine Mahnstufen eingerichtet"
            elif contract is not None and contract.dunning_block:
                reason = f"Mahnsperre: {contract.dunning_block_reason or 'ohne Angabe'}"
            elif total < settings.threshold_amount:
                reason = "Unter der Mahngrenze"
            else:
                config = next((lv for lv in settings.levels if int(lv["level"]) == level), None)
                if config is None:
                    reason = (
                        "Höchste Mahnstufe erreicht: weitere Schritte nur nach Einzelfallprüfung"
                    )
                elif days < int(config["min_days_overdue"]):
                    reason = f"Noch nicht {config['min_days_overdue']} Tage überfällig"
            if reason is None and ledger.leading_system is not LeadingSystem.MHVP:
                reason = "Buchungskreis nicht führend: gemahnt wird im führenden System (6.9.10)"
            session.add(
                DunningCase(
                    tenant_id=tenant_id,
                    run_id=run.id,
                    ledger_id=ledger.id,
                    contract_id=contract_id,
                    debtor_account_id=account_id,
                    level=level,
                    open_items=[
                        {
                            "open_item_id": str(i["id"]),
                            "due_date": i["due_date"].isoformat(),
                            "remaining": str(i["remaining"]),
                        }
                        for i in overdue
                    ],
                    total=total,
                    status="excluded" if reason else "proposed",
                    reason=reason
                    if reason
                    else f"{days} Tage seit Fälligkeit, Konto {account.number if account else ''}",
                )
            )
            counts["excluded" if reason else "proposed"] += 1
    run.totals = counts
    await session.flush()
    return run


async def approve(
    session: AsyncSession, run: DunningRun, user_id: uuid.UUID, is_platform_admin: bool
) -> DunningRun:
    if run.status != "preview":
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Lauf ist bereits freigegeben.")
    if run.created_by == user_id or is_platform_admin:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES, detail="Die Freigabe muss eine andere Person erteilen."
        )
    cases = (
        await session.scalars(
            select(DunningCase).where(
                DunningCase.run_id == run.id, DunningCase.status == "proposed"
            )
        )
    ).all()
    for case in cases:
        ledger = await session.get(Ledger, case.ledger_id)
        if ledger is None or ledger.leading_system is not LeadingSystem.MHVP:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Nur das führende System darf mahnen.")
    run.status, run.approved_by = "approved", user_id
    await session.flush()
    return run
