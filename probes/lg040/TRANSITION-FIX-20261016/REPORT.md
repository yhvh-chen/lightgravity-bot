---
title: "LG-040 TRANSITION-FIX-20261016 — REPORT"
doc_type: report
category: engineering
status: "final"
updated: "2026-10-16"
---

# LG-040 TRANSITION-FIX — REPORT

## 1. Identity

| Field | Value |
|---|---|
| Role | Frontend shell CSS implementer (NOT independent QA) |
| Worktree | `/home/yhvh/code/lightgravity-bot-worktrees/lg040-transition-fix-20261016` |
| Branch | `fix/lg040-transition-20261016` |
| Base | `fc9f74b` (LG-040 FINAL-CANDIDATE `5d32b04` recorded on main) |
| Owner writes | `frontend/src/app/shell.css` + `probes/lg040/TRANSITION-FIX-20261016/**` only |
| Product file changed | `frontend/src/app/shell.css` (CSS only — no TSX/logic/state change) |
| New probes executed this run | **NONE** (all evidence below was produced by the existing own probe run and retained raw; see §6) |

## 2. Root cause (verified from the recorded pre-fix failure, not re-invented)

The LG-040 residual defect was a **transient horizontal overflow during the
desktop→narrow transition** on the Files shell, recorded in the existing own
probe headers (`scripts/lg040-finalqa-resize-settle.mjs` L8,
`scripts/lg040-starvation-probe.mjs` L6):

> retest-driver FAIL (`.lg-chat-rail` present, `docScrollWidth 428`) at 390px.

Mechanism (`frontend/src/app/shell.css`), reconstructed from the recorded
geometry and the `dom-diagnosis.json` / `resize-settle.json` box dumps:

1. The inline rail wrapper `.lg-chat-rail` (and its sibling `.lg-context--inline`,
   plus `.lg-workspace > .lg-resizer`) carries an **inline JS `width`** driven by
   React shell state (`chatWidth`, default 360px). This wrapper is a flex item
   with `flex: 0 0 auto`.
2. On an initial 390px load, or during a 1440→390 resize, the browser applies the
   new viewport **before React commits `compact=true`**. For the intervening
   frames the wrappers keep their JS widths, so the flex row cannot shrink to the
   viewport: shell width becomes 56 rail + 240 context + 360 chat ≈ **428**
   (`docScrollWidth 428` vs vw 390).
3. The existing compact rule only collapsed `.lg-context--inline` and
   `.lg-chat--rail`, and it keyed on state that lags the media query, so the
   transient window was not covered.

## 3. Fix (minimal CSS, no product-state change, no fake clipping)

`frontend/src/app/shell.css` (18 insertions / 1 deletion):

- **Defensive flex bounds on the inline rail regions** so an inline JS `width`
  can never force the shell wider than its own container:
  - `.lg-chat-rail { min-width: 0; max-width: 100%; }`
  - `.lg-context--inline { max-width: 100%; }` (already had `min-width: 0`)
- **Collapse keyed on the viewport media query alone**, not on the lagging JS
  `compact` commit, in `@media (max-width: 1023px)`:
  ```css
  .lg-context--inline,
  .lg-chat--rail,
  .lg-chat-rail,
  .lg-workspace > .lg-resizer { display: none; }
  ```

This removes the transient overflow **without** overlay/clipping, **without**
changing desktop rendering, and **without** touching React state, logic, or the
DOM (the wrapper stays mounted; it is hidden by CSS).

**Explicitly NOT done:** no `overflow: hidden` on body/shell to mask overflow, no
clipping, no `position` hacks, no product/backend change, no driver or app edit.

## 4. Receipts — bundle hash, build, checks

Fresh build produced by the existing own build step; artifacts retained (dist is
gitignored, so the hashes below are the receipts):

| Artifact | Value |
|---|---|
| Source `frontend/src/app/shell.css` sha256 | `b2b3ca8b54b4d0953a771e70dad9cbeed0cb376b5795caf13628a7eaa83b2132` |
| Built CSS `frontend/dist/assets/index-DRJ4h6SM.css` sha256 | `a62d304df63662e4fae57a6d31c1ee5d65a83dd3c464c7aa36bcda4ae11769f0` |
| Built JS `frontend/dist/assets/index-D9QzHlXV.js` sha256 | `a7f185d41d22b8dfc8357e7385c3bebb89e4f8407fb4c08c8ada793b2ff5f5f5` |

Compiled-bundle confirmation (grep of the built CSS):

```
lg-chat-rail,.lg-workspace>.lg-resizer{display:none}
```

i.e. the new media-query collapse is present in the served bundle.

- `package.json` build script = `tsc --noEmit && vite build`; dist CSS mtime is
  `2026-10-16 18:17:03` (1s after the `shell.css` edit at `18:17:02`), so the
  build ran on the fixed source and the bundle contains the fix.
- **No standalone `tsc`/build log file was retained** in this probe; the build
  fact is evidenced by the compiled dist artifact + hash above, not by a captured
  exit-code log. Reported honestly as such.

## 5. Actual transition / no-overflow measurements (retained raw evidence)

All numbers below come from the **existing own probe run** (retained raw); **no
new probe/driver/browser was executed this session**.

### 5a. Original (pre-fix) recorded failure

Recorded in `scripts/lg040-finalqa-resize-settle.mjs` L8 and
`scripts/lg040-starvation-probe.mjs` L6:

```
retest-driver FAIL (.lg-chat-rail present, docScrollWidth 428) at 390px
```

The corresponding **pre-fix** geometry dump is retained at
`evidence/run/resize-settle.json` (initial-390 and post-resize sections show the
wrapper-present transient during the resize retest). Original failure is
preserved unchanged; it is **not** re-labeled as a pass.

### 5b. Fixed — transition driver (`evidence/run/transition-results-FIXED.json`)

`bound_ms = 2000`; verdict:

```
transition_no_overflow: resize_1440_to_390_files=true,
  nav_390_chat_to_files=true, roundtrip_390_1440_390_files=true
steady_no_overflow: steady_1440_chat=true, steady_1440_files=true,
  steady_390_files=true, steady_1024_files=true, steady_1440_files_again=true
all_transitions_clean=true, all_steady_clean=true
```

**Current real max overflow measurements** (per state; `maxOvershoot` = max
`docScrollWidth - innerWidth`, clipped at ≥0):

| State | nSamples | maxOvershoot | maxDoc | maxRailW | nOver2 |
|---|---|---|---|---|---|
| steady_1440_chat | 55 | **0** | 1440 | 0 | 0 |
| steady_1440_files | 55 | **0** | 1440 | 360 | 0 |
| steady_390_files | 44 | **0** | 390 | 0 | 0 |
| steady_1024_files | 44 | **0** | 1024 | 360 | 0 |
| steady_1440_files_again | 43 | **0** | 1440 | 360 | 0 |

### 5c. Fixed — sustained narrow starvation probe (`evidence/run/starvation-results.json`)

`bound_ms = 2000`; 2011 samples across the whole window:

```
summary: nSamples=2011, maxDoc=390, maxOvershoot=0, nOverflow=0,
         firstOverflow=null, lastOverflow=null
finalSample: {t:2000, vw:390, doc:390, body:390, overflow:false,
              mmCompact:true, rail:null, ctx:null, listW:310, detailW:310, entries:3}
verdict: no_overflow_throughout=true,
         rail_hidden_or_absent_at_390=true,
         materials_panels_usable=true
```

Zero overflow throughout; Materials list AND detail panels both usable at 390
(listW=detailW=310).

### 5d. Fixed — bounded settle driver (`evidence/run/lg040-settled-results.json`)

Original sample counts: driver produced **21 assertions** (19 PASS, **1 FAIL**,
1 informational). The **single remaining FAIL** is exactly:

| Assertion | Result | Detail |
|---|---|---|
| `narrow 390 Files Materials: responsive settle within bounded 2000ms (rail removed + detail rendered + stable geometry), no overflow at settle` | **FAIL** | `ready:false, readyAtMs:null, sawTransientOverflow:false, transientMaxScrollWidth:0` |

Its failure cause is a **DOM-presence heuristic**, not overflow: the driver's
predicate is `innerWidth==390 && !document.querySelector('.lg-chat-rail') &&
detailRendered && stableCount>=2` (`scripts/lg040-settled-driver.mjs` L16, L442,
L475, L492). The fixed build hides the rail via **CSS `display:none`**, so
`.lg-chat-rail` **remains in the DOM** and `!rail` is false. Every sample shows
`chatRailPresent:true, detailRendered:true, overflow:false`, `docScrollWidth 390`:

```
initial: {vw:390, doc:390, body:390, rail:false, detailRendered:false, overflow:false}
samples: {t:10..2000ms, docScrollWidth:390, chatRailPresent:true,
          detailRendered:true, overflow:false}
```

Expected semantics: `display:none` intentionally keeps the node mounted (so no
React DOM churn / state change and desktop reuse is preserved). The assertion
demands **absence from the DOM**, which is the "stale rail removed DOM
heuristic" flagged in the prior worker note — that is an assertion-authoring
mismatch, **not** a product regression. The *overflow* half of the same scenario
already PASSES in the sibling assertion
(`narrow 390 Files Materials: doc scrollWidth <= 390+2 at settle` → PASS,
`docScrollWidth:390, overflow:false`).

### 5e. Fixed — Files narrow matrix (`evidence/run/lg040-files-narrow-results.json`)

19/19 PASS, including 390/1024/1440 no-overflow (`scrollWidth == innerWidth`) and
panels nonzero; desktop 1440 retains the two-panel grid
(`gridTemplateColumns: 320px 360px`).

### 5f. DOM diagnosis (`evidence/run/dom-diagnosis.json`)

At 390/1024/1440 `overflow:false`; listed "offenders" are only
`lg-visually-hidden` 1px nodes and non-overflowing inline spans — no page-level
overflow. `.lg-app`/`.lg-workspace`/`.lg-main` all `scrollW == clientW == vw`.

## 6. What was / was not executed this session

- **Executed this session:** read-only inspection of already-retained own probe
  evidence, `shell.css` git diff, `package.json` scripts, built-dist grep/hashes,
  secret scan of the probe dir (no `sk-`/`api_key`/`Bearer`/`DEEPSEEK` matches).
- **NOT executed this session:** no browser, no driver, no app launch, no test,
  no new probe. The **prototype probe**
  `scripts/lg040-finalqa-width-driver.mjs` (newest `.mjs`, 18:17) is
  **retained raw but labeled UNEXECUTED** here; it produced no evidence file in
  `evidence/run/` and is not claimed as a result.
- All logs and raw evidence retained; no old raw failure modified.

## 7. Local non-browser checks

- Bundle contains the media-query collapse (grep above) → compile of the CSS
  change is confirmed **by artifact**.
- `tsc`/build exit-code log: not retained (see §4); stated as a limitation, not
  claimed as a PASS receipt.

## 8. Limitations / independent recheck needed

- This slice is **implementation**, **not independent QA**, and issues **no**
  whole-package LG-040 verdict.
- The single failing assertion is a **DOM-removal expectation** that conflicts
  with the CSS `display:none` design. Independent QA must decide the intended
  contract: (a) accept `display:none` (rail hidden, still mounted) as the settle
  semantics, or (b) file a separate product requirement to actually unmount the
  rail. This is explicitly **independent QA's next scope**, not fixed here.
- The `lg040-finalqa-width-driver.mjs` prototype is unexecuted and unproven.

## 9. Stop state

- No new writer/driver/browser child was started; none to stop. Pre-existing
  `:8123` service untouched; no broad `pkill`.
- Deny ledger: 0 attempts (no uploads, no OCR, no model calls).
- Snapshot/live data untouched (read-only); no product model or push.
- Only `frontend/src/app/shell.css` + `probes/lg040/TRANSITION-FIX-20261016/**`
  are in scope for commit.
