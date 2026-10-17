"""Provider/auth matrix for the installed Antigravity SDK (LG-104/LG-109).

This module is deliberately *static* and does not import the SDK.  It encodes
the non-secret provider fields the Settings layer may persist and the validation
rules shared by:

* connection save/update (``lightgravity.settings``);
* compiled connection plans (``lightgravity.adapter.compiler``);
* static/manual connection tests (``lightgravity.settings.testing``).

The SDK facts come from the LG-105 audit of ``google-antigravity==0.1.22``:

* Gemini API             -> ``LocalAgentConfig(api_key=...)``
* Vertex Express         -> ``LocalAgentConfig(vertex=True, api_key=...)``
* Vertex Project + ADC   -> ``LocalAgentConfig(vertex=True, project=..., location=...)``
* OpenAI-compatible      -> ``LocalOpenAIAgentConfig`` (product loopback proxy)
* LiteRT local           -> ``LiteRTAgentConfig(model_path=..., backend=...)``

SDK support, application configurability, execution eligibility and real
vendor verification remain four separate facts; nothing here promotes one to
another.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

AUTH_MODES = ("api_key", "adc", "proxy_api_key", "none")
LITERT_BACKENDS = ("CPU", "GPU", "NPU")
LITERT_DEFAULT_BACKEND = "GPU"

PROVIDER_BACKENDS = ("gemini", "vertex", "openai-compat", "litert")

#: Backends whose SDK config embeds an API key (as opposed to the product proxy).
API_KEY_BACKENDS = frozenset({"gemini", "vertex"})
#: Backends where the credential is injected by the product loopback proxy.
PROXY_KEY_BACKENDS = frozenset({"openai-compat"})


def effective_auth_mode(
    backend: str,
    auth_mode: str | None,
    *,
    project: str | None = None,
    location: str | None = None,
    credential_ref: str | None = None,
) -> str:
    """Return the concrete auth mode, inferring old files without rewriting them.

    Existing files may predate ``auth_mode``.  Inference is read-only:

    * Gemini and OpenAI-compatible use their historical key paths;
    * Vertex with project/location is ADC, otherwise a key-backed Express record;
    * LiteRT never uses a cloud credential.

    An explicit value always wins (and is validated separately).
    """

    if auth_mode:
        return auth_mode
    if backend == "gemini":
        return "api_key"
    if backend == "vertex":
        if project or location:
            return "adc"
        return "api_key" if credential_ref else "adc"
    if backend == "openai-compat":
        return "proxy_api_key"
    if backend == "litert":
        return "none"
    return "api_key" if credential_ref else "none"


def auth_requires_credential(backend: str, auth_mode: str) -> bool:
    """Whether a network probe needs a secret for this provider/auth mode."""

    return auth_mode in ("api_key", "proxy_api_key") and backend in (
        API_KEY_BACKENDS | PROXY_KEY_BACKENDS
    )


def _diag(code: str, location: str, message: str, **detail: Any) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "location": location,
        **({"detail": detail} if detail else {}),
    }


def validate_provider_fields(
    *,
    backend: str,
    auth_mode: str | None,
    model: str | None,
    base_url: str | None,
    project: str | None,
    location: str | None,
    model_path: str | None,
    litert_backend: str | None,
    credential_ref: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Validate the complete provider field combination.

    Returns ``(effective_auth_mode, diagnostics)``.  Diagnostics are inert
    data: they never contain a credential value.  Callers turn a non-empty list
    into their own ``config_invalid`` error type.
    """

    effective = effective_auth_mode(
        backend,
        auth_mode,
        project=project,
        location=location,
        credential_ref=credential_ref,
    )
    diagnostics: list[dict[str, Any]] = []

    if auth_mode is not None and auth_mode not in AUTH_MODES:
        diagnostics.append(
            _diag(
                "auth_mode_invalid",
                "connection.auth_mode",
                "auth_mode must be one of " + ", ".join(AUTH_MODES),
            )
        )
        return effective, diagnostics
    if litert_backend is not None and litert_backend not in LITERT_BACKENDS:
        diagnostics.append(
            _diag(
                "litert_backend_invalid",
                "connection.litert_backend",
                "litert_backend must be one of " + ", ".join(LITERT_BACKENDS),
            )
        )

    if backend == "gemini":
        if effective != "api_key":
            diagnostics.append(
                _diag(
                    "auth_mode_unsupported",
                    "connection.auth_mode",
                    "Gemini Developer API supports auth_mode=api_key",
                )
            )
        if not model:
            diagnostics.append(
                _diag("model_missing", "connection.model", "connection requires an explicit model")
            )
        for field, value in (
            ("base_url", base_url),
            ("project", project),
            ("location", location),
            ("model_path", model_path),
            ("litert_backend", litert_backend),
        ):
            if value:
                diagnostics.append(
                    _diag(
                        "field_not_supported",
                        f"connection.{field}",
                        f"Gemini API does not support connection.{field}",
                    )
                )
    elif backend == "vertex":
        if effective not in ("api_key", "adc"):
            diagnostics.append(
                _diag(
                    "auth_mode_unsupported",
                    "connection.auth_mode",
                    "Vertex supports auth_mode=api_key (Express) or adc",
                )
            )
        if not model:
            diagnostics.append(
                _diag("model_missing", "connection.model", "connection requires an explicit model")
            )
        if effective == "api_key":
            if not credential_ref:
                # A new Express connection may be saved before its key is set;
                # the test/credential layer reports that honestly.  Do not make
                # saving impossible just because the secret is write-only.
                pass
            if project or location:
                diagnostics.append(
                    _diag(
                        "field_not_supported",
                        "connection.project",
                        "Vertex Express (API key) must not set project or location",
                    )
                )
        elif effective == "adc":
            if not project:
                diagnostics.append(
                    _diag(
                        "project_missing",
                        "connection.project",
                        "Vertex Project + ADC requires project",
                    )
                )
            if not location:
                diagnostics.append(
                    _diag(
                        "location_missing",
                        "connection.location",
                        "Vertex Project + ADC requires location",
                    )
                )
        for field, value in (
            ("base_url", base_url),
            ("model_path", model_path),
            ("litert_backend", litert_backend),
        ):
            if value:
                diagnostics.append(
                    _diag(
                        "field_not_supported",
                        f"connection.{field}",
                        f"Vertex does not support connection.{field}",
                    )
                )
    elif backend == "openai-compat":
        if effective != "proxy_api_key":
            diagnostics.append(
                _diag(
                    "auth_mode_unsupported",
                    "connection.auth_mode",
                    "OpenAI-compatible connections use auth_mode=proxy_api_key",
                )
            )
        if not model:
            diagnostics.append(
                _diag("model_missing", "connection.model", "connection requires an explicit model")
            )
        if not base_url:
            diagnostics.append(
                _diag(
                    "endpoint_missing",
                    "connection.base_url",
                    "openai-compatible connection requires base_url",
                )
            )
        for field, value in (
            ("project", project),
            ("location", location),
            ("model_path", model_path),
            ("litert_backend", litert_backend),
        ):
            if value:
                diagnostics.append(
                    _diag(
                        "field_not_supported",
                        f"connection.{field}",
                        f"openai-compatible does not support connection.{field}",
                    )
                )
    elif backend == "litert":
        if effective != "none":
            diagnostics.append(
                _diag(
                    "auth_mode_unsupported",
                    "connection.auth_mode",
                    "LiteRT local models do not use a cloud credential (auth_mode=none)",
                )
            )
        if not model_path:
            diagnostics.append(
                _diag(
                    "model_path_missing",
                    "connection.model_path",
                    "LiteRT requires an allowed local model_path",
                )
            )
        effective_litert_backend = litert_backend or LITERT_DEFAULT_BACKEND
        if effective_litert_backend not in LITERT_BACKENDS:
            diagnostics.append(
                _diag(
                    "litert_backend_invalid",
                    "connection.litert_backend",
                    "litert_backend must be one of " + ", ".join(LITERT_BACKENDS),
                )
            )
        for field, value in (
            ("base_url", base_url),
            ("project", project),
            ("location", location),
        ):
            if value:
                diagnostics.append(
                    _diag(
                        "field_not_supported",
                        f"connection.{field}",
                        f"LiteRT does not support connection.{field}",
                    )
                )
    else:
        diagnostics.append(
            _diag(
                "backend_unsupported",
                "connection.backend",
                f"connection backend {backend!r} is not in the provider matrix",
            )
        )

    return effective, diagnostics


def _normalized_endpoint(base_url: str | None) -> str:
    raw = (base_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme and parsed.hostname:
        scheme = parsed.scheme.lower()
        port_value = parsed.port
        default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
        port = f":{port_value}" if port_value and port_value != default_port else ""
        return f"{scheme}://{parsed.hostname.lower()}{port}"
    return raw.rstrip("/").lower()


def credential_recipient_identity(
    *,
    backend: str,
    auth_mode: str | None,
    base_url: str | None,
    project: str | None,
    location: str | None,
    credential_ref: str | None = None,
) -> tuple[str, ...]:
    """The non-secret recipient identity a stored key belongs to.

    A key may only be reused for a draft test when this tuple is unchanged.  For
    OpenAI-compatible endpoints the *origin* is compared (scheme/host/port), not
    the full path, so changing a path on the same host is not a silent key
    exfiltration target.  Gemini/Vertex vendor endpoints are fixed by backend
    and auth mode; Vertex ADC uses project/location as its identity and does not
    consume an API key.
    """

    effective = effective_auth_mode(
        backend,
        auth_mode,
        project=project,
        location=location,
        credential_ref=credential_ref,
    )
    if backend == "openai-compat":
        return (backend, effective, _normalized_endpoint(base_url))
    if backend == "vertex" and effective == "adc":
        return (backend, effective, project or "", location or "")
    return (backend, effective)


def capabilities_for_registration(registration: Any) -> dict[str, bool | None]:
    """Project a registry entry into the separate capability facts.

    ``None`` means the backend did not declare that fact.  This function never
    infers executable/vendor verification from SDK support or a passing test.
    """

    return {
        "configurable": getattr(registration, "configurable", None),
        "testable": getattr(registration, "testable", None),
        "executable": getattr(registration, "executable", None),
        "vendor_verified": getattr(registration, "vendor_verified", None),
    }


__all__ = [
    "AUTH_MODES",
    "LITERT_BACKENDS",
    "LITERT_DEFAULT_BACKEND",
    "PROVIDER_BACKENDS",
    "API_KEY_BACKENDS",
    "PROXY_KEY_BACKENDS",
    "effective_auth_mode",
    "auth_requires_credential",
    "validate_provider_fields",
    "credential_recipient_identity",
    "capabilities_for_registration",
]
