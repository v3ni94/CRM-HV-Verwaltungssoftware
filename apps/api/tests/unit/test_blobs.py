"""``BlobStore``: ``put``, ``get`` and ``delete`` map storage errors to the registered problem
``MHVP-DOC-0007`` (503, ADR 0004) without leaking the underlying error text."""

from typing import Any

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore
from tests.conftest import make_settings


class _FailingClient:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def put_object(self, **kwargs: Any) -> None:
        raise self.exc

    def get_object(self, **kwargs: Any) -> None:
        raise self.exc

    def delete_object(self, **kwargs: Any) -> None:
        raise self.exc


def _store(exc: Exception) -> BlobStore:
    return BlobStore(make_settings(), client=_FailingClient(exc))  # type: ignore[arg-type]


_ERRORS = [
    ClientError({"Error": {"Code": "NoSuchBucket", "Message": "testing-secret"}}, "GetObject"),
    EndpointConnectionError(endpoint_url="http://minio.invalid:9000"),
]


@pytest.mark.parametrize("exc", _ERRORS, ids=["client_error", "botocore_error"])
def test_get_and_delete_answer_storage_unavailable(exc: Exception) -> None:
    store = _store(exc)
    for call in (lambda: store.get("k"), lambda: store.delete("k")):
        with pytest.raises(ProblemError) as info:
            call()
        assert info.value.error is ErrorCodes.STORAGE_UNAVAILABLE
        assert "nicht erreichbar" in str(info.value.detail)
        assert "testing-secret" not in str(info.value.detail)


def test_put_keeps_the_same_mapping() -> None:
    with pytest.raises(ProblemError) as info:
        _store(_ERRORS[0]).put("k", b"x", "text/plain", "abc")
    assert info.value.error is ErrorCodes.STORAGE_UNAVAILABLE
