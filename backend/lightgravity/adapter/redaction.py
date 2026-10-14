"""Secret detection/redaction for adapter output.

Resource frontmatter must only ever carry a ``credential_ref``; the adapter
never resolves a secret value and never copies one into a diagnostic, compiled
config or SDK object.  These helpers are defense-in-depth: they flag (and mask)
accidental secret-looking keys so a mistaken resource cannot leak through.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "<redacted>"

#: Normalized (non-alphanumeric stripped) exact key names treated as secrets.
_SENSITIVE_NORMALIZED = frozenset(
    {
        "apikey",
        "token",
        "secret",
        "password",
        "passwd",
        "authorization",
        "bearer",
        "privatekey",
        "accesskey",
        "secretkey",
        "clientsecret",
        "credentialvalue",
        "credential",
    }
)

#: Normalized suffixes treated as secrets (e.g. ``github_token``).
_SENSITIVE_SUFFIXES = (
    "token",
    "secret",
    "password",
    "passwd",
    "apikey",
    "accesskey",
    "privatekey",
)

_NORMALIZE_RE = re.compile(r"[^a-z0-9]")


def _normalize(key: str) -> str:
    return _NORMALIZE_RE.sub("", key.lower())


def is_sensitive_key(key: str) -> bool:
    """Return ``True`` when ``key`` names a secret-like field."""

    normalized = _normalize(key)
    if not normalized:
        return False
    if normalized in _SENSITIVE_NORMALIZED:
        return True
    return normalized.endswith(_SENSITIVE_SUFFIXES)


def sensitive_paths(value: Any, *, prefix: str = "") -> list[str]:
    """Return dotted paths of all secret-like keys inside ``value``."""

    found: list[str] = []
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            path = f"{prefix}.{key}" if prefix else key
            if is_sensitive_key(key):
                found.append(path)
            found.extend(sensitive_paths(child, prefix=path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            found.extend(sensitive_paths(child, prefix=f"{prefix}[{index}]"))
    return found


def redact(value: Any) -> Any:
    """Recursively mask values stored under secret-like keys.

    Non-sensitive values are returned unchanged; mapping/list structure is
    preserved so callers can still serialize the result.
    """

    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            if is_sensitive_key(key):
                redacted[key] = REDACTED
            else:
                redacted[key] = redact(child)
        return redacted
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [redact(item) for item in value]
    return value


__all__ = [
    "REDACTED",
    "is_sensitive_key",
    "redact",
    "sensitive_paths",
]
