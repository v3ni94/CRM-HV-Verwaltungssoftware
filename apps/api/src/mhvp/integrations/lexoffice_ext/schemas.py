"""Request and response schemas of the Lexware Office extension. Secrets never appear in a
response (``api_key_set`` and ``api_key_last4`` only)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from datetime import date as dt_date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LexofficeOrganisationIn(_In):
    legal_entity_id: uuid.UUID | None = None
    label: str | None = Field(default=None, max_length=120)
    api_key: str | None = Field(default=None, min_length=1, max_length=500)
    clear_api_key: bool = False
    base_url: str | None = Field(default=None, max_length=300)
    mailbox_id: uuid.UUID | None = None
    clear_mailbox: bool = False
    avv_confirmed_on: date | None = None
    avv_note: str | None = Field(default=None, max_length=500)
    enabled: bool = False
    sync_contacts: bool = False
    sync_names: bool = False
    invoice_copies: bool = False
    invoice_drafts: bool = False


class LexofficeOrganisationOut(BaseModel):
    id: uuid.UUID
    legal_entity_id: uuid.UUID | None
    legal_entity_name: str | None
    label: str | None
    base_url: str
    app_base_url: str
    enabled: bool
    api_key_set: bool
    api_key_last4: str | None
    token_invalid: bool
    organization_id: str | None
    organization_name: str | None
    profile_tax_type: str | None
    profile_small_business: bool | None
    profile_business_features: list[str]
    has_invoicing: bool
    avv_confirmed_on: date | None
    avv_confirmed_by: uuid.UUID | None
    avv_note: str | None
    mailbox_id: uuid.UUID | None
    sync_contacts: bool
    sync_names: bool
    invoice_copies: bool
    invoice_drafts: bool
    last_tested_at: datetime | None
    last_test_ok: bool | None
    last_test_message: str | None
    message: str | None = None


class LexofficeLegalEntityOut(BaseModel):
    id: uuid.UUID
    kind: str
    name: str


class LexofficeInvoiceKindMappingIn(_In):
    kind: Literal["broker", "consulting", "management"]
    legal_entity_id: uuid.UUID | None


class LexofficeInvoiceKindMappingOut(BaseModel):
    kind: str
    label: str
    legal_entity_id: uuid.UUID | None
    legal_entity_name: str | None
    config_id: uuid.UUID | None


class LexofficeRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    status: str
    counts: dict[str, int]
    errors: list[str]
    created_at: datetime
    finished_at: datetime | None


class LexofficeOutboxOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    config_id: uuid.UUID
    kind: str
    target_kind: str
    target_id: uuid.UUID
    status: str
    attempts: int
    next_attempt_at: datetime
    last_status_code: int | None
    last_error: str | None
    detail: dict[str, Any]
    sent_at: datetime | None
    created_at: datetime


class LexofficePage(BaseModel):
    items: list[Any]
    total: int
    page: int
    size: int


class LexofficeMatchIn(_In):
    scope: Literal["customers_and_vendors", "all"] = "customers_and_vendors"


class LexofficeLinkOut(BaseModel):
    id: uuid.UUID
    config_id: uuid.UUID
    contact_id: uuid.UUID | None
    contact_display_name: str | None
    lexoffice_contact_id: str | None
    lexoffice_version: int | None
    customer_number: int | None
    vendor_number: int | None
    sync_status: str
    synced_contact_version: int | None
    contact_version: int | None
    diverged: bool
    remote_display: dict[str, Any]
    match_reason: str | None
    match_score: Decimal | None
    candidates: list[dict[str, Any]]
    conflict: dict[str, Any] | None
    last_synced_at: datetime | None
    last_error: str | None
    deeplink: str | None


class LexofficeDecideIn(_In):
    action: Literal["link", "create_remote", "create_local", "dismiss"]
    lexoffice_contact_id: str | None = Field(default=None, max_length=64)
    contact_id: uuid.UUID | None = None
    roles: list[Literal["customer", "vendor"]] = Field(default_factory=list)


class LexofficeResolveIn(_In):
    resolution: Literal["keep_crm", "keep_lexoffice"]


class LexofficePushBatchIn(_In):
    contact_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class LexofficeRemoteSearchOut(BaseModel):
    id: str
    display_name: str
    customer_number: int | None
    vendor_number: int | None
    city: str | None
    zip: str | None
    email: str | None


class LexofficeContactStatusOut(BaseModel):
    config_id: uuid.UUID
    label: str | None
    legal_entity_id: uuid.UUID | None
    sync_status: str | None
    last_synced_at: datetime | None
    diverged: bool
    deeplink: str | None
    last_error: str | None
    link_id: uuid.UUID | None


# Invoice drafts -------------------------------------------------------------------------------


class LexofficeLineItemIn(_In):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    quantity: Decimal = Field(gt=0)
    unit_name: str = Field(min_length=1, max_length=50)
    unit_price: Decimal
    tax_rate_percent: Literal[0, 7, 19]


class LexofficeShippingIn(_In):
    type: Literal["none", "service", "serviceperiod"]
    date: dt_date | None = None
    end_date: dt_date | None = None

    @model_validator(mode="after")
    def _dates(self) -> LexofficeShippingIn:
        if self.type in ("service", "serviceperiod") and self.date is None:
            raise ValueError("Leistungsdatum fehlt")
        if self.type == "serviceperiod" and self.end_date is None:
            raise ValueError("Ende des Leistungszeitraums fehlt")
        return self


class LexofficeInvoiceDraftIn(_In):
    config_id: uuid.UUID | None = None
    invoice_kind: Literal["broker", "consulting", "management"] | None = None
    contact_id: uuid.UUID | None = None
    voucher_date: date
    tax_type: Literal["net", "gross", "vatfree"]
    line_items: list[LexofficeLineItemIn] = Field(min_length=1, max_length=300)
    shipping: LexofficeShippingIn
    title: str | None = Field(default=None, max_length=25)
    introduction: str | None = Field(default=None, max_length=2000)
    remark: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _vatfree(self) -> LexofficeInvoiceDraftIn:
        if self.tax_type == "vatfree" and any(i.tax_rate_percent != 0 for i in self.line_items):
            raise ValueError("Steuerfreie Rechnungen erlauben nur 0 Prozent")
        return self


class LexofficeInvoiceDraftPreviewOut(BaseModel):
    config_id: uuid.UUID
    legal_entity_id: uuid.UUID | None
    legal_entity_name: str | None
    payload: dict[str, Any]
    address_from_link: bool
    net: str
    tax: str
    gross: str
    note: str


class LexofficeInvoiceDraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    config_id: uuid.UUID
    legal_entity_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    invoice_kind: str | None
    status: str
    lexoffice_invoice_id: str | None
    deeplink: str | None
    last_error: str | None
    created_at: datetime
    payload: dict[str, Any]


# Invoice copies ------------------------------------------------------------------------------


class LexofficeInvoiceCopyIn(_In):
    invoice_number: str = Field(min_length=1, max_length=64)
    message_id: uuid.UUID | None = None


class LexofficeInvoiceCopyCorrectIn(_In):
    invoice_number: str | None = Field(default=None, min_length=1, max_length=64)
    requester_contact_id: uuid.UUID | None = None
    selected_invoice_id: str | None = Field(default=None, max_length=64)


class LexofficeInvoiceCopyRejectIn(_In):
    reason: str = Field(min_length=1, max_length=500)


class LexofficeLinkRecipientIn(_In):
    contact_id: uuid.UUID


class LexofficeInvoiceCopyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ticket_id: uuid.UUID
    message_id: uuid.UUID | None
    invoice_number: str
    requester_contact_id: uuid.UUID | None
    recipient_contact_id: uuid.UUID | None
    sender_config_id: uuid.UUID | None
    status: str
    lookup: dict[str, Any]
    verification: dict[str, Any]
    document_id: uuid.UUID | None
    xml_document_id: uuid.UUID | None
    reply_message_id: uuid.UUID | None
    last_error: str | None
    created_at: datetime


# Recurring preparation ------------------------------------------------------------------------


class LexofficeRecurringDoneIn(_In):
    lexoffice_template_id: str = Field(min_length=1, max_length=64)


class LexofficeRecurringPrepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    admin_fee_setting_id: uuid.UUID
    property_id: uuid.UUID
    config_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    prepared: dict[str, Any]
    checklist: list[dict[str, Any]]
    status: str
    lexoffice_template_id: str | None
    deeplink: str | None = None
    created_at: datetime
