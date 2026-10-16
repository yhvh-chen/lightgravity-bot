# STATUS — LG-047 R2 independent version QA (IN PROGRESS)

**Verdict (not final):** IN PROGRESS — SDK hard flow PARTIAL; R2 budget EXHAUSTED (8/8).

## Latest (SDK delivery, 2026-10-16 ~21:06)

- Real SDK delivery ATTEMPTED twice via the actual API on the fresh global
  native-alpha source `source_01M521GDB7S4XB86X3WKPD2B6W` (verified v1 /
  d34f0ca58b8d / readable 2223 chars; no seeding). See `REPORT-I-R2-20261016.md`
  §4 and raw in `raw/sdk-attempt2/`.
- **Positive:** real SDK worker wrote `orion-summary.md` with all six fixture
  facts correct from the selected brief; `deliver` subtask `passed`;
  `plan_source: rules`; program workspace + derived acceptance present.
- **Failure:** the program-added independent `verify` subtask hit `429 local auth
  proxy call budget exhausted`; Task → `failed`; acceptance never opened, so the
  real ModelReviewer / stop-gate / QA accept were NOT reached (UNVERIFIED).
- **Budget:** product ledger `generation.count.json = 8/8`; campaign mirror
  reconciled to **8/8, remaining 0**. No further real product call is possible.
- Attempt 1 was an INVALID QA-harness poll bug (2.28s premature teardown → WS
  1006), not a product defect; recorded in `evidence/sdk_attempt1_harness_bug.json`.
- Two important product findings recorded: (1) classifier false-positive on
  “approved” → DECISION; (2) a correct deliverable can still FAIL because the
  program-added `verify` turn exhausts the node/proxy call budget.

## Continuation (2026-10-16 20:35+)

- Prior I-worker (bounded `3850676` / `pi` `3850698`, spec
  `prototype-I-independent-r2-qa-20261016.txt`) STOPPED by exact TERM on PM
  handoff continuation (`prototype-I-r2-handoff-continue-20261016.txt`, this
  worker `3872734`/`3872736`). No product request was in flight at stop
  (generation counter still `1`); orphaned harness `with_server`/`launch_app`
  from its in-flight chatflow invocation reaped; data/ledger preserved; port
  `8123` (separate owner) untouched.
- **Harness defect root-caused (read-only triage `prototype-R2-harness-triage-REPORT.md`) and FIXED**
  in `scripts/with_server.py`: the entry-time `wait_health(0 if port==0)` poll
  always burned the full 90s because port 0 can never connect. Fix: resolve the
  REAL port from the ready file first, then health-check that real port with a
  small finite bound. Old script preserved as
  `scripts/with_server.py.historical-port0-bug`. Boot+health now ~1s (measured),
  no product calls. This is a QA-harness fix only; product untouched.

## Candidate binding (worktree)

| Ref | SHA |
|---|---|
| HEAD (this QA worktree) | `56a2dd9b9ded957df730dc67f5dbdb3342992523` |
| `HEAD^{tree}` | `9e441258a4e609b6f33bf1d8bd07ffb5e130cfa5` |
| `HEAD:backend` | `179167936b7704882826a84c67da1cbe6f693d18` |
| `HEAD:frontend` | `07618bb29bed372f47422b584070101196ce86bc` |
| Branch | `qa/proto-material-r2-20261016` |
| Shared main HEAD | `56a2dd9` (identical to this worktree) |
| Contract version (live) | `1.12.0` |
| Package version | `0.1.0` (package version, not the contract) |

`diff -rq` of main `backend/` vs this worktree `backend/` (excluding `__pycache__`)
is **empty** → the imported source matches this worktree and the frozen
candidate. `PYTHONPATH=backend` is required (the shared main venv `.pth` points
at the main repo); with `PYTHONPATH=<own>/backend`,
`lightgravity.__file__` resolves inside **this** worktree.

## Planned cases (R2)

1. Boot + readiness (real product lifespan, real executor, `reviewer: model`,
   persistent ledger) — **done, 0 model calls**.
2. First actual full flow: browser Chat upload plaintext alpha (human SAMPLE) via
   the UI handler → native auto-extract (no OCR) → receipt/GET body; source picker
   select alpha; ask English facts → real DeepSeek answer; decoy absent; UI
   `Sources` opens real Files material; reload keeps BOTH answer + Sources.
3. Delivery: global conversation + selected source → "Create a Markdown file …";
   program rule plan (derived acceptance + workspace); real SDK single worker
   file tool; real independent model reviewer; stop-gate; user accept.
4. Global + Task selected path; Task truncation with an uploaded long native TEXT
   sample; SourcePicker Task switch clears; legacy unselected message omits field.
5. Pre-forward negatives (0 additional model calls): stale 409, revoked 404,
   cross-Task 422, missing-ref 422, unreadable 503/404, >3 refs 422, oversize
   12000 trunc metadata.
6. Browser 390/1024/1440 geometry + backlinks + pending/errors; 1440→390 max
   overshoot 0, geometry readiness ≤2s.
7. F/G-specific regressions via meaningful local units (fake executor, clearly
   labelled NOT SDK proof).
8. End state: ledger counts, model IDs/usage, processes stopped/confirmed.

## Budget ledger (R2)

- Independent R2 campaign ledger (absolute, controlled, **never reset**):
  `probes/prototype-selected-material-20261016/I-R2-QA/campaign/`
  - manifest: `campaign/manifest.json` (cap **8**)
  - history: `campaign/history.jsonl` (append-only)
- Offline guard self-test (separate temp ledger, **not** product quota):
  `raw/guard_selftest.txt` → all checks pass.
- Product persistent generation ledger root: `campaign/product-data/generation/`
  (survives restart; pre-forward reserve; corrupt ⇒ deny).
- **R2 product requests used: 8 / 8** (remaining 0). Spends: #1 accidental N4
  direct answer; #2 real chatflow UI question; #3 attempt-1 aborted forward;
  #4–#8 SDK attempt-2 worker forwards (see `REPORT-I-R2-20261016.md` §4).

### Prior negative evidence (already captured, 0 additional calls)

- `evidence/negatives.json`: N1 >3 refs 422 `validation_failed` PASS; N2 stale
  version 409 `source_stale` PASS; N3 stale hash 409 PASS; N5 cross-Task 422
  `reference_invalid` PASS; N6 missing ref 422 PASS; N7 unreadable body 503
  `capability_unavailable` PASS. **N4 preserved as FAIL**: the revoke harness
  sent an extra forbidden `request_id` → 422, then an accidental genuine direct
  answer was produced (the 1 spent call). Not rerun (no lowering of semantics).
- `evidence/revoked.json`: corrected revoke action 200 `revoked:true` + selection
  404 `not_found` (recorded, **not** repeated as a model call).

### Known R1 (recorded separately, not counted as R2, not a PASS)

- E-QA R1 frozen candidate `57809d4` verdict **FAIL** (native UTF-8 upload no
  body; generic delivery plan invalid; assistant Sources history missing).
- R1 confirmed **1 real answer via AUXILIARY manual seed** (not the upload main
  path); an orphaned 2nd reservation has no surviving durable proof. The two R1
  ledgers do **not** reconcile to one exact number; the original 12-cap campaign
  is **not** claimed fully verified. R1 is never counted as a PASS and the R2
  counter (0) does **not** erase the old call.
