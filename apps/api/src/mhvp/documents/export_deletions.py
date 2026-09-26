"""``python -m mhvp.documents.export_deletions --since <date> --out <file>`` (D47, M9-03).

Exports the deletion journal (deletions, refusals, holds) of all tenants since the given
date from the append-only domain events. Run it before a restore; replay it afterwards with
``python -m mhvp.documents.replay_deletions`` (see ``docs/runbooks/backup.md``).
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from mhvp.core.config import get_settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.logging import configure_logging, get_logger
from mhvp.documents.deletion_journal import export_journal, parse_since, write_journal


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Löschjournal aus den Ereignissen exportieren.")
    parser.add_argument(
        "--since",
        required=True,
        help="Beginn (TT.MM.JJJJ ist nicht erlaubt, ISO 8601: JJJJ-MM-TT oder Zeitstempel). "
        "Wählen Sie den Zeitpunkt des ältesten Backups, das zurückgespielt werden könnte.",
    )
    parser.add_argument("--out", required=True, type=Path, help="Zieldatei (JSON)")
    parser.add_argument(
        "--tenant",
        action="append",
        type=uuid.UUID,
        default=None,
        help="Nur diesen Mandanten (mehrfach möglich); Standard: alle Mandanten",
    )
    return parser.parse_args(argv)


async def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings)
    log = get_logger("mhvp.export_deletions")
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        journal = await export_journal(
            factory, since=parse_since(args.since), tenant_ids=args.tenant
        )
        write_journal(journal, args.out)
        log.info(
            "deletion_journal_exported",
            path=str(args.out),
            entries=len(journal["entries"]),
            tenants=len(journal["tenants"]),
        )
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(asyncio.run(run()))
