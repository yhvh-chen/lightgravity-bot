#!/usr/bin/env python3
"""SDK registry hooks used by the experiment host.

Only ``pre_tool_call_decide`` is enforcement-relevant: it denies any file tool
whose resolved path is outside the current isolated staging workspace, or whose
name is on the control/secret denylist.  This is defense-in-depth; the driver
*also* re-validates base hashes and the file set program-side after the turn.

``post_tool_call`` is an observation hook: it appends a compact record for
cross-checking executor tool events.  It never rewrites arguments or results.

No secrets/control files are ever placed inside a staging workspace, so the
hook is tested against the *path* rule (offline with canned calls), not by
probing real secret paths.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# Basenames the model must never read or write, regardless of location.
DENY_BASENAMES = frozenset(
    {
        ".env",
        ".env.local",
        "id_rsa",
        "id_ed25519",
        "credentials",
        "secrets.json",
        "TASK.md",
        "RUN.md",
        "PROTOCOL.md",
        "PROJECT.md",
        "backlog.md",
    }
)

# Path fragments that indicate control/reference/acceptance material.
DENY_FRAGMENTS = (
    "/acceptance",
    "/reference",
    "/reference_round1",
    "/evidence/",
    "/.git/",
    "/control/",
)

# Argument keys that may carry a filesystem path across SDK builtin tools.
_PATH_ARG_KEYS = (
    "file_path",
    "path",
    "absolute_path",
    "target_file",
    "target_path",
    "file",
    "filename",
    "directory_path",
    "dir_path",
    "directory",
    "cwd",
)


def extract_paths(data: Any) -> list[str]:
    """Return candidate filesystem paths from a ToolCall (canonical + args)."""

    paths: list[str] = []
    canonical = getattr(data, "canonical_path", None)
    if isinstance(canonical, str) and canonical:
        paths.append(canonical)
    args = getattr(data, "args", None)
    if isinstance(args, dict):
        for key in _PATH_ARG_KEYS:
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                paths.append(value)
    return paths


def _within(candidate: Path, root: Path) -> bool:
    return candidate == root or root in candidate.parents


def check_paths(paths: list[str], *, allowed_root: Path) -> tuple[bool, str]:
    """Return ``(allowed, reason)`` for the candidate paths against ``root``."""

    for raw in paths:
        candidate = Path(raw)
        resolved = candidate if candidate.is_absolute() else (allowed_root / candidate)
        try:
            resolved = resolved.resolve()
        except OSError:
            resolved = allowed_root / candidate
        if not _within(resolved, allowed_root):
            return False, f"path {raw!r} escapes the staging workspace"
        if resolved.name in DENY_BASENAMES:
            return False, f"path {raw!r} is control/secret material"
        posix = "/" + resolved.as_posix().strip("/") + ("/" if resolved.is_dir() else "")
        for fragment in DENY_FRAGMENTS:
            if fragment in posix:
                return False, f"path {raw!r} matches denied fragment {fragment!r}"
    return True, "allowed"


def make_path_guard_hook(
    allowed_root: str | Path,
    decisions: list[dict[str, Any]] | None = None,
    *,
    deny_basenames: frozenset[str] = DENY_BASENAMES,
) -> Any:
    """Build a ``pre_tool_call_decide`` hook enforcing the staging boundary."""

    from google.antigravity.hooks import pre_tool_call_decide
    from google.antigravity.types import HookResult

    root = Path(allowed_root).resolve()

    @pre_tool_call_decide
    def _guard(data: Any) -> Any:
        paths = extract_paths(data)
        ok, reason = check_paths(paths, allowed_root=root)
        if decisions is not None:
            decisions.append(
                {
                    "tool": str(getattr(data, "name", "")),
                    "paths": paths,
                    "allow": ok,
                    "reason": reason,
                }
            )
        if not ok:
            return HookResult(allow=False, message=f"denied by staging guard: {reason}")
        return HookResult(allow=True)

    return _guard


def make_tool_observer(records: list[dict[str, Any]] | None = None) -> Any:
    """Build a ``post_tool_call`` observation hook (no mutation)."""

    from google.antigravity.hooks import post_tool_call

    @post_tool_call
    def _observe(data: Any) -> None:
        if records is None:
            return
        records.append(
            {
                "name": str(getattr(data, "name", "")),
                "error": bool(getattr(data, "error", None)),
                "exception": bool(getattr(data, "exception", None)),
            }
        )

    return _observe


__all__ = [
    "DENY_BASENAMES",
    "DENY_FRAGMENTS",
    "extract_paths",
    "check_paths",
    "make_path_guard_hook",
    "make_tool_observer",
]
