# LG-047 E-QA — STATUS (live checkpoints)

> Owner: independent QA executor (NOT any LG-043/044/045/046 author). Root PM
> only appends task status elsewhere; this file is my own QA evidence.

## Candidate / base

- QA worktree: `/home/yhvh/code/lightgravity-bot-worktrees/proto-material-qa-20261016`
- Branch: `qa/proto-material-20261016`
- Candidate HEAD at start: `0321bd16bb6ec16fd997c1fd66e52c578ef19314`
- **Product-candidate exact-D-hash read receipt**:
  - `HEAD:backend`  = `69d02e7af1554f89594290d739e457535c358345`
    = D report claim `6515e5c:backend` = `f7a32ac:backend` ✔ byte-identical
  - `HEAD:frontend` = `07618bb29bed372f47422b584070101196ce86bc`
    = D report claim `552d839:frontend` = `f7a32ac:frontend` ✔ byte-identical
- Contract version (from live `/api/v1/health`): `1.12.0`; SDK pinned `0.1.22`.

## Campaign budget

- Cap: **12 real product DeepSeek requests for the whole campaign**, retry 0,
  serial, per-request wall ≤90 s.
- Durable pre-forward hard cap: the product's **persistent generation ledger**
  (`LIGHTGRAVITY_MAX_GENERATION_CALLS=12`), rooted in the isolated data dir,
  reserved before forwarding in `LocalAuthProxy.begin_call()`, covering every
  worker/reviewer/dialogue SDK call, never reset, corruption = deny.
- Independent second ledger: `harness/campaign_guard.py` (own append-only
  JSONL) on the worker-forward path.
- **Product calls spent so far: 0 / 12.**

## Checkpoints

### CP1 — harness prep, product calls 0/12 (in progress)
- `harness/campaign_guard.py` written (durable JSONL ledger, pre-forward deny).
- `harness/launch_app.py` written; boots the **real** bootstrap runtime
  (`wire_real_executor=True`), isolated tmp data dir, 3 seeded DeepSeek
  connections, reviewer wired = `model`, `execution_ready=true`.
- `harness/api.py` written (real HTTP client).
- Frontend: fresh `npm run build` on candidate, EXIT 0 (103 modules).
- Offline proof the persistent ledger is pre-forward/durable: granted
  `[T,T,T,F]`, count survives restart, denies at cap (0 product calls).
