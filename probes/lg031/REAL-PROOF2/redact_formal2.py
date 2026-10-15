#!/usr/bin/env python3
"""Redact the REAL-PROOF2 formal evidence for commit.

Strips model ``text`` bodies (``adapter.text``) and any tool arguments, keeping
only the structural/redacted facts.  Never writes prompts/credentials/headers.
Reads the private raw evidence ``evidence/formal-real2.json`` and writes
``evidence/formal-real2.redacted.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "fixtures" / "raw-evidence" / "formal-real2.raw.json"
OUT = HERE / "evidence" / "formal-real2.redacted.json"

_KEEP_EVENT_FIELDS = {
    "adapter.execution_started": {"type", "at", "execution", "objective"},
    "adapter.session_requested": {"type", "at", "execution"},
    "adapter.session_started": {"type", "at", "session_id"},
    "adapter.execution_finished": {"type", "at", "execution", "state"},
    "adapter.error": {"type", "at", "error", "message"},
    "adapter.tool_call": {"type", "at", "name"},
    "adapter.execution_blocked": {"type", "at", "failure"},
}


def main() -> int:
    data = json.loads(RAW.read_text(encoding="utf-8"))
    redacted_events = []
    for ev in data.get("events", []):
        et = ev.get("type")
        keep = _KEEP_EVENT_FIELDS.get(et, {"type"})
        redacted = {k: v for k, v in ev.items() if k in keep}
        if et == "adapter.session_started" and isinstance(ev.get("session"), dict):
            redacted["session_id"] = ev["session"].get("session_id")
        redacted_events.append(redacted)

    out = dict(data)
    out["events"] = redacted_events
    out["events_note"] = (
        "redacted: model text/prompt/tool-args stripped; raw private copy retained on disk"
    )
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {OUT} ({len(redacted_events)} events)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
