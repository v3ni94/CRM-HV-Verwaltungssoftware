"""AG18: the inspection ownership scan is registered in the automation job catalogue."""

from pathlib import Path

import mhvp.worker as worker_module
from mhvp.automation.models import JOB_CATALOG


def test_inspection_ownership_scan_registered() -> None:
    assert "hoa-inspection-ownership-scan" in JOB_CATALOG
    source = Path(worker_module.__file__).read_text(encoding="utf-8")
    assert '"hoa-inspection-ownership-scan"' in source


def test_every_catalogue_key_is_a_beat_entry() -> None:
    source = Path(worker_module.__file__).read_text(encoding="utf-8")
    for key in JOB_CATALOG:
        assert f'"{key}"' in source, key
