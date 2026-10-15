---
title: "Materials Retry R2 — STATUS (Stage A first, before POST plans)"
doc_type: report
category: probe
status: "in-progress — Stage A GET-only reachability retry"
updated: "2026-10-16"
---

# STATUS — materials-retry-20261016-r2

## Authority & scope (this package only)

- User issued **one new bounded retest** of the candidate materials service. This is
  **not** an auto-replay of any prior write request.
- Owner: this pi executor performs **all** investigation/testing; main PM only manages.
- No nested agents. No push / deploy / publish. No provider switch.
- Authorized target: `http://192.168.8.12:11434`; dev host `192.168.8.50`.
  Prior **ARP failure is NOT** grounds to assert the host is powered off.
- Owner writes only under `probes/materials-retry-20261016-r2/**`.
- Persistence: worktree `materials-retry-20261016-r2`, branch
  `test/materials-retry-20261016-r2`, based on actual `main` @ `db01cd6` (clean).
- Task status is **not** changed by this package: LG-035/037 stay `in-progress`,
  LG-040/041 stay `todo`. GET reachability or a smoke call does **not** make
  35/37/40 done and does **not** unlock LG-041 ASR.

## Stage A budget (hard, this package)

- **Max 3 GET total**: `/health`, `/v1/models`, and `/props` **only if the first two succeed**.
- `connect-timeout 3s` / `total 8s` / `retries 0`, `--noproxy 192.168.8.12`, no `/api/ollama`.
- raw `private/` mode 700, files 600; scrub any key/token/credential value before digests.
- On failure: report HTTP / curl / errno / UTC honestly; **at most 1** target TCP
  `11434 connect 3s` + `ip route get`/`ip neigh` same-peer as corroboration
  only. No scanning other IPs/ports/SSH, no network changes. **No auto repeat GET.**

## First 5 rounds (plan before results)

| R | Action | Budget |
|---|---|---|
| R1 | Read-only rules + backlog digest (done) | local only |
| R2 | Create persistent worktree/branch + this STATUS (done) | local only |
| R3 | Stage A GET `/health`, `/v1/models` (+`/props` only if both OK) | ≤3 GET |
| R4 | If Stage A fails: 1×TCP-connect + `ip route get`/`ip neigh` corroboration, then REPORT | 1 TCP |
| R5 | If Stage A ready: freeze capability/model metadata into PLAN, then ≤2 POST smoke (OCR 1 + embedding 1) | ≤2 POST |

## Explicit counters at STATUS write time

- GET used: 0/3 · POST used: 0/2 · TCP probe used: 0/1 · retries: 0
