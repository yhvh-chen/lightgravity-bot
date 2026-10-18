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

import hashlib
import importlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from lightgravity.contracts import AppError, ErrorCode
from lightgravity.settings.errors import SecretStoreError, SettingsConfigInvalid
from lightgravity.store.clock import to_iso, utcnow
from lightgravity.store.errors import ConfigInvalid, RevisionConflict

from .config import (
    DEFAULT_GOOGLE_CREDENTIAL_REF,
    EnglishAsrConfig,
    GoogleAsrConfig,
    HashCache,
    InvalidModelPath,
    MissingModelFile,
    ModelHashMismatch,
    REASON_CREDENTIAL_MISSING,
    REASON_DISABLED,
    REASON_HASH_MISMATCH,
    REASON_INVALID_CONFIG,
    REASON_MODEL_MISSING,
    REASON_RUNTIME_UNAVAILABLE,
    normalize_google_base_url,
    parse_any_block,
    parse_block,
    parse_google_block,
    public_models,
    valid_google_credential_ref,
    valid_google_model,
    validate_config_paths,
    verify_model_dir,
)
from .google_native import (
    GoogleHttpTransport,
    GoogleNativeClient,
    GoogleNativeError,
    GoogleTransportError,
    build_request_body,
    detect_audio_mime,
)
from .provider_contract import (
    GOOGLE_DEFAULT_BASE_URL,
    GOOGLE_DEFAULT_MAX_AUDIO_BYTES,
    GOOGLE_DEFAULT_MODEL,
    GOOGLE_DEFAULT_TIMEOUT_SECONDS,
    GOOGLE_MAX_AUDIO_BYTES,
    GOOGLE_MAX_REQUEST_BYTES,
    GOOGLE_MAX_TIMEOUT_SECONDS,
    GOOGLE_MIN_TIMEOUT_SECONDS,
    GOOGLE_PROMPT_VERSION,
    PROVIDER_EG2_READER,
    PROVIDER_GOOGLE_NATIVE,
    RUNTIME_GOOGLE_NATIVE,
    RUNTIME_INPROCESS,
    select_provider,
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
    config: EnglishAsrConfig | GoogleAsrConfig
    configured: bool
    available: bool
    reason: str | None
    runtime_available: bool
    provider: str = PROVIDER_EG2_READER


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
        secret_store: Any | None = None,
        google_transport: GoogleHttpTransport | None = None,
    ) -> None:
        data_dir = getattr(getattr(settings_repository, "store", None), "data_dir", None)
        if data_dir is None:
            raise ConfigInvalid("English ASR settings require a controlled data root")
        self._repository = settings_repository
        self._env = dict(env or {})
        self._factory = runtime_factory
        # Google product credentials come only from the existing controlled
        # FileSecretStore.  The environment is never consulted for this path.
        self._secret_store = secret_store
        self._google_transport = google_transport
        self._store = EnglishAsrSettingsStore(Path(data_dir))
        self._hash_cache = HashCache()
        self._runtime: Any | None = None
        self._runtime_key: tuple[str, str, int] | None = None
        self._runtime_lock = threading.Lock()
        self._google_lock = threading.Lock()

    # --------------------------------------------------------------- settings
    @property
    def repository(self) -> Any:
        return self._repository

    def _read_document(self) -> EnglishAsrDocument:
        return self._store.read()

    def _google_credential_present(self, ref: str | None) -> bool:
        """Whether the controlled secret store resolves ``ref`` (never its value)."""

        if not ref or self._secret_store is None:
            return False
        try:
            return self._secret_store.get(ref) is not None
        except Exception:  # noqa: BLE001 - an unreadable secret is simply unusable
            return False

    @staticmethod
    def _raw_is_google(block: Any) -> bool:
        return isinstance(block, dict) and block.get("provider") == PROVIDER_GOOGLE_NATIVE

    def _snapshot(self) -> AsrSnapshot:
        try:
            document = self._read_document()
        except (ConfigInvalid, OSError):
            return AsrSnapshot(
                revision=0,
                content_hash="",
                config=EnglishAsrConfig(),
                configured=False,
                available=False,
                reason=REASON_INVALID_CONFIG,
                runtime_available=False,
            )
        raw = document.block
        if raw is None:
            return AsrSnapshot(
                revision=document.revision,
                content_hash=document.content_hash,
                config=EnglishAsrConfig(),
                configured=False,
                available=False,
                reason=REASON_DISABLED,
                runtime_available=False,
            )
        is_google = self._raw_is_google(raw)
        parsed, invalid = parse_any_block(raw)
        if parsed is None or invalid is not None:
            provider = PROVIDER_GOOGLE_NATIVE if is_google else PROVIDER_EG2_READER
            return AsrSnapshot(
                revision=document.revision,
                content_hash=document.content_hash,
                config=GoogleAsrConfig() if is_google else EnglishAsrConfig(),
                # Legacy kept its historical configured=True on an invalid block;
                # Google follows §23.4: configured means valid + resolvable secret.
                configured=not is_google,
                available=False,
                reason=REASON_INVALID_CONFIG,
                runtime_available=False,
                provider=provider,
            )
        if isinstance(parsed, GoogleAsrConfig):
            credential_present = self._google_credential_present(parsed.credential_ref)
            configured = bool(credential_present)
            if not parsed.enabled:
                reason: str | None = REASON_DISABLED
            elif not credential_present:
                reason = REASON_CREDENTIAL_MISSING
            else:
                reason = None
            available = bool(parsed.enabled and configured and reason is None)
            return AsrSnapshot(
                revision=document.revision,
                content_hash=document.content_hash,
                config=parsed,
                configured=configured,
                available=available,
                reason=reason,
                runtime_available=available,
                provider=PROVIDER_GOOGLE_NATIVE,
            )

        config = parsed
        file_reason = validate_config_paths(config, cache=self._hash_cache)
        runtime_available = False
        if config.enabled and file_reason is None:
            runtime_available = self._factory is not None or _runtime_dependencies_importable()
        if file_reason is not None:
            reason = file_reason
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
            provider=PROVIDER_EG2_READER,
        )

    def snapshot(self) -> AsrSnapshot:
        return self._snapshot()

    def view(self, settings: Any | None = None) -> dict[str, Any]:
        """Public GET view; never returns a secret, credential ref or local path."""

        snap = self._snapshot()
        if isinstance(snap.config, GoogleAsrConfig):
            config = snap.config
            return {
                "revision": snap.revision,
                "content_hash": snap.content_hash,
                "provider": PROVIDER_GOOGLE_NATIVE,
                "runtime": RUNTIME_GOOGLE_NATIVE,
                "enabled": config.enabled,
                "configured": snap.configured,
                "available": snap.available,
                "reason": snap.reason,
                "language": LANGUAGE,
                "timestamps_supported": False,
                "model": config.model,
                "base_url": config.base_url,
                "credential_configured": self._google_credential_present(
                    config.credential_ref
                ),
                "models": {},
                "limits": config.public_limits(),
            }
        return {
            "revision": snap.revision,
            "content_hash": snap.content_hash,
            "provider": PROVIDER_EG2_READER,
            "enabled": snap.config.enabled,
            "runtime": snap.config.runtime,
            "configured": snap.configured,
            "available": snap.available,
            "reason": snap.reason,
            "language": LANGUAGE,
            "timestamps_supported": False,
            "model": None,
            "base_url": None,
            "credential_configured": False,
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
        config, invalid = parse_any_block(document.block)
        return bool(config is not None and invalid is None and config.enabled)

    # ------------------------------------------------------------------ update
    def _target_provider(self, payload: Mapping[str, Any], block: Any) -> str:
        """Resolve the provider for this write without guessing."""

        if "provider" in payload:
            provider = payload.get("provider")
            try:
                return select_provider(
                    {"provider": provider, "runtime": payload.get("runtime")}
                ).provider
            except ValueError:
                raise _validation_error(
                    "provider/runtime combination is not supported",
                    "provider_invalid",
                    "provider",
                ) from None
        if block is None:
            return PROVIDER_EG2_READER
        try:
            return select_provider(block).provider
        except ValueError:
            # An existing unknown/mismatched block must be corrected explicitly;
            # update must not silently reinterpret it.
            raise _validation_error(
                "the existing provider/runtime combination is invalid",
                "provider_invalid",
                "provider",
            ) from None

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
        provider = self._target_provider(payload, document.block)
        if provider == PROVIDER_GOOGLE_NATIVE:
            return self._update_google(expected_revision, payload, document)

        current, current_invalid = parse_block(document.block)
        if current is None or current_invalid is not None:
            current = EnglishAsrConfig()

        if "enabled" not in payload or not isinstance(payload.get("enabled"), bool):
            raise _validation_error("enabled must be a boolean", "enabled_invalid", "enabled")
        enabled = bool(payload["enabled"])
        # Google-only write fields never silently apply to the legacy provider.
        for field in ("model", "base_url", "credential_ref", "credential_value"):
            if field in payload:
                raise _validation_error(
                    f"{field} is only valid for google-native",
                    f"{field}_invalid",
                    field,
                )

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

    def _update_google(
        self,
        expected_revision: int,
        payload: Mapping[str, Any],
        document: EnglishAsrDocument,
    ) -> dict[str, Any]:
        if "enabled" not in payload or not isinstance(payload.get("enabled"), bool):
            raise _validation_error("enabled must be a boolean", "enabled_invalid", "enabled")
        enabled = bool(payload["enabled"])

        runtime = payload.get("runtime", RUNTIME_GOOGLE_NATIVE)
        if runtime != RUNTIME_GOOGLE_NATIVE:
            raise _validation_error(
                "runtime must be 'google-native'", "runtime_invalid", "runtime"
            )
        for field in ("model_dir", "reader_dir", "device", "threads"):
            if field in payload:
                raise _validation_error(
                    f"{field} is not valid for google-native",
                    f"{field}_invalid",
                    field,
                )
        if "max_audio_seconds" in payload and payload.get("max_audio_seconds") is not None:
            raise _validation_error(
                "max_audio_seconds is not valid for google-native",
                "max_audio_seconds_invalid",
                "max_audio_seconds",
            )

        current, invalid = (
            parse_google_block(document.block)
            if self._raw_is_google(document.block)
            else (None, REASON_INVALID_CONFIG)
        )
        if invalid is not None:
            current = None

        model = payload.get("model", current.model if current else GOOGLE_DEFAULT_MODEL)
        if not valid_google_model(model):
            raise _validation_error("model is not a safe model id", "model_invalid", "model")
        base_url = payload.get(
            "base_url", current.base_url if current else GOOGLE_DEFAULT_BASE_URL
        )
        try:
            base_url = normalize_google_base_url(base_url)
        except ValueError:
            raise _validation_error(
                "base_url must be the native https endpoint at /v1beta",
                "base_url_invalid",
                "base_url",
            ) from None
        timeout_seconds = self._int_field(
            payload,
            "timeout_seconds",
            current.timeout_seconds if current else GOOGLE_DEFAULT_TIMEOUT_SECONDS,
            GOOGLE_MIN_TIMEOUT_SECONDS,
            GOOGLE_MAX_TIMEOUT_SECONDS,
        )
        max_audio_bytes = self._int_field(
            payload,
            "max_audio_bytes",
            current.max_audio_bytes if current else GOOGLE_DEFAULT_MAX_AUDIO_BYTES,
            1,
            GOOGLE_MAX_AUDIO_BYTES,
        )

        credential_ref = current.credential_ref if current else None
        if "credential_ref" in payload:
            raw_ref = payload.get("credential_ref")
            if not isinstance(raw_ref, str) or not raw_ref.strip():
                raise _validation_error(
                    "credential_ref must be a non-empty write-only reference",
                    "credential_ref_invalid",
                    "credential_ref",
                )
            credential_ref = raw_ref.strip()
            if not valid_google_credential_ref(credential_ref):
                raise _validation_error(
                    "credential_ref is not a valid resource slug",
                    "credential_ref_invalid",
                    "credential_ref",
                )
        value_supplied = "credential_value" in payload
        credential_value = payload.get("credential_value")
        if value_supplied and (
            not isinstance(credential_value, str) or not credential_value.strip()
        ):
            raise _validation_error(
                "credential_value must be a non-empty write-only secret",
                "credential_value_invalid",
                "credential_value",
            )
        if value_supplied and credential_ref is None:
            credential_ref = DEFAULT_GOOGLE_CREDENTIAL_REF

        if enabled:
            if credential_ref is None:
                raise _validation_error(
                    "google-native enable requires a stored credential reference",
                    "credential_missing",
                    "credential_ref",
                )
            if not value_supplied and not self._google_credential_present(credential_ref):
                raise _validation_error(
                    "google-native enable requires a resolvable stored credential",
                    "credential_missing",
                    "credential_ref",
                )
            if value_supplied and self._secret_store is None:
                raise _validation_error(
                    "the controlled secret store is unavailable",
                    "credential_unavailable",
                    "credential_ref",
                )

        config = GoogleAsrConfig(
            enabled=enabled,
            model=str(model),
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            max_audio_bytes=max_audio_bytes,
            credential_ref=credential_ref,
        )

        previous = None
        if value_supplied:
            # ``credential_ref`` is guaranteed non-empty and the store present
            # when enabled; a disabled write may still intentionally rotate a
            # secret, so fail closed if the store is absent.
            if self._secret_store is None:
                raise _validation_error(
                    "the controlled secret store is unavailable",
                    "credential_unavailable",
                    "credential_ref",
                )
            previous = self._secret_store.get(str(credential_ref))
            self._secret_store.put(str(credential_ref), str(credential_value))
        try:
            written = self._store.write(
                config.persisted_block(), expected_revision=expected_revision
            )
        except Exception:
            if value_supplied and self._secret_store is not None:
                self._restore_secret(str(credential_ref), previous)
            raise
        return {
            "revision": written.revision,
            "content_hash": written.content_hash,
            "english_asr": self.view(),
        }

    def _restore_secret(self, ref: str, previous: Any) -> None:
        """Undo a Google secret write when the settings write did not commit."""

        assert self._secret_store is not None
        try:
            if previous is None:
                self._secret_store.delete(ref)
            else:
                self._secret_store.put(ref, previous.reveal())
        except Exception as exc:  # noqa: BLE001 - report without the secret value
            raise SecretStoreError(
                "credential compensation failed after a settings write failure",
                location=ref,
            ) from exc

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
        if isinstance(config, GoogleAsrConfig):
            return self._transcribe_google(
                snap, config, data, filename=filename, cancel_check=cancel_check
            )
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

    def _transcribe_google(
        self,
        snap: AsrSnapshot,
        config: GoogleAsrConfig,
        data: bytes,
        *,
        filename: str,
        cancel_check: Callable[[], bool] | None,
    ) -> AsrOutcome:
        """One native HTTP attempt; no Reader, retry, fallback or late write."""

        if not config.enabled:
            return AsrOutcome("unavailable", "asr_disabled", None)
        if not snap.configured or snap.reason in (
            REASON_CREDENTIAL_MISSING,
            REASON_INVALID_CONFIG,
        ):
            return AsrOutcome(
                "unavailable", "asr_unavailable", "capability_unavailable"
            )
        if not isinstance(data, bytes) or not data:
            return AsrOutcome(
                "failed", "asr_invalid_request", "validation_failed", stop_confirmed=True
            )
        mime_type = detect_audio_mime(filename, data)
        if mime_type is None:
            return AsrOutcome(
                "failed", "asr_invalid_request", "validation_failed", stop_confirmed=True
            )
        if len(data) > min(config.max_audio_bytes, GOOGLE_MAX_AUDIO_BYTES):
            return AsrOutcome(
                "failed", "audio_too_long", "validation_failed", stop_confirmed=True
            )
        try:
            body = build_request_body(config.model, data, mime_type)
        except ValueError:
            return AsrOutcome(
                "failed", "asr_invalid_request", "validation_failed", stop_confirmed=True
            )
        if len(body) > GOOGLE_MAX_REQUEST_BYTES:
            return AsrOutcome(
                "failed", "asr_invalid_request", "validation_failed", stop_confirmed=True
            )
        if cancel_check is not None and cancel_check():
            return AsrOutcome("unavailable", "cancelled", None, stop_confirmed=True)

        secret = None
        if self._secret_store is not None and config.credential_ref:
            try:
                secret = self._secret_store.get(config.credential_ref)
            except Exception:  # noqa: BLE001 - unreadable secret is not a call
                secret = None
        if secret is None:
            return AsrOutcome(
                "unavailable", "asr_unavailable", "capability_unavailable"
            )

        client = GoogleNativeClient(
            model=config.model,
            base_url=config.base_url,
            api_key=secret.reveal(),
            transport=self._google_transport,
        )
        # The local concurrency capacity is one.  A busy slot is a local refusal
        # before any request is dispatched; it is not a provider failure.
        if not self._google_lock.acquire(blocking=False):
            return AsrOutcome(
                "unavailable", "asr_unavailable", "capability_unavailable"
            )

        result: dict[str, Any] = {}
        done = threading.Event()

        def _run() -> None:
            try:
                result["value"] = client.transcribe(
                    body,
                    timeout=float(config.timeout_seconds),
                    cancel_check=cancel_check,
                )
            except BaseException as exc:  # noqa: BLE001 - carried to caller
                result["error"] = exc
            finally:
                done.set()
                self._google_lock.release()

        thread = threading.Thread(target=_run, name="lg-google-asr", daemon=True)
        deadline = time.monotonic() + float(config.timeout_seconds)
        thread.start()
        while True:
            if done.wait(0.05):
                break
            if cancel_check is not None and cancel_check():
                # Post-dispatch cancellation cannot prove the remote stopped.
                return AsrOutcome(
                    "extracting",
                    "asr_stop_unconfirmed",
                    "capability_unavailable",
                    stop_confirmed=False,
                )
            if time.monotonic() >= deadline:
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
            if isinstance(exc, GoogleNativeError):
                if exc.reason == "cancelled":
                    return AsrOutcome(
                        "unavailable", "cancelled", None, stop_confirmed=True
                    )
                if exc.reason == "asr_stop_unconfirmed":
                    return AsrOutcome(
                        "extracting",
                        "asr_stop_unconfirmed",
                        exc.error_code,
                        stop_confirmed=False,
                    )
                status = "unavailable" if exc.reason == "asr_auth_failed" else "failed"
                return AsrOutcome(
                    status,
                    exc.reason,
                    exc.error_code,
                    stop_confirmed=exc.stop_confirmed,
                )
            if isinstance(exc, GoogleTransportError) and exc.sent:
                return AsrOutcome(
                    "extracting",
                    "asr_stop_unconfirmed",
                    "capability_unavailable",
                    stop_confirmed=False,
                )
            return AsrOutcome(
                "failed",
                "asr_provider_unavailable",
                "capability_unavailable",
                stop_confirmed=True,
            )
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
            return AsrOutcome(
                "failed", "asr_response_invalid", "capability_unavailable"
            )
        machine = {
            "engine": "google-native",
            "provider": "google",
            "model": config.model,
            "runtime": RUNTIME_GOOGLE_NATIVE,
            "endpoint_host": getattr(value, "endpoint_host", None),
            "endpoint_path": getattr(value, "endpoint_path", None),
            "prompt_version": GOOGLE_PROMPT_VERSION,
            "model_version": f"google-native:{config.model}",
            "content_variant": "machine",
            "generated_at": to_iso(utcnow()),
            "audio_sha256": hashlib.sha256(data).hexdigest(),
            "mime_type": mime_type,
            "audio_bytes": len(data),
            "request_bytes": int(getattr(value, "request_bytes", len(body))),
            "latency_ms": int(round(float(getattr(value, "latency_seconds", 0.0)) * 1000)),
            "usage": getattr(value, "usage", None),
        }
        return AsrOutcome(
            "ready",
            None,
            None,
            text=text,
            machine=machine,
            latency_seconds=float(getattr(value, "latency_seconds", 0.0)),
            audio_seconds=0.0,
            stop_confirmed=True,
        )

    def _runtime_for(self, snap: AsrSnapshot) -> Any | None:
        config = snap.config
        if not isinstance(config, EnglishAsrConfig):
            return None
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
    secret_store: Any | None = None,
    google_transport: GoogleHttpTransport | None = None,
) -> EnglishAsrService:
    """Assembly seam used by the integration owner (docs/08 §21.6/§23).

    ``secret_store`` is the existing controlled ``FileSecretStore``.  The
    Google path never reads ``LG_GOOGLE_ASR_API_KEY`` or any environment value.
    """

    return EnglishAsrService(
        settings_repository,
        env=env,
        runtime_factory=runtime_factory,
        secret_store=secret_store,
        google_transport=google_transport,
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
