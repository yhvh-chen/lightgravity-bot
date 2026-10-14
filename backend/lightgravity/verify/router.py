"""Independent FastAPI router for verification/acceptance (LG-009).

This module is intentionally **not** wired into ``lightgravity/api/app.py``;
LG-012 / the integration owner mounts :func:`build_router` under ``/api/v1``.
It exposes the verify-owned slice of docs/08 §4.3:

* ``GET  /tasks/{task_id}/acceptance`` — candidate + acceptance snapshot;
* ``POST /tasks/{task_id}/actions``    — ``accept`` / ``reject`` (idempotent on
  ``request_id``).

The router converts ``AppError`` into the frozen error envelope itself, so it can
be mounted on any app without relying on app-level exception handlers.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from lightgravity.contracts import AppError, ErrorCode

from .service import VerificationService


class ActionRequest(BaseModel):
    """Control-action body (docs/08 §4.3). Only accept/reject are handled here."""

    model_config = ConfigDict(extra="forbid")

    action: str
    request_id: str | None = None
    expected_revision: int | None = None
    target_run_id: str | None = None
    decision: str | None = None
    note: str | None = None
    expected_requirements_revision: int | None = None
    expected_deliverable_revision: int | None = None


def _dump(envelope: Any) -> dict[str, Any]:
    return envelope.model_dump(mode="json")


def _error_response(exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=_dump(exc.to_envelope()),
    )


def build_router(service: VerificationService) -> APIRouter:
    """Build the verification router bound to ``service``."""

    router = APIRouter(tags=["verify"])

    @router.get("/tasks/{task_id}/acceptance")
    def get_acceptance(task_id: str) -> Any:
        try:
            view = service.acceptance(task_id)
        except AppError as exc:
            return _error_response(exc)
        return view.to_dict()

    @router.post("/tasks/{task_id}/actions")
    def post_action(task_id: str, payload: ActionRequest) -> Any:
        try:
            if payload.action not in {"accept", "reject"}:
                raise AppError(
                    ErrorCode.INVALID_REQUEST,
                    f"verify router only handles accept/reject, got {payload.action!r}",
                    details={"action": payload.action},
                )
            result = service.decide(
                task_id,
                payload.action,
                request_id=payload.request_id or "",
                expected_revision=payload.expected_revision,
                expected_requirements_revision=payload.expected_requirements_revision,
                expected_deliverable_revision=payload.expected_deliverable_revision,
                target_run_id=payload.target_run_id,
                note=payload.note,
            )
        except AppError as exc:
            return _error_response(exc)
        return result.to_dict()

    return router


__all__ = ["ActionRequest", "build_router"]
