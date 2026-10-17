# LG-112 local delivery — LG-104 provider modal (contract 1.17.0)

Date: 2026-10-17 (local). Owner: independent pi QA R2 / local delivery.
QA verdict: **PASS** — see [`QA-R2.md`](./QA-R2.md).
Candidate source: `qa/provider-modal-r2-20261017`, HEAD
`e9ec008a7fd0a63c4b935423ce0d4b5f9483792c`.

## Identity

| Item | Value |
|---|---|
| QA candidate HEAD (incl. R2 evidence) | `e9ec008a7fd0a63c4b935423ce0d4b5f9483792c` |
| QA source candidate (before R2 evidence) | `c477bb1fc1e337f56b781ed357d6b211ab380889` |
| Product commit | `7fe66d8` (LG-115 native tree) |
| Product tree | `1ad85e93c3798d51be8350329103ef5d5dc41239` |
| Native race fix | `47686ae` — backend tree `caad0343476887b2c49b269ad2691df7dee2b7e0` |
| Frontend product tree | `de9c16f2ec4ffa3b8cd9d10c192376b4aa6f56ae` |
| Tests tree | `653d813b7a8109b36dc6d9d44e2c2d1570ac916d` |
| Root `main` before | `85d009dbc0eecfc398d7f43a086cf20e1d90b63f` |
| Root `main` product/QA merge | `e9ec008a7fd0a63c4b935423ce0d4b5f9483792c` (fast-forward, no merge commit) |

LG-115 and LG-116 are `done`; the merged product tree is the LG-115 native tree,
which already contains the LG-113/native `47686ae` reference-lock repair.
`git diff 44cfd8b 7fe66d8 -- backend frontend` is empty.

Root `main` was advanced **fast-forward** to the QA commit (linear history, no
merge commit). This `DELIVERY.md`/post-delivery logs are a following evidence-only
commit; they change no product file. Product/backend/frontend/tests trees on
`main` were re-verified equal to the QA worktree.

## Staged production build and atomic dist replace

Built with the existing root `frontend/node_modules` (`./node_modules/.bin/tsc
--noEmit && vite build --outDir dist.staging-<UTC> --emptyOutDir`), 109 modules:

| Asset | sha256 |
|---|---|
| `dist/index.html` | `1ebdf3ada3d8abc2302b918e6e9bec0813bdb6a8478e30e82baf22fef7e4f0a3` |
| `dist/assets/index-DfJ7UzJa.js` | `87ce0446c497b64938d452371514eea96f0539cc9a81a26fab08a48f4d378fd7` |
| `dist/assets/index-Tunx1fTy.css` | `4cc5d1da2a85f3147687f2780d30141a4626ed344ee6c1e07ec828c72918fbf4` |

The staged JS/CSS hashes are byte-identical to the QA-worktree build. Previous
live assets (`index-fFXL6xKA.js`, `index-DgA-HVl-.css`) were replaced by
`mv dist dist.prev-<UTC> && mv dist.staging-<UTC> dist` on the same filesystem;
the previous directory was removed after health verification. `8123` serves
these exact assets (JS/CSS 200 with matching hashes; the served `index.html`
contains the runtime token so its response hash differs from the file hash).

## Service change: only 8123

- Old `8123` PID `2516844` stopped with the supported CLI
  (`lightgravity stop --data-dir /tmp/lg002-data --timeout 30`); it required the
  documented SIGKILL escalation after the 30s SIGTERM wait. No broad kill.
- New `8123` PID `2707896`, same paths/host/ports/allow-hosts/`--no-executor`
  and team mode:
  `--data-dir /tmp/lg002-data --workspace-root /tmp/lg002-data/workspaces
  --secret-store /home/yhvh/code/lightgravity-bot/secrets --frontend-dist
  /home/yhvh/code/lightgravity-bot/frontend/dist --host 0.0.0.0 --port 8123
  --allow-host 192.168.8.50 --allow-host 192.168.8.105 --allow-host 0.0.0.0
  --no-executor`.
- Start used a sanitized environment: only `PATH`, `HOME`, `LANG`,
  `LIGHTGRAVITY_TEAM_MODE=1` (matching the previous non-secret team flag). No
  development credential/key env was copied. `LIGHTGRAVITY_MAX_GENERATION_CALLS`
  is **absent** → effective `limit=None` (unlimited, count-only); the generation
  directory/count was unchanged (no reset).
- `token_source` is `generated`; the restart generated a new runtime token, so a
  user may need to sign in again. No account content or real key was read.

## Preservation

- Protected services untouched and alive: `5173` PID `2332542` (Vite polling)
  and `18123` PID `1597462`.
- Root's 12 pre-existing PM-owned dirty docs/index-adjacent files were not
  stashed/reset/staged/overwritten; their sha256 hashes after merge equal the
  pre-delivery baseline.
- Runtime data inventory (paths + sizes) unchanged; `team/accounts.json` size
  `377` unchanged (content not read); generation ledger count unchanged
  (empty, no new history); secret-store path is the same (directory absent both
  before and after; no key content read).
- No merge of `ff885bf`/`eef3b3e`, no push, no release, no cloud resource.

## Runtime health after delivery

| Check | Result |
|---|---|
| Loopback `GET /api/v1/health` | 200 `status=ok`, `contract_version=1.17.0` |
| LAN `GET /api/v1/health` | 200 `status=ok`, `contract_version=1.17.0` |
| `GET /api/v1/version` | `1.17.0`, schema `lightgravity.bot/v1`, Python 3.12.13 |
| `GET /api/v1/settings/connections` (anonymous) | **401** |
| Served assets | `index-DfJ7UzJa.js` and `index-Tunx1fTy.css` 200, hashes match build |
| LAN real Chrome (`http://192.168.8.50:8123/`) | 200, title `LightGravity Bot`, Sign in landing + Username/Password visible, JS/CSS 200, no console errors; **no account login performed** |
| Protected `5173` / `18123` | both still running |

Evidence: `logs/delivery-baseline.txt`, `logs/delivery-after.txt`,
`logs/lan-chrome-check.json`, `screenshots/r2-8123-lan-login.png`,
`logs/artifacts-sha256-r2.txt`.

Real vendor/model calls during QA/delivery: **0**. No LiteRT/GPU/NPU hardware,
no real credential, no user data. Development token/cost: unknown.
