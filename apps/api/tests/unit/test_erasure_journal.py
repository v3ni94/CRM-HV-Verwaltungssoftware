"""GAI-512: pure parts of the contact erasure journal (replay against a database is covered
by the restore procedure in docs/runbooks/backup.md)."""

import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from mhvp.privacy import erasure_journal as ej


def test_is_anonymized_needs_label_and_block() -> None:
    label = f"{ej.ANONYMIZED_PREFIX} 1234abcd"
    assert ej.is_anonymized(cast(Any, SimpleNamespace(blocked=True, display_name=label)))
    assert not ej.is_anonymized(cast(Any, SimpleNamespace(blocked=False, display_name=label)))
    assert not ej.is_anonymized(cast(Any, SimpleNamespace(blocked=True, display_name="Erika")))


def test_entry_ids_validated() -> None:
    good = {
        "tenant_id": str(uuid.uuid4()),
        "event_id": str(uuid.uuid4()),
        "contact_id": str(uuid.uuid4()),
    }
    assert ej._ids(good) is not None
    assert ej._ids({**good, "contact_id": "x"}) is None
    assert ej._ids({"tenant_id": good["tenant_id"]}) is None


def test_read_journal_rejects_unknown_format(tmp_path: Path) -> None:
    path = tmp_path / "j.json"
    path.write_text(json.dumps({"version": 99, "entries": []}))
    with pytest.raises(ValueError, match="Journalformat"):
        ej.read_journal(path)
    path.write_text(json.dumps({"version": ej.JOURNAL_VERSION, "entries": []}))
    assert ej.read_journal(path)["entries"] == []


def test_report_counts() -> None:
    report = ej.ErasureReport(apply=False)
    report.results += [ej.ErasureResult("t", "e", "c", ej.OUTCOME_ABSENT)] * 2
    assert report.counts == {ej.OUTCOME_ABSENT: 2}
