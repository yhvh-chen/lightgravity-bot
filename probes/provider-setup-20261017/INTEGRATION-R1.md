# LG-114 — serial integration R1: consume LG-113 concurrency repair

Status: **frozen candidate for independent LG-112 retest. Not merged, not
deployed, not accepted.** Root PM owns the normative Markdown and the LG-114
task status.

## Gate and identity

| Item | Value |
|---|---|
| LG-113 status | `done`; fix commit supplied |
| Native fix commit | `47686ae74f7a38250c2ec8c20e4af240d69964a3` |
| Native branch / tree | `fix/provider-regression-20261017`; worktree clean |
| Native report | `probes/provider-setup-20261017/TEST-REGRESSION-FIX.md` |
| Original integration evidence | `probes/provider-setup-20261017/INTEGRATION.md` at `ff885bf` |
| PM first-failure record | `probes/provider-setup-20261017/INTEGRATION-FIRST-FAILURES.md` |
| Base | `ff885bf3b1025fd3d313ee4dc3c8b4a494ac1757` (LG-111 evidence child of product `a6c700e`) |
| R1 worktree | `/home/yhvh/code/lightgravity-bot-worktrees/provider-integrated-r1-20261017` |
| R1 branch | `integrate/provider-modal-r1-20261017` |
| Candidate product commit | `345f71f634e7ebf7e2455f6daf63bca639dee32f` |
| Candidate full tree hash | `2ee8293b9456c047a92f9e102f5eeefa96a898be` |
| Backend tree hash | `caad0343476887b2c49b269ad2691df7dee2b7e0` |
| Frontend product tree hash | `a3532347a41e3abd49a65b09c8c6e18fd30d7bef` (unchanged from `ff885bf`) |

The candidate is exactly the native fix applied to the frozen LG-111 base:

```text
git worktree add -b integrate/provider-modal-r1-20261017 <path> ff885bf
git cherry-pick -x 47686ae74f7a38250c2ec8c20e4af240d69964a3
```

`47686ae` has parent `ff885bf`, so the cherry-pick is a direct replay. The
resulting tree is byte-identical to native `47686ae`:

```text
HEAD tree       2ee8293b9456c047a92f9e102f5eeefa96a898be
47686ae tree    2ee8293b9456c047a92f9e102f5eeefa96a898be
git diff 47686ae HEAD  -> empty
```

Only five files differ from `ff885bf`: the three native product files, the
native report, and the native concurrency test. This evidence report and its
logs are the only later additions. No dirty file from any owner was copied.

## Preserved failure history

The first LG-111 full backend run remains **3 failed / 1200 passed / 5 skipped**
(188.60s), not rewritten by the later green run:

- `tests/e2e/settings/test_lg027_default_pin.py::test_default_change_does_not_hot_swap_active_member`
- `tests/e2e/settings/test_lg027_error_branches.py::test_disabled_default_requires_clearing_reference`
- `tests/startup/test_settings_to_task.py::test_settings_only_path_reaches_a_pinned_execution_entry`

The third failure reported `422 reference_invalid` /
`worker_default_unverified` at `http://127.0.0.1:9/v1`. The native investigation
established that all three used loopback as a default while public Settings
eligibility correctly rejects loopback/custom hosts. The fix to those tests is
fixture-local only; the original full log was overwritten before the native
investigation, which is why the PM record above is retained.

Separately, native reproduced a **real deletion race on `ff885bf`**: after
DELETE passed its reference guard, a second `FileStore`/`ConnectionService` on
the same root could commit a worker default or Agent binding, then DELETE
unlinked the connection, leaving a dangling reference. The new concurrency
regressions failed **2/2 before repair** with the explicit dangling-reference
assertion. That reproduction remains part of the native evidence and is not
reclassified as a fixture problem.

## Integrity checks

### Original assertions preserved

Independent AST comparison against root `main` `85d009d`:

| Test file | Assertions `85d009d` | Assertions R1 | AST unchanged |
|---|---:|---:|---|
| `test_lg027_default_pin.py` | 12 | 12 | yes |
| `test_lg027_error_branches.py` | 16 | 16 | yes |
| `test_settings_to_task.py` | 24 | 24 | yes |

Total **52** business assertions unchanged. The original test functions still
exist with their original names. Their only change is a test-local
`monkeypatch` of `EXECUTABLE_OPENAI_COMPAT_HOSTS` to add `127.0.0.1` as the
existing constructor seam.

### Production host policy negative controls (unpatched)

Production policy remains strict; the fix does not touch it:

- `EXECUTABLE_OPENAI_COMPAT_HOSTS = frozenset({"api.deepseek.com"})`
- `AUTHORIZED_UPSTREAM_HOSTS = frozenset({"api.deepseek.com"})`
- `allow_loopback` / `allow_loopback_upstream` remain explicit opt-in seams.

The native negative-control test runs without a host-policy patch and rejects
loopback, arbitrary custom, suffix-spoof and userinfo-spoof endpoints at both
Settings-default selection and `LocalAuthProxy` construction. The existing
adapter host-policy suite also passes. No DeepSeek-host policy or native Task
execution boundary was broadened.

### Reference guard lock ordering

Native `47686ae` adds `connection_reference_lock()` in
`backend/lightgravity/store/locking.py`: a real `flock` at
`<dataRoot>/locks/connection-references.lock`, shared by instances/processes on
the same root, failing closed when no controlled data root exists. It is
acquired **before** entity write locks on all supported reference paths:

| Path | Order |
|---|---|
| `ConnectionService.delete_connection` | reference lock → entity delete lock, guard through unlink |
| `ConnectionService.update_settings` | reference lock → read/validate → settings entity write lock |
| `ResourceService.update` for `kind == "agent"` | reference lock → merged-candidate validation → entity write lock |
| Other resource kinds | no reference lock (`nullcontext`); they do not bind connections |

The lock is not recursively acquired on these paths. This is serialization of
supported controlled writers, **not** multi-file ACID, rollback, or protection
against raw low-level Store writes / external filesystem edits. The report and
code make no cross-file ACID claim.

## Verification run for this integration

All commands ran with cwd
`/home/yhvh/code/lightgravity-bot-worktrees/provider-integrated-r1-20261017`,
interpreter `/home/yhvh/code/lightgravity-bot/.venv/bin/python`,
`PYTHONPATH=backend`, `PYTHONDONTWRITEBYTECODE=1`, and
`-p no:cacheprovider`. Logs are in
[`integration-r1-logs/`](integration-r1-logs/).

| Command | Result | Exit |
|---|---|---:|
| `python -m pytest -q tests/settings/test_connection_delete_concurrency.py` | **8 passed** (2 bindings × 2 race directions + 4 unpatched host controls) | 0 |
| `python -m pytest -q tests/e2e/settings/test_lg027_default_pin.py::test_default_change_does_not_hot_swap_active_member tests/e2e/settings/test_lg027_error_branches.py::test_disabled_default_requires_clearing_reference` | **2 passed** | 0 |
| `python -m pytest -q tests/startup/test_settings_to_task.py::test_settings_only_path_reaches_a_pinned_execution_entry` | **1 passed** | 0 |
| `python -m pytest -q tests/adapter/test_provider_host_policy.py` | **3 passed** | 0 |
| `python -m pytest -q tests/settings/test_provider_integration_lg111.py` | **5 passed** (DELETE 404/409/reference/default, secret preservation, `last_test`, capability binding) | 0 |
| `git diff --check ff885bf HEAD` | clean | 0 |

The startup node was run separately because the native report records a
pre-existing conftest collection conflict when adapter and startup modules are
mixed in one invocation. That collection issue is not a product failure and was
not worked around by changing product code or assertions.

### Native evidence reused, not duplicated

Because the R1 tree is byte-identical to native `47686ae`, the native affected
results remain applicable without another full-backend run:

- `tests/settings/test_connection_delete_concurrency.py`: **8 passed**
- `tests/settings` + `tests/resources` + two LG-027 files: **112 passed**
- `tests/startup/test_settings_to_task.py`: **1 passed**
- `tests/adapter/test_provider_host_policy.py` + `tests/store`: **72 passed**
- `mypy` on the three changed product files: success
- before repair: **2 failed** concurrency reproductions

### Frontend evidence reused

The frontend product tree is unchanged at
`a3532347a41e3abd49a65b09c8c6e18fd30d7bef` (same as `ff885bf` and native).
No frontend file was touched, so the LG-111 evidence is reused with that tree
hash rather than rerun:

- focused frontend tests: **38 passed**
- full frontend suite: **237 passed / 23 files**
- `tsc --noEmit`: exit 0
- `npm run build`: exit 0 (dist not published)

Logs remain at `probes/provider-setup-20261017/integration-logs/`.

## Limits / not claimed

- No independent LG-112 Playwright/browser/visual campaign or sign-off.
- No new full backend suite or full frontend rerun; native affected evidence and
  exact tree-hash equality are the basis, plus the focused runs above.
- No real vendor SDK/network/model request, real credential read, package
  install, cloud resource, or user-data action. Product model calls: **0**;
  development cost: unknown.
- No native Task execution/default expansion and no custom-host allowlist
  expansion.
- No main merge, push, service restart or 8123/5173/18123 update. Root `main`
  remains `85d009d`; the 12 pre-existing root dirty Markdown files and protected
  PIDs `2516844`, `2332542`, `1597462` were preserved.
- No cross-file ACID claim and no coverage of raw Store writes or external file
  edits.
- This report does not mark LG-114 done; Root PM verifies the evidence.

## Freeze

Independent LG-112 retest should use branch `integrate/provider-modal-r1-20261017`
at candidate product commit
`345f71f634e7ebf7e2455f6daf63bca639dee32f` / tree
`2ee8293b9456c047a92f9e102f5eeefa96a898be`. The evidence commit containing this
report and the focused logs is its child; its exact hash is in the final LG-114
message. Do not deploy or merge the older `ff885bf` candidate.
