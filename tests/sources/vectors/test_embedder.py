"""Embedder adapter unit tests (LG-037) — no network.

They verify the wire shape (text vs verified multimodal ``content`` parts) and
that errors are honest, using monkeypatched ``urlopen`` so no real service is
contacted.
"""

from __future__ import annotations

import json

import pytest

from lightgravity.sources.vectors import (
    EmbedInput,
    EmbeddingServiceError,
    EmbeddingUnavailable,
    OpenAICompatEmbeddingBackend,
    UnavailableEmbeddingBackend,
    backend_from_env,
)
from lightgravity.sources.vectors.embedder import (
    ENV_VECTOR_BASE_URL,
    ENV_VECTOR_MODEL,
    _input_element,
)


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")
        self.status = 200

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc) -> None:
        return None


def _vector_payload(dim: int = 3) -> dict:
    return {"data": [{"embedding": [0.1] * dim}], "usage": {"prompt_tokens": 5}}


def test_backend_from_env_disabled_without_config():
    backend = backend_from_env({})
    assert isinstance(backend, UnavailableEmbeddingBackend)
    assert backend.configured is False
    with pytest.raises(EmbeddingUnavailable):
        backend.embed(EmbedInput.text_input("x"))


def test_backend_from_env_builds_with_config():
    backend = backend_from_env(
        {ENV_VECTOR_BASE_URL: "http://example.test:11434", ENV_VECTOR_MODEL: "embeddinggemma-2"}
    )
    assert isinstance(backend, OpenAICompatEmbeddingBackend)
    assert backend.configured is True
    assert backend.model_id == "embeddinggemma-2"


def test_text_input_element_is_plain_string():
    assert _input_element(EmbedInput.text_input("hello")) == "hello"


def test_image_input_element_uses_verified_content_shape():
    element = _input_element(EmbedInput.image(b"PNGDATA", "image/png"))
    assert isinstance(element, dict)
    assert list(element) == ["content"]
    part = element["content"][0]
    assert part["type"] == "image_url"
    assert part["image_url"]["url"].startswith("data:image/png;base64,")


def test_audio_input_element_uses_verified_content_shape():
    element = _input_element(EmbedInput.audio(b"RIFF", "audio/wav"))
    part = element["content"][0]
    assert part["type"] == "input_audio"
    assert "data:audio/wav;base64," in part["input_audio"]["data"]


def test_embed_parses_vector(monkeypatch):
    backend = OpenAICompatEmbeddingBackend(base_url="http://x:1", model="m")
    seen: dict = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(_vector_payload(3))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = backend.embed(EmbedInput.text_input("hello"))
    assert result.dim == 3
    assert result.model == "m"
    assert result.input_kind == "text"
    assert seen["url"].endswith("/v1/embeddings")
    assert seen["body"]["model"] == "m"
    assert seen["body"]["input"] == ["hello"]


def test_embed_rejects_non_numeric_vector(monkeypatch):
    backend = OpenAICompatEmbeddingBackend(base_url="http://x:1", model="m")

    def fake_urlopen(request, timeout):
        return _FakeResponse({"data": [{"embedding": ["nope"]}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(EmbeddingServiceError):
        backend.embed(EmbedInput.text_input("hello"))


def test_embed_rejects_empty_media():
    backend = OpenAICompatEmbeddingBackend(base_url="http://x:1", model="m")
    with pytest.raises(EmbeddingServiceError):
        backend.embed(EmbedInput.image(b"", "image/png"))
