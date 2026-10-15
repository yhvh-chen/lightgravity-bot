# LG-035 TRUTH-PREP — Z2 BINARY CLOSE (addendum, additive only)

* Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/lg035-truth-prep`
* Branch: `prep/lg035-real-truth`
* Date (UTC): 2026-10-16
* Owner scope: `probes/lg035/TRUTH-PREP/**` only (+ LG-035 addendum status).
  Does **not** touch main / shared source / `docs/08` / frontend / coordinator /
  store / contracts / `PROJECT.md` / `api/app.py` / `pyproject.toml` / `uv.lock`.
* Product real worker calls: **0**. No POST, no OCR / embedding / ASR, no model
  call, no provider switch. No push / deploy / publish.
* LG-035 status stays **in-progress**; this addendum makes **no quality-pass
  claim** and does **not** unlock LG-040 / LG-041.

This file is an **addendum**. It does **not** modify any byte of the earlier
`REPORT.md`, `PLAN-STATUS.md` or the frozen `manifest/truth_manifest.json`
history — those are preserved as-is. Corrections and status changes are
**appended** here.

## 0. Purpose

Close the one remaining *preparation* gap for sample **LG035-ZH-Z2**: its
authoritative public-domain original PDF (`NLC416-14jh004627-68702 方言調查表格.pdf`)
was verified by metadata but **not downloaded** (the earlier run exhausted its
GET budget first). This addendum records the **single, separately pre-authorized
read-only GET** that fetches that exact original, verifies its SHA-1 against the
already-frozen manifest expectation, and reads its local structure for
metadata / page count / page-2 pairing with the existing human `ProofreadPage`
ground truth (`truth/LG035-ZH-Z2.p2.txt`).

## 1. Pre-authorization (granted by the user in advance, this session)

| Item | Bound |
|---|---|
| GET requests | **exactly ≤ 1** this session; target is the manifest **already-verified** Z2 exact original URL |
| downloaded bytes | **≤ 1 MiB** (file is known 392,964 B) |
| total request time | ≤ 15 s |
| connect timeout | 5 s |
| retries | **0** (on failure → report honestly, do **not** re-request) |
| redirects | **not allowed** to trigger additional GET |
| other network | **none** — no new search / lookup / HEAD / other URL; no candidate inference service |
| provider | **unchanged** (no switch) |
| if it fails | report `notready` honestly; **do not** issue a second request |

## 2. Honest prior-GET accounting is PRESERVED (not reset)

The earlier package overran its declared GET cap. This is recorded **as fact**
and is **not** retroactively normalised, hidden or zeroed:

* Earlier declared GET cap: **12**; earlier GETs used: **13** → **overrun 1**.
  Cause (verbatim from `REPORT.md` §2): one HTTP 400 wrong thumb guess plus one
  authoritative `imageinfo` lookup used to recover the correct URL. Both are
  reported, not hidden. Retries: 0.
* This addendum authorises **at most 1** additional GET.
* Cumulative accounting this session: **13 (prior) + N (this session, N ≤ 1)**.
  The overrun of **13/12 remains on the record permanently** and is never
  "compensated" by pretending the count was 12.

*(The actual N and the resulting total are filled in §4 after the request.)*

## 3. Download decision rule (no overwrite / no movement / no delete)

1. If a local file already at `samples/private/LG035-ZH-Z2.pdf` exists, **do not**
   GET: hash-check it, and if `sha1 == manifest expected` mark `binary_ready` by
   reuse (this preserves bytes; never overwrite).
2. Otherwise perform the **single** authorized GET to the exact manifest URL
   into `samples/private/LG035-ZH-Z2.pdf` (new private file, mode 0600).
3. Compare **actual** sha1 with the manifest expected sha1
   `fe5572520076aee2f3a252277e0fa648588a02bc`. **Only if equal** may status be
   marked `binary_ready`. If unequal → keep `provenance_verified_binary_pending`
   and report the mismatch; never edit the expected value.
4. No `rm` / `rmtree` / `reset` / `clean` / overwrite / move / delete of any
   original, ever.

## 4. RESULT (filled after the request)

Status of this section: **CLOSED — binary_ready** (appended after the request).

### 4.1 The single authorized GET (actual)

| Item | Value |
|---|---|
| Requests made this session | **1** (no retry, no second request) |
| URL | `https://upload.wikimedia.org/wikipedia/commons/1/14/NLC416-14jh004627-68702_%E6%96%B9%E8%A8%80%E8%AA%BF%E6%9F%A5%E8%A1%A8%E6%A0%BC.pdf` (exact manifest-verified URL) |
| HTTP | **200** |
| bytes downloaded | **392,964** (≤ 1 MiB cap) |
| redirects | **0** (`--max-redirs 0`; no extra GET triggered) |
| total time | 2.107 s (≤ 15 s) |
| connect timeout | 5 s |
| retries | **0** |
| provider switched | **none** |
| other network (search / lookup / HEAD / other URL / inference) | **none** |

### 4.2 Hash verification (agreement required for `binary_ready`)

| Hash | Value |
|---|---|
| expected sha1 (frozen manifest) | `fe5572520076aee2f3a252277e0fa648588a02bc` |
| **actual sha1** (downloaded file) | `fe5572520076aee2f3a252277e0fa648588a02bc` |
| match | **YES → status `binary_ready`** |
| actual sha256 (new, recorded) | `da50c9f6963f70bc022db55a367b88fd4d6c5be36d899ae5a1d7392aada0eb5a` |
| local private path | `samples/private/LG035-ZH-Z2.pdf` (mode **0600**, dir **0700**) |
| bytes on disk | 392,964 (matches manifest) |

The expected value was **not** edited; it was matched. Since it matched on the
first authorized request, no failure/`notready` path was needed and **no second
request** was issued.

### 4.3 Local PDF structure read (no OCR / no vision / no model)

Read with already-installed local tools (`pdfinfo`, `pdfimages`, `pdftotext`);
**nothing installed, no network, no product source changed**.

| Property | Value |
|---|---|
| PDF version | 1.7 |
| Producer | Foxit GSDK |
| Encrypted | no |
| Page count | **18** |
| Page size | 420.48 × 689.28 pts |
| Text layer | **none** — `pdftotext` over the whole document yields ~18 bytes (blank); page 2 yields 1 byte |
| Nature | **pure scanned pages**, each a single CCITT 1-bit greyscale image at 300 DPI (real scan, not synthetic) |
| Page 2 image | index 1, 1701 × 2873 px, 1-bit grey, 300 DPI, object 13 |
| Page-2 scan extracted (private) | `samples/private/lg035_truth_zh_z2_p2-000.png`, 1-bit 1701×2873, 47,541 B, sha256 `ef05ac173cb3ed5fe2716262becd2773a2b6d634354844eccedadc1d55217955` (mode 0600) |

### 4.4 Pairing with the existing human ground truth

The already-frozen human transcription `truth/LG035-ZH-Z2.p2.txt` (1,042 B,
sha256 `8c6ad74b3b647dd85aacb1db665ceafd262da579a0c65aac7e879488665862b0`,
quality level **3 = Proofread**, proofreader *Fish bowl*,
`Page:NLC416-14jh004627-68702 方言調查表格.pdf/2`) is the **same**
`ProofreadPage` record whose scan page is now local. **File title and page index
match exactly** (`…/2` ↔ PDF page 2): the pair is **strictly paired** and the
sample is **not** fabricated or synthetic.

### 4.5 Final GET accounting (honest, not zeroed)

| Line | Count |
|---|---|
| prior GETs (earlier package) | **13** |
| prior declared cap (earlier package) | 12 → **overrun 1 retained** |
| this session (authorized) | **1** |
| **cumulative total** | **14** |

The earlier **13/12 overrun of 1 remains permanently on the record** and is
**not** normalised, hidden, or reset to zero.

### 4.6 What is still NOT done (unchanged)

* **No OCR / embedding / ASR / inference POST** — the quality run is still
  **blocked** by the unreachable endpoint; this addendum makes **no quality
  claim**.
* **Mixed born-digital text + scan in one file** class is still **BLOCKED**
  (not addressed here; recorded, not fabricated).
* **LG-035 stays `in-progress`**; LG-040 / LG-041 remain **locked**.
* No QC score, no vision call, no model was used; the extracted page-2 PNG is a
  lossless structure extraction of the original embedded scan, **not** a
  synthetic image and **not** OCR output.

### 4.7 Documentation clarifications (additive; append-only, history preserved)

These clarifications are recorded **here only**. They do **not** edit any byte of
the earlier `REPORT.md`, `PLAN-STATUS.md`, `QUALITY-PLAN-COHORT-B.md`,
`probes/lg035/STATUS.md` or the frozen legacy manifest history.

**(a) XFUND NC decision is NO LONGER a blocking dependency for this prep.**
The earlier package (and the LG-035 record) listed "whether to accept XFUND's
CC BY-NC-SA 4.0 NC licence is a user decision" as an open to-do. That dependency
is hereby **explicitly revoked for this preparation**: the two **permissive,
licence-clear PD** pairs (Z1 + Z2, both `License=Public domain` scans with human
`ProofreadPage` level-3 transcriptions) are **sufficient** to complete this
*preparation* step. The user therefore **does not need to make any XFUND NC
choice** to unblock TRUTH-PREP.

> **This addendum makes no NC licence judgement on the user's behalf.** XFUND
> remains **excluded** and **not downloaded / not used**; the NC question is left
> entirely to the user for any *future, separate* evaluation use, exactly as the
> historical record already stated. "Revoking the dependency" means only that the
> prep step no longer *waits* on that decision — it does **not** authorise NC use.

**(b) Remaining evaluation conditions are recorded accurately (prep ≠ done).**
The following are **still open evaluation conditions**, not completed work, and
this addendum does **not** close them:

1. **Mixed born-digital text + scan in one file** — still **missing**; no
   licence-clear real hybrid with human truth was found. Class stays **BLOCKED**.
2. **Quality untested** — the authorized OCR endpoint (`192.168.8.12:11434`) is
   still **unreachable**, so real OCR quality was **not measured**. No CER/quality
   figure is claimed anywhere in this addendum.
3. **Image / PDF** preparation is **not blocked by the un-passed ASR line**, but
   real **OCR / embedding** remains blocked this round by the unreachable
   endpoint.

**(c) Preparation alone is NOT LG-035 done.** Preparing real paired material is
**not** a quality pass. LG-035 stays **in-progress**; **LG-040 / LG-041 remain
locked**. No `qualitypass` is reported.

**(d) No fabricated pairing.** If no reliable same-file / same-page pair had been
available, the correct outcome would have been to report **`notready`** rather
than invent a pair. Here the Z2 file title and page index match the human truth
record exactly, so the pair is genuine — no fabrication was needed.

<!-- END-RESULT -->
