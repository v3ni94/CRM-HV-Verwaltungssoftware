import json
import logging

import pytest

from mhvp.core.config import LogFormat
from mhvp.core.logging import configure_logging, get_logger
from tests.conftest import make_settings


def test_json_logging(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(make_settings(log_format=LogFormat.JSON))
    get_logger("mhvp.test").info("hello", amount_cents=100)
    line = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["event"] == "hello"
    assert payload["level"] == "info"
    assert payload["amount_cents"] == 100
    assert payload["timestamp"].endswith("Z")


def test_uvicorn_access_log_disabled() -> None:
    configure_logging(make_settings(log_format=LogFormat.CONSOLE))
    assert logging.getLogger("uvicorn.access").disabled is True
    configure_logging(make_settings())


def test_http_client_loggers_do_not_log_urls() -> None:
    configure_logging(make_settings(log_level="DEBUG"))
    for name in ("httpx", "httpcore", "botocore", "urllib3"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING
