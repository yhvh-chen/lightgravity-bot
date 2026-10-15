---
title: "Materials Vector Quality R5 — STATUS"
doc_type: probe
category: probe
status: "complete — 2nd real audio added & reachable; FROZEN HARD GATE NOT MET (Q_IMG_ZH missed top-5); LG-037 stays in-progress"
updated: "2026-10-16"
---

# STATUS — materials-vector-r5-20261016

## Authority / isolation

- Single pi executor (no nested agents). Root PM only.
- Worktree `/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-r5-20261016`,
  branch `test/materials-vector-r5-20261016`, base `main @ a2dc40a` (verified clean).
- Exact write owner: `probes/materials-vector-r5-20261016/**` in this worktree only.
  Other owner: OCR r5 (isolated). **No product / docs / backlog / contract edits** (product-tree
  delta = 0). No reset / clean / push / deploy / publish. Prior worktrees/raw evidence preserved.

## Task

Close the honest remaining LG-037 cross-modal gap by adding a **second real human-audio candidate
with trustworthy topic truth**, then run a **frozen, pre-registered** cross-modal retrieval
measurement through the **real current product** vector path. Report actual LG-037 acceptance
coverage without inventing new mandatory requirements.

## Rounds

**R1** — setup worktree; read AGENTS/agent/PROJECT/LG-037/LG-040/R4 REPORT/R4 integration REPORT/
docs08 §4.3/§6.6 vector contract. OCR r5 wrapper alive confirmed.

**R2** — 2nd real audio acquired: Wikimedia Commons `File:Zh-地球.ogg` (real human pronunciation of
地球 / Earth), **CC BY-SA 4.0**, author CanonNi, own work 2024-10-07. Metadata via official Commons
API (`http/commons_zh_diqiu_metadata.raw.json`), ONE direct-upload GET (19,957 B ≤ 5 MiB), download
SHA1 `a8c67e62…` verified against API-declared SHA1. No TTS. PCM WAV prepped offline (16 kHz mono,
2.048 s; resample+clip, NOT lossless).

**R3** — FROZEN plan + corpus labels committed **before any inference POST** as `0ca7a42`.
PLAN `80d063da…`, corpus `9853f9ed…`. Planned POST ≤ 18.

**R4** — harness + offline dry-run (fake backend, no network) committed `967d97b`; bounded wait for
OCR r5 wrapper (PID 2784651) to exit; it exited on its own (~6 min, within its 600 s budget) — not
killed. Gate clear.

**R5** — real inference: HTTP 200 health (GET 1/2); **17/17 POST, retries 0, serial**; reservation
ledger persisted before each forward; results + REPORT written; targeted vector suite 38 passed/1
skipped; final commit of owned evidence.

## Frozen hard gate outcome (PLAN §3)

- audio_reachable = **true** (Q_AUD_LANG rank 1, Q_AUD_EARTH rank 1).
- image_reachable = **false** (Q_IMG_ZH absent from top-5; Q_IMG_EN rank 1).
- text_zh_reachable = **true** (rank 1).
- `all_hard_gates_met` = **false** ⇒ **no quality-pass claim**.

## Counters (final)

- GET **1 / 2**; inference POST **17 / 18** (6 text + 2 image + 2 audio + 7 queries); retries **0**;
  concurrency 1; ASR/OCR POST 0; media **1.30 MiB / 10 MiB**; audio 32.048 s total (each POST ≤ 30 s);
  public acquisition metadata GET ≤ 6 + 1 download 19,957 B.
- vector text→audio Recall@5 = 1.0 (both rank 1); text→image Q_IMG_EN rank 1 / Q_IMG_ZH miss;
  Chinese textual positive rank 1; vector MRR 0.8, top-1 0.8; lexical 0.2; negatives 5 false hits each.
- **LG-037 stays in-progress; LG-040 not passed; LG-041 locked (audio embedding ≠ ASR).**
- Cost/tokens **unknown** (endpoint has no price; pi/DeepSeek separate, unknown not 0).

## Honest gap / recommendation

- Closed: **"only 1 real audio candidate"** — a 2nd real human audio (地球/Earth) is now present and
  reachable.
- Open: **frozen image-reachability gate unmet** (Q_IMG_ZH). Quality truth therefore **not robust**
  (tiny corpus). **Do NOT mark LG-037 done / do NOT self-certify QA.** Next action (not done here):
  larger, more balanced cross-modal corpus + score-margin study; do not tune thresholds on these
  frozen queries. LG-037 `in-progress`; LG-040 `todo` (version QA); LG-041 locked.
