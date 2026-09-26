"""API schemas for contacts (section 6.1)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from mhvp.contacts.models import (
    AddressLabel,
    BankAccountApproval,
    Completeness,
    ConsentKind,
    ContactKind,
    ContactMandateStatus,
    ContactRoleCode,
    ContactTypeCode,
    IdentifierKind,
    MandateGrantedVia,
    MandateScheme,
    PartyRole,
    PhoneLabel,
    PreferredChannel,
    RelationKind,
)
from mhvp.contacts.validation import InvalidValueError, normalise_iban, normalise_phone


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AddressIn(_Strict):
    label: AddressLabel = AddressLabel.POSTAL
    street: str | None = Field(default=None, max_length=200)
    house_number: str | None = Field(default=None, max_length=20)
    postal_code: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=100)
    country: str = Field(default="DE", pattern=r"^[A-Z]{2}$")
    addition: str | None = Field(default=None, max_length=200)
    is_primary: bool = False


class PhoneIn(_Strict):
    label: PhoneLabel = PhoneLabel.WORK
    number: str = Field(max_length=40)
    is_primary: bool = False

    @field_validator("number")
    @classmethod
    def _e164(cls, value: str) -> str:
        try:
            return normalise_phone(value)
        except InvalidValueError as exc:
            raise ValueError(str(exc)) from None


class EmailIn(_Strict):
    label: str = Field(default="work", max_length=32)
    email: EmailStr
    is_primary: bool = False
    is_portal_login: bool = False

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.lower()


class IdentifierIn(_Strict):
    kind: IdentifierKind
    value: str = Field(min_length=1, max_length=100)


class BankAccountIn(_Strict):
    label: str | None = Field(default=None, max_length=100)
    iban: str = Field(max_length=50)
    bic: str | None = Field(default=None, pattern=r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")
    bank_name: str | None = Field(default=None, max_length=200)
    holder: str | None = Field(default=None, max_length=200)
    valid_from: date
    valid_to: date | None = None
    sepa_enabled: bool = False
    mandate_reference: str | None = Field(default=None, max_length=35)
    mandate_signed_on: date | None = None
    mandate_granted_via: MandateGrantedVia | None = None
    mandate_note: str | None = Field(default=None, max_length=2_000)
    mandate_document_id: uuid.UUID | None = None
    mandate_scheme: MandateScheme = MandateScheme.CORE
    mandate_status: ContactMandateStatus = ContactMandateStatus.ACTIVE
    mandate_revoked_on: date | None = None

    @field_validator("iban")
    @classmethod
    def _iban(cls, value: str) -> str:
        try:
            return normalise_iban(value)
        except InvalidValueError as exc:
            raise ValueError(str(exc)) from None

    @model_validator(mode="after")
    def _period(self) -> Self:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to liegt vor valid_from")
        return self

    @model_validator(mode="after")
    def _mandate(self) -> Self:
        if self.sepa_enabled:
            if self.mandate_signed_on is None:
                raise ValueError("SEPA-Mandat benötigt ein Unterschriftsdatum")
            if self.mandate_granted_via is None:
                raise ValueError("SEPA-Mandat benötigt die Art der Erteilung")
            if self.mandate_document_id is None and not (self.mandate_note or "").strip():
                raise ValueError("SEPA-Mandat benötigt ein Dokument oder einen Vermerk")
        return self


class ContactIn(_Strict):
    kind: ContactKind
    salutation: str | None = Field(default=None, max_length=50)
    title: str | None = Field(default=None, max_length=50)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    company_name: str | None = Field(default=None, max_length=200)
    legal_form: str | None = Field(default=None, max_length=50)
    position: str | None = Field(default=None, max_length=100)
    date_of_birth: date | None = None
    language: str = Field(default="de", pattern=r"^[a-z]{2}$")
    notes: str | None = Field(default=None, max_length=10_000)
    preferred_channel: PreferredChannel | None = None
    blocked: bool = False
    external_ids: dict[str, str] = Field(default_factory=dict)
    completeness: Completeness = Completeness.COMPLETE
    addresses: list[AddressIn] = Field(default_factory=list, max_length=20)
    phones: list[PhoneIn] = Field(default_factory=list, max_length=20)
    emails: list[EmailIn] = Field(default_factory=list, max_length=20)
    identifiers: list[IdentifierIn] = Field(default_factory=list, max_length=20)
    bank_accounts: list[BankAccountIn] | None = Field(
        default=None,
        max_length=20,
        description="Beim Ändern: weglassen oder null lässt die Bankverbindungen unverändert",
    )
    types: list[ContactTypeCode] = Field(default_factory=list)
    roles: list[ContactRoleCode] = Field(
        default_factory=list,
        description="Manuelle Klassifizierung; automatisch abgeleitete Rollen aus Verträgen "
        "werden zusätzlich beibehalten.",
    )
    tags: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _names(self) -> Self:
        if self.kind is ContactKind.PERSON and not (self.last_name or self.first_name):
            raise ValueError("Personen benötigen Vor- oder Nachname")
        if self.kind is ContactKind.COMPANY and not self.company_name:
            raise ValueError("Firmen benötigen einen Firmennamen")
        return self


class AddressOut(AddressIn):
    id: uuid.UUID


class PhoneOut(BaseModel):
    id: uuid.UUID
    label: PhoneLabel
    number: str
    is_primary: bool


class EmailOut(BaseModel):
    id: uuid.UUID
    label: str
    email: str
    is_primary: bool
    is_portal_login: bool


class IdentifierOut(IdentifierIn):
    id: uuid.UUID


class BankAccountOut(BaseModel):
    id: uuid.UUID
    label: str | None
    iban_masked: str
    bic: str | None
    bank_name: str | None
    holder: str | None
    valid_from: date
    valid_to: date | None
    sepa_enabled: bool
    mandate_reference: str | None
    mandate_signed_on: date | None
    mandate_granted_via: MandateGrantedVia | None
    mandate_note: str | None
    mandate_document_id: uuid.UUID | None
    mandate_scheme: MandateScheme
    mandate_status: ContactMandateStatus
    mandate_revoked_on: date | None
    approval_status: BankAccountApproval = Field(
        description="Vier-Augen-Freigabe der IBAN (M5-01): nur approved wird verwendet."
    )
    requested_by: uuid.UUID | None = None
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None


class BankAccountDecisionIn(_Strict):
    reason: str | None = Field(default=None, max_length=500)


class SepaMandateOut(BaseModel):
    """Compact list for GET /contacts/{id}/sepa-mandates."""

    bank_account_id: uuid.UUID
    iban_masked: str
    mandate_reference: str | None
    mandate_signed_on: date | None
    mandate_scheme: MandateScheme
    mandate_status: ContactMandateStatus
    mandate_revoked_on: date | None


class ContactName(BaseModel):
    """Minimal view for previews (ticket merge): only the display name, no contact details."""

    id: uuid.UUID
    display_name: str


class ContactSummary(BaseModel):
    id: uuid.UUID
    kind: ContactKind
    display_name: str
    primary_email: str | None
    primary_phone: str | None
    city: str | None
    completeness: Completeness
    blocked: bool
    tags: list[str]
    types: list[ContactTypeCode]
    roles: list[ContactRoleCode]
    deleted: bool


class ContactOut(BaseModel):
    id: uuid.UUID
    kind: ContactKind
    display_name: str
    salutation: str | None
    title: str | None
    first_name: str | None
    last_name: str | None
    company_name: str | None
    legal_form: str | None
    position: str | None
    date_of_birth: date | None
    language: str
    notes: str | None
    preferred_channel: PreferredChannel | None
    blocked: bool
    external_ids: dict[str, str]
    completeness: Completeness
    addresses: list[AddressOut]
    phones: list[PhoneOut]
    emails: list[EmailOut]
    identifiers: list[IdentifierOut]
    bank_accounts: list[BankAccountOut]
    types: list[ContactTypeCode]
    roles: list[ContactRoleCode]
    tags: list[str]
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class ContactPage(BaseModel):
    items: list[ContactSummary]
    total: int
    page: int
    page_size: int


class DuplicateQuery(_Strict):
    kind: ContactKind | None = None
    first_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    email: str | None = None
    phone: str | None = None
    iban: str | None = None


class DuplicateCandidate(BaseModel):
    contact: ContactSummary
    score: float = Field(ge=0, le=1)
    reasons: list[str]


class NoteIn(_Strict):
    category: str | None = Field(default=None, max_length=63)
    body: str = Field(min_length=1, max_length=20_000)
    pinned: bool = False


class NoteOut(NoteIn):
    id: uuid.UUID
    created_at: datetime
    created_by: uuid.UUID | None


class RelationIn(_Strict):
    related_contact_id: uuid.UUID
    kind: RelationKind
    valid_from: date | None = None
    valid_to: date | None = None


class RelationOut(RelationIn):
    id: uuid.UUID


class ConsentIn(_Strict):
    kind: ConsentKind
    granted_at: datetime
    source: str = Field(min_length=2, max_length=200)
    document_id: uuid.UUID | None = None


class ConsentOut(ConsentIn):
    id: uuid.UUID
    revoked_at: datetime | None


class PartyMemberIn(_Strict):
    contact_id: uuid.UUID
    role: PartyRole = PartyRole.PRIMARY
    share_percent: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=20, decimal_places=8
    )


class PartyIn(_Strict):
    name: str | None = Field(default=None, max_length=400, description="Leer: wird generiert")
    members: list[PartyMemberIn] = Field(min_length=1, max_length=20)


class PartyMemberOut(PartyMemberIn):
    display_name: str


class PartyOut(BaseModel):
    id: uuid.UUID
    name: str
    members: list[PartyMemberOut]


class SearchHit(BaseModel):
    entity_type: str
    id: uuid.UUID
    title: str
    subtitle: str | None
    score: float


class ObjectRelationOut(BaseModel):
    """Object or unit reference of a contact (tenancy, ownership, property contact)."""

    kind: Literal["mieter", "eigentuemer", "kontakt"]
    property_id: uuid.UUID
    property_name: str
    property_city: str | None = None
    unit_id: uuid.UUID | None = None
    unit_label: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    active: bool
    source: Literal["contract", "property_owner", "property_contact"]
    contract_id: uuid.UUID | None = None
    category_code: str | None = None


class RecomputeRolesOut(BaseModel):
    changed: int
