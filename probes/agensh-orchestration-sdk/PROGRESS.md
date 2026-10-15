---
title: "agensh SDK orchestration experiment — progress log"
doc_type: progress
experiment_id: agensh-sdk-20261015
status: complete
---

# PROGRESS

> Read-only management log.  Times are real UTC (`date -u`).  This package runs
> the experiment; it is not independent version QA.

| time (UTC) | phase | done | budget used (this phase) | notes |
|---|---|---|---|---|
| 2026-10-15T06:28Z | setup | worktree reused; fixtures copied + hashed | 0 SDK / 0 HTTP / 0 tok | `evidence/copied_fixtures.sha256` matches r2 source manifest |
| 2026-10-15T06:32Z | r2 gap | standard-YAML audit of r2 SoT | 0 | 12/108 frontmatter invalid (`lease_path: -`); `evidence/r2_yaml_audit.json` |
| 2026-10-15T06:35Z | offline impl | driver/relay/hooks/sotyaml + offline selftests | 0 | all pass incl. canned SDK turn + relay e2e |
| 2026-10-15T06:40Z | calibration | main 6 turns + no-skills probe 1 turn | 7 turn / 20 HTTP / 93,658 tok / 39s | within HTTP/token/wall; 1 turn over 6-turn soft cap |
| 2026-10-15T06:41Z | freeze | `PROTOCOL.md` + `evidence/FREEZE_MANIFEST.txt` | 0 | 6 runs chosen; `max_model_calls/turn=6` |
| 2026-10-15T06:41–06:48Z | formal | 6 runs (3 B + 3 C) | 51 turn / 158 HTTP / 837,630 tok / 405s | 6/6 pass; no abort |
| 2026-10-15T06:50Z | analysis | `analyze.py` + `recover_planner.py` + YAML audit | 0 | gate PASS=false; B arm invalid |
| 2026-10-15T06:55Z | report + copy | `REPORT.md`; bounded copy to main workspace | 0 | 511 files, 0 hash mismatch; `COPY_VERIFICATION.json` |

## Phase status

- [x] worktree + fixture copy with hash manifest
- [x] r2 safe-YAML evidence-gap audit (read-only)
- [x] experiment host reusing product `AntigravityExecutor` + `LocalAuthProxy`
- [x] metering relay with declared-param unification
- [x] `pre_tool_call_decide` staging path guard
- [x] offline selftests (0 real model)
- [x] calibration (bounded; 7 logical turns)
- [x] freeze PROTOCOL.md
- [x] formal run (6 runs, all passed)
- [x] analysis + REPORT
- [x] bounded copy to main workspace (511 files, 0 hash mismatch, 5 transient excluded)

## Final totals

- Formal: **51 logical turns, 158 upstream HTTP, 837,630 reported tokens, 405 s** (caps: 51/350/1.5M/1800).
- Calibration: 7 turns, 20 HTTP, 93,658 tokens, 39 s.
- Package total: 58 turns, 178 HTTP, 931,288 tokens (caps 374 / 1.6M).
- Verdict: **candidate gate NOT met; B arm invalid (planner output unusable).**
