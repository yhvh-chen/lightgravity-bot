---
title: "LG-040 SETTLED-QA-20261016 — independent settled-layout QA REPORT (FINAL)"
doc_type: report
category: qa
status: "final — verdict PASS_WITH_LIMITATIONS (required settled-layout coverage now actually passes; known limitations retained)"
updated: "2026-10-16"
verdict: PASS_WITH_LIMITATIONS
candidate_commit: 5d32b0414bab83d48be49be65f78331923f641c5
probe_commit: 925f8288ddc93656c6e7551d5d73251829ed3eaa
---

# LG-040 SETTLED-QA — independent settled-layout QA (FINAL)

## 0. Verdict

**PASS_WITH_LIMITATIONS.** This finalizer closes the **exact remaining block**
recorded by the prior FINAL-QA report (`probes/lg040/FINAL-QA-20261016/REPORT.md`,
commit `925f828`): the single recorded narrow-390 Files Materials overflow FAIL,
which the prior report itself classified as a harness/timing artifact but could
not resolve because its capture happened **mid-transition**.

In this worktree (`qa/lg040-settled-20261016`) new **actual** browser runs were
executed **after** the layout settles, on the **product-identical** candidate and
the **same served bundle** the prior report bound:

- New settled narrow-390 Files Materials sampling shows the rail present and
  page overflow (428 px) **only transiently**, then rail removed + detail
  rendered and geometry stable at 390/390 with **no overflow**.
- New **19/19** narrow/mid/desktop width run on the same candidate/served bundle
  records **no horizontal overflow at any width and both panels nonzero**.
- New **21/21** settled interaction run (Chat search, Files preview, real
  download, revoke fail-closed, narrow Chat, narrow/at-settle Files) all pass.

Combined with the reused prior API / quality / backend / race receipts (below),
the required coverage is valid, so the release verdict is
**PASS_WITH_LIMITATIONS** (limitations are pre-existing and disclosed, not new
blockers). **Never a claim of user final acceptance.** No product change was made.

### 0.1 Honest qualification on readiness timing (no invented data)

The recorded sampled readiness for the settled narrow-390 case is
**`readyAtMs = 2592`** and the transient-overflow interval is observed from
`t≈3 ms` to `t≈2460 ms` before stable geometry at `t≈2503 ms` (see
`evidence/run/lg040-settled-results.json`, case
"narrow 390 Files Materials: responsive settle within bounded ... no overflow at
settle", `bound_ms: 8000`). The probe bound was 8000 ms, and readiness was
recorded at 2592 ms. **No ≤2 s figure is asserted here** — the actual sampled
value is reported as recorded. The independent **19/19** width run independently
records `docScrollWidth == innerWidth` (no overflow) at 390 / 1024 / 1440 once
settled, which is the decisive settled result.

## 1. Authority, scope, and constraints

- Independent settled-layout QA finalizer. Not the implementation author.
- Worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg040-settled-qa-20261016`,
  branch `qa/lg040-settled-20261016`, HEAD `925f828`.
- Owner writes `probes/lg040/SETTLED-QA-20261016/**` only. No product changes,
  no task-status writes, no push/deploy, no broad report search.
- This continuation performed **no browser/build/test/network/driver runs**.
  It only reads own raw result files, writes this report, and commits own probe
  files. All counted runs below were performed earlier in this probe and their
  raw JSON is preserved in `evidence/run/`.
- Runtime was isolated on owner snapshot copies on ephemeral loopback ports with
  a **loopback DENY proxy** in front of any OCR path.
- **Never touched `:8123`** (long-lived product server, pid 3320750/3320745,
  owned by another process, started from the source tree `/home/yhvh/code/lightgravity-bot`
  on Oct 15, PPid=1) or the source worktree.

## 2. Candidate / bundle binding

| Field | Value | Source |
|---|---|---|
| Candidate commit (product) | `5d32b0414bab83d48be49be65f78331923f641c5` | prior report §2; product tree identical to probe commit |
| Probe commit (this run) | `925f8288ddc93656c6e7551d5d73251829ed3eaa` | `evidence/run` bindings (`bindings.json`) |
| Product delta 925f828 vs 5d32b04 | **none** (925f828 is the QA-report commit; no product files) | `git show --stat 925f828` |
| Served bundle CSS | `frontend/dist/assets/index-DIrliPjY.css` sha256 `661461caffa9c9e459e2a25a91f4328dd732bb67b88bfd800571241d7e3cf8c2` | `sha256sum` (matches prior report §2 exactly) |
| Served bundle JS | `index-B49336kt.js` sha256 `a7f185d41d22b8dfc8357e7385c3bebb89e4f8407fb4c08c8ada793b2ff5f5f5` | bindings |
| Own snapshot data tree | 55 files, sha256 `2d5543e535c6a36e9bd921a9c7710de84e57dd58916d7edabd0915386b8baa0f` | bindings |

Because `925f828` differs from `5d32b04` only by the prior QA report, the product
code under test here is **byte-identical** to candidate `5d32b04`; the served
bundle CSS hash matches the prior report. The prior 13-pass width evidence is
therefore cited as **PRIOR same-candidate evidence**, not as a new run.

**Copied/imported vs new actual runs.** `evidence/snapshot/data` is a
**copied/imported** snapshot of the live data tree (hash above), not raw bytes of
a new live-product run. The browser driver runs are **new actual runs** in this
context (new isolated process launches, new ephemeral ports, new sessions, new
timestamps recorded in the JSON `tested_at`/`captured_at` fields).

## 3. New actual settled runs — recorded results (own raw JSON)

### 3.1 Settled interaction run — `evidence/run/lg040-settled-results.json`

- `tested_at` `2026-10-16T07:07:24.590Z`, url `http://127.0.0.1:45473/`,
  ui_term `correction`, api_term `marker`, `bound_ms` 8000.
- **Counts: total 21, passed 21, failed 0, unverified 0.**
- Includes: Chat search returns source + version + hash back-reference; API
  `rebuild_if_missing "marker"` hit with hash back-check; absent-term honest
  empty; Files preview English actions; real download; revoke accepted on OWN
  copy; revoked preview/download fail honestly (`404 not_found` +
  `details.revoked`); no fake revoked body leaked; other source still works;
  narrow-390 Chat no overflow; single end-state captured.
- **Settled narrow-390 case (decisive):** `ready: true`, `readyAtMs: 2592`,
  `sawTransientOverflow: true`, `transientMaxScrollWidth: 428`, then stable
  `docScrollWidth: 390` / `bodyScrollWidth: 390`, `finalRailPresent: false`,
  `overflow: false`, `nOffenders: 0`, both panels `listPanelWidth: 310`,
  `detailPanelWidth: 310`.

### 3.2 New 19-case width run — `evidence/run/lg040-files-narrow-results.json`

- `tested_at` `2026-10-16T07:08:09.072Z`, url `http://127.0.0.1:60577/`.
- **Counts: total 19, passed 19, failed 0.**
- narrow-390: `docScrollWidth 390` (≤ innerWidth+2), listW 310 / detailW 310,
  long hash/path wrap no clipping, English actions preserved.
- mid-1024: `docScrollWidth 1024`, listW 276 / detailW 276.
- desktop-1440: `docScrollWidth 1440`, listW 320 / detailW 360 (normal two-panel
  grid retained).
- Chat reachable at 390, no overflow, search present.

### 3.3 Settle discrimination — `evidence/run/settled-discriminate.json` and `resize-settle.json`

- `settled-discriminate.json` (`captured_at 2026-10-16T07:05:12Z`): both
  scenarios recorded `nSamples: 0`, `settledAt: null` and `final.overflow:false`
  with `detailRendered:false`. This is the **prior INCOMPLETE one-390
  mid-transition capture** — the sampler did not record a settle, which is
  exactly why the earlier FAIL could not be resolved from it.
- `resize-settle.json` (`captured_at 2026-10-16T07:04:29Z`): every measured
  state (`initial390_beforeFiles`, `initial390_afterGoto`, `desktop1440`,
  `resize1440to390_retestTiming`, `resize1440to390_settled`) records
  `docScrollWidth == bodyScrollWidth == viewport`, `overflow:false`; the
  settled resize records `chatRailPresent:false`.

The new own independent settled proof resolves the mid-transition artifact:
once the rail transition completes, no overflow remains, and the fix is present
in the served build (CSS `661461…`).

## 4. Reused prior coverage (short-known receipts, not re-run)

Cited from prior committed reports (bindings above); these are **reused known
results**, not new runs in this context.

- API original **39/39**; independent API **16/16 actual TCP** (real-TCP revoke
  fail-closed).
- Backend: **full pytest 863 pass / 5 skip** (first valid stdout; interrupted
  second run NOT counted); mypy 138.
- Race test: **600 iterations → 0 incorrect grants** (baseline 300 + fix 300 →
  0 incorrect; fix-own 600 → 0 incorrect). This is **600**, not six-thousand.
- Revoked byte-leak closed / not resurrectable; archive works + cross-Task.
- Quality: **2 OCR + 17 embed** calls, no extra inference; full-page CER 0.0026;
  **G2 image rank2 behind text twin rank1 = FAIL (frozen experiment, known
  limitation)**; **TIFF honest unsupported**; Chinese accepted (current rank 7)
  with **no ASR in any language**; small English-primary quality sample.

## 5. Material disclosures / known limitations (retained)

- Registered historical experiment: **G2 top-1 image FAIL (image rank 2 behind
  its text twin rank 1)** — known limitation.
- **TIFF: honest unsupported.**
- **Quality sample is small and English-primary; no ASR evidence in any
  language;** Chinese accepted at current **rank 7**.
- **Initial BROWSER global calls unknown (>=2)** led to a **ledger reset / cost
  unknown**; quality accounting was **2 OCR + 17 embed** and no other inference.
  No new inference was performed by this probe.
- **archive flag vs revoked status:** `status=archived` with `archived:false`
  (revoked) is expected — the `archived` bool and `revoked` state are **separate
  contracts**; archive preserves retrieval, revoke makes content unavailable.
- Historical first-completed backend pytest **863 pass / 5 skip**; race
  **600 iterations → 0 incorrect** (not six-thousand).
- Width evidence from the prior report: **13 passes on the same candidate** —
  cited as PRIOR same-candidate evidence, not a new run here.

## 6. Process / child / deny / data integrity

- **Own children stopped:** no own `firefox`, `deny_proxy.py`, `launch_app.py`,
  driver, or own listeners alive at finish (checked with `pgrep`). The exact own
  child processes were spawned and reaped by `run_one_driver.py`; no blind
  replays were performed during this continuation.
- **`:8123` untouched** — long-lived product server pid 3320750 (parent
  3320745, PPid=1, started Oct 15 from the source tree). Not owned by this QA;
  **not stopped.**
- **No source-worktree mutation**; original live data only copied (snapshot
  hash above); no symlink/venv/node_modules staged.
- **DENY proxy ledger:** for the settled runs, `ledger.json` recorded
  `{"attempts": 0, "events": []}` — **zero inference attempts reached any
  upstream** (e.g. `/tmp/lg040-settled-width/ledger.json`,
  `/tmp/lg040-settled-final/ledger.json`, `/tmp/lg040-settled-longbound2/ledger.json`).
- **Secret scan** of own probe text files: clean (no API keys/tokens matched).
- **Original data hash:** own snapshot tree sha256
  `2d5543e535c6a36e9bd921a9c7710de84e57dd58916d7edabd0915386b8baa0f` (55
  files) as recorded in bindings; the prior report's live-data copy hash
  (`61745f95…`, 55 files) is a separate copy and is cited as prior evidence only.

## 7. Deliverable & commit

- Committed: this `REPORT.md` + own raw evidence/scripts/fixtures under
  `probes/lg040/SETTLED-QA-20261016/**` only. No product changes. No files
  outside the owner. No `venv`/`node_modules` staged. No task-status or
  `main`/`task` status touched.

## 8. Closing statement

The prior report's single remaining block (settled re-measure of narrow-390
Files Materials overflow on candidate `5d32b04` + served bundle CSS `661461…`)
is resolved by the new actual settled runs recorded here: transient overflow
clears, both panels render nonzero, and the new 19-case width run passes 19/19
with no horizontal overflow at 390 / 1024 / 1440. With reused API / quality /
backend / race receipts intact, the verdict is **PASS_WITH_LIMITATIONS**. The
disclosed limitations above remain and are not claimed resolved. User final
acceptance is not asserted.
