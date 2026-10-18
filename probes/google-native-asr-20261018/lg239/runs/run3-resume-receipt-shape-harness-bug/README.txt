LG-239 resume attempt 1 preserved before harness correction.

Outcome: no Google call was made in this continuation (still exactly 1 total).
Job terminal success, source text ready, then the harness assumed the receipt had
a top-level `text` field. This receipt v2 projection is `items[]`; the machine
branch is on the latest item carrying text.machine. Harness bug only.

Correction: select the latest receipt item with text.machine, then continue from
the existing source without any audio re-upload.
