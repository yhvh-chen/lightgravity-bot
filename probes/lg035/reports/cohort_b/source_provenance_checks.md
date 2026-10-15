# Cohort B — public-sample provenance / licence checks (verified, with links)

All checks were HTTP reads against public APIs/pages only. No file was used as a
fixture. Download budget spent on samples: **0 bytes** (nothing eligible).

## 1. Microsoft XFUND — real Chinese forms, human labels, but NonCommercial

* Official repo: `https://github.com/doc-analysis/XFUND` (GitHub API `license:
  null`; the licence text is inside the README).
* Paper: XFUND: A Benchmark Dataset for Multilingual Visually Rich Form
  Understanding — `https://arxiv.org/abs/2104.08836`.
* Official download: release `v1.0`
  `https://github.com/doc-analysis/XFUND/releases/tag/v1.0`.
* **Licence (official README §License): CC BY-NC-SA 4.0 — NonCommercial +
  ShareAlike.** Raw text fetched from
  `https://raw.githubusercontent.com/doc-analysis/XFUND/master/README.md`.
  This is **not** licence-clear for a product fixture (the project's
  dependency/licence discipline requires permissive reuse; NC is not
  permissive for this purpose).
* Release assets (verified via GitHub releases API):
  * `zh.val.json` 1,711,142 B — **annotations only** (no images).
  * `zh.val.zip` 69,217,820 B — **images**; exceeds the ≤10 MiB single-file cap.
  * `zh.train.zip` 206,389,536 B — far over cap.
* Verdict: **BLOCKED** — NonCommercial licence AND the image archive is over the
  single-file download cap. The annotation JSON alone cannot be OCRed.

## 2. SWHL/ChineseOCRBench (HuggingFace) — Apache-2.0 re-host, but VQA only

* Dataset: `https://huggingface.co/datasets/SWHL/ChineseOCRBench`.
  API: `license:apache-2.0`, `gated:false`, `private:false`.
* Card (fetched): "3410 images, 3410 QA pairs, all from ReCTS and ESTVQA ...
  data from the MultimodalOCR project".
* Viewer schema (`datasets-server.huggingface.co/first-rows`): features are
  `image, dataset_name, id, question, answers, type`. Sample rows are
  **short-answer VQA** (e.g. question "这家店的名字是什么?" answer "禾不锈钢").
* Size: `num_rows=3410`, `num_bytes_original_files=378,733,877`.
* Verdict: **NOT SUITABLE** — there is **no full-page human transcript**, only a
  short answer, so a page-level CER against human truth cannot be computed. The
  underlying ESTVQA/ReCTS image licence is also not clearly permissive.

## 3. Yuliang-Liu/MultimodalOCR — MIT repo, but underlying image licence unclear

* Repo: `https://github.com/Yuliang-Liu/MultimodalOCR`, `LICENSE.txt` = **MIT**.
* It is the stated upstream of ChineseOCRBench; the Chinese eval images are not
  authored by this repo and their licence is not stated as permissive.
* Verdict: **NOT SUITABLE** — same reason as §2 (VQA, no full-page truth), plus
  upstream image licence unclear.

## 4. tesseract-ocr/test — Apache-2.0, but no Chinese scan+truth pair

* Repo `tesseract-ocr/test`, `license: Apache-2.0` (already used for cohort A).
* `testing/` has 30 `.tif` and only 5 `.txt` truth files; **none** is a real
  Chinese scan with a matching human transcript (`chi_sim.unicharset` is a model
  file, not an image+truth pair).
* Verdict: no Chinese sample available here.

## 5. Data-viewer endpoints used (read-only)

* `https://datasets-server.huggingface.co/splits?dataset=...`
* `https://datasets-server.huggingface.co/first-rows?dataset=...`
* `https://datasets-server.huggingface.co/size?dataset=...`
* HuggingFace dataset metadata API returns **401** for gated datasets
  (`HURIDOCS/xfund`, `unilm/xfund`, `IBM/fintabnet`, `bsmock/pubtabnet`), so
  those cannot be inspected without a token; none was used.
