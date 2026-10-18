# LG263 interrupted waiting-user Run repair

Base ff44edae6d429764fe8e931cb3d294cf853f2c79 / 1.24.0; sequentially follows LG265 commit 1b993cf on fix/lg265-runtime-repairs-20261019. Native defect repair only, pending pi serial integration/version QA.

## Reproduction and change

A minimal temporary FileStore fixture with Task waiting_user, active Run verifying, cleanup pending, and an old session ref reproduced the defect before the fix. RecoveryScanner reported recovery_required while the persisted Task stayed waiting_user: the expected phase assertion failed. This is independent source-level reproduction, not a claim that public Cancel failed on the actual 18252 instance. The previous Cancel422 was an invalid payload; the recorded Accept409 and stale Run facts remain unchanged.

Added the legal waiting_user -> recovery_required transition. Recovery keeps the old nonterminal Run, session refs, cleanup, candidate and artifacts; it does not replay, claim acceptance, release unknown execution, or manufacture a terminal Run. Failed recovery writes now emit recovery_transition_failed and no longer report a successful recovery action.

Cancel from recovery_required uses its existing direct cancelled transition only after confirmed stop; an unconfirmed request leaves it parked. The previous idle verifying/repairing fallback treated no active dispatch as enough evidence. It now requires persisted cleanup=done or an authoritative adapter confirmation, plus no pending reviewer cleanup. GraphDispatcher only forwards the adapter's existing stop-fact port. Empty in-memory refs or absent session refs do not themselves prove stop. Waiting-user Pause also waits for real confirmation before changing phase to paused.

## Functional results

Using the existing Python environment with candidate backend and temporary data only:

- Before fix, the new waiting-user restart regression failed: actual waiting_user vs expected recovery_required (1 failed in 0.30s).
- After fix, tests/control/test_restart_recovery.py and tests/control/test_control.py: 25 passed in 3.97s. Includes conservative restart parking, live-pid preservation, unknown stop retaining slot/Resume rejection, proven cleanup Cancel -> Retry, empty-graph Pause remaining waiting_user, and labelled adapter-confirmation fixture permitting stop.
- Two subsequent focused boundary checks: 2 passed in 0.11s. Pending reviewer cleanup blocks idle Cancel; failed recovery writes are reported honestly.
- git diff --check passed. Backend-only LG263; frontend build was already successful for LG265. No full suite/type/performance matrix, browser, real SDK/model or live-instance control run.

## Actual old sample limitation

For the documented old Run with session_refs and cleanup=pending, the restarted adapter cannot reconstruct its in-memory close/proxy evidence. This repair parks the Task accurately, but cannot honestly clear that slot or open acceptance. Public Cancel remains unconfirmed absent new authoritative stop facts; Resume remains blocked; Accept is not bypassed. Manual confirmation alone is not program stop evidence. There is no new force-clear endpoint, review-only action, automatic replay, storage migration, or generic recovery platform.

Pi should verify the integrated public recovery/control behavior with isolated data. Actual model review, UI and user final acceptance remain separate. Actual 18252/8123/18123/18230/5173, user data, credentials and artifacts were untouched. No merge, push or deployment. Source documents reviewed include the prior native DELIVERY and LG263/USER-ACCEPTANCE.md; the initially requested native/USER-ACCEPTANCE.md path does not exist. docs-kb CLI was unavailable; original documents were read directly.
