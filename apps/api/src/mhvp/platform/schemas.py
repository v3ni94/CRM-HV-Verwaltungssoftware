"""API schemas for platform and tenant administration."""

import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


class CompanyData(BaseModel):
    """Company master data and mandatory business letter details (5.2). Unknown: None."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    legal_form: str | None = None
    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = "DE"
    register_court: str | None = None
    register_number: str | None = None
    management: list[str] = Field(default_factory=list)
    management_title: str | None = None
    vat_id: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    website: str | None = None


class BandSegment(BaseModel):
    """Segment of the letterhead colour band as share of the page width (M6)."""

    model_config = ConfigDict(extra="forbid")

    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    from_: float = Field(alias="from", ge=0, le=1)
    to: float = Field(ge=0, le=1)


class Branding(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    primary_color: str | None = None
    secondary_color: str | None = None
    accent_color: str | None = None
    text_color: str | None = None
    muted_color: str | None = None
    surface_color: str | None = None
    font_family: str | None = None
    logo_light_document_id: uuid.UUID | None = None
    logo_dark_document_id: uuid.UUID | None = None
    letter_band: list[BandSegment] | None = Field(default=None, max_length=8)

    @field_validator(
        "primary_color",
        "secondary_color",
        "accent_color",
        "text_color",
        "muted_color",
        "surface_color",
    )
    @classmethod
    def _hex(cls, value: str | None) -> str | None:
        if value is not None and not _HEX.fullmatch(value):
            raise ValueError("colour must be #RRGGBB")
        return value.upper() if value else value


class TenantSettingsOut(BaseModel):
    tenant_id: uuid.UUID
    company: CompanyData
    branding: Branding
    sources: dict[str, str]
    auto_posting_enabled: bool
    # M20-03 Notbremse: alle Ticketantworten mit Freigabe durch eine zweite Person (Standard aus).
    ticket_reply_approval_all: bool = False
    version: int


class TenantSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: CompanyData | None = None
    branding: Branding | None = None
    ticket_reply_approval_all: bool | None = None


def _mask(value: str | None) -> str | None:
    if not value:
        return None
    return f"…{value[-4:]}" if len(value) > 4 else "…" + value


class TenantBillingSettingsOut(BaseModel):
    """Secrets are write only: vat_id and tax_number are returned masked (last 4 chars)."""

    tenant_id: uuid.UUID
    invoice_prefix: str | None
    vat_status: str
    vat_id_masked: str | None
    tax_number_masked: str | None
    leitweg_id: str | None
    payee_iban_masked: str | None
    kleinunternehmer_note: str | None
    datev_consultant_number: str | None
    datev_client_number: str | None
    datev_chart_of_accounts: str
    datev_account_length: int | None
    datev_fiscal_year_start_month: int
    version: int


class TenantBillingSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_prefix: str | None = Field(default=None, min_length=1, max_length=16)
    vat_status: Literal["unset", "regelbesteuert", "kleinunternehmer"] | None = None
    vat_id: str | None = Field(default=None, max_length=32)
    tax_number: str | None = Field(default=None, max_length=32)
    leitweg_id: str | None = Field(default=None, max_length=64)
    payee_iban: str | None = Field(default=None, max_length=34)
    kleinunternehmer_note: str | None = Field(default=None, max_length=2000)

    @field_validator("payee_iban")
    @classmethod
    def _payee_iban(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        from mhvp.contacts.validation import InvalidValueError, normalise_iban

        try:
            return normalise_iban(value)
        except InvalidValueError as exc:
            raise ValueError(str(exc)) from None

    datev_consultant_number: str | None = Field(default=None, max_length=32)
    datev_client_number: str | None = Field(default=None, max_length=32)
    datev_chart_of_accounts: Literal["unset", "skr03", "skr04"] | None = None
    datev_account_length: int | None = Field(default=None, ge=4, le=8)
    datev_fiscal_year_start_month: int | None = Field(default=None, ge=1, le=12)

    @field_validator("invoice_prefix")
    @classmethod
    def _prefix(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[A-Z0-9]{2,16}", value):
            raise ValueError("invoice_prefix must be 2-16 uppercase letters or digits")
        return value


class BrandingOut(BaseModel):
    tenant_id: uuid.UUID
    name: str
    branding: Branding


class TenantCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    name: str = Field(min_length=2, max_length=200)


class TenantOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    status: str


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=1, max_length=256)
    is_platform_admin: bool = False


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_platform_admin: bool
    totp_enabled: bool


class MemberCreate(BaseModel):
    user_id: uuid.UUID
    role_codes: list[str] = Field(min_length=1)


class MemberOut(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    display_name: str
    status: str
    roles: list[str]
    competences: list[str] = Field(default_factory=list)
    contact_id: uuid.UUID | None = None
    last_login_at: datetime | None = None
    mobile_phone: str | None = None
    portal_access: str | None = None
    portal_access_reason: str | None = None
    # M20-03: Ticketantworten dieses Mitglieds brauchen die Freigabe einer zweiten Person.
    reply_approval_required: bool = False
    reply_approval_reason: str | None = None
    reply_approval_until: date | None = None
    # A37: legal entity scope (only effective for scoped roles, see mhvp.core.auth.scope).
    legal_entity_ids: list[uuid.UUID] = Field(default_factory=list)


class MemberLegalEntities(BaseModel):
    """Zugriffsbereich je Rechtsträger (A37, docs/rules/M18-05-steuerberaterzugang.md). Nur für
    Rollen mit eingeschränktem Bereich (Steuerberater) wirksam; leere Liste bedeutet dort kein
    Zugriff."""

    legal_entity_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


class LegalEntityOption(BaseModel):
    """Rechtsträger des Mandanten zur Auswahl in der Mitarbeiterverwaltung (A37)."""

    id: uuid.UUID
    name: str
    kind: str
    property_id: uuid.UUID | None = None


class MemberMobilePhone(BaseModel):
    """Mobilnummer für SMS-Eskalationen an die Bereitschaft (M35); ``None`` löscht sie."""

    mobile_phone: str | None = Field(
        default=None, min_length=3, max_length=40, pattern=r"^\+?[0-9 ()/-]+$"
    )


class MemberReplyApproval(BaseModel):
    """M20-03 Kennzeichen je Mitglied (Betreiberentscheidung 26.09.2026): Ticketantworten
    brauchen die Freigabe einer zweiten Person. ``reason`` ist bei ``required`` Pflicht;
    ``until`` (einschließlich) befristet das Kennzeichen, danach gilt es nicht mehr."""

    model_config = ConfigDict(extra="forbid")

    required: bool
    reason: Literal["azubi", "neuer_mitarbeiter"] | None = None
    until: date | None = None

    @model_validator(mode="after")
    def _reason_when_required(self) -> "MemberReplyApproval":
        if self.required and self.reason is None:
            raise ValueError("Grund ist bei gesetztem Kennzeichen erforderlich.")
        if not self.required:
            self.reason, self.until = None, None
        return self


class MemberCompetences(BaseModel):
    """Kompetenzcodes des Mitglieds (operator 25.09.2026). Werden gegen den Katalog
    (``mhvp.tickets.competences``, ggf. um die Mandantenerweiterung) geprüft."""

    competence_codes: list[str] = Field(default_factory=list, max_length=64)


class MemberInvite(BaseModel):
    """Tenant administrators add a user: the account is created when the e-mail is new,
    otherwise the existing account joins the tenant. A contact record is created as well."""

    email: EmailStr
    display_name: str = Field(min_length=2, max_length=200)
    password: str | None = Field(
        default=None, max_length=256, description="Startpasswort, nur für neue Konten"
    )
    role_codes: list[str] = Field(min_length=1)


class MemberStatusIn(BaseModel):
    status: Literal["active", "disabled"]


class PasswordResetIn(BaseModel):
    password: str = Field(min_length=1, max_length=256, description="Neues Startpasswort")


class MemberRoles(BaseModel):
    role_codes: list[str]


class RoleCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,62}$")
    name: str = Field(min_length=2, max_length=200)
    parent_role_id: uuid.UUID | None = None
    permissions: list[str] = Field(default_factory=list)


class RoleOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    is_system: bool
    parent_role_id: uuid.UUID | None
    permissions: list[str]


class RolePermissions(BaseModel):
    permissions: list[str]


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    scopes: list[str] = Field(min_length=1)
    expires_at: datetime | None = None


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(description="Wird nur einmal angezeigt")


class WebhookCreate(BaseModel):
    url: str = Field(max_length=2000)
    event_types: list[str] = Field(min_length=1)
    description: str | None = Field(default=None, max_length=200)


class WebhookPatch(BaseModel):
    active: bool | None = None
    event_types: list[str] | None = None


class WebhookOut(BaseModel):
    id: uuid.UUID
    url: str
    event_types: list[str]
    active: bool
    description: str | None
    created_at: datetime | None = None
    # Latest delivery of the subscription (CRM settings page): status, response code and
    # time of the last attempt; None while nothing has been delivered yet.
    last_delivery_status: str | None = None
    last_delivery_status_code: int | None = None
    last_delivery_at: datetime | None = None


class WebhookEventTypeOut(BaseModel):
    type: str
    description: str


class WebhookCreated(WebhookOut):
    secret: str = Field(description="Signaturschlüssel, wird nur einmal angezeigt")


class DeliveryOut(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    status: str
    attempts: int
    next_attempt_at: datetime | None
    last_status_code: int | None
    last_error: str | None
    delivered_at: datetime | None


class EventOut(BaseModel):
    id: uuid.UUID
    type: str
    entity_type: str
    entity_id: uuid.UUID | None
    payload: dict[str, object]
    actor_user_id: uuid.UUID | None
    occurred_at: datetime
    correlation_id: str | None


class AuditOut(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID | None
    changes: dict[str, object]
    actor_user_id: uuid.UUID | None
    occurred_at: datetime


class GateRequestCreate(BaseModel):
    gate: str = Field(pattern=r"^G[1-5]$")
    scope: str = Field(
        min_length=10, max_length=2000, description="Freigegebener Funktionsumfang und Objektgruppe"
    )
    evidence: str = Field(min_length=5, max_length=2000, description="Verweis auf Prüfnachweis")


class GateDecision(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class GateRequestOut(BaseModel):
    id: uuid.UUID
    gate: str
    scope: str
    evidence: str
    status: str
    requested_by: uuid.UUID
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_comment: str | None


class GateStateOut(BaseModel):
    gate: str
    label: str
    open: bool
    scopes: list[str]
