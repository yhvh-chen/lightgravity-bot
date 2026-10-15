#!/usr/bin/env python3
"""Safe YAML frontmatter SoT helpers (round SDK).

Why this module exists
----------------------
The round-2 experiment serialized Markdown frontmatter by hand and parsed it
with a naive ``key: value`` line splitter.  That combination produced records
such as ``lease_path: -`` which are **not valid standard YAML** (``-`` starts a
block sequence entry), and the custom parser silently accepted them.  This
module makes the SoT contract explicit:

* values are serialized with a real safe YAML dumper (``null`` for "no lease");
* values are parsed with a real safe YAML loader that **rejects duplicate keys**
  and non-mapping documents;
* an unclaimed / absent lease is the legal YAML ``null``, never ``-``.

Nothing here imports model code or performs network I/O.  Standard-library
``ruamel.yaml`` (already a repo dependency) is used in safe mode only, so no
arbitrary object construction is possible.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, Mapping

from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


class FrontmatterError(ValueError):
    """Raised when a frontmatter block is missing, malformed or invalid YAML."""


def _safe_yaml() -> YAML:
    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = False
    yaml.default_flow_style = False
    yaml.width = 1_000_000  # never wrap long scalar values
    return yaml


def dump_yaml_block(mapping: Mapping[str, Any]) -> str:
    """Serialize ``mapping`` as a safe YAML block (no ``---`` fences)."""

    yaml = _safe_yaml()
    stream = io.StringIO()
    yaml.dump(dict(mapping), stream)
    text = stream.getvalue()
    if not text.endswith("\n"):
        text += "\n"
    return text


def dump_frontmatter(mapping: Mapping[str, Any], body: str = "") -> str:
    """Return a complete ``---``-fenced Markdown document."""

    block = dump_yaml_block(mapping)
    body = body or ""
    if body and not body.startswith("\n"):
        body = "\n" + body
    return f"---\n{block}---\n{body}"


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split into ``(frontmatter_text, body)``; raise when no fence is present."""

    match = _FRONTMATTER_RE.match(text)
    if match is None:
        raise FrontmatterError("missing leading '---' frontmatter block")
    return match.group(1), text[match.end():]


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Parse a full document's frontmatter with safe YAML + duplicate rejection.

    Raises :class:`FrontmatterError` for a missing block, invalid YAML,
    duplicate keys, or a non-mapping document.
    """

    fm_text, _ = split_frontmatter(text)
    try:
        loaded = _safe_yaml().load(io.StringIO(fm_text))
    except DuplicateKeyError as exc:  # explicit, so callers can branch on it
        raise FrontmatterError(f"duplicate key in frontmatter: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - surface any YAML error uniformly
        raise FrontmatterError(f"invalid YAML frontmatter: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise FrontmatterError(f"frontmatter must be a mapping, got {type(loaded).__name__}")
    return {str(k): v for k, v in loaded.items()}


def parse_frontmatter_file(path: Path | str) -> dict[str, Any]:
    """Read ``path`` and return its parsed frontmatter (raises on invalid YAML)."""

    return parse_frontmatter(Path(path).read_text(encoding="utf-8"))


def try_parse_frontmatter_file(path: Path | str) -> tuple[dict[str, Any], str | None]:
    """Best-effort variant: return ``(frontmatter, error_or_None)``."""

    try:
        return parse_frontmatter_file(path), None
    except FrontmatterError as exc:
        return {}, str(exc)
    except OSError as exc:
        return {}, f"read error: {exc}"


def write_frontmatter_file(path: Path | str, mapping: Mapping[str, Any], body: str = "") -> None:
    """Atomically write a safe-YAML frontmatter Markdown file."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(dump_frontmatter(mapping, body), encoding="utf-8")
    tmp.replace(target)


def is_legal_lease(value: Any) -> bool:
    """True when a ``lease_path`` value is either a non-empty string or null."""

    return value is None or (isinstance(value, str) and value.strip() != "")


__all__ = [
    "FrontmatterError",
    "dump_yaml_block",
    "dump_frontmatter",
    "split_frontmatter",
    "parse_frontmatter",
    "parse_frontmatter_file",
    "try_parse_frontmatter_file",
    "write_frontmatter_file",
    "is_legal_lease",
]
