# LG-047 R2 — Classifier English word/command matching fix (OWN PROBE)

- **Worktree**: `/home/yhvh/code/lightgravity-bot-worktrees/proto-material-classifier-fix-r2-20261016`
- **Branch**: `fix/proto-material-classifier-r2-20261016` (base `56a2dd9`, main LG-047 R1 integration candidate)
- **Scope (owner)**: `backend/lightgravity/coordinator/classification.py` +
  `tests/coordinator/test_classification.py` + this probe dir only. No other
  coordinator/source/frontend/QA/shared-PM files touched.
- **No model / network / SDK call** was made; classification is deterministic.

## Confirmed finding (read-only)

`probes/prototype-selected-material-20261016/I-R2-QA/evidence/classifier_finding.json`
(read-only, not modified): the exact handoff goal classified as `decision` /
`decision` with `matched=["approve"]`, because plain substring `"approve" in
"approved"` hit the `_DECISION` control keyword. Result: a delivery goal was
routed as a control message and never created a Task.

## Root cause

`_hit()` used `keyword in text` for **all** keywords. English keywords are
stems (`approve`, `accept`, `cancel`, `stop`, `status`, `cost`, ...) that also
occur inside ordinary derived words (`approved`, `approval`, `acceptance`,
`cancellation`, `statuses`, ...), and control/decision rules run *before*
delivery, so the incidental stem won.

## Fix (smallest deterministic bounded change)

Only `backend/lightgravity/coordinator/classification.py`, reusing the existing
keyword tuples:

1. **English whole-word matching** — ASCII keywords now match on word
   boundaries (`(?<!\w)…(?!\w)`), so `approve` no longer matches inside
   `approved`/`approval`; `accept` not inside `acceptance`; `cancel` not inside
   `cancellation`. CJK keywords keep the original substring semantics (Chinese
   commands unchanged; no new localization).
2. **Incidental control/decision suppression** — during control/decision
   matching only, an ASCII keyword occurrence that is (a) inside a matched
   quote (`"…"`, `'…'`, `` `…` ``, `“…”`) or (b) immediately followed by a file
   extension (`accept.md`) is treated as content/filename, not a command. The
   keyword still matches elsewhere in the message, so explicit
   `Please approve …` stays `decision` and `cancel …`/`pause …` stay `control`.

No model planner, no NLP library, no new endpoints, no schema/version change; no
broad grammar framework. Classification still uses only the **original user
input**; the untrusted selected-material body is unchanged and never classified.

## Evidence

- `raw/classifier_probe.json` — 20 cases, 0 failures, exit 0, including the
  exact observed goal, the QA corrected goal, filenames
  `acceptance.md`/`approved-budget.md`, explicit approve/accept/reject,
  cancel/pause/resume, `How do I create file?`, quoted `"approve"`, and the
  existing Chinese control/read/status/delivery cases.
- `raw/checks.log` — `pytest tests/coordinator tests/api
  tests/sources/test_lg043_selected_material.py tests/contracts` → **240
  passed**; `mypy backend/lightgravity` → **Success: no issues found in 139
  source files**.
- `tests/coordinator/test_classification.py` — added 7 regression tests
  (13 total) covering the finding and the false-positive/regression set.

## Classification results (before → after)

| Input | Before | After |
|---|---|---|
| orion goal (`… total approved budget …`) | decision | **delivery / create_task** |
| Who approved the budget? | decision | **answer / direct** |
| Create acceptance.md | decision | **delivery** |
| Create approved-budget.md | decision | **delivery** |
| Create a doc … cancellation policy | decision | **delivery** |
| Create a file accept.md … | decision | **delivery** |
| `Create a file with the text "approve" inside` | decision | **delivery** |
| Please approve the current candidate. | decision | **decision** (kept) |
| cancel / pause the running task | control | **control** (kept) |
| 取消那个修改任务 / 读这个文件并解释一下 / 现在进度如何？ | unchanged | **unchanged** |
| How do I create file? | answer | **answer** (no write auth) |

## Remaining / boundaries

- Owner is the implementation side only; independent QA is not performed here.
- Root dispatches independent route re-verification and may reuse the actual
  unchanged SDK pipeline proof with the corrected goal; release remains blocked
  on routing until this fix + independent retest.
- No full-backend run beyond the affected sets above (integration binds a very
  tiny diff).
