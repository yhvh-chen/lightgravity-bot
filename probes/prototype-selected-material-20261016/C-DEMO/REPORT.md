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
  **Correction (see Addendum):** the message routes already exist in the base;
  only the additive optional `selected_sources` field is missing before
  LG-046. Pre-integration, sending that field is rejected as an unknown key
  (`422 validation_failed`), not `404`/`not_ready`.
- No OCR is involved; fixtures are plain UTF-8 text.
- Truncation branch (explicit truncation vs reused limiter rejection) is left
  for the backend owner to declare; the guide documents both and asks QA to
  record which is live.
- Version QA is **not** passed; the gate remains open.

---

## Addendum — wire-fact correction vs the ACTUAL registered DTO

Owner: `pi-proto-demo` (same worktree/branch). Follow-up to `6facb0b`.
Triggered by review request to verify the guide's examples against the
**actual registered request DTOs**, not just the documentation. This addendum
identifies a documentation defect in the original guide and corrects it in
`docs/11-selected-material-demo.md`. No runtime/product code was touched. No
product/model/network/browser/test/service call was made.

### Verified facts (actual DTOs, offline introspection)

Inspected in this worktree (base, LG-043/LG-044 not integrated):

- `backend/lightgravity/coordinator/api.py` → `AppendMessageRequest`
- `backend/lightgravity/api/conversations.py` → `GlobalMessageRequest`
- `backend/lightgravity/api/sources.py` → `SourceCreateRequest`

| DTO | `model_config` extra | Required fields |
|---|---|---|
| `AppendMessageRequest` (task messages) | `forbid` | `message_id`, `content` |
| `GlobalMessageRequest` (global messages) | `forbid` | `message_id`, `content` |
| `SourceCreateRequest` (`POST /sources`) | `forbid` | `request_id`, `filename` (then exactly one of `path`/`content_base64`) |

- `role` is **optional** on both message DTOs (default `"user"`).
- **`selected_sources` does not exist** on any DTO in this base
  (`grep -rn "selected_sources" backend/lightgravity` → no matches).
- Unknown field behavior, real validation (offline, no network):
  `AppendMessageRequest(message_id=..., content=..., selected_sources=[...])`
  → `ValidationError` `type=extra_forbidden`, `loc=('selected_sources',)`,
  `msg="Extra inputs are not permitted"` ⇒ FastAPI `422 validation_failed`.

### Documentation defects found and corrected in `docs/11-selected-material-demo.md`

1. **Wrong failure framing.** The guide said a route might return
   `404`/`not_ready` before integration. **Wrong.** The routes are already
   registered in the base; only the additive optional `selected_sources`
   field is unimplemented. There is **no** `not_ready` code. Pre-integration,
   a message carrying `selected_sources` is an **unknown field** rejected with
   `422 validation_failed` (`extra="forbid"`). Reworded in §0, §1 (new
   subsection), §5 pointer and §9. No invented `not_ready` error remains.
2. **Branch guidance.** The guide told readers to use the demo branch
   `dev/proto-material-demo-20261016`; that branch is **not** a working
   prototype base. Corrected to require integrated **`main` after LG-046**.
3. **Required fields made explicit.** A2 sample now includes `message_id`,
   `content` (required) and an explicit `role` (optional, default `user`) so
   the sample contains all actually-required wire fields. CLI start flags were
   re-checked against README and already matched (no change).

### What was already valid (no change needed)

- CLI start command in §1 matches the [README](../README.md) canonical
  `uv run lightgravity start --data-dir ... --workspace-root ... --secret-store
  ... --host 127.0.0.1 --port 8000` exactly.
- `POST /sources` example keys (`request_id`, `filename`, `content_base64`,
  `media_type`, `title`, `scope`) are all accepted by `SourceCreateRequest`;
  response fields `source.id` / `source.source_version` / `source.content_hash`
  / `job` / `receipts` all exist in `_result_view` / `_source_view`.
- Fixture corpus and `expected-facts.json` remain **fixture truth**, labelled
  human-written SAMPLE, **not OCR**, **not measured model output**. No fake
  outputs introduced.

### Real validation commands (offline; no network/product call)

```text
$ python3 examples/selected-material-prototype/check_fixtures.py
ALL_OK: fixture checks passed
EXIT=0

$ uv run python -c "<introspect DTO fields + extra + required>"
AppendMessageRequest extra= forbid   message_id/content required; role optional
GlobalMessageRequest extra= forbid   message_id/content required; role optional
SourceCreateRequest  extra= forbid   request_id/filename required
EXIT=0

$ uv run python -c "<feed selected_sources to AppendMessageRequest>"
REJECTED type= extra_forbidden loc= ('selected_sources',)
            msg= Extra inputs are not permitted
EXIT=0
```

No product model, network, browser, test or service call was made; the DTO
checks are pure in-process Python introspection/validation. Fixtures were not
altered.

### Stop state

- No product call, no server started, no port bound (note: `uv run` created
  the local `.venv` and built the package for import — no dependency install
  beyond the repo's own lock; no service launched).
- No spend incurred. Cost remains **unknown, not 0** (governed by LG-047).
- Change limited to C-owned paths: `docs/11-selected-material-demo.md` and this
  `C-DEMO/REPORT.md`. No runtime, shared PM doc, or other owner's file edited.

### Limits / remaining risk

- This addendum is **not** LG-047 version QA. Version acceptance is **not**
  claimed and the gate stays open.
- The DTO inspection is of the **base** in this worktree; once LG-043/LG-046
  integrate on `main`, `selected_sources` becomes a real additive field. The
  guide states both the integrated and pre-integration behaviors.
- Truncation branch and other live choices remain for the backend owner to
  declare; the guide still asks QA to record which branch is live.

---

## Correction receipt — CLOSE (owner `pi-proto-demo`, worktree `proto-material-demo-20261016`)

Follow-up to `6facb0b` (predecessor commit for this branch). Purpose: confirm
the already-written C-owned corrections are actually in place and record the
checks I really ran. This is a **correction receipt, not QA**: no version
acceptance is claimed and the LG-047 gate stays open.

### Actual checks performed (offline, read/git only)

```text
$ git status --porcelain
 M docs/11-selected-material-demo.md
 M probes/prototype-selected-material-20261016/C-DEMO/REPORT.md
   (only the two C-owned files; no untracked files; .venv is git-ignored)

$ git diff --name-only
docs/11-selected-material-demo.md
probes/prototype-selected-material-20261016/C-DEMO/REPORT.md

$ git log --oneline -1
6facb0b feat(lg045): English selected-material demo assets + repeatable prototype guide
branch: dev/proto-material-demo-20261016

$ grep -n "integrated\|main.*after LG-046\|dev/proto-material-demo" docs/11-selected-material-demo.md
21,62,65,70,91,231  -> branch/integration statement PRESENT
$ grep -n "validation_failed\|extra=\"forbid\"\|not_ready\|404" docs/11-selected-material-demo.md
  -> DTO-extra="forbid" / 422 validation_failed corrections PRESENT;
     all remaining `404` mentions are either negations of the old wrong
     claim or legitimate `not_found` (revoked / missing-body) rows.
```

### Confirmed

- **Guide DTO corrections applied** in `docs/11-selected-material-demo.md`:
  pre-integration `selected_sources` on `extra="forbid"` DTOs ⇒ `422
  validation_failed`, explicitly **not** `404`/`not_ready`; A2 sample includes
  required `message_id`/`content` plus optional `role`.
- **Branch/integration statement applied**: run on integrated **`main` after
  LG-046**; the demo branch `dev/proto-material-demo-20261016` is explicitly
  **not** a working prototype base.
- Existing raw report content above is **preserved unchanged**.

### Writer-stop / scope

- No other writer process active in this worktree at close time; predecessor
  stopped. Port `8123` belongs to `/home/yhvh/code/lightgravity-bot` and was
  **left untouched**. No child processes owned; no PM/backend/frontend/venv
  files touched. Offline fixture checker was already run in the addendum above
  and was **not** re-run (previous run covers it).

### Not claimed

- **No QA claim.** Version acceptance / LG-047 remains open. No new code
  investigation, no network, no browser, no model, no product test.
- Cost remains **unknown, not 0** (governed by LG-047).
