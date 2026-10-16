---
title: "LG-040 TRANSITION-QA-20261016 — independent final QA REPORT"
doc_type: report
category: qa
status: "final — verdict PASS_WITH_LIMITATIONS (original 2.6s transient defect closed: zero max overshoot + valid in-bound readiness on new actual runs; known limitations retained)"
updated: "2026-10-16"
verdict: PASS_WITH_LIMITATIONS
candidate_commit: 30029eb95465c32fde94dcf7ce44ae18db4a43a0
probe_commit_worktree: "/home/yhvh/code/lightgravity-bot-worktrees/lg040-transition-qa-20261016"
probe_branch: "qa/lg040-transition-20261016"
---

# LG-040 TRANSITION-QA — independent final QA (FRESH, owner-only probe)

## 0. Verdict

**PASS_WITH_LIMITATIONS.** This independent QA of candidate
`30029eb95465c32fde94dcf7ce44ae18db4a43a0` (LG-040 transition CSS fix) finds
**0 open important defects** in the scope tested, and specifically **closes the
original ~2.6 s transient narrow-390 overflow defect** on **new actual**
(build + real app + real Firefox BiDi) evidence:

- **Fresh independent build**: `tsc --noEmit` `EXIT=0`; `vite build` `EXIT=0`;
  the built bundle CSS `index-DRJ4h6SM.css` sha256
  `a62d304df63662e4fae57a6d31c1ee5d65a83dd3c464c7aa36bcda4ae11769f0` **matches
  the implementer's claimed hash**, and the compiled rule
  `lg-chat-rail,.lg-workspace>.lg-resizer{display:none}` is present in the
  served bundle (source-CSS ↔ served-bundle hash binding).
- **Zero max overshoot during transition**: rAF sampling through a 1440→390
  resize (n=195) and a 390 initial-load + Chat→Files nav (n=213 in sampler,
  n=125 in the transition driver) records `maxOvershoot = 0`, `nOver2 = 0`
  everywhere; a sustained-starvation probe records **0 overflow across 1986
  samples** at 390. The pre-fix recorded `docScrollWidth 428` does **not**
  reproduce.
- **Valid in-bound readiness**: with the QA-corrected geometry predicate
  (panels nonzero + action buttons visible + rail hidden; CSS `display:none` /
  zero rendered width accepted, DOM unmount **not** required), readiness is
  `ready=true` at **76 ms**, well inside the **2 s** bound. Threshold was **not**
  relaxed to 8 s.
- **19/19** steady width/interaction cases pass (390 / 1024 / 1440, panels
  nonzero, long-hash wrap, own-scroll preview, Chat@390, desktop two-panel grid).

The **old raw FAIL is preserved unchanged** (`evidence/prior-raw-FAIL/`,
`docScrollWidth 428`), not re-labeled. This report issues a whole-package
LG-040 verdict **PASS_WITH_LIMITATIONS** with the pre-existing disclosed limits
retained (§7). **Never a claim of global safety, cost, or user final acceptance.**

## 1. Authority, scope, constraints (independently honored)

- Independent final QA; **not** the implementer. Root-PM-level only.
- Own worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg040-transition-qa-20261016`,
  own branch `qa/lg040-transition-20261016`, HEAD `30029eb` (created fresh from
  `30029eb`; base main `fc9f74b` untouched).
- Owner writes `probes/lg040/TRANSITION-QA-20261016/**` only. **No** product
  change, task-status change, upstream inference, network OCR/ASR, uploads,
  push/deploy, or `:8123` use; **no** original-data mutation.
- Reused the **whole working** runner/launcher/deny-proxy and the **already-tested**
  transition/starvation/width drivers as byte-identical copies, with only own
  path constants (`ROOT = parents[4]` → this worktree; `FIXTURE_DIR` → own probe).
  No orchestrator was reinvented.
- Runtime isolated on the owner **copy** of the prior real snapshot, on ephemeral
  loopback ports, behind a **loopback DENY proxy**. Read-only w.r.t. product data.
- Work stayed bounded; report + commit prioritized over further investigation.

## 2. Candidate / bundle binding

| Field | Value | Source |
|---|---|---|
| Candidate commit | `30029eb95465c32fde94dcf7ce44ae18db4a43a0` | `git rev-parse HEAD`; run bindings |
| Branch under test | `qa/lg040-transition-20261016` | bindings |
| Source `frontend/src/app/shell.css` sha256 | `b2b3ca8b54b4d0953a771e70dad9cbeed0cb376b5795caf13628a7eaa83b2132` | `bundle-bindings.txt` |
| Built bundle CSS `index-DRJ4h6SM.css` sha256 | `a62d304df63662e4fae57a6d31c1ee5d65a83dd3c464c7aa36bcda4ae11769f0` | fresh `vite build` |
| Built bundle JS `index-D9QzHlXV.js` sha256 | `a7f185d41d22b8dfc8357e7385c3bebb89e4f8407fb4c08c8ada793b2ff5f5f5` | fresh build |
| `dist/index.html` sha256 | `8240d114205736ea9052702eebccefc631383448006cec4d065aa90fa143d5db` | fresh build |
| Compiled collapse rule present | `lg-chat-rail,.lg-workspace>.lg-resizer{display:none}` | grep of built CSS |
| Owner snapshot tree | 55 files, sha256 `a991743489cea30d70677c1a478acef94e7d79d76aa0643a6acfd393221b1646` | bindings (identical across all runs) |

The CSS sha256 here is **independently reproduced** from a fresh build and equals
the value the implementer reported, binding this QA to the same served bundle.

## 3. Fresh build receipts (recorded stdout + EXIT)

| Command | Log | EXIT |
|---|---|---|
| `npx tsc --noEmit` | `evidence/run/tsc-noEmit.log` | `0` (`tsc-noEmit.exit`) |
| `npx vite build` | `evidence/run/vite-build.log` | `0` (`vite-build.exit`) |

`vite-build.log` tail: `✓ 100 modules transformed` / `dist/assets/index-DRJ4h6SM.css 35.14 kB`
/ `dist/assets/index-D9QzHlXV.js 283.11 kB` / `✓ built in 1.10s`.

## 4. New actual runs — decisive results (own raw JSON)

All runs used the real app (`python -m lightgravity start` path via `launch_app.py`,
`serve_frontend=True`, `wire_real_executor=False`), the real built `frontend/dist`,
and real Firefox WebDriver BiDi. **Deny ledger attempts = 0** in every run
(§6).

### 4a. Transition driver — `evidence/run/transition-results.json`
`captured_at 2026-10-16T07:21:23.189Z`, `bound_ms 2000`. Verdict
`all_transitions_clean=true`, `all_steady_clean=true`.

| Sample set | nSamples | maxOvershoot | nOver2 |
|---|---|---|---|
| resize 1440→390 (Files) | 195 | **0** | 0 |
| nav 390 Chat→Files | 125 | **0** | 0 |
| roundtrip 390→1440→390 | 252 | **0** | 0 |
| case17 1440→390→Files/Materials | 211 | **0** | 0 |
| steady 1440 Chat | 55 | **0** | 0 |
| steady 1440 Files | 55 | **0** | 0 |
| steady 390 Files | 44 | **0** | 0 |
| steady 1024 Files | 43 | **0** | 0 |
| steady 1440 Files (again) | 44 | **0** | 0 |

`final390`: `innerWidth 390, docScrollWidth 390, bodyScrollWidth 390,
chatRailPresent false, materialsPresent true, list 310, detail 310, entries 3`.

### 4b. Sustained starvation probe — `evidence/run/starvation-results.json`
`captured_at 2026-10-16T07:22:02.664Z`, `bound_ms 2000`:
`nSamples 1986, maxDoc 390, maxOvershoot 0, nOverflow 0, firstOverflow null`.
Final sample `{t:2000, vw:390, doc:390, rail:null, listW:310, detailW:310,
entries:3}`. Verdict `no_overflow_throughout=true`,
`rail_hidden_or_absent_at_390=true`, `materials_panels_usable=true`.

### 4c. Width/steady matrix — `evidence/run/lg040-files-narrow-results.json`
`tested_at 2026-10-16T07:22:41.628Z`: **counts total 19, passed 19, failed 0**.
Covers 390/1024/1440 no-overflow, list+detail nonzero, long hash/path wrap,
English actions in-viewport, preview own-scroll, Chat@390 search, and desktop
1440 two-panel grid.

### 4d. Own corrected transition sampler — `evidence/run/qa-transition-sampler.json`
`captured_at 2026-10-16T07:24:13.015Z`. Own sampler (bounded, single driver,
reuses the tested BiDi helper pattern; **not** a new harness framework) that
**fixes the incorrect DOM-removal heuristic** and asserts the task's geometry
readiness:

- resize 1440→390: `nSamples 196, maxOvershoot 0, nOver2 0`.
- initial-390 + Chat→Files nav: `nSamples 89, maxOvershoot 0, nOver2 0`.
- **bounded readiness**: `ready=true, readyAtMs=76`, `sawTransientOverflow=false`,
  final `{listW:310, detailW:310, docScrollWidth:390, railHidden:true,
  railPresent:false, actionsVisible:["Save correction","Archive","Download original"],
  overflow:false}`.
- steady: 390 `doc 390, listW 310, detailW 310`; 1024 `doc 1024, listW 276,
  detailW 276`; 1440 `gridTemplateColumns "320px 360px"` (two-panel retained).
- Chat@390: `doc 390, overflow false, hasSearch true`.

`verdict`: `readiness_ready_within_2s=true`, `readiness_readyAtMs=76`,
`resize_no_overshoot=true`, `initial390_nav_no_overshoot=true`,
`steady_no_overflow=true`, `steady390_panels_nonzero=true`, `chat390_no_overflow=true`.

## 5. What this closes and what is preserved

- **Closure of the original ~2.6 s transient defect**: the prior FINAL-QA
  recorded the rail present with `docScrollWidth 428` at 390 and readiness at
  2592 ms with an 8000 ms bound (rejected by PM for the 8 s relaxation). This QA
  closes that defect **only** on new actual evidence of **zero max overshoot**
  and **valid readiness** (`readyAtMs 76 ≤ 2000`). The 2 s bound was **kept**;
  it was never relaxed to 8 s.
- **Corrected heuristic, not relaxed threshold**: the prior settled driver
  required `.lg-chat-rail` to be **removed from the DOM**; the CSS fix uses
  `display:none` (node stays mounted). The corrected predicate accepts
  `display:none` / zero rendered width and instead requires nonzero panels +
  visible actions + stable geometry, still bounded at 2 s. If readiness were
  slower than 2 s the case would be **FAIL**, not relaxed.
- **Old raw FAIL preserved**: `evidence/prior-raw-FAIL/` holds unmodified copies
  of the pre-fix raw records, including the failing assertion
  `narrow 390 Files Materials: no horizontal overflow` with
  `docScrollWidth 428, overflow true` (`lg040-retest-results.pre-fix.json`), and
  the pre-fix settled 20/21 run and pre-fix drivers. See its `README.md`.

## 6. Isolation, safety, stop state

- **Deny proxy ledger = 0 attempts** in all 5 runs (`ledger.json`:
  `{"attempts": 0, "events": []}`). No OCR, no inference, no uploads, no
  reprocess, no LAN calls.
- Snapshot is a **read-only copy**; original product data and the source worktree
  were not mutated. Snapshot tree hash identical across runs
  (`a9917434…`, 55 files).
- Own children stopped in every run (`run_one_driver.py` finally-block: proxy +
  app SIGTERM→SIGKILL). Post-run check: **no lingering** drivers/launchers/Firefox
  from this probe.
- `:8123` pre-existing long-lived service (pid 3320750, PPid=1) **untouched**;
  no broad `pkill`. No push/deploy.

## 7. Milestone audit (succinct; prior independent receipts combined)

- **Main `fc9f74b`** records the FINAL-CANDIDATE `5d32b04` (5-source sequential
  `--no-ff`; backend unchanged; frontend Files CSS + test-only race fix), plus
  API 39/39, retest 16/16 TCP, 219 p1-skip, mypy 138, quality method audit, race
  full 863 p5-skip valid completed, and Files CSS. (Sourced from the FINAL-QA /
  SETTLED-QA reports and the main commit message; not re-derived here.)
- **Backend unchanged since `75c`**: existing independent API 16/16 retest and
  all runtime except shell/Files CSS are unchanged; the candidate `30029eb` is a
  shell-CSS-only delta on top of `fc9f74b`.
- **Prior browser receipts cited, not rediscovered** (short sections):
  - `lg040-browser-retest-r1-20261016` (`59fe58e`): real UI search 2/2 PASS;
    revoke fix re-confirmed; narrow-390 Files overflow observed.
  - `lg040-final-qa-20261016` (`925f828`): 1 narrow transient FAIL, raw preserved.
  - `lg040-settled-qa-20261016` (`8a4560a`): 21/21 settled + 19/19 width but
    readiness 2592 ms with 8000 ms bound → **REJECTED as closure by PM's explicit
    2 s requirement**.
  - The `30029eb` CSS fix is a **new candidate**; this report supplies the new
    own actual checks (build + transition 0 overshoot + in-bound readiness) that
    the earlier 8 s-bound candidate lacked, with source-hash binding to the same
    served bundle.

## 8. Functional coverage / limitations (retained, not new blockers)

**Covered by new actual evidence:** fresh build (tsc/vite EXIT 0); transition
1440↔390 + initial-390 nav zero overshoot; bounded ≤2 s geometry readiness with
corrected predicate; steady 390/1024/1440 panels/actions/long-hash wrap/
preview-own-scroll/two-panel grid; Chat@390; deny ledger 0.

**Retained limitations (pre-existing, disclosed, not fixed here):**
- Original G2 top-1 experiment FAIL (rank-2 behind exact-text twin 1).
- TIFF honest unsupported; no ASR for any language; small English-primary sample.
- Chinese currently accepted at rank 7; table mode optional, default OFF.
- Browser whole-package invocation count **UNKNOWN ≥ 2** with ledger reset in
  earlier slices; cost unknown. Quality durable: 2 OCR + 17 embedding.
- Source revoke `404` all variants; `archived` bool is separate semantics
  (confirmed in prior slices).
- This QA runs were bounded to 2 startup attempts/90 s each; no speculative
  loops; no new test-harness framework.

These limitations are not defects of `30029eb`; they are carried forward from the
milestone and do not block acceptance on the transition fix.

## 9. Files of record

- `REPORT.md` (this file), `STATUS.md`
- `scripts/` — reused-verbatim runner/launcher/deny-proxy + tested
  transition/starvation/width drivers + own bounded `lg040-qa-transition-sampler.mjs`
- `evidence/run/` — build logs + EXIT files, bundle bindings, all raw run JSON +
  screenshots
- `evidence/snapshot/` — read-only 55-file data copy (hash `a9917434…`)
- `evidence/prior-raw-FAIL/` — preserved unmodified pre-fix raw FAIL records

Verdict: **PASS_WITH_LIMITATIONS** — 0 open important defects in the transition
scope; original 2.6 s transient closed by new actual zero-overshoot +
in-bound-readiness evidence; prior raw FAIL preserved; **user final acceptance
pending**.
