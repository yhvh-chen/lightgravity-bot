"""In-memory credential resolution for the executor (docs/08 §8.1, §10).

Resources (Agent/Connection) carry only a ``credential_ref``.  A real secret is
resolved *at execution time*, in memory, from exactly one of:

* the process environment (the deployment injects the DeepSeek key), or
* a controlled secret store exposed by LG-025 through the
  :class:`CredentialResolver` protocol.

The value is never written to disk, never serialized into a result/event/log and
never placed in a resource file.  :class:`Secret` keeps its value behind an
explicit ``reveal()`` call and renders redacted, so an accidental ``repr``/
f-string cannot leak it.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

_ENV_NORMALIZE_RE = re.compile(r"[^A-Za-z0-9]+")


class Secret:
    """An in-memory secret whose ``repr``/``str`` are always redacted."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or not value:
            raise ValueError("secret value must be a non-empty string")
        self._value = value

    def reveal(self) -> str:
        """Return the raw value; callers must not log or serialize it."""

        return self._value

    def __repr__(self) -> str:
        return "Secret(<redacted>)"

    def __str__(self) -> str:
        return "Secret(<redacted>)"

    def __bool__(self) -> bool:
        return True

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Secret):
            return NotImplemented
        return self._value == other._value

    def __hash__(self) -> int:
        return hash(("<secret>", self._value))


@runtime_checkable
class CredentialResolver(Protocol):
    """Resolve a ``credential_ref`` to a secret value, or ``None``."""

    def resolve(self, credential_ref: str) -> Secret | None: ...


def default_env_var_name(credential_ref: str) -> str:
    """Map a slug-ish ref to a conventional env var (``deepseek-api-key``)."""

    return _ENV_NORMALIZE_RE.sub("_", credential_ref).upper()


class EnvCredentialResolver:
    """Resolve credentials from the process environment.

    Lookup order for ``credential_ref``:

    1. an explicit ``mapping`` entry (``ref -> env var name``),
    2. the ref used verbatim as an env var name,
    3. the normalized upper-snake form of the ref.

    An empty or whitespace-only value is treated as absent.
    """

    def __init__(
        self,
        env: Mapping[str, str] | None = None,
        *,
        mapping: Mapping[str, str] | None = None,
    ) -> None:
        self._env = dict(os.environ if env is None else env)
        self._mapping = dict(mapping or {})

    def resolve(self, credential_ref: str) -> Secret | None:
        if not isinstance(credential_ref, str) or not credential_ref.strip():
            return None
        candidates: list[str] = []
        mapped = self._mapping.get(credential_ref)
        if mapped:
            candidates.append(mapped)
        candidates.append(credential_ref)
        candidates.append(default_env_var_name(credential_ref))
        seen: set[str] = set()
        for name in candidates:
            if name in seen:
                continue
            seen.add(name)
            value = self._env.get(name)
            if isinstance(value, str) and value.strip():
                return Secret(value)
        return None


class InMemoryCredentialResolver:
    """Resolver backed by an explicit ref -> value map (controlled store/tests).

    Used by LG-025 once a real secret store exists; this class itself holds no
    credential on disk.
    """

    def __init__(self, secrets: Mapping[str, str]) -> None:
        self._secrets = {
            ref: Secret(value)
            for ref, value in secrets.items()
            if isinstance(value, str) and value.strip()
        }

    def resolve(self, credential_ref: str) -> Secret | None:
        return self._secrets.get(credential_ref)


__all__ = [
    "Secret",
    "CredentialResolver",
    "EnvCredentialResolver",
    "InMemoryCredentialResolver",
    "default_env_var_name",
]
