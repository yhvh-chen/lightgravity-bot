"""Workspace path authorization (LG-004, docs/08 §7 and §10).

``resolve_workspace_path`` is the single choke point for turning an untrusted
relative path into a filesystem path.  It rejects lexical ``..`` escapes,
absolute paths outside the root, and symlinks whose realpath leaves the
authorized workspace root.
"""

from __future__ import annotations

import os
from pathlib import Path

from .errors import PathOutsideWorkspace


def _within(base: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(base)
    except ValueError:
        return False
    return True


def resolve_workspace_path(root: Path | str, relative: str, *, write: bool = False) -> Path:
    """Resolve ``relative`` against ``root`` and enforce containment.

    ``write`` is accepted so callers declare intent; both modes apply the same
    containment rules.  The returned path is fully resolved (symlinks in
    existing components expanded) so callers cannot act on an escaping link.
    """

    root_path = Path(root)
    root_abs = Path(os.path.abspath(str(root_path)))
    root_real = Path(os.path.realpath(str(root_path)))

    raw = Path(relative)
    candidate = raw if raw.is_absolute() else root_path / raw

    # 1. Lexical containment: reject `..` escapes before touching the fs.
    lexical = Path(os.path.abspath(os.path.normpath(str(candidate))))
    if not _within(root_abs, lexical):
        raise PathOutsideWorkspace(relative, root=str(root_real))

    # 2. Symlink containment: resolved path must stay under the real root.
    real = Path(os.path.realpath(str(candidate)))
    if not _within(root_real, real):
        raise PathOutsideWorkspace(relative, root=str(root_real))
    return real


__all__ = ["resolve_workspace_path"]
