# LG-040 RACE-TEST-FIX — STATUS

- **State:** COMPLETE (test-only repair finalized; ready for root merge)
- **Branch:** `fix/lg040-race-test-20261016`
- **Base:** `75c60487ad90c6712fa65c9f24ed235b45c06225`
- **Runtime:** byte-identical to base (no backend/frontend edits)

## Checklist

| Item | Status | Evidence |
|---|---|---|
| Single assertion widened to accept `held_by_other` OR `not_discoverable` | DONE | `git diff tests/collaboration/test_claims.py` |
| One winner / no extra grants retained | DONE | probe 600 iters, `strong_invariant_failures=0` |
| Independent 600-contention probe (not rerun) | DONE | `raw/race_reason_probe_baseline.json` |
| Focused repeat of repaired test | DONE 20/20 | dispatch log `PASS_RUNS=20 FAIL_RUNS=0` |
| Full backend+frontend suite (ONE complete run) | DONE 863P/5S exit0 | `raw/full_backend_pytest_completed_stdout.txt` |
| No runtime/product/doc writes | CONFIRMED | tree-hash compare, `git status` |
| No new tests / no duplicate stress / no rerun | CONFIRMED | this receipt |

## Full-suite outcome

`863 passed, 5 skipped, 1 warning in 104.35s` — `PYTEST_EXIT=0` (tool `exit_code: 0`).

- **Completed-run raw stdout/exit:** `raw/full_backend_pytest_completed_stdout.txt`
- **PARTIAL (killed second capture run, not a result):**
  `raw/full_backend_pytest_PARTIAL_killed_secondrun.txt`

## Owned files to commit

- `tests/collaboration/test_claims.py` (modified)
- `probes/lg040/RACE-TEST-FIX-20261016/**` (new: report/status/receipt + raw + owncases)

## Limits

- Nothing claimed as passing without a captured exit; the completed run has `PYTEST_EXIT=0`.
- No version-QA requested (root merges test fix only, no independent tiny QA).
