"""Contacts, parties and consents (section 6.1, milestone M3)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, ORMExecuteState, Session, mapped_column, with_loader_criteria

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin


def _enum(cls: type[StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class ContactKind(StrEnum):
    PERSON = "person"
    COMPANY = "company"


class PreferredChannel(StrEnum):
    POST = "post"
    EMAIL = "email"
    PORTAL = "portal"


class Completeness(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class AddressLabel(StrEnum):
    POSTAL = "postal"
    PRIVATE = "private"
    WORK = "work"
    PUBLIC = "public"


class PhoneLabel(StrEnum):
    WORK = "work"
    MOBILE = "mobile"
    PRIVATE = "private"
    FAX = "fax"
    OTHER = "other"


class IdentifierKind(StrEnum):
    TAX_NUMBER = "tax_number"
    VAT_ID = "vat_id"
    SEPA_CREDITOR_ID = "sepa_creditor_id"
    REGISTRY_NUMBER = "registry_number"
    CUSTOMER_NUMBER = "customer_number"


class ContactRoleCode(StrEnum):
    """Operator classification, multiple values allowed (task M3-02). Distinct from `kind`
    (person/organisation) and from `ContactTypeCode` (process derived contact types)."""

    EIGENTUEMER = "eigentuemer"
    MIETER = "mieter"
    VERWALTER = "verwalter"
    DIENSTLEISTER = "dienstleister"
    BANK = "bank"
    SONSTIGES = "sonstiges"


class MandateGrantedVia(StrEnum):
    TELEFON = "telefon"
    BRIEF = "brief"
    EMAIL = "email"
    PORTAL = "portal"
    PERSOENLICH = "persoenlich"


class MandateScheme(StrEnum):
    CORE = "core"
    B2B = "b2b"


class ContactMandateStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class BankAccountApproval(StrEnum):
    """Four eyes release of a new or changed contact IBAN (M5-01)."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ContactTypeCode(StrEnum):
    TENANT = "tenant"
    PROSPECT = "prospect"
    OWNER = "owner"
    SERVICE_PROVIDER = "service_provider"
    BROKER = "broker"
    MANAGER = "manager"
    BANK = "bank"
    BOARD_MEMBER = "board_member"
    AUTHORITY = "authority"
    OTHER = "other"


class RelationKind(StrEnum):
    SPOUSE = "spouse"
    REPRESENTATIVE = "representative"
    HEIR = "heir"
    GUARANTOR = "guarantor"
    EMPLOYEE_OF = "employee_of"
    AUTHORIZED_PERSON = "authorized_person"


class DeliveryMode(StrEnum):
    """Delivery rule of an authorised representative (relation kind ``representative``,
    operator decision 26.09.2026): who receives mails, letters and WEG invitations addressed
    to the represented contact."""

    BOTH = "both"
    REPRESENTATIVE_ONLY = "representative_only"
    OWNER_ONLY = "owner_only"


class PartyRole(StrEnum):
    PRIMARY = "primary"
    CO_PARTY = "co_party"
    GUARANTOR = "guarantor"
    LEGAL_REPRESENTATIVE = "legal_representative"


class ContactBankAccountKind(StrEnum):
    """Account types of catalogue B.4 (Masterprompt Ergänzung 27.09.2026)."""

    RENT = "rent"
    BANK_1 = "bank_1"
    BANK_2 = "bank_2"
    HOA = "hoa"
    RESERVE = "reserve"
    DEPOSIT = "deposit"
    HOUSE_MONEY = "house_money"
    LEGACY = "legacy"


class ContactDateKind(StrEnum):
    """Typed dates on a contact (4.1); the birthday stays on ``Contact.date_of_birth``."""

    BIRTHDAY = "birthday"
    DEATH = "death"
    WEDDING = "wedding"
    FOUNDATION = "foundation"
    OTHER = "other"


class ConsentKind(StrEnum):
    DATA_SHARING = "data_sharing"
    PORTAL_TERMS = "portal_terms"
    EMAIL_DELIVERY = "email_delivery"
    MARKETING = "marketing"
    WHATSAPP = "whatsapp"


class Contact(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "contact"
    __table_args__ = (
        Index("ix_contact_tenant_id_last_name", "tenant_id", "last_name"),
        Index("ix_contact_tenant_display_name", "tenant_id", "display_name"),
        Index("ix_contact_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_contact_search_text_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
        Index("ix_contact_roles", "roles", postgresql_using="gin"),
        CheckConstraint(
            "roles <@ ARRAY['eigentuemer', 'mieter', 'verwalter', 'dienstleister', 'bank', "
            "'sonstiges']::text[]",
            name="ck_contact_roles_values",
        ),
        Index(
            "uq_contact_source",
            "tenant_id",
            "source_system",
            "source_id",
            unique=True,
            postgresql_where=text("source_system IS NOT NULL AND source_id IS NOT NULL"),
        ),
    )

    kind: Mapped[ContactKind] = mapped_column(_enum(ContactKind, "contact_kind"), nullable=False)
    salutation: Mapped[str | None] = mapped_column(String(50))
    letter_salutation: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(50))
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    company_name: Mapped[str | None] = mapped_column(String(200))
    legal_form: Mapped[str | None] = mapped_column(String(50))
    position: Mapped[str | None] = mapped_column(String(100))
    # Only where required by a process (e.g. landlord certificate), section 6.1.
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="de")
    notes: Mapped[str | None] = mapped_column(Text)
    preferred_channel: Mapped[PreferredChannel | None] = mapped_column(
        _enum(PreferredChannel, "preferred_channel")
    )
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Consumer property (Verbraucher) as a plain flag for the dunning module (M16-03): NULL
    # means not assessed. It is a note for the reviewer, never a legal determination.
    is_consumer: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Block date and deletion reservation (4.1; operator decision 26.09.2026): ``delete_after``
    # is computed from the retention profile and only shown as due, the deletion itself stays a
    # manual four eyes step on the existing deletion path. No automatic deletion job.
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("retention_profile.id", ondelete="SET NULL")
    )
    delete_after: Mapped[date | None] = mapped_column(Date)
    external_ids: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    completeness: Mapped[Completeness] = mapped_column(
        _enum(Completeness, "contact_completeness"), nullable=False, default=Completeness.COMPLETE
    )
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    # Operator classification (multiple values allowed); derived where contracts exist,
    # manual additions are kept. Values are constrained by ck_contact_roles_values.
    roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    # Maintained by the service: names, company, e-mails, phones, IBAN suffixes (6.1).
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', search_text)", persisted=True)
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_system: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(64))
    # Contact merge (M3-03): a merged source stays as a row (evidence), hidden from lists.
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def _contact_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="CASCADE"), nullable=False, index=True
    )


class ContactAddress(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "contact_address"
    __table_args__ = (
        # AN05 (GAJ-610, migration 0452): a closed address ends on or after its start.
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="valid_range",
        ),
        Index("ix_contact_address_tenant_contact_from", "tenant_id", "contact_id", "valid_from"),
    )

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    label: Mapped[AddressLabel] = mapped_column(
        _enum(AddressLabel, "address_label"), nullable=False
    )
    street: Mapped[str | None] = mapped_column(String(200))
    house_number: Mapped[str | None] = mapped_column(String(20))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="DE")
    addition: Mapped[str | None] = mapped_column(String(200))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # M21-02: date from which an address proposed in the portal applies (migration 0174);
    # empty for addresses recorded in the CRM.
    valid_from: Mapped[date | None] = mapped_column(Date)
    # AN05 (GAJ-610): address history behind the tenant switch contacts.address_history. A
    # replaced address is closed (valid_to, superseded_at) instead of deleted; closed rows are
    # hidden from ordinary selects (see contacts.address_history).
    valid_to: Mapped[date | None] = mapped_column(Date)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContactPhone(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "contact_phone"

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    label: Mapped[PhoneLabel] = mapped_column(_enum(PhoneLabel, "phone_label"), nullable=False)
    number: Mapped[str] = mapped_column(String(32), nullable=False)  # E.164
    country_code: Mapped[str | None] = mapped_column(String(5))
    area_code: Mapped[str | None] = mapped_column(String(10))
    note: Mapped[str | None] = mapped_column(String(200))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ContactEmail(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "contact_email"
    __table_args__ = (
        Index("ix_contact_email_tenant_id_email", "tenant_id", "email"),
        # Exactly one portal login address per contact (4.1): own attribute, not the order.
        Index(
            "ux_contact_email_portal_login",
            "contact_id",
            unique=True,
            postgresql_where=text("is_portal_login"),
        ),
    )

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    label: Mapped[str] = mapped_column(String(32), nullable=False, default="work")
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_portal_login: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ContactIdentifier(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "contact_identifier"

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    kind: Mapped[IdentifierKind] = mapped_column(
        _enum(IdentifierKind, "identifier_kind"), nullable=False
    )
    value: Mapped[str] = mapped_column(String(100), nullable=False)


class ContactDate(IdMixin, TimestampMixin, TenantMixin, Base):
    """Typed dates of a contact, any number (4.1)."""

    __tablename__ = "contact_date"
    __table_args__ = (UniqueConstraint("tenant_id", "contact_id", "kind", "date"),)

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    kind: Mapped[ContactDateKind] = mapped_column(
        _enum(ContactDateKind, "contact_date_kind"), nullable=False
    )
    value: Mapped[date] = mapped_column("date", Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))


class ContactBankAccount(IdMixin, TimestampMixin, TenantMixin, Base):
    """IBAN encrypted per tenant; last four characters in clear for search (6.1)."""

    __tablename__ = "contact_bank_account"
    __table_args__ = (
        Index("ix_contact_bank_account_tenant_id_iban_suffix", "tenant_id", "iban_suffix"),
        Index(
            "ux_contact_bank_account_tenant_mandate_reference",
            "tenant_id",
            "mandate_reference",
            unique=True,
            postgresql_where=text("mandate_reference IS NOT NULL"),
        ),
        # Exactly one default account per contact (4.1).
        Index(
            "ux_contact_bank_account_default",
            "contact_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    label: Mapped[str | None] = mapped_column(String(100))
    kind: Mapped[ContactBankAccountKind | None] = mapped_column(
        _enum(ContactBankAccountKind, "contact_bank_account_kind")
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    bank_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="SET NULL")
    )
    iban: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    iban_suffix: Mapped[str] = mapped_column(String(4), nullable=False)
    # Keyed hash of the normalised IBAN: exact duplicate matching without decryption.
    iban_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bic: Mapped[str | None] = mapped_column(String(11))
    bank_name: Mapped[str | None] = mapped_column(String(200))
    holder: Mapped[str | None] = mapped_column(String(200))
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    # SEPA mandate record on the contact's own bank account (M3-02). Distinct from
    # mhvp.contracts.models.SepaMandate, which ties a mandate to a legal entity and
    # creditor id for actual collection (locked until gate G2); this is bookkeeping of the
    # contact's mandate evidence, no payment function.
    sepa_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    mandate_reference: Mapped[str | None] = mapped_column(String(35))
    mandate_signed_on: Mapped[date | None] = mapped_column(Date)
    mandate_granted_via: Mapped[MandateGrantedVia | None] = mapped_column(
        _enum(MandateGrantedVia, "mandate_granted_via")
    )
    mandate_note: Mapped[str | None] = mapped_column(Text)
    mandate_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    mandate_scheme: Mapped[MandateScheme] = mapped_column(
        _enum(MandateScheme, "contact_mandate_scheme"),
        nullable=False,
        default=MandateScheme.CORE,
        server_default="core",
    )
    mandate_status: Mapped[ContactMandateStatus] = mapped_column(
        _enum(ContactMandateStatus, "contact_mandate_status"),
        nullable=False,
        default=ContactMandateStatus.ACTIVE,
        server_default="active",
    )
    mandate_revoked_on: Mapped[date | None] = mapped_column(Date)
    # Four eyes release (M5-01): a new or changed IBAN stays pending until a second person
    # with contacts:approve releases it; only approved accounts feed mandates and payments.
    approval_status: Mapped[BankAccountApproval] = mapped_column(
        _enum(BankAccountApproval, "bank_account_approval_status"),
        nullable=False,
        default=BankAccountApproval.PENDING,
        server_default="pending",
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Reason given by the second person on rejection (migration 0132); None when approved.
    rejected_reason: Mapped[str | None] = mapped_column(String(500))
    # IBAN change from the CRM screen (migration 0225): the new IBAN is a new row that points
    # to the account it replaces; on release the old row gets ``valid_to`` and, if it was the
    # default account, hands the default over. IBAN history is never overwritten.
    replaces_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact_bank_account.id", ondelete="SET NULL")
    )


class BankAccountChangeKind(StrEnum):
    """Pending changes on an existing bank account that keep the row (migration 0225).
    An IBAN change is not a change kind: it is a new row with ``replaces_account_id``."""

    END = "end"


class ContactBankAccountChange(IdMixin, TimestampMixin, TenantMixin, Base):
    """Four eyes change request on an existing contact bank account (CRM screen). Ending an
    account of a legal entity contact, or any ending proposed by a person without
    ``contacts:approve``, waits here until a second person with ``contacts:approve`` confirms
    it; the requester never decides. At most one pending change per account."""

    __tablename__ = "contact_bank_account_change"
    __table_args__ = (
        Index(
            "ux_contact_bank_account_change_pending",
            "bank_account_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    bank_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contact_bank_account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[BankAccountChangeKind] = mapped_column(
        _enum(BankAccountChangeKind, "contact_bank_account_change_kind"), nullable=False
    )
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[BankAccountApproval] = mapped_column(
        _enum(BankAccountApproval, "bank_account_approval_status"),
        nullable=False,
        default=BankAccountApproval.PENDING,
        server_default="pending",
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_reason: Mapped[str | None] = mapped_column(String(500))


class ContactType(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "contact_type"
    __table_args__ = (UniqueConstraint("tenant_id", "contact_id", "type"),)

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    type: Mapped[ContactTypeCode] = mapped_column(
        _enum(ContactTypeCode, "contact_type_code"), nullable=False
    )
    # manual or derived (from contracts and relations, from M4/M5)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")


class ContactTag(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "contact_tag"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    name: Mapped[str] = mapped_column(String(63), nullable=False)


class ContactTagLink(IdMixin, TenantMixin, Base):
    __tablename__ = "contact_tag_link"
    __table_args__ = (UniqueConstraint("tenant_id", "contact_id", "tag_id"),)

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact_tag.id", ondelete="CASCADE"), nullable=False
    )


class ContactNote(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "contact_note"

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    category: Mapped[str | None] = mapped_column(String(63))
    title: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    follow_up_on: Mapped[date | None] = mapped_column(Date)


class ContactRelation(IdMixin, TimestampMixin, TenantMixin, Base):
    """Directed relation ``contact_id`` -> ``related_contact_id`` (for ``representative``:
    the represented contact -> its authorised representative)."""

    __tablename__ = "contact_relation"
    __table_args__ = (
        CheckConstraint(
            "delivery_mode IN ('both', 'representative_only', 'owner_only')",
            name="ck_contact_relation_delivery_mode",
        ),
        # AM02 / GAJ-604 (migration 0449).
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="period_order",
        ),
    )

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    related_contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[RelationKind] = mapped_column(_enum(RelationKind, "relation_kind"), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    # Only meaningful for kind ``representative``; other kinds keep the default ``both``
    # (migration 0140). Read by ``mhvp.contacts.recipients``.
    delivery_mode: Mapped[DeliveryMode] = mapped_column(
        String(20), nullable=False, default=DeliveryMode.BOTH, server_default="both"
    )


class Party(IdMixin, TimestampMixin, TenantMixin, Base):
    """Contract party or household; contracts reference parties, never contacts (6.1)."""

    __tablename__ = "party"

    name: Mapped[str] = mapped_column(String(400), nullable=False)


class PartyMember(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "party_member"
    __table_args__ = (UniqueConstraint("tenant_id", "party_id", "contact_id"),)

    party_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("party.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contact.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    role: Mapped[PartyRole] = mapped_column(_enum(PartyRole, "party_role"), nullable=False)
    share_percent: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))


class Consent(IdMixin, TimestampMixin, TenantMixin, Base):
    """Consent of a contact per purpose. AE34: ``record_type`` ``objection`` records an
    objection to a processing based on legitimate interest (same lifecycle, never counts as
    a consent); a portal terms acceptance keeps the accepted version and a keyed hash of the
    client address as evidence (``text_version``, ``ip_hash``, never the clear address)."""

    __tablename__ = "consent"
    __table_args__ = (
        CheckConstraint("record_type IN ('consent', 'objection')", name="record_type"),
    )

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    kind: Mapped[ConsentKind] = mapped_column(_enum(ConsentKind, "consent_kind"), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    record_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="consent", server_default="consent"
    )
    text_version: Mapped[str | None] = mapped_column(String(60))
    ip_hash: Mapped[str | None] = mapped_column(String(64))

    @property
    def client_evidence_recorded(self) -> bool:
        return self.ip_hash is not None


class ContactMerge(IdMixin, TimestampMixin, TenantMixin, Base):
    """Merge proposal of two contacts with check result, four eyes decision and execution
    record (M3-03, rule M3-03-kontakt-merge). The source row is never deleted."""

    __tablename__ = "contact_merge"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'executed', 'rejected')", name="ck_contact_merge_status"
        ),
        CheckConstraint("source_id <> target_id", name="ck_contact_merge_distinct"),
        Index("ix_contact_merge_tenant_status", "tenant_id", "status"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="RESTRICT"), nullable=False
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="proposed", server_default="proposed"
    )
    reason: Mapped[str | None] = mapped_column(String(1000))
    check_result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    proposed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(String(1000))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class ContactAccessExportSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """One row per tenant: scope of the data subject access export (AE33, AC07-01).

    Both switches are conservative by default: other persons appear with their role only and
    internal notes are withheld. Which variant is lawful is an open legal question
    (OPEN_QUESTIONS AC07-01); the values are frozen into each prepared export."""

    __tablename__ = "contact_access_export_setting"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_contact_access_export_setting_tenant_id"),
        CheckConstraint("third_party_scope IN ('none', 'names')", name="third_party_scope_values"),
    )

    third_party_scope: Mapped[str] = mapped_column(
        String(16), nullable=False, default="none", server_default="none"
    )
    include_internal_notes: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


# AN05 (GAJ-610): closed addresses of the history stay in contact_address but every ordinary
# ORM select only sees the current rows, so letters, exports and matching never pick a former
# address. The history reader opts out with the execution option below. Bulk DELETE and
# UPDATE (erasure, merge) are not filtered and therefore cover the history as well.
ADDRESS_HISTORY_OPTION = "contact_address_history"


def _hide_closed_addresses(state: ORMExecuteState) -> None:
    if not state.is_select or state.execution_options.get(ADDRESS_HISTORY_OPTION):
        return
    state.statement = state.statement.options(
        with_loader_criteria(
            ContactAddress, lambda cls: cls.superseded_at.is_(None), include_aliases=True
        )
    )


event.listen(Session, "do_orm_execute", _hide_closed_addresses)
