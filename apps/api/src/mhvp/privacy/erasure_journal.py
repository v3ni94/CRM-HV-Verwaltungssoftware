"""Erasure journal for restores (GAI-512, D47, M9-03).

A backup restored after an Art. 17 anonymisation contains the personal data of the contact
again. The journal is derived from the append-only event ``contact.anonymized`` (written by
:func:`mhvp.privacy.erasure.execute`), exported from the live database before the restore and
replayed afterwards:

* a contact that is absent after the restore needs nothing,
* a contact that already carries the anonymised label is left as it is,
* every other contact is anonymised again with the same routine as the original execution
  (:func:`mhvp.privacy.erasure.anonymize_contact`); no lock check is repeated, because the
  release (four eyes, fresh lock check) took place at the original execution,
* a dry run (default) changes nothing,
* every applied replay is recorded as ``contact.anonymized`` with ``replay: true``.

Command line: ``python -m mhvp.privacy.erasure_journal export|replay`` (see
``docs/runbooks/backup.md``, section "Restore nach Kontakt-Anonymisierung").
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.contacts.models import Contact
from mhvp.core.config import get_settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import DomainEvent, emit
from mhvp.core.logging import configure_logging
from mhvp.platform.models import Tenant
from mhvp.privacy.erasure import ANONYMIZED_PREFIX, anonymize_contact

JOURNAL_VERSION = 1
EVENT_TYPE = "contact.anonymized"

OUTCOME_ANONYMIZED = "anonymized"
OUTCOME_WOULD_ANONYMIZE = "would_anonymize"
OUTCOME_ABSENT = "absent"
OUTCOME_ALREADY = "already_anonymized"
OUTCOME_INVALID = "invalid"
CLEAN = {OUTCOME_ANONYMIZED, OUTCOME_WOULD_ANONYMIZE, OUTCOME_ABSENT, OUTCOME_ALREADY}


@dataclass
class ErasureResult:
    tenant_id: str
    event_id: str
    contact_id: str | None
    outcome: str


@dataclass
class ErasureReport:
    apply: bool
    results: list[ErasureResult] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return dict(sorted(Counter(r.outcome for r in self.results).items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "apply": self.apply,
            "counts": self.counts,
            "results": [asdict(r) for r in self.results],
        }


def parse_since(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def export_journal(
    factory: async_sessionmaker[AsyncSession],
    *,
    since: datetime,
    tenant_ids: list[uuid.UUID] | None = None,
) -> dict[str, Any]:
    if tenant_ids is None:
        async with platform_transaction(factory) as session:
            tenant_ids = list(await session.scalars(select(Tenant.id).order_by(Tenant.id)))
    entries: list[dict[str, Any]] = []
    for tenant_id in tenant_ids:
        async with tenant_transaction(factory, tenant_id) as session:
            rows = (
                await session.scalars(
                    select(DomainEvent)
                    .where(DomainEvent.type == EVENT_TYPE, DomainEvent.occurred_at >= since)
                    .order_by(DomainEvent.occurred_at, DomainEvent.id)
                )
            ).all()
            for e in rows:
                if e.payload and e.payload.get("replay"):
                    continue  # a replay entry is no new statement
                entries.append(
                    {
                        "tenant_id": str(e.tenant_id),
                        "event_id": str(e.id),
                        "contact_id": str(e.entity_id) if e.entity_id else None,
                        "request_id": (e.payload or {}).get("request_id"),
                        "occurred_at": e.occurred_at.astimezone(UTC).isoformat(),
                    }
                )
    entries.sort(key=lambda x: (x["occurred_at"], x["event_id"]))
    return {
        "version": JOURNAL_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "since": since.isoformat(),
        "tenants": [str(t) for t in tenant_ids],
        "entries": entries,
    }


def read_journal(path: Path) -> dict[str, Any]:
    journal = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(journal, dict) or journal.get("version") != JOURNAL_VERSION:
        raise ValueError("Unbekanntes Journalformat: version fehlt oder wird nicht unterstützt.")
    if not isinstance(journal.get("entries"), list):
        raise ValueError("Unbekanntes Journalformat: entries fehlt.")
    return journal


def _ids(raw: Any) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID] | None:
    try:
        return (
            uuid.UUID(str(raw["tenant_id"])),
            uuid.UUID(str(raw["event_id"])),
            uuid.UUID(str(raw["contact_id"])),
        )
    except (KeyError, ValueError, TypeError):
        return None


def is_anonymized(contact: Contact) -> bool:
    return bool(contact.blocked and (contact.display_name or "").startswith(ANONYMIZED_PREFIX))


async def replay_journal(
    factory: async_sessionmaker[AsyncSession], journal: dict[str, Any], *, apply: bool
) -> ErasureReport:
    report = ErasureReport(apply=apply)
    for raw in journal["entries"]:
        ids = _ids(raw) if isinstance(raw, dict) else None
        if ids is None:
            report.results.append(
                ErasureResult(
                    "",
                    str((raw or {}).get("event_id", "")) if isinstance(raw, dict) else "",
                    None,
                    OUTCOME_INVALID,
                )
            )
            continue
        tenant_id, event_id, contact_id = ids
        async with tenant_transaction(factory, tenant_id) as session:
            contact = await session.get(Contact, contact_id)
            if contact is None:
                outcome = OUTCOME_ABSENT
            elif is_anonymized(contact):
                outcome = OUTCOME_ALREADY
            elif not apply:
                outcome = OUTCOME_WOULD_ANONYMIZE
            else:
                removed = await anonymize_contact(session, contact, None)
                await emit(
                    session,
                    tenant_id=tenant_id,
                    type=EVENT_TYPE,
                    entity_type="contact",
                    entity_id=contact_id,
                    actor_user_id=None,
                    payload={
                        "replay": True,
                        "journal_event_id": str(event_id),
                        "removed": removed,
                    },
                )
                outcome = OUTCOME_ANONYMIZED
        report.results.append(
            ErasureResult(str(tenant_id), str(event_id), str(contact_id), outcome)
        )
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Löschjournal der Kontakt-Anonymisierungen.")
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="Journal aus den Ereignissen exportieren")
    exp.add_argument("--since", required=True, help="ISO 8601 (JJJJ-MM-TT oder Zeitstempel)")
    exp.add_argument("--out", required=True, type=Path)
    exp.add_argument("--tenant", action="append", type=uuid.UUID, default=None)
    rep = sub.add_parser("replay", help="Journal nach der Wiederherstellung anwenden")
    rep.add_argument("--journal", required=True, type=Path)
    rep.add_argument("--apply", action="store_true", help="Ohne diese Option nur Prüfung")
    rep.add_argument("--report", type=Path, default=None)
    return parser.parse_args(argv)


async def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        if args.command == "export":
            journal = await export_journal(
                factory, since=parse_since(args.since), tenant_ids=args.tenant
            )
            args.out.write_text(
                json.dumps(journal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            print(f"Journal: {len(journal['entries'])} Einträge")  # noqa: T201
            return 0
        try:
            journal = read_journal(args.journal)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"erasure_journal: {exc}", file=sys.stderr)  # noqa: T201
            return 2
        report = await replay_journal(factory, journal, apply=args.apply)
        if args.report is not None:
            args.report.write_text(
                json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        for r in report.results:
            print(f"{r.outcome:20} tenant={r.tenant_id} contact={r.contact_id}")  # noqa: T201
        print(f"Summe ({'angewendet' if args.apply else 'nur Prüfung'}): {report.counts}")  # noqa: T201
        return 0 if all(r.outcome in CLEAN for r in report.results) else 1
    finally:
        await engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(asyncio.run(run()))
