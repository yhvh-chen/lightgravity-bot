"""Frozen provider/config vocabulary for contract 1.22.0 (LG-235 preparation).

This module is intentionally behaviour-free: it contains stable names, limits,
defaults and the legacy-provider discriminator that LG-236/237/238 can import
without duplicating literals.  It performs no network I/O, imports no model
runtime and never reads a credential.

Contract: ``probes/google-native-asr-20261018/lg235/CONTRACT.md`` and
``docs/08-interface-contract.md`` §23.  The Google path is a frozen candidate;
the public ``CONTRACT_VERSION`` is **not** changed here because the public
backend runtime is not implemented in LG-235.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# ------------------------------------------------------------------ providers
#: Legacy 1.20 local in-process EG2 Reader provider.
PROVIDER_EG2_READER = "eg2-reader"
#: Native Google Gemini audio provider (REST ``/v1beta/interactions``).
PROVIDER_GOOGLE_NATIVE = "google-native"
PROVIDER_VALUES = frozenset({PROVIDER_EG2_READER, PROVIDER_GOOGLE_NATIVE})

RUNTIME_INPROCESS = "inprocess"
RUNTIME_GOOGLE_NATIVE = "google-native"
RUNTIME_VALUES = frozenset({RUNTIME_INPROCESS, RUNTIME_GOOGLE_NATIVE})

# -------------------------------------------------------------------- defaults
GOOGLE_PROVIDER = "google"
GOOGLE_ALLOWED_HOST = "generativelanguage.googleapis.com"
GOOGLE_ALLOWED_PATH = "/v1beta"
GOOGLE_DEFAULT_BASE_URL = f"https://{GOOGLE_ALLOWED_HOST}{GOOGLE_ALLOWED_PATH}"
GOOGLE_INTERACTIONS_PATH = "/interactions"
GOOGLE_MODEL_METADATA_PATH = "/models/{model}"
GOOGLE_AUTH_HEADER = "x-goog-api-key"

#: Existing configured model used by the LG-235 probe.  This is a default, not
#: a hard allowlist; an administrator may set another safe native model id.
GOOGLE_DEFAULT_MODEL = "gemini-3.8-flash"
#: Official dedicated transcription model.  LG-235 did not call it and it must
#: not be assumed enabled or silently substituted after a failure.
GOOGLE_DEDICATED_TRANSCRIBE_MODEL = "gemini-3.5-transcribe"

# Official inline-audio limit: 20 MB total request size (prompt + all files).
GOOGLE_MAX_REQUEST_BYTES = 20_000_000
# Conservative raw-audio default; base64 expansion is checked against the
# official total request limit before dispatch.
GOOGLE_DEFAULT_MAX_AUDIO_BYTES = 10_000_000
GOOGLE_MAX_AUDIO_BYTES = 14_000_000
GOOGLE_DEFAULT_TIMEOUT_SECONDS = 180
GOOGLE_MIN_TIMEOUT_SECONDS = 30
GOOGLE_MAX_TIMEOUT_SECONDS = 600
GOOGLE_MAX_CONCURRENCY = 1

GOOGLE_PROMPT_VERSION = "google-native-transcribe-v1"
#: Fixed plain verbatim prompt.  No answer, name, place or number hints.
GOOGLE_PROMPT = (
    "Transcribe the speech in this audio verbatim. Return only the plain "
    "transcription text, with no commentary, labels, or formatting."
)

GOOGLE_SUPPORTED_AUDIO_MIME_TYPES = frozenset(
    {
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/mpeg",
        "audio/mp3",
        "audio/aiff",
        "audio/aac",
        "audio/ogg",
        "audio/flac",
        "audio/webm",
    }
)

# -------------------------------------------------------------------- reasons
#: Additive ``text.reason`` values used by the Google provider.  Existing 1.20
#: values (``asr_disabled``, ``asr_unavailable``, ``asr_failed``,
#: ``asr_timeout``, ``asr_stop_unconfirmed``, ``cancelled``, ...) remain valid.
GOOGLE_REASON_CODES = frozenset(
    {
        "asr_auth_failed",
        "asr_rate_limited",
        "asr_model_unavailable",
        "asr_provider_unavailable",
        "asr_invalid_request",
        "asr_refused",
        "asr_empty_response",
        "asr_response_invalid",
    }
)

#: Settings-view reasons added for the Google provider.  Legacy reasons stay
#: unchanged; ``available=true`` never means the key/model was verified.
GOOGLE_CONFIG_REASONS = frozenset(
    {
        "credential_missing",
        "model_unavailable",
    }
)


@dataclass(frozen=True, slots=True)
class ProviderSelection:
    """Resolved discriminator for one stored settings block."""

    provider: str
    runtime: str
    legacy_default: bool


def select_provider(block: Mapping[str, Any] | None) -> ProviderSelection:
    """Resolve the provider without mutating or validating the whole block.

    Legacy 1.20 blocks have no ``provider`` and must keep working unchanged.
    A missing provider therefore maps to ``eg2-reader`` + ``inprocess``.  A new
    Google block must use ``provider=google-native`` and may omit ``runtime``
    (defaults to ``google-native``) or set it explicitly to the same value.
    Unknown combinations raise ``ValueError`` so callers do not guess.
    """

    if block is None:
        return ProviderSelection(PROVIDER_EG2_READER, RUNTIME_INPROCESS, True)
    if not isinstance(block, Mapping):
        raise ValueError("settings block must be a mapping")
    raw_provider = block.get("provider")
    raw_runtime = block.get("runtime")
    if raw_provider is None:
        if raw_runtime not in (None, RUNTIME_INPROCESS):
            raise ValueError("legacy blocks can only use runtime=inprocess")
        return ProviderSelection(PROVIDER_EG2_READER, RUNTIME_INPROCESS, True)
    if raw_provider == PROVIDER_EG2_READER:
        if raw_runtime not in (None, RUNTIME_INPROCESS):
            raise ValueError("eg2-reader requires runtime=inprocess")
        return ProviderSelection(PROVIDER_EG2_READER, RUNTIME_INPROCESS, False)
    if raw_provider == PROVIDER_GOOGLE_NATIVE:
        if raw_runtime not in (None, RUNTIME_GOOGLE_NATIVE):
            raise ValueError("google-native requires runtime=google-native")
        return ProviderSelection(PROVIDER_GOOGLE_NATIVE, RUNTIME_GOOGLE_NATIVE, False)
    raise ValueError(f"unknown ASR provider: {raw_provider!r}")


__all__ = [
    "PROVIDER_EG2_READER",
    "PROVIDER_GOOGLE_NATIVE",
    "PROVIDER_VALUES",
    "RUNTIME_INPROCESS",
    "RUNTIME_GOOGLE_NATIVE",
    "RUNTIME_VALUES",
    "GOOGLE_PROVIDER",
    "GOOGLE_ALLOWED_HOST",
    "GOOGLE_ALLOWED_PATH",
    "GOOGLE_DEFAULT_BASE_URL",
    "GOOGLE_INTERACTIONS_PATH",
    "GOOGLE_MODEL_METADATA_PATH",
    "GOOGLE_AUTH_HEADER",
    "GOOGLE_DEFAULT_MODEL",
    "GOOGLE_DEDICATED_TRANSCRIBE_MODEL",
    "GOOGLE_MAX_REQUEST_BYTES",
    "GOOGLE_DEFAULT_MAX_AUDIO_BYTES",
    "GOOGLE_MAX_AUDIO_BYTES",
    "GOOGLE_DEFAULT_TIMEOUT_SECONDS",
    "GOOGLE_MIN_TIMEOUT_SECONDS",
    "GOOGLE_MAX_TIMEOUT_SECONDS",
    "GOOGLE_MAX_CONCURRENCY",
    "GOOGLE_PROMPT_VERSION",
    "GOOGLE_PROMPT",
    "GOOGLE_SUPPORTED_AUDIO_MIME_TYPES",
    "GOOGLE_REASON_CODES",
    "GOOGLE_CONFIG_REASONS",
    "ProviderSelection",
    "select_provider",
]
