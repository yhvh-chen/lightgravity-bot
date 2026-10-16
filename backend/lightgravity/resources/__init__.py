"""Team/Resources read + controlled-write service (LG-015).

See :mod:`lightgravity.resources.service`.  The package owns the seven
Resources categories (docs/05 §6.1), agent-template availability and Member
instance reads for the Team view, plus a narrow, validated ``Store.write`` path
for non-connection resources.  It never imports the SDK, never evaluates
Markdown, never resolves a secret value and never expands permissions.
"""

from .service import CATALOG_KINDS, NAV_KIND, UPDATABLE_FIELDS, ResourceService

__all__ = ["ResourceService", "CATALOG_KINDS", "NAV_KIND", "UPDATABLE_FIELDS"]
