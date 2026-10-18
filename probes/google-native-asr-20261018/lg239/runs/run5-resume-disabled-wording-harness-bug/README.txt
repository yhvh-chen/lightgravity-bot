LG-239 resume attempt 3 preserved before harness correction.

Outcome: no Google call was made in this continuation (still exactly 1 total).
Disable succeeded and the API view is honest (enabled=false, available=false,
reason=disabled, configured=true, Google provider). The harness regex expected
"No transcription is generated"; the actual UI wording is "no transcript is
generated." Harness wording assertion bug only. No product defect.

Correction: accept the actual honest disabled wording, then rerun to finish the
retained-history check without any audio upload.
