"""Originals in the S3 object store (11.2 ``MinioStore``). Keys never contain user input.

A missing configuration or an unreachable store answers with the registered problem
``MHVP-DOC-0007`` (503, ADR 0004) instead of an unhandled exception; the underlying error is
logged without credentials. The upload happens before any index row is written, so a failed
put leaves no half written document (rule 0.1.7). ``get`` and ``delete`` map storage errors the
same way; a document row is never left pointing at a half deleted original.
"""

import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from botocore.exceptions import BotoCoreError, ClientError

from mhvp.core.config import Settings
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.storage import create_s3_client

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

log = logging.getLogger(__name__)
TMP_PREFIX = "tmp/"
TMP_DAYS = 1
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

    def exists(self, key: str) -> bool:
        """True when the object is still stored (deletion checklist, AC07)."""
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            log.error("object storage head failed for %s: %s", key, type(exc).__name__)
            raise ProblemError(ErrorCodes.STORAGE_UNAVAILABLE, detail=_UNREACHABLE) from exc
        except BotoCoreError as exc:
            log.error("object storage head failed for %s: %s", key, type(exc).__name__)
            raise ProblemError(ErrorCodes.STORAGE_UNAVAILABLE, detail=_UNREACHABLE) from exc
        return True

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            log.error("object storage delete failed for %s: %s", key, type(exc).__name__)
            raise ProblemError(ErrorCodes.STORAGE_UNAVAILABLE, detail=_UNREACHABLE) from exc

    # Temporary objects (M6-08, S12-06) -----------------------------------------------------

    @staticmethod
    def tmp_key(tenant_id: uuid.UUID, upload_id: uuid.UUID) -> str:
        """Staging key of a presigned upload. Everything below ``TMP_PREFIX`` is temporary:
        the lifecycle rule and the cleanup job remove it after ``TMP_DAYS``."""
        return f"{TMP_PREFIX}{tenant_id}/uploads/{upload_id}"

    @property
    def client(self) -> "S3Client":
        return self._client

    @property
    def bucket(self) -> str:
        return self._bucket

    def ensure_tmp_lifecycle(self) -> bool:
        """Lifecycle rule for temporary objects (11.2 MinioStore, M6-08): expire ``tmp/``
        after ``TMP_DAYS`` and abort incomplete multipart uploads. Returns False when the store
        refuses lifecycle rules; the cleanup job then does the same work."""
        rule = {
            "ID": "mhvp-tmp-expiry",
            "Filter": {"Prefix": TMP_PREFIX},
            "Status": "Enabled",
            "Expiration": {"Days": TMP_DAYS},
            "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": TMP_DAYS},
        }
        try:
            self._client.put_bucket_lifecycle_configuration(
                Bucket=self._bucket,
                LifecycleConfiguration={"Rules": [rule]},  # type: ignore[list-item]
            )
        except (BotoCoreError, ClientError) as exc:
            log.warning("object storage lifecycle rule not set: %s", type(exc).__name__)
            return False
        return True

    def purge_tmp(self, older_than: datetime) -> int:
        """Deletes temporary objects last modified before ``older_than``; returns the count."""
        removed = 0
        token: str | None = None
        try:
            while True:
                kwargs: dict[str, Any] = {"Bucket": self._bucket, "Prefix": TMP_PREFIX}
                if token:
                    kwargs["ContinuationToken"] = token
                page = self._client.list_objects_v2(**kwargs)
                for item in page.get("Contents", []):
                    if item["LastModified"] < older_than:
                        self._client.delete_object(Bucket=self._bucket, Key=item["Key"])
                        removed += 1
                if not page.get("IsTruncated"):
                    return removed
                token = page.get("NextContinuationToken")
        except (BotoCoreError, ClientError) as exc:
            log.error("object storage tmp cleanup failed: %s", type(exc).__name__)
            raise ProblemError(ErrorCodes.STORAGE_UNAVAILABLE, detail=_UNREACHABLE) from exc

    def get_tmp(self, key: str, limit: int) -> bytes | None:
        """Content of a staged upload or None when it is missing; larger than ``limit`` is
        read only up to ``limit + 1`` bytes so the size check can refuse it."""
        try:
            body = self._client.get_object(Bucket=self._bucket, Key=key)["Body"]
            return body.read(limit + 1)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            log.error("object storage get failed for %s: %s", key, type(exc).__name__)
            raise ProblemError(ErrorCodes.STORAGE_UNAVAILABLE, detail=_UNREACHABLE) from exc
        except BotoCoreError as exc:
            log.error("object storage get failed for %s: %s", key, type(exc).__name__)
            raise ProblemError(ErrorCodes.STORAGE_UNAVAILABLE, detail=_UNREACHABLE) from exc
