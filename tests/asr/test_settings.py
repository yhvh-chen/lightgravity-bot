"""Protected English ASR settings: own revision, validation and safe disable."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from lightgravity.asr import build_english_asr_service
from lightgravity.contracts import AppError, ErrorCode
from lightgravity.store.errors import RevisionConflict

from asr_helpers import FakeRuntime, make_repository


def _service(tmp_path: Path, factory: Any = None) -> Any:
    return build_english_asr_service(
        make_repository(tmp_path), runtime_factory=factory or (lambda config: FakeRuntime())
    )


def _enable(service: Any, encoder: Path, reader: Path, **extra: Any) -> dict[str, Any]:
    payload = {
        "enabled": True,
        "model_dir": str(encoder),
        "reader_dir": str(reader),
        **extra,
    }
    return service.update(0, payload, actor="test")


def test_default_view_is_disabled_and_never_leaks_paths(tmp_path: Path) -> None:
    service = _service(tmp_path)
    view = service.view()
    assert view["revision"] == 0
    assert view["content_hash"] == ""
    assert view["configured"] is False
    assert view["enabled"] is False
    assert view["available"] is False
    assert view["reason"] == "disabled"
    assert view["language"] == "en"
    assert view["timestamps_supported"] is False
    assert view["models"]["encoder"]["id"].startswith("google/embeddinggemma-2")
    assert "model_dir" not in view
    assert "reader_dir" not in view
    assert service.capability() == {
        "available": False,
        "reason": "disabled",
        "configured": False,
        "enabled": False,
    }


def test_first_create_revision_and_save_performs_zero_inference(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    calls: list[Any] = []

    def factory(config: Any) -> FakeRuntime:
        calls.append(config)
        return FakeRuntime()

    service = _service(tmp_path, factory)
    encoder, reader = fake_models
    result = _enable(service, encoder, reader)
    assert result["revision"] == 0
    assert result["content_hash"]
    assert result["english_asr"]["revision"] == result["revision"]
    assert result["english_asr"]["content_hash"] == result["content_hash"]
    assert result["english_asr"]["available"] is True
    assert result["english_asr"]["configured"] is True
    assert "model_dir" not in result["english_asr"]
    assert calls == []  # save validates files/hashes only

    # The next write uses the capability's own revision (not global settings).
    updated = service.update(
        0,
        {"enabled": True, "threads": 2},
        actor="test",
    )
    assert updated["revision"] == 1
    assert updated["english_asr"]["revision"] == 1


def test_omitted_paths_are_retained_and_explicit_null_is_rejected(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    service = _service(tmp_path)
    encoder, reader = fake_models
    _enable(service, encoder, reader)
    disabled = service.update(0, {"enabled": False}, actor="test")
    assert disabled["english_asr"]["reason"] == "disabled"
    enabled = service.update(1, {"enabled": True}, actor="test")
    assert enabled["english_asr"]["available"] is True

    with pytest.raises(AppError) as raised:
        service.update(2, {"enabled": True, "model_dir": None}, actor="test")
    assert raised.value.code is ErrorCode.VALIDATION_FAILED
    after = service.view()
    assert after["revision"] == 2  # failed write did not advance/persist
    assert after["available"] is True


def test_invalid_path_or_hash_is_not_persisted(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    service = _service(tmp_path)
    encoder, reader = fake_models
    with pytest.raises(AppError) as missing:
        service.update(
            0,
            {"enabled": True, "model_dir": str(tmp_path / "missing"), "reader_dir": str(reader)},
            actor="test",
        )
    assert missing.value.code is ErrorCode.VALIDATION_FAILED
    assert service.view()["configured"] is False

    (encoder / "model.safetensors").write_bytes(b"tampered")
    with pytest.raises(AppError) as mismatch:
        service.update(
            0,
            {"enabled": True, "model_dir": str(encoder), "reader_dir": str(reader)},
            actor="test",
        )
    assert mismatch.value.code is ErrorCode.VALIDATION_FAILED
    assert service.view()["configured"] is False


def test_safe_disable_may_keep_missing_models_with_honest_reason(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    service = _service(tmp_path)
    encoder, reader = fake_models
    _enable(service, encoder, reader)
    (reader / "reader.pt").unlink()
    disabled = service.update(0, {"enabled": False}, actor="test")
    assert disabled["english_asr"]["enabled"] is False
    assert disabled["english_asr"]["available"] is False
    assert disabled["english_asr"]["reason"] == "model_missing"
    assert disabled["english_asr"]["configured"] is True


def test_stale_expected_revision_is_a_conflict(
    tmp_path: Path, fake_models: tuple[Path, Path]
) -> None:
    service = _service(tmp_path)
    encoder, reader = fake_models
    _enable(service, encoder, reader)
    with pytest.raises(RevisionConflict) as raised:
        service.update(7, {"enabled": False}, actor="test")
    assert raised.value.code is ErrorCode.REVISION_CONFLICT
    assert raised.value.http_status == 409


def test_runtime_required_for_health_capability(
    tmp_path: Path, fake_models: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    service = build_english_asr_service(make_repository(tmp_path))
    encoder, reader = fake_models
    _enable(service, encoder, reader)
    monkeypatch.setattr(
        "lightgravity.asr.service._runtime_dependencies_importable", lambda: False
    )
    view = service.view()
    assert view["enabled"] is True
    assert view["configured"] is True
    assert view["available"] is False
    assert view["reason"] == "runtime_unavailable"


def test_default_application_settings_view_is_present_with_disabled_processing(
    tmp_path: Path,
) -> None:
    from lightgravity.settings import ConnectionService, FileSecretStore
    from lightgravity.store import FileStore

    store = FileStore(tmp_path / "data", tmp_path / "workspaces")
    service = ConnectionService(
        store,
        secret_store=FileSecretStore(tmp_path / "secrets"),
    )
    view = service.get_settings()["english_asr"]
    assert view["configured"] is False
    assert view["available"] is False
    assert view["reason"] == "disabled"


def test_importing_public_asr_package_does_not_import_torch() -> None:
    code = (
        "import sys\n"
        "import lightgravity.asr\n"
        "raise SystemExit(1 if 'torch' in sys.modules else 0)\n"
    )
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "backend") + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    completed = subprocess.run([sys.executable, "-c", code], check=False, env=env)
    assert completed.returncode == 0
