"""Optional English audio machine transcription (docs/08 §21, contract 1.20).

Public assembly surface only:

* ``build_english_asr_service(settings_repository, *, env=None, runtime_factory=None)``
* ``build_english_asr_router(service, *, require_admin=None, safe_origin=None)``
* ``english_asr_capability(service)``

Importing this package never imports ``torch``/``transformers`` (and the smoke
runtime can be imported without FastAPI).  The real runtime is loaded lazily only
after the capability is enabled, its pinned files validate and an operation
actually needs to decode audio.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping


def build_english_asr_service(
    settings_repository: Any,
    *,
    env: Mapping[str, str] | None = None,
    runtime_factory: Callable[[Any], Any] | None = None,
) -> Any:
    from .service import build_english_asr_service as _build

    return _build(settings_repository, env=env, runtime_factory=runtime_factory)


def build_english_asr_router(
    service: Any,
    *,
    require_admin: Callable[..., None] | None = None,
    safe_origin: Callable[..., None] | None = None,
) -> Any:
    from .router import build_english_asr_router as _build

    return _build(service, require_admin=require_admin, safe_origin=safe_origin)


def english_asr_capability(service: Any) -> dict[str, Any]:
    from .service import english_asr_capability as _capability

    return _capability(service)


def english_asr_safe_origin(request: Any) -> None:
    from .router import english_asr_safe_origin as _safe_origin

    _safe_origin(request)


def __getattr__(name: str) -> Any:
    if name == "EnglishAsrService":
        from .service import EnglishAsrService

        return EnglishAsrService
    raise AttributeError(name)


__all__ = [
    "EnglishAsrService",
    "build_english_asr_service",
    "build_english_asr_router",
    "english_asr_capability",
    "english_asr_safe_origin",
]
