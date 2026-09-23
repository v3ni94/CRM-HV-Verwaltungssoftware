"""Export the OpenAPI document: ``python -m mhvp.openapi > openapi.json``.

Uses constructed settings (no environment, no connections), so the output is deterministic
and CI can detect drift against the committed ``apps/api/openapi.json``.
"""

import json
import sys
from typing import Any

from pydantic import SecretStr

from mhvp.core.config import Settings
from mhvp.main import create_app

_PLACEHOLDER = SecretStr("unused://openapi-export")


def build_openapi() -> dict[str, Any]:
    settings = Settings.model_construct(
        database_url=_PLACEHOLDER, redis_url=_PLACEHOLDER, celery_broker_url=_PLACEHOLDER
    )
    return create_app(settings).openapi()


def render_openapi() -> str:
    return json.dumps(build_openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":  # pragma: no cover
    sys.stdout.write(render_openapi())
