LG-239 run 2 preserved before continuation. This run MUST NOT be repeated.

Outcome: one real Google native ASR call was made and returned HTTP 200 in 6082 ms
for the frozen H1 audio (source_01M57APF4Q67D8XT97WE6JKRHA,
job_01M57APF57HXQWCBCX4EBFCEPG). The product call is valid.

The harness then failed because it accepted source text_status=ready while the
job was still at stage=indexing/status=running. The job check required a terminal
status immediately; this is a harness timing bug, not a product failure.

Per LG-239 rules, the audio was NOT resubmitted and no second Google request was
made. The continuation script resumes from the existing source/job and asserts
the final Google attempt count remains exactly 1.
