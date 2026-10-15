#!/usr/bin/env python3
"""SDK registry hooks used by the corrected experiment host.

This is the corrected version of the round-SDK hooks.  Differences from the
first attempt:

* ``_PATH_ARG_KEYS`` now covers the **real** SDK wire keys (``AbsolutePath``,
  ``TargetFile``, ``TargetPath``, ``ScriptPath``, ...) in addition to the
  canonical/aliased keys.  The first attempt only recognised lowercase
  ``file_path``/``absolute_path`` and therefore read every ``view_file`` as
  ``paths=[]`` (guard blind spot).
* file tools are classified (read/write/other) and the guard is **fail-closed**:
  a read/write tool whose path arguments cannot be resolved is denied with an
  explicit ``unknown_file_argument`` reason instead of being allowed with
  ``paths=[]``.
* writes are limited to the *lease* path(s) held by the caller, not merely to
  the staging root.  A reviewer (no lease) can never write.

``post_tool_call`` remains a read-only observation hook.
"""
from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Any

# Basenames the model must never read or write, regardless of location.
DENY_BASENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.example",
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

# Path fragments that indicate control/reference/acceptance/secret material.
DENY_FRAGMENTS = (
    "/acceptance",
    "/reference",
    "/reference_round1",
    "/evidence/",
    "/.git/",
    "/control/",
)

# Argument keys that may carry a filesystem path across SDK builtin tools.
# Includes the real wire keys observed in the SDK native session DB
# (``AbsolutePath`` for view_file, ``TargetFile`` for writes).
_PATH_ARG_KEYS = (
    "AbsolutePath",
    "absolute_path",
    "TargetFile",
    "target_file",
    "TargetPath",
    "target_path",
    "file_path",
    "FilePath",
    "path",
    "Path",
    "file",
    "filename",
    "FileName",
    "directory_path",
    "DirectoryPath",
    "dir_path",
    "directory",
    "output_path",
    "OutputPath",
    "script_path",
    "ScriptPath",
    "cwd",
)

# SDK builtin tool names that read or write files (canonical + aliases).
READ_FILE_TOOLS = frozenset(
    {
        "view_file",
        "view-file",
        "view-file-content",
        "list_directory",
        "list-dir",
        "list-dir-content",
        "find_file",
        "find-file",
        "search_directory",
        "search-dir",
        "grep_search",
        "grep-search",
        "read_file",
        "read-file",
    }
)
WRITE_FILE_TOOLS = frozenset(
    {
        "create_file",
        "create-file",
        "edit_file",
        "edit-file",
        "write_to_file",
        "write-to-file",
        "replace_file_content",
        "replace-file-content",
        "edit_file_content",
    }
)
# Tools with no filesystem path semantics that we explicitly permit.
NON_FILE_TOOLS = frozenset({"finish", "resolve"}) | {f"finish_{i}" for i in range(4)}


def _normalize(path: str) -> str:
    """Translate a wire URI (``file://``/``cns://``) to a clean path string."""

    if "://" not in path:
        return path
    try:
        parsed = urllib.parse.urlparse(path)
    except ValueError:
        return path
    if parsed.scheme in ("file", "cns"):
        return urllib.parse.unquote(parsed.path) or path
    return path


def _get_canonical(data: Any) -> str | None:
    canonical = getattr(data, "canonical_path", None)
    if isinstance(canonical, str) and canonical.strip():
        return canonical
    if isinstance(data, dict):
        value = data.get("canonical_path")
        if isinstance(value, str) and value.strip():
            return value
    return None


def extract_paths(data: Any) -> list[str]:
    """Return candidate filesystem paths from a ToolCall (canonical + args).

    Unlike the first attempt, this reads the *real* wire keys (``AbsolutePath``
    / ``TargetFile``) directly from ``args`` and never relies solely on the
    SDK-derived ``canonical_path`` (which is ``None`` for ``view_file``).
    """

    paths: list[str] = []
    canonical = _get_canonical(data)
    if canonical:
        paths.append(canonical)
    args = getattr(data, "args", None)
    if not isinstance(args, dict) and isinstance(data, dict):
        args = data.get("args")
    if isinstance(args, dict):
        for key in _PATH_ARG_KEYS:
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                paths.append(_normalize(value))
    # de-duplicate, keep order
    seen: set[str] = set()
    unique: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _tool_name(data: Any) -> str:
    name = getattr(data, "name", None)
    if name is None and isinstance(data, dict):
        name = data.get("name")
    if name is None:
        return ""
    return str(getattr(name, "value", name))


def _within(candidate: Path, root: Path) -> bool:
    return candidate == root or root in candidate.parents


def _resolve(raw: str, allowed_root: Path) -> Path:
    candidate = Path(raw)
    resolved = candidate if candidate.is_absolute() else (allowed_root / candidate)
    try:
        return resolved.resolve()
    except OSError:
        return resolved


def _deny_reason_for_path(resolved: Path, allowed_root: Path) -> str | None:
    if not _within(resolved, allowed_root):
        return f"path {resolved.as_posix()!r} escapes the authorized root"
    if resolved.name in DENY_BASENAMES:
        return f"path {resolved.as_posix()!r} is control/secret material"
    posix = "/" + resolved.as_posix().strip("/")
    for fragment in DENY_FRAGMENTS:
        if fragment in posix:
            return f"path {resolved.as_posix()!r} matches denied fragment {fragment!r}"
    return None


def check_call(
    data: Any,
    *,
    allowed_root: Path | str,
    write_lease_paths: frozenset[str] | set[str] | None = None,
) -> tuple[bool, str]:
    """Fail-closed decision for one tool call.

    ``allowed_root`` bounds both reads and writes.  ``write_lease_paths`` (if
    given) further bounds writes: only these absolute paths may be written.  A
    caller with no lease (empty set) may not write at all.
    """

    root = Path(allowed_root).resolve()
    name = _tool_name(data)
    paths = extract_paths(data)

    if name in NON_FILE_TOOLS:
        return True, "allowed"

    is_read = name in READ_FILE_TOOLS or "read" in name or "view" in name
    is_write = name in WRITE_FILE_TOOLS or "write" in name or "create" in name or "edit" in name

    if not is_read and not is_write:
        # Unknown tool: fail closed (the experiment only ever grants the
        # explicitly registered file tools plus finish).
        return False, f"unknown tool {name!r} is not on the allow-list"

    if not paths:
        # Fail closed: a file tool whose path arguments could not be resolved.
        return False, f"unknown_file_argument for tool {name!r} (no resolvable path)"

    lease = set(write_lease_paths or set())
    for raw in paths:
        resolved = _resolve(raw, root)
        reason = _deny_reason_for_path(resolved, root)
        if reason is not None:
            return False, reason
        if is_write:
            if not lease:
                return False, f"write {resolved.as_posix()!r} denied: caller holds no lease"
            if resolved.as_posix() not in lease:
                return False, (f"write {resolved.as_posix()!r} denied: not the held lease "
                               f"{sorted(lease)}")
    return True, "allowed"


# Backwards-compatible path-only entry point (offline tests / legacy callers).
def check_paths(paths: list[str], *, allowed_root: Path | str) -> tuple[bool, str]:
    """Return ``(allowed, reason)`` for candidate paths against ``root``."""

    root = Path(allowed_root).resolve()
    for raw in paths:
        resolved = _resolve(raw, root)
        reason = _deny_reason_for_path(resolved, root)
        if reason is not None:
            return False, reason
    return True, "allowed"


def make_path_guard_hook(
    allowed_root: str | Path,
    decisions: list[dict[str, Any]] | None = None,
    *,
    write_lease_paths: frozenset[str] | set[str] | None = None,
    captured_calls: list[dict[str, Any]] | None = None,
    deny_basenames: frozenset[str] = DENY_BASENAMES,
) -> Any:
    """Build a ``pre_tool_call_decide`` hook enforcing root + lease boundaries.

    ``captured_calls`` (optional) receives the **full, untruncated** tool call
    payload as seen by the SDK hook.  This is the lossless source the driver
    uses for the ``finish`` structured output; the product executor's emitted
    event is bounded to 2000 chars and must never be the control source.
    """

    from google.antigravity.hooks import pre_tool_call_decide
    from google.antigravity.types import HookResult

    root = Path(allowed_root).resolve()
    lease = frozenset(write_lease_paths or set())

    @pre_tool_call_decide
    def _guard(data: Any) -> Any:
        paths = extract_paths(data)
        ok, reason = check_call(data, allowed_root=root, write_lease_paths=lease)
        if captured_calls is not None:
            args = getattr(data, "args", None)
            if not isinstance(args, dict) and isinstance(data, dict):
                args = data.get("args")
            captured_calls.append(
                {
                    "name": _tool_name(data),
                    "args": dict(args) if isinstance(args, dict) else {},
                    "canonical_path": _get_canonical(data),
                    "step_id": getattr(data, "step_id", None),
                    "id": getattr(data, "id", None),
                }
            )
        if decisions is not None:
            decisions.append(
                {
                    "tool": _tool_name(data),
                    "paths": paths,
                    "allow": ok,
                    "reason": reason,
                    "lease_paths": sorted(lease),
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
                "name": _tool_name(data),
                "error": bool(getattr(data, "error", None)),
                "exception": bool(getattr(data, "exception", None)),
            }
        )

    return _observe


__all__ = [
    "DENY_BASENAMES",
    "DENY_FRAGMENTS",
    "READ_FILE_TOOLS",
    "WRITE_FILE_TOOLS",
    "NON_FILE_TOOLS",
    "_PATH_ARG_KEYS",
    "extract_paths",
    "check_call",
    "check_paths",
    "make_path_guard_hook",
    "make_tool_observer",
]
