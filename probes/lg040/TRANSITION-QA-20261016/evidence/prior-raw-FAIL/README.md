# Preserved prior raw FAIL (read-only imports)

These files are **unmodified copies** of earlier probe raw outputs recording the
pre-fix transient narrow-390 Files/Materials overflow (`docScrollWidth 428` at
390px, `.lg-chat-rail` present, `right=428`). They are retained here so the old
raw FAIL is preserved and NOT re-labeled as a pass by this QA.

- `lg040-retest-results.pre-fix.json` — prior FINAL-QA retest raw; the failing
  assertion is `narrow 390 Files Materials: no horizontal overflow`
  (`docScrollWidth: 428`). Source: `probes/lg040/FINAL-QA-20261016/evidence/run/`.
- `overflow-diff.pre-fix.json`, `resize-settle.finalqa.pre-fix.json` — supporting
  pre-fix geometry dumps (same source).
- `lg040-settled-results.pre-fix.json` — pre-fix settled run (20/21; the single
  FAIL is the DOM-removal heuristic, overflow in the same scenario PASSES).
- `transition-results.pre-fix.json`, `starvation-results.pre-fix.json` — the
  TRANSITION-FIX worktree's own pre/post raw, retained verbatim.
- `*.pre-fix.mjs` — the drivers as they existed before this QA's corrected
  geometry predicate; retained to show the old heuristic.

No product file is modified by importing these records.
