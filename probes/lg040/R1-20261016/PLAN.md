---
title: "LG-040 R1-20261016 — concentrated independent release QA PLAN (PM scope)"
doc_type: plan
category: qa
status: "plan frozen — planning/dispatch only; NO QA executed; NO pass/done claim"
updated: "2026-10-16"
---

# PLAN — LG-040 R1-20261016 (concentrated independent release QA)

## 0. Authority & nature

- **Root PM only.** This package (root `agent:pi-lg040`) performs **planning, atomic claim,
  worktree preparation and dispatch prep only**. It does **not** execute QA, does **not** start QA
  workers (root dispatches them later), does **not** write product code/tests, does **not** review
  code, does **not** run network/model calls.
- This is the **already-named** concentrated release QA for LG-040 (`backlog/tasks/LG-040.md`),
  scoped to the **English-primary market decision** (PROJECT.md 2026-10-16) plus the original
  LG-040 acceptance conditions.
- **This plan is not a verdict.** No QA has run. No pass/done is claimed. LG-041 stays locked; ASR
  unsupported in any language; not unblocked by "Chinese acceptable".
- **Current contract baseline (not the historical gate-prep):** contract **1.11.0**, SDK
  **0.1.22**, default OCR **table mode OFF** unless the browser/quality owner explicitly validates
  it as a named test option; table mode ON only for a named test and the ordinary prompt stays
  unchanged. **The old `GATE-PREP` Z2×3 / Chinese-gate contract is historical and NOT the current
  contract.**

## 1. Single integration candidate (what QA validates)

- Product candidate tree = **`main` @ `2f277fa`** (the claimed-plan commit's product subtree).
- All three QA owners must run from the **same claimed-plan commit** and must observe their
  product tree (`backend/`, `frontend/`, `tests/`) **byte-identical to `2f277fa`**. Any product
  delta during QA is a defect/stop, not a silent adaptation.
- QA owners **do not write product source**; they write only their owned probe subtree.

## 2. Requirement sources (English-primary)

| Source | Role |
|---|---|
| `backlog/tasks/LG-040.md` (§目标/范围/验收条件) | original acceptance conditions (authoritative) |
| `PROJECT.md` 2026-10-16 "英文为主" decision | English-primary scope; safety/permission/false-success block in any language; Chinese sample regression + disclosed limits; LG-041 locked |
| `agent.md` §1/§6/§8 | QA separation, worktrees, evidence honesty, no product writes by QA authors |
| `design.md` §8 | frontend acceptance: build/type-check ≠ interaction acceptance; empty/error states; narrow screen |
| `docs/08` (1.11.0), `docs/09` | source-intake/retrieval contracts; intake does **not** create Task/Run |

## 3. Global model budget (strict partitions, combined cap)

- Endpoint: **LAN target only** `http://192.168.8.12:11434`; existing models only
  **`qwen3.8-27b`** (OCR/generation) and **`embeddinggemma-2-Q8_0`** (embedding). No substitute
  provider/endpoint/model.
- **Product OCR POST ≤ 4 total:** BROWSER ≤ 2 (English image + real NIST table); QUALITY ≤ 2
  (mixed real PDF, two pages).
- **Product embedding POST ≤ 18 total, ALL QUALITY.** BROWSER embedding = 0. API inference = 0.
- **At most 22 product-inference POST total.**
- Per role: own **persistent pre-forward reservation + proxy hard caps**; assigned partitions are
  **non-borrowable / non-adaptable**. health/models GET ≤ 2 per BROWSER/QUALITY (total 4).
- All roles: **retries 0**, inference concurrency 1, **OCR 120 s / embed 90 s / connect 5 s**,
  max OCR output 4096 tokens, input ≤ 2 MiB/call; embedding media ≤ 10 MiB; **AUDIO TOTAL ≤ 15 s**
  (one existing real English speech clip ≤ 10 s + optional Earth ≤ 2.048 s).
- **No ASR / no worker / no DeepSeek product generation.** Backend private QA proxies/loggers
  must not print tokens. Data + server/browser processes must be **stopped and confirmed** at end;
  evidence preserved.

## 4. Inference serialization

- **QUALITY may do offline prep but NO LAN inference or health/models GET until the BROWSER wrapper
  `lg040-browser-r1-20261016.txt` has exited** (exact basename). BROWSER does not wait for QUALITY.
- API makes **zero** inference calls; it is not gated by the serialization rule for its own work.
- Every QA phase **freezes exact inputs/truth/call-count before POST**. Timeout stops the current
  network; **no replay of unknown side effects**; unexecuted work is reported honestly as unexecuted.

## 5. Coverage matrix (per-owner)

### 5.1 API owner — `probes/lg040/API-R1-20261016/**`
Real `FileStore` + real `create_app` + real HTTP for:
- scope/ACL, hit back-check; machine/formal/reprocess; archive vs revoke/delete.
- stale/corrupt/rebuild/incompatible-models; idempotent request conflicts; concurrent ingest;
  cancel/restart/recovery.
- **source intake does NOT create Task/Run.**
- Existing `tests/sources/**` reused + necessary **new independent cases/harness**; **zero live
  inference**; stubs **ONLY** for mechanical faults, explicitly labelled.

### 5.2 BROWSER owner — `probes/lg040/BROWSER-R1-20261016/**`
Real built frontend + real app/browser on **isolated data/ports** (not long-lived 8123).
- English desktop + narrow paths; Chat real file upload / inbox attribution / source preview /
  formal edit / search / download / reprocess / revoke / rebuild.
- UI state/text/error/authorization; actual **English image and table OCR in browser if possible**.
- **Inspect existing Firefox/browser helpers first** (`probes/browser-diagnostics/**`,
  `probes/lg038/browser_fixture_server.py`, `probes/lg027/scripts/*`). The old
  `ChromePage.navigate` HTTP issue is **not** a general HTTP block — use a `file://` shell +
  `fetch()` loopback (see `probes/browser-diagnostics/README.md`).
- Empty/error states, truthful "unavailable". **No fake browser, no artifact interception as real
  E2E.** No frontend code fixes in QA; defects → receipts.

### 5.3 QUALITY owner — `probes/lg040/QUALITY-R1-20261016/**`
- Real **English** corpus + labels **frozen in a SEPARATE own commit before POST**.
- English PDF mixed pages + vector image/audio/text ranking vs lexical; resources/caches/rebuild/
  limits.
- **No ASR**; **no Chinese gate block**; **broad statistical claims forbidden**.
- Existing R7 samples/raw may be read as reference
  (`probes/materials-fixtures-r7-20261016/**` NIST SP 811 + `truth/LG035-R7-T1.table.json`; other
  reused licensed fixtures), but the independent quality run uses its **own new explicit phase**.

## 6. Owners (new, fresh, independent)

| Role | Worktree | Branch | Owned writes |
|---|---|---|---|
| API QA | `/home/yhvh/code/lightgravity-bot-worktrees/lg040-api-r1-20261016` | `qa/lg040-api-r1-20261016` | `probes/lg040/API-R1-20261016/**` |
| BROWSER QA | `/home/yhvh/code/lightgravity-bot-worktrees/lg040-browser-r1-20261016` | `qa/lg040-browser-r1-20261016` | `probes/lg040/BROWSER-R1-20261016/**` |
| QUALITY QA | `/home/yhvh/code/lightgravity-bot-worktrees/lg040-quality-r1-20261016` | `qa/lg040-quality-r1-20261016` | `probes/lg040/QUALITY-R1-20261016/**` |

- **No implementation author is reused as a QA owner.** All QA owners are new.
- Native sub-agents forbidden; all QA via existing `pi` + env DeepSeek.
- **Root only prepares; root dispatches QA workers later. This package does not start them.**

## 7. Pass / fail rules (pre-registered)

- **Full PASS requires ALL original LG-040 English-primary requirements incl. browser and
  quality/safety.** Any important unfixed defect ⇒ **not pass**.
- English corpus cohort **pre-registered, not post-hoc tuned**. Chinese R5 FAIL preserved/disclosed
  but **not a standalone blocker** (unless safety/data-loss/permission/false-success).
- **LG-041 stays locked; ASR unsupported in any language.**
- Budget/port/artifact limitations or unverified cases must be stated **explicitly, not faked as
  pass**.
- QA authors **do not fix product**; root dispatches rework, then independent retest within the
  milestone.

## 8. Counters (this planning package)

- Network requests: **0** · POST: **0** · model calls: **0** · product inference: **0**.
- Product code/test writes: **0** · product tree must remain `2f277fa` (only PM/owned docs + the
  claim frontmatter change).
- QA executed: **none** (plan only). Cost: pi unknown, **not 0**.
