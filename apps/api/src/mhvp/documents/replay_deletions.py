"""``python -m mhvp.documents.replay_deletions --journal <file> [--apply]`` (D47, M9-03).

Replays the exported deletion journal against a restored database. Without ``--apply`` the
run only reports what would happen. Documents under a deletion hold, with a blocking retention
rule, with a different content hash or with an open DMS mirror are never deleted; they are
listed for manual review. Exit code 0 when every entry was applied or is absent, 1 when
entries were kept for review, 2 for an unreadable journal.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mhvp.core.config import get_settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.logging import configure_logging, get_logger
from mhvp.documents.blobs import BlobStore
from mhvp.documents.deletion_journal import (
    OUTCOME_ABSENT,
    OUTCOME_DELETED,
    OUTCOME_SKIPPED,
    OUTCOME_WOULD_DELETE,
    read_journal,
    replay_journal,
)

CLEAN = {OUTCOME_ABSENT, OUTCOME_DELETED, OUTCOME_SKIPPED, OUTCOME_WOULD_DELETE}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Löschjournal nach einer Wiederherstellung erneut anwenden."
    )
    parser.add_argument("--journal", required=True, type=Path, help="Journaldatei (JSON)")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Löschungen tatsächlich ausführen; ohne diese Option nur Prüfung",
    )
    parser.add_argument(
        "--report", type=Path, default=None, help="Ergebnis zusätzlich als JSON schreiben"
    )
    return parser.parse_args(argv)


async def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        journal = read_journal(args.journal)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"replay_deletions: {exc}", file=sys.stderr)  # noqa: T201
        return 2
    settings = get_settings()
    configure_logging(settings)
    log = get_logger("mhvp.replay_deletions")
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        report = await replay_journal(factory, journal, BlobStore(settings), apply=args.apply)
    finally:
        await engine.dispose()
    if args.report is not None:
        args.report.write_text(
            json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    for r in report.results:
        line = f"{r.outcome:20} tenant={r.tenant_id} document={r.document_id}"
        print(line + (f" ({r.reason})" if r.reason else ""))  # noqa: T201
    log.info("deletion_journal_replayed", apply=args.apply, **report.counts)
    print(f"Summe ({'angewendet' if args.apply else 'nur Prüfung'}): {report.counts}")  # noqa: T201
    return 0 if all(r.outcome in CLEAN for r in report.results) else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(asyncio.run(run()))
