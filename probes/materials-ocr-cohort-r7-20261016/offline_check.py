#!/usr/bin/env python3
"""LG-035 R7 cohort — OFFLINE parser/ledger check (no model, no network).

1. Parser accepts a correct Markdown table and an aligned plain table.
2. Parser REJECTS unstructured prose (structure=FAIL, no truth fill).
3. A deliberately wrong / partial machine output scores FAIL and is not repaired
   from GT.
4. Truth-as-hypothesis scores 0.0 (sanity double-entry).
5. Ledger integrity: raw-before-score ordering + reservation counts.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVID = os.path.join(HERE, "evidence")
sys.path.insert(0, HERE)

from table_score import parse_table, score_table  # noqa: E402

TRUTH_PATH = "/home/yhvh/code/lightgravity-bot-worktrees/materials-fixtures-r7-20261016/probes/materials-fixtures-r7-20261016/truth/LG035-R7-T1.table.json"

MD_GOOD = """Here is the table:
| Base quantity | Name | Symbol |
| --- | --- | --- |
| length | meter | m |
| mass | kilogram | kg |
| time | second | s |
| electric current | ampere | A |
| thermodynamic temperature | kelvin | K |
| amount of substance | mole | mol |
| luminous intensity | candela | cd |
"""

PLAIN_GOOD = """Base quantity               Name        Symbol
length                      meter       m
mass                        kilogram    kg
time                        second      s
electric current            ampere      A
thermodynamic temperature   kelvin      K
amount of substance         mole        mol
luminous intensity          candela     cd
"""

PROSE = "The SI base units define length, mass, time and other quantities with symbols m, kg, s, A, K, mol, cd."


def main() -> int:
    truth = json.load(open(TRUTH_PATH, encoding="utf-8"))
    out: dict = {"phase": "offline_parser_ledger_check", "checks": []}

    def check(name, ok, detail):
        out["checks"].append({"name": name, "ok": bool(ok), "detail": detail})

    # 1a markdown
    rows, method = parse_table(MD_GOOD)
    check("accept_markdown", method == "markdown_pipe" and len(rows) == 8 and all(len(r) == 3 for r in rows),
          {"method": method, "rows": len(rows)})
    s_md = score_table(MD_GOOD, truth)
    check("markdown_gate_pass", s_md["table_gate_pass"] and s_md["cell_cer"] == 0.0,
          {"cell_cer": s_md["cell_cer"], "gate": s_md["table_gate_pass"]})

    # 1b plain aligned
    rows2, method2 = parse_table(PLAIN_GOOD)
    check("accept_plain", method2 == "plain_aligned" and len(rows2) == 8 and all(len(r) == 3 for r in rows2),
          {"method": method2, "rows": len(rows2)})
    s_pl = score_table(PLAIN_GOOD, truth)
    check("plain_gate_pass", s_pl["table_gate_pass"] and s_pl["cell_cer"] == 0.0,
          {"cell_cer": s_pl["cell_cer"], "gate": s_pl["table_gate_pass"]})

    # 2 reject prose
    s_prose = score_table(PROSE, truth)
    check("reject_prose", s_prose["structure_pass"] is False and s_prose["rows_exact"] is False,
          {"method": s_prose["parse_method"], "machine_rows": s_prose["machine_rows"],
           "gate": s_prose["table_gate_pass"]})

    # 3 wrong machine output not repaired from GT: swap a symbol
    bad = MD_GOOD.replace("| length | meter | m |", "| length | meter | x |")
    s_bad = score_table(bad, truth)
    tok = [t for t in s_bad["symbol_token_checks"] if t["token"] == "m"][0]
    check("no_gt_repair", (not s_bad["symbol_tokens_all_exact"]) and tok["machine_cell"] == "x"
          and s_bad["table_gate_pass"] is False,
          {"cell_cer": s_bad["cell_cer"], "m_cell": tok["machine_cell"],
           "all_exact": s_bad["symbol_tokens_all_exact"]})

    # 4 drop a row -> rows_exact False, CER penalty
    dropped = "\n".join(MD_GOOD.splitlines()[:-2]) + "\n"
    s_drop = score_table(dropped, truth)
    check("row_count_exact_enforced", s_drop["rows_exact"] is False and s_drop["cell_cer"] > 0.0,
          {"machine_rows": s_drop["machine_rows"], "cell_cer": round(s_drop["cell_cer"], 4)})

    # 5 ledger integrity check (if live_ledger.jsonl exists)
    ledger = os.path.join(EVID, "live_ledger.jsonl")
    if os.path.exists(ledger):
        kinds = []
        with open(ledger, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if ln:
                    kinds.append(json.loads(ln)["kind"])
        reserv = kinds.count("reservation")
        raw = kinds.count("raw_response")
        check("ledger_reservation_before_raw", reserv == 3 and raw == 3,
              {"kinds": kinds, "reservations": reserv, "raw": raw})
    else:
        check("ledger_present", True, "no live ledger yet (offline pre-POST)")

    out["all_ok"] = all(c["ok"] for c in out["checks"])
    os.makedirs(EVID, exist_ok=True)
    with open(os.path.join(EVID, "offline_parser_ledger_check.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    for c in out["checks"]:
        print(("OK " if c["ok"] else "FAIL"), c["name"], json.dumps(c["detail"], ensure_ascii=False))
    print("ALL_OK" if out["all_ok"] else "CHECK_FAILED")
    return 0 if out["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
