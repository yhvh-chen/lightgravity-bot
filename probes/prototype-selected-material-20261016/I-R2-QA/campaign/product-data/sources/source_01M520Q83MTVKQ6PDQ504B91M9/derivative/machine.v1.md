---
schema: lightgravity.bot/v1
kind: source_derivative
record_type: machine_native_text
source_version: 1
extractor: native-utf8-text
extractor_model: none
extraction_status: succeeded
source_file: cross-task-negative.txt
total_pages: 1
---

# Machine native text — cross-task-negative.txt

> Machine transcription. Authoritative human edits live in `formal/FORMAL.md`; reprocessing replaces this file only.

## Page 1

<!-- original: cross-task-negative.txt page=1 input_sha256=fe08d3d0688bf0608efa43475affaed47eb27dd893c618428eae957db1bff7af -->

CROSS-TASK NEGATIVE FIXTURE MARKER (SAMPLE FICTION)
================================================================

NOTE: This is human-written SAMPLE data for the selected-material
prototype. It is NOT OCR output and NOT a measured model result.

Purpose
-------
This file exists ONLY to demonstrate the cross-Task isolation rule in
docs/10 §5 and docs/08 §6.6.1: a selected source bound to Task A must
NOT be carried into Task B. Per the frozen contract, selecting this
source while working in a DIFFERENT Task than the one it was uploaded
under must be rejected before model dispatch:

    error.code      = reference_invalid   (HTTP 422)
    error.details   = { not echoed path, no secret }
    model dispatch  = none (rejected first)

The rule is:  cross-Task ref (scope.task_ref != current Task and not
global) -> reference_invalid (422).

How QA uses this file (no new OCR)
----------------------------------
1. Upload this marker under Task A, wait for the real intake receipt.
2. Select it while Task A is the active Task -> this is legal (same Task).
3. Switch to Task B (or the singleton global conversation) -> the
   selection must be CLEARED because selection does not carry across
   Task boundaries (docs/10 §8).
4. Attempt to send a message in Task B that names Task A's source_id ->
   program rejects with reference_invalid (422) before any model call.

Unique sentinel tokens (so a leak is detectable)
------------------------------------------------
CROSS_TASK_SENTINEL = "XTM-ORION-71-FF41"
FIXTURE_KIND        = "cross-task-negative"
EXPECTED_CODE       = "reference_invalid"
EXPECTED_HTTP       = 422

If any answer produced while working in Task B quotes the sentinel
XTM-ORION-71-FF41 or any fact above, that is a CONTRACT VIOLATION and
must be recorded as such, not as a correct result.

END OF SAMPLE MARKER — cross-task-negative.txt
