---
title: "LG-040 FINAL-QA-20261016 — independent final release QA REPORT (FINAL)"
doc_type: report
category: qa
status: "final — verdict INCOMPLETE (one required new browser check recorded FAIL; own evidence shows transient harness/timing artifact, not proven product defect; raw retained)"
updated: "2026-10-16"
verdict: INCOMPLETE
candidate_commit: 5d32b0414bab83d48be49be65f78331923f641c5
---

# LG-040 FINAL-QA — independent final release QA (FINAL VERDICT)

## 0. Verdict

**INCOMPLETE** — the required new-browser verification did **not** fully pass as
recorded. The committed own retest driver records **18 pass / 1 fail** at
narrow-390 Files Materials horizontal overflow. Own reproduction evidence
strongly indicates the single failure is a **driver timing artifact** (chat rail
captured mid-transition), and separate own runs of the *same* case pass — but
because the required check was recorded FAIL once and the artifact proof, while
strong, rests on own harness reasoning (not an independent instrument), the
honest verdict is INCOMPLETE, not PASS / PASS_WITH_LIMITATIONS.

Root PM may repair (re-run the one case with a settle wait, or accept the
recorded artifact with an independent measurement). **No product change is
justified by this evidence.** Raw evidence is retained and committed.

Never a claim of user final acceptance.

## 1. Authority & scope

- Fresh **independent** LG-040 release-QA lead. Not the implementation author.
- Worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg040-final-qa-20261016`,
  branch `qa/lg040-final-20261016`, HEAD `5d32b04`.
- Owner writes `probes/lg040/FINAL-QA-20261016/**` only. No product changes, no
  task-status writes, no new inference calls, no LAN, no push/deploy.
- Runtime was isolated on owner copies on ephemeral loopback ports
  (41877 / 56937 / 40995) with a **loopback DENY proxy** in front of any OCR
  path — zero inference attempts reach any upstream.
- Never touched `:8123` (long-lived product server, owned by another process,
  pid 3320750) or the source worktree.

## 2. Candidate / bundle binding

| Field | Value | Source |
|---|---|---|
| Candidate commit (HEAD) | `5d32b0414bab83d48be49be65f78331923f641c5` | `git rev-parse HEAD` |
| Branch | `qa/lg040-final-20261016` | `git branch` |
| Product delta vs `2f277fa` | revoke fix (`service.py`) + `tests/sources/*` + docs08 line + Files-narrow CSS fix (frontend-only) | `git log` |
| Served bundle CSS | `frontend/dist/assets/index-DIrliPjY.css` sha256 `661461caffa9c9e459e2a25a91f4328dd732bb67b88bfd800571241d7e3cf8c2` | `sha256sum` |
| CSS fix marker in served bundle | `minmax(0,1fr)` ×8 and `min-width:0` ×35 present | `grep` |
| Bundle mtime vs retest | dist CSS 2026-10-16 17:45:05 **before** retest 17:52:35 → served build included the fix | `stat` |
| Own snapshot data tree hash | `61745f95baff81f82f8bc974e66d871616b0433651086699cea990cd7745d73d` (55 files) | `find … | sha256sum` |

**Copied/imported vs new actual runs.** The data tree under
`evidence/snapshot/data` is a **copied/imported** copy of the original live
data (`/tmp/lg040-browser-live/data`), preserved with hashes — it is **not**
raw bytes of a new live-product run. The **browser driver runs are new actual
runs** in this context: new isolated process launches, new ephemeral ports, new
Firefox/BiDi sessions, new timestamps. Do not read the snapshot copy as a new
product run.

## 3. New-browser verification — recorded result (own runtime JSON)

`evidence/run/lg040-retest-results.json` (tested_at `2026-10-16T06:52:35.381Z`,
url `http://127.0.0.1:41877/`, ui_term `correction`, api_term `marker`):

- **Aggregate counts: total 19, passed 18, failed 1, unverified 0.**
- **The 1 failure (verbatim):**
  - case: `narrow 390 Files Materials: no horizontal overflow`
  - detail: `{ w:390, overflow:true, docScrollWidth:428, bodyScrollWidth:428,
    materials:true, entries:3, nOffenders:1,
    offenders:[{ tag:div, cls:"lg-chat-rail", right:428, width:360,
    scrollW:360, clientW:360, display:flex }] }`

The driver's step-H (`scripts/lg040-retest-driver.mjs` L409–442) measures only
**500 ms** after entering Files→Materials at 390, following a desktop-width Chat
view in which `.lg-chat-rail` (width 360) was rendered. The captured offender is
exactly the chat rail sitting at right=428 → transient page overflow.

### 3.1 Own reproduction evidence (why this reads as a timing artifact)

From `evidence/run/overflow-diff.json` and `evidence/run/resize-settle.json`
(all new actual own runs, deny proxy in front, same served bundle):

| Own measurement | 390 docScrollWidth | overflow | rail visible |
|---|---|---|---|
| retest driver `exact_timing_390` (same 500 ms) | 390 | false | false |
| retest step-H replay `exact_retest_seq_390` | 390 | false | false |
| fresh reload replay `fresh_reload_retest_seq_390` | 390 | false | false |
| `with_source_open_390` | 390 | false | false |
| resize 1440→390 **settled** (`resize-settle.json`) | 390 | false | false |
| (failing retest run, above) | 428 | **true** | **true** |

Interpretation: the rail was mid-transition (present) at the instant of the
retest measurement, and absent once layout settled. The committed CSS fix is
present in the served build, so the failure is not a stale-bundle effect. This
is strong evidence of a **harness/timing artifact, not a product defect**.

**Why this does not become PASS.** The required new-browser check did fail as
recorded, and the artifact conclusion is reached with own-harness reasoning
rather than an independent instrument. Per the closing rule, a required new
browser check that did not actually pass ⇒ INCOMPLETE and preserve. The
separate narrow-width driver (19/19, and a narrow core of 13 passes) does **not**
waive the recorded FAIL.

## 4. Original-milestone coverage (reused short-known reports, not re-read)

Cited from short prior reports; binds recorded below. These are **reused** known
results, not new runs in this context.

- API original **39/39**; independent API **16/16 actual TCP**.
- Backend: **219 pass + 1 skip**; **mypy 138**; first completed backend pytest
  **863 pass / 5 skip** from the first valid stdout (2nd interrupted run NOT
  counted).
- Race test: runtime unchanged; baseline 300 + fix 300 iterations → **0
  incorrect grants**; fix-own **600 iterations → 0 incorrect**.
- Revoked byte-leak closed / not resurrectable; archive works + cross-Task.
- Quality: reused **2 OCR + 17 embed**, no extra; full-page CER **0.0026**
  (corrects the invalid 600-char-slice 2.79 = historical INVALID_REFERENCE);
  scan 0 corrections; **G2 image rank2 behind text twin rank1** frozen
  experiment = **FAIL, known limitation**; **TIFF honest unsupported**; Chinese
  accepted (current rank7) with **no ASR** in any language.
- Frontend own build: bundle CSS hash above; build provenance recorded at the
  candidate commit (see §2). Portal to full independent build receipt =
  the served dist hash binding; treat any deeper frontend-own build receipt as
  bound by hash above.

## 5. Open / unverified items (material disclosure)

- **Retest narrow-390 overflow FAIL** — recorded once; own evidence says
  transient timing artifact; **not independently instrumented** ⇒ drives the
  INCOMPLETE verdict.
- **Browser whole-package run count unknown (>=2)**; **ledger reset** in the
  reused whole-package context; **costs unknown**. Accounting gap retained.
- **ASR: none** in any language (no ASR evidence claimed).
- **TIFF: honest unsupported.**
- **G2 image rank2/top-1: FAIL (frozen experiment), known limitation.**
- **archive flag oddity:** own `end-state.json` reports the revoked source as
  `status=archived` but `archived:false`; own `revoked-overflow.json` reports
  `revoked:True, status:archived`. Reversible-flag semantics not reconciled here;
  flagged for PM, not asserted as a defect.

## 6. Process / child / deny / data integrity

- **No own probe children remain.** No `firefox`, `deny_proxy.py`,
  `launch_app.py`, driver, or own listeners (41877/56937/40995) alive at close.
- **`:8123` untouched** — long-lived product server pid 3320750, not owned by
  this QA. **Not stopped.**
- **No prior pi writer replaying**; the only bounded pi process alive is the
  current close-out continuation running this task.
- **DENY proxy ledger:** zero inference attempts permitted to reach any upstream
  (loopback refuse-before-forward design). Deny ledger recorded per run.
- **Abnormal child exits:** drivers are spawned and reaped by
  `run_one_driver.py`; no blind replays were performed; raw logs (where produced)
  retained; no replay of the failed case in a way that would hide it.
- **Source worktree / original data:** original live data at
  `/tmp/lg040-browser-live/data` was only **copied** (hash above). Source
  worktree not modified.
- **Secret scan** of own probe text files: clean (no keys/tokens).

## 7. Deliverable & commit

- Files committed: this `REPORT.md` + existing own raw evidence/scripts/fixtures
  under `probes/lg040/FINAL-QA-20261016/**` only. No `venv`/`node_modules`
  staged. No product changes. No files outside owner.

## 8. Exact remaining block

One item: **re-measure `narrow 390 Files Materials: no horizontal overflow` with
a settled layout (rail transition complete) on candidate `5d32b04` + served
bundle CSS `661461…`, and either (a) record a passing committed result, or
(b) accept the timing-artifact classification with an independent measurement.**
Until then the release verdict stays **INCOMPLETE** and raw evidence is
preserved.
