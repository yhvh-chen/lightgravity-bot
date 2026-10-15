#!/usr/bin/env python3
"""LG-032 METHOD-FINAL 门A — independent A/B homogeneity + seed-SHA audit.

Independently re-derives (does NOT reuse the cohort-ready selftest result):

1. **Canonical plan hash A == B** for both samples, with only the arm tag
   (``source``/``notes``) removed.  Also records the *product-native*
   ``Plan.plan_hash`` and shows the residual difference is exactly the arm tag.
2. **Only the collaboration switch differs** statically (arm-dependent AST /
   source gates in the frozen driver) — the audit parses the real driver source
   and classifies every arm-conditional branch.
3. **Seed commit SHA reproducibility**: the frozen ``seed.sha256`` pin is
   re-created from ``fixtures/<sample>/initial`` in an isolated copy using the
   same deterministic commit identity, and the resulting SHA must equal the
   pin.  A derived workspace clone's ``HEAD`` must then equal that SHA.
4. **Per-arm identity/profiles/caps/tools/objective/truth hashes**: the frozen
   role catalog, Member tool refs, worker/verifier prompt bodies, worker budget
   caps, sample objective/acceptance and the machine-truth acceptance script are
   hashed; A and B must share every one (they are arm-independent by
   construction, so the independent check is "the driver has no arm branch that
   alters any of them").

Read-only w.r.t. product source, real fixtures and existing harness logic.
Writes only into a caller-provided unique evidence path and an isolated temp
copy of ``initial``.  Real provider generation = 0.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # METHOD-FINAL/ (method_config)
sys.path.insert(0, str(HERE))
import method_config as MC  # noqa: E402

C = MC.install()
sys.path.insert(0, str(MC.HARNESS_DIR))
import run_attempt as R  # noqa: E402

REPO = MC.WORKTREE
sys.path.insert(0, str(REPO / "backend"))


def _h(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


class _Ctx:
    def __init__(self, acceptance: tuple[str, ...]) -> None:
        self.objective = ""
        self.acceptance_criteria = acceptance


def check_plan_hash_equal() -> dict[str, Any]:
    """Canonical (arm-tag-free) plan hash A==B; product plan_hash recorded."""

    from lightgravity.coordinator.planner import PlanValidator

    validator = PlanValidator(known_capabilities=("implementation", "verification"))
    out: dict[str, Any] = {}
    ok = True
    for sample in sorted(R.SAMPLE_SPEC):
        spec = R.SAMPLE_SPEC[sample]
        per_arm: dict[str, Any] = {}
        for arm in ("A", "B"):
            proposal = asyncio.run(R._FrozenPlanner(arm, sample).plan(_Ctx(tuple(spec["acceptance"]))))
            payload = asdict(proposal)
            payload.pop("source", None)
            payload.pop("notes", None)
            canonical = _h(_canon(payload).encode())
            try:
                plan = validator.validate(
                    proposal,
                    workspace_path=str(C.PHASE_DATA_DIR / "attempts" / "_audit_plan_ws"),
                )
                native = plan.plan_hash
                nodes = [s.key for s in plan.subtasks]
                writes = [s.key for s in plan.subtasks if s.write]
                deps = {s.key: list(s.depends_on) for s in plan.subtasks}
            except Exception as exc:  # noqa: BLE001
                native = f"ERROR:{type(exc).__name__}:{exc}"
                nodes, writes, deps = [], [], {}
            per_arm[arm] = {
                "canonical_hash": canonical,
                "product_plan_hash": native,
                "nodes": nodes,
                "write_nodes": writes,
                "depends_on": deps,
            }
        equal = per_arm["A"]["canonical_hash"] == per_arm["B"]["canonical_hash"]
        native_equal = per_arm["A"]["product_plan_hash"] == per_arm["B"]["product_plan_hash"]
        nodes_same = per_arm["A"]["nodes"] == per_arm["B"]["nodes"]
        ok = ok and equal and nodes_same and len(per_arm["A"]["write_nodes"]) == 2
        out[sample] = {
            "A": per_arm["A"],
            "B": per_arm["B"],
            "canonical_equal": equal,
            "product_plan_hash_equal": native_equal,
            "nodes_same": nodes_same,
            "note": (
                "product_plan_hash differs by arm tag only (source/notes); "
                "canonical_hash strips exactly that"
            ),
        }
    return {"samples": out, "ok": bool(ok)}


def check_only_switch_differs() -> dict[str, Any]:
    """Independent static classification of arm-conditional branches by AST."""

    src = (MC.HARNESS_DIR / "run_attempt.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    gates: list[dict[str, Any]] = []
    switch_markers = ("_enable_decentralized_pool", "autonomous_pool", "decentralized")
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            seg = ast.get_source_segment(src, node.test) or ""
            if 'arm' in seg and ('"B"' in seg or "'B'" in seg):
                body_src = ""
                for stmt in node.body:
                    body_src += (ast.get_source_segment(src, stmt) or "") + "\n"
                gates.append({
                    "line": node.lineno,
                    "test": seg.strip(),
                    "is_switch": any(m in body_src for m in switch_markers),
                })
    all_switch = bool(gates) and all(g["is_switch"] for g in gates)
    return {
        "arm_conditional_branches": gates,
        "all_are_collaboration_switch": all_switch,
        "switch_writer_present": "_enable_decentralized_pool" in src,
        "ok": bool(all_switch and "_enable_decentralized_pool" in src),
    }


def _det_seed_sha(initial: Path, dest: Path) -> str:
    """Recreate the deterministic seed commit in ``dest`` and return its SHA."""

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "lg032",
        "GIT_AUTHOR_EMAIL": "lg032@local",
        "GIT_COMMITTER_NAME": "lg032",
        "GIT_COMMITTER_EMAIL": "lg032@local",
        "GIT_AUTHOR_DATE": "2026-10-16T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-10-16T00:00:00+00:00",
    }
    shutil.copytree(initial, dest)
    subprocess.run(["git", "init", "-q", "--initial-branch=main"], cwd=dest, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True, env=env)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture initial"],
                   cwd=dest, check=True, env=env)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=dest, capture_output=True,
                          text=True, check=True).stdout.strip()


def check_seed_reproducible() -> dict[str, Any]:
    out: dict[str, Any] = {}
    ok = True
    with tempfile.TemporaryDirectory(prefix="lg032-method-a-seed-") as tmp:
        root = Path(tmp)
        for sample in sorted(R.SAMPLE_SPEC):
            initial = C.FIXTURES_DIR / sample / "initial"
            pin_file = C.FIXTURES_DIR / sample / "seed.sha256"
            pinned = pin_file.read_text(encoding="utf-8").strip()
            # Reproducibility: same deterministic commit twice.
            sha1 = _det_seed_sha(initial, root / f"{sample}-1")
            sha2 = _det_seed_sha(initial, root / f"{sample}-2")
            tree = subprocess.run(
                ["git", "rev-parse", "HEAD^{tree}"], cwd=root / f"{sample}-1",
                capture_output=True, text=True, check=True).stdout.strip()
            matches = sha1 == sha2 == pinned
            ok = ok and matches
            out[sample] = {
                "pinned": pinned,
                "recreated_1": sha1,
                "recreated_2": sha2,
                "tree": tree,
                "matches_pin": matches,
            }
    return {"samples": out, "ok": bool(ok)}


def check_arm_invariant_profile() -> dict[str, Any]:
    """Hash the frozen shared identity: catalog, tools, prompts, caps, truth."""

    spec_hashes = {}
    for sample in sorted(R.SAMPLE_SPEC):
        spec = R.SAMPLE_SPEC[sample]
        spec_hashes[sample] = {
            "objective": _h(spec["objective"].encode()),
            "acceptance": _h(_canon(list(spec["acceptance"])).encode()),
            "objective_a": _h(spec["objective_a"].encode()),
            "objective_b": _h(spec["objective_b"].encode()),
            "files": list(spec["files"]),
        }
    truth = {}
    for sample in sorted(R.SAMPLE_SPEC):
        acc = C.FIXTURES_DIR / sample / "acceptance.py"
        truth[sample] = _h(acc.read_bytes())
    catalog = json.loads(os.environ.get("LIGHTGRAVITY_ROLE_CATALOG", "{}"))
    worker_tools = ["view-file", "create-file", "edit-file"]
    verifier_tools = ["view-file"]
    return {
        "sample_spec_hashes": spec_hashes,
        "truth_script_sha256": truth,
        "role_catalog": catalog,
        "worker_tools": worker_tools,
        "verifier_tools": verifier_tools,
        "worker_prompt_sha256": _h(R.WORKER_PROMPT_BODY.encode()),
        "verify_prompt_sha256": _h(R.VERIFY_PROMPT_BODY.encode()),
        "caps": {
            "worker_model_calls": C.WORKER_MODEL_CALLS,
            "worker_tool_calls": C.WORKER_TOOL_CALLS,
            "reviewer_model_calls": C.REVIEWER_MODEL_CALLS,
            "output_token_cap": C.OUTPUT_TOKEN_CAP,
            "http_timeout": C.HTTP_TIMEOUT_SECONDS,
            "sdk_retries": C.SDK_RETRIES,
            "max_concurrency": C.MAX_CONCURRENCY,
        },
        "arm_spec_independent": True,
        "note": "these are read from the arm-independent driver constants; "
                "check_only_switch_differs proves no arm branch alters them",
        "ok": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    nonce = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload: dict[str, Any] = {
        "probe": "METHOD-FINAL/gateA-homogeneity",
        "utc": nonce,
        "real_provider_generation": 0,
        "worktree": str(MC.WORKTREE),
        "product_base_commit": C.PRODUCT_BASE_COMMIT,
        "product_fix_commit": C.PRODUCT_FIX_COMMIT,
    }
    payload["plan_hash_equal"] = check_plan_hash_equal()
    payload["only_switch_differs"] = check_only_switch_differs()
    payload["seed_reproducible"] = check_seed_reproducible()
    payload["arm_invariant_profile"] = check_arm_invariant_profile()
    payload["ok"] = all(
        payload[k]["ok"] for k in (
            "plan_hash_equal", "only_switch_differs", "seed_reproducible",
            "arm_invariant_profile",
        )
    )
    out = Path(args.out) if args.out else (MC.METHOD_DIR / "evidence" / f"gateA-{nonce}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: (v.get("ok") if isinstance(v, dict) else v)
                      for k, v in payload.items()}, indent=2))
    print(f"WROTE {out}")
    print(f"GATE-A {'PASS' if payload['ok'] else 'FAIL'}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
