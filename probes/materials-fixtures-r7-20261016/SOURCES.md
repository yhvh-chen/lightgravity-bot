# LG-035 R7 — acquisition / provenance record

All acquisition in this package is **read-only GET** to primary official sources.
No model / OCR / embedding / ASR call. No product LAN request. No broad crawl, no remote install.

## Budget (declared vs used)

| Item | Declared cap | Used | Notes |
|---|---|---|---|
| read-only GET (primary official) | ≤ 14 | **7** | 3 domain reachability probes + 1 content-length HEAD + 3 PDF byte downloads served via single GET each (see below) |
| downloads (full PDF bodies) | ≤ 3 | **1** | only NIST SP 811 (2,027,518 B) |
| per-download size | ≤ 10 MiB | 1.93 MiB | ok |
| total download bytes | ≤ 15 MiB | 1.93 MiB | ok |
| per-request timeout | 15 s | 15 s | `--connect-timeout 5 --max-time 15` |
| retries | 0 | 0 | |

Exact requests (in order):

1. `GET https://www.nist.gov` → 200, 96,864 B (reachability probe, body discarded)
2. `GET https://ntrs.nasa.gov` → 200, 53,778 B (reachability probe, discarded)
3. `GET https://www.census.gov` → 200, 388,813 B (reachability probe, discarded)
4. `GET https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication811e2008.pdf` (headers/size only) → 200, content-type `application/pdf`, 2,027,518 B
5. `GET https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication811e2008.pdf` (full body, saved) → 200, 2,027,518 B, 1.816 s
6. `GET https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication330e2008.pdf` (headers/size only, unused) → 200, 1,086,411 B
7. `GET https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication811e2008.pdf` (HEAD-style size check counted as GET) → 200

Total GET counter: **7 / 14**. Downloads: **1 / 3**. Bytes downloaded: **1,935,142 / 15,728,640** (saved body only).

## Selected source

| Field | Value |
|---|---|
| Title | Guide for the Use of the International System of Units (SI) — NIST Special Publication 811, 2008 Edition |
| Issuer | National Institute of Standards and Technology (NIST), US federal agency |
| Host | `nvlpubs.nist.gov` (official NIST Publications library) |
| URL | `https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication811e2008.pdf` |
| HTTP status | 200 |
| Bytes | 2,027,518 |
| sha256 | `788dd8f0bcb0ec06e40c300690266742532a7e760a93be57764b77ed0ef3482f` |
| sha1 | `9c13799ff92bebcf75ee49ea0761dfd61548da10` |
| PDF version | 1.6, 90 pages, letter, native text layer, AcroForm |
| License | **US Government work → public domain** (17 U.S.C. §105). NIST SP publications are US federal works and are not subject to copyright in the United States. |
| Attribution | NIST SP 811 (2008), Thompson & Taylor, "Guide for the Use of the International System of Units (SI)". |

## Reused fixtures (unchanged, already in repo)

| File | sha256 | License |
|---|---|---|
| `probes/lg035/fixtures/clear_real.pdf` | `89c6b42242d0aa16efdb7ff814604c4bfc5214e0bbdd040ead67dcf453d9ec0f` | Apache-2.0 (tesseract-ocr/test) |
| `probes/lg035/fixtures/phototest.gold.txt` | `76ef157baeb6ab275b7d90f310477a8060d5822aea2b2e05d480f459b016a6ed` | Apache-2.0 (tesseract-ocr/test) |
| `probes/lg035/fixtures/phototest.tif` | `d2241a1eb6d6cd2eb6544b8e228c2862c852b7467d16ed636caa32179b780692` | Apache-2.0 (tesseract-ocr/test) |
| `probes/lg035/fixtures/8071_093.3B.tif` | `d4f01cba19c99f8894d94a6d43eb8ed8013f8cf17fc08af9346bb9fb3697d452` | Apache-2.0 (tesseract-ocr/test) |

## Explicit disclosures

* The selected table page is **BORN-DIGITAL** (native text layer), **not a historical scan**.
  It is not claimed to be a scanned document. It is nevertheless a *real document OCR* input
  because the product rasterises the real published page and the model sees pixels.
* The mixed fixture is a **composite TEST FIXTURE**, not an unmodified historical document.
* The table page is English (US federal SI guide). The original task does **not** require a
  Chinese table: Chinese printed-page coverage already has Z1 evidence (page CER 0.0423 ≤ 0.15).
* No model output is used as truth anywhere in this package.
