---
title: "LG-040 API-RETEST-R1-20261016 — status"
doc_type: status
category: qa
status: "DONE — API slice PASS; flake classified test-timing (pre-existing, baseline==fix)"
updated: "2026-10-16"
---

# STATUS — LG-040 API-RETEST-R1-20261016

Independent QA owner, distinct from implementer. Owner scope
`probes/lg040/API-RETEST-R1-20261016/**` only.

- Candidate: HEAD `75c6048`, product tree `77685f0c64ba0403f6ba93823e7162d37be8e7bd`
  = fix `266945c` (re-verified via `git ls-tree -r HEAD -- backend frontend tests
  | git hash-object --stdin`).
- Worktree clean; no product/tests/main edits.

## Rounds

- R1 read AGENTS/agent.md, RETEST-CANDIDATE, ACL-ADDENDUM, REVOKE-FIX REPORT/STATUS.
- R2 verified candidate/fix product tree hash; created private `.venv` (`uv sync --frozen`).
- R3 wrote PLAN; copied/adapted independent real-TCP harness into `owncases/`.
- R4 fixed 2 harness-only bugs (machine seed marker text; download returns raw
  bytes not JSON; machine dir is `derivative/`); **real-TCP 16/16 PASS**.
- R5 hash-checked baseline vs fix for the flake: `test_claims.py` +
  `backend/lightgravity/collaboration` byte-identical.
- R6 targeted repeats: fix 3/3 pass, baseline 3/3 pass (isolated).
- R7 forced-contention stress 300×: fix 282 pass/0 double-grant; baseline
  276 pass/0 double-grant; failures all reason `not_discoverable` → test timing
  assumption, not product atomicity.
- R8 affected suites: sources+api 219 passed/1 skipped; focused 8 passed; mypy
  clean. Wrote REPORT + raw evidence.

## Commands + exits (recorded)

```
git ls-tree -r HEAD -- backend frontend tests | git hash-object --stdin
  -> 77685f0c64ba0403f6ba93823e7162d37be8e7bd             (exit 0)
PYTHONPATH=$PWD/backend python owncases/harness_retest_tcp.py
  -> retest real-TCP: 16/16 PASS                          (exit 0)
PYTHONPATH=$PWD/backend python -m pytest tests/sources tests/api -q
  -> 219 passed, 1 skipped                                (exit 0)
PYTHONPATH=$PWD/backend python -m pytest tests/sources/test_lg040_revoke_availability.py -q
  -> 8 passed                                             (exit 0)
PYTHONPATH=$PWD/backend python -m mypy
  -> Success: no issues found in 138 source files         (exit 0)
PYTHONPATH=$PWD/backend python owncases/race_probe.py 300 fix
  -> 282/300 pass, 0 double-grant, fails=not_discoverable (exit 1 by design)
PYTHONPATH=<baseline>/backend python owncases/race_probe.py 300 baseline
  -> 276/300 pass, 0 double-grant, fails=not_discoverable (exit 1 by design)
test_claims isolated: fix 3/3 pass; baseline 3/3 pass
```

## Counters

- Real TCP: loopback uvicorn server(s), all stopped, ports released (R15 PASS). No 8123.
- LAN/model calls: 0 · product inference: 0 · retries: 0 · OCR/vector env unset.
- Verdict: API slice PASS. Flake = pre-existing test-timing assumption
  (baseline==fix, 0 double-grants); NOT a product atomicity defect, NOT an
  LG-040 regression. Whole-version verdict is not this slice's alone.
- Cost: pi unknown, not 0.
