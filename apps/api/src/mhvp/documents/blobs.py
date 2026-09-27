"""Originals in the S3 object store (11.2 ``MinioStore``). Keys never contain user input.

A missing configuration or an unreachable store answers with the registered problem
``MHVP-DOC-0007`` (503, ADR 0004) instead of an unhandled exception; the underlying error is
logged without credentials. The upload happens before any index row is written, so a failed
put leaves no half written document (rule 0.1.7). ``get`` and ``delete`` map storage errors the
same way; a document row is never left pointing at a half deleted original.
"""

import logging
import uuid
from typing import TYPE_CHECKING

from botocore.exceptions import BotoCoreError, ClientError

from mhvp.core.config import Settings
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.storage import create_s3_client

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

log = logging.getLogger(__name__)
_NOT_CONFIGURED = (
    "Der Dokumentenspeicher ist nicht eingerichtet. Bitte die Systemverwaltung informieren."
)
_UNREACHABLE = (
    "Der Dokumentenspeicher ist derzeit nicht erreichbar. Es wurde nichts gespeichert, "
    "bitte später erneut versuchen."
)


class BlobStore:
    def __init__(self, settings: Settings, client: "S3Client | None" = None) -> None:
        try:
            self._client = client or create_s3_client(settings)
        except ValueError as exc:
            log.error("object storage not configured: %s", exc)
            raise ProblemError(ErrorCodes.STORAGE_UNAVAILABLE, detail=_NOT_CONFIGURED) from exc
        self._bucket = settings.s3_bucket
        # Exposed so that ``store_document`` reaches the scan settings without a new argument
        # at its thirty call sites.
        self.settings = settings

    @staticmethod
    def key(tenant_id: uuid.UUID, document_id: uuid.UUID) -> str:
        return f"tenants/{tenant_id}/documents/{document_id}"

    def put(self, key: str, data: bytes, mime_type: str, sha256: str) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=mime_type,
                Metadata={"sha256": sha256},
            )
        except (BotoCoreError, ClientError) as exc:
            log.error("object storage put failed for %s: %s", key, type(exc).__name__)
            raise ProblemError(ErrorCodes.STORAGE_UNAVAILABLE, detail=_UNREACHABLE) from exc

    def get(self, key: str) -> bytes:
        try:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            log.error("object storage get failed for %s: %s", key, type(exc).__name__)
            raise ProblemError(ErrorCodes.STORAGE_UNAVAILABLE, detail=_UNREACHABLE) from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            log.error("object storage delete failed for %s: %s", key, type(exc).__name__)
            raise ProblemError(ErrorCodes.STORAGE_UNAVAILABLE, detail=_UNREACHABLE) from exc
