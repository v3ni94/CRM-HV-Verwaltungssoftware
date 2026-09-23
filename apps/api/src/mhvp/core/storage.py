"""S3 client factory. The platform uses only the S3 API, no vendor extensions (ADR 0005)."""

from typing import TYPE_CHECKING

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from mhvp.core.config import Settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def create_s3_client(settings: Settings) -> "S3Client":
    access_key, secret_key = settings.s3_access_key_id, settings.s3_secret_access_key
    if not settings.s3_endpoint_url or access_key is None or secret_key is None:
        raise ValueError("object storage is not configured (MHVP_S3_*)")
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=access_key.get_secret_value(),
        aws_secret_access_key=secret_key.get_secret_value(),
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=2,
            read_timeout=5,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )


def ensure_bucket(client: "S3Client", bucket: str) -> bool:
    """Create ``bucket`` if missing. Returns True if it was created."""
    try:
        client.head_bucket(Bucket=bucket)
        return False
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code not in {"404", "NoSuchBucket", "NotFound"}:
            raise
    client.create_bucket(Bucket=bucket)
    return True
