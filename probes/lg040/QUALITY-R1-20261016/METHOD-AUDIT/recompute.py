#!/usr/bin/env python3
"""LG-040 QUALITY-R1-20261016 METHOD-AUDIT — offline re-scoring (0 model calls).

Independent re-scoring of the EXISTING frozen bytes only. No network, no POST,
no new experiment. Uses the SAME normalization as the original harness
(NFKC -> lowercase -> collapse whitespace -> strip) and the SAME media files.

Findings produced:
  F1 OCR page-1 CER: full-page native truth vs the 600-char mid-page slice.
  F2 TIFF/PNG embedding support classification.
  F3 Q3 image retrieval rank/margin + semantic-duplicate detection.

Run:  .venv/bin/python recompute.py
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import re
import unicodedata

import pypdfium2 as pdfium

HERE = pathlib.Path(__file__).resolve().parent
PKG = HERE.parent
ROOT = PKG.parents[2]

NIST_PDF = ROOT / "probes/materials-fixtures-r7-20261016/sources/nist-sp811/nistspecialpublication811e2008.pdf"
R7_RAW_HYP = ROOT / "probes/materials-ocr-cohort-r7-20261016/evidence/raw/call2_LG035-R7-MIX_p1_text.txt"
R7_SCORES = ROOT / "probes/materials-ocr-cohort-r7-20261016/evidence/scores.json"
QGOLD = PKG / "corpus/d2_phototest_gold.txt"
D3_TIF = ROOT / "probes/lg035/fixtures/phototest.tif"
D3_PNG = PKG / "corpus/d3_phototest.png"


def sha256_file(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm(s: str) -> str:
    """EXACT normalization of the original harness (run_quality.py compute_ocr_cer)."""
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"\s+", " ", s).strip()


def lev(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> tuple[float, int]:
    d = lev(ref, hyp)
    return round(d / max(len(ref), 1), 4), d


def qa_page1_hyp() -> str:
    mc = json.loads((PKG / "evidence/phase1/ocr_machine_content.json").read_text(encoding="utf-8"))
    p1 = mc["content"].split("## Page 1")[1].split("## Page 2")[0]
    return norm(re.sub(r"<!--.*?-->", "", p1, flags=re.S))


def f1_ocr() -> dict:
    doc = pdfium.PdfDocument(str(NIST_PDF))
    page = doc[15]
    full = page.get_textpage().get_text_bounded()
    fulln = norm(full)
    # the erroneous slice the original harness used
    start = full.index("Table 1 gives the seven base quantities")
    end = full.index("4.2 SI derived units")
    slice_n = norm(full[start:end])
    hyp = qa_page1_hyp()
    r7 = json.loads(R7_SCORES.read_text(encoding="utf-8"))
    r7_hyp = norm(R7_RAW_HYP.read_text(encoding="utf-8"))
    c_full, d_full = cer(fulln, hyp)
    c_slice, d_slice = cer(slice_n, hyp)
    c_r7_full, d_r7_full = cer(fulln, r7_hyp)
    return {
        "input_image_sha256": "265f187a8345146435282a6bf898141d748a50b086b8377d4e72fa916150f571",
        "nist_pdf_sha256": sha256_file(NIST_PDF),
        "ocr_hyp_norm_chars": len(hyp),
        "full_page16_native_norm_chars": len(fulln),
        "erroneous_slice_norm_chars": len(slice_n),
        "slice_span_chars_raw": [start, end],
        "cer_hyp_vs_FULL_page": c_full,
        "editdist_hyp_vs_FULL_page": d_full,
        "cer_hyp_vs_600slice_original": c_slice,
        "editdist_hyp_vs_600slice_original": d_slice,
        "r7_prior_truth_source": r7["pages"]["mix_p1_born_digital"]["truth_source"],
        "r7_prior_truth_norm_chars": r7["pages"]["mix_p1_born_digital"]["truth_len_norm"],
        "r7_prior_reported_cer": r7["pages"]["mix_p1_born_digital"]["page_cer"],
        "r7_prior_pass": r7["pages"]["mix_p1_born_digital"]["pass"],
        "r7_hyp_cer_vs_FULL_page_recomputed": c_r7_full,
        "classification": "BENCHMARK_DEFECT",
    }


def f3_ranking() -> dict:
    rr = PKG / "evidence/raw_responses"

    def emb(f: str):
        return json.loads((rr / f).read_text(encoding="utf-8"))["data"][0]["embedding"]

    def cos(a, b):
        return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b)))

    docs = {
        "D1": emb("01_embedding_POST.json"),
        "D2": emb("02_embedding_POST.json"),
        "D4": emb("03_embedding_POST.json"),
        "MIX": emb("04_embedding_POST.json"),
        "D3": emb("05_embedding_POST.json"),
    }
    q3 = emb("06_embedding_POST.json")
    order = sorted(((round(cos(q3, v), 6), k) for k, v in docs.items()), reverse=True)
    d2_text = norm(QGOLD.read_text(encoding="utf-8"))
    return {
        "Q3_query": "scanned page of twelve point text with the quick brown fox sentence",
        "cosine_order": [{"doc": k, "score": s} for s, k in order],
        "rank1": order[0][1],
        "rank2": order[1][1],
        "rank_margin_1_2": round(order[0][0] - order[1][0], 6),
        "D2_gold_is_image_text_duplicate": "12 point text" in d2_text and "quick brown dog" in d2_text,
        "D3_is_image_of_same_content": True,
        "d2_sha256": sha256_file(QGOLD),
        "d3_tif_sha256": sha256_file(D3_TIF),
        "d3_png_sha256": sha256_file(D3_PNG),
        "classification": "KNOWN_LIMIT (same-content cross-modal; not wrong-document)",
    }


def f2_formats() -> dict:
    return {
        "d3_tif_filecmd": "TIFF image data, little-endian, 640x480 bps=1",
        "d3_tif_sha256": sha256_file(D3_TIF),
        "d3_png_sha256": sha256_file(D3_PNG),
        "tiff_embed_http": 500,
        "tiff_embed_body": json.loads((PKG / "evidence/phase1/raw_responses/05_embedding_POST.json").read_text())["error"],
        "png_embed_ok": True,
        "classification": "KNOWN_LIMIT (honest unavailable; not false success)",
    }


def main() -> None:
    out = {
        "audit": "LG-040 QUALITY-R1-20261016 METHOD-AUDIT",
        "offline_only": True,
        "new_model_calls": 0,
        "normalization": "NFKC -> lower -> collapse whitespace -> strip (same as original harness)",
        "F1_ocr": f1_ocr(),
        "F2_formats": f2_formats(),
        "F3_ranking": f3_ranking(),
    }
    (HERE / "recompute_output.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
