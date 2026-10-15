"""Optional vector index HTTP surface (LG-037, docs/08 §4.3/§6.6).

This router exposes the **optional** vector path without touching
``api/app.py`` (owned by the single integration writer).  The integration owner
mounts it with one line:

```python
from .vector import build_vector_router
app.include_router(build_vector_router(), prefix=API_PREFIX)
```

Endpoints (all additive and optional; the vector backend is **disabled by
default** and configured only through environment variables):

* ``GET  /vector/status`` — honest cache/backend status: enabled, model, dim,
  documents, cache version and a clear reason when unavailable.  It never calls
  the embedding service.
* ``GET  /vector/search`` — vector search with回源 re-verification; when the
  backend/cache is unavailable it reports ``index_status=index_unavailable`` and
  ``lexical_fallback=true`` with empty hits (the lexical ``/search`` endpoint and
  original viewing stay available).  Read-only; never writes through GET.
* ``POST /vector/rebuild`` — delete and rebuild the vector cache **from the file
  source of truth**.  No separate vector database service is started.

No endpoint widens authorization: search scope only narrows, and every hit is
re-verified against ``SOURCE.md`` before it is returned.  No ``source.indexed``
permission/attribution state is stored in the cache.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from ..contracts import AppError, ErrorCode
from ..store.errors import ConfigInvalid
from .context import ApiContext, get_context

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


def _service(request: Request, ctx: ApiContext) -> Any:
    """Return the per-app vector service bound to the live Store.

    It shares the ``SourceStore`` already built by the sources/search routers so
    every path reads the same file SoT.  The backend comes from environment
    configuration only (no hard-coded host).
    """

    cached = getattr(request.app.state, "vector_search_service", None)
    if cached is not None:
        return cached

    from ..sources.vectors import build_vector_service

    # A test/integration seam may inject an explicit backend (kept opaque to the
    # app factory); production builds the backend from environment config only.
    injected = getattr(request.app.state, "vector_test_backend", None)
    source_service = getattr(request.app.state, "source_service", None)
    store = getattr(source_service, "store", None)
    service = build_vector_service(
        data_dir=ctx.data_dir,
        task_store=ctx.store,
        events=ctx.store,
        backend=injected,
    )
    if store is not None:
        # Reuse the exact store the sources/search services read.
        service._store = store  # noqa: SLF001 - single-process wiring, same package
    request.app.state.vector_search_service = service
    return service


def build_vector_router() -> APIRouter:
    router = APIRouter(tags=["vector"])

    @router.get("/vector/status")
    def status(
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        """Report backend + cache status honestly; makes no service call."""

        service = _service(request, ctx)
        stats: dict[str, Any] = {}
        if service.index.exists() and service.index.readable():
            stats = service.index.stats()
        return {
            "enabled": service.enabled,
            "backend": {
                "configured": service.enabled,
                "model": service.backend.model_id if service.enabled else None,
            },
            "cache": {
                "exists": service.index.exists(),
                "readable": service.index.readable() if service.index.exists() else False,
                **stats,
            },
            "reason": None if service.enabled else "vector_backend_not_configured",
        }

    @router.get("/vector/search")
    def search(
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
        q: Annotated[str, Query(min_length=1, max_length=2000)],
        task_ref: Annotated[str | None, Query()] = None,
        project_ref: Annotated[str | None, Query()] = None,
        inbox_ref: Annotated[str | None, Query()] = None,
        include_global: Annotated[bool, Query()] = False,
        limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
        rebuild_if_missing: Annotated[bool, Query()] = False,
    ) -> dict[str, Any]:
        """Vector search with回源 re-verification and honest fallback."""

        from ..sources.vectors import VectorSearchRequest

        if not any((task_ref, project_ref, inbox_ref, include_global)):
            include_global = True
        try:
            return _service(request, ctx).search(
                VectorSearchRequest(
                    query=q,
                    task_ref=task_ref,
                    project_ref=project_ref,
                    inbox_ref=inbox_ref,
                    include_global=include_global,
                    limit=limit,
                    rebuild_if_missing=rebuild_if_missing,
                )
            )
        except AppError:
            raise
        except ConfigInvalid as exc:
            raise AppError(ErrorCode.VALIDATION_FAILED, exc.message, details=exc.details) from exc

    @router.post("/vector/rebuild")
    def rebuild(
        request: Request,
        ctx: Annotated[ApiContext, Depends(get_context)],
        source_id: Annotated[str | None, Query()] = None,
    ) -> dict[str, Any]:
        """Delete and rebuild the vector cache from the file source of truth."""

        service = _service(request, ctx)
        try:
            return service.rebuild(source_ids=[source_id] if source_id else None)
        except AppError:
            raise
        except ConfigInvalid as exc:
            raise AppError(ErrorCode.VALIDATION_FAILED, exc.message, details=exc.details) from exc

    return router


__all__ = ["build_vector_router"]
