#!/usr/bin/env python3
"""Freeze the cohort-3 protocol manifest: hashes of code/config/fixtures/prompts.

Run AFTER all harness edits and BEFORE the first formal request.  The manifest is
the frozen identity of the sampled protocol; any later change to an input or to
the harness invalidates the freeze and must stop the cohort.

Usage::

    .venv/bin/python probes/lg023/cohort3/harness/protocol_manifest.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[3]

import cohort3_config as C  # noqa: E402

OUT = C.EVIDENCE_DIR / "offline" / "protocol_manifest.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"freeze violated: {message}")


def main() -> int:
    _validate(C.PHASE_GENERATION_LIMIT == 48, "phase total must be 48")
    _validate(C.ATTEMPT_GENERATION_LIMIT == 12, "attempt cap must be 12")
    _validate(len(C.ATTEMPTS) == 4, "must be exactly 4 attempts")
    _validate(C.WORKER_TOOL_CALLS == 32, "tool cap must be 32")
    _validate(C.WORKER_MODEL_CALLS == 12, "worker model calls must be 12")
    _validate(C.OUTPUT_TOKEN_CAP == 16000, "output cap must be 16000")
    _validate(C.HTTP_TIMEOUT_SECONDS == 120, "http timeout must be 120")
    _validate(C.SDK_RETRIES == 0, "retries must be 0")
    _validate(C.MAX_CONCURRENCY == 2, "concurrency must be <= 2")
    _validate(C.LEDGER_HISTORY == C.PHASE_DATA_DIR / "generation" / "generation.jsonl",
              "frozen ledger path must be <phase>/generation/generation.jsonl")

    # frozen prompt template + planner are inside run_attempt.py; hash it whole.
    run_attempt = HERE / "run_attempt.py"
    spec = importlib.util.spec_from_file_location("cohort3_run_attempt_manifest", run_attempt)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    harness = {
        p.name: _sha(p) for p in sorted(HERE.glob("*.py"))
    }
    fixtures = {
        str(p.relative_to(C.FIXTURES_DIR)): _sha(p)
        for p in sorted(C.FIXTURES_DIR.rglob("*")) if p.is_file()
    }

    product_commit = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True,
    ).stdout.strip()

    manifest = {
        "experiment_id": "lg023-cohort3-20261016",
        "worktree": str(C.WORKTREE),
        "branch": "eval/lg023-cohort3",
        "product_base_commit": C.PRODUCT_BASE_COMMIT,
        "harness_head_commit": product_commit,
        "contract": C.CONTRACT_VERSION,
        "sdk": C.SDK_VERSION,
        "model": C.MODEL,
        "frozen": {
            "phase_generation_limit": C.PHASE_GENERATION_LIMIT,
            "attempt_generation_limit": C.ATTEMPT_GENERATION_LIMIT,
            "attempts": ["__".join(a) for a in C.ATTEMPTS],
            "worker_model_calls": C.WORKER_MODEL_CALLS,
            "worker_tool_calls": C.WORKER_TOOL_CALLS,
            "reviewer_model_calls": C.REVIEWER_MODEL_CALLS,
            "output_token_cap": C.OUTPUT_TOKEN_CAP,
            "http_timeout_seconds": C.HTTP_TIMEOUT_SECONDS,
            "sdk_retries": C.SDK_RETRIES,
            "max_concurrency": C.MAX_CONCURRENCY,
            "ledger_history": str(C.LEDGER_HISTORY),
            "workspace_isolation": "off-both-arms",
        },
        "prompt_template": mod.WORKER_PROMPT_BODY,
        "harness_sha256": harness,
        "fixtures_sha256": fixtures,
        "frozen_protocol_hash": hashlib.sha256(
            json.dumps({"frozen": {
                "phase_generation_limit": C.PHASE_GENERATION_LIMIT,
                "attempt_generation_limit": C.ATTEMPT_GENERATION_LIMIT,
                "attempts": ["__".join(a) for a in C.ATTEMPTS],
                "worker_model_calls": C.WORKER_MODEL_CALLS,
                "worker_tool_calls": C.WORKER_TOOL_CALLS,
                "output_token_cap": C.OUTPUT_TOKEN_CAP,
                "http_timeout_seconds": C.HTTP_TIMEOUT_SECONDS,
                "sdk_retries": C.SDK_RETRIES,
                "max_concurrency": C.MAX_CONCURRENCY,
                "ledger_history": str(C.LEDGER_HISTORY),
                "prompt_template": mod.WORKER_PROMPT_BODY,
                "planner_samples": sorted(mod.SAMPLE_SPEC),
            }}, sort_keys=True).encode()
        ).hexdigest(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"frozen_protocol_hash": manifest["frozen_protocol_hash"],
                      "harness_head_commit": product_commit,
                      "wrote": str(OUT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
