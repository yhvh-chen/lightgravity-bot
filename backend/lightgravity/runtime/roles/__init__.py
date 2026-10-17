"""Pinned agency-agents role library (LG-120).

The package ships the complete, adapted role catalog as Markdown resources.  It
never clones the upstream repository at runtime and never executes upstream
scripts.  ``catalog`` is the read/validate boundary; ``seed`` is the idempotent
Store writer used once at startup.
"""

from .catalog import (
    AGENCY_COMMIT,
    AGENCY_COPYRIGHT,
    AGENCY_LICENSE,
    AGENCY_REPOSITORY,
    CAPABILITIES,
    CAPABILITY_TOOL_REFS,
    EXECUTABLE_CAPABILITIES,
    ROLE_LIBRARY_VERSION,
    RoleTemplate,
    capability_catalog,
    classify_role,
    iter_templates,
    load_manifest,
)
from .seed import RoleSeedReport, seed_role_library

__all__ = [
    "AGENCY_COMMIT",
    "AGENCY_COPYRIGHT",
    "AGENCY_LICENSE",
    "AGENCY_REPOSITORY",
    "CAPABILITIES",
    "CAPABILITY_TOOL_REFS",
    "EXECUTABLE_CAPABILITIES",
    "ROLE_LIBRARY_VERSION",
    "RoleSeedReport",
    "RoleTemplate",
    "capability_catalog",
    "classify_role",
    "iter_templates",
    "load_manifest",
    "seed_role_library",
]
