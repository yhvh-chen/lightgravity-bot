"""Canonical Markdown settings document for the English ASR capability.

The interface freeze allows ``english_asr`` to live in an independent canonical
settings file.  That is what this store implements:

``<data>/settings/ENGLISH_ASR.md``

It is a Markdown + YAML frontmatter fact source with its own ``revision`` and
``content_hash`` (SHA-256 of the complete document).  The first creation is
revision ``0``/empty hash, so the protected PUT can use the frozen first-create
``expected_revision: 0`` rule without guessing from the global ``SETTINGS.md``.

Writes use the same advisory lock + atomic replace primitives as the rest of the
store.  There is no JSON sidecar and no second authoritative database.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lightgravity.contracts import SCHEMA_NAMESPACE
from lightgravity.store.atomic import atomic_write_text
from lightgravity.store.errors import ConfigInvalid, RevisionConflict
from lightgravity.store.frontmatter import (
    merge_maps,
    parse_document,
    plain,
    render_document,
)
from lightgravity.store.locking import LockManager

SETTINGS_DIR = "settings"
SETTINGS_FILENAME = "ENGLISH_ASR.md"
SETTINGS_KIND = "settings"
SETTINGS_ID = "english_asr"
LOCK_KEY = "entity:english_asr_settings:settings"

_BODY = (
    "# English ASR settings\n\n"
    "Canonical local settings for the optional in-process English audio\n"
    "transcription capability. Model paths are intentionally write-only in the\n"
    "public API; this file lives under the controlled data root.\n"
)


@dataclass(frozen=True, slots=True)
class EnglishAsrDocument:
    """One read of the canonical document."""

    revision: int
    content_hash: str
    block: dict[str, Any] | None
    exists: bool
    path: Path


class EnglishAsrSettingsStore:
    """Read/write the independent canonical ASR settings document."""

    def __init__(self, data_dir: Path | str) -> None:
        self._data_dir = Path(data_dir)
        self._path = self._data_dir / SETTINGS_DIR / SETTINGS_FILENAME
        self._locks = LockManager(self._data_dir / "locks")

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> EnglishAsrDocument:
        if not self._path.is_file():
            return EnglishAsrDocument(
                revision=0,
                content_hash="",
                block=None,
                exists=False,
                path=self._path,
            )
        text = self._path.read_text("utf-8")
        raw, _body = parse_document(text, source=str(self._path))
        data = plain(raw)
        if data.get("schema") != SCHEMA_NAMESPACE:
            raise ConfigInvalid(
                "English ASR settings document has an unsupported schema",
                diagnostics=[
                    {
                        "code": "schema_unsupported",
                        "location": str(self._path),
                        "actual": data.get("schema"),
                    }
                ],
                location=str(self._path),
            )
        if data.get("kind") != SETTINGS_KIND or data.get("id") != SETTINGS_ID:
            raise ConfigInvalid(
                "English ASR settings document has an unexpected kind/id",
                diagnostics=[
                    {
                        "code": "identity_invalid",
                        "location": str(self._path),
                        "kind": data.get("kind"),
                        "id": data.get("id"),
                    }
                ],
                location=str(self._path),
            )
        revision = data.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ConfigInvalid(
                "English ASR settings document has an invalid revision",
                diagnostics=[{"code": "revision_invalid", "location": str(self._path)}],
                location=str(self._path),
            )
        block = data.get("english_asr")
        if block is not None and not isinstance(block, dict):
            raise ConfigInvalid(
                "english_asr must be a mapping",
                diagnostics=[{"code": "english_asr_invalid", "location": str(self._path)}],
                location=str(self._path),
            )
        return EnglishAsrDocument(
            revision=revision,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            block=dict(block) if isinstance(block, dict) else None,
            exists=True,
            path=self._path,
        )

    def write(
        self,
        block: dict[str, Any],
        *,
        expected_revision: int,
    ) -> EnglishAsrDocument:
        """Persist a complete validated block under the canonical lock."""

        with self._locks.acquire(LOCK_KEY):
            current = self.read()
            raw: Any
            if current.exists:
                if current.revision != expected_revision:
                    raise RevisionConflict(
                        SETTINGS_KIND,
                        SETTINGS_ID,
                        expected=expected_revision,
                        actual=current.revision,
                    )
                text = self._path.read_text("utf-8")
                raw, body = parse_document(text, source=str(self._path))
                existing = raw.get("english_asr")
                if isinstance(existing, dict):
                    merge_maps(existing, block)
                else:
                    raw["english_asr"] = dict(block)
                next_revision = current.revision + 1
            else:
                if expected_revision != 0:
                    raise RevisionConflict(
                        SETTINGS_KIND,
                        SETTINGS_ID,
                        expected=expected_revision,
                        actual=0,
                    )
                raw = {}
                body = _BODY
                raw["schema"] = SCHEMA_NAMESPACE
                raw["kind"] = SETTINGS_KIND
                raw["id"] = SETTINGS_ID
                raw["english_asr"] = dict(block)
                next_revision = 0
            raw["revision"] = next_revision
            text = render_document(raw, body)
            atomic_write_text(self._path, text)
            return EnglishAsrDocument(
                revision=next_revision,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                block=dict(block),
                exists=True,
                path=self._path,
            )


__all__ = [
    "EnglishAsrDocument",
    "EnglishAsrSettingsStore",
    "SETTINGS_FILENAME",
]
