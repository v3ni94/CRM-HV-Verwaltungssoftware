"""AJ10 (GAI-313 to GAI-315): bounded reads, 413, type checks, webhook body limit."""

from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers
from starlette.requests import Request

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.uploads import (
    check_dump_file,
    check_text_dump,
    check_zip_file,
    check_zip_signature,
    read_body_limited,
    read_limited,
)


def _upload(name: str, data: bytes, mime: str = "application/octet-stream") -> UploadFile:
    return UploadFile(io.BytesIO(data), filename=name, headers=Headers({"content-type": mime}))


def _request(chunks: list[bytes], content_length: str | None = None) -> Request:
    headers = [(b"content-length", content_length.encode())] if content_length else []
    queue = [{"type": "http.request", "body": c, "more_body": True} for c in chunks]
    queue.append({"type": "http.request", "body": b"", "more_body": False})

    async def receive() -> dict:
        return queue.pop(0)

    scope = {"type": "http", "method": "POST", "headers": headers, "path": "/"}
    return Request(scope, receive)


def test_read_limited_within_limit() -> None:
    assert asyncio.run(read_limited(_upload("a.csv", b"abc"), 3)) == b"abc"


def test_read_limited_over_limit_is_413_with_code() -> None:
    with pytest.raises(ProblemError) as err:
        asyncio.run(read_limited(_upload("a.csv", b"abcd"), 3))
    assert err.value.error is ErrorCodes.UPLOAD_TOO_LARGE
    assert ErrorCodes.UPLOAD_TOO_LARGE.status == 413
    assert ErrorCodes.UPLOAD_TOO_LARGE.code == "MHVP-DOC-0010"


def test_read_limited_stops_reading_early() -> None:
    upload = _upload("a.csv", b"x" * (3 * 1024 * 1024))
    with pytest.raises(ProblemError):
        asyncio.run(read_limited(upload, 10))
    assert upload.file.tell() <= 11


def test_body_limited_declared_and_chunked() -> None:
    with pytest.raises(ProblemError):
        asyncio.run(read_body_limited(_request([b"a"], "999"), 10))
    with pytest.raises(ProblemError) as err:
        asyncio.run(
            read_body_limited(
                _request([b"a" * 8, b"b" * 8]), 10, error=ErrorCodes.WEBHOOK_TOO_LARGE
            )
        )
    assert err.value.error is ErrorCodes.WEBHOOK_TOO_LARGE
    assert asyncio.run(read_body_limited(_request([b"ab", b"cd"]), 10)) == b"abcd"


def test_dump_and_zip_type_checks() -> None:
    check_dump_file(_upload("dump.sql", b"x", "application/sql"))
    check_dump_file(_upload("dump.sql", b"x"))
    for bad in (_upload("dump.exe", b"x"), _upload("dump.sql", b"x", "image/png")):
        with pytest.raises(ProblemError):
            check_dump_file(bad)
    check_zip_file(_upload("a.zip", b"x", "application/zip"))
    with pytest.raises(ProblemError):
        check_zip_file(_upload("a.sql", b"x", "application/zip"))
    check_zip_signature(b"PK\x03\x04rest")
    with pytest.raises(ProblemError):
        check_zip_signature(b"not a zip")
    check_text_dump(b"INSERT INTO t VALUES (1);")
    with pytest.raises(ProblemError):
        check_text_dump(b"PK\x03\x04")
    with pytest.raises(ProblemError):
        check_text_dump(b"a\x00b")
