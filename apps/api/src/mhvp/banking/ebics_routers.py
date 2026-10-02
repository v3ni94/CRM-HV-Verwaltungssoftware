"""EBICS connector scaffold endpoints (/api/v1/banking/ebics, M11-01, AE23, rule M11-11).

Flow (docs/runbooks/ebics-setup.md): tenant switch on, subscriber from the bank contract,
keys (authentication X002 and encryption E002 always generated and stored encrypted, the
signature key A005/A006 only in the variant ``server``, otherwise its public key is uploaded or
INI is confirmed as done elsewhere), INI and HIA, letter data, confirmation of the bank's
activation, HPB, verification of the bank key hash values against the bank letter by a second
person, then the statement download C53 with import through ``services.import_file``.

Every bank call goes through ``mhvp.banking.ebics_transport``; without an installed
implementation the call answers ``MHVP-BANK-0050`` (AE23-01). Read only: no payment is
submitted here, the payment channel ``ebics`` stays locked (``EbicsSubmitter``, G2).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking import ebics_keys as keys_mod
from mhvp.banking import services as svc
from mhvp.banking.ebics import PREREQUISITES
from mhvp.banking.ebics_connector import EbicsConnector, parse_c53
from mhvp.banking.ebics_models import (
    EbicsKey,
    EbicsOrder,
    EbicsSignatureKeyMode,
    EbicsSubscriber,
    EbicsSubscriberStatus,
    EbicsTenantSetting,
)
from mhvp.banking.ebics_transport import (
    C53,
    EbicsClientKeys,
    EbicsSubscriberRef,
    EbicsTransport,
    EbicsTransportError,
    get_transport,
    is_available,
)
from mhvp.core import crypto
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/banking/ebics", tags=["Bank"])
log = logging.getLogger(__name__)

READ = require_permission("accounting:read")
APPROVE = require_permission("banking:approve")
SETTINGS = require_permission("tenant_settings:update")

S = EbicsSubscriberStatus
OPEN_QUESTIONS = ("V2", "S16-03-02", "AE23-01", "AE23-02", "AE23-03", "AE23-04")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EbicsStatusOut(BaseModel):
    enabled: bool
    signature_key_mode: str
    transport_available: bool
    transport: str
    min_key_bits: int
    default_key_bits: int
    key_bits_strict_from: date
    order_types: list[str]
    c53_btf: str
    payment_submission: str
    prerequisites: list[str]
    sources: list[str]
    open_questions: list[str]


class EbicsSettingsIn(_In):
    enabled: bool | None = None
    signature_key_mode: Literal["external", "server"] | None = None


class EbicsSubscriberIn(_In):
    label: str = Field(min_length=1, max_length=200)
    host_id: str = Field(pattern=r"^\S{1,64}$")
    partner_id: str = Field(pattern=r"^\S{1,64}$")
    ebics_user_id: str = Field(pattern=r"^\S{1,64}$")
    url: str = Field(max_length=500, pattern=r"^https://\S+$")
    ebics_version: Literal["2.5", "3.0"]
    signature_version: Literal["A005", "A006"]
    key_bits: Literal[2048, 3072, 4096] | None = None


class EbicsKeysIn(_In):
    reason: str | None = Field(default=None, min_length=3, max_length=200)


class EbicsSignatureKeyIn(_In):
    public_key_pem: str = Field(min_length=100, max_length=20000)
    reason: str | None = Field(default=None, min_length=3, max_length=200)


class EbicsNoteIn(_In):
    note: str = Field(min_length=3, max_length=2000)


class EbicsActivationIn(_In):
    activated_on: date
    note: str | None = Field(default=None, max_length=2000)


class EbicsVerifyIn(_In):
    authentication_hash: str = Field(min_length=8, max_length=300)
    encryption_hash: str = Field(min_length=8, max_length=300)


class EbicsSuspendIn(_In):
    reason: str = Field(min_length=3, max_length=2000)


class EbicsStatementsIn(_In):
    date_from: date | None = None
    date_to: date | None = None


class EbicsKeyOut(BaseModel):
    id: uuid.UUID
    owner: str
    usage: str
    version: str
    key_bits: int
    source: str
    public_key_sha256: str
    letter_hash: str | None
    has_private_key: bool
    runs_out: date | None
    created_at: datetime
    retired_at: datetime | None
    retire_reason: str | None


class EbicsOrderOut(BaseModel):
    id: uuid.UUID
    order_type: str
    btf: str | None
    status: str
    transport: str | None
    transport_ref: str | None
    date_from: date | None
    date_to: date | None
    file_sha256: str | None
    result: dict[str, Any]
    error_code: str | None
    error_detail: str | None
    created_at: datetime
    created_by: uuid.UUID | None


class EbicsSubscriberOut(BaseModel):
    id: uuid.UUID
    label: str
    host_id: str
    partner_id: str
    ebics_user_id: str
    url: str
    ebics_version: str
    signature_version: str
    key_bits: int
    signature_key_mode: str
    status: str
    next_step: str
    ini_sent_at: datetime | None
    ini_external: bool
    ini_note: str | None
    hia_sent_at: datetime | None
    activated_on: date | None
    activation_note: str | None
    bank_keys_fetched_at: datetime | None
    bank_keys_fetched_by: uuid.UUID | None
    bank_keys_verified_at: datetime | None
    bank_keys_verified_by: uuid.UUID | None
    suspended_at: datetime | None
    suspend_reason: str | None
    last_download_at: datetime | None
    created_at: datetime
    keys: list[EbicsKeyOut]


class EbicsSubscriberDetailOut(EbicsSubscriberOut):
    retired_keys: list[EbicsKeyOut]
    orders: list[EbicsOrderOut]


class EbicsLetterOut(BaseModel):
    order_type: str
    usage: str
    version: str
    key_bits: int
    exponent_hex: str
    modulus_hex: str
    public_key_sha256: str
    letter_hash: str | None
    letter_hash_status: str


class EbicsLettersOut(BaseModel):
    host_id: str
    partner_id: str
    ebics_user_id: str
    ebics_version: str
    generated_at: datetime
    letters: list[EbicsLetterOut]
    notice: str


def _now() -> datetime:
    return datetime.now(UTC)


async def _setting(session: AsyncSession) -> EbicsTenantSetting | None:
    row: EbicsTenantSetting | None = await session.scalar(select(EbicsTenantSetting))
    return row


async def _require_enabled(session: AsyncSession) -> EbicsTenantSetting:
    setting = await _setting(session)
    if setting is None or not setting.enabled:
        raise ProblemError(ErrorCodes.EBICS_DISABLED)
    return setting


async def _subscriber(
    session: AsyncSession, subscriber_id: uuid.UUID, *, lock: bool = False
) -> EbicsSubscriber:
    query = select(EbicsSubscriber).where(EbicsSubscriber.id == subscriber_id)
    if lock:
        query = query.with_for_update()
    sub = await session.scalar(query)
    if sub is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return sub


async def _keys(
    session: AsyncSession, subscriber_id: uuid.UUID, *, active: bool = True
) -> list[EbicsKey]:
    query = select(EbicsKey).where(EbicsKey.subscriber_id == subscriber_id)
    query = query.where(
        EbicsKey.retired_at.is_(None) if active else EbicsKey.retired_at.is_not(None)
    )
    rows = await session.scalars(query.order_by(EbicsKey.created_at))
    return list(rows.all())


def _active(keys: list[EbicsKey], owner: str, usage: str) -> EbicsKey | None:
    return next((k for k in keys if k.owner == owner and k.usage == usage), None)


def _state(sub: EbicsSubscriber, *allowed: EbicsSubscriberStatus) -> None:
    if sub.status not in {a.value for a in allowed}:
        raise ProblemError(ErrorCodes.EBICS_STATE, detail=f"Aktueller Zustand: {sub.status}.")


def _next_step(sub: EbicsSubscriber, keys: list[EbicsKey]) -> str:
    status = sub.status
    if status == S.CREATED:
        return "generate_keys"
    if status == S.KEYS_READY:
        if sub.ini_sent_at is None:
            if _active(keys, "subscriber", "signature") is None:
                return "upload_signature_key_or_confirm_ini"
            return "send_ini"
        return "send_hia"
    if status == S.INITIALISED:
        return "confirm_activation"
    if status == S.ACTIVATED:
        return "fetch_bank_keys"
    if status == S.BANK_KEYS_RECEIVED:
        return "verify_bank_keys"
    if status == S.READY:
        return "download_statements"
    return "none"


def _key_out(key: EbicsKey) -> EbicsKeyOut:
    return EbicsKeyOut(
        id=key.id,
        owner=key.owner,
        usage=key.usage,
        version=key.version,
        key_bits=key.key_bits,
        source=key.source,
        public_key_sha256=key.public_key_sha256,
        letter_hash=key.letter_hash,
        has_private_key=key.private_key is not None,
        runs_out=keys_mod.runs_out(key.key_bits),
        created_at=key.created_at,
        retired_at=key.retired_at,
        retire_reason=key.retire_reason,
    )


def _order_out(order: EbicsOrder) -> EbicsOrderOut:
    return EbicsOrderOut(
        id=order.id,
        order_type=order.order_type,
        btf=order.btf,
        status=order.status,
        transport=order.transport,
        transport_ref=order.transport_ref,
        date_from=order.date_from,
        date_to=order.date_to,
        file_sha256=order.file_sha256,
        result=order.result or {},
        error_code=order.error_code,
        error_detail=order.error_detail,
        created_at=order.created_at,
        created_by=order.created_by,
    )


def _sub_fields(sub: EbicsSubscriber, keys: list[EbicsKey]) -> dict[str, Any]:
    return {
        "id": sub.id,
        "label": sub.label,
        "host_id": sub.host_id,
        "partner_id": sub.partner_id,
        "ebics_user_id": sub.ebics_user_id,
        "url": sub.url,
        "ebics_version": sub.ebics_version,
        "signature_version": sub.signature_version,
        "key_bits": sub.key_bits,
        "signature_key_mode": sub.signature_key_mode,
        "status": sub.status,
        "next_step": _next_step(sub, keys),
        "ini_sent_at": sub.ini_sent_at,
        "ini_external": sub.ini_external,
        "ini_note": sub.ini_note,
        "hia_sent_at": sub.hia_sent_at,
        "activated_on": sub.activated_on,
        "activation_note": sub.activation_note,
        "bank_keys_fetched_at": sub.bank_keys_fetched_at,
        "bank_keys_fetched_by": sub.bank_keys_fetched_by,
        "bank_keys_verified_at": sub.bank_keys_verified_at,
        "bank_keys_verified_by": sub.bank_keys_verified_by,
        "suspended_at": sub.suspended_at,
        "suspend_reason": sub.suspend_reason,
        "last_download_at": sub.last_download_at,
        "created_at": sub.created_at,
        "keys": [_key_out(k) for k in keys],
    }


async def _detail(session: AsyncSession, sub: EbicsSubscriber) -> EbicsSubscriberDetailOut:
    await session.flush()
    await session.refresh(sub)
    active = await _keys(session, sub.id)
    retired = await _keys(session, sub.id, active=False)
    orders = await session.scalars(
        select(EbicsOrder)
        .where(EbicsOrder.subscriber_id == sub.id)
        .order_by(EbicsOrder.created_at.desc())
        .limit(20)
    )
    return EbicsSubscriberDetailOut(
        **_sub_fields(sub, active),
        retired_keys=[_key_out(k) for k in retired],
        orders=[_order_out(o) for o in orders.all()],
    )


def _ref(sub: EbicsSubscriber) -> EbicsSubscriberRef:
    return EbicsSubscriberRef(
        host_id=sub.host_id,
        partner_id=sub.partner_id,
        user_id=sub.ebics_user_id,
        url=sub.url,
        ebics_version=sub.ebics_version,
        signature_version=sub.signature_version,
    )


def _client_keys(keys: list[EbicsKey]) -> EbicsClientKeys:
    auth = _active(keys, "subscriber", "authentication")
    enc = _active(keys, "subscriber", "encryption")
    if auth is None or enc is None or auth.private_key is None or enc.private_key is None:
        raise ProblemError(ErrorCodes.EBICS_STATE, detail="Teilnehmerschlüssel fehlen.")
    bank_auth = _active(keys, "bank", "authentication")
    bank_enc = _active(keys, "bank", "encryption")
    return EbicsClientKeys(
        authentication_private_pem=auth.private_key,
        encryption_private_pem=enc.private_key,
        bank_authentication_public_pem=bank_auth.public_key_pem if bank_auth else None,
        bank_encryption_public_pem=bank_enc.public_key_pem if bank_enc else None,
    )


async def _call[T](fn: Callable[..., T], *args: Any) -> T:
    """Runs a (blocking) transport call outside the event loop; bank errors become
    ``MHVP-BANK-0056`` with the bank's return code kept unchanged."""
    try:
        return await asyncio.to_thread(fn, *args)
    except EbicsTransportError as exc:
        suffix = f" (Rückmeldung {exc.code})" if exc.code else ""
        raise ProblemError(ErrorCodes.EBICS_BANK_ERROR, detail=f"{exc}{suffix}"[:500]) from None


def _order(
    sub: EbicsSubscriber,
    principal: TenantPrincipal,
    transport: EbicsTransport,
    order_type: str,
    *,
    status: str = "done",
    error: ProblemError | None = None,
    **fields: Any,
) -> EbicsOrder:
    return EbicsOrder(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        subscriber_id=sub.id,
        order_type=order_type,
        transport=transport.name,
        status="failed" if error is not None else status,
        error_code=error.error.code if error is not None else None,
        error_detail=(error.detail or error.error.title)[:2000] if error is not None else None,
        **fields,
    )


async def _event(
    session: AsyncSession,
    principal: TenantPrincipal,
    sub: EbicsSubscriber,
    kind: str,
    payload: dict[str, Any] | None = None,
) -> None:
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=f"ebics_subscriber.{kind}",
        entity_type="ebics_subscriber",
        entity_id=sub.id,
        actor_user_id=principal.user_id,
        payload=payload or {},
    )


def _new_key(
    principal: TenantPrincipal,
    sub: EbicsSubscriber,
    *,
    owner: str,
    usage: str,
    version: str,
    public_pem: str,
    source: str,
    private_pem: str | None,
    letter_hash: str | None,
) -> EbicsKey:
    return EbicsKey(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        subscriber_id=sub.id,
        owner=owner,
        usage=usage,
        version=version,
        key_bits=keys_mod.public_key_bits(public_pem),
        source=source,
        public_key_pem=public_pem,
        public_key_sha256=keys_mod.public_key_sha256(public_pem),
        private_key=private_pem,
        letter_hash=letter_hash,
    )


def _retire(key: EbicsKey, principal: TenantPrincipal, reason: str) -> None:
    """Retires a key row; the private key is wiped (S16-03-02), public data stays."""
    key.retired_at = _now()
    key.retired_by = principal.user_id
    key.retire_reason = reason[:200]
    key.private_key = None


def _reset_initialisation(sub: EbicsSubscriber) -> None:
    sub.ini_sent_at = None
    sub.ini_sent_by = None
    sub.ini_external = False
    sub.ini_note = None
    sub.hia_sent_at = None
    sub.hia_sent_by = None
    sub.activated_on = None
    sub.activation_confirmed_by = None
    sub.activation_note = None
    sub.bank_keys_verified_at = None
    sub.bank_keys_verified_by = None


def _after_init_step(sub: EbicsSubscriber) -> None:
    if sub.ini_sent_at is not None and sub.hia_sent_at is not None:
        sub.status = S.INITIALISED.value


async def _locked_subscriber(
    session: AsyncSession, subscriber_id: uuid.UUID
) -> tuple[EbicsTenantSetting, EbicsSubscriber]:
    setting = await _require_enabled(session)
    return setting, await _subscriber(session, subscriber_id, lock=True)


@router.get("/status", summary="EBICS-Einrichtungsstand (Schalter, Übertragung, Quellen)")
async def ebics_status(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> EbicsStatusOut:
    async with tenant_tx(request, principal) as session:
        setting = await _setting(session)
    transport = get_transport()
    return EbicsStatusOut(
        enabled=bool(setting and setting.enabled),
        signature_key_mode=setting.signature_key_mode if setting else "external",
        transport_available=is_available(),
        transport=transport.name,
        min_key_bits=keys_mod.min_key_bits(local_today()),
        default_key_bits=keys_mod.DEFAULT_KEY_BITS,
        key_bits_strict_from=keys_mod.STRICT_FROM,
        order_types=["INI", "HIA", "HPB", "C53"],
        c53_btf=C53.btf,
        payment_submission="locked_g2",
        prerequisites=list(PREREQUISITES),
        sources=list(keys_mod.SOURCES),
        open_questions=list(OPEN_QUESTIONS),
    )


@router.put("/settings", summary="EBICS-Mandantenschalter setzen")
async def ebics_settings(
    body: EbicsSettingsIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> EbicsStatusOut:
    """Switch (default off) and the variant for the signature key (default ``external``).
    The variant applies to subscribers created afterwards; existing ones keep theirs."""
    async with tenant_tx(request, principal) as session:
        setting = await _setting(session)
        if setting is None:
            setting = EbicsTenantSetting(tenant_id=principal.tenant_id)
            session.add(setting)
        before = {"enabled": setting.enabled, "signature_key_mode": setting.signature_key_mode}
        if body.enabled is not None:
            setting.enabled = body.enabled
        if body.signature_key_mode is not None:
            setting.signature_key_mode = body.signature_key_mode
        setting.enabled = bool(setting.enabled)
        setting.signature_key_mode = setting.signature_key_mode or "external"
        setting.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ebics_setting.updated",
            entity_type="ebics_tenant_setting",
            entity_id=setting.id,
            actor_user_id=principal.user_id,
            changes={
                "before": before,
                "after": {
                    "enabled": setting.enabled,
                    "signature_key_mode": setting.signature_key_mode,
                },
            },
        )
    return await ebics_status(request, principal)


@router.get("/subscribers", summary="EBICS-Teilnehmer", dependencies=[Depends(strict_query)])
async def list_subscribers(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[EbicsSubscriberOut]:
    async with tenant_tx(request, principal) as session:
        subs = (
            await session.scalars(select(EbicsSubscriber).order_by(EbicsSubscriber.created_at))
        ).all()
        out = []
        for sub in subs:
            out.append(EbicsSubscriberOut(**_sub_fields(sub, await _keys(session, sub.id))))
        return out


@router.post("/subscribers", status_code=201, summary="EBICS-Teilnehmer anlegen")
async def create_subscriber(
    body: EbicsSubscriberIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> EbicsSubscriberDetailOut:
    bits = body.key_bits or keys_mod.DEFAULT_KEY_BITS
    try:
        keys_mod.check_key_bits(bits, local_today())
    except ValueError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from None
    async with tenant_tx(request, principal) as session:
        setting = await _require_enabled(session)
        duplicate = await session.scalar(
            select(EbicsSubscriber.id).where(
                EbicsSubscriber.host_id == body.host_id,
                EbicsSubscriber.partner_id == body.partner_id,
                EbicsSubscriber.ebics_user_id == body.ebics_user_id,
            )
        )
        if duplicate is not None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Teilnehmer mit diesen Kennungen besteht bereits."
            )
        sub = EbicsSubscriber(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            label=body.label,
            host_id=body.host_id,
            partner_id=body.partner_id,
            ebics_user_id=body.ebics_user_id,
            url=body.url,
            ebics_version=body.ebics_version,
            signature_version=body.signature_version,
            key_bits=bits,
            signature_key_mode=setting.signature_key_mode,
            status=S.CREATED.value,
        )
        session.add(sub)
        await session.flush()
        await _event(session, principal, sub, "created", {"host_id": sub.host_id})
        return await _detail(session, sub)


@router.get("/subscribers/{subscriber_id}", summary="EBICS-Teilnehmer mit Schlüsseln")
async def get_subscriber(
    subscriber_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> EbicsSubscriberDetailOut:
    async with tenant_tx(request, principal) as session:
        return await _detail(session, await _subscriber(session, subscriber_id))


@router.post(
    "/subscribers/{subscriber_id}/keys",
    summary="Teilnehmerschlüssel erzeugen oder wechseln",
)
async def generate_keys(
    subscriber_id: uuid.UUID,
    body: EbicsKeysIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> EbicsSubscriberDetailOut:
    """Generates authentication (X002) and encryption (E002) keys, and the signature key in
    the variant ``server``. With active keys this is a rotation: ``reason`` is required, the
    old rows are retired (private key wiped) and initialisation starts again (INI, HIA,
    activation, HPB and bank key verification)."""
    async with tenant_tx(request, principal) as session:
        _, sub = await _locked_subscriber(session, subscriber_id)
        if sub.status == S.SUSPENDED:
            _state(sub)
        keys = await _keys(session, sub.id)
        server_sig = sub.signature_key_mode == EbicsSignatureKeyMode.SERVER
        usages = ["authentication", "encryption"] + (["signature"] if server_sig else [])
        old = [k for k in keys if k.owner == "subscriber" and k.usage in usages]
        rotation = bool(old)
        if rotation and body.reason is None:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Für den Schlüsselwechsel ist ein Grund nötig."
            )
        bits = sub.key_bits
        try:
            keys_mod.check_key_bits(bits, local_today())
        except ValueError as exc:
            raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from None
        pairs = await asyncio.gather(
            *(asyncio.to_thread(keys_mod.generate_key_pair, bits) for _ in usages)
        )
        for key in old:
            _retire(key, principal, body.reason or "Schlüsselwechsel")
        await session.flush()
        transport = get_transport()
        versions = {
            "authentication": keys_mod.AUTHENTICATION_VERSION,
            "encryption": keys_mod.ENCRYPTION_VERSION,
            "signature": sub.signature_version,
        }
        for usage, pair in zip(usages, pairs, strict=True):
            session.add(
                _new_key(
                    principal,
                    sub,
                    owner="subscriber",
                    usage=usage,
                    version=versions[usage],
                    public_pem=pair.public_pem,
                    source="generated",
                    private_pem=pair.private_pem,
                    letter_hash=transport.letter_hash(
                        pair.public_pem, versions[usage], sub.ebics_version
                    ),
                )
            )
        if rotation:
            _reset_initialisation(sub)
        sub.status = S.KEYS_READY.value
        sub.updated_by = principal.user_id
        await session.flush()
        await _event(
            session,
            principal,
            sub,
            "keys_rotated" if rotation else "keys_generated",
            {"usages": usages, "key_bits": bits, "reason": body.reason},
        )
        return await _detail(session, sub)


@router.post(
    "/subscribers/{subscriber_id}/signature-key",
    summary="Öffentlichen Signaturschlüssel hinterlegen (Variante extern)",
)
async def upload_signature_key(
    subscriber_id: uuid.UUID,
    body: EbicsSignatureKeyIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> EbicsSubscriberDetailOut:
    """Only the public key of the signing person's key pair; the private key stays on the
    person's medium (DK security recommendations 3.1.2). A replacement needs ``reason`` and
    resets INI."""
    try:
        public_pem = keys_mod.normalised_public_pem(body.public_key_pem)
        keys_mod.check_key_bits(keys_mod.public_key_bits(public_pem), local_today())
    except ValueError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from None
    async with tenant_tx(request, principal) as session:
        _, sub = await _locked_subscriber(session, subscriber_id)
        if sub.signature_key_mode != EbicsSignatureKeyMode.EXTERNAL:
            raise ProblemError(
                ErrorCodes.EBICS_STATE,
                detail="Der Signaturschlüssel wird in dieser Variante von der Plattform erzeugt.",
            )
        _state(sub, S.CREATED, S.KEYS_READY)
        keys = await _keys(session, sub.id)
        old = _active(keys, "subscriber", "signature")
        if old is not None:
            if body.reason is None:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Für den Schlüsselwechsel ist ein Grund nötig."
                )
            _retire(old, principal, body.reason)
            await session.flush()
        transport = get_transport()
        session.add(
            _new_key(
                principal,
                sub,
                owner="subscriber",
                usage="signature",
                version=sub.signature_version,
                public_pem=public_pem,
                source="uploaded",
                private_pem=None,
                letter_hash=transport.letter_hash(
                    public_pem, sub.signature_version, sub.ebics_version
                ),
            )
        )
        sub.ini_sent_at = None
        sub.ini_sent_by = None
        sub.ini_external = False
        sub.ini_note = None
        await _event(session, principal, sub, "signature_key_uploaded", {"replaced": bool(old)})
        return await _detail(session, sub)


@router.post("/subscribers/{subscriber_id}/ini", summary="INI senden (Signaturschlüssel)")
async def send_ini(
    subscriber_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> EbicsSubscriberDetailOut:
    failure: ProblemError | None = None
    async with tenant_tx(request, principal) as session:
        _, sub = await _locked_subscriber(session, subscriber_id)
        _state(sub, S.KEYS_READY)
        if sub.ini_sent_at is not None:
            raise ProblemError(ErrorCodes.EBICS_STATE, detail="INI ist bereits erledigt.")
        sig = _active(await _keys(session, sub.id), "subscriber", "signature")
        if sig is None:
            raise ProblemError(ErrorCodes.EBICS_STATE, detail="Signaturschlüssel fehlt.")
        transport = get_transport()
        try:
            result = await _call(transport.send_ini, _ref(sub), sig.public_key_pem)
        except ProblemError as exc:
            failure = exc
            session.add(_order(sub, principal, transport, "INI", error=exc))
        else:
            session.add(
                _order(sub, principal, transport, "INI", transport_ref=result.transport_ref)
            )
            sub.ini_sent_at = _now()
            sub.ini_sent_by = principal.user_id
            _after_init_step(sub)
            await _event(session, principal, sub, "ini_sent")
        detail = await _detail(session, sub)
    if failure is not None:
        raise failure
    return detail


@router.post(
    "/subscribers/{subscriber_id}/ini/external",
    summary="INI als außerhalb der Plattform erledigt bestätigen (Variante extern)",
)
async def confirm_ini_external(
    subscriber_id: uuid.UUID,
    body: EbicsNoteIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> EbicsSubscriberDetailOut:
    async with tenant_tx(request, principal) as session:
        _, sub = await _locked_subscriber(session, subscriber_id)
        if sub.signature_key_mode != EbicsSignatureKeyMode.EXTERNAL:
            raise ProblemError(ErrorCodes.EBICS_STATE, detail="Nur in der Variante extern.")
        _state(sub, S.KEYS_READY)
        if sub.ini_sent_at is not None:
            raise ProblemError(ErrorCodes.EBICS_STATE, detail="INI ist bereits erledigt.")
        sub.ini_sent_at = _now()
        sub.ini_sent_by = principal.user_id
        sub.ini_external = True
        sub.ini_note = body.note
        _after_init_step(sub)
        await _event(session, principal, sub, "ini_confirmed_external")
        return await _detail(session, sub)


@router.post(
    "/subscribers/{subscriber_id}/hia",
    summary="HIA senden (Authentifikations- und Verschlüsselungsschlüssel)",
)
async def send_hia(
    subscriber_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> EbicsSubscriberDetailOut:
    failure: ProblemError | None = None
    async with tenant_tx(request, principal) as session:
        _, sub = await _locked_subscriber(session, subscriber_id)
        _state(sub, S.KEYS_READY)
        if sub.hia_sent_at is not None:
            raise ProblemError(ErrorCodes.EBICS_STATE, detail="HIA ist bereits erledigt.")
        keys = await _keys(session, sub.id)
        auth = _active(keys, "subscriber", "authentication")
        enc = _active(keys, "subscriber", "encryption")
        if auth is None or enc is None:
            raise ProblemError(ErrorCodes.EBICS_STATE, detail="Teilnehmerschlüssel fehlen.")
        transport = get_transport()
        try:
            result = await _call(
                transport.send_hia, _ref(sub), auth.public_key_pem, enc.public_key_pem
            )
        except ProblemError as exc:
            failure = exc
            session.add(_order(sub, principal, transport, "HIA", error=exc))
        else:
            session.add(
                _order(sub, principal, transport, "HIA", transport_ref=result.transport_ref)
            )
            sub.hia_sent_at = _now()
            sub.hia_sent_by = principal.user_id
            _after_init_step(sub)
            await _event(session, principal, sub, "hia_sent")
        detail = await _detail(session, sub)
    if failure is not None:
        raise failure
    return detail


@router.get("/subscribers/{subscriber_id}/letters", summary="Daten für INI- und HIA-Brief")
async def letters(
    subscriber_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> EbicsLettersOut:
    """Public key data of the active subscriber keys. The letter hash is the value the
    transport computed; without a transport it is missing (``source_required``, AE23-02) and
    no letter may be sent to the bank. The layout of the letter is not reproduced here."""
    async with tenant_tx(request, principal) as session:
        sub = await _subscriber(session, subscriber_id)
        keys = await _keys(session, sub.id)
    out = []
    for order_type, usage in (
        ("INI", "signature"),
        ("HIA", "authentication"),
        ("HIA", "encryption"),
    ):
        key = _active(keys, "subscriber", usage)
        if key is None:
            continue
        exponent, modulus = keys_mod.exponent_modulus_hex(key.public_key_pem)
        out.append(
            EbicsLetterOut(
                order_type=order_type,
                usage=usage,
                version=key.version,
                key_bits=key.key_bits,
                exponent_hex=exponent,
                modulus_hex=modulus,
                public_key_sha256=key.public_key_sha256,
                letter_hash=key.letter_hash,
                letter_hash_status="transport" if key.letter_hash else "source_required",
            )
        )
    if not out:
        raise ProblemError(ErrorCodes.EBICS_STATE, detail="Noch keine Teilnehmerschlüssel.")
    return EbicsLettersOut(
        host_id=sub.host_id,
        partner_id=sub.partner_id,
        ebics_user_id=sub.ebics_user_id,
        ebics_version=sub.ebics_version,
        generated_at=_now(),
        letters=out,
        notice=(
            "Hash-Werte vor der Unterschrift mit dem Ausdruck vergleichen. Ohne Hash-Wert der "
            "Übertragung (Quellenbedarf AE23-02) keinen Brief an die Bank senden."
        ),
    )


def _hex_rows(value: str, width: int = 64) -> list[str]:
    return [value[i : i + width] for i in range(0, len(value), width)] or [""]


@router.get(
    "/subscribers/{subscriber_id}/letters.pdf",
    summary="INI- und HIA-Brief als PDF (Briefbogen des Mandanten)",
    response_class=Response,
)
async def letters_pdf(
    subscriber_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    """GAE-23: the INI and HIA letter on the tenant letterhead (documents.letters, DIN 5008
    layout of the renderer). Hash values are printed only as the transport computed them; a
    missing hash is never calculated here (AE23-02): the letter then carries the draft marking
    and the notice not to send it. The layout of the bank's own form is not reproduced."""
    from mhvp.documents import letters as letters_mod
    from mhvp.documents.services import letterhead

    data = await letters(subscriber_id, request, principal)
    async with tenant_tx(request, principal) as session:
        head = await letterhead(session, BlobStore(request.app.state.settings))
        sub = await _subscriber(session, subscriber_id)
    missing_hash = any(item.letter_hash is None for item in data.letters)
    tables: dict[str, letters_mod.LetterTable] = {}
    parts = [
        "Wir übermitteln die öffentlichen Schlüssel des EBICS-Teilnehmers zur Freischaltung. "
        "Die Hash-Werte entsprechen den elektronisch übertragenen Schlüsseln.",
    ]
    for index, item in enumerate(data.letters):
        name = f"k{index}"
        rows = [
            ["Auftragsart", item.order_type],
            ["Verwendung", item.usage],
            ["Version", item.version],
            ["Schlüssellänge", f"{item.key_bits} Bit"],
            ["Exponent (hex)", item.exponent_hex],
        ]
        rows += [
            ["Modulus (hex)" if i == 0 else "", line]
            for i, line in enumerate(_hex_rows(item.modulus_hex))
        ]
        rows.append(
            [
                "Hash-Wert",
                item.letter_hash or "nicht verfügbar (Übertragung liefert keinen Wert, AE23-02)",
            ]
        )
        tables[name] = letters_mod.LetterTable(
            header=["Angabe", "Wert"], rows=rows, widths=(0.25, 0.75)
        )
        parts.append(f"[[table:{name}]]")
    parts.append(
        "Ort, Datum und Unterschrift des Teilnehmers:\n\n"
        "______________________________________________"
    )
    letter = letters_mod.Letter(
        recipient_lines=[sub.label],
        subject=f"EBICS-Initialisierung (INI/HIA), Teilnehmer {data.ebics_user_id}",
        body="\n\n".join(parts),
        tables=tables,
        letter_date=local_today(),
        info=[
            ("Host-ID", data.host_id),
            ("Kunden-ID", data.partner_id),
            ("Teilnehmer-ID", data.ebics_user_id),
            ("EBICS-Version", data.ebics_version),
        ],
        notice=data.notice,
        draft_notice=(
            "ENTWURF: Hash-Wert fehlt, nicht an die Bank senden" if missing_hash else None
        ),
    )
    content = await asyncio.to_thread(letters_mod.render_pdf, head, letter)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "content-disposition": (
                f'attachment; filename="ebics-ini-hia-{data.ebics_user_id}.pdf"'
            ),
            "cache-control": "no-store",
        },
    )


@router.post(
    "/subscribers/{subscriber_id}/activation",
    summary="Freischaltung durch die Bank bestätigen",
)
async def confirm_activation(
    subscriber_id: uuid.UUID,
    body: EbicsActivationIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> EbicsSubscriberDetailOut:
    if body.activated_on > local_today():
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Das Freischaltdatum liegt in der Zukunft."
        )
    async with tenant_tx(request, principal) as session:
        _, sub = await _locked_subscriber(session, subscriber_id)
        _state(sub, S.INITIALISED)
        sub.activated_on = body.activated_on
        sub.activation_confirmed_by = principal.user_id
        sub.activation_note = body.note
        sub.status = S.ACTIVATED.value
        await _event(
            session, principal, sub, "activated", {"activated_on": body.activated_on.isoformat()}
        )
        return await _detail(session, sub)


@router.post("/subscribers/{subscriber_id}/hpb", summary="Bankschlüssel abholen (HPB)")
async def fetch_bank_keys(
    subscriber_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> EbicsSubscriberDetailOut:
    """Stores the bank's public keys with the hash values the transport reported. The keys
    are not usable before a second person verified them against the bank letter."""
    failure: ProblemError | None = None
    async with tenant_tx(request, principal) as session:
        _, sub = await _locked_subscriber(session, subscriber_id)
        _state(sub, S.ACTIVATED, S.BANK_KEYS_RECEIVED, S.READY)
        keys = await _keys(session, sub.id)
        transport = get_transport()
        try:
            client = _client_keys(keys)
            received = await _call(transport.fetch_bank_keys, _ref(sub), client)
            by_usage = {k.usage: k for k in received}
            if set(by_usage) != {"authentication", "encryption"}:
                raise ProblemError(ErrorCodes.EBICS_BANK_ERROR, detail="HPB-Antwort unvollständig.")
            for item in by_usage.values():
                keys_mod.load_public_key(item.public_pem)
        except ValueError as exc:
            failure = ProblemError(ErrorCodes.EBICS_BANK_ERROR, detail=str(exc))
            session.add(_order(sub, principal, transport, "HPB", error=failure))
        except ProblemError as exc:
            failure = exc
            session.add(_order(sub, principal, transport, "HPB", error=exc))
        else:
            for key in keys:
                if key.owner == "bank":
                    _retire(key, principal, "Neue Bankschlüssel (HPB)")
            await session.flush()
            for item in by_usage.values():
                session.add(
                    _new_key(
                        principal,
                        sub,
                        owner="bank",
                        usage=item.usage,
                        version=item.version,
                        public_pem=keys_mod.normalised_public_pem(item.public_pem),
                        source="bank",
                        private_pem=None,
                        letter_hash=(
                            keys_mod.normalise_hash(item.letter_hash) if item.letter_hash else None
                        ),
                    )
                )
            session.add(_order(sub, principal, transport, "HPB"))
            sub.bank_keys_fetched_at = _now()
            sub.bank_keys_fetched_by = principal.user_id
            sub.bank_keys_verified_at = None
            sub.bank_keys_verified_by = None
            sub.status = S.BANK_KEYS_RECEIVED.value
            await _event(session, principal, sub, "bank_keys_fetched")
        detail = await _detail(session, sub)
    if failure is not None:
        raise failure
    return detail


@router.post(
    "/subscribers/{subscriber_id}/bank-keys/verify",
    summary="Bankschlüssel gegen den Bankbrief prüfen (zweite Person)",
)
async def verify_bank_keys(
    subscriber_id: uuid.UUID,
    body: EbicsVerifyIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> EbicsSubscriberDetailOut:
    """Both hash values are typed from the bank letter (paper or signed document) and compared
    with the values received with HPB. The person who fetched the keys cannot verify them. A
    mismatch is recorded and the subscriber stays locked."""
    failure: ProblemError | None = None
    async with tenant_tx(request, principal) as session:
        _, sub = await _locked_subscriber(session, subscriber_id)
        _state(sub, S.BANK_KEYS_RECEIVED)
        if principal.user_id is None or principal.user_id == sub.bank_keys_fetched_by:
            raise ProblemError(ErrorCodes.EBICS_FOUR_EYES)
        keys = await _keys(session, sub.id)
        auth = _active(keys, "bank", "authentication")
        enc = _active(keys, "bank", "encryption")
        if auth is None or enc is None or not auth.letter_hash or not enc.letter_hash:
            raise ProblemError(ErrorCodes.EBICS_BANK_KEY_HASH_MISSING)
        mismatched = [
            usage
            for usage, key, typed in (
                ("authentication", auth, body.authentication_hash),
                ("encryption", enc, body.encryption_hash),
            )
            if keys_mod.normalise_hash(typed) != key.letter_hash
        ]
        if mismatched:
            failure = ProblemError(
                ErrorCodes.EBICS_BANK_KEY_MISMATCH,
                detail="Abweichung bei: " + ", ".join(mismatched),
            )
            await _event(session, principal, sub, "bank_key_mismatch", {"usages": mismatched})
        else:
            sub.bank_keys_verified_at = _now()
            sub.bank_keys_verified_by = principal.user_id
            sub.status = S.READY.value
            await _event(session, principal, sub, "bank_keys_verified")
        detail = await _detail(session, sub)
    if failure is not None:
        raise failure
    return detail


@router.post("/subscribers/{subscriber_id}/suspend", summary="EBICS-Teilnehmer sperren")
async def suspend_subscriber(
    subscriber_id: uuid.UUID,
    body: EbicsSuspendIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> EbicsSubscriberDetailOut:
    """Local lock, final; the bank side lock (SPR or by phone per contract) stays with the
    operator (AE23-03). The switch is not required, so a lock is possible at any time."""
    async with tenant_tx(request, principal) as session:
        sub = await _subscriber(session, subscriber_id, lock=True)
        if sub.status == S.SUSPENDED:
            raise ProblemError(ErrorCodes.EBICS_STATE, detail="Bereits gesperrt.")
        sub.status = S.SUSPENDED.value
        sub.suspended_at = _now()
        sub.suspended_by = principal.user_id
        sub.suspend_reason = body.reason
        for key in await _keys(session, sub.id):
            if key.owner == "subscriber" and key.private_key is not None:
                _retire(key, principal, "Teilnehmer gesperrt")
        await _event(session, principal, sub, "suspended")
        return await _detail(session, sub)


async def _known_account(session: AsyncSession, iban: str) -> Any:
    from mhvp.properties.models import PropertyBankAccount

    return await session.scalar(
        select(PropertyBankAccount.id).where(
            PropertyBankAccount.iban_fingerprint == crypto.fingerprint(iban)
        )
    )


async def _import_c53(
    session: AsyncSession,
    request: Request,
    principal: TenantPrincipal,
    content: bytes,
) -> dict[str, Any]:
    return await import_c53_content(
        session,
        blobs=BlobStore(request.app.state.settings),
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        content=content,
    )


async def import_c53_content(
    session: AsyncSession,
    *,
    blobs: BlobStore,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    content: bytes,
) -> dict[str, Any]:
    """Imports every camt.053 of the download whose accounts are known; members of unknown
    accounts are skipped and reported (suffix only). Re-delivered statements add nothing (B08:
    bank reference per account, D05)."""
    from mhvp.banking.raw_archive import archive_raw

    parsed, skipped_members = parse_c53(content)
    keys = ("new", "duplicates", "possible_duplicates", "transfers", "statements")
    counts = dict.fromkeys(keys, 0)
    runs: list[str] = []
    skipped_accounts: list[dict[str, str]] = []
    nonconforming = 0
    for member, file in parsed:
        nonconforming += 0 if member.name_conforms else 1
        unknown = [s.iban for s in file.statements if await _known_account(session, s.iban) is None]
        if unknown:
            skipped_accounts.extend({"file": member.name, "iban_suffix": i[-4:]} for i in unknown)
            continue
        try:
            run = await svc.import_file(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                parsed=file,
                document_id=None,
            )
        except IntegrityError:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Der Auszug wird gerade parallel importiert."
            ) from None
        run.source = "ebics:C53"
        for key in counts:
            counts[key] += int((run.counts or {}).get(key, 0))
        runs.append(str(run.id))
        if run.property_bank_account_id is not None:
            try:
                await archive_raw(
                    session,
                    blobs,
                    tenant_id=tenant_id,
                    account_id=run.property_bank_account_id,
                    data=member.data,
                    ext="xml",
                    day=local_today(),
                    created_by=user_id,
                    label="EBICS C53 Rohdatei",
                )
            except ProblemError:
                log.warning("bank.ebics_raw_archive_failed", exc_info=True)
        await emit(
            session,
            tenant_id=tenant_id,
            type="bank_sync_run.completed",
            entity_type="bank_sync_run",
            entity_id=run.id,
            actor_user_id=user_id,
            payload=run.counts,
        )
    return {
        "files": len(parsed),
        "runs": runs,
        "skipped_members": skipped_members,
        "skipped_accounts": skipped_accounts,
        "names_nonconforming": nonconforming,
        **counts,
    }


@router.post(
    "/subscribers/{subscriber_id}/statements",
    summary="Kontoauszüge abrufen (C53, camt.053)",
)
async def download_statements(
    subscriber_id: uuid.UUID,
    body: EbicsStatementsIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> EbicsOrderOut:
    """Downloads the C53 ZIP (BTF ``EOP/DE//camt.053/ZIP``) and imports it like an uploaded
    statement file. Whether the bank honours a date range is defined by the specification and
    the contract (AE23-02); the range is passed to the transport unchanged."""
    if body.date_from and body.date_to and body.date_from > body.date_to:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Zeitraum ist ungültig.")
    if body.date_to and body.date_to > local_today():
        raise ProblemError(ErrorCodes.VALIDATION, detail="Zeitraum liegt in der Zukunft.")
    failure: ProblemError | None = None
    async with tenant_tx(request, principal) as session:
        _, sub = await _locked_subscriber(session, subscriber_id)
        _state(sub, S.READY)
        keys = await _keys(session, sub.id)
        transport = get_transport()
        fields: dict[str, Any] = {
            "btf": C53.btf,
            "date_from": body.date_from,
            "date_to": body.date_to,
        }
        try:
            connector = EbicsConnector(_ref(sub), _client_keys(keys), transport)
            content, ref = await _call(connector.download_statements, body.date_from, body.date_to)
            fields["file_sha256"] = hashlib.sha256(content).hexdigest()
            fields["transport_ref"] = ref
            # one savepoint: a failure leaves no partial import, only the failed order
            async with session.begin_nested():
                result = await _import_c53(session, request, principal, content)
        except ValueError as exc:
            failure = ProblemError(ErrorCodes.VALIDATION, detail=str(exc)[:500])
            order = _order(sub, principal, transport, "C53", error=failure, **fields)
        except ProblemError as exc:
            failure = exc
            order = _order(sub, principal, transport, "C53", error=exc, **fields)
        else:
            order = _order(sub, principal, transport, "C53", result=result, **fields)
            sub.last_download_at = _now()
            from mhvp.banking.routers import _queue_proposals

            for run_id in result["runs"]:
                _queue_proposals(session, request, principal.tenant_id, uuid.UUID(run_id))
        session.add(order)
        await session.flush()
        await session.refresh(order)
        out = _order_out(order)
    if failure is not None:
        raise failure
    return out
