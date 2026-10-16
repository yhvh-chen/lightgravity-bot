# LG-040 RACE-TEST-FIX — RECEIPT (exact evidence)

Base/runtime HEAD: `75c60487ad90c6712fa65c9f24ed235b45c06225`

## Full suite (COMPLETED, archived from preserved dispatch log)

Source: `/home/yhvh/.cache/lightgravity-bot/dispatch-logs/lightgravity-pi-bounded-dk559sx0.log`
tool call `call_00_vWibTsudb1ivbqrU8SLD2924` (`tool_execution_end.result.structuredContent`).

- command: `python -m pytest backend tests -q -p no:cacheprovider --basetemp=/tmp/lg040-racefix-fullpytmp`
- `exit_code`: `0`
- `wall_time_seconds`: `106`
- summary line: `863 passed, 5 skipped, 1 warning in 104.35s (0:01:44)`
- `PYTEST_EXIT=0`
- archived stdout: `raw/full_backend_pytest_completed_stdout.txt`

### Second (killed) run — NOT a result

Tool call `call_00_Diqb4KfOmtmxPhXBvdov3666` has **no `tool_execution_end`** in the log; the
wrapper was killed (exit143) mid-run. It produced
`raw/full_backend_pytest_PARTIAL_killed_secondrun.txt` (truncated ~66%, no exit code, one
interrupted-run `F` from stale basetemp). Labelled PARTIAL. Not rerun.

## Focused repeat of repaired test

- Log evidence: `PASS_RUNS=20 FAIL_RUNS=0` (20 process invocations; each log at
  `/tmp/lg040-racefix-run-<i>.log`).

## Independent 600-contention probe (run ONCE, not rerun)

File: `raw/race_reason_probe_baseline.json`
- `iterations`: 600
- `strong_invariant_failures`: 0
- `loser_reason_distribution`: `held_by_other` 575, `not_discoverable` 25
- `old_exact_reason_failures`: 25 (old exact-reason assertion would fail 25/600)

## Product byte-identity vs base

- `backend` HEAD == base == `14c12191a4a4e55ef5c127e423ae45573b74cb00`
- `frontend` HEAD == base == `e55eb88575b4615867f92de11e916403717b1b1b`
- `git diff --stat 75c6048 -- backend frontend docs backlog README.md PROJECT.md AGENTS.md agent.md design.md` → empty

## Working tree

```
 M tests/collaboration/test_claims.py
?? probes/lg040/RACE-TEST-FIX-20261016/
```
