---
title: "LG-040 BROWSER R1 — non-replay recovery REPORT"
doc_type: report
category: qa
updated: "2026-10-16"
---

# LG-040 BROWSER R1 — recovery REPORT

Non-replay recovery/finalization of the interrupted independent LG-040 browser QA.
This closure performed **0 new LAN calls** (no GET/POST/inference) and **no live
rerun**. All evidence below is read from already-persisted owner artifacts.

## 1. Identity / provenance

| Item | Value |
|---|---|
| Worktree | `/home/yhvh/code/lightgravity-bot-worktrees/lg040-browser-r1-20261016` |
| Branch | `qa/lg040-browser-r1-20261016` |
| HEAD | `edaad8e2b06c45423f2b5062f0780d62c00ada97` |
| Product subtree vs `2f277fa` | `git diff 2f277fa HEAD -- backend frontend tests` = **empty (unchanged)** |
| Working-tree product changes | **none** (`git status backend frontend tests` clean) |
| Original wrapper | `lightgravity-pi-bounded.py` invocation `u5o8l3a_` |
| Original limits | wall 720 s, model-idle 150 s, rounds 100, noncache 170000, auto-retries 0 |
| Original observed | elapsed **721 s**, rounds 98, noncache **140249**, tools 130 ok / 7 failed, `stop_reason=wall_deadline_exceeded`, `side_effects_unknown=true` |
| Original exit | **143** (SIGTERM at wall deadline), `auto_restart=false`, invocation_count 1 |

The exit-143 was the **harness wall clock (721 s > 720 s)** firing on the last
tool call — a `run_browser_e2e.sh --mode live` invocation. It was not a mid-driver
abort: the driver wrote all 31 cases (its final line is the last case
`narrow 390 no horizontal overflow`) at 17:08:48, and the ledger's final
`post_result` landed at 17:08:32. The interruption happened after the driver
process finished, during wrapper teardown. **No unknown side effect was replayed
in this closure.**

## 2. Budget: ACTUAL persistent reservation (not assumed 0)

The previous agent's last message claimed *"budget still 0 POST"* **before**
rerunning live. The persisted pre-forward reservation ledger proves both POSTs
were really consumed:

`/tmp/lg040-browser-live/ledger.json`:

```json
{"cap": 2, "get_cap": 2, "post_used": 2, "get_used": 0,
 "events": [
  {"kind":"post_reserved","path":"/v1/chat/completions","used":1},
  {"kind":"post_result","status":200,"result":"ok"},
  {"kind":"post_reserved","path":"/v1/chat/completions","used":2},
  {"kind":"post_result","status":200,"result":"ok"}]}
```

`logs/proxy-live.log` corroborates: `proxy: "POST /v1/chat/completions" 200 -`
twice. Both POSTs were forwarded to the LAN OCR model. A byte-exact copy of the
ledger (and the run's `proxy_ready.json`/`app_ready.json`, plus both
`ocr_evidence.jsonl` files) is preserved in `evidence/live/proxy-ledger.json`,
`evidence/live/proxy-ready.json`, `evidence/live/app-ready.json`,
`evidence/live/ocr-evidence-src1-clear_real.jsonl`,
`evidence/live/ocr-evidence-src2-nist-table.jsonl` — no secrets, only the
nonsecret budget/forward evidence.

| Budget item | Value |
|---|---|
| Hard cap (this owner, product OCR POST) | 2 |
| **Used (actual, ledger-confirmed)** | **2** (both HTTP 200) |
| Reserved-not-yet-used | 0 |
| Remaining under the frozen cap | **0** |
| Unknown | 0 — reservations are pre-forward, fsync'd, no gap between reserve and forward observed |
| Original cap status | **NON-RENEWED** (unchanged; this closure spent nothing) |

Fallback caveat: the ledger is per-run-dir and reset by `run_browser_e2e.sh`
(`rm -f "$RUN_DIR/ledger.json"`). The two POSTs above are from the **final live
run only**; earlier dry/test/run probes used dead/1-cap proxies. Total product
OCR POSTs across the whole package cannot be reconstructed beyond the cited
run, so the honest statement is: **at least 2 confirmed POSTs, cap reached**.

## 3. What the two POSTs actually produced (real OCR evidence)

Both calls are recorded in product-side `derivative/ocr_evidence.jsonl` with real
token/latency/prompt-kind facts:

| # | Input | `prompt_kind` | prompt_sha256 (prefix) | tokens (p/c) | latency | outcome |
|---|---|---|---|---|---|---|
| 1 | `clear_real.pdf` | `default` | `7cb03181…` | 276 / 114 | 7.197 s | **succeeded** |
| 2 | `honest_table_grid_scale4.png` | `table` | `4c7d8ec4…` | 954 / 1833 | 98.817 s | **succeeded** |

`prompt_sha256` values match `evidence/prompt-discipline.json`
(`ocr_prompt_sha=7cb03181…`, `ocr_table_prompt_sha=4c7d8ec4…`), and `prompt_kind`
for input 2 is `table` while input 1 is `default`. This **proves the OCR env
wiring was in fact correct on the live run**: the default prompt was used for the
non-table scan and the table prompt for the classified table, matching
`FROZEN-INPUTS.md`. Table classification for input 2:
`{"is_table":true,"reason":"dominant ruled multi-column region","column_count":3}`.

Real transcribed bodies were persisted (machine derivatives):

- `clear_real.pdf` → real scan text ("This is a lot of 12 point text… the quick
  brown dog jumped over the lazy fox…"), `extraction_status: succeeded`.
- `honest_table_grid_scale4.png` → real SI base unit table (length/meter/m,
  mass/kilogram/kg, … candela/cd), `extraction_status: succeeded`.

> **Harness note:** the **dry** run (`evidence/dry/ocr-content.json`) honestly
> shows `extractor_model: unavailable` / `extraction_status: failed` with
> "OCR backend unavailable: LIGHTGRAVITY_OCR_BASE_URL/LIGHTGRAVITY_OCR_MODEL are
> not set" — that is the **intended dry-mode** (dead `127.0.0.1:1`), a harness
> condition, **not** a product OCR defect. In the live run the same env produces
> successful real transcriptions, so the earlier failure was environment wiring,
> now fixed and re-proven live.

## 4. Frontend / browser provenance (exact label)

- **Real built frontend, same-origin HTTP document.** Served by the real product
  app created via `lightgravity.api.app:create_app`, which mounts the built
  `frontend/dist` (real Vite asset `assets/index-DXPFHVmX.js`, 283246 bytes;
  `index-B-eiJ8uk.css`, 34785 bytes — `frontend/dist` is gitignored but present
  and real, not a stub).
- Driver first case: `PASS real same-origin http document :: {"origin":
  "http://127.0.0.1:42219","url":"http://127.0.0.1:42219/"}`.
- This is **NOT** a `file://` fetch and **NOT** an interception/mock layer: the
  upload path used the real `<input type=file>`, and the app ran the real source
  intake → OCR → Files pipeline against an isolated data dir
  `/tmp/lg040-browser-live/data`.

## 5. Per-required-UI-case verdict (actual action / status / screenshot)

Source: `evidence/live/lg040-browser-results.json` (31 cases, 28 pass / 3 fail)
and `evidence/live/*.png`. Screenshots preserved, unmodified:

| # | UI case | Real action | Status | Screenshot | Verdict |
|---|---|---|---|---|---|
| 1 | Chat desktop load (1440) | open `http://127.0.0.1:42219/`, render Chat | PASS | `evidence/live/01-chat-desktop-1440.png` | **PASS** |
| 2 | Chat material intake / upload area | real `<input type=file>` present, English copy | PASS | `evidence/live/02-chat-uploads-desktop-1440.png` | **PASS** |
| 3 | Files → Materials desktop (1440) | Files view, Materials tab, preview | PASS | `evidence/live/03-files-materials-desktop-1440.png` | **PASS** |
| 4 | Chat narrow (390) no overflow | viewport 390, no horizontal overflow | PASS | `evidence/live/04-chat-narrow-390.png` | **PASS** |
| 5 | Files Materials narrow (390) | Materials list at 390 | PASS | `evidence/live/05-files-materials-narrow-390.png` | **PASS** |
| 5b | Files narrow (390) | Files at 390 | PASS | `evidence/live/05-files-narrow-390.png` | **PASS** |

Full driver case list (all with recorded detail in the results JSON): same-origin
document, fixture byte route, Chat English intake, Chat empty state, "no delivery
Task created", API sources empty, upload1 (real PDF), upload1 receipt (real source
id, no Task/Run), upload2 (real PNG), upload2 receipt, inbox attribution (no
task_ref), Files Materials lists 2 sources, Files source preview + English
actions, OCR reprocess #1, source1 real status, OCR #1 trusted body, Files source
2, OCR reprocess #2, Chat search available, search hit, formal editor reachable,
formal correction saved (rev 3), download original, download formal, search
rebuild, revoke via API, revoked=archived honest, unauthorized Settings write
honest failure, loopback upload not gated (documented policy), narrow 390.

**Kept-case PASS examples (real, not cosmetic):** upload receipts show real
ULID source ids (`source_01M51N3TJT5QQGYGNB92V5C7MH`, `source_01M51N3TRHB3Y5KQ5SAPSBEFRB`)
with no Task/Run; formal save returned "Saved formal version (revision 3)";
downloads returned real filenames; revoke → status `archived` with vector
disabled; unauthorized sensitive Settings write surfaced
`missing or invalid local access token (unauthorized)`.

## 6. Important defects / failures (honest, with classification)

1. **`search returns a real source hit with v+hash` — FAIL → UNVERIFIED (test design).**
   The driver searched the literal term **`Invoice`**, which appears in **neither**
   OCR'd document (a generic scan and a SI-units table). A "no matching material"
   result is therefore the **expected** product behavior for that query, not a
   product bug. The index did contain a doc, but with `basis: formal` (the
   human-edited FORMAL.md body), and the formal body was the correction marker
   from the same run. **The search path is UNVERIFIED** for a matching term; it is
   not proven broken.
   Minimal re-check for the later retest: perform a UI search for a term actually
   present in a trusted body (e.g. `meter` or `brown`) at a source that is
   `extracted`/`indexed`, and assert the hit shows `v<N>` + `#<hash>`.

2. **`search rebuild_if_missing returns hit with hash back-check` — FAIL → UNVERIFIED (same cause).**
   `GET /api/v1/search?q=Invoice&include_global=true&rebuild_if_missing=true&limit=10`
   returned `200` with `hits: 0`. Same wrong-term cause as (1). Note the query was
   a **new LAN GET** issued by the driver; it is not a product defect by itself.

3. **Live product-state vs on-disk state divergence — informational.**
   `evidence/live/product-state.json` (captured during the run) shows source1
   `status: failed` while the final on-disk `SOURCE.md` shows `status: extracted`
   with two real derivatives and `lexical: indexed`. Similarly `archived: false`
   is listed with `status: archived` for source2. This is a **snapshot-timing**
   artifact of capturing state mid-pipeline, not a verified product bug. It should
   be re-captured once, at the end of a clean run, before any acceptance claim.

**No product source defect was verified in this closure.** No fix was applied
(product unchanged). No "whole-version PASS" is claimed.

## 7. Harness / evidence limits (could not be resolved read-only)

- The two search cases above are **UNVERIFIED**, not FAIL-as-product, because the
  driver query term was wrong. A corrected-term search is required for a verdict.
- The `dry` 3rd "failure" (`false_success: true`, i.e. UI toast claimed reprocess
  started while the dead-backend derivative says failed) is **dry-mode-only**; in
  live mode OCR actually succeeded, so it does not indicate a live product defect.
  It is worth a targeted check in the retest (does the UI surface a machine-
  derivative failure while showing a "Reprocess started" toast?).
- Ledger is per-run-dir and reset each run; whole-package POST total is only
  bounded as "≥2, cap reached".
- The run was ended by harness wall deadline, so any behavior *after* the driver's
  last case (e.g. the app's own async completion, final state persistence) was not
  observed. The last ledger `post_result` (17:08:32) precedes driver end
  (17:08:48), so no OCR POST was dropped mid-flight, but post-driver app
  finalization is unobserved.
- Tokens ledger / PI cost: **not printed here** (per instruction). PI cost is
  **unknown, not 0**.

## 8. Process / port cleanup (recorded, checked — not claimed blindly)

- `ss -ltnp` / `lsof` show **no listener** for this package: no proxy port, no app
  port (e.g. 42219/38621), no Firefox/geckodriver/BiDi port in 38k–45k.
- `pgrep -f lg040-browser-r1-20261016` shows only the **current closure wrapper**
  (`lg040-browser-r1-close-20261016`, PID 3467551) — no leftover proxy/app/browser
  from the interrupted run, so **nothing needed stopping**.
- `8123` (LG-040 dev/API) and the in-flight **QUALITY** run (ports 18140/18141,
  `/tmp/lg040-quality-r1-20261016`) were **left untouched**, as required.
- No `kill` was issued for any product/other-package process. `run_browser_e2e.sh`
  has an `EXIT/INT/TERM` trap that kills only its own `APP_PID`/`PROXY_PID`; the
  interrupted SIGTERM would have triggered that trap for its own children.

## 9. Exact next step (for the root-coordinated retest AFTER QUALITY)

Do **not** rerun live now and do **not** renew the browser OCR budget. After the
QUALITY run finishes and no concurrent LAN is active, the root-coordinated final
candidate retest should:

1. Fix the driver search term to a string present in a trusted body and re-run the
   UI search + `rebuild_if_missing` cases (currently UNVERIFIED).
2. Re-capture `product-state.json` **once at the end** of a clean run to remove the
   snapshot-timing divergence in §6.3.
3. Obtain an explicit budget decision for any further live OCR POST (cap currently
   reached at 2, NON-RENEWED).
4. Re-verify product subtree stays at `2f277fa` and screenshots stay unmodified.
