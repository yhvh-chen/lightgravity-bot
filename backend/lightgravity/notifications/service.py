"""Notification service: project durable events and overlay read state.

LG-019.  The service is the read+ack surface behind
``GET/POST /api/v1/notifications`` (docs/08 §4.3, frozen path): it projects
notifications from the durable Task event streams, overlays the persisted
read/read_at flags, and never invents a notification.  Marking read is
idempotent and stored durably, so a browser refresh or restart keeps the state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..store.protocol import Store
from .models import Notification
from .projection import project_store
from .store import NotificationStateStore


@dataclass(slots=True)
class NotificationService:
    store: Store
    state: NotificationStateStore
    _cache: list[Notification] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------- projection
    def task_ids(self) -> list[str]:
        try:
            return [summary.id for summary in self.store.list_tasks()]
        except Exception:  # noqa: BLE001 - a broken index must not break the badge
            return []

    def project(self) -> list[Notification]:
        """All notifications currently derivable from durable events."""

        return project_store(self.store, self.task_ids())

    def list(
        self,
        *,
        unread_only: bool = False,
        task_ref: str | None = None,
        kinds: Iterable[str] | None = None,
    ) -> list[dict[str, object]]:
        wanted = set(kinds) if kinds else None
        items: list[dict[str, object]] = []
        for notification in self.project():
            if wanted is not None and notification.kind not in wanted:
                continue
            if task_ref is not None and notification.task_ref != task_ref:
                continue
            state = self.state.read_state(notification.notification_id)
            record = notification.to_dict()
            record["read"] = bool(state.get("read"))
            record["read_at"] = state.get("read_at")
            if unread_only and record["read"]:
                continue
            items.append(record)
        return items

    def unread_count(self) -> int:
        return len(self.list(unread_only=True))

    # ------------------------------------------------------------------- ack
    def mark_read(self, notification_ids: Iterable[str]) -> dict[str, object]:
        """Persist read flags for the projection's stable ids.

        Unknown ids are reported honestly in ``unknown`` instead of silently
        creating a record, so a stale client cannot fabricate unread state.
        """

        known = {item.notification_id: item for item in self.project()}
        marked: list[str] = []
        unknown: list[str] = []
        for notification_id in notification_ids:
            if notification_id in known:
                self.state.mark_read(notification_id)
                marked.append(notification_id)
            else:
                unknown.append(notification_id)
        return {
            "marked_read": marked,
            "unknown": unknown,
            "unread": self.unread_count(),
        }

    # ------------------------------------------------------------- targeting
    def locate(self, notification_id: str) -> dict[str, object] | None:
        """Return the Task/Run/candidate/version locator for one notification."""

        for item in self.list():
            if item["notification_id"] == notification_id:
                return item
        return None


__all__ = ["NotificationService"]
