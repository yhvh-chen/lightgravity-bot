"""Frozen 1.22.0 provider vocabulary (LG-235); no network or model runtime."""

from __future__ import annotations

import pytest

from lightgravity.asr.provider_contract import (
    GOOGLE_ALLOWED_HOST,
    GOOGLE_ALLOWED_PATH,
    GOOGLE_AUTH_HEADER,
    GOOGLE_DEFAULT_BASE_URL,
    GOOGLE_DEFAULT_MAX_AUDIO_BYTES,
    GOOGLE_DEFAULT_MODEL,
    GOOGLE_DEFAULT_TIMEOUT_SECONDS,
    GOOGLE_INTERACTIONS_PATH,
    GOOGLE_MAX_REQUEST_BYTES,
    GOOGLE_PROMPT,
    GOOGLE_PROMPT_VERSION,
    PROVIDER_EG2_READER,
    PROVIDER_GOOGLE_NATIVE,
    RUNTIME_GOOGLE_NATIVE,
    RUNTIME_INPROCESS,
    select_provider,
)


def test_legacy_block_without_provider_maps_to_inprocess_eg2() -> None:
    selected = select_provider({"enabled": False, "runtime": "inprocess"})
    assert selected.provider == PROVIDER_EG2_READER
    assert selected.runtime == RUNTIME_INPROCESS
    assert selected.legacy_default is True


def test_google_block_maps_to_native() -> None:
    selected = select_provider(
        {"enabled": True, "provider": "google-native", "runtime": "google-native"}
    )
    assert selected.provider == PROVIDER_GOOGLE_NATIVE
    assert selected.runtime == RUNTIME_GOOGLE_NATIVE
    assert selected.legacy_default is False


def test_google_runtime_may_be_omitted() -> None:
    selected = select_provider({"enabled": True, "provider": "google-native"})
    assert selected.runtime == RUNTIME_GOOGLE_NATIVE


@pytest.mark.parametrize(
    "block",
    [
        {"provider": "unknown"},
        {"provider": "eg2-reader", "runtime": "google-native"},
        {"provider": "google-native", "runtime": "inprocess"},
        {"runtime": "google-native"},
    ],
)
def test_unknown_or_mismatched_provider_is_rejected(block: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        select_provider(block)


def test_frozen_google_defaults_and_limits() -> None:
    assert GOOGLE_DEFAULT_MODEL == "gemini-3.8-flash"
    assert GOOGLE_DEFAULT_BASE_URL == "https://generativelanguage.googleapis.com/v1beta"
    assert GOOGLE_ALLOWED_HOST == "generativelanguage.googleapis.com"
    assert GOOGLE_ALLOWED_PATH == "/v1beta"
    assert GOOGLE_INTERACTIONS_PATH == "/interactions"
    assert GOOGLE_AUTH_HEADER == "x-goog-api-key"
    assert GOOGLE_MAX_REQUEST_BYTES == 20_000_000
    assert GOOGLE_DEFAULT_MAX_AUDIO_BYTES == 10_000_000
    assert GOOGLE_DEFAULT_TIMEOUT_SECONDS == 180
    assert GOOGLE_PROMPT_VERSION == "google-native-transcribe-v1"
    assert "verbatim" in GOOGLE_PROMPT
