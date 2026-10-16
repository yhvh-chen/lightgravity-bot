"""Lexical search HTTP endpoint (LG-036, docs/08 §4.3 ``GET /search``).

Implements the one endpoint frozen for this task:

* ``GET /api/v1/search`` — lexical-first search with **authorization filtering**;
  every hit is re-verified against the file source of truth before it is
  returned, and hits whose source was revoked/deleted/moved/edited are reported
  as ``source_stale`` instead of dangling results.

The endpoint is **read-only**: it never writes through GET (it borrows no
business write authorization), never creates a Task/Run, and never returns
content the caller is not authorized to see.  A corrupt or missing cache is
reported honestly with ``index_unavailable` (503) rather than returning an empty
success.

The router factory only depends on :class:`ApiContext`, so wiring is a single
``app.include_router(build_search_router(), prefix=API_PREFIX)`` line in the
integration owner's ``api/app.py`` (see ``probes/lg036/INTEGRATION.md``).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from ..contracts import AppError, ErrorCode
from ..store.errors import ConfigInvalid
from .context import ApiContext, get_context

#: Default page size for search results (docs/08 §4.1 collection convention).
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


def _service(request: Request, ctx: ApiContext) -> Any:
    """Return the per-app lexical search service bound to the live Store.

    It shares the ``SourceStore`` already built by the sources router when that
    service exists, so both halves read the same file SoT.
    """

    cached = getattr(request.app.state, "lexical_search_service", None)
    if cached is not None:
        return cached

    from ..sources import build_source_service
    from ..sources.lexical import LexicalSearchService

    source_service = getattr(request.app.state, "source_service", None)
    if source_service is None:
        def _resolve(relative: str, write: bool) -> Any:
            return ctx.store.resolve_path(relative, write=write)

        source_service = build_source_service(
            data_dir=ctx.data_dir,
            task_store=ctx.store,
            resolve_path=_resolve,
            events=ctx.store,
        )
        request.app.state.source_service = source_service

    service = LexicalSearchService(
        source_service.store,
        task_store=ctx.store,
        events=ctx.store,
    )
    request.app.state.lexical_search_service = service
    return service


def build_search_router() -> APIRouter:
    router = APIRouter(tags=["search"])

    @router.get("/search")
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
        """Search the derived lexical index with authorization re-verification.

        ``rebuild_if_missing`` only *rebuilds a missing cache from the file SoT*;
        it never widens the returned authorization scope (the scope filter only
        narrows).  Corrupt caches are reported, never silently ignored.
        """

        from ..sources.lexical import SearchRequest

        if not any((task_ref, project_ref, inbox_ref, include_global)):
            # Without any caller scope we still return only global material; the
            # filter never defaults to "everything".
            include_global = True
        try:
            return _service(request, ctx).search(
                SearchRequest(
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

    return router


__all__ = ["build_search_router"]
