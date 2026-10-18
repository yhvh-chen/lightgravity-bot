"""Native Google Gemini audio transcription over plain HTTP (docs/08 §23).

This module is intentionally narrow:

* one inline ``POST <base_url>/interactions`` request per ASR attempt;
* authentication only through the ``x-goog-api-key`` header;
* no SDK, Files API, fallback provider, model roulette or automatic retry;
* response text only from completed ``model_output`` text parts.

The transport is injectable so boundary tests can replay the recorded LG-235
responses without any network or real Google credential.  The default
transport uses ``http.client`` from the standard library and distinguishes
"connected but body may have been sent" from connection/DNS/TLS failures so the
caller can be honest about stop confirmation.
"""

from __future__ import annotations

import base64
import http.client
import json
import socket
import ssl
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlparse

from .provider_contract import (
    GOOGLE_ALLOWED_HOST,
    GOOGLE_ALLOWED_PATH,
    GOOGLE_AUTH_HEADER,
    GOOGLE_INTERACTIONS_PATH,
    GOOGLE_PROMPT,
    GOOGLE_PROMPT_VERSION,
    GOOGLE_SUPPORTED_AUDIO_MIME_TYPES,
)

# Additive reasons used only by the Google path (docs/08 §23.7).
REASON_AUTH_FAILED = "asr_auth_failed"
REASON_RATE_LIMITED = "asr_rate_limited"
REASON_MODEL_UNAVAILABLE = "asr_model_unavailable"
REASON_PROVIDER_UNAVAILABLE = "asr_provider_unavailable"
REASON_INVALID_REQUEST = "asr_invalid_request"
REASON_REFUSED = "asr_refused"
REASON_EMPTY_RESPONSE = "asr_empty_response"
REASON_RESPONSE_INVALID = "asr_response_invalid"
REASON_STOP_UNCONFIRMED = "asr_stop_unconfirmed"

_USAGE_KEYS = (
    "total_tokens",
    "total_input_tokens",
    "input_tokens_by_modality",
    "total_output_tokens",
    "total_thought_tokens",
    "total_cached_tokens",
    "total_tool_use_tokens",
)

_REFUSAL_STATUSES = frozenset(
    {"refused", "blocked", "safety", "rejected", "denied", "policy_violation"}
)

# Extension fallback is only used after magic sniffing.  It never guesses an
# unknown/non-audio extension: the caller gets a pre-dispatch failure instead.
_EXTENSION_MIME = {
    ".wav": "audio/wav",
    ".wave": "audio/wav",
    ".mp3": "audio/mpeg",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
    ".aif": "audio/aiff",
    ".aiff": "audio/aiff",
    ".aifc": "audio/aiff",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
}


class GoogleTransportError(Exception):
    """Transport failure with enough truth to classify stop confirmation.

    ``sent`` is true once the HTTP request line/body may have left the process.
    The exception never contains the credential, request body or response body.
    """

    def __init__(self, message: str, *, sent: bool) -> None:
        super().__init__(message)
        self.sent = sent


class GoogleNativeError(Exception):
    """Protocol/provider failure mapped to one frozen ASR reason."""

    def __init__(
        self,
        reason: str,
        *,
        stop_confirmed: bool = True,
        error_code: str | None = "capability_unavailable",
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.stop_confirmed = stop_confirmed
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class GoogleNativeResult:
    text: str
    latency_seconds: float
    request_bytes: int
    endpoint_host: str
    endpoint_path: str
    usage: dict[str, Any] | None


class GoogleHttpTransport(Protocol):
    def post(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]: ...


class HttpConnectionTransport:
    """Standard-library HTTPS transport with explicit connect/dispatch split."""

    def post(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, bytes]:
        parsed = urlparse(url)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() != GOOGLE_ALLOWED_HOST:
            raise GoogleTransportError("unsupported endpoint", sent=False)
        connection = http.client.HTTPSConnection(
            GOOGLE_ALLOWED_HOST,
            parsed.port or 443,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        try:
            # A failure here proves no request body left this process.
            try:
                connection.connect()
            except (socket.gaierror, ssl.SSLError, OSError, TimeoutError) as exc:
                raise GoogleTransportError(
                    f"connection failed ({type(exc).__name__})", sent=False
                ) from exc
            try:
                connection.request(
                    "POST",
                    parsed.path or f"{GOOGLE_ALLOWED_PATH}{GOOGLE_INTERACTIONS_PATH}",
                    body=body,
                    headers=dict(headers),
                )
                response = connection.getresponse()
                payload = response.read()
                return int(response.status), payload
            except (OSError, TimeoutError, http.client.HTTPException) as exc:
                # Once dispatch starts, a timeout/reset cannot prove the remote
                # stopped; the caller parks the job as unknown instead of
                # pretending success/failure or replaying it.
                raise GoogleTransportError(
                    f"request outcome unknown ({type(exc).__name__})", sent=True
                ) from exc
        finally:
            connection.close()


def detect_audio_mime(filename: str | None, data: bytes) -> str | None:
    """Return an explicit supported audio MIME type, or ``None``.

    Magic bytes take precedence over the filename extension.  Unknown formats
    are rejected before any request is built or sent.
    """

    head = data[:16]
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "audio/wav"
    if head.startswith(b"FORM") and head[8:12] in (b"AIFF", b"AIFC"):
        return "audio/aiff"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"fLaC"):
        return "audio/flac"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "audio/webm"
    if head.startswith(b"ID3"):
        return "audio/mpeg"
    if len(head) >= 2 and head[0] == 0xFF:
        # ADTS AAC uses layer bits 00; MPEG audio uses a non-zero layer.
        if head[1] & 0xF6 == 0xF0:
            return "audio/aac"
        if head[1] & 0xE0 == 0xE0:
            return "audio/mpeg"
    if filename:
        lowered = filename.lower()
        for extension, mime in _EXTENSION_MIME.items():
            if lowered.endswith(extension):
                return mime
    return None


def build_request_body(model: str, audio: bytes, mime_type: str) -> bytes:
    """Serialize the frozen inline-audio request body (no credential)."""

    if mime_type not in GOOGLE_SUPPORTED_AUDIO_MIME_TYPES:
        raise ValueError("unsupported audio MIME type")
    payload = {
        "model": model,
        "input": [
            {"type": "text", "text": GOOGLE_PROMPT},
            {
                "type": "audio",
                "data": base64.b64encode(audio).decode("ascii"),
                "mime_type": mime_type,
            },
        ],
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _usage_from(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        return None
    result: dict[str, Any] = {}
    for key in _USAGE_KEYS:
        value = usage.get(key)
        result[key] = value if isinstance(value, (int, list)) and not isinstance(value, bool) else None
    return result


def parse_response(payload: bytes) -> tuple[str, dict[str, Any] | None]:
    """Extract only completed ``model_output`` text parts.

    A real thought step (``type=thought``) is ignored.  A literal word such as
    ``thought`` inside the model_output text is model output and is preserved.
    """

    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise GoogleNativeError(REASON_RESPONSE_INVALID) from exc
    if not isinstance(data, dict):
        raise GoogleNativeError(REASON_RESPONSE_INVALID)
    status = data.get("status")
    if status != "completed":
        if isinstance(status, str) and status.lower() in _REFUSAL_STATUSES:
            raise GoogleNativeError(REASON_REFUSED)
        if data.get("error") is not None:
            raise GoogleNativeError(REASON_REFUSED)
        raise GoogleNativeError(REASON_RESPONSE_INVALID)
    steps = data.get("steps")
    if not isinstance(steps, list):
        raise GoogleNativeError(REASON_RESPONSE_INVALID)
    parts: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            raise GoogleNativeError(REASON_RESPONSE_INVALID)
        if step.get("type") != "model_output":
            # The real H1/H2 responses include a thought step with signature.
            # It is metadata, never transcript text.
            continue
        content = step.get("content")
        if not isinstance(content, list):
            raise GoogleNativeError(REASON_RESPONSE_INVALID)
        for part in content:
            if not isinstance(part, dict):
                raise GoogleNativeError(REASON_RESPONSE_INVALID)
            if part.get("type") != "text":
                continue
            text = part.get("text")
            if not isinstance(text, str):
                raise GoogleNativeError(REASON_RESPONSE_INVALID)
            parts.append(text)
    text = "\n".join(parts).strip()
    if not text:
        raise GoogleNativeError(REASON_EMPTY_RESPONSE)
    return text, _usage_from(data)


def _map_status(status: int) -> GoogleNativeError:
    if status in (401, 403):
        return GoogleNativeError(REASON_AUTH_FAILED)
    if status == 404:
        return GoogleNativeError(REASON_MODEL_UNAVAILABLE)
    if status == 429:
        return GoogleNativeError(REASON_RATE_LIMITED)
    if status in (400, 413, 422):
        return GoogleNativeError(REASON_INVALID_REQUEST, error_code="validation_failed")
    if 500 <= status <= 599:
        return GoogleNativeError(REASON_PROVIDER_UNAVAILABLE)
    return GoogleNativeError(REASON_PROVIDER_UNAVAILABLE)


class GoogleNativeClient:
    """One bounded native transcription call (no retry and no fallback)."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        transport: GoogleHttpTransport | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._transport = transport or HttpConnectionTransport()

    def endpoint(self) -> tuple[str, str, str]:
        parsed = urlparse(self._base_url)
        host = (parsed.hostname or "").lower()
        path = f"{parsed.path.rstrip('/')}{GOOGLE_INTERACTIONS_PATH}"
        return f"https://{host}{path}", host, path

    def transcribe(
        self,
        body: bytes,
        *,
        timeout: float = 180.0,
        cancel_check: Callable[[], bool] | None = None,
    ) -> GoogleNativeResult:
        url, host, path = self.endpoint()
        headers = {
            "Content-Type": "application/json",
            GOOGLE_AUTH_HEADER: self._api_key,
        }
        if cancel_check is not None and cancel_check():
            raise GoogleNativeError("cancelled", stop_confirmed=True, error_code=None)
        started = time.monotonic()
        try:
            status, payload = self._transport.post(
                url=url,
                headers=headers,
                body=body,
                timeout=timeout,
            )
        except GoogleTransportError as exc:
            if exc.sent:
                raise GoogleNativeError(
                    REASON_STOP_UNCONFIRMED,
                    stop_confirmed=False,
                    error_code="capability_unavailable",
                ) from exc
            raise GoogleNativeError(REASON_PROVIDER_UNAVAILABLE) from exc
        latency = time.monotonic() - started
        if status != 200:
            raise _map_status(status)
        text, usage = parse_response(payload)
        return GoogleNativeResult(
            text=text,
            latency_seconds=latency,
            request_bytes=len(body),
            endpoint_host=host,
            endpoint_path=path,
            usage=usage,
        )


__all__ = [
    "GoogleHttpTransport",
    "GoogleNativeClient",
    "GoogleNativeError",
    "GoogleNativeResult",
    "GoogleTransportError",
    "HttpConnectionTransport",
    "REASON_AUTH_FAILED",
    "REASON_EMPTY_RESPONSE",
    "REASON_INVALID_REQUEST",
    "REASON_MODEL_UNAVAILABLE",
    "REASON_PROVIDER_UNAVAILABLE",
    "REASON_RATE_LIMITED",
    "REASON_REFUSED",
    "REASON_RESPONSE_INVALID",
    "REASON_STOP_UNCONFIRMED",
    "build_request_body",
    "detect_audio_mime",
    "parse_response",
]
