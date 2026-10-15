"""Persistent notifications projected from durable events (LG-019).

Public surface: the :class:`NotificationService` (projection + read state +
accurate Task/Run/version targeting) and :func:`build_notifications_router` for
``GET/POST /api/v1/notifications``.
"""

from __future__ import annotations

from .models import NOTIFICATION_KINDS, Notification, severity_for
from .projection import PHASE_TO_KIND, notification_id, project_store, project_task
from .service import NotificationService
from .store import NotificationStateStore

__all__ = [
    "NOTIFICATION_KINDS",
    "Notification",
    "NotificationService",
    "NotificationStateStore",
    "PHASE_TO_KIND",
    "notification_id",
    "project_store",
    "project_task",
    "severity_for",
]
