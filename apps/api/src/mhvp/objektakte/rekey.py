"""Re-encryption of objektakte secrets to the CRM master key (M35 technical preparation, open
question M35-03, docs/plans/M35-objektakte-uebernahme.md sections 1.3, 3.1 and 5).

objektakte encrypts with one AES-256-GCM key per purpose (``FIELD_KEYS``: ``iban``, ``token``,
``iban_hmac`` for the IBAN hash; ``src/objektakte/crypto.py`` there), ciphertext
``"v1:" + base64(nonce || ct)`` with AAD ``"<purpose>:<aad>"``. The CRM encrypts with
``mhvp.core.crypto`` (HKDF per scope from ``MHVP_MASTER_KEY``, scope = tenant id). This
module reads an objektakte SQL export, decrypts the two field families in memory, verifies
each IBAN against objektakte's own HMAC (``iban_hash``) when the HMAC key is given, and
re-encrypts for the target tenant.

What it never does: log, print or write plaintext or a key; store plaintext in a file; run
without the operator naming the tenant; write anything in ``--dry-run`` mode. The protocol
(JSON) holds per row only: table, source id, field, status, sha256 of the source ciphertext,
sha256 of the new ciphertext, the last four IBAN characters, and whether the HMAC matched.
Keys come from the environment (``OBJEKTAKTE_IBAN_KEY``, ``OBJEKTAKTE_IBAN_HMAC_KEY``,
``OBJEKTAKTE_TOKEN_KEY``; base64 of 32 bytes, same rules as objektakte's ``_key_bytes``) and
``MHVP_MASTER_KEY``, never from the command line (process list).

Targets in apply mode:

- IBAN of ``parties_owner``/``parties_tenant`` -> ``ContactBankAccount`` of the contact with
  the same ``source_id`` (created by the Stufe 1 import), ``approval_status = pending``: the
  four eyes release of a payee IBAN (M5-01) stays with a human, this tool never approves
  (rule 0.1.6). A contact that already has an account with the same fingerprint is skipped.
  ``source_id`` here is prefixed per table (``owner:<id>`` / ``tenant:<id>``, Kleinbefund
  27.09.2026), matching the same rekey the Stufe 1 import gives ``Contact.source_id`` (see
  ``mhvp.objektakte.objektakte_import._party_source_id``); the two objektakte tables have
  separate id sequences, so an unprefixed id could name the wrong contact.
- Drive tokens of ``oauth_tokens`` -> only recorded (re-encrypted ciphertext is verified and
  discarded) unless ``--tokens-target dms_connection`` is given, which writes the refresh
  token into the tenant's Google Drive ``DmsConnection.secret`` when that connection exists
  and has no refresh token yet. The operator decides whether the CRM reuses the objektakte
  OAuth grant or obtains its own (M35-03).

The decision on timing, four eyes and key deletion (M35-03) stays with the operator and the
data protection officer; this tool is the technical means for the run they approve.

CLI: ``python -m mhvp.objektakte.rekey --dump export.sql --tenant <slug|uuid> --dry-run``.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import sys
import uuid
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core import crypto
from mhvp.core.clock import local_today
from mhvp.core.sqldump import parse_dump

log = logging.getLogger(__name__)

ENV_IBAN_KEY = "OBJEKTAKTE_IBAN_KEY"
ENV_IBAN_HMAC_KEY = "OBJEKTAKTE_IBAN_HMAC_KEY"
ENV_TOKEN_KEY = "OBJEKTAKTE_TOKEN_KEY"  # noqa: S105 - environment variable name
IBAN_TABLES = ("parties_owner", "parties_tenant")
# Same prefixing as mhvp.objektakte.objektakte_import._party_source_id (Kleinbefund 27.09.2026).
PARTY_SOURCE_PREFIX = {"parties_owner": "owner", "parties_tenant": "tenant"}
TOKEN_TABLE = "oauth_tokens"  # noqa: S105 - table name
_VERSION_RE = re.compile(r"^v(\d+):(.+)$", re.S)


class RekeyError(Exception):
    """Safe to show: never contains a key or plaintext."""


# --- objektakte cipher, replicated (src/objektakte/crypto.py there) ----------------------------


def objektakte_key_bytes(raw: str) -> bytes:
    """Same derivation as objektakte ``_key_bytes``: base64 of 32 bytes, otherwise the raw
    string; anything not 32 bytes long is sha256'd to 32 bytes."""
    if not raw:
        raise RekeyError("Schlüssel fehlt")
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception:
        key = raw.encode("utf-8")
    if len(key) != 32:
        key = hashlib.sha256(key).digest()
    return key


class ObjektakteFieldCipher:
    def __init__(self, purpose: str, key: bytes, version: int = 1) -> None:
        self.purpose = purpose
        self.version = version
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: str, aad: str = "") -> str:
        nonce = os.urandom(12)
        ct = self._aead.encrypt(nonce, plaintext.encode("utf-8"), f"{self.purpose}:{aad}".encode())
        return f"v{self.version}:" + base64.b64encode(nonce + ct).decode("ascii")

    def decrypt(self, token: str, aad: str = "") -> str:
        match = _VERSION_RE.match(token)
        if match is None:
            raise RekeyError("Chiffrat ohne Versionspräfix")
        if int(match.group(1)) != self.version:
            raise RekeyError(f"Schlüsselversion v{match.group(1)} nicht aktiv")
        try:
            blob = base64.b64decode(match.group(2))
            nonce, ct = blob[:12], blob[12:]
            return self._aead.decrypt(nonce, ct, f"{self.purpose}:{aad}".encode()).decode("utf-8")
        except (InvalidTag, ValueError) as exc:
            raise RekeyError("Chiffrat nicht lesbar") from exc


def normalize_iban(raw: str) -> str:
    """objektakte ``normalize_iban``: strip whitespace, upper case, OCR ``O`` -> ``0`` after
    the country code (the HMAC is computed over this form)."""
    compact = re.sub(r"\s+", "", raw).upper()
    return compact[:2] + compact[2:].replace("O", "0")


def iban_hmac_hex(iban: str, key: bytes) -> str:
    return hmac.new(key, normalize_iban(iban).encode("ascii"), hashlib.sha256).hexdigest()


def decode_binary_literal(value: Any) -> bytes | None:
    """A VARBINARY column as the dump parser hands it over: ``0x...`` hex, ``_binary '...'``
    (parser keeps the ``_binary `` prefix), or a plain quoted string."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    text = str(value)
    if text.startswith("_binary "):
        text = text[len("_binary ") :]
    if re.fullmatch(r"0x[0-9A-Fa-f]*", text):
        return bytes.fromhex(text[2:])
    return text.encode("latin-1", errors="replace")


# --- rows --------------------------------------------------------------------------------------


@dataclass
class RekeyEntry:
    table: str
    source_id: str
    field: str
    status: str  # rekeyed | skipped | mismatch | error | written | contact_missing | exists
    source_sha256: str | None = None
    target_sha256: str | None = None
    last4: str | None = None
    hmac_verified: bool | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class RekeyedSecret:
    """Held in memory only for the apply step; never serialised."""

    table: str
    source_id: str
    field: str
    aad: str
    ciphertext: bytes  # CRM format for the target scope
    fingerprint: str
    last4: str
    plaintext: str = dc_field(repr=False, default="")


@dataclass
class RekeyReport:
    tenant_id: str
    dry_run: bool
    started_at: str
    entries: list[RekeyEntry] = dc_field(default_factory=list)
    counts: dict[str, int] = dc_field(default_factory=dict)

    def add(self, entry: RekeyEntry) -> None:
        self.entries.append(entry)
        self.counts[entry.status] = self.counts.get(entry.status, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "dry_run": self.dry_run,
            "started_at": self.started_at,
            "counts": dict(sorted(self.counts.items())),
            "entries": [e.as_dict() for e in self.entries],
        }


@dataclass
class Ciphers:
    iban: ObjektakteFieldCipher | None = None
    iban_hmac_key: bytes | None = None
    token: ObjektakteFieldCipher | None = None

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Ciphers:
        source: dict[str, str] = dict(os.environ) if env is None else env
        iban_raw, hmac_raw, token_raw = (
            source.get(ENV_IBAN_KEY, ""),
            source.get(ENV_IBAN_HMAC_KEY, ""),
            source.get(ENV_TOKEN_KEY, ""),
        )
        return cls(
            iban=ObjektakteFieldCipher("iban", objektakte_key_bytes(iban_raw))
            if iban_raw
            else None,
            iban_hmac_key=objektakte_key_bytes(hmac_raw) if hmac_raw else None,
            token=ObjektakteFieldCipher("token", objektakte_key_bytes(token_raw))
            if token_raw
            else None,
        )


def _sha(data: bytes | str | None) -> str | None:
    if data is None:
        return None
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def rekey_rows(
    tables: dict[str, list[dict[str, Any]]],
    ciphers: Ciphers,
    tenant_id: uuid.UUID,
    *,
    dry_run: bool,
    now: datetime | None = None,
) -> tuple[RekeyReport, list[RekeyedSecret]]:
    """Decrypt every encrypted field of the export with the objektakte keys, verify, re-encrypt
    for ``tenant_id``. Pure: no database, no file. Returns the protocol and the re-encrypted
    secrets (in memory, for ``apply``)."""
    scope = str(tenant_id)
    report = RekeyReport(
        tenant_id=scope, dry_run=dry_run, started_at=(now or datetime.now(UTC)).isoformat()
    )
    secrets: list[RekeyedSecret] = []

    for table in IBAN_TABLES:
        for row in tables.get(table, []):
            source_id = f"{PARTY_SOURCE_PREFIX[table]}:{row.get('id')}"
            blob = decode_binary_literal(row.get("iban_encrypted"))
            if not blob:
                continue  # objektakte kept only last4/hash (store_full_iban off): nothing to rekey
            entry = RekeyEntry(
                table, source_id, "iban_encrypted", "error", source_sha256=_sha(blob)
            )
            if ciphers.iban is None:
                entry.detail = f"{ENV_IBAN_KEY} nicht gesetzt"
                report.add(entry)
                continue
            try:
                plaintext = ciphers.iban.decrypt(blob.decode("ascii"))
            except (RekeyError, UnicodeDecodeError) as exc:
                entry.detail = str(exc) if isinstance(exc, RekeyError) else "Chiffrat nicht lesbar"
                report.add(entry)
                continue
            iban = normalize_iban(plaintext)
            entry.last4 = iban[-4:]
            stored_hash = decode_binary_literal(row.get("iban_hash"))
            if ciphers.iban_hmac_key is not None and stored_hash:
                expected = iban_hmac_hex(iban, ciphers.iban_hmac_key)
                entry.hmac_verified = hmac.compare_digest(expected, stored_hash.hex())
                if not entry.hmac_verified:
                    entry.status = "mismatch"
                    entry.detail = "HMAC stimmt nicht mit iban_hash überein"
                    report.add(entry)
                    continue
            ciphertext = crypto.encrypt(iban, scope=scope)
            entry.target_sha256 = _sha(ciphertext)
            entry.status = "rekeyed"
            report.add(entry)
            secrets.append(
                RekeyedSecret(
                    table,
                    source_id,
                    "iban_encrypted",
                    "",
                    ciphertext,
                    crypto.fingerprint(iban, scope=scope),
                    iban[-4:],
                    plaintext=iban,
                )
            )

    for row in tables.get(TOKEN_TABLE, []):
        source_id = str(row.get("id"))
        for column, aad in (
            ("access_token_encrypted", "access"),
            ("refresh_token_encrypted", "refresh"),
        ):
            blob = decode_binary_literal(row.get(column))
            if not blob:
                continue
            entry = RekeyEntry(TOKEN_TABLE, source_id, column, "error", source_sha256=_sha(blob))
            if ciphers.token is None:
                entry.detail = f"{ENV_TOKEN_KEY} nicht gesetzt"
                report.add(entry)
                continue
            try:
                plaintext = ciphers.token.decrypt(blob.decode("ascii"), aad=aad)
            except (RekeyError, UnicodeDecodeError) as exc:
                entry.detail = str(exc) if isinstance(exc, RekeyError) else "Chiffrat nicht lesbar"
                report.add(entry)
                continue
            ciphertext = crypto.encrypt(plaintext, scope=scope)
            entry.target_sha256 = _sha(ciphertext)
            entry.status = "rekeyed"
            report.add(entry)
            secrets.append(
                RekeyedSecret(
                    TOKEN_TABLE,
                    source_id,
                    column,
                    aad,
                    ciphertext,
                    crypto.fingerprint(plaintext, scope=scope),
                    "",
                    plaintext=plaintext,
                )
            )
    return report, secrets


# --- apply -------------------------------------------------------------------------------------


async def apply_secrets(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    secrets: list[RekeyedSecret],
    report: RekeyReport,
    *,
    tokens_target: str = "none",
    today: date | None = None,
) -> None:
    """Write the re-encrypted secrets (see module docstring for the targets)."""
    from mhvp.contacts.models import BankAccountApproval, Contact, ContactBankAccount
    from mhvp.documents.models import DmsConnection, StorageKind

    today = today or local_today()
    contacts = {
        row.source_id: row.id
        for row in (
            await session.scalars(
                select(Contact).where(
                    Contact.tenant_id == tenant_id, Contact.source_system == "objektakte"
                )
            )
        ).all()
        if row.source_id
    }
    for secret in secrets:
        if secret.table in IBAN_TABLES:
            contact_id = contacts.get(secret.source_id)
            if contact_id is None:
                report.add(RekeyEntry(secret.table, secret.source_id, "apply", "contact_missing"))
                continue
            exists = await session.scalar(
                select(ContactBankAccount.id).where(
                    ContactBankAccount.tenant_id == tenant_id,
                    ContactBankAccount.contact_id == contact_id,
                    ContactBankAccount.iban_fingerprint == secret.fingerprint,
                )
            )
            if exists is not None:
                report.add(RekeyEntry(secret.table, secret.source_id, "apply", "exists"))
                continue
            session.add(
                ContactBankAccount(
                    tenant_id=tenant_id,
                    contact_id=contact_id,
                    label="objektakte-Übernahme",
                    iban=secret.plaintext,  # EncryptedText encrypts for the session's scope
                    iban_suffix=secret.last4,
                    iban_fingerprint=secret.fingerprint,
                    valid_from=today,
                    approval_status=BankAccountApproval.PENDING,
                )
            )
            report.add(
                RekeyEntry(secret.table, secret.source_id, "apply", "written", last4=secret.last4)
            )
            continue
        # Drive tokens
        if tokens_target != "dms_connection" or secret.field != "refresh_token_encrypted":
            report.add(
                RekeyEntry(
                    secret.table,
                    secret.source_id,
                    secret.field,
                    "skipped",
                    detail="tokens_target=none",
                )
            )
            continue
        connection = await session.scalar(
            select(DmsConnection).where(
                DmsConnection.tenant_id == tenant_id,
                DmsConnection.kind == StorageKind.GOOGLE_DRIVE,
            )
        )
        if connection is None:
            report.add(
                RekeyEntry(
                    secret.table,
                    secret.source_id,
                    secret.field,
                    "skipped",
                    detail="keine Drive-Anbindung",
                )
            )
            continue
        current = json.loads(connection.secret or "{}")
        if current.get("refresh_token"):
            report.add(RekeyEntry(secret.table, secret.source_id, secret.field, "exists"))
            continue
        current["refresh_token"] = secret.plaintext
        connection.secret = json.dumps(current)
        report.add(RekeyEntry(secret.table, secret.source_id, secret.field, "written"))
    await session.flush()


# --- CLI ---------------------------------------------------------------------------------------


def write_protocol(report: RekeyReport, path: Path) -> None:
    path.write_text(json.dumps(report.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


async def _resolve_tenant(settings: Any, key: str) -> uuid.UUID:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import platform_transaction
    from mhvp.platform.models import Tenant

    engine = create_app_engine(settings)
    try:
        try:
            tenant_uuid: uuid.UUID | None = uuid.UUID(key)
        except ValueError:
            tenant_uuid = None
        query = select(Tenant.id)
        query = (
            query.where(Tenant.id == tenant_uuid)
            if tenant_uuid
            else query.where(Tenant.slug == key)
        )
        async with platform_transaction(create_session_factory(engine)) as session:
            found = await session.scalar(query)
    finally:
        await engine.dispose()
    if found is None:
        raise RekeyError(f"Mandant {key!r} nicht gefunden")
    return found


async def run_cli(args: argparse.Namespace) -> int:
    from mhvp.core.config import get_settings
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    settings = get_settings()
    if settings.master_key is None:
        sys.stderr.write("MHVP_MASTER_KEY fehlt\n")
        return 2
    crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    dump_path = Path(args.dump)
    try:
        tenant_id = await _resolve_tenant(settings, args.tenant)
        ciphers = Ciphers.from_env()
    except RekeyError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    tables = parse_dump(await asyncio.to_thread(dump_path.read_text, "utf-8", "replace"))
    report, secrets = rekey_rows(tables, ciphers, tenant_id, dry_run=args.dry_run)
    if not args.dry_run:
        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
                await apply_secrets(
                    session, tenant_id, secrets, report, tokens_target=args.tokens_target
                )
        finally:
            await engine.dispose()
    secrets.clear()
    if args.protocol:
        write_protocol(report, Path(args.protocol))
    print(  # noqa: T201
        json.dumps({"tenant_id": str(tenant_id), "dry_run": args.dry_run, "counts": report.counts})
    )
    return 0 if not any(k in report.counts for k in ("error", "mismatch")) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mhvp.objektakte.rekey",
        description="objektakte-Chiffrate (IBAN, Drive-Token) auf den CRM-Master-Key umschlüsseln.",
    )
    parser.add_argument("--dump", required=True, help="objektakte SQL-Export (mysqldump)")
    parser.add_argument("--tenant", required=True, help="Ziel-Mandant (Slug oder UUID)")
    parser.add_argument("--dry-run", action="store_true", help="nur prüfen, nichts schreiben")
    parser.add_argument("--protocol", help="Pfad der JSON-Protokolldatei (ohne Klartext)")
    parser.add_argument(
        "--tokens-target",
        choices=("none", "dms_connection"),
        default="none",
        help="Ziel der Drive-Refresh-Tokens (Standard: nur prüfen)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING)
    args = build_parser().parse_args(argv)
    if not Path(args.dump).is_file():
        sys.stderr.write(f"Export {args.dump} nicht gefunden\n")
        return 2
    return asyncio.run(run_cli(args))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
