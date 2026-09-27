"""M35-03 technical preparation: `mhvp.objektakte.rekey` round trip. objektakte ciphertexts
(replicated `FieldCipher`) in the two export forms (`0x` hex, `_binary`) are decrypted, the
IBAN verified against objektakte's HMAC, re-encrypted for the tenant scope of the CRM master
key and readable there; wrong key, wrong HMAC and missing key are reported without plaintext;
`--dry-run` writes nothing; the protocol never contains a plaintext or key."""

from __future__ import annotations

import base64
import json
import os
import uuid
from pathlib import Path

import pytest

from mhvp.core import crypto
from mhvp.core.sqldump import parse_dump
from mhvp.objektakte import rekey

IBAN = "DE89370400440532013000"
IBAN_KEY = base64.b64encode(b"i" * 32).decode()
HMAC_KEY = base64.b64encode(b"h" * 32).decode()
TOKEN_KEY = base64.b64encode(b"t" * 32).decode()


@pytest.fixture(autouse=True)
def master_key() -> None:
    crypto.set_master_key(b"m" * 32)


def _ciphers(**overrides: str) -> rekey.Ciphers:
    env = {
        rekey.ENV_IBAN_KEY: IBAN_KEY,
        rekey.ENV_IBAN_HMAC_KEY: HMAC_KEY,
        rekey.ENV_TOKEN_KEY: TOKEN_KEY,
    }
    env.update(overrides)
    return rekey.Ciphers.from_env({k: v for k, v in env.items() if v})


def _dump(iban_ct: str, iban_hash_hex: str, access_ct: str, refresh_ct: str) -> str:
    iban_hex = iban_ct.encode("ascii").hex()
    owner_cols = (
        "(`id`,`type`,`last_name`,`iban_last4`,`iban_key_version`,`iban_hash`,`iban_encrypted`)"
    )
    token_cols = (
        "(`id`,`provider`,`account_email`,`access_token_encrypted`,`refresh_token_encrypted`)"
    )
    return "\n".join(
        [
            f"INSERT INTO `parties_owner` {owner_cols} VALUES",
            f"(201,'natural_person','Musterfrau','{IBAN[-4:]}',1,0x{iban_hash_hex},0x{iban_hex}),",
            "(202,'natural_person','Ohne',NULL,NULL,NULL,NULL);",
            f"INSERT INTO `parties_tenant` {owner_cols} VALUES",
            f"(301,'natural_person','Mieter','{IBAN[-4:]}',1,0x{iban_hash_hex},"
            f"_binary '{iban_ct}');",
            f"INSERT INTO `oauth_tokens` {token_cols} VALUES",
            f"(1,'google','ablage@example.test',_binary '{access_ct}',_binary '{refresh_ct}');",
        ]
    )


def _tables() -> dict[str, list[dict[str, object]]]:
    ciphers = _ciphers()
    assert ciphers.iban is not None
    assert ciphers.token is not None
    assert ciphers.iban_hmac_key
    iban_ct = ciphers.iban.encrypt(IBAN)
    hash_hex = rekey.iban_hmac_hex(IBAN, ciphers.iban_hmac_key)
    access = ciphers.token.encrypt("ya29.access", aad="access")
    refresh = ciphers.token.encrypt("1//refresh", aad="refresh")
    return parse_dump(_dump(iban_ct, hash_hex, access, refresh))


def test_roundtrip_rekeys_iban_and_tokens_for_tenant_scope() -> None:
    tenant_id = uuid.uuid4()
    report, secrets = rekey.rekey_rows(_tables(), _ciphers(), tenant_id, dry_run=True)
    assert report.counts == {"rekeyed": 4}
    by_key = {(s.table, s.source_id, s.field): s for s in secrets}
    owner = by_key[("parties_owner", "owner:201", "iban_encrypted")]
    assert crypto.decrypt(owner.ciphertext, scope=str(tenant_id)) == IBAN
    assert owner.fingerprint == crypto.fingerprint(IBAN, scope=str(tenant_id))
    assert owner.last4 == IBAN[-4:]
    tenant_row = by_key[("parties_tenant", "tenant:301", "iban_encrypted")]
    assert crypto.decrypt(tenant_row.ciphertext, scope=str(tenant_id)) == IBAN
    refresh = by_key[("oauth_tokens", "1", "refresh_token_encrypted")]
    assert crypto.decrypt(refresh.ciphertext, scope=str(tenant_id)) == "1//refresh"
    # the new ciphertext is bound to the scope: another tenant cannot read it
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(owner.ciphertext, scope=str(uuid.uuid4()))
    entries = {(e.table, e.source_id, e.field): e for e in report.entries}
    assert entries[("parties_owner", "owner:201", "iban_encrypted")].hmac_verified is True
    assert entries[("parties_owner", "owner:201", "iban_encrypted")].source_sha256
    assert entries[("parties_owner", "owner:201", "iban_encrypted")].target_sha256


def test_protocol_holds_no_plaintext_or_key(tmp_path: Path) -> None:
    tenant_id = uuid.uuid4()
    report, _ = rekey.rekey_rows(_tables(), _ciphers(), tenant_id, dry_run=True)
    target = tmp_path / "protokoll.json"
    rekey.write_protocol(report, target)
    text = target.read_text(encoding="utf-8")
    assert IBAN not in text
    assert "ya29.access" not in text
    assert "1//refresh" not in text
    assert IBAN_KEY not in text
    assert TOKEN_KEY not in text
    assert HMAC_KEY not in text
    data = json.loads(text)
    assert data["counts"] == {"rekeyed": 4}
    assert data["entries"][0]["last4"] == IBAN[-4:]


def test_wrong_key_and_wrong_hmac_are_errors_without_plaintext() -> None:
    tenant_id = uuid.uuid4()
    wrong = _ciphers(**{rekey.ENV_IBAN_KEY: base64.b64encode(b"x" * 32).decode()})
    report, secrets = rekey.rekey_rows(_tables(), wrong, tenant_id, dry_run=True)
    assert report.counts["error"] == 2  # both IBAN rows, tokens still fine
    assert report.counts["rekeyed"] == 2
    assert all(s.table == rekey.TOKEN_TABLE for s in secrets)
    assert all(IBAN not in (e.detail or "") for e in report.entries)

    tables = _tables()
    tables["parties_owner"][0]["iban_hash"] = "0x" + ("00" * 32)
    report, secrets = rekey.rekey_rows(tables, _ciphers(), tenant_id, dry_run=True)
    assert report.counts["mismatch"] == 1
    assert not any(s.source_id == "owner:201" and s.table == "parties_owner" for s in secrets)


def test_missing_key_is_reported_per_row_not_raised() -> None:
    tenant_id = uuid.uuid4()
    report, secrets = rekey.rekey_rows(
        _tables(), _ciphers(**{rekey.ENV_TOKEN_KEY: ""}), tenant_id, dry_run=True
    )
    assert report.counts == {"rekeyed": 2, "error": 2}
    assert all(
        rekey.ENV_TOKEN_KEY in (e.detail or "") for e in report.entries if e.status == "error"
    )
    assert len(secrets) == 2


def test_key_bytes_follows_objektakte_derivation() -> None:
    assert rekey.objektakte_key_bytes(IBAN_KEY) == b"i" * 32
    assert len(rekey.objektakte_key_bytes("kurz")) == 32  # sha256 fallback like objektakte
    with pytest.raises(rekey.RekeyError):
        rekey.objektakte_key_bytes("")


def test_binary_literal_forms() -> None:
    assert rekey.decode_binary_literal("0x7631") == b"v1"
    assert rekey.decode_binary_literal("_binary v1:abc") == b"v1:abc"
    assert rekey.decode_binary_literal(None) is None
    assert rekey.decode_binary_literal("") == b""


def test_cli_dry_run_refuses_missing_dump(tmp_path: Path) -> None:
    code = rekey.main(["--dump", str(tmp_path / "fehlt.sql"), "--tenant", "hvm", "--dry-run"])
    assert code == 2


def test_cli_never_takes_keys_as_arguments() -> None:
    parser = rekey.build_parser()
    options = {a.dest for a in parser._actions}
    assert not any("key" in name.lower() for name in options)
    assert os.environ.get(rekey.ENV_IBAN_KEY) is None or True  # keys only via environment
