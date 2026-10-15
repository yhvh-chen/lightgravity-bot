#!/usr/bin/env python3
"""Read-only audit of round-2 (r2) SoT frontmatter with a *standard* YAML parser.

Motivation
----------
r2's own consistency check parsed frontmatter with a naive ``key: value`` line
splitter, which accepted the illegal scalar ``lease_path: -``.  Standard YAML
rejects that (``-`` opens a block sequence).  This script re-audits every r2
``TASK.md`` / ``RUN.md`` / ``subtasks/*.md`` with the safe-YAML parser used by
the SDK-round experiment (``driver/sotyaml.py``), records the exact parse error
for each invalid file, and never mutates r2 output.

It also re-derives the "granted lease" map from the *parsed* subtask files and
compares it with the r2 ``events.jsonl`` ``claim_result`` events, so the report
can state precisely which candidate-SoT requirements are and are not proven.

Usage:
    python3 driver/audit_r2_yaml.py /home/yhvh/code/lightgravity-bot/probes/agensh-orchestration-r2
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sotyaml import FrontmatterError, parse_frontmatter  # noqa: E402


def _audit_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        fm = parse_frontmatter(text)
        return {"path": str(path), "ok": True, "keys": sorted(fm.keys()), "frontmatter": fm}
    except FrontmatterError as exc:
        return {"path": str(path), "ok": False, "error": str(exc)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("r2_root")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    root = Path(args.r2_root).resolve()
    runs = sorted(p for p in (root / "runs").glob("*") if p.is_dir())

    report: dict = {
        "r2_root": str(root),
        "runs": [],
        "summary": {},
        "claim_authority_agreement": {},
    }
    invalid_total = 0
    invalid_reasons: Counter[str] = Counter()
    file_total = 0
    kind_stats: dict[str, Counter] = {
        "TASK.md": Counter(), "RUN.md": Counter(), "subtasks": Counter()
    }
    agreement_rows = []
    for run in runs:
        run_records = []
        files: list[tuple[str, Path]] = []
        if (run / "TASK.md").exists():
            files.append(("TASK.md", run / "TASK.md"))
        if (run / "RUN.md").exists():
            files.append(("RUN.md", run / "RUN.md"))
        for p in sorted((run / "subtasks").glob("*.md")):
            files.append(("subtasks", p))
        parsed_leases: dict[str, str] = {}
        for kind, path in files:
            file_total += 1
            rec = _audit_file(path)
            rec["kind"] = kind
            run_records.append(rec)
            if not rec["ok"]:
                invalid_total += 1
                invalid_reasons[rec["error"].split(":")[0]] += 1
                kind_stats[kind][f"invalid"] += 1
            else:
                kind_stats[kind]["ok"] += 1
                if kind == "subtasks":
                    fm = rec["frontmatter"]
                    if fm.get("lease_state") == "granted" and fm.get("lease_path") not in (None, "-"):
                        parsed_leases[str(fm["lease_path"])] = str(fm.get("worker", ""))
        report["runs"].append({"run": run.name, "files": run_records})

        # compare with events.jsonl claim_result authority
        ev_path = run / "events.jsonl"
        event_leases: dict[str, str] = {}
        event_invalid = 0
        if ev_path.exists():
            for line in ev_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    event_invalid += 1
                    continue
                if ev.get("type") == "claim_result" and ev.get("state") == "granted":
                    p = ev.get("granted_path")
                    if isinstance(p, str):
                        event_leases[p] = str(ev.get("worker", ""))
        agree = parsed_leases == event_leases
        agreement_rows.append({
            "run": run.name,
            "parsed_granted_leases": parsed_leases,
            "event_granted_leases": event_leases,
            "agree": agree,
            "event_json_invalid_lines": event_invalid,
        })
    report["summary"] = {
        "runs": len(runs),
        "files_audited": file_total,
        "invalid_files": invalid_total,
        "invalid_by_kind": {k: dict(v) for k, v in kind_stats.items()},
        "invalid_reasons": dict(invalid_reasons),
    }
    report["claim_authority_agreement"] = {
        "all_agree": all(r["agree"] for r in agreement_rows) if agreement_rows else None,
        "rows": agreement_rows,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
