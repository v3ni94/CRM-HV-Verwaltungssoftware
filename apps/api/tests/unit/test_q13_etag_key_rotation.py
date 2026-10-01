"""S12-04 (optional If-Match helper), M2-02 path guard and S16-03 (generic key rotation):
unit level, no database."""

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.core import crypto
from mhvp.core.auth.principal import Principal
from mhvp.core.auth.scope import property_path_guard
from mhvp.core.etag import check_if_match, etag_of
from mhvp.core.key_rotation import (
    RotationError,
    discover_targets,
    rotate_blob,
    unpaired_fingerprint_columns,
)
from mhvp.core.problems import ProblemError

OLD = b"o" * 32
NEW = b"n" * 32


def test_etag_from_version_and_timestamp() -> None:
    assert etag_of(3) == '"3"'
    ts = datetime(2026, 9, 30, 12, 0, 0, 123456, tzinfo=UTC)
    assert etag_of(ts) == f'"t{1790769600123456}"'
    check_if_match(None, 3)  # no header: unchecked
    check_if_match('"3"', 3)
    check_if_match('W/"3"', 3)
    check_if_match("*", 3)
    check_if_match('"1", "3"', 3)
    with pytest.raises(ProblemError) as exc:
        check_if_match('"2"', 3)
    assert exc.value.error.status == 412


def _principal(**kw: Any) -> Principal:
    base: dict[str, Any] = {
        "user_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "roles": ("standard",),
        "permissions": frozenset(),
    }
    base.update(kw)
    return Principal(**base)


def test_property_path_guard() -> None:
    own, foreign = uuid.uuid4(), uuid.uuid4()
    principal = _principal(property_ids=(own,))

    def request(value: str | None) -> Any:
        params = {} if value is None else {"property_id": value}
        return SimpleNamespace(path_params=params, state=SimpleNamespace(principal=principal))

    asyncio.run(property_path_guard(request(None)))
    asyncio.run(property_path_guard(request("kein-uuid")))
    asyncio.run(property_path_guard(request(str(own))))
    with pytest.raises(ProblemError) as exc:
        asyncio.run(property_path_guard(request(str(foreign))))
    assert exc.value.error.status == 404


def test_rotate_blob_roundtrip_and_idempotent() -> None:
    scope = str(uuid.uuid4())
    blob = crypto.encrypt_with_master(OLD, "DE02120300000000202051", scope)
    status, fresh, plaintext, found_scope = rotate_blob(OLD, NEW, blob)
    assert status == "rotated"
    assert found_scope == scope
    assert fresh is not None
    assert plaintext == "DE02120300000000202051"
    assert crypto.decrypt_with_master(NEW, fresh) == plaintext
    assert crypto.ciphertext_scope(fresh) == scope
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt_with_master(OLD, fresh)
    again = rotate_blob(OLD, NEW, fresh)
    assert again[0] == "already_rotated"
    assert again[1] is None
    with pytest.raises(crypto.CryptoError):
        rotate_blob(b"x" * 32, NEW, blob)  # wrong old key: error, never a silent skip


def test_fingerprint_with_master_matches_process_key() -> None:
    crypto.set_master_key(OLD)
    scope = str(uuid.uuid4())
    assert crypto.fingerprint("abc", scope) == crypto.fingerprint_with_master(OLD, "abc", scope)
    assert crypto.fingerprint_with_master(NEW, "abc", scope) != crypto.fingerprint("abc", scope)


def test_discovery_finds_encrypted_columns_and_pairs() -> None:
    import mhvp.models  # noqa: F401

    targets = {t.table.name: t for t in discover_targets()}
    assert "contact_bank_account" in targets
    account = targets["contact_bank_account"]
    assert "iban" in account.columns
    assert account.fingerprints.get("iban") == "iban_fingerprint"
    for table, column in unpaired_fingerprint_columns():
        assert column.endswith("fingerprint")
        assert (
            column.removesuffix("_fingerprint")
            not in targets.get(table.name, SimpleNamespace(columns=())).columns
        )


def test_same_key_is_refused() -> None:
    from mhvp.core.key_rotation import run

    with pytest.raises(RotationError):
        asyncio.run(run(None, OLD, OLD, dry_run=True))  # type: ignore[arg-type]
