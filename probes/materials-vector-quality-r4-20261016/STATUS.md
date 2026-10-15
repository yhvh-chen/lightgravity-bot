---
title: "Materials Vector Quality R4 — STATUS"
doc_type: probe
category: probe
status: "complete — real cross-modal evidence obtained; partial (1 of 2 real audio candidates); LG-037 stays in-progress"
updated: "2026-10-16"
---

# STATUS — materials-vector-quality-r4-20261016

## Authority / isolation

- Single pi executor (no nested agents). Root PM only.
- New isolated worktree
  `/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-quality-r4-20261016`,
  branch `test/materials-vector-quality-r4-20261016`, base `main @ 71a2041` (verified clean).
- Exact write owner: `probes/materials-vector-quality-r4-20261016/**` in this worktree only.
  No product code / docs / backlog / contract edits. No reset / clean / push / deploy / publish.
- All prior worktrees, dirty state and raw evidence preserved.

## Task

LG-037 remaining **real cross-modal** (text→image, text→audio) retrieval quality evidence via the
**actual current product** vector embedder/index/service, with a **pre-registered** small real corpus
and **exact relevance labels frozen BEFORE any POST**.

## Network gate (frozen rule)

- Prior OCR owner wrapper `materials-ocr-r4-repair-20261016.txt` (`python3 .../lightgravity-pi-bounded.py
  .../materials-ocr-r4-repair-20261016.txt ...`). PID observed **2727394**.
- **DO NOT send ANY network while that wrapper PID still exists.** Do not kill it.
- Phase order: (A) OFFLINE freeze (PLAN + corpus + labels) → separate commit BEFORE any POST;
  (B) if wrapper gone, bounded network phase; (C) if still active when ready, save plan and PAUSE
  network until it exits, bounded by wall budget.

## Phase A progress (offline)

- [x] read AGENTS/agent/PROJECT/README/LG-037/LG-040; docs08 §4.3/§6.6 vector contract;
      docs09 §7 quality/vector boundaries.
- [x] read R3 REPORT + R3 audit REPORT (invented negative-control criterion; product has no
      threshold/abstention — negative false-hits must be **reported**, not treated as ACL failure).
- [x] OFFLINE FREEZE commit `ff6615e` (`PLAN.md` + `corpus.json`) BEFORE any POST.
- [x] prior OCR wrapper PID 2727394 observed; exited before network phase; not killed.
- [x] bounded network phase: GET 1/2, POST 16/16, retries 0, serial. Real
      text→image and text→audio cross-modal hits obtained (see REPORT).
- [x] REPORT.md written.
- [ ] final commit of owned evidence (in progress).

### Fixture inventory (pre-network, no downloads, no synthesis)
  - real image candidates (Apache-2.0, tesseract-ocr/test, human gold): `phototest.tif`,
    `phototest-rotated-L.png`, `8071_093.3B.tif`.
  - real image candidate (Public domain PD scan + Wikisource human transcription CC BY-SA 4.0):
    Z1 page-10 JPG (in preserved `lg035-truth-prep` worktree).
  - real audio candidate (CC BY-SA 3.0, real human English-Wikipedia "Chinese language" reading):
    `probes/lg039/evidence/real_voice_chinese_language-1.ogg`.
  - synthetic fixtures explicitly EXCLUDED (source-intake Pillow PNG / espeak-ng WAV).
- [ ] freeze PLAN + label manifest, commit (PHASE-A COMMIT).
- [ ] bounded network phase.
- [ ] REPORT.

## Honest limits (already known, not a result)

- Product `VectorSearchService.search()` embeds **only a text query** (`EmbedInput.text_input`).
  There is no image→image or audio→audio query API. Cross-modal evidence here is therefore
  **text-query → media-vector** ranking against the product's single ranked list.
- Only **1 real audio candidate** is available in the project; a second meaningful real audio
  candidate with trustworthy semantic truth is **absent**. If confirmed, that exact missing sample
  will be named instead of fabricating a label.
- Audio embedding ≠ ASR; this does not unlock LG-041.
- LG-040 is NOT claimed passed; QA only at an integrated named milestone.

## Case counter (final)

- network GET: **1 / 2**. inference POST: **16 / 16**. ASR POST: 0. OCR POST: 0.
  retries 0. concurrency 1.
- media uploaded: **2.68 MiB / 10 MiB**. real audio input: **30.0 s / 30 s**.
- result: vector text→image Recall@5 1.0 (rank 5, rank 1); text→audio Recall@5 1.0 (rank 1);
  MRR 0.7333; negative controls 5 false hits each (reported, not an ACL failure).
- **LG-037 stays in-progress; LG-040 not passed; LG-041 locked (audio embedding ≠ ASR).**
- Honest gap: only **1** real audio candidate exists; 2nd named as missing, not fabricated.
