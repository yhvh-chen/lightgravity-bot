#!/usr/bin/env python3
"""Offline extraction of full tool-call arguments from SDK native session DBs.

The SDK's local harness persists each trajectory step into a sqlite ``steps``
table; ``step_payload`` is a serialized protobuf whose exact schema ships inside
the harness binary (it is *newer* than the generated ``steps_pb2`` /
``localharness_pb2`` in the installed package, so direct ``ParseFromString``
silently drops most fields).  We therefore walk the protobuf wire format
generically and recover every embedded length-delimited string, then locate the
full ``finish`` structured output by JSON-decoding those strings.

This is used for **offline replay / audit** of the first attempt (whose emitted
tool arguments were truncated to 2000 chars by the product executor).  The
corrected runtime does not depend on it: the lossless ``finish`` payload is
captured natively by a ``pre_tool_call`` hook (see ``hooks.py``).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator

_DECODER = json.JSONDecoder()

# Keys that identify a structured ``finish`` payload (any phase).
_FINISH_KEYS = ("plan", "interface_notes", "claim", "summary", "findings")


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    shift = 0
    value = 0
    while True:
        if pos >= len(buf):
            raise ValueError("truncated varint")
        byte = buf[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return value, pos
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def iter_proto_fields(buf: bytes) -> Iterator[tuple[int, int, Any]]:
    """Yield ``(field_number, wire_type, value)`` for a protobuf byte string."""

    pos = 0
    n = len(buf)
    while pos < n:
        try:
            key, pos = _read_varint(buf, pos)
        except ValueError:
            return
        field_no = key >> 3
        wire = key & 0x07
        try:
            if wire == 0:
                value, pos = _read_varint(buf, pos)
            elif wire == 1:
                value = buf[pos:pos + 8]
                pos += 8
            elif wire == 2:
                length, pos = _read_varint(buf, pos)
                value = buf[pos:pos + length]
                pos += length
            elif wire == 5:
                value = buf[pos:pos + 4]
                pos += 4
            else:
                return
        except (ValueError, IndexError):
            return
        if isinstance(value, int) and value < 0:
            return
        yield field_no, wire, value


def _collect_strings(buf: bytes, out: list[bytes], depth: int = 0) -> None:
    """Recursively collect length-delimited blobs (bounded depth)."""

    if depth > 6:
        return
    for _field, wire, value in iter_proto_fields(buf):
        if wire != 2 or not isinstance(value, (bytes, bytearray)):
            continue
        value = bytes(value)
        out.append(value)
        # A nested message is likely; recurse (bounded).
        if len(value) >= 2 and value[:1] in (b"\x08", b"\x0a", b"\x12", b"\x1a", b"\x22", b"\x2a"):
            _collect_strings(value, out, depth + 1)


def _looks_like_finish(obj: Any) -> bool:
    return isinstance(obj, dict) and any(k in obj for k in _FINISH_KEYS)


def _scan_json(text: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    start = 0
    while True:
        i = text.find("{", start)
        if i < 0:
            return found
        try:
            obj, end = _DECODER.raw_decode(text, i)
        except ValueError:
            start = i + 1
            continue
        if _looks_like_finish(obj):
            found.append(obj)
        start = max(end, i + 1)


def candidates_from_payload(payload: bytes) -> list[dict[str, Any]]:
    """Recover candidate finish objects from one ``step_payload`` blob."""

    blobs: list[bytes] = [payload]
    _collect_strings(payload, blobs)
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for blob in blobs:
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for obj in _scan_json(text):
            key = json.dumps(obj, sort_keys=True, ensure_ascii=False)
            if key not in seen:
                seen.add(key)
                found.append(obj)
    return found


def extract_finish_payloads(db_path: Path | str) -> list[dict[str, Any]]:
    """Return all distinct finish candidates in a session DB, best-effort."""

    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        try:
            rows = [r[0] for r in cur.execute("select step_payload from steps order by idx")]
        except sqlite3.Error:
            rows = []
        found: list[dict[str, Any]] = []
        seen: set[str] = set()
        for payload in rows:
            if not isinstance(payload, (bytes, bytearray)):
                continue
            for obj in candidates_from_payload(bytes(payload)):
                key = json.dumps(obj, sort_keys=True, ensure_ascii=False)
                if key not in seen:
                    seen.add(key)
                    found.append(obj)
        return found
    finally:
        con.close()


def extract_best_finish_payload(db_path: Path | str) -> dict[str, Any] | None:
    """Pick the most complete finish payload (largest serialized size)."""

    candidates = extract_finish_payloads(db_path)
    if not candidates:
        return None
    return max(candidates, key=lambda o: len(json.dumps(o, ensure_ascii=False)))


__all__ = [
    "iter_proto_fields",
    "candidates_from_payload",
    "extract_finish_payloads",
    "extract_best_finish_payload",
]
