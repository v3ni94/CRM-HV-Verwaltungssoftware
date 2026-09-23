"""Originals in the S3 object store (11.2 ``MinioStore``). Keys never contain user input."""

import uuid
from typing import TYPE_CHECKING

from mhvp.core.config import Settings
from mhvp.core.storage import create_s3_client

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class BlobStore:
    def __init__(self, settings: Settings, client: "S3Client | None" = None) -> None:
        self._client = client or create_s3_client(settings)
        self._bucket = settings.s3_bucket

    @staticmethod
    def key(tenant_id: uuid.UUID, document_id: uuid.UUID) -> str:
        return f"tenants/{tenant_id}/documents/{document_id}"

    def put(self, key: str, data: bytes, mime_type: str, sha256: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=mime_type,
            Metadata={"sha256": sha256},
        )

    def get(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)
