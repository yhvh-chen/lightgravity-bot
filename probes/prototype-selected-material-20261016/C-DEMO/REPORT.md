# C-DEMO REPORT (LG-045)

> Owner: `pi-proto-demo` (worktree `proto-material-demo-20261016`, branch
> `dev/proto-material-demo-20261016`). This REPORT was written early and updated
> before commit, per DISPATCH recovery discipline.

## Status

**Implementation complete — pending LG-047 version QA.** No product/model/network
call was made. Version acceptance is **not** claimed.

## Scope delivered

Owner files only (as assigned by DISPATCH for LG-045):

- `examples/selected-material-prototype/**`
  - `README.md` — labels the corpus as human-written **SAMPLE** data (not OCR,
    not measured model output) and explains the decoy + cross-Task marker.
  - `fixtures/alpha-brief.txt` — fictional project **ORION-71** (unique facts).
  - `fixtures/beta-brief.txt` — fictional project **LUMEN-33** (unique facts).
  - `fixtures/gamma-decoy.txt` — contradictory decoy, meant to stay unselected
    (different owner/date/budget for the same-sounding name).
  - `fixtures/cross-task-negative.txt` — cross-Task isolation negative marker
    with sentinel `XTM-ORION-71-FF41` and expected `reference_invalid` (422).
  - `expected-facts.json` — **fixture truth** (what the human wrote) + negative
    case error codes + truncation policy. Explicitly not measured model output.
  - `check_fixtures.py` — small offline checker (UTF-8 parse, referenced files
    exist, bounded word counts, guide links resolve). Not a product test.
- `docs/11-selected-material-demo.md` — English, repeatable prototype guide
  (Flow A upload→receipt→select→ask→open source; Flow B selected material→
  explicit file-delivery task→artifact→acceptance), negative cases with frozen
  error codes, scope isolation, LG-047 budget discipline.

**Not touched:** runtime product code, shared PM docs (`README.md`, `PROJECT.md`,
`BACKLOG.md`, `docs/08`), other owners' files, frontend/backend.

## Raw commands (real, with exit)

```text
$ python3 examples/selected-material-prototype/check_fixtures.py
...
ALL_OK: fixture checks passed
EXIT=0

$ python3 -c "import json;json.load(open('examples/selected-material-prototype/expected-facts.json'));print('json ok')"
json ok
EXIT=0

$ find examples docs/11-selected-material-demo.md -type f | sort
(8 files listed)
EXIT=0
```

No model, no network, no SDK, no service call was made at any point.

## Actual offline validation commands

| Command | Exit |
|---|---|
| `python3 examples/selected-material-prototype/check_fixtures.py` | 0 |
| `python3 -c "import json; json.load(open('examples/selected-material-prototype/expected-facts.json'))"` | 0 |

## Stop state

- No product call, no server started, no background process, no port bound.
- No spend incurred. Cost is **unknown, not 0** (no call attempted; spend is
  governed by LG-047).
- Only owned paths created; no worktree/source of other owners edited.

## Limits / remaining risk

- Expected facts are **fixture truth, not measured model output**; every model
  answer is **unverified until LG-047 QA**.
- The guide cites endpoints per the frozen docs/10 + docs/08 §6.6.1 contract.
  Until LG-043/LG-044 integrate (LG-046), a route may legitimately return
  `404`/`not_ready`; the guide states this and does not assume availability.
- No OCR is involved; fixtures are plain UTF-8 text.
- Truncation branch (explicit truncation vs reused limiter rejection) is left
  for the backend owner to declare; the guide documents both and asks QA to
  record which is live.
- Version QA is **not** passed; the gate remains open.
