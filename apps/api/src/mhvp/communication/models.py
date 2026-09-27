"""Mailboxes and messages (6.6, M20). Credentials are encrypted and never returned."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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
    # Gmail push (operator 26.09.2026): ``users.watch`` on the label INBOX with the platform's
    # Pub/Sub topic. ``gmail_watch_expiration`` is Google's expiry (at most seven days); the
    # daily job and the beat sync renew the watch a day before. ``gmail_watch_history_id`` is
    # the history id Google returned with the watch, ``gmail_last_push_at`` the last accepted
    # push notification for this address. The incremental cursor stays ``gmail_history_id``.
    gmail_watch_expiration: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gmail_watch_history_id: Mapped[str | None] = mapped_column(String(32))
    gmail_last_push_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Full inbox backfill (operator 26.09.2026): paginated ``messages.list`` of the label INBOX,
    # independent of the history cursor, resumable via ``backfill_page_token``. Status values:
    # idle, queued, running, done, failed (``mhvp.communication.backfill``).
    backfill_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="idle", server_default="idle"
    )
    backfill_total: Mapped[int | None] = mapped_column(Integer)
    backfill_done: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    backfill_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    backfill_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    backfill_page_token: Mapped[str | None] = mapped_column(Text)


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
        # Open Gmail archive jobs for the retry beat (migration 0160).
        Index(
            "ix_message_archive_open",
            "tenant_id",
            "archive_status",
            postgresql_where=text("archive_status IN ('pending', 'failed', 'scope_missing')"),
        ),
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
    # Gmail archive tracking (operator report 27.09.2026): ``archive_status`` is one of
    # pending (requested, not yet done), archived, skipped (mailbox switch off or no Gmail
    # id), failed (Gmail error, retried by the beat job) or scope_missing (consent lacks
    # gmail.modify, retried after the mailbox is reconnected). ``archived_at`` set means the
    # job is done and never repeated (idempotent); ``archive_error`` holds the last reason.
    archive_status: Mapped[str | None] = mapped_column(String(16))
    archive_error: Mapped[str | None] = mapped_column(Text)
    archive_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


class MailApprovalReauth(IdMixin, TimestampMixin, TenantMixin, Base):
    """M20-04: letzte erfolgreiche Re-Authentifizierung (Passwort oder TOTP) je Nutzer, gültig
    für ``mhvp.communication.mail_approval.REAUTH_WINDOW`` (5 Minuten) vor einer Mailfreigabe.
    Eine Zeile je (Mandant, Nutzer); ein erneuter Nachweis überschreibt die vorherige."""

    __tablename__ = "mail_approval_reauth"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_mail_approval_reauth_user"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)  # password, totp
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MailApprovalDeputy(IdMixin, TimestampMixin, TenantMixin, Base):
    """M20-04 Vertretungsregel: befristete Vertretung, damit ein Stellvertreter bei
    Abwesenheit eines Postfachnutzers dessen Mailfreigaben übernehmen kann. Es gibt noch kein
    eigenes Abwesenheits-/HR-Modul (docs/ASSUMPTIONS.md M20-04); Zeitraum und Grund werden hier
    manuell hinterlegt, keine automatische Ableitung aus Kalender oder Urlaubsplanung."""

    __tablename__ = "mail_approval_deputy"
    __table_args__ = (
        Index("ix_mail_approval_deputy_absent", "tenant_id", "absent_user_id", "ends_at"),
    )

    absent_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    deputy_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PostalSettings(IdMixin, TimestampMixin, TenantMixin, Base):
    """Postversand je Mandant (M23-01, docs/rules/M23-01.md): Anbieter, Freigabe und
    verschluesselte Zugangsdaten. Standard ``manual`` und ``enabled = false``: ohne
    ausdrueckliche Freigabe reicht kein Endpunkt, Job oder Import einen Brief bei einem
    externen Anbieter ein. Der API-Schluessel wird nie zurueckgegeben."""

    __tablename__ = "postal_settings"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_postal_settings_tenant"),)

    provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual", server_default="manual"
    )  # manual, letterxpress (weitere ueber ``postal.register_provider``)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    username: Mapped[str | None] = mapped_column(String(200))
    api_key: Mapped[str | None] = mapped_column(EncryptedText())
    # LetterXpress: ``test`` legt Auftraege nur in den Warenkorb, ``live`` versendet.
    mode: Mapped[str] = mapped_column(
        String(8), nullable=False, default="test", server_default="test"
    )
    default_color: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    default_duplex: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    default_registered: Mapped[str | None] = mapped_column(String(8))  # r1, r2
    last_balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class PostalJob(IdMixin, TimestampMixin, TenantMixin, Base):
    """Auftrag beim Postdienst je Zustellung (``dispatch``). Status: submitted, printed, sent,
    delivered, failed, cancelled. Die Statushistorie steht in ``postal_job_event``."""

    __tablename__ = "postal_job"
    __table_args__ = (
        Index("ix_postal_job_dispatch", "tenant_id", "dispatch_id"),
        Index("ix_postal_job_open", "tenant_id", "provider", "status"),
    )

    dispatch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dispatch.id"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id"), nullable=False
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id"), nullable=False
    )
    dunning_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dunning_case.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_job_id: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="submitted", server_default="submitted"
    )
    options: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    recipient_address: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    filename: Mapped[str | None] = mapped_column(String(255))
    pages: Mapped[int | None] = mapped_column(Integer)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    tracking_code: Mapped[str | None] = mapped_column(String(64))
    tracking_status: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PostalJobEvent(IdMixin, TimestampMixin, TenantMixin, Base):
    """Statushistorie eines Postauftrags (an der Zustellung sichtbar): Quelle ``provider``
    (Statusabruf), ``manual`` (Erfassung im CRM) oder ``system``."""

    __tablename__ = "postal_job_event"
    __table_args__ = (Index("ix_postal_job_event_job", "tenant_id", "job_id"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("postal_job.id", ondelete="CASCADE"), nullable=False
    )
    dispatch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dispatch.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
