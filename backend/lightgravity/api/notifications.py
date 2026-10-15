"""Frozen notification endpoints (LG-019; docs/08 §4.3).

* ``GET  /api/v1/notifications``      unread/all notification list + unread count
* ``POST /api/v1/notifications``      mark one or more notifications read

Notifications are a durable projection of the persisted event streams
(docs/04 §8): the list never fabricates a record, and mark-read writes only the
read flag.  Accurate Task/Run/candidate/requirements-revision targeting is part
of each item so the shell can return the user to the exact place.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from ..notifications import NotificationService
from .context import get_notifications


class MarkReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: One or more projection notification ids (``notif_...``).
    notification_ids: list[str]
    #: Optional request id so a retried mark-read is idempotent end-to-end.
    request_id: str | None = None


def build_notifications_router() -> APIRouter:
    router = APIRouter(tags=["notifications"])

    @router.get("/notifications")
    def list_notifications(
        service: Annotated[NotificationService, Depends(get_notifications)],
        unread_only: Annotated[bool, Query()] = False,
        task_ref: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> dict[str, Any]:
        items = service.list(unread_only=unread_only, task_ref=task_ref)
        # ``unread`` is the honest badge count over the full set, not the page.
        return {
            "items": items[:limit],
            "next_cursor": None,
            "unread": service.unread_count(),
        }

    @router.post("/notifications")
    def mark_notifications_read(
        payload: MarkReadRequest,
        service: Annotated[NotificationService, Depends(get_notifications)],
    ) -> dict[str, Any]:
        return service.mark_read(payload.notification_ids)

    return router


__all__ = ["MarkReadRequest", "build_notifications_router"]
