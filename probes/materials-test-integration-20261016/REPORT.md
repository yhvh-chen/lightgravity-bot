---
title: "Materials evidence test integration — REPORT (2026-10-16)"
doc_type: report
category: integration
status: "complete — 4 evidence branches merged --no-ff into main; PM docs/task bodies updated; no product code change"
updated: "2026-10-16"
---

# REPORT — materials-test-integration-20261016

## 0. One-line result

Four clean materials evidence branches (`materials-retry-r2`, `lg040-gate-prep`, `materials-quality-r3`,
`materials-r3-audit`) were independently audited and merged **`--no-ff`** into `main` with **no conflict
and no product/task/docs-tree change** (only `probes/**`). The R3-audit worktree, whose original
executor was stopped by harness token budget at ~106 s *after* writing its report but *before* commit,
was finalized by append-only errata and committed as the sixth owned file. PM then updated PROGRESS
top, BACKLOG top, and the evidence BODY of LG-035/037 (status/assignee/frontmatter unchanged).
**No product code changed; no broad tests re-run; no push/deploy/publish.**

## 1. Starting state (verified, read-only)

- Repo root `/home/yhvh/code/lightgravity-bot`, branch `main`, **clean**, HEAD **`db01cd6`**.
- All dirty/raw worktrees and branches **preserved**; no reset/clean; no duplicate cherry-pick.
- Four evidence branches, each 1 commit ahead of the **common base `db01cd6`**:

| branch | tip | files | product/task/docs diff vs db01cd6 |
|---|---|---|---|
| `test/materials-retry-20261016-r2` | `b3b7b4f` | 14 (probes/r2) | **empty** |
| `qa/lg040-gate-prep-20261016` | `0d4359b` | 4 (probes/lg040) | **empty** |
| `test/materials-quality-20261016-r3` | `9e8ec8c` | 17 (probes/r3) | **empty** |
| `qa/materials-r3-audit-20261016` | `db01cd6` + untracked | 5 owned → 6 after errata | **empty** |

Persistent worktree paths (checkpoints):
`/home/yhvh/code/lightgravity-bot-worktrees/{materials-retry-20261016-r2,materials-quality-20261016-r3,lg040-gate-prep-20261016,materials-r3-audit-20261016}`.

## 2. Audit-worktree finalization (explicit handover, no auto-replay)

- Original R3-audit executor wrote `STATUS.md`, `recompute_cer.py/.json`, `score_sep.py`, `REPORT.md`
  (complete), then was **stopped by harness token budget at ~106 s**; wrapper exit **143 (SIGTERM)**,
  **not a normal exit**; stop occurred **after** report flush, **before** `git add/commit`.
- Integration owner (explicit post-inspection handover): confirmed the **only** untracked paths are exactly
  the 5 owned files under `probes/materials-r3-audit-20261016/**`, **no other tracked dirty**, **no
  extraneous writes**; did **not** re-run tests/scoring/network/models; appended
  `ERRATA-DELIVERY.md` (**did not rewrite** original REPORT/raw evidence bytes), then committed **only
  these owned files**.
- Commit: **`c94b2e7`** (parent `db01cd6`), branch `qa/materials-r3-audit-20261016`, worktree clean after.
- **Errata substance**: original REPORT §10 prematurely said the package "is committed" and "budget
  respected" — corrected to "not yet committed; stopped at ~106 s by token budget; finalized later by
  integration owner". Cost: **0 inference/model calls is LAN-runtime only**; the audit ran on **pi
  DeepSeek** whose **token/cost totals are unknown, not zero**; shared pi QA totals likewise unknown.

## 3. Merge sequence (`--no-ff`, serial, conflict inspection)

| # | branch → merge commit | files | conflicts |
|---|---|---|---|
| 1 | `test/materials-retry-20261016-r2@b3b7b4f` → **`d2f733a`** | 14 | none (ort) |
| 2 | `qa/lg040-gate-prep-20261016@0d4359b` → **`ab78f37`** | 4 | none (ort) |
| 3 | `test/materials-quality-20261016-r3@9e8ec8c` → **`d8edb22`** | 17 | none (ort) |
| 4 | `qa/materials-r3-audit-20261016@c94b2e7` → **`dd1cc37`** | 6 | none (ort) |

- `git diff --stat db01cd6 HEAD -- backend/ frontend/ src/ tests/ docs/ pyproject.toml uv.lock Makefile backlog/` = **EMPTY**.
- All four branch tips are now **ancestors of `main`**; **both** the R3 report and its independent audit
  report are preserved (distinct paths, no overwrite). No duplicate content, no repeated cherry-pick.
- `main` after merges: **`dd1cc37`**, clean.

## 4. Merged evidence (relative links, now valid on `main`)

- **retry r2** — `probes/materials-retry-20261016-r2/REPORT.md`: Stage A **3/3 GET 200** (llama.cpp
  router, not Ollama); frozen budget **2/2 POST**: OCR real Z1 **CER 0.0423 ≤ 0.15 PASS**; embedding
  **768-dim finite nonzero L2=1.0**; **ASR 0 POST**.
- **LG-040 gate-prep** — `probes/lg040/GATE-PREP-20261016/REPORT.md`: independent offline audit; r2
  headline numbers **reproduced exactly**; 1 honest caveat (self-declared PLAN freeze time cannot be
  proven from git alone) + boundary clarifications. **QA preparation, not the LG-040 verdict.**
- **quality r3** — `probes/materials-quality-20261016-r3/REPORT.md`: **16/18 POST**; OCR **Z2 table page
  FAIL** (segment CER 0.328 > 0.25, structure collapsed) while Z1 printed page PASS (r2); vector
  **Recall@5 1.0 / MRR 1.0** vs lexical **0.7 / 0.8** on **7 docs / 7 queries (indicative only)**;
  negative-control hits reported; **ASR 0 POST; LG-041 locked**; no product/task change.
- **R3 independent audit** — `probes/materials-r3-audit-20261016/REPORT.md` + `ERRATA-DELIVERY.md`.

## 5. Corrections carried from the independent audit (crucial)

- **Z2 whole-page CER 0.2948 reproduces**; corrected **layout-agnostic segment CER ≈0.3172**, still
  **> 0.25** ⇒ table-class **FAIL robust** to scoring method. R3's own segment matcher is **flawed**
  (best single-line overlap; over-reports 0.3323/0.3281) — a **scoring bug**, not a verdict flip.
- **R3 `structure_pass` criterion is invented**, not protocol §4 (row count / column count / byte-exact
  cells); directionally the structure FAIL is supported.
- **Render resolution**: source PDF page is **300 DPI** (1701×2873 px); product `render(scale=2.0)` ⇒
  **~816×1379 px ≈ 144 DPI**; `408×689` is the page **point size, not the pixel grid**. Render scale is
  **not env-configurable** (additive config gap, "B3").
- **Negative queries returning top-5 is expected top-k NN candidate behaviour, NOT an ACL/contract
  failure** — no zero-hit requirement exists. Report the false hits, but do **not** close LG-037
  cross-modal quality and do **not** calibrate a threshold on the same 7 queries.
- **Image vector callability ≠ text↔image quality.** Prior **Z1 CER 0.0423 stands**.
- **Service** is really **`192.168.8.12:11434` llama.cpp router** (not Ollama), healthy **only at the
  recorded timestamps** — not a general future promise.
- **ASR (LG-041) stays locked** on LG-039's quality gate; the "audio support declared" fact is **not** a
  new user decision to unlock it.

## 6. PM documentation & task changes (this package)

- `PROGRESS.md`: new top section **"2026-10-16 资料质量证据集成收拢检查点"** with merge SHAs, evidence
  links, audit corrections, CLI-read status; the entire prior snapshot below it is marked **historical**
  and preserved byte-for-byte.
- `BACKLOG.md`: top batch-status refreshed with real quality evidence links + current remaining; CLI
  section corrected to the **`backlog/` root** convention (`.../lightgravity-bot/backlog`).
- `backlog/tasks/LG-035.md`, `backlog/tasks/LG-037.md`: **BODY-only** evidence/remainder appended before
  `## 参考`; **frontmatter status/assignee/title/depends_on unchanged**; no claim/done change.

## 7. Task status (CLI, backlog root)

```
node /home/yhvh/code/olav-tasks/dist/cli.js tasks validate /home/yhvh/code/lightgravity-bot/backlog --json
  -> {"ok":true,"tasks":41,"truncated":false,"diagnostics":[]}
node .../cli.js tasks digest /home/yhvh/code/lightgravity-bot/backlog --json
  -> complete=true, counts {todo:2, in-progress:2, done:37}, ready=[], diagnostics=[]
node .../cli.js tasks ready /home/yhvh/code/lightgravity-bot/backlog --json
  -> {"tasks":[], ...complete:true}
```

- LG-035 **in-progress**, LG-037 **in-progress**; LG-040/LG-041 **todo (not unlocked)**;
  LG-036/038 done pending LG-040; LG-031/032 done preserved.
- Contract **1.11.0**, SDK **0.1.22**, autonomous default **off** — unchanged.

## 8. Pending / not claimed

- **LG-040 not executed / not ready**: single-column printed page PASS, but **table page FAIL, mixed
  born-digital+scan class missing, cross-modal retrieval quality unverified**.
- **LG-041 blocked** on real Chinese ASR quality.
- Parallel `fix/materials-ocr-r4-20261016` is **INPROGRESS with no result** — not merged, not read as
  final, not awaited/polled.
- **No full QA pass claimed.** Product code / tests / docs07 / docs08 untouched.

## 9. Cost & boundaries

- **Product real generation this package: 0; external service calls this package: 0.** Model calls
  occurred only inside the already-merged evidence branches (counted there: r2 2 POST, r3 16 POST,
  plus GETs; audit 0 POST).
- pi DeepSeek dev cost for this integration = **unknown, not zero**; shared pi QA totals **unknown**.
- No push / deploy / publish; all original worktrees, private samples, experiments and failures preserved.

## 10. Evidence index (this package)

- This `REPORT.md`
- Merged: `probes/materials-retry-20261016-r2/**`, `probes/lg040/GATE-PREP-20261016/**`,
  `probes/materials-quality-20261016-r3/**`, `probes/materials-r3-audit-20261016/**`
- PM: `PROGRESS.md`, `BACKLOG.md`, `backlog/tasks/LG-035.md`, `backlog/tasks/LG-037.md`
- Base `db01cd6` → post-merge `dd1cc37`.
