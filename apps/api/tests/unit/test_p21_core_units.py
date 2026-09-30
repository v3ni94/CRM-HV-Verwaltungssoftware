"""P21 unit tests: bulk report, rule templates, presigned URLs."""

import uuid
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from moto import mock_aws

from mhvp.automation.schemas import AutomationRuleIn
from mhvp.automation.templates import RULE_TEMPLATES
from mhvp.core.bulk import run_bulk
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.storage import presigned_download_url, presigned_upload_url


async def test_bulk_reports_partial_success() -> None:
    ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    seen: list[uuid.UUID] = []

    async def action(item: uuid.UUID) -> None:
        seen.append(item)
        if item == ids[1]:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="fehlt")

    report = await run_bulk([*ids, ids[0]], action)
    assert (report.total, report.succeeded, report.failed) == (3, 2, 1)
    assert report.items[1].ok is False
    assert report.items[1].detail == "fehlt"
    assert len(seen) == 3


def test_rule_templates_are_valid_and_inactive() -> None:
    for template in RULE_TEMPLATES:
        body: dict[str, Any] = {k: v for k, v in template.items() if k != "key"}
        rule = AutomationRuleIn(**body)
        assert rule.active is False


def test_presigned_urls_are_signed_and_expire() -> None:
    with mock_aws():
        client = boto3.client(
            "s3", region_name="us-east-1", config=BotoConfig(signature_version="s3v4")
        )
        get = presigned_download_url(client, "b", "k/1", filename='a"b.pdf', expires=60)
        put = presigned_upload_url(client, "b", "k/2", content_type="application/pdf")
    assert "X-Amz-Signature" in get
    assert "X-Amz-Expires=60" in get
    assert "ab.pdf" in get
    assert "X-Amz-Signature" in put
