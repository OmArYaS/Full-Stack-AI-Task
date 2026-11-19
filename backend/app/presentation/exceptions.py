"""Map domain errors to structured HTTP error responses."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from domain.errors import (
    DomainError,
    EmptyInputError,
    ExtractionError,
    InputTooLongError,
    InvalidStatusTransitionError,
    LLMProviderError,
    LLMTimedOutError,
    LLMUnreachableError,
    SchemaError,
    TaskNotFoundError,
)

# Status mapping for domain errors, most specific first.
_STATUS_MAP: list[tuple[type[DomainError], int]] = [
    (EmptyInputError, 422),
    (InputTooLongError, 422),
    (TaskNotFoundError, 404),
    (InvalidStatusTransitionError, 400),
    (SchemaError, 422),
    (LLMUnreachableError, 502),
    (LLMTimedOutError, 504),
    (LLMProviderError, 502),
    (ExtractionError, 422),
]


def _status_for(error: DomainError) -> int:
    """Look up the HTTP status code for a domain error."""
    for error_type, status in _STATUS_MAP:
        if isinstance(error, error_type):
            return status
    return 500


def add_error_handlers(app: FastAPI) -> None:
    """Attach structured domain/validation error handlers to ``app``."""

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=_status_for(exc),
            content={
                "error": exc.__class__.__name__,
                "message": str(exc),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "RequestValidationError",
                "message": "Request validation failed.",
                "details": jsonable_encoder(exc.errors()),
            },
        )
