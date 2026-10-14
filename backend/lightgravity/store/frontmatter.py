"""Markdown + YAML frontmatter parsing (LG-004, docs/02 §2, docs/08 §7).

Design rules:

* Parse with ``ruamel.yaml`` round-trip mode so unknown fields, key order and
  comments survive a read/modify/write cycle.
* Duplicate YAML keys are rejected (``allow_duplicate_keys = False``) and
  surfaced as a structured diagnostic instead of a traceback.
* The prose body is kept untouched; the store never rewrites it.
"""

from __future__ import annotations

from io import StringIO
from collections.abc import MutableMapping
from typing import Any, cast

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.error import YAMLError

from .errors import ConfigInvalid

_DELIMITER = "---"


def _new_yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.allow_duplicate_keys = False
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    # Avoid forced line wrapping changing stored bytes.
    yaml.width = 1_000_000
    return yaml


def _diag(code: str, message: str, location: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "level": "error",
        "location": location,
        "detail": detail or {},
    }


def split_frontmatter(text: str, *, source: str = "<memory>") -> tuple[str, str]:
    """Split ``text`` into (yaml_text, body), requiring a closed ``---`` block."""

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _DELIMITER:
        raise ConfigInvalid(
            "document has no YAML frontmatter opening delimiter",
            diagnostics=[_diag("frontmatter_missing", "missing opening '---'", source)],
            location=source,
        )
    for index in range(1, len(lines)):
        if lines[index].strip() == _DELIMITER:
            yaml_text = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            return yaml_text, body
    raise ConfigInvalid(
        "document frontmatter is not closed",
        diagnostics=[_diag("frontmatter_unclosed", "missing closing '---'", source)],
        location=source,
    )


def parse_frontmatter(yaml_text: str, *, source: str = "<memory>") -> CommentedMap:
    """Parse frontmatter YAML into a round-trip mapping, rejecting duplicates."""

    yaml = _new_yaml()
    try:
        loaded = yaml.load(yaml_text) if yaml_text.strip() else CommentedMap()
    except DuplicateKeyError as exc:
        raise ConfigInvalid(
            "frontmatter contains duplicate YAML keys",
            diagnostics=[
                _diag(
                    "duplicate_key",
                    str(exc).strip() or "duplicate key",
                    source,
                    {"key": getattr(exc, "key", None)},
                )
            ],
            location=source,
        ) from exc
    except YAMLError as exc:
        raise ConfigInvalid(
            "frontmatter is not valid YAML",
            diagnostics=[_diag("invalid_yaml", str(exc).strip() or "invalid YAML", source)],
            location=source,
        ) from exc
    if loaded is None:
        return CommentedMap()
    if not isinstance(loaded, dict):
        raise ConfigInvalid(
            "frontmatter must be a YAML mapping",
            diagnostics=[_diag("frontmatter_not_mapping", "expected a mapping", source)],
            location=source,
        )
    return cast(CommentedMap, loaded)


def parse_document(text: str, *, source: str = "<memory>") -> tuple[CommentedMap, str]:
    """Parse a full Markdown document into (frontmatter, body)."""

    yaml_text, body = split_frontmatter(text, source=source)
    return parse_frontmatter(yaml_text, source=source), body


def merge_maps(base: MutableMapping[str, Any], updates: dict[str, Any]) -> MutableMapping[str, Any]:
    """Deep-merge ``updates`` into ``base`` in place, preserving unknown keys.

    Mapping nodes are merged recursively so partial updates (e.g. only
    ``queue.state``) keep sibling extension fields.  Lists and scalars replace.
    """

    for key, value in updates.items():
        existing = base.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            merge_maps(existing, value)
        else:
            base[key] = value
    return base


def render_document(data: CommentedMap, body: str) -> str:
    """Render a frontmatter mapping plus body back to Markdown text."""

    yaml = _new_yaml()
    buffer = StringIO()
    yaml.dump(data, buffer)
    yaml_text = buffer.getvalue()
    if not yaml_text.endswith("\n"):
        yaml_text += "\n"
    return f"{_DELIMITER}\n{yaml_text}{_DELIMITER}\n{body}"


def plain(data: Any) -> Any:
    """Recursively convert ruamel container types into plain Python data."""

    if isinstance(data, dict):
        return {key: plain(value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [plain(item) for item in data]
    return data


def as_mapping(value: Any) -> dict[str, Any]:
    """Return ``value`` as a string-keyed dict, or ``{}`` if it is not a mapping."""

    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


__all__ = [
    "split_frontmatter",
    "parse_frontmatter",
    "parse_document",
    "merge_maps",
    "render_document",
    "plain",
    "as_mapping",
]
