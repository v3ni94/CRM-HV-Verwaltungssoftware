"""Shared mailbox distribution by token (11.4, M6-04, Q03-02).

One tenant (the hub) synchronises a shared mailbox and enables ``distribute`` in its intake
address configuration. Messages to ``belege+<token>@example.de`` with the token of another
tenant of the same mailbox are handed over to that tenant: the attachments are stored as new
documents of the target tenant and a copy of the inbound message is created there. The target
tenant's own document inbox (``intake.process_mailbox``) then processes it like any forward,
including the allowed sender list.

Safeguards: only the hub tenant's own messages are read (row level security stays in force),
the token must belong to an enabled configuration of another tenant with the same mailbox
address, a sender outside that tenant's allowed list is dropped, nothing is handed over twice
(Message-ID or sender, subject and time as key), and the hub keeps its original message.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.communication.models import Message
from mhvp.core.config import Settings
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import emit
from mhvp.core.problems import ProblemError
from mhvp.documents import intake_address
from mhvp.documents import services as svc
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentSource, StorageKind
from mhvp.platform.models import TenantSettings

log = logging.getLogger(__name__)

WATERMARK_KEY = "document_intake_distribution_watermark"
MAX_PER_RUN = 50


@dataclass
class _File:
    filename: str
    mime_type: str
    data: bytes


@dataclass
class _Packet:
    target: uuid.UUID
    hub: uuid.UUID
    recipient: str
    message: dict[str, Any]
    files: list[_File] = field(default_factory=list)


async def _configs(
    factory: async_sessionmaker[AsyncSession], tenant_ids: list[uuid.UUID]
) -> dict[uuid.UUID, intake_address.IntakeAddress]:
    result: dict[uuid.UUID, intake_address.IntakeAddress] = {}
    for tenant_id in tenant_ids:
        async with tenant_transaction(factory, tenant_id) as session:
            row = await session.scalar(select(TenantSettings))
            config = intake_address.load(row.sources) if row is not None else None
        if config is not None and config.enabled:
            result[tenant_id] = config
    return result


async def _collect(
    factory: async_sessionmaker[AsyncSession],
    store: BlobStore,
    hub_id: uuid.UUID,
    hub: intake_address.IntakeAddress,
    targets: dict[str, tuple[uuid.UUID, intake_address.IntakeAddress]],
) -> list[_Packet]:
    packets: list[_Packet] = []
    async with tenant_transaction(factory, hub_id) as session:
        row = await session.scalar(select(TenantSettings))
        if row is None:
            return packets
        sources = dict(row.sources or {})
        watermark = sources.get(WATERMARK_KEY)
        stmt = (
            select(Message)
            .where(Message.direction == "in", func.cardinality(Message.attachment_document_ids) > 0)
            .order_by(Message.created_at)
            .limit(MAX_PER_RUN)
        )
        if watermark:
            stmt = stmt.where(Message.created_at > datetime.fromisoformat(watermark))
        latest: datetime | None = None
        for message in (await session.scalars(stmt)).all():
            recipients = list(message.to_addresses or []) + list(message.cc_addresses or [])
            token = intake_address.token_of(hub, recipients)
            entry = targets.get(token or "")
            if entry is None or token == hub.token:
                latest = message.created_at
                continue
            target_id, target = entry
            if (
                target_id == hub_id
                or target.mailbox_address != hub.mailbox_address
                or not intake_address.sender_allowed(target, message.from_address)
            ):
                latest = message.created_at
                continue
            packet = _Packet(
                target=target_id,
                hub=hub_id,
                recipient=target.address,
                message={
                    "from_address": message.from_address,
                    "to_addresses": list(message.to_addresses or []),
                    "cc_addresses": list(message.cc_addresses or []),
                    "subject": message.subject,
                    "body": message.body,
                    "body_html": message.body_html,
                    "header_message_id": message.header_message_id,
                    "received_at": message.received_at,
                },
            )
            try:
                for document_id in message.attachment_document_ids:
                    document = await session.get(Document, document_id)
                    if document is None or document.storage is not StorageKind.MINIO:
                        continue
                    packet.files.append(
                        _File(
                            document.filename,
                            document.mime_type,
                            store.get(document.storage_ref),
                        )
                    )
            except ProblemError:
                # Storage unavailable: leave the watermark before this message, retry next run.
                log.warning("document_intake_distribution_blob_failed")
                break
            latest = message.created_at
            if packet.files:
                packets.append(packet)
        if latest is not None:
            row.sources = {**sources, WATERMARK_KEY: latest.isoformat()}
    return packets


async def _deliver(
    factory: async_sessionmaker[AsyncSession],
    store: BlobStore,
    settings: Settings,
    packet: _Packet,
) -> bool:
    data = packet.message
    async with tenant_transaction(factory, packet.target) as session:
        header_id = data["header_message_id"]
        duplicate = select(Message.id).where(Message.direction == "in")
        if header_id:
            duplicate = duplicate.where(Message.header_message_id == header_id)
        else:
            duplicate = duplicate.where(
                Message.from_address == data["from_address"],
                Message.subject == data["subject"],
                Message.received_at == data["received_at"],
            )
        if await session.scalar(duplicate.limit(1)) is not None:
            return False
        ids: list[uuid.UUID] = []
        for item in packet.files:
            try:
                document = await svc.store_document(
                    session,
                    store,
                    tenant_id=packet.target,
                    data=item.data,
                    title=item.filename[:300],
                    filename=item.filename,
                    mime_type=item.mime_type,
                    source=DocumentSource.EMAIL,
                    category_id=None,
                    links=[],
                    created_by=None,
                    settings=settings,
                )
            except ProblemError:
                log.warning("document_intake_distribution_file_rejected")
                continue
            ids.append(document.id)
        if not ids:
            return False
        session.add(
            Message(
                tenant_id=packet.target,
                channel="email",
                direction="in",
                status="new",
                attachment_document_ids=ids,
                **data,
            )
        )
        await session.flush()
        await emit(
            session,
            tenant_id=packet.target,
            type="document.intake_distributed",
            entity_type="tenant_settings",
            entity_id=None,
            actor_user_id=None,
            payload={"files": len(ids), "hub": str(packet.hub)},
        )
    return True


async def distribute_shared_mailboxes(
    factory: async_sessionmaker[AsyncSession],
    store: BlobStore,
    settings: Settings,
    tenant_ids: list[uuid.UUID],
) -> int:
    """Hands messages of hub tenants over to the tenants named by the plus token; returns
    the number of delivered messages."""
    configs = await _configs(factory, tenant_ids)
    hubs = {tid: cfg for tid, cfg in configs.items() if cfg.distribute}
    if not hubs:
        return 0
    targets = {cfg.token: (tid, cfg) for tid, cfg in configs.items()}
    delivered = 0
    for hub_id, hub in hubs.items():
        for packet in await _collect(factory, store, hub_id, hub, targets):
            if await _deliver(factory, store, settings, packet):
                delivered += 1
    return delivered
