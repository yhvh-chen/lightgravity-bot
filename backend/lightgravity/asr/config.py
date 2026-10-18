"""Configuration parsing, file/hash validation and provenance for English ASR.

No model is imported or loaded here.  Validation only stats/reads the exact
pinned files and computes/caches their SHA-256; the settings PUT uses the same
functions so an invalid path/hash is rejected before persistence.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from .pins import (
    DEFAULT_MAX_AUDIO_BYTES,
    DEFAULT_MAX_AUDIO_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    ENCODER_PIN,
    MAX_THREADS,
    MIN_THREADS,
    ModelPin,
    READER_PIN,
)
from .provider_contract import (
    GOOGLE_ALLOWED_HOST,
    GOOGLE_ALLOWED_PATH,
    GOOGLE_DEFAULT_BASE_URL,
    GOOGLE_DEFAULT_MAX_AUDIO_BYTES,
    GOOGLE_DEFAULT_MODEL,
    GOOGLE_DEFAULT_TIMEOUT_SECONDS,
    GOOGLE_MAX_AUDIO_BYTES,
    GOOGLE_MAX_CONCURRENCY,
    GOOGLE_MAX_REQUEST_BYTES,
    GOOGLE_MAX_TIMEOUT_SECONDS,
    GOOGLE_MIN_TIMEOUT_SECONDS,
    PROVIDER_GOOGLE_NATIVE,
    RUNTIME_GOOGLE_NATIVE,
    select_provider,
)

REASON_DISABLED = "disabled"
REASON_MODEL_MISSING = "model_missing"
REASON_HASH_MISMATCH = "model_hash_mismatch"
REASON_RUNTIME_UNAVAILABLE = "runtime_unavailable"
REASON_INVALID_CONFIG = "invalid_config"
REASON_RESOURCE_UNAVAILABLE = "resource_unavailable"
#: Additive Google settings reasons (docs/08 §23.4).  They describe local
#: configuration only; no provider/key verification is implied.
REASON_CREDENTIAL_MISSING = "credential_missing"
REASON_MODEL_UNAVAILABLE = "model_unavailable"

_VALID_REASONS = {
    REASON_DISABLED,
    REASON_MODEL_MISSING,
    REASON_HASH_MISMATCH,
    REASON_RUNTIME_UNAVAILABLE,
    REASON_INVALID_CONFIG,
    REASON_RESOURCE_UNAVAILABLE,
    REASON_CREDENTIAL_MISSING,
    REASON_MODEL_UNAVAILABLE,
}

#: Stable default secret ref when a Google write supplies a value but omits a
#: ref.  It is only a key in the existing FileSecretStore; it is never an env var.
DEFAULT_GOOGLE_CREDENTIAL_REF = "google-asr-api"
_GOOGLE_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_GOOGLE_CREDENTIAL_REF_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


@dataclass(frozen=True, slots=True)
class EnglishAsrConfig:
    """Typed, non-secret view of the saved settings block."""

    enabled: bool = False
    runtime: str = "inprocess"
    model_dir: str | None = None
    reader_dir: str | None = None
    device: str = "cpu"
    threads: int = 4
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_audio_seconds: int = DEFAULT_MAX_AUDIO_SECONDS
    max_audio_bytes: int = DEFAULT_MAX_AUDIO_BYTES

    @property
    def configured(self) -> bool:
        return bool(self.model_dir and self.reader_dir)

    def public_limits(self) -> dict[str, int]:
        return {
            "max_audio_seconds": self.max_audio_seconds,
            "max_audio_bytes": self.max_audio_bytes,
            "timeout_seconds": self.timeout_seconds,
            "max_concurrency": 1,
        }

    def safe_dict(self) -> dict[str, Any]:
        """Settings-safe block (never includes the write-only paths)."""

        return {
            "enabled": self.enabled,
            "runtime": self.runtime,
            "device": self.device,
            "threads": self.threads,
            "timeout_seconds": self.timeout_seconds,
            "max_audio_seconds": self.max_audio_seconds,
            "max_audio_bytes": self.max_audio_bytes,
        }

    def persisted_block(self) -> dict[str, Any]:
        """Complete block to persist, including the local paths."""

        return {
            **self.safe_dict(),
            "model_dir": self.model_dir,
            "reader_dir": self.reader_dir,
        }


@dataclass(frozen=True, slots=True)
class GoogleAsrConfig:
    """Typed, non-secret view of a stored ``google-native`` settings block."""

    enabled: bool = False
    provider: str = PROVIDER_GOOGLE_NATIVE
    runtime: str = RUNTIME_GOOGLE_NATIVE
    model: str = GOOGLE_DEFAULT_MODEL
    base_url: str = GOOGLE_DEFAULT_BASE_URL
    timeout_seconds: int = GOOGLE_DEFAULT_TIMEOUT_SECONDS
    max_audio_bytes: int = GOOGLE_DEFAULT_MAX_AUDIO_BYTES
    credential_ref: str | None = None

    @property
    def max_request_bytes(self) -> int:
        return GOOGLE_MAX_REQUEST_BYTES

    def public_limits(self) -> dict[str, int | None]:
        return {
            "max_audio_seconds": None,
            "max_audio_bytes": self.max_audio_bytes,
            "max_request_bytes": GOOGLE_MAX_REQUEST_BYTES,
            "timeout_seconds": self.timeout_seconds,
            "max_concurrency": GOOGLE_MAX_CONCURRENCY,
        }

    def persisted_block(self) -> dict[str, Any]:
        """Complete block to persist (credential ref is write-only, not secret)."""

        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "runtime": self.runtime,
            "model": self.model,
            "base_url": self.base_url,
            "credential_ref": self.credential_ref,
            "timeout_seconds": self.timeout_seconds,
            "max_audio_bytes": self.max_audio_bytes,
        }


AsrConfig = EnglishAsrConfig | GoogleAsrConfig


def _is_int(value: Any, *, minimum: int, maximum: int) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and minimum <= value <= maximum
    )


def normalize_google_base_url(value: Any) -> str:
    """Validate the frozen native endpoint base and return it without a trailing slash."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("base_url must be a non-empty https URL")
    candidate = value.strip()
    try:
        parsed = urlparse(candidate)
    except ValueError as exc:
        raise ValueError("base_url is not a valid URL") from exc
    if parsed.scheme != "https":
        raise ValueError("base_url must use https")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("base_url must not contain user information")
    if parsed.query or parsed.fragment:
        raise ValueError("base_url must not contain a query or fragment")
    if (parsed.hostname or "").lower() != GOOGLE_ALLOWED_HOST:
        raise ValueError("base_url host is not the native Google endpoint")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("base_url has an invalid port") from exc
    if port not in (None, 443):
        raise ValueError("base_url port must be omitted or 443")
    path = parsed.path.rstrip("/")
    if path != GOOGLE_ALLOWED_PATH:
        raise ValueError("base_url path must be /v1beta")
    return f"https://{GOOGLE_ALLOWED_HOST}{GOOGLE_ALLOWED_PATH}"


def valid_google_model(value: Any) -> bool:
    return isinstance(value, str) and bool(_GOOGLE_MODEL_RE.match(value))


def valid_google_credential_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(_GOOGLE_CREDENTIAL_REF_RE.match(value))


def parse_google_block(block: Any) -> tuple[GoogleAsrConfig | None, str | None]:
    """Parse a stored ``google-native`` block without raising."""

    if not isinstance(block, dict):
        return None, REASON_INVALID_CONFIG
    try:
        selection = select_provider(block)
    except ValueError:
        return None, REASON_INVALID_CONFIG
    if selection.provider != PROVIDER_GOOGLE_NATIVE:
        return None, REASON_INVALID_CONFIG

    # Google mode has no local model/runtime fields.  Their presence would
    # silently resurrect Reader semantics, so it is an invalid configuration.
    for field in ("model_dir", "reader_dir", "device", "threads"):
        if field in block:
            return None, REASON_INVALID_CONFIG
    if "max_audio_seconds" in block and block.get("max_audio_seconds") is not None:
        return None, REASON_INVALID_CONFIG

    enabled = block.get("enabled", False)
    model = block.get("model", GOOGLE_DEFAULT_MODEL)
    base_url = block.get("base_url", GOOGLE_DEFAULT_BASE_URL)
    timeout = block.get("timeout_seconds", GOOGLE_DEFAULT_TIMEOUT_SECONDS)
    max_bytes = block.get("max_audio_bytes", GOOGLE_DEFAULT_MAX_AUDIO_BYTES)
    credential_ref = block.get("credential_ref")
    if not isinstance(enabled, bool) or not valid_google_model(model):
        return None, REASON_INVALID_CONFIG
    try:
        normalized_base_url = normalize_google_base_url(base_url)
    except ValueError:
        return None, REASON_INVALID_CONFIG
    if not _is_int(
        timeout, minimum=GOOGLE_MIN_TIMEOUT_SECONDS, maximum=GOOGLE_MAX_TIMEOUT_SECONDS
    ):
        return None, REASON_INVALID_CONFIG
    if not _is_int(max_bytes, minimum=1, maximum=GOOGLE_MAX_AUDIO_BYTES):
        return None, REASON_INVALID_CONFIG
    if credential_ref is not None and not valid_google_credential_ref(credential_ref):
        return None, REASON_INVALID_CONFIG
    return (
        GoogleAsrConfig(
            enabled=enabled,
            model=str(model),
            base_url=normalized_base_url,
            timeout_seconds=timeout,
            max_audio_bytes=max_bytes,
            credential_ref=(
                credential_ref.strip() if isinstance(credential_ref, str) else None
            ),
        ),
        None,
    )


def parse_any_block(block: Any) -> tuple[AsrConfig | None, str | None]:
    """Dispatch to the legacy or Google parser using the frozen discriminator."""

    if block is None:
        return None, None
    if not isinstance(block, dict):
        return None, REASON_INVALID_CONFIG
    try:
        selection = select_provider(block)
    except ValueError:
        return None, REASON_INVALID_CONFIG
    if selection.provider == PROVIDER_GOOGLE_NATIVE:
        return parse_google_block(block)
    return parse_block(block)


def parse_block(block: Any) -> tuple[EnglishAsrConfig | None, str | None]:
    """Parse a stored block without raising; return ``(config, invalid_reason)``."""

    if block is None:
        return None, None
    if not isinstance(block, dict):
        return None, REASON_INVALID_CONFIG
    runtime = block.get("runtime", "inprocess")
    device = block.get("device", "cpu")
    enabled = block.get("enabled", False)
    threads = block.get("threads", 4)
    timeout = block.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    max_seconds = block.get("max_audio_seconds", DEFAULT_MAX_AUDIO_SECONDS)
    max_bytes = block.get("max_audio_bytes", DEFAULT_MAX_AUDIO_BYTES)
    model_dir = block.get("model_dir")
    reader_dir = block.get("reader_dir")
    valid = (
        isinstance(enabled, bool)
        and runtime == "inprocess"
        and device == "cpu"
        and _is_int(threads, minimum=MIN_THREADS, maximum=MAX_THREADS)
        and _is_int(timeout, minimum=30, maximum=DEFAULT_TIMEOUT_SECONDS)
        and _is_int(max_seconds, minimum=1, maximum=DEFAULT_MAX_AUDIO_SECONDS)
        and _is_int(max_bytes, minimum=1, maximum=DEFAULT_MAX_AUDIO_BYTES)
        and (model_dir is None or (isinstance(model_dir, str) and bool(model_dir.strip())))
        and (reader_dir is None or (isinstance(reader_dir, str) and bool(reader_dir.strip())))
    )
    if not valid:
        return None, REASON_INVALID_CONFIG
    return (
        EnglishAsrConfig(
            enabled=enabled,
            runtime=runtime,
            model_dir=model_dir.strip() if isinstance(model_dir, str) else None,
            reader_dir=reader_dir.strip() if isinstance(reader_dir, str) else None,
            device=device,
            threads=threads,
            timeout_seconds=timeout,
            max_audio_seconds=max_seconds,
            max_audio_bytes=max_bytes,
        ),
        None,
    )


class MissingModelFile(Exception):
    """A required pinned file is absent."""


class ModelHashMismatch(Exception):
    """A required pinned file exists but does not match its SHA-256."""


class InvalidModelPath(Exception):
    """A directory is not an absolute, contained local directory."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class HashCache:
    """Small process-local hash cache keyed by path + stat identity."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, tuple[int, int, str]] = {}

    def sha256(self, path: Path) -> str:
        stat = path.stat()
        key = str(path)
        with self._lock:
            cached = self._values.get(key)
            if cached is not None and cached[0] == stat.st_size and cached[1] == stat.st_mtime_ns:
                return cached[2]
        digest = sha256_file(path)
        with self._lock:
            self._values[key] = (stat.st_size, stat.st_mtime_ns, digest)
        return digest

    def remember(self, path: Path, digest: str) -> None:
        try:
            stat = path.stat()
        except OSError:
            return
        with self._lock:
            self._values[str(path)] = (stat.st_size, stat.st_mtime_ns, digest)


def _require_local_directory(value: str) -> Path:
    if "://" in value:
        raise InvalidModelPath("model directories must be local paths, not URLs")
    path = Path(value)
    if not path.is_absolute():
        raise InvalidModelPath("model directories must be absolute local paths")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise MissingModelFile(str(path)) from exc
    if not resolved.is_dir():
        raise MissingModelFile(str(path))
    return resolved


def verify_model_dir(
    value: str,
    pin: ModelPin,
    *,
    cache: HashCache | None = None,
    check_hash: bool = True,
) -> Path:
    """Verify one local model directory against the exact pinned files.

    The supplied directory must be absolute and local.  Each required file is
    resolved and must stay inside that directory (an escaping symlink is
    rejected).  Missing files raise :class:`MissingModelFile`; mismatched bytes
    raise :class:`ModelHashMismatch`.
    """

    root = _require_local_directory(value)
    for name, expected in pin.files.items():
        candidate = root / name
        if not candidate.is_file():
            raise MissingModelFile(str(candidate))
        try:
            real = candidate.resolve(strict=True)
        except OSError as exc:
            raise MissingModelFile(str(candidate)) from exc
        try:
            real.relative_to(root)
        except ValueError as exc:
            raise InvalidModelPath(f"{name} escapes the configured model directory") from exc
        if not check_hash:
            continue
        actual = cache.sha256(real) if cache is not None else sha256_file(real)
        if actual.lower() != expected.lower():
            raise ModelHashMismatch(f"{name} SHA-256 does not match the pinned value")
    return root


def validate_config_paths(
    config: EnglishAsrConfig,
    *,
    cache: HashCache | None = None,
    check_hash: bool = True,
) -> str | None:
    """Return a contract reason for the pair of configured local directories."""

    if config.model_dir is None or config.reader_dir is None:
        return REASON_MODEL_MISSING if config.enabled else REASON_DISABLED
    for value, pin in ((config.model_dir, ENCODER_PIN), (config.reader_dir, READER_PIN)):
        try:
            verify_model_dir(value, pin, cache=cache, check_hash=check_hash)
        except (MissingModelFile, InvalidModelPath):
            return REASON_MODEL_MISSING
        except ModelHashMismatch:
            return REASON_HASH_MISMATCH
        except OSError:
            return REASON_MODEL_MISSING
    return None


def public_models() -> dict[str, dict[str, str]]:
    return {
        "encoder": ENCODER_PIN.public(),
        "reader": READER_PIN.public(),
    }


def public_limits(config: EnglishAsrConfig) -> dict[str, int]:
    return config.public_limits()


def normalize_reason(reason: str | None) -> str | None:
    return reason if reason in _VALID_REASONS else None


def env_thread_default(env: Mapping[str, str] | None) -> int:
    """Optional non-secret thread override used only for first-class runtime config.

    The saved setting is authoritative.  The environment is accepted by the
    service factory for test/runtime injection, but an invalid value is ignored
    rather than silently widening the 1-8 bound.
    """

    if not env:
        return 4
    raw = os.environ.get("LIGHTGRAVITY_ENGLISH_ASR_THREADS") if env is None else env.get(
        "LIGHTGRAVITY_ENGLISH_ASR_THREADS"
    )
    try:
        value = int(str(raw).strip()) if raw is not None else 4
    except ValueError:
        return 4
    return value if MIN_THREADS <= value <= MAX_THREADS else 4


__all__ = [
    "REASON_DISABLED",
    "REASON_MODEL_MISSING",
    "REASON_HASH_MISMATCH",
    "REASON_RUNTIME_UNAVAILABLE",
    "REASON_INVALID_CONFIG",
    "REASON_RESOURCE_UNAVAILABLE",
    "REASON_CREDENTIAL_MISSING",
    "REASON_MODEL_UNAVAILABLE",
    "DEFAULT_GOOGLE_CREDENTIAL_REF",
    "EnglishAsrConfig",
    "GoogleAsrConfig",
    "AsrConfig",
    "normalize_google_base_url",
    "valid_google_model",
    "valid_google_credential_ref",
    "parse_google_block",
    "parse_any_block",
    "parse_block",
    "sha256_file",
    "HashCache",
    "MissingModelFile",
    "ModelHashMismatch",
    "InvalidModelPath",
    "verify_model_dir",
    "validate_config_paths",
    "public_models",
    "public_limits",
    "normalize_reason",
    "env_thread_default",
]
