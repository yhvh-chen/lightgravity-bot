"""Independent Embedding usage configuration (LG-117, docs/07 §8, docs/08 §19.4).

The Embedding purpose is deliberately separate from chat/worker/reviewer
connections: a saved embedding record is never a default model and never a
coordinator/worker/reviewer selector.  The authority is one optional
``SETTINGS.md.embedding`` block; secrets live only in the existing protected
secret store under the stable ref ``embedding-api``.

Precedence is exact and intentionally conservative:

1. a saved block is authoritative for enabled/base_url/model/timeouts;
   ``enabled: false`` disables the path even when environment variables exist;
2. without a saved block, the existing ``LIGHTGRAVITY_VECTOR_*`` environment
   variables are the fallback;
3. a saved ``credential_ref`` resolves **only** the secret store; a missing
   secret is reported as unconfigured and never silently replaces itself with
   the environment token;
4. without a saved ``credential_ref`` the legacy resolver order is used
   (secret store, then the vector environment token);
5. ``LIGHTGRAVITY_VECTOR_DIM`` is only an expectation hint and is never used to
   fabricate the dimension reported by a real response.

The module exposes only non-secret views.  Secret values stay behind
``Secret`` and are revealed only while constructing one in-memory backend.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from lightgravity.adapter.credentials import Secret
from lightgravity.sources.vectors.embedder import (
    DEFAULT_COLD_TIMEOUT_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    ENV_VECTOR_BASE_URL,
    ENV_VECTOR_COLD_TIMEOUT,
    ENV_VECTOR_MODEL,
    ENV_VECTOR_TIMEOUT,
    ENV_VECTOR_TOKEN,
    EmbeddingBackend,
    UnavailableEmbeddingBackend,
    backend_from_values,
)
from lightgravity.sources.vectors.index import VECTOR_CACHE_VERSION, VectorIndex

from .errors import SecretStoreError, SettingsConfigInvalid
from .models import CredentialStatus, GlobalSettings
from .repository import ConnectionRepository
from .secret_store import SOURCE_ENVIRONMENT, SOURCE_SECRET_STORE, FileSecretStore

EMBEDDING_CREDENTIAL_REF = "embedding-api"
SOURCE_SETTINGS = "settings"
SOURCE_NONE = "none"

_VALID_CREDENTIAL_ACTIONS = ("keep", "set", "remove")


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    """Effective non-secret embedding configuration."""

    enabled: bool
    base_url: str | None
    model: str | None
    timeout_seconds: float
    cold_timeout_seconds: float
    credential_ref: str | None
    source: str
    saved: bool

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.base_url and self.model)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "cold_timeout_seconds": self.cold_timeout_seconds,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class ResolvedEmbedding:
    """Effective config plus the in-memory credential and its public status."""

    config: EmbeddingConfig
    secret: Secret | None
    credential: CredentialStatus
    unavailable_reason: str | None

    @property
    def usable(self) -> bool:
        return self.unavailable_reason is None


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _positive_float(value: Any, *, fallback: float) -> float:
    if isinstance(value, bool) or value is None:
        return fallback
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(number) or number <= 0:
        return fallback
    return number


def _env_float(env: Mapping[str, str], key: str, fallback: float) -> float:
    return _positive_float(env.get(key), fallback=fallback)


def _valid_base_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class EmbeddingSettingsService:
    """Resolve, persist and test the independent Embedding purpose."""

    def __init__(
        self,
        repository: ConnectionRepository,
        *,
        secret_store: FileSecretStore,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._repo = repository
        self._secrets = secret_store
        self._env = dict(os.environ if env is None else env)

    # --------------------------------------------------------------- reads
    def read_settings(self) -> GlobalSettings:
        return self._repo.read_settings()

    def config(self, settings: GlobalSettings | None = None) -> EmbeddingConfig:
        settings = settings or self._repo.read_settings()
        block = settings.embedding
        if block is not None:
            enabled_value = block.get("enabled")
            enabled = enabled_value if isinstance(enabled_value, bool) else False
            return EmbeddingConfig(
                enabled=enabled,
                base_url=_optional_text(block.get("base_url")),
                model=_optional_text(block.get("model")),
                timeout_seconds=_positive_float(
                    block.get("timeout_seconds"), fallback=DEFAULT_TIMEOUT_SECONDS
                ),
                cold_timeout_seconds=_positive_float(
                    block.get("cold_timeout_seconds"),
                    fallback=DEFAULT_COLD_TIMEOUT_SECONDS,
                ),
                credential_ref=_optional_text(block.get("credential_ref")),
                source=SOURCE_SETTINGS,
                saved=True,
            )

        base_url = _optional_text(self._env.get(ENV_VECTOR_BASE_URL))
        model = _optional_text(self._env.get(ENV_VECTOR_MODEL))
        token = _optional_text(self._env.get(ENV_VECTOR_TOKEN))
        has_env = any(
            _optional_text(self._env.get(key))
            for key in (
                ENV_VECTOR_BASE_URL,
                ENV_VECTOR_MODEL,
                ENV_VECTOR_TOKEN,
                ENV_VECTOR_TIMEOUT,
                ENV_VECTOR_COLD_TIMEOUT,
            )
        )
        return EmbeddingConfig(
            enabled=bool(base_url and model),
            base_url=base_url,
            model=model,
            timeout_seconds=_env_float(
                self._env, ENV_VECTOR_TIMEOUT, DEFAULT_TIMEOUT_SECONDS
            ),
            cold_timeout_seconds=_env_float(
                self._env, ENV_VECTOR_COLD_TIMEOUT, DEFAULT_COLD_TIMEOUT_SECONDS
            ),
            credential_ref=None,
            source=SOURCE_ENVIRONMENT if (has_env or token) else SOURCE_NONE,
            saved=False,
        )

    def _resolve_credential(self, config: EmbeddingConfig) -> CredentialStatus:
        # Saved explicit ref: secret store only.  A missing secret must not fall
        # back to an environment token (docs/08 §19.4 rule ③).
        if config.saved and config.credential_ref:
            status = self._secrets.status(config.credential_ref)
            return status

        # No saved ref: existing resolver order, secret store then env token.
        stored = self._secrets.status(EMBEDDING_CREDENTIAL_REF)
        if stored.configured:
            return stored
        env_token = _optional_text(self._env.get(ENV_VECTOR_TOKEN))
        if env_token:
            return CredentialStatus(
                ref=None, configured=True, source=SOURCE_ENVIRONMENT, version=None
            )
        return CredentialStatus(ref=None, configured=False)

    def _secret_for(self, credential: CredentialStatus) -> Secret | None:
        if not credential.configured:
            return None
        if credential.source == SOURCE_ENVIRONMENT:
            token = _optional_text(self._env.get(ENV_VECTOR_TOKEN))
            return Secret(token) if token else None
        if credential.ref:
            return self._secrets.get(credential.ref)
        return None

    def resolve(self, settings: GlobalSettings | None = None) -> ResolvedEmbedding:
        config = self.config(settings)
        credential = self._resolve_credential(config)
        secret = self._secret_for(credential)
        reason: str | None = None
        if not config.enabled:
            reason = "embedding_disabled"
        elif not config.base_url or not config.model:
            reason = "embedding_config_incomplete"
        elif config.saved and config.credential_ref and not credential.configured:
            reason = "embedding_credential_missing"
        elif credential.configured and secret is None:
            reason = "embedding_credential_missing"
        return ResolvedEmbedding(
            config=config,
            secret=secret,
            credential=credential,
            unavailable_reason=reason,
        )

    def backend(self, resolution: ResolvedEmbedding | None = None) -> EmbeddingBackend:
        resolved = resolution or self.resolve()
        if not resolved.usable:
            return UnavailableEmbeddingBackend(
                resolved.unavailable_reason or "embedding backend is not configured"
            )
        config = resolved.config
        return backend_from_values(
            base_url=config.base_url,
            model=config.model,
            bearer_token=(
                resolved.secret.reveal() if resolved.secret is not None else None
            ),
            timeout_seconds=config.timeout_seconds,
            cold_timeout_seconds=config.cold_timeout_seconds,
            unavailable_reason=resolved.unavailable_reason
            or "embedding backend is not configured",
        )

    # --------------------------------------------------------------- cache view
    def _cache_index(self) -> VectorIndex | None:
        data_dir = getattr(self._repo.store, "data_dir", None)
        if data_dir is None:
            return None
        return VectorIndex(Path(data_dir) / "sources-index" / "vectors")

    def cache_view(self, config: EmbeddingConfig) -> dict[str, Any]:
        """Report whether the existing vector cache matches the effective model."""

        index = self._cache_index()
        header: dict[str, Any] = {}
        if index is not None:
            try:
                header = index.header()
            except Exception:  # noqa: BLE001 - a corrupt cache is reported, not fatal
                header = {}
        vector_model = header.get("model") if isinstance(header.get("model"), str) else None
        view: dict[str, Any] = {
            "compatible": None,
            "reason": None,
            "vector_model": vector_model,
        }
        if not config.enabled:
            view["reason"] = "embedding_disabled"
            return view
        if not config.base_url or not config.model:
            view["reason"] = "embedding_config_incomplete"
            return view
        if not header:
            view["reason"] = "cache_missing"
            return view
        if header.get("cache_version") != VECTOR_CACHE_VERSION:
            view["compatible"] = False
            view["reason"] = "cache_version_mismatch_rebuild_required"
            return view
        if vector_model != config.model:
            view["compatible"] = False
            view["reason"] = "model_mismatch_rebuild_required"
            return view
        view["compatible"] = True
        return view

    def view(
        self, settings: GlobalSettings | None = None
    ) -> dict[str, Any]:
        settings = settings or self._repo.read_settings()
        config = self.config(settings)
        credential = self._resolve_credential(config)
        return {
            **config.to_dict(),
            "credential": credential.to_dict(),
            "cache": self.cache_view(config),
        }

    # --------------------------------------------------------------- writes
    def _validate_update(
        self,
        *,
        enabled: Any,
        base_url: str | None,
        model: str | None,
        timeout_seconds: Any,
        cold_timeout_seconds: Any,
    ) -> tuple[bool, str | None, str | None, float, float]:
        if not isinstance(enabled, bool):
            raise SettingsConfigInvalid(
                "embedding.enabled must be a boolean",
                diagnostics=[{"code": "embedding_enabled_invalid", "location": "enabled"}],
            )
        clean_base = _optional_text(base_url)
        clean_model = _optional_text(model)
        if enabled:
            if not clean_base or not clean_model:
                raise SettingsConfigInvalid(
                    "enabled embedding settings require base_url and model",
                    diagnostics=[
                        {
                            "code": "embedding_config_incomplete",
                            "location": "embedding",
                        }
                    ],
                )
            if not _valid_base_url(clean_base):
                raise SettingsConfigInvalid(
                    "embedding.base_url must be an http(s) URL",
                    diagnostics=[{"code": "embedding_base_url_invalid", "location": "base_url"}],
                )
        elif clean_base and not _valid_base_url(clean_base):
            raise SettingsConfigInvalid(
                "embedding.base_url must be an http(s) URL",
                diagnostics=[{"code": "embedding_base_url_invalid", "location": "base_url"}],
            )

        current = self.config()
        timeout = current.timeout_seconds
        if timeout_seconds is not None:
            parsed = _positive_float(timeout_seconds, fallback=0.0)
            if parsed <= 0:
                raise SettingsConfigInvalid(
                    "embedding.timeout_seconds must be a finite positive number",
                    diagnostics=[
                        {"code": "embedding_timeout_invalid", "location": "timeout_seconds"}
                    ],
                )
            timeout = parsed
        cold_timeout = current.cold_timeout_seconds
        if cold_timeout_seconds is not None:
            parsed_cold = _positive_float(cold_timeout_seconds, fallback=0.0)
            if parsed_cold <= 0:
                raise SettingsConfigInvalid(
                    "embedding.cold_timeout_seconds must be a finite positive number",
                    diagnostics=[
                        {
                            "code": "embedding_cold_timeout_invalid",
                            "location": "cold_timeout_seconds",
                        }
                    ],
                )
            cold_timeout = parsed_cold
        return enabled, clean_base, clean_model, timeout, cold_timeout

    def update(
        self,
        *,
        expected_revision: int | None,
        enabled: bool,
        base_url: str | None,
        model: str | None,
        credential_action: str,
        credential_value: str | None,
        timeout_seconds: float | None,
        cold_timeout_seconds: float | None,
        actor: str,
    ) -> dict[str, Any]:
        if credential_action not in _VALID_CREDENTIAL_ACTIONS:
            raise SettingsConfigInvalid(
                "credential_action must be keep, set or remove",
                diagnostics=[
                    {"code": "embedding_credential_action_invalid", "location": "credential_action"}
                ],
            )
        if credential_action == "set" and not (
            isinstance(credential_value, str) and credential_value.strip()
        ):
            raise SettingsConfigInvalid(
                "credential_action=set requires a non-empty credential_value",
                diagnostics=[
                    {"code": "embedding_credential_value_missing", "location": "credential_value"}
                ],
            )
        if credential_action != "set" and credential_value:
            raise SettingsConfigInvalid(
                "credential_value is only accepted with credential_action=set",
                diagnostics=[
                    {"code": "embedding_credential_value_unexpected", "location": "credential_value"}
                ],
            )

        current_settings = self._repo.read_settings()
        current = self.config(current_settings)
        enabled, clean_base, clean_model, timeout, cold_timeout = self._validate_update(
            enabled=enabled,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            cold_timeout_seconds=cold_timeout_seconds,
        )

        if current_settings.exists:
            if expected_revision is None:
                raise SettingsConfigInvalid(
                    "expected_revision is required to update existing settings",
                    diagnostics=[
                        {"code": "expected_revision_missing", "location": "expected_revision"}
                    ],
                )
            if expected_revision != current_settings.revision:
                from lightgravity.store import RevisionConflict

                raise RevisionConflict(
                    "settings",
                    "settings",
                    expected=expected_revision,
                    actual=current_settings.revision,
                )
        elif expected_revision not in (None, 0):
            raise SettingsConfigInvalid(
                "settings do not exist yet; expected_revision must be 0",
                diagnostics=[
                    {"code": "expected_revision_invalid", "location": "expected_revision"}
                ],
            )

        if credential_action == "set":
            credential_ref: str | None = EMBEDDING_CREDENTIAL_REF
        elif credential_action == "remove":
            credential_ref = None
        else:
            credential_ref = current.credential_ref
            if credential_ref is None and not current.saved:
                credential_ref = None

        block = {
            "enabled": enabled,
            "base_url": clean_base,
            "model": clean_model,
            "credential_ref": credential_ref,
            "timeout_seconds": timeout,
            "cold_timeout_seconds": cold_timeout,
        }

        previous_secret = self._secrets.get(EMBEDDING_CREDENTIAL_REF)
        credential_changed = credential_action in ("set", "remove")
        try:
            if credential_action == "set":
                self._secrets.put(EMBEDDING_CREDENTIAL_REF, str(credential_value))
            elif credential_action == "remove":
                self._secrets.delete(EMBEDDING_CREDENTIAL_REF)
            if current_settings.exists:
                assert expected_revision is not None
                written = self._repo.write_settings(
                    {"embedding": block},
                    expected_revision=expected_revision,
                    actor=actor,
                )
            else:
                written = self._repo.create_settings(
                    default_coordinator_connection_ref=None,
                    default_worker_connection_ref=None,
                    embedding=block,
                    actor=actor,
                    request_id="settings-embedding",
                )
        except Exception:
            if credential_changed:
                try:
                    if previous_secret is None:
                        self._secrets.delete(EMBEDDING_CREDENTIAL_REF)
                    else:
                        self._secrets.put(EMBEDDING_CREDENTIAL_REF, previous_secret.reveal())
                except SecretStoreError:
                    pass
            raise

        return {
            "revision": written.revision,
            "content_hash": written.content_hash,
            **self.view(written),
        }

    def fingerprint(self) -> str:
        """Opaque non-secret key used to invalidate cached vector services."""

        settings = self._repo.read_settings()
        config = self.config(settings)
        return "|".join(
            [
                str(settings.revision),
                config.source,
                "1" if config.enabled else "0",
                config.base_url or "",
                config.model or "",
                config.credential_ref or "",
            ]
        )


__all__ = [
    "EMBEDDING_CREDENTIAL_REF",
    "EmbeddingConfig",
    "EmbeddingSettingsService",
    "ResolvedEmbedding",
    "SOURCE_SETTINGS",
    "SOURCE_NONE",
]
