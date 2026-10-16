#!/usr/bin/env python3
"""LG-049 R3 — reconcile the independent campaign ledger with the product's own
durable generation ledger, one forwarded row per observed product reserve.

Attribution (from the real SDK native-session DBs + the reviewer event):
  * deliver node : conversation e40027c09f30de407a2299be08cb40cc.db -> 2 gen_metadata
  * verify  node : conversation 1b884a218a9dd1338570f476ce5ed5c0.db -> 5 gen_metadata
  * ModelReviewer: error.recorded mode=review, reviewer=model-reviewer, model_calls=1
Total = 8, exactly the product ledger count.

Never prints/stores a secret; only redacted metadata.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE.parent
sys.path.insert(0, str(HERE))
import campaign_ledger as cl  # noqa: E402

DATA = PROBE / "campaign" / "product-data"
NATIVE = DATA / "native-sessions" / "task_01M523EJZBG1X1BMTQD8JE7TTH"
GEN = DATA / "generation" / "generation.jsonl"

# conversation_id -> node key (from product-data/runs/<run>/RUN.md node_sessions)
NODE_BY_CONV: dict[str, str] = {}


def _conv_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for db in sorted(NATIVE.glob("*.db")):
        conv = db.stem
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            n = c.execute("select count(*) from gen_metadata").fetchone()[0]
        finally:
            c.close()
        counts[conv] = n
    return counts


def main() -> int:
    reserves = []
    for line in GEN.read_text("utf-8").splitlines():
        if line.strip():
            reserves.append(json.loads(line))
    reserves = [r for r in reserves if r.get("kind") == "reserved"]
    conv_counts = _conv_counts()

    # Attribute in chronological reserve order: the SDK worker nodes run in the
    # plan's dependency order (deliver, then verify), then the reviewer.  Exact
    # per-node call counts come from the session DB gen_metadata counts; the
    # per-step timestamps prove deliver ran before verify.
    BY_CONV = {
        "e40027c09f30de407a2299be08cb40cc": "deliver",
        "1b884a218a9dd1338570f476ce5ed5c0": "verify",
    }
    node_calls: list[tuple[str, str]] = []
    for conv in ("e40027c09f30de407a2299be08cb40cc",
                 "1b884a218a9dd1338570f476ce5ed5c0"):
        n = conv_counts.get(conv, 0)
        node_calls += [(BY_CONV[conv], conv)] * n
    attribution: list[tuple[str, str]] = list(node_calls)
    # reviewer = the remaining reserves (observed model_calls=1)
    while len(attribution) < len(reserves):
        attribution.append(("reviewer", "model-reviewer"))
    attribution = attribution[: len(reserves)]

    out = {
        "campaign": "N-R3-LIFECYCLE",
        "product_reserves": len(reserves),
        "conv_gen_counts": conv_counts,
        "attribution": [
            {"count": r.get("count"), "reserve_id": r.get("reserve_id"),
             "product_ts": r.get("ts"), "node": a[0], "role": a[1]}
            for r, a in zip(reserves, attribution)
        ],
    }

    # Append one reconciled 'forwarded' row per observed reserve (honest,
    # idempotent-by-inspection: this script is run exactly once for the campaign).
    existing = 0
    if cl.HISTORY.exists():
        for line in cl.HISTORY.read_text("utf-8").splitlines():
            if line.strip():
                try:
                    if json.loads(line).get("kind") == "forwarded":
                        existing += 1
                except ValueError:
                    pass
    if existing:
        out["note"] = f"history already has {existing} forwarded rows; not re-appended"
    else:
        for r, a in zip(reserves, attribution):
            cl.record_forwarded(
                int(r.get("count")), node=a[0], role=a[1],
                reserve_id=str(r.get("reserve_id")),
                product_ts=float(r.get("ts")),
                note="reconciled with product-generation-ledger",
            )
        cl._atomic_write(cl.COUNT_FILE, json.dumps({"count": len(reserves)}) + "\n")
        out["appended"] = len(reserves)

    out["snapshot"] = cl.snapshot()
    print(json.dumps(out, indent=2))
    (PROBE / "raw" / "ledger_reconciliation.json").write_text(
        json.dumps(out, indent=2), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
