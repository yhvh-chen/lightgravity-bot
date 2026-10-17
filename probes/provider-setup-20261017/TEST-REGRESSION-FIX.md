# LG-113 — fixture integrity and concurrent connection deletion

Date: 2026-10-17. Owner: native Codex defect-repair subagent.
Base: frozen candidate `ff885bf` (product `a6c700eb0ee9058a4235871910a421b1be457ebc`).
Branch: `fix/provider-regression-20261017`.
Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/provider-regression-fix-20261017`.

## Findings

The first integration run remains **3 failed / 1200 passed / 5 skipped** as
recorded by PM in `INTEGRATION-FIRST-FAILURES.md`; later success does not replace
that history. The original full log was overwritten before this investigation.

The three changed tests use loopback fixtures for default selection. New public
Settings eligibility correctly rejects loopback/custom hosts, so they failed
before reaching their original pinning, disabled-reference and startup scenarios.
The pi changes add only test-local monkeypatches to the capability host set.
They retain all original assertions. An AST comparison to `85d009d` confirms:

- `test_lg027_default_pin.py`: all 12 assertion ASTs unchanged.
- `test_lg027_error_branches.py`: all 16 assertion ASTs unchanged.
- `test_settings_to_task.py`: all 24 assertion ASTs unchanged.

These fixture adaptations are legitimate. They do not change the separate
`LocalAuthProxy` allowlist or opt the production executor into loopback forwarding.
No edit to those three files, compiler policy, host allowlist, proxy, or runtime
bootstrap was needed by LG-113.

A separate **real deletion defect** was reproduced on frozen `ff885bf`: DELETE
held the connection entity lock while checking Settings/Agent references, but
new references used unrelated entity locks. By pausing DELETE just after a
successful guard, a second store/service instance could commit either a new
worker default or an Agent binding, after which DELETE removed the connection.
Both operations succeeded and left a dangling reference. New regressions failed
**2/2 before repair**, with the explicit dangling-reference assertion.

## Repair and boundary

A shared advisory lock at `<dataRoot>/locks/connection-references.lock` now
serializes the supported controlled reference writers:

- `ConnectionService.delete_connection`: guard through unlink.
- `ConnectionService.update_settings`: reference validation through commit.
- `ResourceService.update` for Agent: merged-candidate reference validation
  through commit. Other resource kinds do not take this lock.

All three acquire this root lock **before** their existing entity write locks.
It is a real `flock`, shared across instances/processes using the same data root,
not a Python in-memory mutex. A controlled reference operation without a data
root fails closed. Existing entity revisions and write behavior are retained.
No lock is recursively acquired on these paths. The implementation serializes
these operations; it does **not** provide multi-file ACID, rollback, external
filesystem edit protection, or safety for callers bypassing the controlled
services with raw low-level Store writes. Runtime Agent seeding does not bind
connections; public Agent reference edits use ResourceService.

The original production DeepSeek-only host policy and opt-in loopback forwarding
seams are unchanged.

## Verification

All commands ran in this isolated worktree with the existing venv interpreter
`/home/yhvh/code/lightgravity-bot/.venv/bin/python` and `PYTHONPATH=backend`.

| Command | Actual result |
|---|---|
| `python -m pytest -q tests/settings/test_connection_delete_concurrency.py` before repair | **2 failed**, both dangling-reference reproductions |
| Same focused file after repair and expanded cases | **8 passed** |
| `python -m pytest -q tests/settings tests/resources tests/e2e/settings/test_lg027_default_pin.py tests/e2e/settings/test_lg027_error_branches.py` | **112 passed**, one existing Starlette/AnyIO deprecation warning |
| `python -m pytest -q tests/startup/test_settings_to_task.py` | **1 passed** |
| `python -m pytest -q tests/adapter/test_provider_host_policy.py tests/store` | **72 passed** |
| `python -m mypy backend/lightgravity/store/locking.py backend/lightgravity/settings/service.py backend/lightgravity/resources/service.py` | **success**, 3 source files |
| `git diff --check` | **pass** |

The initial combined test invocation mixed startup and adapter conftest modules
and failed collection (`make_settings` imported from adapter conftest). Startup
was then run separately; no product patch or fixture assertion was changed to
work around collection. No complete backend rerun was necessary after the
integration's recorded full suite; the affected services/store were tested.

The 8 new tests use temporary data and independent FileStore/service instances.
They cover deletion winning against each binder, binding winning against each
DELETE, no dangling default/Agent, retained referenced connections, and
unpatched loopback/custom/suffix-spoof/userinfo-spoof host rejection by both
Settings default policy and actual proxy construction before any network call.
The race tests force the relevant guard/validation interleavings and join both
workers with deadlines; lock conflicts cannot masquerade as reference rejection.

## Preservation and limits

No browser, independent QA, vendor SDK/model/provider request, real credential,
package installation, environment change, root/PM/task document, live data,
service, frontend, deployment, merge or push was performed. Product model calls:
**0**. Development token/cost: unknown. The three protected services were not
contacted or controlled. Independent pi LG-112 QA and pi integration remain
required; this report does not mark tasks done or the version accepted.
