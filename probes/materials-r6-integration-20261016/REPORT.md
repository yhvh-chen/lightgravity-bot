---
title: "Materials R6 Integration — REPORT (OCR layout evidence-only + protocol memo + vector diagnosis/observe probes)"
doc_type: report
category: probe
status: "complete — evidence integrated; PM decisions recorded; no quality pass; LG-035/037 stay in-progress"
updated: "2026-10-16"
---

# REPORT — probes/materials-r6-integration-20261016

Sole pi technical integration executor (PM-owned file list); root PM only. This
package performed **no product code change** and made **0 network / model calls**
(no GET/POST/ASR/embedding; no new tests; no model probes). It only (a) imported
the OCR-layout r6 **evidence bytes** from branch A into main and (b) merged the
probes-only branches B/C/D with `--no-ff`, then wrote PM docs.

Base `main` at report time: **`7c27f18`** (verified clean, no uncommitted/staged
changes). Integration tip: see §5.

---

## 1. PM decisions (authoritative)

1. **OCR-layout r6 product prototype NOT merged.** `backend/lightgravity/sources/ocr/layout.py`
   + `__init__.py` exports + `tests/sources/ocr/test_layout.py` stay on branch A
   only: scale-sensitive (gutter model changes at scale 4.0), not integrated into
   the default pipeline, standalone API premature. Only the evidence package
   `probes/materials-ocr-layout-r6-20261016/**` was imported. Branch/worktree
   preserved. **No quality pass.**
2. **B/C/D merged `--no-ff`** (probes-only), sequential, no repeated cherry-pick,
   historical report bytes unchanged.
3. **Forward-looking protocol correction planning accepted.** The unsupported
   "15×3" Z2 assumption cannot be used as proven geometric truth. Historical
   R3/R4/R5 FAIL stays (segment CER > 0.25); the old protocol/JSON are untouched;
   no Z2 pass is declared. A genuine grid + human cell truth / new frozen cohort
   and table cell CER ≤ 0.25 / page CER ≤ 0.15 remain required. Uncertainty U1
   recorded honestly; no visual claim. Existing user authorisation for ordinary
   future work is not re-asked; no new permission block invented. No task status
   change; real table and mixed coverage remain UNMET.
4. **LG-037 stays `in-progress`**: no actual new ranking obtained on timeouts;
   the old R5 image hard gate FAIL is unchanged. Distinguish the old negative-NN
   expected no-abstention from ACL. No new threshold / media filters.

---

## 2. Check-in facts (real, read-only)

- **Own main writer only.** Before any write: `main@7c27f18` clean, no
  uncommitted/staged changes, no stash. All four source branches verified at
  their reported tips, each based on `7c27f18`:

  | Source | Branch | Tip |
  |---|---|---|
  | A | `dev/materials-ocr-layout-r6-20261016` | **`98df131`** |
  | B | `investigate/materials-vector-diagnosis-r6-20261016` | **`541e318`** |
  | C | `test/materials-vector-observe-r6-20261016` | **`612fcce`** |
  | D | `investigate/materials-ocr-protocol-r6-20261016` | **`503ab45`** |

- **Prior bounded wrappers absent (excluding own).** At start the only running
  `lightgravity-pi-bounded.py` (PID 2859379) is **this integration task's own
  wrapper** (`materials-r6-integrate-20261016.txt`; this shell's parent chain
  `… → 2859379 → 2859382 pi`). All prior materials wrappers (A/B/C/D owners) had
  already exited on their own; none were killed. No unrelated long-lived
  materials wrapper present. **No external `main` writer** (HEAD and `git status`
  matched expectation before merging).
- **Preserved:** all raw evidence, worktrees and branches untouched. No
  reset / clean / push / deploy / publish. No unexpected dirty state overwritten.

---

## 3. What each source delivered (as reported; not re-run)

### A — `dev/materials-ocr-layout-r6-20261016@98df131` (product prototype + reports)
- Commits: `d996bef` product prototype (LG-035 R6 Phase A), `98df131` probes
  evidence + truth-vs-layout audit + REPORT.
- Offline, program-side layout/column analyser (pixels + geometry only; stdlib
  PNG decode; deterministic integer coordinates; `input_sha256` provenance).
  **0 network / 0 OCR / 0 model calls / 0 GT used by the algorithm.**
- Real Z2 page 2 measured layout: content box x 109..704, y 319..1039; **no
  horizontal/vertical ruling**; text lines 12; region column counts `[3,2,1,2]`;
  model `multi_column_local`. Scale-4.0 render changes region/column counts
  (5–6 cols) ⇒ **pixel gutter model is scale-sensitive**, so layout counts are
  **2 vs 4 unstable** across scales. English controls stay `single_column`
  (no spurious tabular claim).
- **Wrapper exited 143 (`token_budget_exceeded`) AFTER evidence+report commit,
  not a normal success.** Verified clean / no active writer at integration time;
  not re-run.
- **Integration erratum (recorded here; source report bytes unchanged):** A's
  exit was budget-terminated after commit (not normal success); layout counts
  are scale-unstable (2 vs 4); this is **evidence of a structural signal only,
  not a quality pass**. The default OCR pipeline is unchanged; no integration
  was made in main. Replay of the prototype would require A's product candidate
  `d996bef`; main keeps the unchanged product (default pipeline).

### B — `investigate/materials-vector-diagnosis-r6-20261016@541e318` (probes-only)
- **Explicit non-replay recovery** after a first attempt exit 143
  (`token_budget_exceeded`) then close; report partial.
- Proven offline: query text identical R4→R5 (`老子 道德經 註解 學說`); media
  document vectors **bit-identical** across rounds (cos 1.0); same-title text
  documents changed (`fragment_hash` differs, cos 0.9959–0.9992). Ranking flip
  coincides with corpus change, not image/model change.
- **Source score = null / query vector absent ⇒ old query→doc margins UNKNOWN.**
  No quantitative margin recompute possible.
- `evidence/full_ranking_q_img_zh.py` is a **broken draft (syntax error; never
  ran; JSON never generated)** — retained as-is, **not usable, not corrected**
  (do not present unexecuted code as a result).
- **No proven product sorting defect.**

### C — `test/materials-vector-observe-r6-20261016@612fcce` (probes-only, verify full tip)
- New recorder supports **candidate scores** and **outer verified hit
  separately** (outer carries no score; product `VerifiedHit` has no
  `score`/`similarity`).
- Real 2-POST run: both queries **blocked** at 30 s (`index_unavailable`);
  health GET 1/1 → **HTTP 200**. **No actual query vectors / no real new
  ranking obtained.**
- Controlled-stub pipeline demonstrates `order_match=true` on a **WEAK PATH only**
  — proves the observability mechanism, **not quality**.
- **Honest defect kept:** the first live run's failure exception type was not
  captured; the recorder was then fixed but **NOT live-replayed** (no remaining
  budget; unknown side effects not replayed).

### D — `investigate/materials-ocr-protocol-r6-20261016@503ab45` (probes-only)
- **Explicit non-replay recovery** after a first attempt exit 143 then close.
- `DECISION.md` traces the **"15×3"** Z2 shape to **R4 scoring code
  `score_r4.py:227` (`e9fd5e5`)** then hardened in R5 PLAN (`7afe8eb`) — **not**
  in the original protocol (`SCORING-PROTOCOL.md` §4 is generic) nor the human
  truth (5 sections × 3 prefix-labelled dialect lines, a linear list).
- Product-rendered Z2 page-2 pixels: content box [109,319,704,1039], **0 rulings**,
  13 line bands, all starting at the left margin; supports a **suspected
  protocol-class defect**, **not absolute proof**.
- **Uncertainty U1: no human visual confirmation** (this session's model could
  not view images; verdict rests on pixel inference + the real model's own
  output, **not human eyes**). **No absolute visual claim.**

---

## 4. Integration actions (exact)

1. **A evidence import (PM-owned, probes-only, precise owned dir):**
   `git restore --source=dev/materials-ocr-layout-r6-20261016 -- probes/materials-ocr-layout-r6-20261016`
   (source dir verified **absent on main** first). Only the **12 owned evidence
   files** entered; all **byte-identical** to source (per-file `cmp`). **Not
   imported:** `sources/ocr/layout.py`, `sources/ocr/__init__.py`,
   `tests/sources/ocr/test_layout.py`. Owned commit **`72f7125`**.
2. **B merge `--no-ff`** → **`d189f43`** (9 probe files).
3. **C merge `--no-ff`** → **`7069ffe`** (14 probe files).
4. **D merge `--no-ff`** → **`6bef4ed`** (9 probe files).
5. PM docs updated (this package + PROGRESS top + README + PROJECT + LG-035/037
   bodies).

All merges were clean (`ort`), no repeated pick, no conflict.

---

## 5. Verification (real, post-integration)

- **Product tree delta = 0:** `git diff --stat 7c27f18 HEAD -- backend frontend
  tests docs contracts pyproject.toml uv.lock Makefile src` is **empty**.
- **All changed paths 7c27f18..HEAD are probes-only** (the four source probe
  dirs + this integration package); no product/doc-shared path appears.
- **Frozen report bytes byte-identical to source** (git blob equality):
  - A `probes/materials-ocr-layout-r6-20261016/REPORT.md` = `4923cb23…`
  - B `probes/materials-vector-diagnosis-r6-20261016/REPORT.md` = `4296c4fe…`
  - C `probes/materials-vector-observe-r6-20261016/REPORT.md` = `d22d35b6…`
  - D `probes/materials-ocr-protocol-r6-20261016/DECISION.md` = `1a60cb7f…`
- **Source branch tips unchanged** after integration: `98df131`, `541e318`,
  `612fcce`, `503ab45`.
- **No product bytes rewritten / no full-suite rerun / no probe re-run.**

---

## 6. Board CLI (EXACT dedicated command, absolute root)

```
node /home/yhvh/code/olav-tasks/dist/cli.js tasks validate /home/yhvh/code/lightgravity-bot/backlog --json
→ {"ok":true,"tasks":41,"truncated":false,"diagnostics":[]}   exit 0

node /home/yhvh/code/olav-tasks/dist/cli.js tasks digest   /home/yhvh/code/lightgravity-bot/backlog --json
→ complete:true; counts {todo:2, in-progress:2, done:37}; in_progress [LG-035, LG-037];
  ready:[]; diagnostics:[]                                     exit 0

node /home/yhvh/code/olav-tasks/dist/cli.js tasks ready    /home/yhvh/code/lightgravity-bot/backlog --json
→ {"tasks":[], ... diagnostics:[]}                             exit 0
```

Expected **41 tasks / 0 diagnostics / 37 done / 2 in-progress / 2 todo /
ready []** — **matches**. No diff; nothing faked.

---

## 7. Network / cost counters (this integration stage)

| counter | value |
|---|---|
| new LAN product calls | **0** (no GET; no real new POST beyond source history) |
| source history LAN (from reports, not re-run) | C: **2 POST + 1 GET**; B/D/A: **0**; A offline 0 |
| audio inputs | **0** (no ASR; LG-041 stays locked) |
| retries | **0** |
| product worker / OCR / embedding / ASR calls | **0** |
| push / deploy / publish / reset / clean | **none** |
| pi / DeepSeek execution cost | **unknown, not 0** |

Prior **R5 audio-overrun errata retained** (authorised total ≤ 30 s; actual
32.048 s ≈ 6.8% over; "per-POST ≤ 30 s" is not the original total bound) — no
re-run, no retroactive budget rewrite.

---

## 8. Status & remaining concrete blockers

- **LG-035 `in-progress`** (frontmatter unchanged; body appended). **Real table
  (grid + human cell truth, cell CER ≤ 0.25) and mixed born-digital+scanned
  coverage remain UNMET.** Forward-looking protocol reclassification is a
  proposal only; no retroactive pass; no threshold change (table cell CER 0.25,
  printed page CER 0.15 unchanged).
- **LG-037 `in-progress`** (frontmatter unchanged; body appended). **No actual
  new ranking obtained** (endpoint embeddings blocked at 30 s); the old **R5
  frozen image hard gate FAIL is unchanged**. Old negative-NN no-abstention is
  expected top-k NN, **not** an ACL/contract failure. **No new threshold / media
  filter.**
- **LG-040/LG-041 remain locked**; LG-040 is the named central version QA.
- Contract **`1.11.0`**, SDK **`google-antigravity==0.1.22`** unchanged.
- No task status / assignee change in this integration.

---

## 9. Next steps (concrete, not new gates)

- **OCR (LG-035):** build a genuine **grid + human cell-level truth** sample with
  cell CER, and freeze a corrected protocol / new cohort **before** any future
  model call. The Z2 page is better treated as a multi-column / side-by-side
  reading-order benchmark than a 15×3 grid.
- **Vector (LG-037):** a **larger, more balanced cross-modal corpus + score
  margin diagnosis**; **no auto-sampling and no threshold tuning on the frozen
  R5 queries**. A stable ≤ 30 s endpoint response is a precondition for a new
  (non-replay) real observation using the C harness.
