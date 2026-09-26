"""API schemas for documents, categories, retention, DMS connections, templates, letters."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mhvp.documents.models import (
    DocumentSource,
    LinkRole,
    MirrorStatus,
    RetentionStart,
    StorageKind,
    TextStatus,
)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")


class LinkIn(_In):
    entity_type: str = Field(max_length=63)
    entity_id: uuid.UUID
    role: LinkRole = LinkRole.ATTACHMENT


class LinkOut(_Out):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    role: LinkRole


class MirrorOut(_Out):
    kind: StorageKind
    status: MirrorStatus
    external_ref: str | None
    attempts: int
    last_error: str | None


class DocumentOut(_Out):
    id: uuid.UUID
    title: str
    filename: str
    mime_type: str
    size: int
    sha256: str
    storage: StorageKind
    category_id: uuid.UUID | None
    text_status: TextStatus
    source: DocumentSource
    retention_profile_id: uuid.UUID | None
    retention_until: date | None
    retention_hold_reason: str | None
    visibility: list[str]
    created_at: datetime
    links: list[LinkOut] = Field(default_factory=list)
    mirrors: list[MirrorOut] = Field(default_factory=list)
    duplicate_of: list[uuid.UUID] = Field(default_factory=list)


class DocumentHit(_Out):
    id: uuid.UUID
    title: str
    filename: str
    mime_type: str
    category_id: uuid.UUID | None
    created_at: datetime
    snippet: str | None = None


class DocumentPage(BaseModel):
    items: list[DocumentHit]
    total: int
    page: int
    page_size: int


class DocumentPatch(_In):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    category_id: uuid.UUID | None = None
    visibility: list[str] | None = None
    retention_profile_id: uuid.UUID | None = None
    retention_until: date | None = None

    @field_validator("visibility")
    @classmethod
    def _visibility(cls, value: list[str] | None) -> list[str] | None:
        allowed = {"tenant", "owner", "provider", "board"}
        if value is not None and (not value or set(value) - allowed):
            raise ValueError(f"erlaubt: {', '.join(sorted(allowed))}")
        return value


class HoldIn(_In):
    reason: str = Field(min_length=5, max_length=500)


class CategoryIn(_In):
    code: str = Field(pattern=r"^[a-z0-9_]{2,63}$")
    name: str = Field(min_length=1, max_length=200)
    parent_id: uuid.UUID | None = None
    paperless_document_type: str | None = Field(default=None, max_length=128)
    drive_folder: str | None = Field(default=None, max_length=64)
    sort_order: int = 0


class CategoryOut(CategoryIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID


class RetentionProfileIn(_In):
    document_class: str = Field(min_length=2, max_length=63)
    legal_entity_kind: str | None = Field(default=None, max_length=32)
    legal_basis: str = Field(min_length=5, description="Quelle aus Anhang C, z. B. R17 oder R18")
    retention_years: int = Field(gt=0, le=100)
    start_rule: RetentionStart


class RetentionProfileOut(RetentionProfileIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    released_at: datetime | None
    released_by: uuid.UUID | None
    created_by: uuid.UUID | None = None


class DmsConnectionIn(_In):
    enabled: bool = False
    base_url: str | None = Field(default=None, max_length=500)
    secret: str | None = Field(default=None, max_length=4000, description="nur schreibbar")
    options: dict[str, str] = Field(default_factory=dict)
    # Paperless (A30): Geheimnis des Post-Consume-Webhooks, nur schreibbar (leer = behalten),
    # und Schalter "Belegeingang aus Paperless automatisch" (M14-05, Standard aus).
    webhook_secret: str | None = Field(
        default=None, min_length=16, max_length=200, description="nur schreibbar"
    )
    auto_receipt_intake: bool = False


class DmsConnectionOut(_Out):
    kind: StorageKind
    enabled: bool
    base_url: str | None
    has_secret: bool
    options: dict[str, str]
    has_webhook_secret: bool = False
    auto_receipt_intake: bool = False


class DmsDocumentOut(_Out):
    """Ein Paperless-Dokument in der Ticket- oder Objektansicht (M31)."""

    id: int
    title: str
    created: str | None
    added: str | None
    correspondent: str | None
    document_type: str | None
    tags: list[str]
    page_count: int | None
    original_file_name: str | None
    preview_url: str
    download_url: str


class DmsDocumentPageMeta(_Out):
    page: int
    per_page: int
    total: int


class DmsDocumentPage(_Out):
    data: list[DmsDocumentOut]
    meta: DmsDocumentPageMeta


class TemplateIn(_In):
    code: str = Field(pattern=r"^[a-z0-9_]{2,63}$")
    name: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=2000)
    body: str = Field(min_length=1, max_length=100_000)
    category_id: uuid.UUID | None = None


class TemplateOut(TemplateIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    version: int
    active: bool


class LetterIn(_In):
    template_id: uuid.UUID
    contact_id: uuid.UUID
    property_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    letter_date: date | None = None
    reference: str | None = Field(default=None, max_length=50, description="Unser Zeichen")
    fields: dict[str, str] = Field(default_factory=dict, description="Platzhalter felder.*")
    signatory: list[str] = Field(default_factory=list, max_length=4)


class SerialLetterIn(_In):
    template_id: uuid.UUID
    contact_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    property_id: uuid.UUID | None = None
    letter_date: date | None = None
    reference: str | None = Field(default=None, max_length=50)
    fields: dict[str, str] = Field(default_factory=dict)
    signatory: list[str] = Field(default_factory=list, max_length=4)


class SerialLetterOut(BaseModel):
    documents: list[DocumentOut]
