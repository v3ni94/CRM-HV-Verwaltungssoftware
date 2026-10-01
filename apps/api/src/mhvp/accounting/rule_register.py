"""Rule version register helpers (GA08-02, GA08-03, GA08-05; 7.12, 7.10 H03 and H05).

``select_version`` picks the version whose effective date range covers a date (not the
current day), so a settlement period decides which rule applies. The dated check points
below are drafts with a note and no legal consequence: no calculation reads them, dates and
contents stay to be verified against the official text (annex C R12, R14, R16)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import RuleVersion

# Rule id of the register entry that selects the settlement rule of operating costs.
SETTLEMENT_RULE_ID = "M17-betrkv-statement"
CHECKPOINT_GROUP = "Prüfpunkt"


@dataclass(frozen=True)
class Checkpoint:
    rule_id: str
    title: str
    effective_from: date | None  # None: the day of registration (date of the open question)
    source_status: str
    note: str


CHECKPOINTS: tuple[Checkpoint, ...] = (
    Checkpoint(
        "H03-HeizkostenV-5",
        "Prüfpunkt HeizkostenV § 5: Ausstattung, Fernablesbarkeit, Nachrüst und Übergangsfristen",
        None,
        "Entwurf, Master-Prompt 7.10 H03, Anhang C R14; Fristen und Wortlaut amtlich zu prüfen",
        "Hinweis ohne Rechtsfolge: konkreten Geräte- und Gebäudebestand prüfen, Fristen je Objekt "
        "erst nach amtlicher Prüfung eintragen (OPEN_QUESTIONS AA12-02).",
    ),
    Checkpoint(
        "H03-HeizkostenV-12",
        "Prüfpunkt HeizkostenV § 12: Kürzungsrecht und Sonderfälle (zum Beispiel Wärmepumpen)",
        None,
        "Entwurf, Master-Prompt 7.10 H02 und H03, Anhang C R14; Wortlaut amtlich zu prüfen",
        "Hinweis ohne Rechtsfolge: Kürzungsrechte nicht unbesehen auf Eigentümer gegen die GdWE "
        "übertragen; Sonderfälle je Objekt prüfen (OPEN_QUESTIONS AA12-02).",
    ),
    Checkpoint(
        "H05-CO2KostAufG-5a-5d",
        "Prüfpunkt CO2KostAufG §§ 5a bis 5d: spätere Anwendungszeitpunkte 2028",
        date(2028, 1, 1),
        "Entwurf, Master-Prompt 7.10 H05, Anhang C R16; Datum nur als Platzhalter für 2028",
        "Hinweis ohne Rechtsfolge: nicht auf die Abrechnung 2026 anwenden; vor Umsetzung Wortlaut, "
        "Inkrafttreten und Heizungssachverhalt amtlich prüfen (OPEN_QUESTIONS AA12-03).",
    ),
    Checkpoint(
        "H05-CO2KostAufG-5a-5d",
        "Prüfpunkt CO2KostAufG §§ 5a bis 5d: spätere Anwendungszeitpunkte 2029",
        date(2029, 1, 1),
        "Entwurf, Master-Prompt 7.10 H05, Anhang C R16; Datum nur als Platzhalter für 2029",
        "Hinweis ohne Rechtsfolge: nicht auf die Abrechnung 2026 anwenden; vor Umsetzung Wortlaut, "
        "Inkrafttreten und Heizungssachverhalt amtlich prüfen (OPEN_QUESTIONS AA12-03).",
    ),
)


def select_version(rows: Sequence[RuleVersion], day: date) -> RuleVersion | None:
    """Latest non-withdrawn version whose range covers ``day``."""
    covering = [
        r
        for r in rows
        if r.status != "withdrawn"
        and r.effective_from <= day
        and (r.effective_to is None or r.effective_to >= day)
    ]
    covering.sort(key=lambda r: (r.effective_from, r.version))
    return covering[-1] if covering else None


async def version_for_period(
    session: AsyncSession, rule_id: str, period_from: date
) -> RuleVersion | None:
    """Register entry that applies to a settlement period (selected by its start)."""
    rows = (await session.scalars(select(RuleVersion).where(RuleVersion.rule_id == rule_id))).all()
    return select_version(rows, period_from)


def snapshot_reference(row: RuleVersion | None) -> dict[str, object] | None:
    """What the snapshot keeps of the register entry (rule id, version, status)."""
    if row is None:
        return None
    return {
        "id": str(row.id) if row.id is not None else None,
        "rule_id": row.rule_id,
        "version": row.version,
        "status": row.status,
        "effective_from": row.effective_from.isoformat(),
    }


def due_checkpoints(rows: Sequence[RuleVersion], today: date) -> list[RuleVersion]:
    """Check point entries (group Prüfpunkt) whose date is reached; hint only (GA08-02)."""
    due = [
        r
        for r in rows
        if CHECKPOINT_GROUP in (r.case_groups or [])
        and r.status != "withdrawn"
        and r.effective_from <= today
    ]
    return sorted(due, key=lambda r: (r.effective_from, r.rule_id, r.version))


async def seed_checkpoints(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID | None, today: date
) -> list[RuleVersion]:
    """Create the missing check point drafts; idempotent per rule id and date."""
    created: list[RuleVersion] = []
    for cp in CHECKPOINTS:
        day = cp.effective_from or today
        existing = (
            await session.scalars(select(RuleVersion).where(RuleVersion.rule_id == cp.rule_id))
        ).all()
        if any(r.effective_from == day for r in existing):
            continue
        row = RuleVersion(
            tenant_id=tenant_id,
            created_by=user_id,
            rule_id=cp.rule_id,
            version=max((r.version for r in existing), default=0) + 1,
            title=cp.title,
            effective_from=day,
            case_groups=[CHECKPOINT_GROUP],
            source_status=cp.source_status,
            change_reason=cp.note[:500],
            status="draft",
        )
        session.add(row)
        await session.flush()
        created.append(row)
    return created


DEFAULT_LEAD_DAYS = 30


def checkpoint_state(row: RuleVersion, today: date, lead_days: int = DEFAULT_LEAD_DAYS) -> str:
    """AB10-01: ``withdrawn``, ``done`` (confirmed), ``due``, ``upcoming`` (inside the lead
    time) or ``open``. A hint only, no legal consequence."""
    if row.status == "withdrawn":
        return "withdrawn"
    if row.status == "confirmed":
        return "done"
    if row.effective_from <= today:
        return "due"
    if (row.effective_from - today).days <= lead_days:
        return "upcoming"
    return "open"
