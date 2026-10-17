# LG-108 — explicit connection-test budget repair

Date: 2026-10-17. Owner: native Codex defect-repair subagent.
Base: `85d009dbc0eecfc398d7f43a086cf20e1d90b63f`.
Branch: `fix/provider-test-budget-20261017`.
Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/provider-test-fix-20261017`.

## Change

`ConnectionTester` previously compared its process-lifetime `_network_calls`
against `max_network_calls=1`. A first explicit test exhausted every later test.
The runtime layer makes exactly one request per explicit invocation, so it now
checks whether that invocation's configured allowance permits that one request.
Zero/negative allowances still skip requests. Positive allowances never add
requests or retries; the existing per-invocation product proxy still has
`max_calls=1`.

The public constructor/test signatures and `network_calls` property's cumulative
diagnostic meaning remain unchanged. The cumulative diagnostic increment/read
now uses a lock. No request-specific budget, connection, or credential is stored
in shared mutable tester state. Product generation ledger, global reservations,
proxy enforcement, and bootstrap configuration are unchanged.

## Verification

Commands executed in this isolated worktree using the existing root venv and
`PYTHONPATH=backend`:

- Regression before repair: `python -m pytest -q tests/settings/test_testing.py`
  produced **1 failed, 5 passed**; the second same-process explicit invocation
  was incorrectly skipped. An earlier edit command used unavailable bare
  `python` and therefore made no edit; its unchanged suite passed 6 tests. The
  reproduction above used the existing venv interpreter successfully.
- Focused repair suite: `python -m pytest -q tests/settings/test_testing.py
  tests/settings/test_testing_budget.py` — **12 passed**.
- Related suite: `python -m pytest -q tests/settings
  tests/adapter/test_proxy.py` — **59 passed**, one pre-existing Starlette/AnyIO
  deprecation warning.
- `python -m mypy backend/lightgravity/settings/testing.py` — **success**,
  no issues in one source file.
- `git diff --check` — **pass**.

The new integration regression uses the real product `LocalAuthProxy`, actual
loopback HTTP, synthetic credentials and a local provider response double. It
covers sequential and deliberately overlapping tests with distinct connections,
models and keys; matching Authorization/model pairs; unique proxy URLs and
confirmed stopped proxies; a second request rejected with 429 by each proxy;
a shared temporary persistent ledger with unlimited or one-call global ceiling;
and ledger reservations observed by a fresh reader. Unit regressions cover
repeated explicit calls, local zero allowance, and timeout without automatic
retry or exhausting the next invocation's allowance.

## Limits and preservation

This verifies existing OpenAI-compatible tester/proxy budgeting only. It makes
no claim about vendor SDK, real provider authentication or model inference.
Product/vendor/model calls: **0**. Browser/independent QA: **not run** (pi-owned).
Full backend suite: not run; focused affected suites passed. Development
cost/token usage: unknown.

Only the tester, related tests and this report were changed. No provider feature,
frontend, schema/contract, root/task document, package, env, service, live data,
real credential or existing root dirty/index state was changed. No service
control operation or request to live 8123/5173/18123 was performed; protected
8123 PID 2516844 was not touched. No merge, deployment or push. Commit is handed
to the pi integration owner; task acceptance remains with project management.
