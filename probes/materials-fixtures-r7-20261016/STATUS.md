# LG-035 R7 — materials fixtures (STATUS)

* Owner: pi execution owner (LG-035 R7 package). Primary-only PM.
* Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/materials-fixtures-r7-20261016`
* Branch: `test/materials-fixtures-r7-20261016`
* Base: clean `main@2d76c83` (verified `git status --porcelain` empty before `git worktree add`).
* Writer scope: **`probes/materials-fixtures-r7-20261016/**` ONLY**. No product/docs/backlog edits.
* Date (UTC): 2026-10-16.

## Goal (this package)

Deliver **offline/acquisition-only** fixtures so the *frozen* LG-035 acceptance classes become
testable, without inventing synthetic data or machine-as-truth:

1. **One genuine published grid TABLE**: a small, simple table region from an **official,
   public-domain / permissively licensed native born-digital PDF** (US federal / official source).
   The PDF's **original text layer** (human-authored, not OCR) supplies the **human cell truth**
   BEFORE any model call. Product rasterizer (pypdfium2) renders the region ⇒ legitimate
   real-document OCR input, not a synthetic drawn grid.
2. **A mixed born-digital + real-scan PDF fixture**: composite of the selected born-digital table
   PAGE (native text layer present) + an existing real-scan PAGE (no text layer), combined with
   pypdfium2. Composite is a **test fixture**, not a claim of an unmodified historical document.

## Hard constraints (acknowledged)

* Offline/acquisition only: model/OCR/embedding/ASR HTTP = **0** in this package.
* No product LAN requests. No push/deploy/publish/reset/clean. No nested agents. No secrets output.
* Acquisition budget ≤14 read-only GET (primary official only) / ≤3 downloads ≤10 MiB each,
  ≤15 MiB total; timeout 15 s each; no crawl/remote install.
* Truth from original text/metadata/manual transcription with provenance, **before** model calls.
* Thresholds unchanged: table **cell CER ≤ 0.25** with actual row/column structure; printed page
  CER ≤ 0.15; numeric/ID tokens byte-exact after NFKC; machine-vs-formal protection unchanged.
* Freeze COHORT-PLAN + truth/cell schema + input hashes + thresholds before any FUTURE model
  calls. Actual calls NOT authorized here.

## Round log

* **R1**: base verified clean; isolated worktree/branch created; mandatory docs read
  (AGENTS.md, agent.md, LG-035, PROJECT.md, README checkpoint, R6 DECISION.md,
  SCORING-PROTOCOL.md, truth_manifest.json). STATUS written. Tooling probed (pypdfium2 in
  `.venv`, pdftotext/pdfinfo/pdfimages system). Next: select official PD native PDF with a small
  simple grid table; verify origin/license/bytes; extract region via product PDF-coordinate bounds
  + hash map; derive cell truth from native text layer with provenance.
* **R2–R3**: acquired NIST SP 811 (2008) from `nvlpubs.nist.gov` (public domain, 1.93 MiB);
  located **Table 1. SI base units** on PDF page 16; measured exact PDF-native region bounds and
  3 column gutters from the native text layer.
* **R4**: built `LG035-R7-T1` table fixture (raster crop via product-native CropBox, scale 4.0)
  and mixed `LG035-R7-MIX` PDF (born-digital p.16 + real scan `clear_real.pdf`).
  `verify_truth.py` → **PASS** (24/24 cells byte-exact, 3×8 structure, text-layer split correct);
  grid decode → 3 horizontal rules, 0 vertical rules (consistent gutters).
* **R5**: froze `COHORT-PLAN-R7.md`, `truth/TRUTH-MANIFEST.json`, `SOURCES.md`, `REPORT.md`,
  `evidence/local_checks.txt`. All changes confined to `probes/materials-fixtures-r7-20261016/**`.
  Budget: GET 7/14, downloads 1/3, 1.93 MiB / 15 MiB, retries 0. Next: commit.
