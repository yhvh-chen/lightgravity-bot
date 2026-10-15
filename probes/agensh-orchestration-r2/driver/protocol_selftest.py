#!/usr/bin/env python3
"""Offline protocol self-test (no network, mock model only).

Verifies the driver's program side:
  1. mutual-exclusion claim grant (first writer wins, second rejected);
  2. unwritable path rejected (package __init__);
  3. ordered message visibility (second claim sees the first claim + message;
     edit phase sees both);
  4. unclaimed-write / overreach rejection;
  5. base-hash mismatch and syntax-error rejection;
  6. state version (subtask base_revision == round base revision);
  7. recovery issues no duplicate requests (call journal replay);
  8. no credentials in the test subprocess env;
  9. same-version acceptance (reference passes, initial fails) -- via validate_fixtures.

Usage: python3 driver/protocol_selftest.py
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_experiment import Experiment, clean_env, parse_frontmatter, sha256_text, writable_paths  # noqa: E402

FAILURES = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global FAILURES
    print(f"{name}: {'OK' if ok else 'FAIL'} {detail}")
    if not ok:
        FAILURES += 1


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="agensh-r2-selftest-"))
    try:
        args = argparse.Namespace(mock=True, resume=False, runs_dir=str(tmp / "runs"))
        exp = Experiment(args)
        snap = {"src/slugs.py": "a", "src/ranges.py": "b", "src/__init__.py": ""}

        # 1. mutual exclusion
        granted: dict[str, str] = {}
        g1 = exp.grant_claim("src/slugs.py", "w1", granted, snap)
        g2 = exp.grant_claim("src/slugs.py", "w2", granted, snap)
        check("claim.mutex", g1["state"] == "granted" and g2["state"] == "rejected"
              and "already_claimed" in g2["reason"], f"{g1} {g2}")
        # 2. unwritable
        g3 = exp.grant_claim("src/__init__.py", "w2", granted, snap)
        check("claim.unwritable", g3["state"] == "rejected", str(g3))
        check("writable.set", writable_paths(snap) == ["src/ranges.py", "src/slugs.py"],
              str(writable_paths(snap)))

        # 3. ordered message visibility
        p_first = exp.claim_messages("t1_independent", "C", 1, "w1", "goal", snap, [], "",
                                     None, {}, [])
        p_second = exp.claim_messages("t1_independent", "C", 1, "w2", "goal", snap, [], "",
                                      None, {"src/slugs.py": "w1"},
                                      [{"worker": "w1", "text": "HELLO-FROM-W1"}])
        first_txt = json.dumps(p_first, ensure_ascii=False)
        second_txt = json.dumps(p_second, ensure_ascii=False)
        check("msg.order", "HELLO-FROM-W1" not in first_txt
              and "HELLO-FROM-W1" in second_txt and "src/slugs.py" in second_txt,
              "first cannot see; second can see first claim+message")
        e1 = exp.edit_messages("t1_independent", "C", 1, "w1", "goal", snap, [], "", None,
                               "src/slugs.py", {"src/slugs.py": "w1"},
                               [{"worker": "w1", "text": "HELLO-FROM-W1"},
                                {"worker": "w2", "text": "MSG-FROM-W2"}])
        e1txt = json.dumps(e1, ensure_ascii=False)
        check("msg.edit.visible", "HELLO-FROM-W1" in e1txt and "MSG-FROM-W2" in e1txt,
              "edit phase sees both messages")

        # 4. overreach / unclaimed write
        edit_ok = {"edits": [{"path": "src/slugs.py", "base_sha256": sha256_text("a"),
                              "content": "x = 1\n"}]}
        valid, over, invalid = exp.validate_edits(snap, None, edit_ok)
        check("edit.unclaimed.rejected", not valid and over and not invalid, f"{over}")
        edit_ok2 = {"edits": [{"path": "src/ranges.py", "base_sha256": sha256_text("b"),
                               "content": "y = 2\n"}]}
        valid, over, invalid = exp.validate_edits(snap, "src/slugs.py", edit_ok2)
        check("edit.overreach.other_lease", not valid and over, f"{over}")

        # 5. base hash mismatch + syntax error
        bad_hash = {"edits": [{"path": "src/slugs.py", "base_sha256": "deadbeef",
                               "content": "x = 1\n"}]}
        valid, over, invalid = exp.validate_edits(snap, "src/slugs.py", bad_hash)
        check("edit.basehash", not valid and invalid and invalid[0]["reason"] == "base_sha256_mismatch",
              f"{invalid}")
        syn = {"edits": [{"path": "src/slugs.py", "base_sha256": sha256_text("a"),
                          "content": "def broken(:\n"}]}
        valid, over, invalid = exp.validate_edits(snap, "src/slugs.py", syn)
        check("edit.syntax", not valid and invalid and "syntax_error" in invalid[0]["reason"],
              f"{invalid}")
        good = {"edits": [{"path": "src/slugs.py", "base_sha256": sha256_text("a"),
                           "content": "def ok():\n    return 1\n"}]}
        valid, over, invalid = exp.validate_edits(snap, "src/slugs.py", good)
        check("edit.valid", len(valid) == 1 and not over and not invalid)

        # 6/7. full mock run + state version + recovery without duplicate requests
        spec = {"task": "t1_independent", "group": "B", "repeat": 0}
        res = exp.run_sample(spec)
        first_calls = exp.fake.calls
        check("run.completed", res.get("completed") is True and res.get("all_passed") is True,
              f"final={res.get('final_passed')}/{res.get('final_total')}")
        run_dir = Path(tmp / "runs" / res["run_id"])
        base_r1 = res["round1"]["base_revision"]
        fm = parse_frontmatter(run_dir / "subtasks" / "r1-w1.md")
        check("state.version", fm.get("base_revision") == base_r1,
              f"subtask={fm.get('base_revision')} round={base_r1}")
        check("run.no_sot", res.get("sot_issues") == [], str(res.get("sot_issues")))

        # partial recovery: remove results.json but keep the call journal; resume must not re-request
        (run_dir / "results.json").unlink()
        args2 = argparse.Namespace(mock=True, resume=True, runs_dir=str(tmp / "runs"))
        exp2 = Experiment(args2)
        res2 = exp2.run_sample(spec)
        check("recovery.no_duplicate_request", exp2.fake.calls == 0,
              f"new HTTP calls={exp2.fake.calls} (was {first_calls} on first run)")
        check("recovery.same_result", res2.get("all_passed") is True)

        # 8. no credentials to test subprocess
        env = clean_env()
        check("env.no_secret", "DEEPSEEK_API_KEY" not in env and all(
            "KEY" not in k and "SECRET" not in k.upper() and "TOKEN" not in k.upper() for k in env),
            str(sorted(env.keys())))

        # raw scan: driver must not have written any auth header material anywhere under runs
        leaked = []
        for p in Path(tmp / "runs").rglob("*"):
            if p.is_file() and p.suffix in (".json", ".jsonl", ".md"):
                txt = p.read_text(encoding="utf-8", errors="replace")
                if "Bearer " in txt or "Authorization" in txt:
                    leaked.append(str(p))
        check("raw.no_auth_leak", not leaked, f"leaked={leaked}")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\nprotocol self-test: {'ALL OK' if FAILURES == 0 else f'{FAILURES} FAILURES'}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
