"""Non-persistent draft test for the independent Embedding purpose (LG-117).

The draft endpoint is intentionally isolated from the saved ``SETTINGS.md``,
secret store, diagnostics, Tasks/Runs and defaults.  A static test only parses
and validates the supplied values.  A network test is attempted only when the
caller explicitly sends ``allow_network=true`` and performs at most one minimal
embeddings request with no tools, subagents or automatic retry.

The result reports the requested model, the model actually reported by the
response, the real vector dimension and latency.  A configuration value is never
used to fabricate ``reported_model``/``dim``, and a vector is accepted only when
it is non-empty and every component is a finite number.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from lightgravity.adapter.credentials import Secret
from lightgravity.sources.vectors.embedder import (
    DEFAULT_COLD_TIMEOUT_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    EmbedInput,
    EmbeddingServiceError,
    EmbeddingTimeout,
    EmbeddingUnavailable,
    backend_from_values,
)

from .embedding import EmbeddingConfig, EmbeddingSettingsService, SOURCE_NONE

_TEST_TEXT = "lightgravity embedding connectivity test"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _positive(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _valid_base_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


@dataclass(frozen=True, slots=True)
class DraftEmbeddingSpec:
    """The unsaved values accepted by ``POST /settings/embedding/test-draft``."""

    base_url: str | None = None
    model: str | None = None
    credential_value: str | None = None
    use_existing_credential: bool = False
    allow_network: bool = False
    timeout_seconds: float | None = None
    cold_timeout_seconds: float | None = None


class EmbeddingDraftTester:
    """Run one static or explicitly-authorized embeddings draft test."""

    def __init__(self, service: EmbeddingSettingsService) -> None:
        self._service = service
        self._network_calls = 0

    @property
    def network_calls(self) -> int:
        return self._network_calls

    def test_draft(self, spec: DraftEmbeddingSpec) -> dict[str, Any]:
        started = time.monotonic()
        base_url = _optional_text(spec.base_url)
        model = _optional_text(spec.model)
        effective = self._service.config()
        timeout = _positive(spec.timeout_seconds) or effective.timeout_seconds
        cold_timeout = (
            _positive(spec.cold_timeout_seconds) or effective.cold_timeout_seconds
        )

        checks: list[dict[str, Any]] = []
        errors: list[str] = []
        if not base_url:
            errors.append("base_url is required")
        elif not _valid_base_url(base_url):
            errors.append("base_url must be an http(s) URL")
        if not model:
            errors.append("model is required")
        if spec.timeout_seconds is not None and _positive(spec.timeout_seconds) is None:
            errors.append("timeout_seconds must be a finite positive number")
        if (
            spec.cold_timeout_seconds is not None
            and _positive(spec.cold_timeout_seconds) is None
        ):
            errors.append("cold_timeout_seconds must be a finite positive number")

        typed_secret: Secret | None = None
        credential_source: str = SOURCE_NONE
        credential_detail = "no credential supplied"
        if isinstance(spec.credential_value, str) and spec.credential_value.strip():
            typed_secret = Secret(spec.credential_value)
            credential_detail = "transient credential supplied; not stored"
        elif spec.use_existing_credential:
            resolved = self._service.resolve()
            if resolved.credential.configured and resolved.secret is not None:
                typed_secret = resolved.secret
                credential_source = resolved.credential.source or SOURCE_NONE
                credential_detail = "existing credential resolved for this test"
            else:
                errors.append("existing credential is not configured")

        if errors:
            checks.append(
                {
                    "name": "config_parse",
                    "status": "failed",
                    "detail": "; ".join(errors),
                }
            )
            checks.append(
                {
                    "name": "runtime_network",
                    "status": "skipped",
                    "detail": "configuration is invalid; no network request was made",
                }
            )
            return self._result(
                overall="failed",
                requested_model=model,
                reported_model=None,
                dim=None,
                latency=None,
                credential_source=credential_source,
                checks=checks,
                error={"code": "embedding_config_invalid", "message": "; ".join(errors)},
                cache_impact="none",
            )

        checks.append(
            {
                "name": "config_parse",
                "status": "passed",
                "detail": (
                    f"base_url={urlparse(str(base_url)).hostname or 'configured'}; "
                    f"credential={credential_detail}"
                ),
            }
        )

        if not spec.allow_network:
            checks.append(
                {
                    "name": "runtime_network",
                    "status": "skipped",
                    "detail": "network test was not explicitly allowed",
                }
            )
            return self._result(
                overall="not_run",
                requested_model=model,
                reported_model=None,
                dim=None,
                latency=None,
                credential_source=credential_source,
                checks=checks,
                error=None,
                cache_impact=self._cache_impact(model),
            )

        backend = backend_from_values(
            base_url=base_url,
            model=model,
            bearer_token=(
                typed_secret.reveal() if typed_secret is not None else None
            ),
            timeout_seconds=timeout,
            cold_timeout_seconds=cold_timeout,
        )
        call_started = time.monotonic()
        try:
            self._network_calls += 1
            result = backend.embed(EmbedInput.text_input(_TEST_TEXT))
        except (EmbeddingUnavailable, EmbeddingTimeout, EmbeddingServiceError) as exc:
            latency = time.monotonic() - call_started
            detail = (
                getattr(exc, "detail", None)
                or exc.details.get("reason")
                or exc.message
                or type(exc).__name__
            )
            checks.append(
                {
                    "name": "runtime_network",
                    "status": "failed",
                    "detail": str(detail)[:500],
                }
            )
            return self._result(
                overall="failed",
                requested_model=model,
                reported_model=None,
                dim=None,
                latency=latency,
                credential_source=credential_source,
                checks=checks,
                error={
                    "code": "embedding_test_failed",
                    "message": str(detail)[:500],
                },
                cache_impact="none",
            )
        except Exception as exc:  # noqa: BLE001 - report failure, never leak a value
            latency = time.monotonic() - call_started
            checks.append(
                {
                    "name": "runtime_network",
                    "status": "failed",
                    "detail": type(exc).__name__,
                }
            )
            return self._result(
                overall="failed",
                requested_model=model,
                reported_model=None,
                dim=None,
                latency=latency,
                credential_source=credential_source,
                checks=checks,
                error={"code": "embedding_test_failed", "message": type(exc).__name__},
                cache_impact="none",
            )

        latency = result.latency_seconds or (time.monotonic() - call_started)
        finite = bool(result.vector) and all(
            isinstance(value, float) and math.isfinite(value) for value in result.vector
        )
        dim = len(result.vector) if finite else None
        reported = result.reported_model
        if not finite:
            checks.append(
                {
                    "name": "runtime_network",
                    "status": "failed",
                    "detail": "response vector was empty or contained non-finite values",
                }
            )
            return self._result(
                overall="failed",
                requested_model=model,
                reported_model=reported,
                dim=None,
                latency=latency,
                credential_source=credential_source,
                checks=checks,
                error={
                    "code": "embedding_vector_invalid",
                    "message": "response vector was empty or not finite",
                },
                cache_impact="none",
            )

        if reported == model:
            overall = "verified"
            detail = f"reported model matches requested model; dim={dim}"
        elif reported is None:
            overall = "partial"
            detail = (
                f"real vector returned dim={dim}; the response did not report a model, "
                "so the actual model is unconfirmed"
            )
        else:
            overall = "partial"
            detail = (
                f"real vector returned dim={dim}; reported model {reported!r} differs "
                f"from requested model {model!r}"
            )
        checks.append(
            {
                "name": "runtime_network",
                "status": "passed",
                "detail": detail,
            }
        )
        return self._result(
            overall=overall,
            requested_model=model,
            reported_model=reported,
            dim=dim,
            latency=latency,
            credential_source=credential_source,
            checks=checks,
            error=None,
            cache_impact=self._cache_impact(model),
        )

    def _cache_impact(self, model: str | None) -> str:
        if not model:
            return "none"
        draft = EmbeddingConfig(
            enabled=True,
            base_url="http://configured.test",
            model=model,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            cold_timeout_seconds=DEFAULT_COLD_TIMEOUT_SECONDS,
            credential_ref=None,
            source="none",
            saved=False,
        )
        cache = self._service.cache_view(draft)
        if cache.get("compatible") is False:
            return "rebuild_required"
        return "none"

    def _result(
        self,
        *,
        overall: str,
        requested_model: str | None,
        reported_model: str | None,
        dim: int | None,
        latency: float | None,
        credential_source: str,
        checks: list[dict[str, Any]],
        error: dict[str, Any] | None,
        cache_impact: str,
    ) -> dict[str, Any]:
        return {
            "draft": True,
            "overall": overall,
            "requested_model": requested_model,
            "reported_model": reported_model,
            "dim": dim,
            "latency_seconds": latency,
            "finished_at": _now_iso(),
            "credential_source": credential_source,
            "checks": checks,
            "error": error,
            "cache_impact": cache_impact,
        }


__all__ = ["DraftEmbeddingSpec", "EmbeddingDraftTester"]
