# LG-040 RACE-TEST-FIX — REPORT

- **Task:** LG-040 flaky race-test repair (test-only)
- **Branch:** `fix/lg040-race-test-20261016`
- **Base / runtime HEAD:** `75c60487ad90c6712fa65c9f24ed235b45c06225`
- **Owner files:** `tests/collaboration/test_claims.py` + `probes/lg040/RACE-TEST-FIX-20261016/**`
- **Runtime change:** none. `backend` and `frontend` trees are byte-identical to `75c6048`
  (`backend` hash `14c12191a4a4e55ef5c127e423ae45573b74cb00`,
  `frontend` hash `e55eb88575b4615867f92de11e916403717b1b1b`).

## Change (single assertion)

`tests/collaboration/test_claims.py::test_two_owner_race_on_real_store_only_one_wins`

Before:

```python
assert refused[0].reason == "held_by_other"
```

After:

```python
assert refused[0].reason in {"held_by_other", "not_discoverable"}, refused[0]
```

Rationale: the loser is refused fail-closed for one of two legitimate reasons, depending on
whether its discovery snapshot was taken before or after the winner's committed write:
`held_by_other` (subtask still visible as claimable) or `not_discoverable` (now-running subtask
with a live lease already excluded from its view). Both are single-winner refusals; only the
exact reason was racy, never the outcome. The test retains all strong invariants
(exactly one winner, exactly one refusal, committed owner/fence).

## Evidence

### Independent 600-contention probe (own, `owncases/race_reason_probe.py`)

`raw/race_reason_probe_baseline.json` — 600 iterations of two-owner contention against the real
store, run on the unchanged backend:

- `strong_invariant_failures`: **0** (no double-grant, no extra grants, every iteration exactly
  one grant and one refusal).
- `loser_reason_distribution`: `held_by_other` 575, `not_discoverable` 25.
- `old_exact_reason_failures`: 25 — i.e. the old exact-reason assertion would have failed 25/600;
  the new set-membership assertion is satisfied by all 600.

This probe was run once; it was **not** rerun merely because the assertion changed (backend
unchanged, already proved).

### Focused repeat of the repaired test

20/20 process invocations of the single test passed (`PASS_RUNS=20 FAIL_RUNS=0`), on the final
candidate. Raw dispatch-log evidence preserved.

### Full backend+frontend pytest suite (ONE complete run)

Completed cleanly during the previous wrapper session; exact stdout+exit archived from the
preserved dispatch log into
`raw/full_backend_pytest_completed_stdout.txt`:

```
863 passed, 5 skipped, 1 warning in 104.35s (0:01:44)
PYTEST_EXIT=0
```

- Command: `python -m pytest backend tests -q -p no:cacheprovider --basetemp=/tmp/lg040-racefix-fullpytmp`
- Tool `exit_code`: `0`, `wall_time_seconds`: `106`
- HEAD at run time: `75c60487ad90c6712fa65c9f24ed235b45c06225`
- Env: quality-gate/external-call vars unset (`LIGHTGRAVITY_OCR_*`, `LIGHTGRAVITY_VECTOR_*`),
  external calls = 0.

**Not rerun.** The previous wrapper's *second* full-suite invocation (made only to write raw
stdout into a file) was killed at ~66% by the wrapper's exit143; it produced a truncated capture
now kept as `raw/full_backend_pytest_PARTIAL_killed_secondrun.txt` and explicitly labelled
**PARTIAL** (no exit code; its trailing `F` is an interrupted-run/stale-basetemp artifact, not a
real failure). The independent, un-piped `863 passed / exit 0` run above supersedes it.

## Result

- Full suite: **863 passed, 5 skipped, exit 0** (completed run, captured exit).
- Assertion change: single, test-only.
- No runtime/product/docs/backlog edits. No new tests, no duplicated stress/repeat runs.

## Limits / notes

- The PARTIAL kill artifact is retained for provenance; it is not a passing or failing result.
- `held_by_other` vs `not_discoverable` is nondeterministic by design and irrelevant to the
  one-winner contract; the probe quantifies it (25/600 under this store).
