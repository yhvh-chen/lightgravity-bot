"""English ASR settings/capability service and bounded local transcription.

Public assembly seams (docs/08 §21.6):

* :func:`build_english_asr_service` - owns all path/hash/config validation and
  exposes ``view``/``update``/``capability``/``snapshot``/``transcribe``.
* :func:`english_asr_capability` - pure read-only result for ``api/health.py``.
* :func:`build_english_asr_router` (in ``router.py``) - the protected settings
  PUT route; the integration owner includes it in ``api/app.py``.

Settings live in their own canonical Markdown document with revision/hash
(``settings/ENGLISH_ASR.md``).  A successful save performs file/hash validation
only: it never loads the model, runs inference, mutates sources or triggers a
reprocess.  In-flight work keeps an immutable snapshot; later operations read
the new snapshot without a GET primer.
"""

from __future__ import annotations

import importlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from lightgravity.contracts import AppError, ErrorCode
from lightgravity.settings.errors import SettingsConfigInvalid
from lightgravity.store.clock import to_iso, utcnow
from lightgravity.store.errors import ConfigInvalid

from .config import (
    EnglishAsrConfig,
    HashCache,
    InvalidModelPath,
    MissingModelFile,
    ModelHashMismatch,
    REASON_DISABLED,
    REASON_HASH_MISMATCH,
    REASON_INVALID_CONFIG,
    REASON_MODEL_MISSING,
    REASON_RUNTIME_UNAVAILABLE,
    parse_block,
    public_models,
    validate_config_paths,
    verify_model_dir,
)
from .pins import (
    DEFAULT_MAX_AUDIO_BYTES,
    DEFAULT_MAX_AUDIO_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    ENCODER_PIN,
    ENGINE,
    LANGUAGE,
    MAX_THREADS,
    MIN_THREADS,
    MODEL_VERSION,
    READER_PIN,
)
from .settings_store import EnglishAsrDocument, EnglishAsrSettingsStore

RuntimeFactory = Callable[[EnglishAsrConfig], Any]


@dataclass(frozen=True, slots=True)
class AsrSnapshot:
    """Immutable config/provenance snapshot for one operation."""

    revision: int
    content_hash: str
    config: EnglishAsrConfig
    configured: bool
    available: bool
    reason: str | None
    runtime_available: bool


@dataclass(frozen=True, slots=True)
class AsrOutcome:
    """Result of one bounded ASR branch attempt (never persisted here)."""

    status: str
    reason: str | None
    error_code: str | None
    text: str | None = None
    machine: dict[str, Any] | None = None
    latency_seconds: float = 0.0
    audio_seconds: float = 0.0
    stop_confirmed: bool = True


def _runtime_dependencies_importable() -> bool:
    """Import the optional runtime module (never called when the feature is off)."""

    try:
        importlib.import_module(f"{__package__}.runtime")
        return True
    except Exception:  # noqa: BLE001 - optional dependency boundary
        return False


def _validation_error(message: str, code: str, field: str) -> AppError:
    return AppError(
        ErrorCode.VALIDATION_FAILED,
        message,
        details={"diagnostics": [{"code": code, "location": field}]},
    )


class EnglishAsrService:
    """Store-backed settings + capability + one-instance CPU transcription."""

    def __init__(
        self,
        settings_repository: Any,
        *,
        env: Mapping[str, str] | None = None,
        runtime_factory: RuntimeFactory | None = None,
    ) -> None:
        data_dir = getattr(getattr(settings_repository, "store", None), "data_dir", None)
        if data_dir is None:
            raise ConfigInvalid("English ASR settings require a controlled data root")
        self._repository = settings_repository
        self._env = dict(env or {})
        self._factory = runtime_factory
        self._store = EnglishAsrSettingsStore(Path(data_dir))
        self._hash_cache = HashCache()
        self._runtime: Any | None = None
        self._runtime_key: tuple[str, str, int] | None = None
        self._runtime_lock = threading.Lock()

    # --------------------------------------------------------------- settings
    @property
    def repository(self) -> Any:
        return self._repository

    def _read_document(self) -> EnglishAsrDocument:
        return self._store.read()

    def _snapshot(self) -> AsrSnapshot:
        try:
            document = self._read_document()
        except (ConfigInvalid, OSError):
            config = EnglishAsrConfig()
            return AsrSnapshot(
                revision=0,
                content_hash="",
                config=config,
                configured=False,
                available=False,
                reason=REASON_INVALID_CONFIG,
                runtime_available=False,
            )
        if document.block is None:
            config = EnglishAsrConfig()
            return AsrSnapshot(
                revision=document.revision,
                content_hash=document.content_hash,
                config=config,
                configured=False,
                available=False,
                reason=REASON_DISABLED,
                runtime_available=False,
            )
        parsed, invalid = parse_block(document.block)
        if parsed is None or invalid is not None:
            return AsrSnapshot(
                revision=document.revision,
                content_hash=document.content_hash,
                config=EnglishAsrConfig(),
                configured=True,
                available=False,
                reason=REASON_INVALID_CONFIG,
                runtime_available=False,
            )
        config = parsed
        file_reason = validate_config_paths(config, cache=self._hash_cache)
        runtime_available = False
        if config.enabled and file_reason is None:
            runtime_available = self._factory is not None or _runtime_dependencies_importable()
        if file_reason is not None:
            reason: str | None = file_reason
        elif not config.enabled:
            reason = REASON_DISABLED
        elif not runtime_available:
            reason = REASON_RUNTIME_UNAVAILABLE
        else:
            reason = None
        return AsrSnapshot(
            revision=document.revision,
            content_hash=document.content_hash,
            config=config,
            configured=True,
            available=bool(config.enabled and reason is None),
            reason=reason,
            runtime_available=runtime_available,
        )

    def snapshot(self) -> AsrSnapshot:
        return self._snapshot()

    def view(self, settings: Any | None = None) -> dict[str, Any]:
        """Public GET view; never returns model/reader paths or transcript text."""

        snap = self._snapshot()
        return {
            "revision": snap.revision,
            "content_hash": snap.content_hash,
            "enabled": snap.config.enabled,
            "runtime": snap.config.runtime,
            "configured": snap.configured,
            "available": snap.available,
            "reason": snap.reason,
            "language": LANGUAGE,
            "timestamps_supported": False,
            "models": public_models(),
            "limits": {
                "max_audio_seconds": snap.config.max_audio_seconds,
                "max_audio_bytes": snap.config.max_audio_bytes,
                "timeout_seconds": snap.config.timeout_seconds,
                "max_concurrency": 1,
            },
        }

    def capability(self) -> dict[str, Any]:
        snap = self._snapshot()
        return {
            "available": snap.available,
            "reason": snap.reason,
            "configured": snap.configured,
            "enabled": snap.config.enabled,
        }

    def settings_enabled(self) -> bool:
        """Cheap pure read used only for the new-job ``max_asr_calls`` value."""

        try:
            document = self._read_document()
        except (ConfigInvalid, OSError):
            return False
        config, invalid = parse_block(document.block)
        return bool(config is not None and invalid is None and config.enabled)

    # ------------------------------------------------------------------ update
    def update(
        self,
        expected_revision: int,
        payload: Mapping[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise _validation_error(
                "expected_revision must be an integer", "expected_revision_invalid", "expected_revision"
            )
        try:
            document = self._read_document()
        except (ConfigInvalid, OSError) as exc:
            raise SettingsConfigInvalid(
                "the existing English ASR settings document is invalid and cannot be updated",
                diagnostics=[{"code": "invalid_config", "location": str(self._store.path)}],
            ) from exc
        current, current_invalid = parse_block(document.block)
        if current is None or current_invalid is not None:
            current = EnglishAsrConfig()

        if "enabled" not in payload or not isinstance(payload.get("enabled"), bool):
            raise _validation_error("enabled must be a boolean", "enabled_invalid", "enabled")
        enabled = bool(payload["enabled"])

        runtime = payload.get("runtime", current.runtime)
        if runtime != "inprocess":
            raise _validation_error(
                "runtime must be 'inprocess'", "runtime_invalid", "runtime"
            )
        device = payload.get("device", current.device)
        if device != "cpu":
            raise _validation_error("device must be 'cpu'", "device_invalid", "device")

        threads = self._int_field(payload, "threads", current.threads, MIN_THREADS, MAX_THREADS)
        timeout_seconds = self._int_field(
            payload, "timeout_seconds", current.timeout_seconds, 30, DEFAULT_TIMEOUT_SECONDS
        )
        max_audio_seconds = self._int_field(
            payload,
            "max_audio_seconds",
            current.max_audio_seconds,
            1,
            DEFAULT_MAX_AUDIO_SECONDS,
        )
        max_audio_bytes = self._int_field(
            payload,
            "max_audio_bytes",
            current.max_audio_bytes,
            1,
            DEFAULT_MAX_AUDIO_BYTES,
        )

        model_supplied = "model_dir" in payload
        reader_supplied = "reader_dir" in payload
        model_dir = self._path_field(payload, "model_dir", current.model_dir)
        reader_dir = self._path_field(payload, "reader_dir", current.reader_dir)
        if model_supplied and model_dir is not None:
            self._validate_supplied_path(model_dir, ENCODER_PIN, "model_dir")
        if reader_supplied and reader_dir is not None:
            self._validate_supplied_path(reader_dir, READER_PIN, "reader_dir")
        if enabled:
            if model_dir is None or reader_dir is None:
                raise _validation_error(
                    "the first enable requires both absolute model_dir and reader_dir",
                    "model_paths_missing",
                    "model_dir",
                )
            self._validate_supplied_path(model_dir, ENCODER_PIN, "model_dir")
            self._validate_supplied_path(reader_dir, READER_PIN, "reader_dir")

        config = EnglishAsrConfig(
            enabled=enabled,
            runtime=str(runtime),
            model_dir=model_dir,
            reader_dir=reader_dir,
            device=str(device),
            threads=threads,
            timeout_seconds=timeout_seconds,
            max_audio_seconds=max_audio_seconds,
            max_audio_bytes=max_audio_bytes,
        )
        written = self._store.write(
            config.persisted_block(), expected_revision=expected_revision
        )
        return {
            "revision": written.revision,
            "content_hash": written.content_hash,
            "english_asr": self.view(),
        }

    def _int_field(
        self,
        payload: Mapping[str, Any],
        field: str,
        current: int,
        minimum: int,
        maximum: int,
    ) -> int:
        if field not in payload:
            return current
        value = payload[field]
        if isinstance(value, bool) or not isinstance(value, int) or not (minimum <= value <= maximum):
            raise _validation_error(
                f"{field} must be an integer in [{minimum}, {maximum}]",
                f"{field}_invalid",
                field,
            )
        return value

    def _path_field(
        self,
        payload: Mapping[str, Any],
        field: str,
        current: str | None,
    ) -> str | None:
        if field not in payload:
            return current
        value = payload[field]
        if not isinstance(value, str) or not value.strip():
            raise _validation_error(
                f"{field} must be a non-empty absolute local directory",
                f"{field}_invalid",
                field,
            )
        return value.strip()

    def _validate_supplied_path(self, value: str, pin: Any, field: str) -> None:
        if "://" in value or not Path(value).is_absolute():
            raise _validation_error(
                f"{field} must be an absolute local directory",
                f"{field}_invalid",
                field,
            )
        try:
            verify_model_dir(value, pin, cache=self._hash_cache)
        except (MissingModelFile, InvalidModelPath):
            raise _validation_error(
                f"{field} does not contain the pinned files",
                f"{field}_missing",
                field,
            ) from None
        except ModelHashMismatch:
            raise _validation_error(
                f"{field} contains files whose SHA-256 does not match the pinned values",
                f"{field}_hash_mismatch",
                field,
            ) from None
        except OSError:
            raise _validation_error(
                f"{field} is not readable", f"{field}_unreadable", field
            ) from None

    # -------------------------------------------------------------- transcribe
    def transcribe(
        self,
        data: bytes,
        *,
        filename: str = "audio",
        cancel_check: Callable[[], bool] | None = None,
    ) -> AsrOutcome:
        """One bounded attempt; no retry, no writes and no late output persistence."""

        snap = self._snapshot()
        config = snap.config
        if not config.enabled:
            return AsrOutcome("unavailable", "asr_disabled", None)
        if snap.reason is not None and not snap.available:
            if snap.reason in (
                REASON_MODEL_MISSING,
                REASON_HASH_MISMATCH,
                REASON_INVALID_CONFIG,
                REASON_RUNTIME_UNAVAILABLE,
            ):
                return AsrOutcome("unavailable", "asr_unavailable", "capability_unavailable")
        if not isinstance(data, bytes) or not data:
            return AsrOutcome(
                "failed", "audio_decode_failed", "validation_failed", stop_confirmed=True
            )
        limit_bytes = min(config.max_audio_bytes, DEFAULT_MAX_AUDIO_BYTES)
        if len(data) > limit_bytes:
            return AsrOutcome(
                "failed", "audio_too_long", "validation_failed", stop_confirmed=True
            )
        if cancel_check is not None and cancel_check():
            return AsrOutcome("unavailable", "cancelled", None, stop_confirmed=True)

        if cancel_check is not None and cancel_check():
            return AsrOutcome("unavailable", "cancelled", None, stop_confirmed=True)

        runtime = self._runtime_for(snap)
        if runtime is None:
            return AsrOutcome("unavailable", "asr_unavailable", "capability_unavailable")

        result: dict[str, Any] = {}
        done = threading.Event()

        def _run() -> None:
            try:
                result["value"] = runtime.transcribe(
                    data, filename=filename, cancel_check=cancel_check
                )
            except BaseException as exc:  # noqa: BLE001 - carried back to the calling thread
                result["error"] = exc
            finally:
                done.set()

        thread = threading.Thread(target=_run, name="lg-english-asr", daemon=True)
        deadline = time.monotonic() + float(config.timeout_seconds)
        thread.start()
        while True:
            if done.wait(0.05):
                break
            if time.monotonic() >= deadline:
                # A deadline is not stop confirmation.  Give the real call one
                # short grace window to return; only then can we classify a
                # timeout as confirmed.  Do not kill or replay either way.
                if done.wait(0.25):
                    break
                return AsrOutcome(
                    "extracting",
                    "asr_stop_unconfirmed",
                    "capability_unavailable",
                    stop_confirmed=False,
                )
        timed_out = time.monotonic() > deadline
        cancelled = bool(cancel_check is not None and cancel_check())
        if "error" in result:
            exc = result["error"]
            if cancelled:
                return AsrOutcome("unavailable", "cancelled", None, stop_confirmed=True)
            if isinstance(exc, MemoryError):
                return AsrOutcome("failed", "resource_exhausted", "capability_unavailable")
            name = type(exc).__name__
            if name == "AudioTooLong":
                return AsrOutcome("failed", "audio_too_long", "validation_failed")
            if name == "AudioDecodeError":
                return AsrOutcome("failed", "audio_decode_failed", "validation_failed")
            if name == "ModelIncompatible":
                return AsrOutcome("failed", "model_incompatible", "capability_unavailable")
            if name == "RuntimeUnavailable":
                return AsrOutcome("failed", "asr_unavailable", "capability_unavailable")
            if name == "InferenceFailed":
                return AsrOutcome("failed", "asr_failed", "capability_unavailable")
            return AsrOutcome("failed", "asr_failed", "capability_unavailable")
        if cancelled:
            return AsrOutcome("unavailable", "cancelled", None, stop_confirmed=True)
        if timed_out:
            return AsrOutcome(
                "failed",
                "asr_timeout",
                "capability_unavailable",
                stop_confirmed=True,
            )
        value = result.get("value")
        text = getattr(value, "text", None)
        if not isinstance(text, str) or not text.strip():
            return AsrOutcome("failed", "asr_failed", "capability_unavailable")
        generated_at = to_iso(utcnow())
        machine = {
            "engine": ENGINE,
            "encoder": ENCODER_PIN.public(),
            "reader": READER_PIN.public(),
            "runtime": "inprocess",
            "model_version": MODEL_VERSION,
            "content_variant": "machine",
            "generated_at": generated_at,
        }
        return AsrOutcome(
            "ready",
            None,
            None,
            text=text,
            machine=machine,
            latency_seconds=float(getattr(value, "latency_seconds", 0.0)),
            audio_seconds=float(getattr(value, "audio_seconds", 0.0)),
            stop_confirmed=True,
        )

    def _runtime_for(self, snap: AsrSnapshot) -> Any | None:
        config = snap.config
        if not config.enabled or config.model_dir is None or config.reader_dir is None:
            return None
        key = (config.model_dir, config.reader_dir, config.threads)
        with self._runtime_lock:
            if self._runtime is not None and self._runtime_key == key:
                return self._runtime
            if self._runtime is not None and hasattr(self._runtime, "close"):
                try:
                    self._runtime.close()
                except Exception:  # noqa: BLE001 - dropping old weights is best effort
                    pass
            self._runtime = None
            self._runtime_key = None
            try:
                if self._factory is not None:
                    runtime = self._factory(config)
                else:
                    runtime_module = importlib.import_module(f"{__package__}.runtime")
                    runtime = runtime_module.Eg2ReaderRuntime(
                        config, hash_cache=self._hash_cache
                    )
            except Exception:  # noqa: BLE001 - capability stays false/failed honestly
                return None
            self._runtime = runtime
            self._runtime_key = key
            return runtime


def build_english_asr_service(
    settings_repository: Any,
    *,
    env: Mapping[str, str] | None = None,
    runtime_factory: RuntimeFactory | None = None,
) -> EnglishAsrService:
    """Assembly seam used by the integration owner (docs/08 §21.6)."""

    return EnglishAsrService(
        settings_repository, env=env, runtime_factory=runtime_factory
    )


def english_asr_capability(service: EnglishAsrService) -> dict[str, Any]:
    """Pure read-only capability/reason result for ``GET /health``."""

    return service.capability()


__all__ = [
    "AsrOutcome",
    "AsrSnapshot",
    "EnglishAsrService",
    "build_english_asr_service",
    "english_asr_capability",
]
