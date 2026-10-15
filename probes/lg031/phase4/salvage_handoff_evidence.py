"""LG-031 phase4 — read-only salvage of the already-persisted real handoff evidence.

The phase4 real run (`run_01M5079F4W8V37RHRTN7W6WWV6`) created its
``data/``/``workspace``/``store``/``worktrees`` under a ``tempfile.TemporaryDirectory``
that was deleted when the probe exited.  The probe's *own* extraction of the frozen
``upstream_artifact_refs`` was buggy (globbed ``subtasks/*.md`` instead of
``subtasks/<id>/SUBTASK.md``), so the saved JSON shows ``handoff_refs: []``.

However, the same run's **SDK sessions** (the ``google-antigravity`` trajectory
store, one SQLite DB per session) were written to ``$TMPDIR/antigravity_*`` and
**survived**.  Each session's first step payload embeds the exact request prompt
the product built for that worker, including the ``Upstream artifacts:`` block the
dependent ``verify`` worker received.  Those DBs are the original product evidence
for the very same run.

This script **only reads** those already-existing DBs (opened ``mode=ro``), extracts
the bounded, sanitized facts the LG-031 hard condition 4 needs, and re-checks the
referenced artifact hashes.  It performs **no model calls, no network, no writes to
the original evidence**, and never re-runs the fixture.

Usage::

    uv run python probes/lg031/phase4/salvage_handoff_evidence.py \
        --session-dir /tmp/antigravity_285smjk4 \
        --session-dir /tmp/antigravity_82urbszj \
        --session-dir /tmp/antigravity_7qlg37q5 \
        [--stdout /tmp/phase4_run_stdout.txt] \
        [--out probes/lg031/phase4/evidence/salvaged_handoff_evidence.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

#: The single real run this salvage is about.  Any session that does not mention
#: both ids is not part of the run and is skipped (never counted, never merged).
RUN_ID = "run_01M5079F4W8V37RHRTN7W6WWV6"
TASK_ID = "task_01M5079F4WRHPVMVHGM1NS7FK9"

#: ``<subtask>@<64hex>:<artifact>`` — the frozen versioned/hashed handoff form.
HANDOFF_RE = re.compile(r"(?P<subtask>subtask_[0-9A-Za-z]+)@(?P<hash>[0-9a-f]{64}):(?P<artifact>\S+)")
DISCOVER_RE = re.compile(r'\{"ok": true, "reason": "discovered".*?\}\s*$')
GRANT_RE = re.compile(r'\{"ok": true, "reason": "granted".*?\}\s*$')
UPSTREAM_RE = re.compile(r"Upstream artifacts:\n(?P<block>(?:- .*\n?)+)")

#: Reviewer prompt markers (to recover the resolvable evidence excerpt + verdict).
EVIDENCE_HDR_RE = re.compile(r"^--- (?P<ref>.+?) ---$", re.MULTILINE)


def _readonly_connect(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def _decode_printable(blob: bytes) -> str:
    """Extract the printable text from a protobuf step payload.

    The payload is an opaque protobuf of UTF-8 length-delimited strings, so a raw
    string is often preceded/followed by control and length bytes that are not
    valid UTF-8.  We decode the blob incrementally: valid UTF-8 runs are kept
    with their control bytes (except NUL / low control bytes) dropped, and any
    byte that cannot start/continue a UTF-8 sequence is skipped in place rather
    than aborting the whole payload.  This keeps a word split by a protobuf
    length byte rejoined while discarding genuine binary noise.
    """

    out = bytearray()
    i = 0
    n = len(blob)
    while i < n:
        byte = blob[i]
        if byte < 0x20:
            # NUL / low control / length byte: drop, keep neighbouring words joined.
            # Keep real newlines for line structure.
            if byte == 0x0A:
                out.append(byte)
            i += 1
            continue
        if byte < 0x80:
            out.append(byte)
            i += 1
            continue
        # Multi-byte UTF-8 lead byte: validate the sequence; keep it if valid,
        # otherwise skip just this byte.
        length = 2 if byte < 0xE0 else 3 if byte < 0xF0 else 4
        chunk = blob[i : i + length]
        try:
            out.extend(chunk.decode("utf-8").encode("utf-8"))
            i += length
        except UnicodeDecodeError:
            i += 1
    text = out.decode("utf-8", errors="ignore")
    return "\n".join(line for line in text.split("\n") if len(line.strip()) >= 2 or not line)


def _session_text(db: Path) -> str:
    con = _readonly_connect(db)
    try:
        chunks: list[str] = []
        for (blob,) in con.execute("select step_payload from steps order by idx"):
            if isinstance(blob, (bytes, bytearray)):
                chunks.append(_decode_printable(bytes(blob)))
        return "\n".join(chunks)
    finally:
        con.close()


def _extract_handoffs(text: str, subtask_prefixes: set[str]) -> list[dict[str, str]]:
    """Recover the request-level upstream handoff refs from a worker's prompt."""

    seen: dict[str, dict[str, str]] = {}
    for match in HANDOFF_RE.finditer(text):
        ref = match.group(0)
        subtask = match.group("subtask")
        # Only keep handoffs whose *source* node is one of this run's subtasks.
        if subtask_prefixes and not any(subtask.startswith(p) for p in subtask_prefixes):
            continue
        seen[ref] = {
            "ref": ref,
            "source_subtask": subtask,
            "content_hash": match.group("hash"),
            "artifact": match.group("artifact"),
        }
    return [seen[k] for k in sorted(seen)]


def _extract_json_line(text: str, pattern: re.Pattern[str]) -> dict[str, Any] | None:
    for match in pattern.finditer(text):
        raw = match.group(0).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            continue
    return None


def _discovery_projection(text: str) -> dict[str, Any] | None:
    for line in text.splitlines():
        stripped = line.strip()
        if '"reason": "discovered"' in stripped and stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                continue
    return None


def _grant_receipt(text: str) -> dict[str, Any] | None:
    for line in text.splitlines():
        stripped = line.strip()
        if '"reason": "granted"' in stripped and stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                continue
    return None


def _classify_session(text: str) -> str:
    """Classify a session by program-owned markers, not prose wording.

    Prose sentences can be split by protobuf length bytes, so we key on the
    reviewer prompt's structural ``candidate_ref``/review header and on the
    discovery projection's program-owned ``capability`` value.
    """

    if "candidate_ref" in text or "Review the following candidate" in text:
        return "reviewer"
    if '"capability": "verification"' in text or '"capability":"verification"' in text:
        return "verify_worker"
    if '"capability": "implementation"' in text or '"capability":"implementation"' in text:
        return "deliver_worker"
    return "unknown"


def _verify_diff_hash(reviewer_text: str) -> dict[str, Any]:
    """Re-check the diff-evidence ``@sha256:`` against the excerpt in the prompt.

    The reviewer prompt embeds a bounded excerpt of each resolvable evidence file.
    For the diff patch this excerpt *is* the full patch body, so its sha256 must
    equal the hash carried in the ``evidence:...@sha256:<hex>`` reference.
    """

    result: dict[str, Any] = {"checked": False}
    # Find the diff-evidence ref line and the body between it and the next hdr.
    ref_match = re.search(
        r"^--- (?P<ref>evidence:[^ ]*?-diff\.patch)@sha256:(?P<hash>[0-9a-f]{64}) ---$",
        reviewer_text,
        re.MULTILINE,
    )
    if not ref_match:
        return result
    body_start = ref_match.end() + 1  # skip the newline after the header
    body = reviewer_text[body_start:]
    # The bounded excerpt is the unified diff; it ends at the first blank line
    # (next evidence header / prompt prose) in the reviewer material.
    cut = body.find("\n\n")
    if cut != -1:
        body = body[:cut]
    body = body.rstrip("\n") + "\n"  # patch files end with a newline
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    result = {
        "checked": True,
        "ref": ref_match.group("ref"),
        "expected_sha256": ref_match.group("hash"),
        "recomputed_sha256": digest,
        "match": digest == ref_match.group("hash"),
        "excerpt_bytes": len(body.encode("utf-8")),
    }
    return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def salvage(session_dirs: list[Path], stdout_path: Path | None) -> dict[str, Any]:
    sessions: list[dict[str, Any]] = []
    # First pass: which subtask ids belong to this run (from the verified sessions).
    texts: dict[Path, str] = {}
    subtask_prefixes: set[str] = set()
    for directory in session_dirs:
        dbs = sorted(directory.glob("*.db"))
        if not dbs:
            continue
        db = dbs[0]
        text = _session_text(db)
        if RUN_ID not in text:
            # Not part of the salvage target run; do not count or merge it.
            continue
        texts[db] = text
        subtask_prefixes.update(re.findall(r"(subtask_01M5079F[A-Z0-9]*)", text))

    for db, text in texts.items():
        kind = _classify_session(text)
        entry: dict[str, Any] = {
            "session_db": db.name,
            "session_dir": str(db.parent),
            "session_db_sha256": _file_sha256(db),
            "kind": kind,
            "handoffs_received": _extract_handoffs(text, subtask_prefixes),
            "discovery_projection": _discovery_projection(text),
            "grant_receipt": _grant_receipt(text),
        }
        entry["grant_receipt_has_token"] = _receipt_has_secret(entry["grant_receipt"])
        if kind == "reviewer":
            entry["verdict"] = _extract_json_line(
                text, re.compile(r'\{"outcome": "passed".*?"findings": \[\]\}')
            ) or _extract_json_line(
                text, re.compile(r'\{"outcome": ".*?"findings": \[\]\}')
            )
            entry["diff_hash_check"] = _verify_diff_hash(text)
        sessions.append(entry)

    # Stable ordering by kind for readability.
    sessions.sort(key=lambda s: (s["kind"], s["session_db"]))

    result: dict[str, Any] = {
        "status": "recovered",
        "run_id": RUN_ID,
        "task_id": TASK_ID,
        "source": "surviving google-antigravity SDK session store (read-only)",
        "note": (
            "Recovered from the already-persisted SDK sessions of the same single real "
            "run; the tempfile run data/workspace/store/worktree directories were deleted "
            "by the probe's TemporaryDirectory. No model call, no re-run, no write to the "
            "original evidence."
        ),
        "sessions": sessions,
        "handoffs_received_total": sorted(
            {h["ref"] for s in sessions for h in s["handoffs_received"]}
        ),
        "sandbox_set_has_secret": _sandbox_has_secret(sessions),
        "hash_verification": _hash_verification(sessions),
        "residual_gaps": [
            "The tempfile run data/workspace/store/worktree directories were deleted by the "
            "probe's TemporaryDirectory; only the SDK sessions (below), the raw stdout and "
            "the persistent generation ledger survive.",
            "The handoff ``content_hash`` is the sha256 of the *subtask entity document* "
            "(SUBTASK.md) captured at the passed revision; that file was inside the deleted "
            "temp dir and no surviving artifact carries its bytes, so the content_hash value "
            "is recoverable as a *recorded* fact but not re-derivable offline from original "
            "bytes.  It is NOT fabricated.",
        ],
    }
    if stdout_path is not None and stdout_path.is_file():
        result["original_stdout"] = {
            "path": str(stdout_path),
            "sha256": _file_sha256(stdout_path),
            "bytes": stdout_path.stat().st_size,
        }
    return result


def _hash_verification(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise which referenced artifact hashes were re-checked offline."""

    checks: list[dict[str, Any]] = []
    for session in sessions:
        check = session.get("diff_hash_check")
        if isinstance(check, dict) and check.get("checked"):
            checks.append(check)
    return {
        "diff_patch_sha256_rechecked": checks,
        "all_rechecked_match": bool(checks) and all(c.get("match") for c in checks),
    }


_SECRET_MARKERS = ("grant", "token", "secret", "authorization", "api_key", "api-key")


def _receipt_has_secret(receipt: dict[str, Any] | None) -> bool:
    if not receipt:
        return False
    blob = json.dumps(receipt).lower()
    # ``granted``/``fence`` are expected, contract-level facts; a *secret* would be
    # an opaque bearer value.  The frozen receipt carries no such value.
    return any(f'"{m}":' in blob and m not in ("grant",) for m in _SECRET_MARKERS)


def _sandbox_has_secret(sessions: list[dict[str, Any]]) -> bool:
    return any(s.get("grant_receipt_has_token") for s in sessions)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", action="append", default=[], type=Path)
    parser.add_argument("--stdout", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.session_dir:
        print(json.dumps({"status": "error", "reason": "no --session-dir given"}))
        return 2
    result = salvage(args.session_dir, args.stdout)
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
