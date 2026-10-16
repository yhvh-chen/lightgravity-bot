# REPORT — L-R2-ROUTING-QA (independent targeted routing regression, sole J product delta)

**Type:** independent, *targeted* version-QA of the **sole J product delta**
(`backend/lightgravity/coordinator/classification.py`) for LG-047 R2 — **NOT** a
new per-small-task QA gate, **NOT** a full LG-047 milestone PASS.
**Owner:** independent QA delegated by root PM (`pi`), **independent of the J
implementer and of the active I-R2-QA browser/SDK collector**.
**Status of this report: FINAL.**

> Scope of independence: this agent authored **no** product/test code, did not
> touch the J worktree, the active `qa/proto-material-r2-20261016` (I-R2-QA)
> worktree, its campaign, ledger or processes. Only this own probe dir under
> `probes/prototype-selected-material-20261016/L-R2-ROUTING-QA/**` is written.

## 0. Bound facts (candidate hashes / commit)

| Ref | SHA |
|---|---|
| Base for this worktree (frozen `main` entry) | `0188ca21c8f4aa7db88162d0cf035d35e387884d` (`0188ca2`) |
| J fix branch tip | `fix/proto-material-classifier-r2-20261016` @ `2352c52` |
| J integration merge commit (`main`, `--no-ff`) | `7e433c3` (parents `56a2dd9` + `2352c52`) |
| LG-047 R1 integration candidate (pre-J) | `56a2dd9` |
| `main:backend/lightgravity/coordinator/classification.py` blob | `8893f6ddb0839c92e21618f46c62a224b901a35f` |

This QA worktree branch `qa/proto-material-route-r2-20261016` is created **from
`0188ca2`** (main after the J integration report/commit). The only product code
under test is `coordinator/classification.py`; its hash here is asserted equal to
the J-integrated `main` blob (see §3).

## 1. Goal (exact observed-file goal under test)

The exact goal that the R2 QA finding (I-R2, read-only) observed being
misrouted as `decision`/control (never creating a Task):

> "Create a Markdown file orion-summary.md using only the selected brief.
> Include project name, programme owner, primary launch date, **total approved
> budget**, project ID, and change ticket. Return the file as the deliverable."

Expected after the J fix: classified `delivery` → next action `create_task`, and
routed through the **public global messages API** with a selected native
uploaded source, so that a Task is created with a **valid program plan**
(acceptance criteria + authorized workspace) and the selected-source snapshot is
handed off to the queue/Run trigger.

## 2. Evidence boundary (explicit)

- **Component/API ONLY.** The in-process API fixture uses the real
  `create_app` wiring with an **unavailable executor / held dispatcher** — there
  is **no actual Antigravity SDK, no model, no DeepSeek, no network**. Any
  successful task creation here is **API/component evidence only** and must
  **not** be read as "actual SDK delivery".
- No fake answers/reviewer are produced. Those legs are held (no executor) and
  labelled as such.
- **0 real product/model/SDK calls** in this QA. No port `8123`, no browser, no
  deps, no product-code edits.

## 3. Findings / observed behaviour

### 3.1 Independent PYTHONPATH binding (own worktree)

The shared venv at `/home/yhvh/code/lightgravity-bot/.venv` contains an editable
`.pth` (`_editable_impl_lightgravity_bot.pth`) whose only line is
`/home/yhvh/code/lightgravity-bot/backend` — i.e. it binds the **main** repo, not
this worktree. This QA therefore ran every probe with an explicit
**`PYTHONPATH=$PWD/backend`** prefix; the import resolves to this worktree:

```
lightgravity.__file__ = /home/yhvh/code/lightgravity-bot-worktrees/proto-material-route-qa-r2-20261016/backend/lightgravity/__init__.py
```

(recorded in `raw/checks.log`). No product/site-packages change was made.

### 3.2 Changed scope (git diff metadata only)

`git diff --stat 56a2dd9..2352c52` = exactly 5 paths, of which the **only product
file** is `backend/lightgravity/coordinator/classification.py` (+100/-3); the rest
are J's probe dir and the J test file. `HEAD:…classification.py` blob =
`main:…classification.py` blob = `8893f6ddb0839c92e21618f46c62a224b901a35f`.
No schema, dependency, endpoint or contract-version change is in scope.

### 3.3 Before-finding reference (read-only, old blob)

Loading `56a2dd9:backend/lightgravity/coordinator/classification.py` (pre-J) into
a throwaway module and classifying the exact observed goal yields:

```
PRE-J observed goal: decision decision ['approve']
```

(`raw/before_after_reference.json` records the full before/after set.) Confirms
the R2 finding: plain substring `"approve" in "approved"` hit the `_DECISION`
control keyword, so a delivery goal was routed as a control/decision message and
never created a Task.

### 3.4 Deterministic classifier matrix (own probe, 25 cases)

`raw/classifier_matrix.py` / `.json` — **25 cases, 0 failures, exit 0**.
Highlights (all `ok=true`):

| Case | Result |
|---|---|
| exact observed goal (`… total approved budget …`) | `delivery` / `create_task` |
| `Who approved the budget?` | `answer` / `direct` (no write auth) |
| `How do I create a file?` | `answer` / `direct` (no write auth) |
| `Create acceptance.md`, `Create approved-budget.md`, `Create a file accept.md …` | `delivery` / `create_task` |
| `'Create a file with the text "approve" inside'` | `delivery` / `create_task` |
| `What is the approval status?` | `status_query` / `query` |
| genuine `approve` / `accept` / `reject` | `decision` / `decision` (kept) |
| genuine `cancel` / `pause` / `stop` | `control` / `control` (kept) |
| genuine `resume` / `continue` | `retry` / `retry` (kept) |
| Chinese `取消那个修改任务` / `接受这个交付` / `读这个文件并解释一下` / `现在进度如何？` / `创建一个说明文件` | unchanged (control/decision/bounded_read/status/delivery) |

### 3.5 Public global-messages API route (component/API ONLY)

`raw/api_route_probe.py` / `.json` — **15/15 checks pass, exit 0**.
The fixture holds the dispatcher with an **in-process component executor**;
**no SDK, no model, no network**. Observed behaviour:

- `POST /api/v1/sources` (native UTF-8 `text/plain`, `content_base64`) → `201`,
  `status=extracted`, machine derivative with `model_version="none"`, receipt
  detail `"native UTF-8 text extracted (model-free)"` — so the body was produced
  by the **real native service path**, **not a seeded derivative**.
- `POST /api/v1/conversations/global/messages` (observed goal +
  `selected_sources`) → `kind="task"`, `data.intent="delivery"`,
  `data.creates_task=true`. **Route confirmed: delivery / createTask.**
- Created Task carries program-derived `acceptance_criteria` **and** an authorized
  `workspace_ref` (`tasks/<task_id>`), so the default rule plan validates.
- `selected_trigger` is message-bound (`message_id="qa-l-r2-msg-1"`) with the
  uploaded `source_id` in its snapshot (selected-source handoff).
- The Run persists a validated program plan: `plan_source="rules"`,
  `plan_hash=07bf8753…`, subtask keys `["deliver","verify"]`.
- Worker `ExecuteRequest` has a real workspace path, acceptance criteria, and the
  exact selected brief body (untrusted-wrapped) in its instructions.

`raw/api_negative_routing.py` / `.json` — **8/8 pass, exit 0**: through the same
public API, `How do I create a file?`, `Who approved the budget?`,
`What can you do?`, `Please approve the current candidate.` and `cancel the running
task` create **no Task** (direct answer / clarify), while the quoted-`approve`
and filename deliveries create a Task. No implicit write authorization.

### 3.6 Targeted tests (NOT the full suite)

`raw/checks.log.txt`
(is the `.gitignore`-proof durable copy; `*.log` is ignored in this repo, the same
trap that dropped J's `checks.log`):

- `pytest tests/coordinator tests/api tests/contracts` → **198 passed**
- `pytest tests/sources/test_lg043_selected_material.py` → **42 passed**
- total **240 passed**, matching J's cited affected set exactly.
- The full backend suite was **not** run (out of this targeted QA's scope/budget).

### 3.7 Real-call / boundary ledger

- **0 real product/model/SDK calls.** Every API call went through
  `httpx.ASGITransport` (in-process); no socket, no DeepSeek, no Antigravity SDK.
- **No** port `8123`: a pre-existing uvicorn (PID `3320750`, started `Oct 15`,
  cwd = main repo) was already listening on `127.0.0.1:8123`; this QA started no
  server and did not touch it.
- No browser, no new deps, no product/schema/test edits, no push/deploy.
- The active I-R2-QA worktree (`qa/proto-material-r2-20261016`), its campaign,
  ledger and processes were **not touched**; no cross-task material was used.

### 3.8 Unexpected important bugs

None found in the scope of the sole J product delta. No FAIL, no repair.

## 4. Verdict — routing delta ONLY

**PASS (routing delta only).** The sole J product delta
(`coordinator/classification.py`) correctly routes the exact observed goal
`delivery`/`create_task` through the public global messages API with a native
uploaded selected source, a message-bound source snapshot handoff, and a valid
program plan; ordinary questions do not authorize write; genuine English
commands and existing Chinese examples keep their routes.

**Explicitly NOT claimed:** this is **not** an actual-SDK delivery and **not** a
full LG-047 milestone PASS. The SDK/browser legs are collected separately by the
independent I-R2-QA collector. **LG-047 remains INPROGRESS** until I's
browser+SDK proof and the final composition land.

## 5. References

- Base/entry: `0188ca2`; J branch tip `2352c52`; integration merge `7e433c3`
- J fix report: `probes/prototype-selected-material-20261016/J-CLASSIFIER-FIX-R2/REPORT.md`
- J integration report: `probes/prototype-selected-material-20261016/J-R2-INTEGRATION/REPORT.md`
- Raw: `raw/checks.log.txt` (durable copy of the gitignored `checks.log`),
  `raw/classifier_matrix.{py,json}`,
  `raw/before_after_reference.json`, `raw/api_route_probe.{py,json}`,
  `raw/api_negative_routing.{py,json}`
