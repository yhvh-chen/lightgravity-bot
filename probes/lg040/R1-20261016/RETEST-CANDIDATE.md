---
title: "LG-040 R1-20261016 — RETEST-CANDIDATE (integration candidate after three-source serial merge)"
doc_type: report
category: qa
status: "candidate prepared — awaiting independent retest; NO whole-version PASS claimed"
updated: "2026-10-16"
---

# LG-040 R1-20261016 — RETEST CANDIDATE

## 0. Authority & nature

- Sole pi main **integration/setup executor** for the LG-040 verified-MAJOR repair
  candidate. Root PM scope only.
- This package: **merges the three existing owner branches** (API probes / BROWSER
  probes / revoke fix), records the candidate, and prepares **new independent
  retest worktrees**. It does **not** run QA, does **not** start retest workers
  (root dispatches them after this package exits), does **not** review code, does
  **not** write product code/tests beyond the actual merge, and does **not** make
  new network/model calls in this package.
- This document is **not a verdict**. No whole-version PASS/done is claimed.

## 1. New integration candidate

| Field | Value |
|---|---|
| Candidate commit | `92d6f5b` (merge of fix on top of the two probe merges) |
| Prior product base | `main` @ `dd4ca81` = product tree of `2f277fa` |
| Source base (docs/PM) | `2f277fa` |
| Candidate product tree hash (`backend frontend tests`) | `77685f0c64ba0403f6ba93823e7162d37be8e7bd` |
| Fix branch product tree hash | `77685f0c64ba0403f6ba93823e7162d37be8e7bd` |
| Byte-identity | `git diff 266945c HEAD -- backend frontend tests docs/08-interface-contract.md` = **empty** |

- The candidate product tree (`backend/ frontend/ tests/` + `docs/08`) is
  **byte-identical to the fix commit `266945c`**. The only product-facing delta
  vs. `2f277fa`/`dd4ca81` is the exact fix delta in §2.
- All three merges were **sequential `--no-ff`**; no conflict; no product edit by
  this package; raw QA reports preserved byte-identical to their source branches.

## 2. Exact fix delta vs. `2f277fa` / `dd4ca81`

Product paths (the complete product-side delta):

| Path | Change |
|---|---|
| `backend/lightgravity/sources/service.py` | +39 lines: `REVOKED_STATUS = "archived"` + `_ensure_available(record)` raising existing `NOT_FOUND` (404) with `details={source_id,status,revoked:true}`; gated **before any byte read** in `content_view`, `download_view`, `source_actions("reprocess")`, `edit_formal`. Does **not** gate the additive reversible `archived` boolean. |
| `tests/sources/test_lg040_revoke_availability.py` | new: 8 focused cases (fix owner). |
| `tests/sources/test_lg038_materials_flow.py` | updated 17 lines: revision test now asserts refusal + on-disk preservation (previously encoded buggy 200-on-revoked-download). |
| `docs/08-interface-contract.md` | +1 narrow implementation line under §6.6 (no contract version change). |

- `backend/lightgravity/api/sources.py` **unchanged** — the existing `AppError` →
  HTTP mapping already yields 404 for `not_found`.
- Expected independent-retest status: **HTTP 404 `not_found`**, `error.details.revoked = true`.
- Retention preserved: original/machine/formal bytes and history stay on disk;
  `revoke` idempotency, controlled writes/versioning/locks, archive/unarchive
  openable/searchable semantics all unchanged; revoked `status` not overwritten by
  reprocess/formal (no resurrection).

## 3. Merged source owners (all exited clean, verified)

| Merge (commit) | Source branch @commit | Content |
|---|---|---|
| `38138df` | `qa/lg040-api-r1-20261016` @ `ade76b9` | API probes: original **39/39 PASS** + ACL addendum **12 PASS / 2 FAIL** — confirmed revoke content/download leak (MAJOR). Probes only, product tree unchanged. |
| `05d9f7b` | `qa/lg040-browser-r1-20261016` @ `47ce895` | BROWSER probes (probes-only): real built-frontend UI, two real OCR POSTs (ledger 2/2, cap NON-RENEWED), **INCOMPLETE** — search cases UNVERIFIED due to wrong test term `Invoice`. Product tree unchanged. |
| `92d6f5b` | `fix/lg040-revoke-r1-20261016` @ `266945c` | Revoke fail-closed fix + focused tests + docs08 narrow + fix report; product base `dd4ca81`. |

- Pre-merge state: main `dd4ca81` clean, no stash, **no external main writer**
  (only this package's own wrapper `lg040-retest-candidate-20261016.txt` was live).
- All three source worktrees exited clean (`git status` empty per branch). Raw
  reports verified byte-identical after merge (§1).
- The QUALITY **METHOD-AUDIT** owner is still **ACTIVE** in its own isolated
  `lg040-quality-r1-20261016` worktree. This package did **not** read, merge, or
  touch that branch — it is out of scope here.

## 4. Retained prior plan/results (not rewritten)

- `probes/lg040/R1-20261016/PLAN.md` and `STATUS.md` are **preserved unchanged**
  (this file adds a candidate addendum; it does not rewrite them).
- Historical `GATE-PREP-20261016` remains historical, not the current contract.
- Total-package BROWSER OCR POST accounting: the per-run ledger resets each run;
  the whole-package total is **unknown** beyond the cited final live run (≥2
  confirmed, cap reached). Recorded honestly, not normalized to a clean count.

## 5. Remaining independent retest scope (root dispatches)

These new contexts are **independent of implementation** and reuse prior QA
artifact data (0 new model calls by design):

- **API retest** — worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg040-api-retest-r1-20261016`,
  branch `qa/lg040-api-retest-r1-20261016`, owner `probes/lg040/API-RETEST-R1-20261016/**`.
  API slice currently **confirmed MAJOR implemented, awaiting independent retest**.
- **BROWSER retest** — worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg040-browser-retest-r1-20261016`,
  branch `qa/lg040-browser-retest-r1-20261016`, owner `probes/lg040/BROWSER-RETEST-R1-20261016/**`.
  Needs **2 valid search cases** (corrected term) and a **single end-of-run state
  capture**; **0 new OCR calls** expected (cap already exhausted; 2/2 spent).
- **QUALITY** — still in its independent METHOD-AUDIT; **not** a whole-PASS.
- Budget: original phase budget unchanged (BROWSER ≤2 OCR already exhausted;
  QUALITY 2 OCR / 17-of-18 embeddings used, no extra allocation; ASR 0). Retests
  make **0** model calls by reusing prior artifact data.

## 6. Counters (this integration package)

- Network: **0** · POST: **0** · model calls: **0** · product inference: **0** ·
  retries: **0**.
- **Product edits by this package: 0** (the only product delta is the merged fix,
  byte-identical to `266945c`). No unsolicited fix. No merge conflict required
  resolution.
- New backlog Task/Run: **0** · SDK/default-model changes: **0**.
- pi cost: unknown, **not 0**.

## 7. Status

- Candidate **prepared, awaiting independent retest**. Not done, not blocked;
  no decision required here. LG-040 remains **in-progress**.
