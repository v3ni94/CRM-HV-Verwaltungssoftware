"""Mailboxes and messages (6.6, M20). Credentials are encrypted and never returned."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin


def _fk(target: str) -> Any:
    return mapped_column(UUID(as_uuid=True), ForeignKey(target), nullable=True)


class Mailbox(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "mailbox"

    address: Mapped[str] = mapped_column(String(320), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="imap")  # imap, gmail
    imap_host: Mapped[str | None] = mapped_column(String(255))
    imap_port: Mapped[int | None] = mapped_column(Integer)
    smtp_host: Mapped[str | None] = mapped_column(String(255))
    smtp_port: Mapped[int | None] = mapped_column(Integer)
    username: Mapped[str | None] = mapped_column(String(320))
    secret: Mapped[str | None] = mapped_column(EncryptedText())
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_uid: Mapped[int | None] = mapped_column(Integer)
    # Gmail: `secret` holds the OAuth refresh token; the history id is the incremental cursor.
    gmail_history_id: Mapped[str | None] = mapped_column(String(32))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    # Default mailbox: every member of the tenant may read it; others need a MailboxUser row.
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # "Erledigt archiviert Mail" (operator 25.09.2026, M20): beim Setzen eines verknüpften
    # Tickets auf erledigt/geschlossen werden dessen Gmail-Nachrichten aus dem Posteingang
    # archiviert (Job in ``mhvp.communication.tasks``). Nur für ``kind == "gmail"`` wirksam.
    archive_on_ticket_done: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # Fehlt dem gespeicherten Google-Consent der Bereich ``gmail.modify`` (nur bei älteren
    # Verbindungen), wird hier ein Hinweis vermerkt statt den Archivierungsjob scheitern zu
    # lassen; die Verbindung ist dann unter Einstellungen, Postfächer neu herzustellen.
    archive_scope_missing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Google Calendar (M23-02): reuses the mailbox's Google OAuth refresh token (`secret`).
    calendar_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    calendar_id: Mapped[str] = mapped_column(
        String(320), nullable=False, default="primary", server_default="primary"
    )
    # Soft delete (Review 26.09.2026, M12): ein entferntes Postfach bleibt als deaktivierter
    # Datensatz erhalten, seine Nachrichten behalten die Postfachbindung und damit die
    # bisherige Sichtbarkeitsregel (Freigabe je Benutzer oder Administrator). Ein erneutes
    # Verbinden derselben Adresse belebt den Datensatz wieder.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MailboxUser(IdMixin, TenantMixin, Base):
    """Read access of a user to a non default mailbox (granted by a tenant admin)."""

    __tablename__ = "mailbox_user"
    __table_args__ = (
        UniqueConstraint("mailbox_id", "user_id", name="uq_mailbox_user"),
        Index("ix_mailbox_user_tenant", "tenant_id", "user_id"),
    )

    mailbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mailbox.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class Message(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "message"
    __table_args__ = (
        Index("ix_message_header_id", "tenant_id", "header_message_id"),
        Index("ix_message_gmail_thread", "tenant_id", "gmail_thread_id"),
    )

    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="email")
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # in, out
    mailbox_id: Mapped[uuid.UUID | None] = _fk("mailbox.id")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="new"
    )  # in: new, assigned, done. out: draft, pending, sending, sent (Vier-Augen-Freigabe,
    # M20). ``sending`` ist der eigene Schritt zwischen Freigabe und Versandnachweis (Review
    # 26.09.2026, M1): die Message-ID ist bereits gespeichert und dient als Idempotenzschlüssel.
    from_address: Mapped[str | None] = mapped_column(String(320))
    to_addresses: Mapped[list[str]] = mapped_column(
        ARRAY(String(320)), nullable=False, default=list
    )
    # Kopie-Empfänger (Cc) getrennt von ``to_addresses`` (Ticket-Mailverlauf, operator
    # 26.09.2026); eingehend aus der Kopfzeile, ausgehend aus dem Antwortformular.
    cc_addresses: Mapped[list[str]] = mapped_column(
        ARRAY(String(320)), nullable=False, default=list, server_default=text("'{}'")
    )
    subject: Mapped[str | None] = mapped_column(String(998))
    body: Mapped[str | None] = mapped_column(Text)
    # Bereinigtes HTML der Mail (``mhvp.communication.html``), nur für die Anzeige; der
    # Klartext in ``body`` bleibt die Grundlage für Regeln, Suche und KI-Vorschläge.
    body_html: Mapped[str | None] = mapped_column(Text)
    header_message_id: Mapped[str | None] = mapped_column(String(998))
    in_reply_to: Mapped[str | None] = mapped_column(String(998))
    # Kopfzeile ``References`` (RFC 5322), damit Antworten beim Empfänger im Thread bleiben.
    references_header: Mapped[str | None] = mapped_column(Text)
    thread_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contact_id: Mapped[uuid.UUID | None] = _fk("contact.id")
    property_id: Mapped[uuid.UUID | None] = _fk("property.id")
    ticket_id: Mapped[uuid.UUID | None] = _fk("ticket.id")
    document_id: Mapped[uuid.UUID | None] = _fk("document.id")
    attachment_document_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    classification: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    appointment_suggestions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    reply_due: Mapped[date | None] = mapped_column(Date)
    # Freigabe-Workflow für ausgehende Mails (M20): submit -> approve/reject (Vier-Augen-Prinzip).
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_note: Mapped[str | None] = mapped_column(Text)
    # M20-03: Kennzeichen des Verfassers zum Zeitpunkt der Vorformulierung (Ticketantwort):
    # bei true braucht der Entwurf die Freigabe einer zweiten Person, Grund wie an der
    # Mitgliedschaft (``azubi``, ``neuer_mitarbeiter``). Nachvollziehbar am Ticket.
    author_approval_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    author_approval_reason: Mapped[str | None] = mapped_column(String(32))
    gmail_message_id: Mapped[str | None] = mapped_column(String(64))
    # Gmail-Thread der eingehenden Mail (Review 26.09.2026, M7): Rückfall für die Zuordnung,
    # wenn weder ``In-Reply-To`` noch ``References`` eine bekannte Nachricht treffen.
    gmail_thread_id: Mapped[str | None] = mapped_column(String(64))
    # Letzter Versandfehler bei der Freigabe (Status ``pending`` bleibt, Anzeige
    # "fehlgeschlagen" im Ticket); wird beim erfolgreichen Versand geleert.
    send_error: Mapped[str | None] = mapped_column(Text)
    # KI-Vorschlag je eingehender Mail (M20 Übernahme): Kategorie, Dringlichkeit, Zusammenfassung,
    # erkanntes Objekt/Kontakt, Antwortentwurf, passendes Playbook. Nur Vorschlag (mhvp.ai.gateway).
    suggestion: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    suggestion_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="none", server_default="none"
    )  # none, pending, ready, failed, skipped


class Playbook(IdMixin, TimestampMixin, TenantMixin, Base):
    """Aus geschlossenen Tickets gelernter Ablauf (M20 Übernahme aus dem Immoware Hub)."""

    __tablename__ = "playbook"
    __table_args__ = (UniqueConstraint("tenant_id", "title", name="uq_playbook_title"),)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64))
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    reply_template: Mapped[str | None] = mapped_column(Text)
    source_ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ticket.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft"
    )  # draft, active, archived
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Dispatch(IdMixin, TimestampMixin, TenantMixin, Base):
    """Delivery of a document to a recipient per channel with evidence (M23)."""

    __tablename__ = "dispatch"
    __table_args__ = (Index("ix_dispatch_contact", "tenant_id", "contact_id"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id"), nullable=False
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)  # post, email, portal
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="prepared"
    )  # prepared, sent, delivered, failed
    message_id: Mapped[uuid.UUID | None] = _fk("message.id")
    batch: Mapped[str | None] = mapped_column(String(64))
    evidence_kind: Mapped[str | None] = mapped_column(String(32))
    evidence_ref: Mapped[str | None] = mapped_column(String(200))
    evidence_document_id: Mapped[uuid.UUID | None] = _fk("document.id")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvoiceIntakeAutoRun(IdMixin, TimestampMixin, TenantMixin, Base):
    """Markierung des automatischen Belegeingangs (M14-05): je Anhang höchstens ein
    ``extract_invoice``-Lauf. Der eindeutige Schlüssel (tenant_id, document_id) verhindert
    doppelte Läufe auch bei parallelen oder wiederholten Abrufen."""

    __tablename__ = "invoice_intake_auto_run"
    __table_args__ = (UniqueConstraint("tenant_id", "document_id"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id"), nullable=False
    )
    message_id: Mapped[uuid.UUID | None] = _fk("message.id")
    task_run_id: Mapped[uuid.UUID | None] = _fk("ai_task_run.id")
