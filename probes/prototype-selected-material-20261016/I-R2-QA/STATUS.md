# STATUS — LG-047 R2 independent version QA (IN PROGRESS)

**Verdict (not final):** IN PROGRESS — no PASS declared.

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
- **R2 product requests used: 0 / 8** (as of this checkpoint).

### Known R1 (recorded separately, not counted as R2, not a PASS)

- E-QA R1 frozen candidate `57809d4` verdict **FAIL** (native UTF-8 upload no
  body; generic delivery plan invalid; assistant Sources history missing).
- R1 confirmed **1 real answer via AUXILIARY manual seed** (not the upload main
  path); an orphaned 2nd reservation has no surviving durable proof. The two R1
  ledgers do **not** reconcile to one exact number; the original 12-cap campaign
  is **not** claimed fully verified. R1 is never counted as a PASS and the R2
  counter (0) does **not** erase the old call.
