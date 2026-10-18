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
from ..adapter.proxy import global_generation_counter
from ..asr import english_asr_capability
from ..contracts import (
    CONTRACT_VERSION,
    SCHEMA_NAMESPACE,
    HealthResponse,
    VersionResponse,
)

router = APIRouter(tags=["meta"])


@router.get("/diagnostics/generation")
async def generation_budget() -> dict[str, object]:
    """Real cross-session upstream generation-request count (LG-022 R1).

    LG-022 QA could not state a real product model-call limit because each
    proxy counted independently.  This reports the process-global counter that
    every worker session, reviewer turn and retry shares; ``limit`` is the hard
    cap (from ``LIGHTGRAVITY_MAX_GENERATION_CALLS``, ``None`` = count only).
    Only a count/limit/remaining is exposed, never a credential or prompt.
    """

    snapshot = global_generation_counter().snapshot()
    return {"generation": snapshot}


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Process liveness, version and capability overview."""

    context = getattr(request.app.state, "context", None)
    wired = context is not None
    # LG-144: these three are advertised only from the real assembled app.  The
    # deferred worker is created in the FastAPI lifespan, so ``material_intake_v2``
    # turns true only once the resident process really started it (a bare factory
    # built without a lifespan reports false).  Semantic/media wiring is mounted
    # by ``create_app`` itself; the flags record that real assembly, not merely a
    # version number.
    material_wired = bool(
        wired
        and getattr(request.app.state, "material_intake_wired", False)
        and getattr(request.app.state, "intake_worker", None) is not None
    )
    semantic_wired = bool(
        wired and getattr(request.app.state, "semantic_search_wired", False)
    )
    media_wired = bool(
        wired and getattr(request.app.state, "media_direct_embedding_wired", False)
    )
    # 1.20: this is *processing availability* from the real wired service, not
    # permission to configure.  The admin GET /settings view stays present when
    # this is false (default off/model missing/runtime unavailable), so the UI
    # gates the form on view presence rather than this capability.  A broken
    # optional config must never crash liveness.
    english_asr_available = False
    if wired:
        connections = getattr(context, "connections", None)
        if connections is not None:
            try:
                english_asr_available = bool(
                    english_asr_capability(connections.english_asr).get("available")
                )
            except Exception:  # noqa: BLE001 - health must stay a read-only liveness fact
                english_asr_available = False
    capabilities = {
        "health": True,
        "version": True,
        "store": wired,
        "coordinator": wired,
        "events_sse": wired,
        "settings": wired,
        "files": wired,
        "resources": wired,
        "verification": bool(getattr(context, "verification", None)),
        "global_chat": wired,
        # LG-054 additive: the private Personal conversation surface exists and
        # enforces server-derived ownership.  Optional for older 1.13 backends.
        "personal_chat": wired,
        # LG-062 additive: admin account management + self password are mounted.
        # Team mode only (single-user keeps the 1.14 surface untouched); older
        # backends report false and the UI degrades honestly.
        "accounts": bool(getattr(context, "team", None)),
        # LG-117 additive: the embedding settings view/PUT/draft routes are
        # mounted inside the settings router.  Optional for older backends.
        "embedding_settings": wired,
        # LG-119 additive: the complete private attachment router is mounted in
        # api/app.py and Personal messages accept the private attachment seam.
        "private_attachments": wired,
        # LG-126 additive: the read-only grouped Team projection router is
        # mounted in api/app.py; the bounded capacity governor is the one the
        # application coordinator actually constructed/configured.  Both are
        # advertised only from the real wired object, never guessed.
        "team_groups": wired,
        "capacity_v2": bool(
            wired
            and callable(getattr(getattr(context, "coordinator", None), "capacity_snapshot", None))
        ),
        # The real SDK adapter is only advertised once LG-006/LG-010 inject it.
        "sdk_adapter": bool(getattr(context, "real_executor", False)),
        # LG-144 / docs/08 §20.2 additive gates.  They describe real assembly:
        # deferred intake worker + receipt v2 + message source_refs, mounted
        # semantic search/rebuild/config routes, and the direct image/audio
        # embedding path.  They do not mean embedding is configured.
        "material_intake_v2": material_wired,
        "semantic_search": semantic_wired,
        "media_direct_embedding": media_wired,
        # 1.20 additive: true only when the saved config is enabled, the pinned
        # local files/hashes validate and the optional in-process runtime is
        # importable.  It does not promise every clip will transcribe.
        "english_asr": english_asr_available,
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
