"""One way contact sync CRM to Lexware Office after a person applied a change (rule
INT-LEXO-01, section 4 of the spec).

Hook :func:`queue_contact_sync` is called from ``PUT/PATCH /contacts/{id}`` and from the
accepted ``contact_change`` proposal; never from imports, bulk actions, automation or the
portal. It only writes queue rows. The worker handlers here read the remote contact first,
check content conflicts against the baseline, merge only the changed managed fields into the
full read object and ``PUT`` it with the read version (409 is re-read up to three times).
Bank data never leaves the platform (forbidden field check in ``payloads``).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts import services as contact_services
from mhvp.contacts.models import Contact
from mhvp.integrations.lexoffice_async import (
    LexofficeConflictError,
    LexofficeNotFoundError,
    LexofficeUnavailableError,
)
from mhvp.integrations.lexoffice_ext import payloads, services
from mhvp.integrations.lexoffice_ext.payloads import MANAGED_FIELDS
from mhvp.integrations.models import (
    LexofficeContactLink,
    LexofficeLinkStatus,
    LexofficeOutbox,
    LexofficeOutboxKind,
    LexofficeOutboxStatus,
    LexofficeTenantConfig,
)
from mhvp.tickets.models import TicketEvent

log = logging.getLogger(__name__)

BERLIN = ZoneInfo("Europe/Berlin")
MAX_CONFLICT_REREADS = 3
LINKED_STATES = frozenset(
    {
        LexofficeLinkStatus.LINKED.value,
        LexofficeLinkStatus.SYNCED.value,
        LexofficeLinkStatus.ERROR.value,
        LexofficeLinkStatus.PENDING.value,
    }
)
CHANGE_TO_MANAGED = {
    "addresses": "address",
    "emails": "email",
    "phones": "phone",
    "first_name": "name",
    "last_name": "name",
    "company_name": "name",
    "salutation": "name",
}


def managed_fields_of(changed: set[str] | list[str]) -> set[str]:
    return {CHANGE_TO_MANAGED[c] for c in changed if c in CHANGE_TO_MANAGED}


async def _ticket_event(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    ticket_id: uuid.UUID | None,
    kind: str,
    data: dict[str, Any],
    user_id: uuid.UUID | None = None,
) -> None:
    if ticket_id is None:
        return
    session.add(
        TicketEvent(tenant_id=tenant_id, ticket_id=ticket_id, kind=kind, data=data, user_id=user_id)
    )


async def queue_contact_sync(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    contact_id: uuid.UUID,
    contact_version: int,
    changed_fields: set[str] | list[str],
    actor_user_id: uuid.UUID | None,
    source: str,
    *,
    valid_from: date | None = None,
    ticket_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    """Never raises; returns the ids of the queue rows written (one per enabled config)."""
    try:
        return await _queue_contact_sync(
            session,
            tenant_id,
            contact_id,
            contact_version,
            managed_fields_of(changed_fields),
            actor_user_id,
            source,
            valid_from=valid_from,
            ticket_id=ticket_id,
        )
    except Exception:  # pragma: no cover - defensive, the contact change must not fail
        log.exception("lexoffice: queue_contact_sync failed", extra={"contact_id": str(contact_id)})
        return []


async def _queue_contact_sync(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    contact_id: uuid.UUID,
    contact_version: int,
    fields: set[str],
    actor_user_id: uuid.UUID | None,
    source: str,
    *,
    valid_from: date | None,
    ticket_id: uuid.UUID | None,
) -> list[uuid.UUID]:
    if not fields:
        return []
    written: list[uuid.UUID] = []
    for config in await services.list_configs(session, tenant_id):
        if not services.feature_on(config, "sync_contacts"):
            continue
        link = await session.scalar(
            select(LexofficeContactLink).where(
                LexofficeContactLink.config_id == config.id,
                LexofficeContactLink.contact_id == contact_id,
            )
        )
        if link is None or link.sync_status not in LINKED_STATES:
            continue
        wanted = set(fields)
        if not config.sync_names:
            wanted.discard("name")
        if not wanted:
            continue
        # Supersede older pending updates of the same contact and carry their fields along.
        pending = (
            await session.scalars(
                select(LexofficeOutbox).where(
                    LexofficeOutbox.config_id == config.id,
                    LexofficeOutbox.kind == LexofficeOutboxKind.CONTACT_UPDATE.value,
                    LexofficeOutbox.target_id == contact_id,
                    LexofficeOutbox.status == LexofficeOutboxStatus.PENDING.value,
                )
            )
        ).all()
        for old in pending:
            if old.payload.get("contact_version") == contact_version:
                continue
            old.status = LexofficeOutboxStatus.SUPERSEDED.value
            wanted |= set(old.payload.get("fields") or [])
        next_at: datetime | None = None
        if valid_from is not None and valid_from > datetime.now(BERLIN).date():
            next_at = datetime(
                valid_from.year, valid_from.month, valid_from.day, tzinfo=BERLIN
            ).astimezone(UTC)
        row = await services.enqueue(
            session,
            tenant_id=tenant_id,
            config_id=config.id,
            kind=LexofficeOutboxKind.CONTACT_UPDATE,
            idempotency_key=f"contact-{contact_id}-cfg{config.id}-v{contact_version}",
            target_kind="contact",
            target_id=contact_id,
            payload={
                "contact_id": str(contact_id),
                "contact_version": contact_version,
                "fields": sorted(wanted),
                "source": source,
                "force": False,
                "ticket_id": str(ticket_id) if ticket_id else None,
            },
            requested_by=actor_user_id,
            next_attempt_at=next_at,
        )
        if row.status == LexofficeOutboxStatus.PENDING.value:
            row.payload = {
                **row.payload,
                "fields": sorted(set(row.payload.get("fields") or []) | wanted),
            }
        link.sync_status = LexofficeLinkStatus.PENDING.value
        written.append(row.id)
        await _ticket_event(
            session,
            tenant_id,
            ticket_id,
            "lexoffice_sync_queued",
            {"contact_id": str(contact_id), "fields": sorted(wanted), "config_id": str(config.id)},
            actor_user_id,
        )
    await session.flush()
    return written


async def on_contact_removed(
    session: AsyncSession, tenant_id: uuid.UUID, contact_id: uuid.UUID
) -> None:
    """Soft delete or anonymisation: links become ``unlinked_local``, pending rows fail, and
    every stored value of the contact is cleared. No call to Lexware."""
    links = (
        await session.scalars(
            select(LexofficeContactLink).where(
                LexofficeContactLink.tenant_id == tenant_id,
                LexofficeContactLink.contact_id == contact_id,
            )
        )
    ).all()
    for link in links:
        link.sync_status = LexofficeLinkStatus.UNLINKED_LOCAL.value
        link.baseline_snapshot = {}
        link.remote_display = {}
        link.conflict = None
    rows = (
        await session.scalars(
            select(LexofficeOutbox).where(
                LexofficeOutbox.tenant_id == tenant_id,
                LexofficeOutbox.target_kind == "contact",
                LexofficeOutbox.target_id == contact_id,
            )
        )
    ).all()
    for row in rows:
        if row.status == LexofficeOutboxStatus.PENDING.value:
            row.status = LexofficeOutboxStatus.FAILED.value
            row.last_error = "Kontakt lokal entfernt"
        row.detail = {}
    await session.flush()


# Worker handlers ---------------------------------------------------------------------------


async def _link_and_contact(
    ctx: services.WorkerContext, row: LexofficeOutbox
) -> tuple[LexofficeContactLink | None, Any]:
    link = await ctx.session.scalar(
        select(LexofficeContactLink).where(
            LexofficeContactLink.config_id == ctx.config.id,
            LexofficeContactLink.contact_id == row.target_id,
        )
    )
    contact = await ctx.session.get(Contact, row.target_id)
    if contact is None or contact.deleted_at is not None:
        services.fail(row, "Kontakt lokal entfernt")
        if link is not None:
            link.sync_status = LexofficeLinkStatus.UNLINKED_LOCAL.value
        return None, None
    loaded = await contact_services.load(ctx.session, row.target_id)
    return link, loaded


def _remote_display(remote: dict[str, Any]) -> dict[str, Any]:
    roles = remote.get("roles") or {}
    managed = payloads.remote_managed_values(remote)
    addr = managed.get("billing_address") or {}
    return {
        "name": payloads.display_name(managed),
        "kind": managed["kind"],
        "customer_number": (roles.get("customer") or {}).get("number"),
        "vendor_number": (roles.get("vendor") or {}).get("number"),
        "email": (managed.get("email") or {}).get("value"),
        "city": addr.get("city"),
        "zip": addr.get("zip"),
        "archived": bool(remote.get("archived")),
        "updated_date": remote.get("updatedDate"),
        "multi_entry_lists": payloads.multi_entry_lists(remote),
    }


def apply_remote(link: LexofficeContactLink, remote: dict[str, Any]) -> None:
    roles = remote.get("roles") or {}
    link.lexoffice_version = remote.get("version")
    link.customer_number = (roles.get("customer") or {}).get("number")
    link.vendor_number = (roles.get("vendor") or {}).get("number")
    link.remote_display = _remote_display(remote)


@services.handler(LexofficeOutboxKind.REFRESH_LINK)
async def refresh_link(ctx: services.WorkerContext, row: LexofficeOutbox) -> None:
    link = await ctx.session.get(LexofficeContactLink, row.target_id)
    if link is None or not link.lexoffice_contact_id:
        services.fail(row, "Verknüpfung nicht gefunden.")
        return
    try:
        remote = await ctx.client.get_contact(link.lexoffice_contact_id)
    except LexofficeNotFoundError as exc:
        link.sync_status = LexofficeLinkStatus.REMOTE_MISSING.value
        link.last_error = exc.redacted()
        services.fail(row, exc.redacted(), exc.status_code)
        return
    apply_remote(link, remote)
    link.baseline_snapshot = payloads.remote_managed_values(remote)
    if remote.get("archived"):
        link.sync_status = LexofficeLinkStatus.REMOTE_MISSING.value
    elif payloads.multi_entry_lists(remote):
        link.sync_status = LexofficeLinkStatus.MANUAL_REQUIRED.value
        link.last_error = "Mehrfach belegte Listen in Lexware Office, bitte dort bereinigen."
    else:
        link.sync_status = LexofficeLinkStatus.LINKED.value
        link.last_error = None
    link.last_synced_at = ctx.now
    row.detail = {"lexoffice_version_after": remote.get("version")}


@services.handler(LexofficeOutboxKind.CONTACT_CREATE)
async def contact_create(ctx: services.WorkerContext, row: LexofficeOutbox) -> None:
    link, loaded = await _link_and_contact(ctx, row)
    if loaded is None or link is None:
        if loaded is not None:
            services.fail(row, "Verknüpfung nicht gefunden.")
        return
    snapshot = payloads.snapshot_from_contact(loaded)
    blocker = payloads.validate_snapshot(snapshot, {"name"})
    if blocker:
        link.sync_status = LexofficeLinkStatus.MANUAL_REQUIRED.value
        link.last_error = f"Pflichtfeld fehlt: {blocker}"
        services.fail(row, link.last_error)
        return
    roles: list[Literal["customer", "vendor"]] = [
        r for r in row.payload.get("roles") or [] if r in ("customer", "vendor")
    ]
    body = payloads.build_contact_create(snapshot, roles)
    try:
        result = await ctx.client.create_contact(body)
    except LexofficeUnavailableError as exc:
        if exc.maybe_processed:
            adopted = await _adopt_existing(ctx, snapshot)
            if adopted is not None:
                result = adopted
            else:
                link.sync_status = LexofficeLinkStatus.MANUAL_REQUIRED.value
                link.last_error = "Anlage möglicherweise erfolgt, bitte in Lexware Office prüfen"
                services.fail(row, link.last_error, exc.status_code)
                return
        else:
            raise
    remote_id = str(result.get("id") or "")
    if not remote_id:
        services.fail(row, "Antwort ohne ID.")
        return
    link.lexoffice_contact_id = remote_id
    link.lexoffice_version = result.get("version")
    link.baseline_snapshot = snapshot
    link.synced_contact_version = loaded.version
    link.sync_status = LexofficeLinkStatus.LINKED.value
    link.last_synced_at = ctx.now
    link.last_error = None
    link.remote_display = {"name": payloads.display_name(snapshot), "kind": snapshot["kind"]}
    row.detail = {
        "sent_fields": sorted(k for k in body if k != "version"),
        "lexoffice_id": remote_id,
    }
    await services.audit(
        ctx.session,
        ctx.tenant_id,
        "push_sent",
        entity_type="lexoffice_link",
        entity_id=link.id,
        actor=row.requested_by,
        payload={"kind": row.kind, "fields": row.detail["sent_fields"]},
    )


async def _adopt_existing(
    ctx: services.WorkerContext, snapshot: dict[str, Any]
) -> dict[str, Any] | None:
    """After a 504 on create: exactly one remote hit with equal name and zip is adopted."""
    email = (snapshot.get("email") or {}).get("value")
    name = snapshot.get("company_name") or snapshot.get("last_name") or ""
    try:
        if email:
            page = await ctx.client.list_contacts(email=email)
        elif len(name) >= 3:
            page = await ctx.client.list_contacts(name=name)
        else:
            return None
    except LexofficeNotFoundError:
        return None
    hits = [h for h in page.get("content") or [] if isinstance(h, dict)]
    if len(hits) != 1:
        return None
    managed = payloads.remote_managed_values(hits[0])
    same_name = payloads.display_name(managed).lower() == payloads.display_name(snapshot).lower()
    zip_local = (snapshot.get("billing_address") or {}).get("zip")
    zip_remote = (managed.get("billing_address") or {}).get("zip")
    if same_name and (zip_local or None) == (zip_remote or None):
        return hits[0]
    return None


@services.handler(LexofficeOutboxKind.CONTACT_UPDATE)
async def contact_update(ctx: services.WorkerContext, row: LexofficeOutbox) -> None:
    link, loaded = await _link_and_contact(ctx, row)
    if loaded is None:
        return
    ticket_id = uuid.UUID(row.payload["ticket_id"]) if row.payload.get("ticket_id") else None
    if link is None or not link.lexoffice_contact_id or link.sync_status not in LINKED_STATES:
        services.fail(row, "Kontakt ist nicht verknüpft.")
        return
    fields = set(row.payload.get("fields") or []) & MANAGED_FIELDS
    force = bool(row.payload.get("force"))
    snapshot = payloads.snapshot_from_contact(loaded)
    blocker = payloads.validate_snapshot(snapshot, fields)
    if blocker:
        link.sync_status = LexofficeLinkStatus.MANUAL_REQUIRED.value
        link.last_error = f"Pflichtfeld fehlt: {blocker}"
        services.fail(row, link.last_error)
        await _final_failure(ctx, row, link, ticket_id)
        return
    for _attempt in range(MAX_CONFLICT_REREADS):
        try:
            remote = await ctx.client.get_contact(link.lexoffice_contact_id)
        except LexofficeNotFoundError as exc:
            link.sync_status = LexofficeLinkStatus.REMOTE_MISSING.value
            link.last_error = "Kontakt in Lexware Office nicht gefunden."
            services.fail(row, exc.redacted(), 404)
            await _final_failure(ctx, row, link, ticket_id)
            return
        remote_managed = payloads.remote_managed_values(remote)
        if not force:
            conflict: dict[str, Any] = {}
            unchanged = True
            for field in fields:
                base = (
                    payloads.field_value(link.baseline_snapshot, field)
                    if link.baseline_snapshot
                    else None
                )
                current = payloads.field_value(remote_managed, field)
                wanted = payloads.field_value(snapshot, field)
                if current != wanted:
                    unchanged = False
                if link.baseline_snapshot and current != base and current != wanted:
                    conflict[field] = {"crm": wanted, "lexoffice": current, "baseline": base}
            if conflict:
                link.sync_status = LexofficeLinkStatus.CONFLICT.value
                link.conflict = conflict
                link.last_error = "Datensatz in Lexware Office zwischenzeitlich geändert."
                services.fail(row, link.last_error, 409)
                await _final_failure(ctx, row, link, ticket_id)
                return
            if unchanged:
                _mark_synced(link, snapshot, fields, remote.get("version"), row, ctx.now)
                row.detail = {"sent_fields": [], "lexoffice_version_after": remote.get("version")}
                return
        merged = payloads.merge_contact_update(remote, snapshot, fields, force=force)
        if merged.blocker:
            link.sync_status = (
                LexofficeLinkStatus.REMOTE_MISSING.value
                if merged.blocker == "remote_archived"
                else LexofficeLinkStatus.MANUAL_REQUIRED.value
            )
            link.last_error = {
                "remote_archived": "Kontakt in Lexware Office ist archiviert.",
                "multi_entry": "Mehrfach belegte Listen in Lexware Office, bitte dort pflegen.",
                "kind_changed": (
                    "Person und Firma unterscheiden sich, bitte in Lexware Office pflegen."
                ),
            }[merged.blocker]
            services.fail(row, link.last_error)
            await _final_failure(ctx, row, link, ticket_id)
            return
        if merged.payload is None:  # pragma: no cover - blocker handled above
            raise LexofficeConflictError("Kein Payload.", status_code=409)
        before = {f: payloads.field_value(remote_managed, f) for f in fields}
        try:
            result = await ctx.client.update_contact(link.lexoffice_contact_id, merged.payload)
        except LexofficeConflictError as exc:
            row.last_status_code = exc.status_code
            continue
        version_after = result.get("version", (remote.get("version") or 0) + 1)
        _mark_synced(link, snapshot, fields, version_after, row, ctx.now)
        link.conflict = None
        row.detail = {
            "sent_fields": sorted(fields),
            "before": before,
            "after": {f: payloads.field_value(snapshot, f) for f in fields},
            "lexoffice_version_before": remote.get("version"),
            "lexoffice_version_after": version_after,
        }
        await _ticket_event(
            ctx.session,
            ctx.tenant_id,
            ticket_id,
            "lexoffice_sync_sent",
            {
                "text": f"Lexware Office: übertragen am {ctx.now.astimezone(BERLIN):%d.%m.%Y}",
                "fields": sorted(fields),
                "config_id": str(ctx.config.id),
            },
        )
        await services.audit(
            ctx.session,
            ctx.tenant_id,
            "push_sent",
            entity_type="lexoffice_link",
            entity_id=link.id,
            actor=row.requested_by,
            payload={"kind": row.kind, "fields": sorted(fields)},
        )
        return
    raise LexofficeConflictError("Datensatz zwischenzeitlich geändert.", status_code=409)


def _mark_synced(
    link: LexofficeContactLink,
    snapshot: dict[str, Any],
    fields: set[str],
    version: Any,
    row: LexofficeOutbox,
    now: datetime,
) -> None:
    baseline = dict(link.baseline_snapshot or {})
    for field in fields:
        if field == "name":
            for key in ("kind", "first_name", "last_name", "company_name"):
                baseline[key] = snapshot.get(key)
        elif field == "address":
            baseline["billing_address"] = snapshot.get("billing_address")
        else:
            baseline[field] = snapshot.get(field)
    link.baseline_snapshot = baseline
    link.lexoffice_version = version
    link.synced_contact_version = int(row.payload.get("contact_version") or 0) or None
    link.sync_status = LexofficeLinkStatus.SYNCED.value
    link.last_synced_at = now
    link.last_error = None


async def _final_failure(
    ctx: services.WorkerContext,
    row: LexofficeOutbox,
    link: LexofficeContactLink,
    ticket_id: uuid.UUID | None,
) -> None:
    await _ticket_event(
        ctx.session,
        ctx.tenant_id,
        ticket_id,
        "lexoffice_sync_failed",
        {
            "text": f"Lexware Office: fehlgeschlagen, {link.last_error}",
            "config_id": str(ctx.config.id),
        },
    )
    await services.audit(
        ctx.session,
        ctx.tenant_id,
        "push_failed",
        entity_type="lexoffice_link",
        entity_id=link.id,
        actor=row.requested_by,
        payload={"kind": row.kind, "status": link.sync_status},
    )


def config_for_link(
    link: LexofficeContactLink, configs: list[LexofficeTenantConfig]
) -> LexofficeTenantConfig | None:
    return next((c for c in configs if c.id == link.config_id), None)
