---
title: "Materials Vector Quality R4 — Integration REPORT (LG-037 cross-modal evidence into main)"
doc_type: report
category: probe
status: "complete — evidence-only integration; source REPORT byte-identical; LG-037 stays in-progress"
updated: "2026-10-16"
---

# Integration REPORT — materials-vector-r4-integration-20261016

This package is the **integration owner's record** for merging the evidence branch
`test/materials-vector-quality-r4-20261016` into `main`. It is **not** a QA verdict and **not** a
quality re-run. It changes **no** product/test/contract/doc/backlog file and adds **no** new tests:
the merged branch is evidence-only and the product tree is byte-identical before and after.

## 1. Preconditions verified at start (read-only)

- Working tree `/home/yhvh/code/lightgravity-bot` on `main`, **clean**, HEAD **`572fd0f`**
  (expected). No stash, no unexpected dirty. This is the expected immediate parent.
- Candidate worktree `/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-quality-r4-20261016`
  on branch `test/materials-vector-quality-r4-20261016`, **clean**, tip **`335c87c`** (expected).
- Preserved prior integration: `575f84a` (Materials OCR R4) is an ancestor of `main`; its docs and
  the R4 PM records are intact (verified via `git cat-file -e 575f84a^{commit}`).
- **Prior bounded wrappers absent (excluding self).** Only one `lightgravity-pi-bounded.py` process
  was live at start: **PID 2744813 = this integration task's own wrapper**
  (`materials-vector-r4-integrate-20261016.txt`), which spawned this `pi` (PPID chain confirmed). No
  other wrapper or bounded worker was running. The previously-observed
  `materials-ocr-r4-repair-20261016` wrapper had already exited (its log ends with the R4 delivery
  text) and was **not** killed by this task. An unrelated long-lived `pi` (PID 2903293, since
  2026-09-04) exists but is not a bounded materials wrapper and was left untouched.
- No unexpected external `main` writer was observed: HEAD matched the expected `572fd0f` and `git
  status` was clean immediately before the single merge.

## 2. Branch content and product-tree delta (frozen facts)

`git diff --name-status 71a2041 test/materials-vector-quality-r4-20261016` — **9 files, all under
`probes/materials-vector-quality-r4-20261016/**`** (`.gitignore`, `PLAN.md`, `REPORT.md`,
`STATUS.md`, `corpus.json`, `evidence/crossmodal_harness.py`,
`evidence/crossmodal_results.json`, `evidence/vector_cache_summary.json`,
`http/health.raw.json`).

`git diff --stat 71a2041 test/... -- backend/ frontend/ src/ tests/ contracts/ docs/ pyproject.toml
uv.lock Makefile backlog/ README.md PROGRESS.md` → **empty (zero product-tree delta)**.

## 3. The single write action

- `git merge --no-ff test/materials-vector-quality-r4-20261016` → **`bd7fb18`**
  (parents `572fd0f` + `335c87c`), ort strategy, **no conflicts**, no repeated cherry-pick.
- Post-merge checks (read-only):
  - `git diff --stat 572fd0f bd7fb18 -- backend/ frontend/ src/ tests/ contracts/ docs/ pyproject.toml
    uv.lock Makefile backlog/ README.md PROGRESS.md` → **empty (product tree zero delta before AND
    after)**.
  - The merged source report is **byte-identical** to the branch original:
    `sha256 probes/materials-vector-quality-r4-20261016/REPORT.md =
    f4a5b9986a8677443a7e0880e3c2c327d94fe4a1461dc102153ad9afbcc3cbc7`.
  - `test/materials-vector-quality-r4-20261016` is now an ancestor of `main`
    (`git merge-base --is-ancestor ... HEAD` OK).
- All historical raw evidence, previous probes, worktrees and dirty state were preserved. No
  reset/clean/push/deploy/publish.

## 4. Contextual caveat on the source report's audio handling (NEW text here only)

The **source `REPORT.md` is preserved byte-for-byte and is not edited.** This integration report
records one contextual correction so the merged claim is read precisely, without altering the raw
bytes:

- The source report's phrase **"lossless container/PCM conversion"** is a **misnomer for the actual
  transform**. The real, recorded operation was `ffmpeg -ac 1 -ar 16000 -t 30 -c:a pcm_s16le`:
  it **resamples to 16000 Hz mono and clips to the first 30 seconds**. Resampling and time-clipping
  are **not** lossless.
- Therefore the embedded audio vector corresponds to the **30 s PCM excerpt**, while the **original
  Ogg/Vorbis asset is 143.58 s** (CC BY-SA 3.0, real human speech). The original Ogg exists and is
  the provenance anchor; it was **not** what was embedded.
- The audio truth is **topic-level labels only** ("Chinese language / 中文"). **No transcript was
  produced or used**: this is an **audio embedding**, **not ASR**. **LG-041 remains locked.**
- The raw-oqq attempt failing with `capability_unavailable` (with the exact upstream HTTP
  status/message uncaptured) is preserved as an honest limitation, as is the "no retry beyond the
  single planned attempt" budget statement.

## 5. Honest limitations carried forward (unchanged from source)

- Real counts (as reported by the source, **not** re-executed here): **16 embedding POST**
  (including **1 raw-ogg failure**), **1 GET**, **0 retries**, serial, concurrency 1.
- Positives **3**: text→image Recall@5 = 1.0 (**Q_IMG_ZH rank 5, Q_IMG_EN rank 1**), text→audio
  Recall@5 = 1.0 (**Q_AUD_ZH rank 1**); vector **MRR = 0.7333**, top-1 = 0.6667.
- **Lexical baseline returned 0 media hits** (media has no transcript) — that is **expected** and is
  **NOT** evidence that vectors are globally superior.
- Negative controls returned **5 ranked false hits each** (no threshold/abstention), reported as the
  expected top-k-NN behaviour, **not** an ACL/contract failure.
- **Only 1 real audio candidate** exists; the **second is named as missing**, not fabricated.
- **No second model was actually switched/tested**; the model-switch behaviour is an offline
  compatibility guard only.
- **Cost:** LAN/token cost **unknown** (endpoint exposes no price); **pi/DeepSeek execution cost is
  separate and unknown, not zero.** This integration stage made **0** product LAN calls (no
  GET/POST/ASR/embedding) and added **no** new tests.
- **No QA / full-quality claim.** LG-040 is **not** passed; LG-041 stays **locked**; LG-037 stays
  **in-progress** (partial cross-modal, not done); LG-035 table quality remains **FAIL**.

## 6. Status (unchanged by this integration)

Digest remains **37 done / 2 in-progress / 2 todo**; LG-035 `in-progress`, LG-037 `in-progress`,
LG-040/041 `todo` (locked). Contract `1.11.0`, SDK `0.1.22` unchanged. No task frontmatter,
status or assignee was modified by this package (LG-037 verification body appended only).

## 7. Evidence index

- Merged branch tip: `335c87c`; merge commit: **`bd7fb18`** (parents `572fd0f`, `335c87c`).
- Source (unmodified): `probes/materials-vector-quality-r4-20261016/REPORT.md`
  (sha256 `f4a5b998…`), plus its `PLAN.md`/`STATUS.md`/`corpus.json`/`evidence/**`/`http/**`.
- Preserved OCR R4 merge: `575f84a`.
