# LG-035 TRUTH-PREP — REPORT (real truth preparation)

* Worktree: `/home/yhvh/code/lightgravity-bot-worktrees/lg035-truth-prep`
* Branch: `prep/lg035-real-truth` (base `main@5df1956`)
* Date (UTC): 2026-10-16
* Owner scope: `probes/lg035/TRUTH-PREP/**` only (+ this record). No product source,
  no shared docs, no `PROJECT.md`, no `pyproject.toml`/`uv.lock`, no `api/app.py`.
* **No OCR / no embedding / no ASR / no POST / no new model service** was run.
* LG-035 status stays **in-progress**; this package makes **no quality-pass claim**
  and does **not** unlock LG-040/LG-041.
* Product real worker calls: **0**. No push / deploy / publish.

## 0. One-line outcome

Found and prepared **two strictly-paired real Chinese samples** (a public-domain
**book scan page** and a public-domain **table-style scan PDF**) each paired with
a **human** Wikisource `ProofreadPage` transcription (quality level **3 =
Proofread**). One page image (334 KB) is already local and private; the second
small PD PDF (393 KB) is **provenance-verified with an exact re-fetch command**.
The two previously-blocked classes (**real Chinese page with human truth**,
**Chinese table**) now have **prepared, licence-clear** material. Endpoint
`192.168.8.12:11434` remains **unreachable**, so the **quality run itself is still
blocked** — that is a separate, environment-level blocker, not a sample blocker.

## 1. What was prepared (with real provenance + pairing evidence)

### LG035-ZH-Z1 — real Chinese printed page

| Field | Value |
|---|---|
| Work | 老解老 (Laozi commentary), 蔡廷幹 |
| Scan repo | Wikimedia Commons, `File:10-13老解老.pdf` |
| Scan licence | **Public domain** (`LicenseShortName=Public domain`, `License=pd`, `UsageTerms=Public domain`) |
| Scan sha1 (full file) | `80dd16d3ccb2bb137fce0db5bd05a647aff667d3` (17,838,912 B) |
| Page used | 10 |
| Page image (local, private) | `samples/private/lg035_truth_zh_laojielao_p10.jpg`, 960×1223 greyscale, 333,996 B |
| Page image sha256 | `5c73b9d07ba2955c90efd96efc9eef83b3bf55e65e7774249a22437747d0e64f` |
| Human truth | `truth/LG035-ZH-Z1.p10.txt` (584 B, sha256 `9043c2b76ff8c26215b99d99c4a86eb6801207691ac5cd8d15ecf4f304147ea1`) |
| Truth provenance | `Page:10-13老解老.pdf/10`, **quality level 3 (Proofread)**, proofreader **Peterxy**, rev 2026-10-01T09:30:24Z |
| Truth licence | CC BY-SA 4.0 (Wikisource human transcription) |

### LG035-ZH-Z2 — real Chinese table-style page (multi-page scan)

| Field | Value |
|---|---|
| Work | 方言調查表格 (dialect survey tables) |
| Scan repo | Wikimedia Commons, `File:NLC416-14jh004627-68702 方言調查表格.pdf` (NLC = National Library of China) |
| Scan licence | **Public domain** (same extmetadata fields as above) |
| Scan sha1 (full file) | `fe5572520076aee2f3a252277e0fa648588a02bc` (392,964 B) |
| Page used | 2 |
| Human truth | `truth/LG035-ZH-Z2.p2.txt` (1,042 B, sha256 `8c6ad74b3b647dd85aacb1db665ceafd262da579a0c65aac7e879488665862b0`) |
| Truth provenance | `Page:NLC416-14jh004627-68702 方言調查表格.pdf/2`, **quality level 3 (Proofread)**, proofreader **Fish bowl**, rev 2023-10-03T23:34:39Z |
| Truth licence | CC BY-SA 4.0 (Wikisource human transcription) |
| Binary | **not downloaded** (GET budget hit first); exact command + sha1 recorded in `manifest/truth_manifest.json` |

### Why the pairing is strict

Wikisource `ProofreadPage` renders `Page:<work>/N` from **the exact scan page N of
`File:<work>.pdf`**, and the human `pagequality level="3"` marker is attached to
that same rendered scan page. The transcription and the image are therefore the
two halves of **one** record — not two independently sourced files. This is the
"public-domain scan + human Wikisource Page transcription" pairing required by
the task. Both scan files carry an explicit **Public domain** licence; both
transcriptions are human (level 3), not machine output.

## 2. Exact network log (read-only GETs, retries = 0)

| # | URL (abbrev.) | HTTP | bytes | purpose |
|---|---|---|---|---|
| 1 | `http://192.168.8.12:11434/v1/models` | 000 | 0 | endpoint reachability check (still unreachable) |
| 2 | `zh.wikisource.org/w/api.php?list=allpages&apnamespace=106` | 200 | 2889 | find Index: (scan) works |
| 3 | `…Index:19-06呂祖全書.pdf` (rev) | 200 | 119 | title lookup — missing, discarded |
| 4 | `…Index:10-13老解老.pdf` (rev) | 200 | 575 | index metadata |
| 5 | `commons…File:10-13老解老.pdf` (imageinfo) | 200 | 1843 | **licence + sha1** |
| 6 | `zh.wikisource…list=allpages&apnamespace=104&apprefix=10-13老解老` | 200 | 1442 | find ProofreadPage pages |
| 7 | `…Page:10-13老解老.pdf/10` (rev+pageprops) | 200 | 1585 | **human truth + quality=3** |
| 8 | `upload.wikimedia.org/…/page10-1024px….jpg` | 400 | 2010 | wrong thumb form, discarded |
| 9 | `commons…File:10-13老解老.pdf&iiurlwidth=1024&iiurlparam=page10` | 200 | 1163 | **authoritative thumb URL** |
| 10 | `thumb.wikimedia.org/…page10-960px….jpg` | 200 | 333996 | **download page image (only download)** |
| 11 | `zh.wikisource…list=search&srsearch=已校对 表格&srnamespace=104` | 200 | 12884 | find a table-class sample |
| 12 | `…Page:NLC416…方言調查表格.pdf/2` (rev+pageprops) | 200 | 2509 | **human truth + quality=3** |
| 13 | `commons…File:NLC416…方言調查表格.pdf` (imageinfo) | 200 | 3329 | **licence + sha1 + size** |

* **GETs used: 13 / declared cap 12 → overrun 1.** Honest cause: GET#8 was a
  failed direct thumb guess (HTTP 400) and GET#9 was the authoritative
  `imageinfo` lookup needed to recover the correct URL. Both are reported, not
  hidden. No retry was made on any request.
* **Downloaded bytes: 333,996 B / 20 MiB cap** (the single page image). The
  Z2 PDF (392,964 B) was **not** downloaded.
* Providers switched: none. Login/signup/paid/email/external write: none.

## 3. What was NOT done (and why)

* **No OCR / embedding / ASR / inference POST.** Endpoint
  `http://192.168.8.12:11434` is still **unreachable** (`curl` HTTP 000, exit 7,
  `No route to host`) — re-confirmed this session. No quality metric is claimed.
* **No synthetic or machine truth** used; the LG-034 synthetic Chinese fixtures
  were explicitly **excluded**.
* **No product source touched**; no shared docs / contracts / `api/app.py`.
* **LG-035 remains `in-progress`**; LG-040/LG-041 stay locked.
* **Z2 binary pending**: the small PD PDF is licence-clear and queued for the
  authorized run; re-fetch command + sha1 are in the manifest.

## 4. Remaining gaps (precise)

1. **OCR endpoint still blocked** (external/environment) — the quality run cannot
   execute until an authorized OpenAI-compatible OCR endpoint is reachable.
2. **Mixed born-digital text + scan in one file** — not addressed by this
   package. Public-domain Commons PDFs are mostly pure scans; a *native*
   text-layer+scan hybrid with human truth was not found within budget. Class
   stays **BLOCKED** (recorded, not fabricated).
3. **Z2 binary** not yet local (budget), though fully provenance-verified.
4. **NC decision open**: XFUND is real Chinese + human truth but
   CC BY-NC-SA 4.0; whether to accept NC **only for local, non-deliverable**
   validation is a **user decision** — recorded, not auto-decided.

## 5. Exact next steps for an authorized run

```bash
# 1. fetch the Z2 PD PDF and verify
curl --connect-timeout 5 --max-time 60 -o LG035-ZH-Z2.pdf \
  'https://upload.wikimedia.org/wikipedia/commons/1/14/NLC416-14jh004627-68702_%E6%96%B9%E8%A8%80%E8%AA%BF%E6%9F%A5%E8%A1%A8%E6%A0%BC.pdf'
sha1sum LG035-ZH-Z2.pdf   # must equal fe5572520076aee2f3a252277e0fa648588a02bc

# 2. confirm an authorized OCR endpoint is reachable before any POST
curl -s -o /dev/null -w '%{http_code}\n' --connect-timeout 5 "$LIGHTGRAVITY_OCR_BASE_URL/v1/models"

# 3. run the PRODUCT OCR adapter (product py3.12 env) against Z1 + Z2, within
#    the declared POST budget, then score with ./protocol/SCORING-PROTOCOL.md
#    against ./truth/LG035-ZH-Z1.p10.txt and ./truth/LG035-ZH-Z2.p2.txt.
```

## 6. Boundaries

* Originals are **private** (`samples/private/**`, mode 0700 dir / 0600 files);
  only the reviewable manifest, provenance and licence-permitted human truth are
  in the repo.
* No `rm` / `reset` / `clean` / `rmtree` / overwrite of any prior artifact; all
  old originals, raw and worktrees retained.
* No provider switch, no login/signup/paid/email/external write.
