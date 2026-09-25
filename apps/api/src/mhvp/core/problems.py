"""RFC 9457 problem details with registered error codes (ADR 0004).

Every error response uses ``application/problem+json``. ``title`` and ``detail`` are German
user texts, ``developer_message`` is English. Codes follow ``MHVP-<DOMAIN>-<NNNN>`` and are
registered once in :data:`REGISTRY`.
"""

import re
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from mhvp.core.context import get_correlation_id

PROBLEM_CONTENT_TYPE = "application/problem+json"
CODE_PATTERN = re.compile(r"^MHVP-[A-Z]+-\d{4}$")


@dataclass(frozen=True, slots=True)
class ErrorCode:
    code: str
    status: int
    title: str
    developer_message: str

    @property
    def type_uri(self) -> str:
        return f"urn:mhvp:problem:{self.code}"


class ErrorCodes:
    INTERNAL = ErrorCode("MHVP-CORE-0001", 500, "Interner Fehler", "Unexpected server error.")
    NOT_FOUND = ErrorCode(
        "MHVP-CORE-0002", 404, "Ressource nicht gefunden", "No route or resource matches."
    )
    METHOD_NOT_ALLOWED = ErrorCode(
        "MHVP-CORE-0003", 405, "Methode nicht erlaubt", "HTTP method not allowed here."
    )
    VALIDATION = ErrorCode("MHVP-CORE-0004", 422, "Eingaben ungültig", "Request validation failed.")
    HTTP_ERROR = ErrorCode(
        "MHVP-CORE-0005", 400, "Anfrage nicht verarbeitbar", "Generic HTTP error."
    )
    NOT_AUTHENTICATED = ErrorCode(
        "MHVP-AUTH-0001", 401, "Anmeldung erforderlich", "Missing or invalid credentials."
    )
    INVALID_CREDENTIALS = ErrorCode(
        "MHVP-AUTH-0002", 401, "Anmeldung fehlgeschlagen", "E-mail, password or code invalid."
    )
    FORBIDDEN = ErrorCode(
        "MHVP-AUTH-0003", 403, "Keine Berechtigung", "Permission missing for this action."
    )
    ACCOUNT_LOCKED = ErrorCode(
        "MHVP-AUTH-0004", 423, "Konto vorübergehend gesperrt", "Too many failed logins."
    )
    TENANT_MISMATCH = ErrorCode(
        "MHVP-AUTH-0005", 403, "Mandant passt nicht zur Adresse", "Host and token tenant differ."
    )
    PASSWORD_POLICY = ErrorCode(
        "MHVP-AUTH-0006", 422, "Passwort erfüllt die Vorgaben nicht", "Password policy violated."
    )
    REFRESH_INVALID = ErrorCode(
        "MHVP-AUTH-0007", 401, "Sitzung abgelaufen", "Refresh token invalid, expired or reused."
    )
    AUTH_NOT_CONFIGURED = ErrorCode(
        "MHVP-AUTH-0008", 503, "Anmeldung nicht verfügbar", "Signing or encryption key missing."
    )
    TENANT_SELECTION = ErrorCode(
        "MHVP-AUTH-0009", 409, "Mandant auswählen", "Several memberships, tenant_id required."
    )
    OIDC_INVALID = ErrorCode(
        "MHVP-AUTH-0010", 400, "Anmeldeanfrage ungültig", "OIDC request invalid (RFC 6749)."
    )
    RESOURCE_NOT_FOUND = ErrorCode(
        "MHVP-PLAT-0001", 404, "Datensatz nicht gefunden", "Entity not found in this tenant."
    )
    CONFLICT = ErrorCode(
        "MHVP-PLAT-0002", 409, "Datensatz existiert bereits", "Unique constraint violated."
    )
    VERSION_CONFLICT = ErrorCode(
        "MHVP-PLAT-0003", 412, "Datensatz wurde zwischenzeitlich geändert", "If-Match mismatch."
    )
    WEBHOOK_TARGET = ErrorCode(
        "MHVP-HOOK-0001", 422, "Webhook-Ziel nicht zulässig", "Unsafe or invalid webhook URL."
    )
    GATE_FOUR_EYES = ErrorCode(
        "MHVP-GATE-0002",
        403,
        "Freigabe durch eine zweite Person erforderlich",
        "Requester and approver must be different persons.",
    )
    GATE_STATE = ErrorCode(
        "MHVP-GATE-0003", 409, "Freigabeantrag nicht im passenden Zustand", "Invalid state."
    )
    RETENTION_LOCKED = ErrorCode(
        "MHVP-DOC-0001",
        409,
        "Dokument ist aufbewahrungspflichtig oder gesperrt",
        "Deletion needs a released retention profile, an expired period and no hold (6.9.5).",
    )
    PLACEHOLDER = ErrorCode(
        "MHVP-DOC-0002", 422, "Platzhalter nicht auflösbar", "Template placeholder error."
    )
    UPLOAD_REJECTED = ErrorCode(
        "MHVP-DOC-0003", 422, "Datei nicht zulässig", "File type, content or size not accepted."
    )
    LETTERHEAD_INCOMPLETE = ErrorCode(
        "MHVP-DOC-0004",
        422,
        "Briefbogen unvollständig",
        "Mandatory company data of the tenant is missing (tenant settings).",
    )
    DMS_NOT_CONFIGURED = ErrorCode(
        "MHVP-DOC-0005",
        502,
        "Paperless ist nicht eingerichtet",
        "No enabled Paperless DmsConnection with base_url and token for this tenant.",
    )
    DMS_UNAVAILABLE = ErrorCode(
        "MHVP-DOC-0006",
        503,
        "Paperless nicht erreichbar",
        "Paperless request failed or timed out.",
    )
    ACC_UNBALANCED = ErrorCode(
        "MHVP-ACC-0001",
        422,
        "Buchungssatz nicht ausgeglichen",
        "A journal entry needs at least two lines and equal debit and credit sums (B02).",
    )
    ACC_PERIOD_LOCKED = ErrorCode(
        "MHVP-ACC-0002",
        409,
        "Zeitraum festgeschrieben",
        "The booking date lies in a locked period of the ledger (B03).",
    )
    ACC_POSTED_IMMUTABLE = ErrorCode(
        "MHVP-ACC-0003",
        409,
        "Gebuchter Satz unveränderlich",
        "Posted entries are corrected by reversal only (B03).",
    )
    ACC_WRONG_ENTITY = ErrorCode(
        "MHVP-ACC-0004",
        422,
        "Falscher Rechtsträger",
        "Accounts, open items or bank accounts belong to another ledger (B01).",
    )
    RELEASE_GATE_CLOSED = ErrorCode(
        "MHVP-GATE-0001",
        403,
        "Funktion nicht freigegeben",
        "Release gate is closed for this tenant (ADR 0003).",
    )
    IMW_NOT_CONFIGURED = ErrorCode(
        "MHVP-IMW-0001",
        502,
        "Immoware24 ist nicht eingerichtet",
        "No enabled ImmowareConnection with base_url and credentials for this tenant.",
    )
    IMW_UNAVAILABLE = ErrorCode(
        "MHVP-IMW-0002",
        503,
        "Immoware24 nicht erreichbar",
        "DAV request to Immoware24 failed or timed out.",
    )
    IMW_WRITE_BLOCKED = ErrorCode(
        "MHVP-IMW-0003",
        500,
        "Schreibversuch blockiert",
        "Write path to Immoware24 is hard-blocked; only PROPFIND/REPORT/GET are allowed.",
    )
    FINAPI_NOT_CONFIGURED = ErrorCode(
        "MHVP-BANK-0001",
        502,
        "finAPI ist für diesen Mandanten nicht eingerichtet",
        "No FinApiTenantConfig with client credentials for this tenant.",
    )
    FINAPI_UNAVAILABLE = ErrorCode(
        "MHVP-BANK-0002",
        503,
        "finAPI nicht erreichbar",
        "Request to the finAPI Access API failed or was rejected.",
    )
    FINAPI_NOT_VERIFIED = ErrorCode(
        "MHVP-BANK-0003",
        501,
        "finAPI-Funktion noch nicht freigegeben",
        (
            "Endpoint or field is marked 'zu prüfen' in docs/integrations/finapi.md and is not "
            "called until confirmed against the official documentation."
        ),
    )
    FINAPI_STATE = ErrorCode(
        "MHVP-BANK-0004",
        409,
        "Bankverbindung ist im falschen Zustand",
        "The requested action does not match the connection's current finAPI state.",
    )


def _build_registry() -> dict[str, ErrorCode]:
    registry: dict[str, ErrorCode] = {}
    for value in vars(ErrorCodes).values():
        if isinstance(value, ErrorCode):
            if not CODE_PATTERN.fullmatch(value.code):
                raise ValueError(f"invalid error code format: {value.code}")
            if value.code in registry:
                raise ValueError(f"duplicate error code: {value.code}")
            registry[value.code] = value
    return registry


REGISTRY: dict[str, ErrorCode] = _build_registry()


class FieldError(BaseModel):
    location: list[str | int]
    field: str
    code: str
    message: str


class Problem(BaseModel):
    """Response schema of every error (documented in OpenAPI)."""

    type: str = Field(examples=["urn:mhvp:problem:MHVP-CORE-0002"])
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    code: str
    developer_message: str
    correlation_id: str | None = None
    errors: list[FieldError] | None = None


class ProblemError(Exception):
    """Raise to answer with a registered problem."""

    def __init__(
        self,
        error: ErrorCode,
        *,
        detail: str | None = None,
        developer_message: str | None = None,
        errors: list[FieldError] | None = None,
        extensions: dict[str, Any] | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(developer_message or error.developer_message)
        self.error = error
        self.detail = detail
        self.developer_message = developer_message or error.developer_message
        self.errors = errors
        self.extensions = extensions or {}
        self.status = status or error.status


def problem_response(
    error: ErrorCode,
    *,
    instance: str | None,
    status: int | None = None,
    detail: str | None = None,
    developer_message: str | None = None,
    errors: list[FieldError] | None = None,
    extensions: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    problem = Problem(
        type=error.type_uri,
        title=error.title,
        status=status or error.status,
        detail=detail,
        instance=instance,
        code=error.code,
        developer_message=developer_message or error.developer_message,
        correlation_id=get_correlation_id(),
        errors=errors,
    )
    body = problem.model_dump(mode="json", exclude_none=True)
    for key, value in (extensions or {}).items():
        body.setdefault(key, value)
    return JSONResponse(
        body, status_code=problem.status, media_type=PROBLEM_CONTENT_TYPE, headers=headers
    )


_VALIDATION_MESSAGES = {
    "missing": "Pflichtangabe fehlt.",
    "extra_forbidden": "Angabe ist nicht zulässig.",
}


def _field_errors(exc: RequestValidationError) -> list[FieldError]:
    errors: list[FieldError] = []
    for item in exc.errors():
        location = [part if isinstance(part, int) else str(part) for part in item.get("loc", ())]
        error_type = str(item.get("type", "value_error"))
        # The submitted value ("input") is deliberately not echoed: it may contain personal data.
        errors.append(
            FieldError(
                location=location,
                field=str(location[-1]) if location else "",
                code=error_type,
                message=_VALIDATION_MESSAGES.get(error_type, "Wert ist ungültig."),
            )
        )
    return errors


async def _handle_problem(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ProblemError):  # pragma: no cover - registered per type
        raise exc
    return problem_response(
        exc.error,
        instance=request.url.path,
        status=exc.status,
        detail=exc.detail,
        developer_message=exc.developer_message,
        errors=exc.errors,
        extensions=exc.extensions,
    )


async def _handle_validation(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover - registered per type
        raise exc
    return problem_response(
        ErrorCodes.VALIDATION,
        instance=request.url.path,
        detail="Bitte die markierten Angaben prüfen.",
        errors=_field_errors(exc),
    )


async def _handle_http(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover - registered per type
        raise exc
    headers = dict(exc.headers) if exc.headers else None
    if exc.status_code == 404:
        return problem_response(ErrorCodes.NOT_FOUND, instance=request.url.path, headers=headers)
    if exc.status_code == 405:
        return problem_response(
            ErrorCodes.METHOD_NOT_ALLOWED, instance=request.url.path, headers=headers
        )
    return problem_response(
        ErrorCodes.HTTP_ERROR,
        instance=request.url.path,
        status=exc.status_code,
        headers=headers,
    )


def install_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ProblemError, _handle_problem)
    app.add_exception_handler(RequestValidationError, _handle_validation)
    app.add_exception_handler(StarletteHTTPException, _handle_http)
