"""Protected English ASR settings route (docs/08 §21.3).

The integration owner mounts this router under ``/api/v1``.  The route is under
``/settings`` so the existing global sensitive/admin access classification and
origin rules apply; ``require_admin`` is an optional extra program guard and
``safe_origin`` is the existing settings origin check seam.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from .service import EnglishAsrService


class EnglishAsrUpdateRequest(BaseModel):
    """Write-only settings payload; secrets/paths are never returned by the view.

    Bounds are the union of the legacy and Google contracts; the service applies
    the provider-specific limits (for example legacy timeout <= 180 while a
    Google timeout may be up to 600).
    """

    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    enabled: bool
    provider: str | None = None
    runtime: str = "inprocess"
    model_dir: str | None = None
    reader_dir: str | None = None
    device: str = "cpu"
    threads: int = Field(default=4, ge=1, le=8)
    timeout_seconds: int = Field(default=180, ge=30, le=600)
    max_audio_seconds: int | None = Field(default=30, ge=1, le=30)
    max_audio_bytes: int = Field(default=10_000_000, ge=1, le=14_000_000)
    # Google-native additive fields; both are write-only.
    model: str | None = None
    base_url: str | None = None
    credential_ref: str | None = None
    credential_value: str | None = None


def english_asr_safe_origin(request: Request) -> None:
    """Public wrapper around the existing settings Host/Origin guard.

    The integration owner can pass this directly as ``safe_origin`` without
    importing a private settings helper.
    """

    from lightgravity.settings.router import _require_safe_origin

    _require_safe_origin(request)


def build_english_asr_router(
    service: EnglishAsrService,
    *,
    require_admin: Callable[[Request], None] | None = None,
    safe_origin: Callable[[Request], None] | None = None,
) -> APIRouter:
    """Return only the new English ASR settings route."""

    router = APIRouter(tags=["settings"])

    @router.put("/settings/english_asr")
    def update_english_asr(
        payload: EnglishAsrUpdateRequest,
        request: Request,
        response: Response,
        x_lg_actor: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if require_admin is not None:
            require_admin(request)
        if safe_origin is not None:
            safe_origin(request)
        data = payload.model_dump(exclude_unset=True)
        expected = int(data.pop("expected_revision"))
        result = service.update(expected, data, actor=x_lg_actor or "settings-api")
        response.headers["Cache-Control"] = "no-store"
        response.headers["ETag"] = f'"{result["revision"]}"'
        return result

    return router


__all__ = [
    "EnglishAsrUpdateRequest",
    "build_english_asr_router",
    "english_asr_safe_origin",
]
