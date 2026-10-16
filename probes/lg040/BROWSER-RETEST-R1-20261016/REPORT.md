---
title: "LG-040 BROWSER RETEST R1-20261016 — REPORT"
doc_type: report
category: qa
status: "final"
updated: "2026-10-16"
---

# LG-040 BROWSER RETEST R1 — REPORT

## 1. Identity

| Field | Value |
|---|---|
| Role | Fresh independent pi BROWSER recheck (not product implementer) |
| Task | LG-040 (whole-package verdict NOT owned by this slice) |
| Worktree | `/home/yhvh/code/lightgravity-bot-worktrees/lg040-browser-retest-r1-20261016` |
| Branch | `qa/lg040-browser-retest-r1-20261016` |
| HEAD | `75c6048` |
| Candidate | `75c6048` (R1 integration candidate) |
| Product fix | `266945c` (product tree byte-identical to candidate) |
| Owner writes | `probes/lg040/BROWSER-RETEST-R1-20261016/**` only |
| Persisted pending | `OWN` probes and `BROWSER-RETEST-R1-20261016` preserved (nothing wiped) |

## 2. Startup-failure diagnosis (the reason the prior retest aborted)

Prior wrapper exited 143 at ~284 s with **no** REPORT / **no** commit and the
message *"run dir gone … orchestrator getting killed early"*.

**Verified root cause (deterministic, from existing logs + scripts, no full
orchestration replay):**

`scripts/orchestrate.py` used `ROOT = Path(__file__).resolve().parents[5]`,
which resolves to `/home/yhvh/code/lightgravity-bot-worktrees` — the **parent of
the worktree**, one level too high. Hence:

```
VENV = ROOT/.venv/bin/python
     = /home/yhvh/code/lightgravity-bot-worktrees/.venv/bin/python   (does not exist)
```

The first `subprocess.Popen([VENV, deny_proxy.py, …])` therefore raised
`FileNotFoundError [Errno 2]` **immediately**, before any ready-file or process
log was written. From the wrapper's point of view the run dir stayed empty and
looked like an unexplained early kill. Evidence:

- `/tmp/orch-trace.log` stops at `imported orchestrate` (never reaches `main()` output).
- Direct reproduction: `Popen(['/home/yhvh/code/lightgravity-bot-worktrees/.venv/bin/python', …])`
  → `FileNotFoundError [Errno 2]`.
- `launch_app.py` correctly uses `parents[4]` (= worktree root); `run_retest.sh`
  correctly computes `ROOT=$PROBE/../../..`. Only `orchestrate.py` was off-by-one.
- Prior same-owner smoke with the **correct** root (`/tmp/lg040-retest-sm2/smoke.out`)
  proved the real app/browser path itself starts and serves search.

**NOT the cause** (checked, ruled out): missing parent dirs (`RUN.mkdir` runs
first), shell quoting, inherited ENV, timeout/wait-on-SSE, accidental self-pkill,
or any product startup/runtime defect. No product service was touched.

**Fix (owner scripts only):** `orchestrate.py` `parents[5]` → `parents[4]`, plus
a `heartbeat.log` that is written at each startup step so a hard parent kill
still leaves a persistent trace. No product file modified.

## 3. What this slice actually did

Recovered the prior working browser harness (real app + real `frontend/dist` +
real Firefox WebDriver BiDi) and ran it against a **snapshot copy** of the prior
real data (`evidence/snapshot/data`, byte-identical to `/tmp/lg040-browser-live`).
Backend inference was routed to a loopback **DENY proxy** (refuses before any
HTTP; ledger persisted). Command actually used:

```
RUN_DIR=/tmp/lg040-browser-retest-run3-<pid> \
  .venv/bin/python probes/lg040/BROWSER-RETEST-R1-20261016/scripts/orchestrate.py
```

Run evidence: `evidence/run-logs/` (heartbeat, orchestrator stdout, driver log,
deny-proxy log, ready files, ledger) and `evidence/run/` (screenshots, end-state,
results JSON).

## 4. Results — the two previously UNVERIFIED search cases

Both target cases **PASS** on the final candidate:

1. **UI search with a term from an ACTUAL trusted body.**
   `ui_term = correction` (present in the real `formal/FORMAL.md` body
   `… LG040-FORMAL-EN Correction marker 2026-10-16`). Real browser UI (Chat search
   input, `Search`) returned the expected hit:
   - `source_id = source_01M51N3TJT5QQGYGNB92V5C7MH` (clear_real.pdf)
   - `v1` version and `#89c6b42242d0` hash back-reference present
   - `basis: formal`, `verified`, `Open in Files` action present.
   → **PASS** (was UNVERIFIED #1). Screenshot `01-chat-search-desktop-1440.png`.

2. **`rebuild_if_missing=true` search with hash back-check.**
   `api_term = marker` → HTTP 200, 1 hit, `content_hash` present
   (`89c6b422…`), same source.
   → **PASS** (was UNVERIFIED #2).

Prior BROWSER findings preserved unchanged: the earlier *bad Invoice queries*
were **harness errors** (wrong term), **not** a product search defect. This run
confirms that with a correct trusted-body term the search works.

### Full driver result set: 18/19 PASS, 1 FAIL, 0 UNVERIFIED

Highlights (all real HTTP + real DOM, deny ledger **0 attempts**):

- real same-origin HTTP document (`http://127.0.0.1:<port>/`) — PASS
- snapshot exposes real prior-run sources (`clear_real.pdf`, `honest_table_grid_scale4.png`, `g.txt`) — PASS
- Chat search input available — PASS
- **UI search "correction" returns expected source + v + hash back-reference — PASS**
- **rebuild_if_missing "marker" returns hit with hash back-check — PASS**
- absent term is an honest empty result (index ok, 0 hits) — PASS
- Files Materials lists real snapshot sources — PASS
- Files preview opens real source with English actions — PASS
- non-revoked source download via UI returns real data — PASS
- revoke on OWN copy accepted — PASS
- revoked source status archived, reversible flag preserved — PASS
- **revoked preview (content) fails honestly: 404 `not_found` + `details.revoked` — PASS** (fix confirmed)
- **revoked download fails honestly: 404 `not_found` + `details.revoked` — PASS** (fix confirmed)
- other non-revoked source still functional after revoke — PASS
- UI does not render a fake revoked body (no leaked table content) — PASS
- default source scope preserved after actions — PASS
- narrow 390 Chat: no horizontal overflow — PASS
- **narrow 390 Files Materials: no horizontal overflow — FAIL** (see §6)
- single end-state captured after all actions — PASS

Single end-state (one capture, after all actions, on owner copy) recorded in
`evidence/run/end-state.json`: the local revoke left
`honest_table_grid_scale4.png` as `archived` (reversible flag `archived:false`
preserved), the other sources unchanged; UI entry list matches the API SoT.

Screenshots (desktop 1440 + 390 narrow): `evidence/run/01..05*.png`.

## 5. Zero-external-call enforcement (verified)

- Loopback DENY proxy ledger: `{"attempts": 0, "events": []}` — **zero** inference
  attempts reached any upstream; there is no upstream. No model / LAN / DeepSeek
  product calls. No new OCR; no reprocess invoked OCR; no new uploads.
- No proxy/ledger reset; `--ledger` written fresh in each new run dir only.
- No credentials copied into evidence.
- Own child processes started by the orchestrator were all stopped at exit
  (`stopped own children`, pid-scoped SIGTERM/SIGKILL). No leftover
  driver/proxy/app/firefox process; the pre-existing `:8123` service
  (pid 3320745/3320750, another worktree) was **not** touched.
- Original prior data `/tmp/lg040-browser-live/**` read-only / untouched.

## 6. Honest remaining limitation (out of slice scope)

- **FAIL: narrow 390 Files Materials has horizontal overflow** (driver measured
  `documentElement.scrollWidth > innerWidth + 2`). This is a real UI observation
  at 390 px, independent of the two search cases; likely the Files Materials
  two-column grid (`.lg-files-materials__body` `minmax(220px,320px) 1fr`) or the
  outer Files grid retaining a fixed minimum at 390 px. Reported as an
  **observation, not triaged as a product defect by this slice**; it is outside
  the two-search-case closure target.
- This slice does **not** issue a whole-package LG-040 verdict; it closes the
  BROWSER search cases and re-confirms the revoke fix.

## 7. Slice verdict

**PASS for the two targeted BROWSER search cases** (UI term + rebuild_if_missing
with hash back-check), plus **PASS re-confirmation of the revoke fail-closed fix**
on the final candidate, with **0 new external/model/OCR calls**. One honest
out-of-scope UI observation (narrow-390 Files overflow) is reported, not hidden.

Provenance / budget caveat preserved: original BROWSER run used real HTTP + 2
real OCR operations whose artifacts are the snapshotted data; **no new OCR quota
exists**. The whole-package per-run ledger reset caveat from the prior package is
retained and not restated as an exact global count.
