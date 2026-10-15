#!/usr/bin/env python3
"""Materials Quality R3 — scoring helpers (pure local; no network).

Implements the frozen TRUTH-PREP SCORING-PROTOCOL: NFKC + whitespace-strip,
Levenshtein over code points, CER, field-token byte-exactness after NFKC, and
the Z2 structural check (row/col counts from the human layout).
"""
from __future__ import annotations

import unicodedata


def normalise(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return "".join(ch for ch in s if not ch.isspace())


def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
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


def cer(truth: str, hyp: str) -> dict:
    nt, nh = normalise(truth), normalise(hyp)
    d = edit_distance(nt, nh)
    return {
        "truth_chars": len(nt),
        "hyp_chars": len(nh),
        "edit_distance": d,
        "cer": round(d / max(1, len(nt)), 6),
    }


# ---- Z2 human layout (frozen from truth/LG035-ZH-Z2.p2.txt) ------------------
# Rows = the *-prefixed dialect lines; 3 dialects per section; segments are the
# comma/clause-delimited cells. The structural criterion is frozen in PLAN §2.
Z2_HUMAN_ROWS = [
    "*國、有一囘，北風跟太陽兩個人在那兒爭論誰的本事大。",
    "*蘇、有一轉，北風搭太陽两家頭勒浪爭啥人格本事大。",
    "*廣、有一句，北風同𤍠頭兩個人喺處爭論邊個嘅本事大。",
    "*北風說，我的本事大極了。",
    "*北風說，我格本事大極哉。",
    "*北風話，我嘅本事至大嘅喇。",
    "*世界上的東西沒有不怕我的。",
    "*世界浪格末事嘸不勿怕我格。",
    "*世界上嘅野冇唔怕我嘅。",
    "*船碰見了我就會翻，房子碰見了我就會坍，樹碰見了我就會倒，什",
    "*船碰着仔我就會翻，房子碰着仔我就會坍，樹碰着仔我就會倒，啥",
    "*船見親我就會噲沈，屋見親我我就會 冧，樹見親我就會倒，個",
    "*末貓阿，狗阿，花阿，草阿，他們見了我，更是怕得不得了了。",
    "*格貓阿，狗阿，花阿，草阿，俚篤見仔我，加二嚇得勿知那亨哉。",
    "*的貓阿，狗阿，花阿，草阿，佢哋見親我，越發怕到交關喇。",
]


def z2_human_segments() -> list[str]:
    segs: list[str] = []
    for row in Z2_HUMAN_ROWS:
        segs.append(row)
    return segs


def field_tokens(truth: str) -> list[str]:
    """Number/ID-like tokens that must appear byte-exact (NFKC) per protocol §3."""
    import re

    n = normalise_keeptokens(truth)
    return re.findall(r"\d[\d,]*", n)


def normalise_keeptokens(s: str) -> str:
    return unicodedata.normalize("NFKC", s)
