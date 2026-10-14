"""Frozen meta endpoints: ``GET /api/v1/health`` and ``GET /api/v1/version``.

Owner: LG-002 (docs/08 §4.3). These endpoints report real process/version facts
only; unimplemented capabilities are reported as ``false``.  LG-012 reports the
capabilities actually wired by the app context instead of a hard-coded list.
"""

from __future__ import annotations

import platform
import sys

from fastapi import APIRouter, Request

from .. import __version__
from ..contracts import (
    CONTRACT_VERSION,
    SCHEMA_NAMESPACE,
    HealthResponse,
    VersionResponse,
)

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Process liveness, version and capability overview."""

    context = getattr(request.app.state, "context", None)
    wired = context is not None
    capabilities = {
        "health": True,
        "version": True,
        "store": wired,
        "coordinator": wired,
        "events_sse": wired,
        "settings": wired,
        "files": wired,
        "resources": wired,
        # The real SDK adapter is only advertised once LG-006/LG-010 inject it.
        "sdk_adapter": bool(getattr(context, "real_executor", False)),
    }
    return HealthResponse(
        status="ok",
        package_version=__version__,
        contract_version=CONTRACT_VERSION,
        schema_version=SCHEMA_NAMESPACE,
        capabilities=capabilities,
    )


@router.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    """Contract version, schema version and build information."""

    return VersionResponse(
        contract_version=CONTRACT_VERSION,
        schema_version=SCHEMA_NAMESPACE,
        package_version=__version__,
        python_version=platform.python_version(),
        platform=f"{sys.platform}-{platform.machine()}",
    )


__all__ = ["router"]
