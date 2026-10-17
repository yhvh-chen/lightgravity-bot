"""Private Personal attachment package (LG-119).

Public entry points for the integration owner:

* :func:`attachment_service_for` builds the owner-scoped service from a data root;
* :func:`build_attachments_router` is the complete FastAPI route factory.  The
  integrator mounts it once with ``prefix=API_PREFIX`` (shared ``api/app.py``).
"""

from __future__ import annotations

from pathlib import Path

from .models import (
    MAX_ATTACHMENTS_PER_MESSAGE,
    MAX_CONTEXT_CHARS,
    MAX_CONTEXT_FILE_BYTES,
    MAX_UPLOAD_BYTES,
    AttachmentLimits,
    ModelAttachmentContext,
    PrivateAttachment,
)
from .service import PrivateAttachmentService
from .store import AttachmentStore

PRIVATE_ATTACHMENT_ROOT_NAME = "private-attachments"


def attachment_service_for(data_dir: Path | str) -> PrivateAttachmentService:
    """Build the private attachment service rooted under a controlled data dir."""

    root = Path(data_dir)
    return PrivateAttachmentService(
        AttachmentStore(root / PRIVATE_ATTACHMENT_ROOT_NAME),
        root,
    )


def build_attachments_router():  # type: ignore[no-untyped-def]
    # Imported lazily so importing the package (service/models) does not pull in
    # FastAPI router dependencies for non-API callers/tests.
    from .router import build_attachments_router as _build

    return _build()


__all__ = [
    "MAX_ATTACHMENTS_PER_MESSAGE",
    "MAX_CONTEXT_CHARS",
    "MAX_CONTEXT_FILE_BYTES",
    "MAX_UPLOAD_BYTES",
    "AttachmentLimits",
    "AttachmentStore",
    "ModelAttachmentContext",
    "PRIVATE_ATTACHMENT_ROOT_NAME",
    "PrivateAttachment",
    "PrivateAttachmentService",
    "attachment_service_for",
    "build_attachments_router",
]
