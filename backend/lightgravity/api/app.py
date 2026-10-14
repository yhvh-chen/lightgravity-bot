"""FastAPI application factory.

The factory keeps configuration injectable for tests. Run with:

    uv run uvicorn --factory lightgravity.api.app:create_app
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..config import Settings
from ..contracts import (
    API_PREFIX,
    CONTRACT_VERSION,
    AppError,
    ErrorCode,
    error_envelope,
)
from .health import router as health_router

_STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.INVALID_REQUEST,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.PATH_OUTSIDE_WORKSPACE,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.INVALID_REQUEST,
    409: ErrorCode.REVISION_CONFLICT,
    422: ErrorCode.VALIDATION_FAILED,
    429: ErrorCode.BUDGET_EXHAUSTED,
    500: ErrorCode.INTERNAL_ERROR,
    503: ErrorCode.CAPABILITY_UNAVAILABLE,
}


def _dump(envelope: Any) -> dict[str, Any]:
    return envelope.model_dump(mode="json")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # Ensure the gitignored data root exists before serving; it stays
        # separate from source (docs/08 §10).
        resolved.ensure_data_dir()
        application.state.settings = resolved
        yield

    app = FastAPI(
        title="LightGravity Bot API",
        version=CONTRACT_VERSION,
        lifespan=lifespan,
    )

    @app.exception_handler(AppError)
    async def _app_error_handler(
        request: Request, exc: AppError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.http_status,
            content=_dump(exc.to_envelope(request_id=request_id)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        envelope = error_envelope(
            ErrorCode.VALIDATION_FAILED,
            "request failed schema validation",
            details={"errors": exc.errors()},
        )
        return JSONResponse(status_code=422, content=_dump(envelope))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        envelope = error_envelope(code, str(exc.detail))
        return JSONResponse(status_code=exc.status_code, content=_dump(envelope))

    app.include_router(health_router, prefix=API_PREFIX)
    return app
