"""Atomic file replacement and append-only JSONL durability (LG-004, docs/08 §7).

* :func:`atomic_write_text` implements same-directory temp file + ``fsync`` +
  ``os.replace`` (plus a directory ``fsync``) so a crash never exposes a
  half-written document.
* :func:`append_jsonl` appends exactly one newline-terminated record and
  ``fsync``s before returning.
* :func:`recover_jsonl` truncates an incomplete/garbage tail to the last valid
  record, which is the documented partial-write recovery behaviour.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

TEMP_PREFIX = ".lg-tmp-"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fsync_dir(directory: Path) -> None:
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_text(path: Path, text: str) -> None:
    """Atomically replace ``path`` with ``text`` (durable single-file write)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=TEMP_PREFIX)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    _fsync_dir(path.parent)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON record as a newline-terminated, fsynced line."""

    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with open(path, "a", encoding="utf-8", newline="") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Load valid JSON objects from ``path``.

    Returns ``(records, bad_line_count)``.  A trailing partial line is counted
    as bad and ignored; callers use :func:`recover_jsonl` to persist the
    truncation.
    """

    if not path.is_file():
        return [], 0
    text = path.read_text("utf-8")
    if not text.strip():
        return [], 0
    complete = text if text.endswith("\n") else text.rsplit("\n", 1)[0]
    records: list[dict[str, Any]] = []
    bad = 0
    for line in complete.split("\n"):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(value, dict):
            records.append(value)
        else:
            bad += 1
    return records, bad


def recover_jsonl(path: Path) -> bool:
    """Truncate ``path`` to its last valid record; return whether it changed."""

    if not path.is_file():
        return False
    text = path.read_text("utf-8")
    if not text:
        return False
    changed = False
    if not text.endswith("\n"):
        text = text.rsplit("\n", 1)[0]
        changed = True
    lines = text.split("\n") if text else []
    good: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            changed = True
            break
        if not isinstance(value, dict):
            changed = True
            break
        good.append(line)
    if not changed:
        return False
    rebuilt = "".join(f"{line}\n" for line in good)
    atomic_write_text(path, rebuilt)
    return True


__all__ = [
    "TEMP_PREFIX",
    "sha256_text",
    "atomic_write_text",
    "append_jsonl",
    "load_jsonl",
    "recover_jsonl",
]
