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
    RELEASE_GATE_CLOSED = ErrorCode(
        "MHVP-GATE-0001",
        403,
        "Funktion nicht freigegeben",
        "Release gate is closed for this tenant (ADR 0003).",
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
        developer_message=str(exc.detail),
        headers=headers,
    )


def install_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ProblemError, _handle_problem)
    app.add_exception_handler(RequestValidationError, _handle_validation)
    app.add_exception_handler(StarletteHTTPException, _handle_http)
