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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

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


class PartyRole(StrEnum):
    PRIMARY = "primary"
    CO_PARTY = "co_party"
    GUARANTOR = "guarantor"
    LEGAL_REPRESENTATIVE = "legal_representative"


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


def _contact_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="CASCADE"), nullable=False, index=True
    )


class ContactAddress(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "contact_address"

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    label: Mapped[AddressLabel] = mapped_column(
        _enum(AddressLabel, "address_label"), nullable=False
    )
    street: Mapped[str | None] = mapped_column(String(200))
    house_number: Mapped[str | None] = mapped_column(String(20))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="DE")
    addition: Mapped[str | None] = mapped_column(String(200))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ContactPhone(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "contact_phone"

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    label: Mapped[PhoneLabel] = mapped_column(_enum(PhoneLabel, "phone_label"), nullable=False)
    number: Mapped[str] = mapped_column(String(32), nullable=False)  # E.164
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ContactEmail(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "contact_email"
    __table_args__ = (Index("ix_contact_email_tenant_id_email", "tenant_id", "email"),)

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
    )

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    label: Mapped[str | None] = mapped_column(String(100))
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
    body: Mapped[str] = mapped_column(Text, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ContactRelation(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "contact_relation"

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    related_contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[RelationKind] = mapped_column(_enum(RelationKind, "relation_kind"), nullable=False)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


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
    __tablename__ = "consent"

    contact_id: Mapped[uuid.UUID] = _contact_fk()
    kind: Mapped[ConsentKind] = mapped_column(_enum(ConsentKind, "consent_kind"), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
