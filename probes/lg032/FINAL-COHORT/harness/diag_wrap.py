"""Narrow diagnostic: capture the real exception from the pool selection executor.

Harness-only observer (no product edit): wraps ``AntigravityExecutor.execute``
to record any exception/traceback plus the request shape to a narrow file.
"""
from __future__ import annotations

import functools
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(os.environ.get("LG032_DIAG_OUT", "/tmp/lg032-diag")) 
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "exec_diag.jsonl"


def install(executor) -> None:
    orig = executor.execute
    if getattr(orig, "_lg032_diag", False):
        return

    @functools.wraps(orig)
    async def wrapped(request, emit):
        rec = {
            "at": datetime.now(timezone.utc).isoformat(),
            "phase": "selection" if not request.acceptance_criteria else "execution",
            "objective_head": (request.objective or "")[:80],
            "allowed_tools": list(request.allowed_tools) if request.allowed_tools is not None else None,
            "custom_tools": [getattr(t, "__name__", str(t)) for t in request.custom_tools],
            "workspace": request.workspace_path,
            "agent_ref": request.agent_ref,
            "save_dir": request.save_dir,
            "skill_refs": list(request.skill_refs or ()),
            "connection_ref": request.connection_ref,
        }
        try:
            result = await orig(request, emit)
            rec["outcome"] = "returned"
            rec["state"] = getattr(result, "state", None)
            rec["summary"] = (getattr(result, "summary", "") or "")[:300]
        except BaseException as exc:  # noqa: BLE001 - diagnostic
            rec["outcome"] = "raised"
            rec["exc_type"] = type(exc).__name__
            rec["exc_str"] = str(exc)[:800]
            rec["traceback"] = traceback.format_exc()[-3000:]
            raise
        finally:
            with LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, default=str) + "\n")
        return result

    wrapped._lg032_diag = True  # type: ignore[attr-defined]
    executor.execute = wrapped  # type: ignore[method-assign]
