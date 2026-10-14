"""Read-only resource metadata endpoints (LG-012, docs/08 §4.3/§6.5).

``GET /resources/{kind}`` and ``GET /resources/{kind}/{id}`` expose the seven
Resources navigation categories plus Connections.  Reads go through the LG-004
``Store`` (Markdown is the single authority); the listing scans the same
``resources/<dir>`` layout the Store owns and skips files that fail validation
instead of hiding the valid ones.  Secrets are never present: Connections carry
a ``credential_ref`` only.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response

from ..contracts import AppError, ErrorCode
from ..store import ConfigInvalid, EntityNotFound, Versioned
from ..store.entities import RESOURCE_DIRS
from .context import ApiContext, get_context


def _resource_ids(ctx: ApiContext, kind: str) -> list[str]:
    directory = ctx.data_dir / "resources" / RESOURCE_DIRS[kind]
    if not directory.is_dir():
        return []
    if kind == "skill":
        return sorted(path.parent.name for path in directory.glob("*/SKILL.md"))
    return sorted(path.stem for path in directory.glob("*.md"))


def _item(versioned: Versioned) -> dict[str, Any]:
    entity = versioned.entity
    return {
        "id": versioned.entity_id,
        "kind": versioned.kind,
        "title": entity.get("title") or versioned.entity_id,
        "enabled": bool(entity.get("enabled", True)),
        "revision": versioned.revision,
        "etag": versioned.etag,
    }


def _detail(versioned: Versioned) -> dict[str, Any]:
    payload = dict(versioned.entity)
    payload["revision"] = versioned.revision
    payload["etag"] = versioned.etag
    payload["body"] = versioned.body
    return payload


def build_resource_router() -> APIRouter:
    router = APIRouter(tags=["resources"])

    @router.get("/resources/{kind}")
    def list_resources(
        kind: str,
        ctx: Annotated[ApiContext, Depends(get_context)],
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        cursor: Annotated[str | None, Query()] = None,
    ) -> dict[str, Any]:
        if kind not in RESOURCE_DIRS:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                f"unknown resource kind {kind!r}",
                details={"kind": kind, "allowed": sorted(RESOURCE_DIRS)},
            )
        ids = _resource_ids(ctx, kind)
        if cursor:
            ids = [item for item in ids if item > cursor]
        page = ids[:limit]
        items: list[dict[str, Any]] = []
        for resource_id in page:
            try:
                items.append(_item(ctx.store.read(kind, resource_id)))
            except (EntityNotFound, ConfigInvalid):
                # Invalid resources are surfaced by the Store index diagnostics,
                # not by hiding the rest of the category.
                continue
        next_cursor = page[-1] if len(ids) > limit and page else None
        return {"items": items, "next_cursor": next_cursor}

    @router.get("/resources/{kind}/{resource_id}")
    def get_resource(
        kind: str,
        resource_id: str,
        response: Response,
        ctx: Annotated[ApiContext, Depends(get_context)],
    ) -> dict[str, Any]:
        if kind not in RESOURCE_DIRS:
            raise AppError(
                ErrorCode.INVALID_REQUEST,
                f"unknown resource kind {kind!r}",
                details={"kind": kind, "allowed": sorted(RESOURCE_DIRS)},
            )
        versioned = ctx.store.read(kind, resource_id)
        response.headers["ETag"] = versioned.etag
        return _detail(versioned)

    return router


__all__ = ["build_resource_router"]
