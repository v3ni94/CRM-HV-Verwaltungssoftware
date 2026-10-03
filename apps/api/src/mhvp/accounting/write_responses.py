"""AL04 (GAI-304): typed responses of writing accounting routes without money amounts.

``extra="allow"`` keeps fields a handler adds later (no silent field loss). Routes that
return amounts stay untyped until the JSON format of Decimal amounts is decided (AK11).
"""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    PrivateAttr,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    ValidatorFunctionWrapHandler,
    model_serializer,
    model_validator,
)


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")


class AccountingPaymentTypeAccountOut(_Open):
    payment_type_code: str
    account_id: uuid.UUID | None = None


class AccountingReceivableRunReverseOut(_Open):
    reversed: int
    status: str


class AccountingAdminFeeCreatedOut(_Open):
    id: uuid.UUID
    lexoffice_recurring_prep_id: uuid.UUID | None = None


class AccountingRecurringPlanCreatedOut(_Open):
    id: uuid.UUID
    next_due: date | None = None


class AccountingDeliveryProofOut(_Open):
    id: uuid.UUID
    case_id: uuid.UUID
    kind: str
    proof_date: date
    reference: str | None = None
    document_id: uuid.UUID | None = None
    note: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None


class AccountingDocumentStoredOut(_Open):
    document_id: uuid.UUID
    created: bool


class AccountingPaperlessIntakeOut(_Open):
    document_id: str
    run_id: str
    proposal_id: uuid.UUID | None = None


class AccountingJournalExportOut(_Open):
    id: uuid.UUID
    rows: int
    sha256: str | None = None
    content: str


class AccountingDatevExportOut(AccountingJournalExportOut):
    skipped_split_bookings: list[Any] = []


class AccountingS35aCertificateDocumentOut(_Open):
    document_id: str
    contract_id: str
    year: int
    repeat_notice: str | None = None


class AccountingEntityCreditorIdOut(_Open):
    legal_entity_id: uuid.UUID
    sepa_creditor_id: str | None = None


class AccountingTenantCreditorIdOut(_Open):
    tenant_id: uuid.UUID
    sepa_creditor_id: str | None = None


class RawJsonOut(BaseModel):
    """AN11 (GAI-304, ADR 0037): documents a response while keeping its bytes unchanged.

    Routes annotated ``dict[str, Any]`` (or ``Any``) serialize the handler result through
    Pydantic, so ``Decimal`` is already a JSON string (``"1234.50"``) today. Subclasses
    declare the fields for OpenAPI and validate the handler result, but serialize the
    original handler value in JSON mode, so declared field types never coerce a value
    (``7`` stays ``7``, it does not become ``"7"``) and the bytes stay identical.
    """

    model_config = ConfigDict(extra="allow", json_schema_mode_override="validation")
    _raw: Any = PrivateAttr(default=None)

    @model_validator(mode="wrap")
    @classmethod
    def _keep_raw(cls, data: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        instance = handler(data)
        if isinstance(instance, RawJsonOut) and not isinstance(data, RawJsonOut):
            instance._raw = data
        return instance

    @model_serializer(mode="wrap")
    def _dump_raw(  # type: ignore[no-untyped-def]
        self, handler: SerializerFunctionWrapHandler, info: SerializationInfo
    ):
        # No return annotation on purpose: Pydantic then documents the declared fields.
        if info.mode_is_json() and self._raw is not None:
            return self._raw
        return handler(self)
