# LG-035 R7 — OCR cohort (STATUS)

* Owner: pi execution owner (LG-035 R7 real table + mixed-page cohort). Primary-only PM.
* Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/materials-ocr-cohort-r7-20261016`
* Branch: `test/materials-ocr-cohort-r7-20261016`, base clean `main@2d76c83`.
* Writer scope: **`probes/materials-ocr-cohort-r7-20261016/**` ONLY**.
* Fixture source (read-only): `materials-fixtures-r7-20261016` @ `f21d6e3` (clean, exited).
* Date (UTC): 2026-10-16.

## Goal

RUN the predeclared 3-call cohort using the genuine NIST SI table + mixed PDF, with the
main **actual** `OpenAICompatOcrBackend` and **actual** `PdfiumRasterizer`. Freeze an
executable PLAN in a separate commit BEFORE any POST.

## Hard constraints (acknowledged)

* Exactly 3 planned OCR POST to `http://192.168.8.12:11434`, model `qwen3.8-27b`, concurrency 1,
  retry 0, 120 s/call, max output 4096, each input ≤ 2 MiB, total ≤ 6 MiB.
* audio 0 / embedding 0 / ASR 0 / worker 0. Optional ≤ 1 health GET (8 s).
* Reservation before forward; raw (redacted) before scoring. No timeout replay.
* No product/docs/backlog edits; no default prompt change (R5 candidate rejected).
* No nested agents; no secret output; no push/deploy/publish/reset/clean.
* Truth = original human-authored PDF text layer, frozen fixtures unchanged.

## Round log

* **R1 (offline prep)**: read AGENTS.md, agent.md, LG-035, fixture REPORT/COHORT-PLAN-R7/
  SOURCES/TRUTH-MANIFEST. Confirmed fixture hashes; confirmed the previous endpoint wrapper
  (`materials-endpoint-r7-20261016`, prompt basename `materials-endpoint-r7-20261016.txt`) has
  **exited** (no process, no open connection, REPORT committed). Created isolated worktree/branch.
* **R2 (offline verify)**: `preflight.py` re-renders MIX p1/p2 with the actual `PdfiumRasterizer`
  and confirms `p1 == NIST p16 scale2`, `p2 == clear_real.pdf p1 scale2`; all input/truth/gold
  hashes match the frozen manifest. `offline_check.py` parser/ledger check PASS.
* **R3 (freeze)**: PLAN + harness committed BEFORE any POST (this commit).

## Live run

* **R4 (live)**: 1 health GET 200. 3/3 planned POST ok (`finish_reason=stop`), serial, retry 0.
  reservation→raw persisted per call before scoring. Latency 86.05/38.37/7.15 s; tokens
  878/158, 2022/621, 276/113. No timeout, no replay, no adaptive extras.
* **R5 (score)**: table hardgate **FAIL** (machine rows 0 / cols 0, `parse_method=none`,
  cell CER 1.0 — model emitted a flat one-token-per-line list, no grid; no GT fill).
  MIX p1 **PASS** page CER 0.0295; MIX p2 **PASS** page CER 0.0000.
* **R6 (report)**: `REPORT.md` + errata note written; all changes inside this package only.

## Result

Table hardgate **FAIL**; mixed-page gates **PASS**. LG-035 stays **in-progress**, LG-040/041
not unlocked, R3/R4/R5 FAIL unchanged. No self-marked done.
