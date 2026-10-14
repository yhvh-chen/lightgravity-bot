"""Frozen meta endpoints: ``GET /api/v1/health`` and ``GET /api/v1/version``.

Owner: LG-002 (docs/08 §4.3). These endpoints report real process/version facts
only; unimplemented capabilities are reported as ``false``.
"""

from __future__ import annotations

import platform
import sys

from fastapi import APIRouter

from .. import __version__
from ..contracts import (
    CONTRACT_VERSION,
    SCHEMA_NAMESPACE,
    HealthResponse,
    VersionResponse,
)

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Process liveness, version and capability overview."""

    return HealthResponse(
        status="ok",
        package_version=__version__,
        contract_version=CONTRACT_VERSION,
        schema_version=SCHEMA_NAMESPACE,
        capabilities={
            # Implemented by this skeleton:
            "health": True,
            "version": True,
            # Not yet implemented; owning tasks listed in docs/08 §11:
            "store": False,
            "events_sse": False,
            "sdk_adapter": False,
        },
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
