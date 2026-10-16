---
title: "Selected-material prototype — repeatable user guide (LG-045)"
doc_type: guide
category: engineering
contract_version: "1.12.0"
updated: "2026-10-16"
---

# Selected-material prototype — repeatable user guide

This is the English, step-by-step guide for trying the **selected-material**
rapid prototype by hand. It is written for LG-047 QA and for anyone who wants
to reproduce the two prototype flows. It is a **user guide**, not a claim that
the feature is finished.

> **Status: implementation done; LG-047 name-milestone version QA is `done` (PASS_WITH_LIMITATIONS) as of 2026-10-16.** This guide
> describes how to drive the frozen contract. A full lifecycle run has been
> observed and independently QA-verified (see the result block below and
> [N-R3-LIFECYCLE REPORT](../probes/prototype-selected-material-20261016/N-R3-LIFECYCLE/REPORT-N-R3-LIFECYCLE-20261016.md));
> the limitations in §9 still apply. Any result you obtain is an *observation* to compare against
> the fixture truth.
>
> **Version QA result (2026-10-16, LG-049 `N-R3-LIFECYCLE`, PASS_WITH_LIMITATIONS):** on the frozen
> product (`main` == `0188ca2`, zero product-code change) the full real SDK delivery lifecycle
> passed: native upload of the alpha brief via `selected_sources` → EXACT prior-failing delivery
> target routed to `delivery/create_task` → rules plan `deliver`+`verify` (sequential SDK nodes) →
> real SDK worker wrote all 6 fixture facts → `verify` node passed (R2 had 429 here) → program
> machine gate → **real independent ModelReviewer passed** (`reviewer_kind=model`, `model_calls=1`)
> → **worker `cleanup=done`+`member.released` and reviewer `reviewer_cleanup.confirmed=true` before
> accept** → API accept (optimistic revision) → `done`; artifact refs returned real authorized
> bodies and history Sources matched the bindings. Count: **8/16** product requests
> (deliver 2 + verify 5 + reviewer 1). Product code was not
> changed (J's classifier fix was already in `main`).
>
> **Run it on integrated `main`.** The demo branch
> `dev/proto-material-demo-20261016` is not an integrated prototype base; see
> §1 for the exact pre-integration behavior (unknown `selected_sources` ⇒
> `422 validation_failed`, not a `404`/`not_ready` route).
>
> **Integration status (2026-10-16, LG-046):** the LG-043 backend and LG-044
> frontend are now merged into `main` (`--no-ff`), so the `selected_sources`
> field **is** present on this integrated candidate and the flows below apply.
> The “pre-integration / before LG-046” explanation in §1 is retained as
> historical context and for reproduction on the base product only. Contract
> version is now finalized at **`1.12.0`** (no longer reserved).
>
> **Fixture data is human-written SAMPLE data, not OCR output and not measured
> model results.** See [`examples/selected-material-prototype/README.md`](../examples/selected-material-prototype/README.md).
> The expected facts live in
> [`examples/selected-material-prototype/expected-facts.json`](../examples/selected-material-prototype/expected-facts.json).
>
> **R1 返修后的事实（2026-10-16，F+G 合并候选；后续已被 R2/R3 验证取代，本条保留为历史）**：
> - **原生文本成功，无需 OCR**：`text/plain`（及 `text/markdown`、`text/x-markdown`、`text/x-log`、`application/x-ndjson`）上传后由**原生 UTF-8 模型免调用**提取器同步落盘为一个 machine 派生件（`extractor=native-utf8-text`、`model=none`），可经 `GET /sources/{id}/content?kind=auto` 读到正文。非 UTF-8 或超限（2 MB）如实 `failed` 且不留伪造正文。
> - **PDF/图像处理不变，仍走显式 OCR 路径**：这两种媒体类型上传保持 `received`，需显式 `reprocess` 触发既有 OCR；原生文本修复**不改**该路径。
> - **选定回答（含来源）已持久化进历史**：每个 `direct`/`bounded_read` 回答把助手行 `assistant:<message_id>`（携带 `resolved_source_bindings` 与 `selected_context` 快照）写入同一会话 SoT，`GET .../messages` 可重放；重试同一 `message_id` 幂等（不重复落库、不重复派发）。**旧的“无助手历史”行为是已修复的 bug；旧会话历史不再行数逐字节一致。**
> - **无选材普通 Chat 交付使用确定性文件计划**：请求未命名验收条件/工作区时，程序派生可检查验收条件并在授权根内预置 Task 工作区，使**未改动**的 `PlanValidator` 接受原型默认规则计划——单一执行槽内**顺序**运行既有 `deliver` + `verify` 两个 SDK worker 节点，随后由**独立 ModelReviewer** 复核（三者均预算化、保留不削弱）。**勘误（2026-10-16，LG-048 诊断）**：本节先前“最小单 worker 规则计划”措辞对普通 Chat 交付不准确（`default_delivery=True` 派生验收条件 ⇒ 追加 `verify`）；此为文档勘误，非行为变更。
> - **`Sources` 仍不是已验证引用**：绑定只说明程序提供了哪些文本，引用**未经 span 验证**；一切仍以人工比对 fixture truth 为准。

## 0. What this prototype is (and is not)

The prototype lets a user **manually select 1–3 already-ingested sources** and
have the program resolve their text, bind it as **provided context**, and use
**exactly that same bounded body** for both the Chat reply and the worker
context.

- Contract: [docs/10-selected-material-prototype.md](10-selected-material-prototype.md)
  (single source of truth) plus [docs/08](08-interface-contract.md) §6.6.1.
- **In scope:** selecting ingested sources, resolving their exact text,
  binding a bounded context snapshot, rejecting stale/revoked/cross-Task/
  over-limit selections before model dispatch.
- **Explicitly out of scope here:** OCR, ASR, embedding, reprocessing, new
  inference paths, new vendors, project/MCP/search/Office/ASR/planner
  behavior, auto-retrieval, installers. This prototype adds none of those.

### Honest labels you will see

| Label | Meaning |
|---|---|
| **Sources** | The UI label for where selected material appears. It is **provided context**, not a verified citation. |
| `provided_context_note` | The program's explicit note that sources are provided as context and citations are **not** span-verified. |
| `resolved_source_bindings` | The program-resolved list of what was actually bound (id, version, hash, layer, locator, char_count, truncated). |
| `layer` | `formal` if a human formal version exists, otherwise `machine` (trusted machine derivative only). |

The program never claims that the model *cited* anything. An answer is
compared to the fixture truth by a human; the program only guarantees which
text was provided.

## 1. Prerequisites

- A working checkout of this repository **on the integrated branch `main`
  after LG-046 has landed and the LG-047 R1 repairs (F+G) are merged and the
  J classifier fix (`2352c52`) is in `main`**
  (LG-043 backend + LG-044 frontend + R1 native-intake/history/plan repairs +
  J English whole-word classifier fix) — this is the frozen, version-QA'd state as of 2026-10-16
  (`main` product tree == `0188ca2`).
  **Do not run this guide on the demo owner branch
  `dev/proto-material-demo-20261016`** — that branch only contains the demo
  assets and the base product; it is **not** a working prototype base because
  the `selected_sources` field is not implemented there.
- Python `>=3.12,<3.13`, `uv 0.12.x`, Node 22 / npm 10, GNU make
  (see [README](../README.md) "版本要求").
- The two prototype owner worktrees are integrated (LG-043 backend, LG-044
  frontend). On the current integrated `main` the selection field **is**
  implemented; the pre-integration explanation below is kept for reproducing
  the base product only.

### What "not integrated yet" actually looks like (do not invent a `not_ready` error)

The routes in this guide (`POST /api/v1/sources`, the receipt/content
endpoints, `POST /api/v1/tasks/{task_id}/messages` and
`POST /api/v1/conversations/global/messages`) **already exist** in the base.
They are **not** "unregistered routes returning `404`", and there is **no**
`not_ready` error code in the base. What is missing before LG-046 is only the
**additive optional `selected_sources` field** on the two message DTOs.

Because the base request DTOs are declared with
`ConfigDict(extra="forbid")` (see `backend/lightgravity/coordinator/api.py`
`AppendMessageRequest` and `backend/lightgravity/api/conversations.py`
`GlobalMessageRequest`), sending `selected_sources` to a **not-yet-integrated**
base is rejected as an **unknown field** with `validation_failed` (**422**),
not `404` and not a fabricated `not_ready` code. The upload and source-read
endpoints work unchanged on the base. So:

- On the **integrated `main` after LG-046**: the message request accepts
  `selected_sources` and the flows below apply as written.
- On the **base / pre-integration branch**: upload and source reads still work,
  but any message carrying `selected_sources` may return `422`
  `validation_failed` because the field is not yet registered. Record that as
  "field not integrated yet", **not** as a prototype defect and **not** as a
  `not_ready` response.

### Start the app with the existing CLI (do not invent commands)

Use only the commands that already exist in this repository. The canonical
start command from the [README](../README.md) is:

```bash
uv sync                                   # rebuild backend deps from uv.lock
uv run lightgravity start \
  --data-dir ./bot-data --workspace-root ./bot-data/workspaces \
  --secret-store ./secrets --host 127.0.0.1 --port 8000
```

`make serve` builds the frontend first and then starts; `make run` is the
backend-only shortcut. The server listens on **loopback only** by default.
Open <http://127.0.0.1:8000/> after it starts.

> The prototype does **not** add a new start command, a new installer, or a
> new service. If a command is not documented in the README, it does not
> exist — do not type a guessed command and report its failure as a prototype
> defect.

### Credentials

- Model credentials come **only from the process environment** (or a controlled
  `credential_ref` through Settings). They are never written to Markdown, chat,
  logs or commits.
- **Never** paste a real key into a `curl` example, a prompt, or a document.
  The examples below contain no key material by design.
- The backend enforces a **hard global generation budget before forwarding**;
  see the LG-047 budget rule in §7.

## 2. Fixture corpus

| File | Use |
|---|---|
| `fixtures/alpha-brief.txt` | Primary source, project **ORION-71**. |
| `fixtures/beta-brief.txt` | Secondary source, project **LUMEN-33**. |
| `fixtures/gamma-decoy.txt` | Contradictory decoy — select it **never** (only in a deliberate leakage test). |
| `fixtures/cross-task-negative.txt` | Cross-Task isolation negative marker. |

`expected-facts.json` holds the fixture truth. Examples of what a correct
answer about the selected `alpha-brief.txt` must contain: `ORION-71`,
owner `Halden Reyes`, launch `2027-03-14`, budget `418,250 EUR`, project ID
`PRJ-ORION-71`, change ticket `CB-8842`. It must **not** contain the decoy
values (`ORION-99`, `Dana Whitfield`, `2028-09-01`, `999,999 EUR`).

Run the offline fixture check (no network, no model):

```bash
python3 examples/selected-material-prototype/check_fixtures.py
```

> **Expected outcome is conditional.** Passing this script only means the
> assets parse and link correctly. It says nothing about any model answer.

## 3. Flow A — upload → intake receipt → select → ask → open source

This is the "ask a fact question" flow. It uses the **existing** source
endpoints recorded in [docs/08 §4.3](08-interface-contract.md):

- `POST /api/v1/sources` — register one intake request (idempotent via
  `request_id`); it lands the original and does not create a Task/Run.
- `GET /api/v1/sources/{source_id}/receipt` — the real per-file receipt.
- `POST /api/v1/tasks/{task_id}/messages` (or
  `POST /api/v1/conversations/global/messages`) with the additive optional
  `selected_sources` field.

### Step A1 — upload a fixture and wait for the real intake receipt

Upload is Chat-first in the product direction; for a scripted QA step the
existing `POST /api/v1/sources` accepts an inline body. Use **placeholders**
for IDs and never hardcode a real source id or hash — the UI/API ids and
version hashes come from the actual upload:

```bash
# Placeholders only — <BASE64_OF_FIXTURE> stands for the bytes you actually read.
curl -sS -X POST http://127.0.0.1:8000/api/v1/sources \
  -H 'Content-Type: application/json' \
  -H 'X-LG-Token: <UI_TOKEN>' \
  -d '{
    "request_id": "req_sample_alpha_001",
    "filename": "alpha-brief.txt",
    "content_base64": "<BASE64_OF_FIXTURE>",
    "media_type": "text/plain",
    "title": "ORION-71 brief (sample)",
    "scope": { "task_ref": null, "project_ref": null, "inbox_ref": null }
  }'
```

- `<UI_TOKEN>` is the runtime token the app injects into the page; it is **not**
  a model credential.
- The response returns the real `source.id`, `source.source_version` and
  `source.content_hash`. **Record those values from the actual response**;
  they are what you pass as `selected_sources` later. Do not invent them.
- The response also contains `job` and `receipts`. **Wait until the receipt
  reflects completion** (`job.status` reaching a terminal value and the
  receipt showing the file) before selecting. The guide deliberately does not
  pin an exact polling interval — poll the receipt endpoint and stop when it
  reports done:
>
> **R1 fact:** for a **native text** `media_type` the program runs a minimal
> synchronous **model-free** pump after receive, so the source reaches terminal
> `extracted`/`done` and a machine derivative exists without any OCR or manual
> seed. For **PDF/image** the source stays `received` until you call the
> explicit `reprocess` OCR action (unchanged). If a selection reports
> `capability_unavailable` (**503**) the source has no readable body yet.

```bash
curl -sS http://127.0.0.1:8000/api/v1/sources/<SOURCE_ID>/receipt \
  -H 'X-LG-Token: <UI_TOKEN>'
```

### Step A2 — select 1–2 sources and ask a fact question

Send a message that carries the additive optional `selected_sources` array.
Use the **real** `source_id` / `source_version` / `content_hash` captured in A1.

The actual registered message request DTOs (both task and global) require
`message_id` and `content`; `role` is **optional** and defaults to `"user"`.
The sample below includes all currently-required fields plus an explicit
`role` for clarity:

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/tasks/<TASK_ID>/messages \
  -H 'Content-Type: application/json' \
  -H 'X-LG-Token: <UI_TOKEN>' \
  -d '{
    "message_id": "msg_sample_q1_001",
    "role": "user",
    "content": "Using only the selected brief, what is the project code name, the programme owner, the primary launch date, and the total approved budget?",
    "selected_sources": [
      { "source_id": "<SOURCE_ID_FROM_A1>",
        "source_version": <SOURCE_VERSION_FROM_A1>,
        "content_hash": "<CONTENT_HASH_FROM_A1>" }
    ]
  }'
```

> **Wire caveat (verified against the actual DTO).** `selected_sources` is an
> **additive optional** field that only exists once LG-043/LG-046 is integrated.
> On the base DTOs (`extra="forbid"`) it is an unknown key and the request is
> rejected with `validation_failed` (**422**) — not `404`, not `not_ready`.
> The same applies to the singleton global route; legacy senders that omit the
> field behave exactly as before (§1, docs/10 §2 risk note).

- **Task scope:** selecting a source whose `scope.task_ref` differs from the
  current Task and is not `global` is rejected with `reference_invalid` (422)
  **before** model dispatch. See §6.
- **Global scope:** the singleton global conversation accepts the same field;
  selection there is global and still must not be carried into a Task.

The reply's `data` carries `resolved_source_bindings`, `context_truncated` and
`provided_context_note`. Verify that:

1. `resolved_source_bindings[].source_id` matches what you selected;
2. `provided_context_note` says citations are **not** span-verified;
3. `char_count` is within the 12000 Unicode-char total budget and, if
   `truncated` is true, `truncation` includes
   `{reason, original_char_count, kept_char_count, max_total}`.

### Step A3 — open the actual source

Open the real bytes through the existing content endpoint and confirm the text
you selected is the text you see:

```bash
curl -sS "http://127.0.0.1:8000/api/v1/sources/<SOURCE_ID>/content?kind=auto" \
  -H 'X-LG-Token: <UI_TOKEN>'
```

`kind=auto` previews the `formal` layer if present, otherwise the `machine`
derivative — matching the `layer` reported in `resolved_source_bindings`.

### Step A4 — judge the answer

Compare the reply to `expected-facts.json`. The program has already told you
which text it provided; your job in QA is only to check whether the answer is
consistent with that text and the fixture truth, and whether decoy values
leaked.
>
> **R1 fact — reopen the history:** the assistant answer (and, when a selection
> was present, its `resolved_source_bindings` / `selected_context` snapshot) is
> persisted in the **same conversation** the user message used, so a reopen of
> `GET /api/v1/tasks/{task_id}/messages` (or the singleton
> `/api/v1/conversations/global/messages`) shows the `assistant:<message_id>`
> row. `Sources` still means *provided context*, **not** verified citations.

> **Expected outcome (conditional, not a measurement):** if the selected
> source, the real `ModelDialogue` path and the environment are all healthy,
> the answer is expected to contain the fixture facts for the selected brief
> and to contain **no** decoy values. This sentence states an expectation, not
> an observed model result. If any precondition is missing (no default
> connection, revoked source, stale hash), the correct outcome is the
> documented rejection below — not a fabricated answer.

## 4. Flow B — selected material → explicit file-delivery task → view artifact → acceptance

This is the "produce a deliverable" flow. It uses the **existing** delivery
machinery; the prototype only adds selection context.

### Step B1 — select material, then state a concrete delivery task

Use a delivery intent that matches the **existing classifier verbs**. A plain,
known-intent phrasing that maps to an existing file-producing action is:

> "Create a Markdown file summary with these exact fixture facts: project code
> name ORION-71, programme owner Halden Reyes, primary launch date 2027-03-14,
> total approved budget 418,250 EUR."

Send it as a Task message with `selected_sources` exactly as in A2. The key
point: the request names a **concrete deliverable** (a Markdown file with
specific facts). Do **not** phrase it as open-ended research or a full
document project — that capability is **not** what this prototype validates.
>
> **R1 fact:** an ordinary Chat delivery that names neither acceptance criteria
> nor a workspace now gets a program-derived checkable acceptance criterion and
> an authorized Task workspace, so the unchanged `PlanValidator` accepts the
> default rule plan (previously the default delivery failed plan validation).
> **Erratum (2026-10-16, LG-048 diagnosis):** that default plan is **not** a
> single worker for a normal Chat delivery — it runs the existing `deliver` +
> `verify` SDK worker nodes **sequentially in one execution slot**, followed by
> the independent ModelReviewer; all are budgeted and preserved (not weakened).
> `verify` (an SDK node behind the program machine gate) is **not** the
> independent ModelReviewer. No planner model call is added.

### Step B2 — wait for the delivery to reach acceptance

Follow the normal delivery lifecycle (see [docs/04](04-bot-behavior.md) and the
[README](../README.md) "交付 Task" section): the program generates the minimal
rule-based plan, recruits, executes, machine-checks, then the independent
reviewer step. A worker's self-reported success only enters verification.

> **Reviewer note:** if no independent reviewer connection is configured,
> review is honestly `unavailable` and acceptance is **blocked**. That is the
> correct behavior, not a bug to work around.

### Step B3 — view the artifact

```bash
curl -sS http://127.0.0.1:8000/api/v1/tasks/<TASK_ID>/artifacts \
  -H 'X-LG-Token: <UI_TOKEN>'
```

Preview a canonical evidence artifact by its `evidence:` reference through
`GET /api/v1/tasks/{task_id}/artifacts/content`. Confirm the artifact quotes
the exact fixture facts that were provided in context.

### Step B4 — user acceptance

Acceptance is explicit and human. Use `POST /api/v1/tasks/{task_id}/actions`
with `action: "accept"` and the optional `expected_requirements_revision` /
`expected_deliverable_revision`. If the revisions do not match, the program
returns `acceptance_stale` and the decision does not apply to a newer version.

> **Expected outcome (conditional):** when the worker/verifier path is healthy,
> the artifact is expected to contain the exact provided fixture facts and to
> be acceptable. When it is not, the run must stop honestly (`unavailable`,
> `recovery_required`, or a documented error) — never claim success.

## 5. Negative and edge cases to document (frozen error codes)

Each case below is **rejected before model dispatch** using **existing**
[docs/08 §4.2](08-interface-contract.md) error codes. No new codes were added.
QA documents whether the real system returns these codes; it does not invent
new ones.

| Case | How to trigger | Expected code | HTTP |
|---|---|---|---|
| Over limit | Put 4 entries in `selected_sources` | `validation_failed` (details `max_selected_sources: 3`) | 422 |
| Stale | Send a `source_version`/`content_hash` that no longer matches | `source_stale` | 409 |
| Revoked | Select a source that was revoked (`status=archived` revoke marker) | `not_found` (details `revoked: true`) | 404 |
| Cross-Task | Select a source whose `scope.task_ref` is another Task (non-global) | `reference_invalid` | 422 |
| Missing / unreadable body | Select a source with no readable body | `not_found` or `capability_unavailable` | 404 / 503 |
| Truncation | Provide material whose total body exceeds 12000 Unicode chars | explicit truncation with `truncation` metadata (see below) | 200 |

### Cross-Task / stale / revoked / 3-limit construction without new OCR

- **Cross-Task:** upload `cross-task-negative.txt` under Task A, then try to
  select it while Task B is active. Expect `reference_invalid` (422). No OCR is
  involved — it is plain UTF-8 text.
- **Stale:** record the `source_version`/`content_hash` at first upload, then
  create a new version of the same source, then send the **old** pair. Expect
  `source_stale` (409). Again no OCR.
- **Revoked:** use `POST /api/v1/sources/{source_id}/actions` with
  `action: "revoke"`, then attempt any read or selection. The frozen revoke
  semantics are **fail-closed**: reads and reprocess are rejected with
  `not_found` (404, `details.revoked=true`). Original bytes remain on disk
  (`revoke` ≠ `delete`).
- **3-limit:** send a four-element `selected_sources` array. Expect
  `validation_failed` (422) with `details.max_selected_sources = 3`.
- **Truncation:** the frozen choice is **explicit truncation with metadata**
  (`truncated: true`, `truncation: {reason, original_char_count,
  kept_char_count, max_total}`). The contract also permits reusing the
  existing limiter rejection; the backend owner declares the implemented
  branch. QA documents which branch is live rather than assuming.

> **Scope reminder:** the fixture corpus needs **no new OCR** to exercise any
> case above, because every fixture is plain text. Do not add OCR just to
> produce these negative cases.

## 6. Scope isolation and untrusted-data rules

- Selection scope is `global` or a single Task; switching Task **clears** the
  selection (docs/10 §8). Selection is never carried across Tasks.
- Selected text is **untrusted data, not instructions**. The program wraps it
  with explicit delimiters and labels its origin. The model must not treat it
  as permission or as a task instruction, and the program grants no permission
  based on it.
- `Sources` is a **provided-context** label, not a verified-citation claim.
  The UI must not present it as a verified authority.

## 7. LG-047 budget and replay discipline

- **Historical budget rule (retained):** the **only** LG-047 product budget is **12 real DeepSeek requests across
  all attempts** (including every retry and reviewer turn), **retry 0**,
  **serial**, **per-request wall ≤ 90 s**. There is **no** automatic growth and
  **no** new quota; growth requires PM re-planning. R1 (FAIL) and R2 (FAIL/INCOMPLETE,
  8/8 exhausted) are kept as historical cost records; the **R3 `N-R3-LIFECYCLE`**
  campaign (PM-authorized **cap 16**) consumed **8/16** and passed. **Cumulative cost
  across R1/R2/R3 is unknown, not 0.**
- The backend enforces a **hard global generation budget before forwarding**,
  and it is a **per-campaign persistent ledger** that is **not reset**. The
  limit is observed through `GET /api/v1/diagnostics/generation`.
- This guide must be driven without **unbounded replay**: if a step fails,
  record the failure, keep the gate open, and do not loop the whole flow
  repeatedly to "get a green run".
- Credentials are environment-only. Never print or echo them.

**This guide itself makes no product, model or network call.** Driving it in
LG-047 does consume the budget above; nothing here spends it.

## 8. What "done" looks like for a single attempt

For one attempt, record:

1. The real `source_id` / `source_version` / `content_hash` returned by upload.
2. The `resolved_source_bindings` returned in the reply.
3. Whether the answer matched the fixture truth and whether any decoy value
   leaked.
4. For Flow B, the artifact reference and the reviewer outcome.
5. Any rejection, with the exact error code and HTTP status.

A passing attempt is still **not** user final acceptance. Report observations and
compare them against the version QA record (LG-047 is `done`,
PASS_WITH_LIMITATIONS; user final acceptance remains pending).

## 9. Limits of this guide

- One full lifecycle run has been observed and independently QA-verified
  (LG-049 `N-R3-LIFECYCLE`, PASS_WITH_LIMITATIONS, 8/16); the browser UI
  evidence is reused from I (frontend tree unchanged) and no full test suite was
  re-run (product code unchanged). The prototype is still not a claim of
  user final acceptance.
- No OCR truth is claimed; fixtures are plain text samples.
- This guide contains no hardcoded real source id or real hash, and no secret.
  IDs and hashes are always taken from the actual upload response.
- Endpoints are described per the frozen [docs/10](10-selected-material-prototype.md)
  / [docs/08](08-interface-contract.md) §6.6.1 contract. The message routes
  themselves are not new; only the `selected_sources` field is additive. Before
  LG-046 integration, selecting a source over the message route is rejected as
  an unknown field (`422 validation_failed`), **not** with `404`/`not_ready`.

## See also

- **Review/demo entry (actual run to inspect):** [N-R3-LIFECYCLE REPORT](../probes/prototype-selected-material-20261016/N-R3-LIFECYCLE/REPORT-N-R3-LIFECYCLE-20261016.md)
  with raw evidence under `probes/prototype-selected-material-20261016/N-R3-LIFECYCLE/{evidence,raw,campaign}/`
  (uploaded `alpha-brief.txt`, written `orion-summary.md` with the 6 facts, run/ledger).
- Closure report: [K-RELEASE-CLOSE](../probes/prototype-selected-material-20261016/K-RELEASE-CLOSE/REPORT.md)
- Frozen contract: [docs/10-selected-material-prototype.md](10-selected-material-prototype.md)
- Interface contract: [docs/08-interface-contract.md](08-interface-contract.md) §4.2, §5.2, §6.6.1
- Source design direction: [docs/09-source-intake-and-retrieval.md](09-source-intake-and-retrieval.md)
- Demo assets: [examples/selected-material-prototype/README.md](../examples/selected-material-prototype/README.md)
