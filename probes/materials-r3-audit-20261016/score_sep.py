#!/usr/bin/env python3
"""DATA-ONLY check: would a score threshold even be feasible? NO tuning/validation.
Reads the frozen R3 retrieval_results.json (real product hits, no scores cached)
and the product index config. We only report that hit scores are NOT persisted,
so feasibility of a threshold cannot be assessed from R3 evidence."""
import json
r=json.load(open("/home/yhvh/code/lightgravity-bot-worktrees/materials-quality-20261016-r3/probes/materials-quality-20261016-r3/evidence/retrieval_results.json"))
# do hits carry scores?
sample=r["queries"][0]
print("vector_hits tuple fields:", sample["vector_hits"][:1])
print("KEYS of a query entry:", list(sample.keys()))
print("score present in vector_hits?", any("score" in str(h) for h in sample["vector_hits"]))
print("negative Q6 hits count:", len(r["vector_metrics"]["negative_controls"]["Q6"]["hits"]))
print("positive Q1 hits count:", len([e for e in r["queries"] if e["q"]=="Q1"][0]["vector_hits"]))
print("budget:", r["budget"])
