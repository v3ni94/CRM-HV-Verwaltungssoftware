"""One-shot job (migrate service): make sure the object storage bucket exists.

Run with ``python -m mhvp.core.storage_bootstrap``. Idempotent.
"""

import sys

from mhvp.core.config import get_settings
from mhvp.core.logging import configure_logging, get_logger
from mhvp.core.storage import create_s3_client, ensure_bucket


def main() -> int:
    settings = get_settings()
    configure_logging(settings)
    log = get_logger("mhvp.storage_bootstrap")
    if not settings.s3_configured:
        log.error("object_storage_not_configured")
        return 1
    created = ensure_bucket(create_s3_client(settings), settings.s3_bucket)
    log.info("object_storage_bucket_ready", bucket=settings.s3_bucket, created=created)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
