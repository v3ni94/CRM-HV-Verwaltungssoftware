"""Structured logging (structlog, JSON by default) with correlation ids.

Request bodies and query strings are never logged, so personal data does not reach the
logs by default (section 16, pseudonymisation in logs).
"""

import logging
import sys

import structlog
from structlog.types import Processor

from mhvp.core.config import LogFormat, Settings

_SHARED_PROCESSORS: list[Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
]


def configure_logging(settings: Settings) -> None:
    renderer: Processor
    if settings.log_format is LogFormat.CONSOLE:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    # Uvicorn's own access log would include query strings; the correlation middleware
    # writes a sanitised access log instead.
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    access.disabled = True

    # HTTP client libraries log full URLs including query strings at INFO level.
    for name in ("httpx", "httpx2", "httpcore", "httpcore2", "anthropic", "botocore", "urllib3"):
        logging.getLogger(name).setLevel(max(logging.WARNING, root.level))


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.stdlib.get_logger(name)
    return logger
