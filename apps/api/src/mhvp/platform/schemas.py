"""API schemas for platform and tenant administration."""

import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from mhvp.tickets.resolution_kinds import ResolutionKindsConfig

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
    # B26/M21-04: Portal white label. Empty means neutral portal; nothing is invented.
    portal_name: str | None = Field(default=None, max_length=80)
    imprint_url: str | None = Field(default=None, max_length=500, pattern=r"^https://")
    privacy_url: str | None = Field(default=None, max_length=500, pattern=r"^https://")
    # GAI-109: apply colours in the CRM at runtime (tenant switch, default off).
    crm_apply: bool | None = None

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


class ReceivableRulesConfig(BaseModel):
    """M13-01 to M13-03 (docs/rules/M13-01.md to M13-03.md): receivable rules per tenant.
    Default off; the tax adviser review of the rules is open, so nothing is posted by
    assumption. ``proration_method`` is the tenant default for contracts without own rule."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    proration_method: Literal["calendar_days", "thirty_360", "full_month"] = "calendar_days"
    vat_enabled: bool = False
    # M13-01a (docs/OPEN_QUESTIONS.md): Mandanten-Standard für die Zahlweise
    # (``mhvp.contracts.models.PaymentInterval``), den ein neuer Vertrag übernimmt, solange der
    # Zahlungsplan keine eigene Angabe erhält (``ScheduleIn.interval is None``). ``None`` heißt
    # weiterhin monatlich (bisheriges Verhalten ohne Mandantenvorgabe).
    payment_interval: Literal["monthly", "quarterly", "semiannual", "annual"] | None = None
    # P02-03 / S15-01: monthly receivable preview job (``mhvp.accounting.tasks``), drafts
    # only, default off.
    monthly_preview_enabled: bool = False


class SignatureTemplate(BaseModel):
    """E-Mail-Signaturvorlage des Mandanten (operator 27.09.2026). Platzhalter ``{name}``,
    ``{position}``, ``{phone}``, ``{mobile}``, ``{email}``, ``{company}``, ``{street}``,
    ``{postal_code}``, ``{city}``, ``{register}``, ``{website}``. ``None`` bedeutet Standard
    aus den Firmendaten (``mhvp.communication.signatures``)."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=4000)
    html: str | None = Field(default=None, max_length=20000)
    # Öffentlich erreichbare Logo-URL für die HTML-Signatur (höchstens 180 px breit gerendert).
    logo_url: str | None = Field(default=None, max_length=500, pattern=r"^https://")


class TenantSettingsOut(BaseModel):
    tenant_id: uuid.UUID
    company: CompanyData
    branding: Branding
    sources: dict[str, str]
    auto_posting_enabled: bool
    # M20-03 Notbremse: alle Ticketantworten mit Freigabe durch eine zweite Person (Standard aus).
    ticket_reply_approval_all: bool = False
    # Regel M19-10: Wiedereröffnung per Mail nur bis so viele Kalendertage nach dem Abschluss,
    # danach Folgeticket (Standard 30, 0 bedeutet immer Folgeticket).
    ticket_reopen_window_days: int = 30
    # B20: Portal zweiter Faktor, ``account_choice`` (Standard) oder ``required``.
    portal_second_factor: str = "account_choice"
    # P08-04, M25-07: Standardfrist der Bereitstellung von Einsichtspaketen in Tagen,
    # None ohne Ablauf.
    inspection_package_default_days: int | None = None
    # T01-01: Aufbewahrung der Mandantenexport-Archive in Tagen, leer = keine automatische Löschung.
    export_retention_days: int | None = None
    # ADR 0010, M7-04: Lernbeispiele aus Ticketabschlüssen speichern (Standard aus).
    ai_learning_examples_enabled: bool = False
    # ADR 0010 Nachtrag 27.09.2026: Aufbewahrung der Lernbeispiele in Monaten (Standard 24).
    ai_learning_examples_retention_months: int = 24
    # ADR 0014, M12-04: Entscheidungsprotokoll des lernenden Buchhalters (Standard aus, nur
    # lesend hier; Änderung über ``PUT /banking/learning`` mit Grund und Ereignis).
    learning_bookkeeper_enabled: bool = False
    # Lern-Workflow (rule M9-11): consistent manual decisions before a rule is proposed.
    rule_proposal_threshold: int = 5
    # Lernende Bankregeln (Regel M12-06): Schwellen für Regelvorschläge aus Buchungen.
    bank_rule_proposal_threshold: int = 5
    bank_rule_recurring_threshold: int = 3
    # Automatikstufen je Fallklasse (Regel M12-05, nur lesend; Änderung über
    # ``/banking/automation``) und der Schalter der Ausgangsautomatik (M12-05 offen).
    bookkeeping_automation: dict[str, str] = Field(default_factory=dict)
    auto_posting_outgoing_enabled: bool = False
    # Messdienstleister module switch (default off).
    metering_module_enabled: bool = False
    # Offline Erfassung des Übergabeprotokolls (rule M30-10, ADR 0016, default off).
    handover_offline_enabled: bool = False
    # Rule H03: Verbrauchsinformation monthly job, notifications and template verification
    # (all default off; tenants see nothing until the template is verified).
    consumption_info_enabled: bool = False
    consumption_info_notifications_enabled: bool = False
    consumption_info_template_verified: bool = False
    # Regel M19-07, M19-04: deaktivierte eingebaute und eigene Erledigungsarten.
    resolution_kinds: ResolutionKindsConfig = Field(default_factory=ResolutionKindsConfig)
    # M20-04 Vier-Augen-Prinzip beim Mailversand: all, external_only (Standard) oder off.
    mail_approval_mode: str = "external_only"
    # M13-01 to M13-03: Sollstellungsregeln je Mandant (Standard aus).
    receivable_rules: ReceivableRulesConfig = Field(default_factory=ReceivableRulesConfig)
    # E-Mail-Signatur (operator 27.09.2026): Vorlage und manuell angelegte Positionen.
    signature_template: SignatureTemplate = Field(default_factory=SignatureTemplate)
    position_catalogue_extra: list[str] = Field(default_factory=list)
    # Rückkanal Gmail zu Plattform (rule M20-08): mode off, record_only (Standard) or done
    # and its guards; ``gmail_spike_confirmed_at`` is set by the spike confirmation.
    gmail_done_sync_mode: str = "record_only"
    # U15-04: Inhaltsmodus der Benachrichtigungsmails, ``voll`` (Standard) oder ``hinweis``
    # (nur Anzahl und Link ins CRM). Gespeichert im JSON ``sources``, keine Migration.
    notification_mail_content: str = "voll"
    # GAC-07: Versicherungsmakler erhält insurance:read und claims:read nur bei gesetztem
    # Schalter (Standard aus, gespeichert im JSON ``sources``, keine Migration).
    insurance_broker_access: bool = False
    gmail_done_closes_ticket: bool = False
    gmail_done_on_trash: bool = True
    gmail_reopen_on_unarchive: bool = True
    gmail_restore_inbox_on_reopen: bool = False
    gmail_settle_seconds: int = 180
    gmail_reconcile_grace_seconds: int = 300
    gmail_keep_open_labels: list[str] = Field(default_factory=list)
    gmail_close_assigned_tickets: bool = False
    gmail_spike_confirmed_at: datetime | None = None
    gmail_spike_protocol_ref: str | None = None
    version: int


# Gmail system labels that never count as work labels (rule M20-08).
GMAIL_SYSTEM_LABELS = frozenset(
    {"INBOX", "TRASH", "SPAM", "UNREAD", "STARRED", "IMPORTANT", "SENT", "DRAFT", "CHAT"}
)


class GmailSpikeConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_ref: str = Field(min_length=1, max_length=500)


class TenantSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gmail_done_sync_mode: str | None = Field(default=None, pattern=r"^(off|record_only|done)$")
    gmail_done_closes_ticket: bool | None = None
    gmail_done_on_trash: bool | None = None
    gmail_reopen_on_unarchive: bool | None = None
    gmail_restore_inbox_on_reopen: bool | None = None
    gmail_settle_seconds: int | None = Field(default=None, ge=0, le=3600)
    gmail_reconcile_grace_seconds: int | None = Field(default=None, ge=60, le=3600)
    gmail_keep_open_labels: list[str] | None = Field(default=None, max_length=20)
    gmail_close_assigned_tickets: bool | None = None

    @field_validator("gmail_keep_open_labels")
    @classmethod
    def _keep_open_labels(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [" ".join(v.split()) for v in value]
        if any(not v or len(v) > 128 for v in cleaned):
            raise ValueError("Jedes Arbeitslabel braucht 1 bis 128 Zeichen.")
        for label in cleaned:
            upper = label.upper()
            if upper in GMAIL_SYSTEM_LABELS or upper.startswith("CATEGORY_"):
                raise ValueError(f"Systemlabel {label} ist kein Arbeitslabel.")
        return cleaned

    company: CompanyData | None = None
    branding: Branding | None = None
    ticket_reply_approval_all: bool | None = None
    notification_mail_content: str | None = Field(default=None, pattern="^(voll|hinweis)$")
    insurance_broker_access: bool | None = None
    ticket_reopen_window_days: int | None = Field(default=None, ge=0, le=3650)
    portal_second_factor: str | None = Field(default=None, pattern="^(account_choice|required)$")
    # P08-04: Standardfrist in Tagen (1 bis 365); mit clear_inspection_package_default_days
    # wird sie geleert (ohne Ablauf).
    inspection_package_default_days: int | None = Field(default=None, ge=1, le=365)
    clear_inspection_package_default_days: bool = False
    # T01-01: Aufbewahrung der Exportarchive in Tagen (1 bis 3650); clear_ leert sie.
    export_retention_days: int | None = Field(default=None, ge=1, le=3650)
    clear_export_retention_days: bool = False
    ai_learning_examples_enabled: bool | None = None
    ai_learning_examples_retention_months: int | None = Field(default=None, ge=1, le=120)
    rule_proposal_threshold: int | None = Field(default=None, ge=2, le=50)
    bank_rule_proposal_threshold: int | None = Field(default=None, ge=2, le=50)
    bank_rule_recurring_threshold: int | None = Field(default=None, ge=2, le=50)
    metering_module_enabled: bool | None = None
    handover_offline_enabled: bool | None = None
    consumption_info_enabled: bool | None = None
    consumption_info_notifications_enabled: bool | None = None
    consumption_info_template_verified: bool | None = None
    resolution_kinds: ResolutionKindsConfig | None = None
    mail_approval_mode: str | None = Field(default=None, pattern="^(all|external_only|off)$")
    receivable_rules: ReceivableRulesConfig | None = None
    signature_template: SignatureTemplate | None = None
    position_catalogue_extra: list[str] | None = Field(default=None, max_length=100)

    @field_validator("position_catalogue_extra")
    @classmethod
    def _positions(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [" ".join(v.split()) for v in value]
        if any(not v or len(v) > 120 for v in cleaned):
            raise ValueError("Positionen müssen 1 bis 120 Zeichen lang sein.")
        return list(dict.fromkeys(cleaned))


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
    # B26/M21-04: PNG or JPEG logo available at ``/tenant/branding/logo/{variant}``.
    has_logo_light: bool = False
    has_logo_dark: bool = False
    # AE29: codes of the approved portal legal texts (impressum, datenschutz, nutzungsbedingungen).
    legal_texts_released: list[str] = Field(default_factory=list)


class TenantCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    name: str = Field(min_length=2, max_length=200)
    # AE36: demo tenant (invented data only, excluded from billing, exports and statistics).
    is_demo: bool = False


class TenantOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    status: str
    is_demo: bool = False


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
    is_superadmin: bool = False
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
    # E-Mail-Signatur (operator 27.09.2026): Position (Freitext, Katalog) und Durchwahl.
    position: str | None = None
    phone: str | None = None
    portal_access: str | None = None
    portal_access_reason: str | None = None
    # M20-03: Ticketantworten dieses Mitglieds brauchen die Freigabe einer zweiten Person.
    reply_approval_required: bool = False
    reply_approval_reason: str | None = None
    reply_approval_until: date | None = None
    # A37: legal entity scope (only effective for scoped roles, see mhvp.core.auth.scope).
    legal_entity_ids: list[uuid.UUID] = Field(default_factory=list)
    # M2-02: Objektzuordnung (leer = alle Objekte, siehe mhvp.core.auth.scope).
    property_ids: list[uuid.UUID] = Field(default_factory=list)


class MemberProperties(BaseModel):
    """Objektzuordnung eines Mitglieds (3.4, M2-02, docs/rules/M2-02-objektzuordnung.md). Leere
    Liste bedeutet keine Einschränkung; Administratorrollen sind nie eingeschränkt."""

    property_ids: list[uuid.UUID] = Field(default_factory=list, max_length=2000)


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


class MemberPosition(BaseModel):
    """Position und Durchwahl für die E-Mail-Signatur (operator 27.09.2026). Die Position ist
    Freitext; Katalogwerte (``mhvp.communication.signatures.POSITION_CATALOGUE`` plus die
    Mandantenliste) sind Vorschläge. ``None`` löscht den jeweiligen Wert."""

    model_config = ConfigDict(extra="forbid")

    position: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(
        default=None, min_length=3, max_length=40, pattern=r"^\+?[0-9 ()/-]+$"
    )

    @field_validator("position")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None


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


def _check_event_types(value: list[str]) -> list[str]:
    from mhvp.core.webhooks import is_known_event_type

    unknown = [t for t in value if not is_known_event_type(t)]
    if unknown:
        raise ValueError(f"unknown event types: {', '.join(unknown)}")
    return value


class WebhookCreate(BaseModel):
    url: str = Field(max_length=2000)
    event_types: list[str] = Field(min_length=1)
    description: str | None = Field(default=None, max_length=200)

    @field_validator("event_types")
    @classmethod
    def _known_types(cls, value: list[str]) -> list[str]:
        return _check_event_types(value)


class WebhookPatch(BaseModel):
    active: bool | None = None
    event_types: list[str] | None = None
    # GAH-207: target and description are editable; the URL passes the same SSRF check.
    url: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=200)

    @field_validator("event_types")
    @classmethod
    def _known_patch_types(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _check_event_types(value)


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
    # GAH-206: consecutive final failures, time of the last one and the reason of an automatic
    # deactivation (``consecutive_failures``), shown as warning on the settings page.
    consecutive_failures: int = 0
    last_failure_at: datetime | None = None
    disabled_reason: str | None = None


class WebhookTestOut(BaseModel):
    delivery_id: uuid.UUID
    event_id: uuid.UUID


class WebhookSettingsOut(BaseModel):
    """GAH-206, GAH-202 tenant switches (questions AI07-01, AI07-02)."""

    auto_disable_after: int | None = None
    objektakte_require_timestamp: bool = False


class WebhookSettingsIn(BaseModel):
    auto_disable_after: int | None = Field(default=None, ge=1, le=100)
    objektakte_require_timestamp: bool | None = None


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
    # GA14-02: structured scope; omitted means all (default).
    scope_property_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)
    scope_legal_entity_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    scope_functions: list[str] | None = Field(default=None, max_length=20)
    # GA14-03/GA14-04: checklist code -> confirmation note, linked evidence document.
    checklist: dict[str, str] | None = Field(default=None, max_length=30)
    evidence_document_id: uuid.UUID | None = None


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
    # False only for an approval by the superadmin without a second person (ADR 0011).
    four_eyes: bool = True
    opened_by: uuid.UUID | None = None
    opened_at: datetime | None = None
    revoked_by: uuid.UUID | None = None
    revoked_at: datetime | None = None
    revoke_comment: str | None = None
    evidence_document_id: uuid.UUID | None = None
    scope_property_ids: list[uuid.UUID] | None = None
    scope_legal_entity_ids: list[uuid.UUID] | None = None
    scope_functions: list[str] | None = None
    checklist: dict[str, str] | None = None
    # GAJ-504: confirmed checklist codes without a checkable evidence reference in the note.
    checklist_unverified: list[str] = []


class GateChecklistItemOut(BaseModel):
    code: str
    label: str


class GateChecklistOut(BaseModel):
    gate: str
    label: str
    items: list[GateChecklistItemOut]
    functions: list[str]
    evidence_document_required: bool


class PlatformSettingsOut(BaseModel):
    """Platform wide switches (ADR 0011); ``gate_superadmin_bypass`` weakens the four eyes
    control of ADR 0003 and stays off until the operator switches it on."""

    gate_superadmin_bypass: bool
    version: int
    updated_by: uuid.UUID | None
    updated_at: datetime


class PlatformSettingsPatch(BaseModel):
    gate_superadmin_bypass: bool | None = None


class SuperadminOut(BaseModel):
    user_id: uuid.UUID | None
    email: str | None


class GateStateOut(BaseModel):
    gate: str
    label: str
    open: bool
    scopes: list[str]
    # GA14-02: approvals restricted to properties, legal entities or functions only.
    partially_open: bool = False


class PlatformGateOverviewOut(BaseModel):
    """GA14-04 (AB02): platform view of one tenant's gates and requests."""

    tenant_id: uuid.UUID
    gates: list[GateStateOut]
    requests: list[GateRequestOut]
