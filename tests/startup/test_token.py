"""Runtime token handshake: memory-only, no persistence, HTML injection (LG-020)."""

from __future__ import annotations

from pathlib import Path

from lightgravity.api.bootstrap import StartupOptions, build_runtime
from lightgravity.config import Settings
from lightgravity.runtime.token import (
    RUNTIME_TOKEN_ENV,
    RuntimeToken,
    inject_runtime_token,
    resolve_runtime_token,
)


def test_generated_token_is_random_and_not_source_environment() -> None:
    first = resolve_runtime_token({})
    second = resolve_runtime_token({})
    assert first.source == "generated"
    assert len(first.value) >= 32
    assert first.value != second.value


def test_environment_token_is_respected_without_leaking() -> None:
    token = resolve_runtime_token({RUNTIME_TOKEN_ENV: "  injected-value  "})
    assert token == RuntimeToken("injected-value", "environment")
    assert "injected-value" not in repr(token)


def test_inject_runtime_token_into_head() -> None:
    html = "<html><head><title>t</title></head><body></body></html>"
    injected = inject_runtime_token(html, "abc123")
    assert injected.index("__LG_RUNTIME_TOKEN__") > injected.index("<head>")
    assert injected.index("__LG_RUNTIME_TOKEN__") < injected.index("</head>")
    assert '"abc123"' in injected


def test_inject_runtime_token_without_head_prepends() -> None:
    injected = inject_runtime_token("<p>bare</p>", "xyz")
    assert injected.startswith("<script>")
    assert '"xyz"' in injected


def test_token_value_is_not_persisted_to_disk(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        workspace_root=tmp_path / "data" / "workspaces",
        secret_store=tmp_path / "secrets",
    )
    token = resolve_runtime_token({})
    state = build_runtime(
        StartupOptions(settings=settings, token=token, serve_frontend=False)
    )
    # The app really carries the token for the access policy...
    assert state.token.value == token.value
    # ...but nothing under the runtime data/secret roots contains the value.
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert token.value not in path.read_text("utf-8", errors="ignore")
