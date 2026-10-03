"""AO12-01: ``export_deletions --out -`` keeps stdout free of log lines (backup journal)."""

import logging
import sys

import pytest

from mhvp.core.config import get_settings
from mhvp.core.logging import configure_logging, get_logger
from mhvp.documents import export_deletions


def test_logs_go_to_stderr_with_stdout_target(capsys: pytest.CaptureFixture[str]) -> None:
    root = logging.getLogger()
    saved = list(root.handlers)
    try:
        configure_logging(get_settings())
        # configure_logging binds sys.stdout at call time; rebind to the captured stream.
        for handler in root.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setStream(sys.stdout)
        export_deletions._logs_to_stderr()
        get_logger("mhvp.test_ao12").warning("ao12_probe")
        out, err = capsys.readouterr()
        assert "ao12_probe" not in out
        assert "ao12_probe" in err
    finally:
        root.handlers = saved
