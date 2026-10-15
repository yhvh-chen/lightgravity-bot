#!/usr/bin/env python3
"""Freeze snapshot: hash frozen inputs, params, prompts and acceptance before the run.

Writes:
  evidence/offline/config_snapshot.json   frozen constants + task goals + hashes
  evidence/offline/prompt_snapshot.json   every prompt branch with sha256
  evidence/offline/freeze_manifest.sha256 hashes of driver + fixtures + snapshots

The freeze timestamp is written to stdout (UTC, system clock) so PROTOCOL.md can
record the real time, not a placeholder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "driver"))
import run_experiment as rx  # noqa: E402


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sha256_text(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "evidence" / "offline"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    ex = rx.Experiment(argparse.Namespace(mock=True, resume=False, runs_dir=str(out / "_tmp_runs")))

    config = {
        "model": rx.MODEL, "max_tokens": rx.MAX_TOKENS, "temperature": rx.TEMPERATURE,
        "first_event_timeout": rx.FIRST_EVENT_TIMEOUT, "total_timeout": rx.TOTAL_TIMEOUT,
        "thinking": {"type": "disabled"},
        "order_seed": rx.ORDER_SEED, "repeats": rx.REPEATS,
        "max_normal_calls": rx.MAX_NORMAL_CALLS, "max_retries": rx.MAX_RETRIES,
        "max_http": rx.MAX_HTTP, "max_total_tokens": rx.MAX_TOTAL_TOKENS,
        "wall_seconds": rx.WALL_SECONDS, "max_edit_bytes": rx.MAX_EDIT_BYTES,
        "message_max_chars": rx.MESSAGE_MAX_CHARS, "findings_max_items": rx.FINDINGS_MAX_ITEMS,
        "finding_max_chars": rx.FINDING_MAX_CHARS,
        "first_worker_by_repeat": rx.FIRST_WORKER_BY_REPEAT,
        "all_tasks": rx.ALL_TASKS, "all_groups": rx.ALL_GROUPS,
        "writable_exclude_basenames": sorted(rx.WRITABLE_EXCLUDE_BASENAMES),
        "goals": {t: {"goal1": rx.TASKS[t]["goal1"], "goal2": rx.TASKS[t]["goal2"]}
                  for t in rx.ALL_TASKS},
        "program_rules": rx.PROGRAM_RULES,
        "acceptance_hashes": {t: sha256_file(ROOT / "fixtures" / t / "acceptance.py")
                              for t in rx.ALL_TASKS},
    }
    config["goals_hashes"] = {t: {k: sha256_text(v) for k, v in g.items()}
                              for t, g in config["goals"].items()}
    (out / "config_snapshot.json").write_text(json.dumps(config, ensure_ascii=False, indent=2),
                                              encoding="utf-8")

    # Build every prompt branch against the real initial fixtures.
    prompts: dict[str, dict[str, str]] = {}
    for task in rx.ALL_TASKS:
        snap = {p.relative_to(ROOT / "fixtures" / task / "initial").as_posix():
                p.read_text(encoding="utf-8")
                for p in (ROOT / "fixtures" / task / "initial").rglob("*") if p.is_file()}
        for group in rx.ALL_GROUPS:
            plan = json.loads(json.dumps(ex.fake._plan(task))) if group == "B" else None
            for rnd in (1, 2):
                goal = rx.TASKS[task][f"goal{rnd}"]
                for worker in ("w1", "w2"):
                    key = f"{task}/{group}/r{rnd}/{worker}"
                    cm = ex.claim_messages(task, group, rnd, worker, goal, snap, [], "",
                                           plan, {}, [])
                    em = ex.edit_messages(task, group, rnd, worker, goal, snap, [], "",
                                          plan, rx.writable_paths(snap)[0], {}, [])
                    prompts[key + "/claim"] = {"sha256": sha256_text(json.dumps(cm, ensure_ascii=False)),
                                               "messages": cm}
                    prompts[key + "/edit"] = {"sha256": sha256_text(json.dumps(em, ensure_ascii=False)),
                                              "messages": em}
        pm = ex.planner_messages(task, rx.TASKS[task]["goal1"], snap)
        prompts[f"{task}/planner"] = {"sha256": sha256_text(json.dumps(pm, ensure_ascii=False)),
                                      "messages": pm}
    (out / "prompt_snapshot.json").write_text(json.dumps(prompts, ensure_ascii=False, indent=2),
                                              encoding="utf-8")

    # manifest of frozen inputs
    lines = []
    for p in sorted(list((ROOT / "driver").glob("*.py")) + list((ROOT / "fixtures").rglob("*"))):
        if p.is_file() and "__pycache__" not in p.parts:
            lines.append(f"{sha256_file(p)}  {p.relative_to(ROOT).as_posix()}")
    for name in ("config_snapshot.json", "prompt_snapshot.json"):
        lines.append(f"{sha256_file(out / name)}  evidence/offline/{name}")
    manifest = "\n".join(lines) + "\n"
    (out / "freeze_manifest.sha256").write_text(manifest, encoding="utf-8")
    manifest_hash = sha256_text(manifest)
    (out / "freeze_manifest.hash.txt").write_text(
        f"manifest_sha256: {manifest_hash}\n"
        f"frozen_at_utc: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
        f"epoch: {time.time():.3f}\n", encoding="utf-8")
    print(f"frozen_at_utc={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print(f"manifest_sha256={manifest_hash}")
    print(f"files_hashed={len(lines)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
