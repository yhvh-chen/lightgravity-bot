"""OpenAI-compatible OCR adapter (LG-035).

Design constraints taken from docs/08 §6.6, docs/09 §7/§10 and the LG-035
brief:

* **Real HTTP, configurable**: the base URL and model come from configuration
  (environment / settings), never a hard-coded LAN address.  No other vendor
  and no local model weights are installed automatically.
* **Bounded**: one request per page, a per-page ``max_tokens`` cap and an
  explicit timeout.  **No automatic retry** and concurrency is the caller's
  choice; a timeout is reported as an unknown outcome and is never replayed
  automatically (docs/08 §9, docs/09 §8).
* **No credential leakage**: an optional bearer token may be supplied in
  process memory only; it is never logged, echoed or persisted.
* **OCR only**: the request carries an image data URL and a strict prompt that
  forbids inference/completion.  Ground-truth text is never placed in the
  prompt.

The wire protocol is the OpenAI ``chat/completions`` typed-content form with an
``image_url`` part, which is what the verified ``llama.cpp`` router served in
the source-intake probe (``probes/source-intake/evidence``).
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from ...contracts import AppError, ErrorCode

#: Default per-page completion cap.  Overridable per request but never unbounded.
DEFAULT_MAX_TOKENS = 2000
#: Default read timeout in seconds for every request after the first cold load.
DEFAULT_TIMEOUT_SECONDS = 90.0
#: A first request may trigger a router model load; allow a longer cold bound.
DEFAULT_COLD_TIMEOUT_SECONDS = 180.0

#: Documented safe upper bound for an explicit OCR render scale.  The default
#: 2.0 renders ~144 DPI; 4.0 renders ~288 DPI and is the largest value the
#: product treats as safe for a single bounded page (it stays well below the
#: 300-DPI native scan of the LG-035 Z2 sample and does not change page/input
#: limits).  Larger values are rejected, never silently clamped.
MAX_OCR_SCALE = 4.0

#: Prompt deliberately forbids inference so the model does not invent content.
OCR_PROMPT = (
    "You are a precise OCR engine. Transcribe only the text that is visibly "
    "present in the image, exactly as written, preserving line breaks and "
    "punctuation. Do not infer, complete, translate, summarise or add any "
    "commentary. If a region is unreadable, output the token [unreadable] "
    "instead of guessing. Return only the transcription."
)

_IMAGE_MEDIA_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "image/bmp",
}


class OcrUnavailable(AppError):
    """No OCR backend is configured/available; the original must be kept."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "OCR backend is not available",
            details={"reason": detail, "backend": "none"},
        )
        self.detail = detail


class OcrScaleInvalid(AppError):
    """An explicit OCR render-scale env value is not a safe finite positive number."""

    def __init__(self, key: str, raw: str, *, reason: str) -> None:
        super().__init__(
            ErrorCode.VALIDATION_FAILED,
            "OCR render scale configuration is invalid",
            details={"env": key, "value": raw, "reason": reason,
                     "safe_max": MAX_OCR_SCALE},
        )
        self.key = key
        self.raw = raw
        self.reason = reason


class OcrTimeout(AppError):
    """A request exceeded its timeout: outcome unknown, never auto-replayed."""

    def __init__(self, *, timeout_seconds: float, page: int | None = None) -> None:
        super().__init__(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "OCR request timed out; outcome unknown and not auto-replayed",
            details={"timeout_seconds": timeout_seconds, "page": page, "outcome": "unknown"},
        )


class OcrServiceError(AppError):
    """The backend answered with an error; a clear failure, not fake text."""

    def __init__(self, *, status: int, message: str) -> None:
        super().__init__(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "OCR backend returned an error",
            details={"status": status, "message": message},
        )


@dataclass(frozen=True, slots=True)
class OcrRequest:
    """One page/image OCR request.

    ``data`` is the exact image bytes that will be base64-encoded; the adapter
    never mutates or re-encodes them, so the derivative can be traced back to a
    concrete input by hash.
    """

    data: bytes
    media_type: str
    page: int | None = None
    max_tokens: int = DEFAULT_MAX_TOKENS
    timeout_seconds: float | None = None
    cold: bool = False


@dataclass(frozen=True, slots=True)
class OcrPageResult:
    """A machine transcription plus the provenance needed to trace it."""

    page: int | None
    text: str
    model: str
    media_type: str
    input_sha256: str
    input_bytes: int
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_seconds: float
    finish_reason: str | None
    #: Raw response body for the redacted evidence log (may be large).
    raw_response: str


class OcrBackend(Protocol):
    """Minimal OCR capability the processing layer depends on."""

    def transcribe(self, request: OcrRequest) -> OcrPageResult: ...

    @property
    def model_id(self) -> str: ...


class UnavailableOcrBackend:
    """Explicit "no OCR backend" stub; never fabricates text."""

    def __init__(self, reason: str = "no OCR backend configured") -> None:
        self._reason = reason

    @property
    def model_id(self) -> str:
        return "unavailable"

    def transcribe(self, request: OcrRequest) -> OcrPageResult:
        raise OcrUnavailable(self._reason)


class OpenAICompatOcrBackend:
    """Real HTTP OCR over an OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        bearer_token: str | None = None,
        default_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        cold_timeout_seconds: float = DEFAULT_COLD_TIMEOUT_SECONDS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        user_agent: str = "lightgravity-bot/0.1 (lg035-ocr)",
    ) -> None:
        if not base_url or not model:
            raise OcrUnavailable("base_url and model are required")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._token = bearer_token
        self._timeout = float(default_timeout_seconds)
        self._cold_timeout = float(cold_timeout_seconds)
        self._max_tokens = int(max_tokens)
        self._user_agent = user_agent

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def endpoint(self) -> str:
        return f"{self._base_url}/v1/chat/completions"

    def transcribe(self, request: OcrRequest) -> OcrPageResult:
        import hashlib
        import time

        media_type = request.media_type if request.media_type in _IMAGE_MEDIA_TYPES else "image/png"
        data_url = f"data:{media_type};base64,{base64.b64encode(request.data).decode('ascii')}"
        body: dict[str, Any] = {
            "model": self._model,
            "temperature": 0,
            "stream": False,
            "max_tokens": min(int(request.max_tokens or self._max_tokens), self._max_tokens),
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": OCR_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
        }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        timeout = float(
            request.timeout_seconds
            if request.timeout_seconds is not None
            else (self._cold_timeout if request.cold else self._timeout)
        )
        http_request = urllib.request.Request(  # noqa: S310 - configured endpoint only
            self.endpoint, data=payload, headers=headers, method="POST"
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(http_request, timeout=timeout) as response:  # noqa: S310
                raw = response.read().decode("utf-8", "replace")
                status = response.status
        except urllib.error.HTTPError as exc:  # server answered with an error
            detail = _safe_error_text(exc)
            raise OcrServiceError(status=exc.code, message=detail) from None
        except TimeoutError:
            raise OcrTimeout(timeout_seconds=timeout, page=request.page) from None
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                raise OcrTimeout(timeout_seconds=timeout, page=request.page) from None
            raise OcrServiceError(status=0, message=f"connection failed: {_safe_reason(reason)}") from None
        except OSError as exc:
            raise OcrServiceError(status=0, message=f"transport error: {type(exc).__name__}") from None
        latency = time.monotonic() - started
        if status != 200:
            raise OcrServiceError(status=status, message="unexpected status")
        text, usage, finish_reason = _parse_chat_response(raw)
        return OcrPageResult(
            page=request.page,
            text=text,
            model=self._model,
            media_type=media_type,
            input_sha256=hashlib.sha256(request.data).hexdigest(),
            input_bytes=len(request.data),
            prompt_tokens=_as_int(usage.get("prompt_tokens")),
            completion_tokens=_as_int(usage.get("completion_tokens")),
            latency_seconds=latency,
            finish_reason=finish_reason,
            raw_response=raw,
        )


def _parse_chat_response(raw: str) -> tuple[str, dict[str, Any], str | None]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise OcrServiceError(status=200, message="response was not valid JSON") from None
    if not isinstance(payload, dict):
        raise OcrServiceError(status=200, message="response was not a JSON object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OcrServiceError(status=200, message="response contained no choices")
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        # Some stacks return typed parts; concatenate the text parts only.
        text = "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") in (None, "text")
        )
    elif isinstance(content, str):
        text = content
    else:
        raise OcrServiceError(status=200, message="response message had no text content")
    usage = payload.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    finish_reason = first.get("finish_reason") if isinstance(first, dict) else None
    return text, usage, finish_reason if isinstance(finish_reason, str) else None


def _safe_error_text(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", "replace")
    except Exception:  # pragma: no cover - defensive
        return f"HTTP {exc.code}"
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body[:500]
    if isinstance(parsed, dict):
        for key in ("message", "error", "code"):
            value = parsed.get(key)
            if isinstance(value, str):
                return value[:500]
            if isinstance(value, dict) and isinstance(value.get("message"), str):
                return value["message"][:500]
    return body[:500]


def _safe_reason(reason: Any) -> str:
    return type(reason).__name__ if reason is not None else "unknown"


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


#: Environment variables for the OCR backend.  They are optional and are read
#: only through :func:`backend_from_env`; nothing is hard-coded to a LAN host.
ENV_OCR_BASE_URL = "LIGHTGRAVITY_OCR_BASE_URL"
ENV_OCR_MODEL = "LIGHTGRAVITY_OCR_MODEL"
ENV_OCR_TOKEN = "LIGHTGRAVITY_OCR_TOKEN"
ENV_OCR_TIMEOUT = "LIGHTGRAVITY_OCR_TIMEOUT_SECONDS"
ENV_OCR_COLD_TIMEOUT = "LIGHTGRAVITY_OCR_COLD_TIMEOUT_SECONDS"
ENV_OCR_MAX_TOKENS = "LIGHTGRAVITY_OCR_MAX_TOKENS"

#: Optional PDF page-render scale for the OCR rasteriser.  The PDF user unit is
#: 1/72 inch, so a scale of ``2.0`` renders at ~144 DPI (the historical default,
#: documented as "~150 DPI").  This is an optional quality/composition knob and
#: **not** a secret; it is read only through :func:`backend_from_env`-style code
#: and never hard-codes a host.  Absent/empty keeps the default unchanged.
ENV_OCR_SCALE = "LIGHTGRAVITY_OCR_SCALE"


def backend_from_env(env: Any = None) -> OcrBackend:
    """Build the configured OCR backend, or an honest unavailable stub.

    Missing configuration yields :class:`UnavailableOcrBackend` so the product
    keeps the original and records a clear failure instead of contacting an
    unknown service or silently switching vendors.  No default host is assumed.
    """

    import os

    source = os.environ if env is None else env
    base_url = (source.get(ENV_OCR_BASE_URL) or "").strip()
    model = (source.get(ENV_OCR_MODEL) or "").strip()
    if not base_url or not model:
        return UnavailableOcrBackend(
            f"{ENV_OCR_BASE_URL}/{ENV_OCR_MODEL} are not set; OCR stays disabled"
        )
    token = (source.get(ENV_OCR_TOKEN) or "").strip() or None
    kwargs: dict[str, Any] = {"base_url": base_url, "model": model, "bearer_token": token}
    if (value := _float_env(source, ENV_OCR_TIMEOUT)) is not None:
        kwargs["default_timeout_seconds"] = value
    if (value := _float_env(source, ENV_OCR_COLD_TIMEOUT)) is not None:
        kwargs["cold_timeout_seconds"] = value
    if (value := _int_env(source, ENV_OCR_MAX_TOKENS)) is not None:
        kwargs["max_tokens"] = value
    return OpenAICompatOcrBackend(**kwargs)


def _float_env(source: Any, key: str) -> float | None:
    raw = source.get(key)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _int_env(source: Any, key: str) -> int | None:
    raw = source.get(key)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def parse_scale_env(
    source: Any, key: str = ENV_OCR_SCALE, *, default: float
) -> float:
    """Parse an optional, validated OCR render scale from the environment.

    Returns ``default`` when the variable is absent or empty (default behaviour
    unchanged).  A present-but-invalid value is **not** silently clamped: it
    raises :class:`OcrScaleInvalid` with an explicit diagnostic so a bad security
    or quality value cannot slip through as an accidental pass.  The value must
    be finite, strictly positive and no greater than the documented safe maximum
    (:data:`MAX_OCR_SCALE`); the existing page/input/memory bounds still apply.
    """

    import math

    raw = source.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise OcrScaleInvalid(
            key, str(raw), reason="not a number"
        ) from None
    if not math.isfinite(value):
        raise OcrScaleInvalid(key, str(raw), reason="not finite")
    if value <= 0:
        raise OcrScaleInvalid(key, str(raw), reason="must be positive")
    if value > MAX_OCR_SCALE:
        raise OcrScaleInvalid(
            key, str(raw), reason=f"above safe maximum {MAX_OCR_SCALE}"
        )
    return value


__all__ = [
    "OcrBackend",
    "OcrPageResult",
    "OcrRequest",
    "OcrServiceError",
    "OcrTimeout",
    "OcrUnavailable",
    "OpenAICompatOcrBackend",
    "UnavailableOcrBackend",
    "backend_from_env",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_COLD_TIMEOUT_SECONDS",
    "ENV_OCR_BASE_URL",
    "ENV_OCR_MODEL",
    "ENV_OCR_TOKEN",
    "ENV_OCR_SCALE",
    "parse_scale_env",
    "OcrScaleInvalid",
    "MAX_OCR_SCALE",
    "OCR_PROMPT",
]
