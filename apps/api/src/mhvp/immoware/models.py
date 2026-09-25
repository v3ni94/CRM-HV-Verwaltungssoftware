"""Immoware24-Spiegel per DAV (M32, Übernahme aus dem Immoware Hub, /home/user/IMMOWARE24).

Es gibt keine Immoware24-REST-API. Der Hub belegt ausschliesslich WebDAV, CardDAV und CalDAV als
Zugangswege, strikt lesend (docs/immoware/07-sync-strategy.md, docs/immoware/08-security.md des
Hubs). Dieses Paket spiegelt Dokumente, Kontakte und Termine je Tenant; Zuordnung ausschliesslich
ueber externe IDs (href, uid), nie ueber Namen oder E-Mail. Kein Hard Delete: entfallene Zeilen
erhalten ``deleted_at``.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

SOURCE_SYSTEM = "immoware24"


def _enum(cls: type[StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class SyncKind(StrEnum):
    WEBDAV = "webdav"
    CARDDAV = "carddav"
    CALDAV = "caldav"


class SyncStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"
    FAILED = "failed"


class ImmowareConnection(IdMixin, TimestampMixin, TenantMixin, Base):
    """Eine DAV-Anbindung je Tenant (read only). Passwort feldverschluesselt (ADR 0006)."""

    __tablename__ = "immoware_connection"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    base_url: Mapped[str | None] = mapped_column(String(500))
    carddav_url: Mapped[str | None] = mapped_column(String(500))
    caldav_url: Mapped[str | None] = mapped_column(String(500))
    username: Mapped[str | None] = mapped_column(String(200))
    password: Mapped[str | None] = mapped_column(EncryptedText())
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verify_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    poll_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_error: Mapped[str | None] = mapped_column(Text)
    # Discovery (RFC 6764/4918, Betreiberbericht 25.09.2026): nur gesetzt, solange die
    # jeweilige URL nicht manuell vom Anwender gepflegt wurde.
    webdav_root_url: Mapped[str | None] = mapped_column(String(500))
    carddav_url_discovered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    caldav_url_discovered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    webdav_root_discovered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    last_diagnosis: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_diagnosis_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auto_take_over_contacts: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class _MirrorMixin:
    """Pflichtfelder jeder externen Entitaet (Regel 4 des Hubs)."""

    source_system: Mapped[str] = mapped_column(String(32), nullable=False, default=SOURCE_SYSTEM)
    external_id: Mapped[str] = mapped_column(String(1000), nullable=False)
    external_parent_id: Mapped[str | None] = mapped_column(String(1000))
    external_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64))
    sync_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImmowareDavDocument(IdMixin, TimestampMixin, TenantMixin, _MirrorMixin, Base):
    """Ein WebDAV-Eintrag (Ordner oder Datei) des Immoware24-Posteingangs/Dokumentenbaums."""

    __tablename__ = "immoware_dav_document"
    __table_args__ = (UniqueConstraint("tenant_id", "external_id"),)

    href: Mapped[str] = mapped_column(String(1000), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(200))
    size: Mapped[int | None] = mapped_column(Integer)
    etag: Mapped[str | None] = mapped_column(String(300))
    last_modified: Mapped[str | None] = mapped_column(String(100))
    is_collection: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Dreistellige Objektnummer, aus dem Pfad geraten (z.B. ".../123 Musterstrasse/...").
    object_number_guess: Mapped[str | None] = mapped_column(String(3))
    # Uebernahme in den CRM-Dokumentenbestand (Betreiberbericht 25.09.2026): idempotent je
    # href+etag, siehe service.take_over_document.
    taken_over_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL"), index=True
    )
    taken_over_etag: Mapped[str | None] = mapped_column(String(300))


class ImmowareDavContact(IdMixin, TimestampMixin, TenantMixin, _MirrorMixin, Base):
    """Ein vCard-Eintrag des Immoware24-Adressbuchs (CardDAV)."""

    __tablename__ = "immoware_dav_contact"
    __table_args__ = (UniqueConstraint("tenant_id", "external_id"),)

    href: Mapped[str] = mapped_column(String(1000), nullable=False)
    etag: Mapped[str | None] = mapped_column(String(300))
    uid: Mapped[str | None] = mapped_column(String(300))
    vcard_raw: Mapped[str | None] = mapped_column(Text)
    fn: Mapped[str | None] = mapped_column(String(300))
    org: Mapped[str | None] = mapped_column(String(300))
    emails: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    phones: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    addresses: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    matched_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="SET NULL")
    )


class ImmowareDavEvent(IdMixin, TimestampMixin, TenantMixin, _MirrorMixin, Base):
    """Ein iCalendar-Termin des Immoware24-Kalenders (CalDAV)."""

    __tablename__ = "immoware_dav_event"
    __table_args__ = (UniqueConstraint("tenant_id", "external_id"),)

    href: Mapped[str] = mapped_column(String(1000), nullable=False)
    etag: Mapped[str | None] = mapped_column(String(300))
    uid: Mapped[str | None] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(String(500))
    dtstart: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dtend: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    ical_raw: Mapped[str | None] = mapped_column(Text)


class ImmowareSyncRun(IdMixin, TimestampMixin, TenantMixin, Base):
    """Protokoll eines Abholvorgangs je Art (fuer /sync/runs und Fehlerdiagnose)."""

    __tablename__ = "immoware_sync_run"

    kind: Mapped[SyncKind] = mapped_column(_enum(SyncKind, "immoware_sync_kind"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[SyncStatus] = mapped_column(
        _enum(SyncStatus, "immoware_sync_status"), nullable=False, default=SyncStatus.RUNNING
    )
    seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    # Pro-Ordner-Fehler eines WebDAV-Laufs (401/403 u.a.), der Lauf selbst bricht dabei nicht ab
    # (Betreiberbericht 25.09.2026): Liste von {"url": <maskiert>, "status": int, "note": str}.
    folder_errors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )


class LearningKind(StrEnum):
    """Art des Lernlaufs (M33, Uebernahme des Moduls Learning aus dem Immoware Hub)."""

    WEBDAV = "webdav"
    CARDDAV = "carddav"
    CALDAV = "caldav"


class LearningStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ImmowareLearningRun(IdMixin, TimestampMixin, TenantMixin, Base):
    """Ein Lauf der Lernphase (M33): erkundet lesend Struktur und Feldnutzung des Immoware24-
    Spiegels je Art und vergleicht das Ergebnis mit dem letzten erfolgreichen Lauf gleicher Art
    (LearningDiffer im Hub). Reine Erkenntnisgewinnung ohne Schreibpfad, siehe
    docs/plans/M33-immoware-lernphase.md."""

    __tablename__ = "immoware_learning_run"

    kind: Mapped[LearningKind] = mapped_column(
        _enum(LearningKind, "immoware_learning_kind"), nullable=False, index=True
    )
    status: Mapped[LearningStatus] = mapped_column(
        _enum(LearningStatus, "immoware_learning_status"),
        nullable=False,
        default=LearningStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    facts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
