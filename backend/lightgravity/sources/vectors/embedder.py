"""Optional multimodal embedding adapter (LG-037).

This module is the **only** place that talks to a vector/embedding service.  It
follows the same discipline as the LG-035 OCR adapter:

* **Real HTTP, configurable**: the base URL and model come from configuration
  (environment), never a hard-coded LAN address.  No vendor default, no local
  model weights, no automatic install.
* **Bounded**: one request per call, an explicit timeout and a cold-load bound.
  **No automatic retry**; concurrency is the caller's responsibility.
* **No credential leakage**: an optional bearer token lives in process memory
  only; it is never logged, echoed or persisted.
* **Protocol honesty**: text uses the verified llama.cpp OpenAI-compatible
  ``/v1/embeddings`` ``input`` shape; media uses the **verified** multimodal
  ``input[].content[]`` typed-part shape (``image_url`` / ``input_audio``) taken
  from ``probes/source-intake/evidence/eg2-endpoint-20261015/REPORT.md``.  We do
  **not** pass generic OpenAI string-embedding calls off as multimodal ability.
* **Media stays media**: image/audio bytes are sent as media parts and never
  fabricated into text here; ASR/OCR are separate paths (LG-035/LG-039).

Embedding output is a **vector**, never text: it is not a transcription and not
a recognition-quality claim.
"""

from __future__ import annotations

import base64
import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from ...contracts import AppError, ErrorCode

#: Default read timeout (seconds) for a warm request.
DEFAULT_TIMEOUT_SECONDS = 60.0
#: A first request may trigger a router model load; allow a longer cold bound.
DEFAULT_COLD_TIMEOUT_SECONDS = 150.0

#: Verified llama.cpp content-part media kinds (source-intake probe §3).
_MEDIA_PART_TYPES = {
    "image": "image_url",
    "audio": "input_audio",
}


class EmbeddingUnavailable(AppError):
    """No embedding backend is configured/available; callers degrade honestly."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "embedding backend is not available",
            details={"reason": detail, "backend": "none"},
        )
        self.detail = detail


class EmbeddingTimeout(AppError):
    """A request exceeded its timeout: outcome unknown, never auto-replayed."""

    def __init__(self, *, timeout_seconds: float) -> None:
        super().__init__(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "embedding request timed out; outcome unknown and not auto-replayed",
            details={"timeout_seconds": timeout_seconds, "outcome": "unknown"},
        )


class EmbeddingServiceError(AppError):
    """The backend answered with an error; a clear failure, not a fake vector."""

    def __init__(self, *, status: int, message: str) -> None:
        super().__init__(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "embedding backend returned an error",
            details={"status": status, "message": message},
        )


@dataclass(frozen=True, slots=True)
class EmbedInput:
    """One embedding input: either plain text or a media part.

    A media input carries the exact bytes and media type so the vector can be
    traced back to a concrete input by hash.  ``part_type`` selects the verified
    llama.cpp content-part kind (``text`` / ``image_url`` / ``input_audio``).
    """

    part_type: str
    text: str | None = None
    data: bytes | None = None
    media_type: str | None = None

    @classmethod
    def text_input(cls, text: str) -> "EmbedInput":
        return cls(part_type="text", text=text)

    @classmethod
    def image(cls, data: bytes, media_type: str) -> "EmbedInput":
        return cls(part_type="image", data=data, media_type=media_type)

    @classmethod
    def audio(cls, data: bytes, media_type: str) -> "EmbedInput":
        return cls(part_type="audio", data=data, media_type=media_type)


@dataclass(frozen=True, slots=True)
class EmbedResult:
    """One embedding plus the provenance needed to record it honestly."""

    vector: tuple[float, ...]
    model: str
    dim: int
    input_kind: str  # "text" | "image" | "audio"
    input_sha256: str
    input_bytes: int
    latency_seconds: float
    prompt_tokens: int | None
    #: Raw response body (redacted evidence only; may be large).
    raw_response: str


class EmbeddingBackend(Protocol):
    """Minimal embedding capability the vector index depends on."""

    def embed(self, item: EmbedInput) -> EmbedResult: ...

    @property
    def model_id(self) -> str: ...

    @property
    def configured(self) -> bool: ...


class UnavailableEmbeddingBackend:
    """Explicit "no embedding backend" stub; never fabricates a vector.

    ``configured`` is ``False`` so callers can keep the optional vector path
    disabled with an honest reason while lexical search and original viewing
    continue to work (docs/08 §6.6).
    """

    def __init__(self, reason: str = "no embedding backend configured") -> None:
        self._reason = reason

    @property
    def model_id(self) -> str:
        return "unavailable"

    @property
    def configured(self) -> bool:
        return False

    def embed(self, item: EmbedInput) -> EmbedResult:
        raise EmbeddingUnavailable(self._reason)


class OpenAICompatEmbeddingBackend:
    """Real HTTP embeddings over a llama.cpp OpenAI-compatible endpoint.

    Text inputs go through the plain ``input`` string/array shape.  Media inputs
    use the verified ``input[].content[]`` typed-part shape; a media part is
    base64 data-URL encoded exactly as the source-intake probe did.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        bearer_token: str | None = None,
        default_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        cold_timeout_seconds: float = DEFAULT_COLD_TIMEOUT_SECONDS,
        user_agent: str = "lightgravity-bot/0.1 (lg037-vectors)",
    ) -> None:
        if not base_url or not model:
            raise EmbeddingUnavailable("base_url and model are required")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._token = bearer_token
        self._timeout = float(default_timeout_seconds)
        self._cold_timeout = float(cold_timeout_seconds)
        self._user_agent = user_agent

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def configured(self) -> bool:
        return True

    @property
    def endpoint(self) -> str:
        return f"{self._base_url}/v1/embeddings"

    def embed(self, item: EmbedInput) -> EmbedResult:
        import hashlib

        body: dict[str, Any] = {
            "model": self._model,
            "encoding_format": "float",
            "input": [_input_element(item)],
        }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        timeout = self._cold_timeout if item.part_type == "text" else self._timeout
        http_request = urllib.request.Request(  # noqa: S310 - configured endpoint only
            self.endpoint, data=payload, headers=headers, method="POST"
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(http_request, timeout=timeout) as response:  # noqa: S310
                raw = response.read().decode("utf-8", "replace")
                status = response.status
        except urllib.error.HTTPError as exc:
            raise EmbeddingServiceError(status=exc.code, message=_safe_error_text(exc)) from None
        except TimeoutError:
            raise EmbeddingTimeout(timeout_seconds=timeout) from None
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                raise EmbeddingTimeout(timeout_seconds=timeout) from None
            raise EmbeddingServiceError(
                status=0, message=f"connection failed: {_safe_reason(reason)}"
            ) from None
        except OSError as exc:
            raise EmbeddingServiceError(
                status=0, message=f"transport error: {type(exc).__name__}"
            ) from None
        latency = time.monotonic() - started
        if status != 200:
            raise EmbeddingServiceError(status=status, message="unexpected status")
        vector, usage = _parse_embeddings_response(raw)
        digest_source = _digest_source(item)
        return EmbedResult(
            vector=vector,
            model=self._model,
            dim=len(vector),
            input_kind=item.part_type,
            input_sha256=hashlib.sha256(digest_source).hexdigest(),
            input_bytes=len(digest_source),
            latency_seconds=latency,
            prompt_tokens=_as_int(usage.get("prompt_tokens")),
            raw_response=raw,
        )


def _input_element(item: EmbedInput) -> Any:
    """Build one ``input`` element in the verified wire shape."""

    if item.part_type == "text":
        if not item.text:
            raise EmbeddingServiceError(status=0, message="empty text input")
        return item.text
    part_type = _MEDIA_PART_TYPES.get(item.part_type)
    if part_type is None:
        raise EmbeddingServiceError(status=0, message=f"unsupported input kind {item.part_type!r}")
    if not item.data:
        raise EmbeddingServiceError(status=0, message="empty media input")
    media_type = item.media_type or "application/octet-stream"
    data_url = f"data:{media_type};base64,{base64.b64encode(item.data).decode('ascii')}"
    if part_type == "image_url":
        part = {"type": "image_url", "image_url": {"url": data_url}}
    else:
        part = {"type": "input_audio", "input_audio": {"data": data_url}}
    return {"content": [part]}


def _digest_source(item: EmbedInput) -> bytes:
    if item.part_type == "text":
        return (item.text or "").encode("utf-8")
    return item.data or b""


def _parse_embeddings_response(raw: str) -> tuple[tuple[float, ...], dict[str, Any]]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise EmbeddingServiceError(status=200, message="response was not valid JSON") from None
    if not isinstance(payload, dict):
        raise EmbeddingServiceError(status=200, message="response was not a JSON object")
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise EmbeddingServiceError(status=200, message="response contained no data")
    first = data[0]
    embedding = first.get("embedding") if isinstance(first, dict) else None
    if not isinstance(embedding, list) or not embedding:
        raise EmbeddingServiceError(status=200, message="response had no embedding vector")
    vector: list[float] = []
    for value in embedding:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise EmbeddingServiceError(status=200, message="embedding contained non-numeric values")
        number = float(value)
        if not math.isfinite(number):
            raise EmbeddingServiceError(status=200, message="embedding contained non-finite values")
        vector.append(number)
    usage = payload.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    return tuple(vector), usage


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


#: Environment variables for the embedding backend.  Optional; nothing is
#: hard-coded to a LAN host (the only authorized candidate is a test endpoint).
ENV_VECTOR_BASE_URL = "LIGHTGRAVITY_VECTOR_BASE_URL"
ENV_VECTOR_MODEL = "LIGHTGRAVITY_VECTOR_MODEL"
ENV_VECTOR_TOKEN = "LIGHTGRAVITY_VECTOR_TOKEN"
ENV_VECTOR_TIMEOUT = "LIGHTGRAVITY_VECTOR_TIMEOUT_SECONDS"
ENV_VECTOR_COLD_TIMEOUT = "LIGHTGRAVITY_VECTOR_COLD_TIMEOUT_SECONDS"
#: Optional expected dimension override; the live vector still records its own.
ENV_VECTOR_DIM = "LIGHTGRAVITY_VECTOR_DIM"


def backend_from_env(env: Any = None) -> EmbeddingBackend:
    """Build the configured embedding backend, or an honest unavailable stub.

    Missing configuration yields :class:`UnavailableEmbeddingBackend` so the
    optional vector path stays disabled, lexical search and original viewing
    keep working, and no unknown service is contacted.  No default host.
    """

    import os

    source = os.environ if env is None else env
    base_url = (source.get(ENV_VECTOR_BASE_URL) or "").strip()
    model = (source.get(ENV_VECTOR_MODEL) or "").strip()
    if not base_url or not model:
        return UnavailableEmbeddingBackend(
            f"{ENV_VECTOR_BASE_URL}/{ENV_VECTOR_MODEL} are not set; vector index stays disabled"
        )
    token = (source.get(ENV_VECTOR_TOKEN) or "").strip() or None
    kwargs: dict[str, Any] = {"base_url": base_url, "model": model, "bearer_token": token}
    if (value := _float_env(source, ENV_VECTOR_TIMEOUT)) is not None:
        kwargs["default_timeout_seconds"] = value
    if (value := _float_env(source, ENV_VECTOR_COLD_TIMEOUT)) is not None:
        kwargs["cold_timeout_seconds"] = value
    return OpenAICompatEmbeddingBackend(**kwargs)


def _float_env(source: Any, key: str) -> float | None:
    raw = source.get(key)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    """Cosine similarity of two equal-length vectors (0.0 when degenerate)."""

    a = tuple(float(x) for x in left)
    b = tuple(float(x) for x in right)
    if not a or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_COLD_TIMEOUT_SECONDS",
    "ENV_VECTOR_BASE_URL",
    "ENV_VECTOR_MODEL",
    "ENV_VECTOR_TOKEN",
    "ENV_VECTOR_TIMEOUT",
    "ENV_VECTOR_COLD_TIMEOUT",
    "ENV_VECTOR_DIM",
    "EmbedInput",
    "EmbedResult",
    "EmbeddingBackend",
    "EmbeddingServiceError",
    "EmbeddingTimeout",
    "EmbeddingUnavailable",
    "OpenAICompatEmbeddingBackend",
    "UnavailableEmbeddingBackend",
    "backend_from_env",
    "cosine_similarity",
]
