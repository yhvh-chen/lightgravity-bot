"""Show that the current product stop path never stops the real SDK reviewer.

Same as decisive scenario A, but instead of releasing the gate we observe the
run for a bounded window after the "unconfirmed" stop, to demonstrate the turn
keeps running purely because the product never told the SDK to cancel.

0 real model calls.  Wrap in timeout 45.
"""
from __future__ import annotations
import asyncio, json, sys, tempfile, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lightgravity.adapter.proxy as _proxy_module  # noqa: E402
_proxy_module.AUTHORIZED_UPSTREAM_HOSTS = frozenset({"api.deepseek.com", "127.0.0.1"})
import lightgravity.coordinator  # noqa: E402,F401
from lightgravity.coordinator.control import ControlService  # noqa: E402
from lightgravity.coordinator.state import StateWriter  # noqa: E402
from lightgravity.store import FileStore  # noqa: E402
from lightgravity.verify.review import ModelReviewer, ReviewerSupport  # noqa: E402
from lightgravity.verify.review_lifecycle import ReviewLifecycle, run_review_off_loop  # noqa: E402
from fake_upstream import FakeUpstream  # noqa: E402
from decisive_product_vs_sdk_cancel import _FakeCredential, _QueueDouble, _DispatcherDouble, _seed  # noqa: E402


async def _main() -> dict:
    from lightgravity.verify.candidate import load_candidate
    from lightgravity.verify.review import ReviewContext, resolve_candidate_evidence
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); (root / "ws").mkdir(parents=True, exist_ok=True)
        store = FileStore(root / "data", root / "ws")
        upstream = FakeUpstream(hold_seconds=20.0)
        out = {"provider": "provider-substitute", "real_model_calls": 0}
        try:
            task_id, run_id, session_refs = _seed(store)
            reviewer = ModelReviewer(
                ReviewerSupport(model="fake-reviewer", base_url=upstream.base_url, credential_ref="fake-ref"),
                lambda ref: _FakeCredential(), timeout_seconds=30.0,
            )
            lifecycle = ReviewLifecycle(stop_timeout_seconds=5.0)
            resource_stop_report: dict = {}
            loop = asyncio.get_running_loop()
            def runner(stop_event):
                candidate = load_candidate(store, task_id)
                ctx = ReviewContext(task_id=task_id, run_id=run_id, candidate=candidate, store=store,
                                    resolved_evidence=resolve_candidate_evidence(store, candidate),
                                    stop_event=stop_event, resource_stop_report=resource_stop_report)
                return reviewer.review(ctx)
            future = run_review_off_loop(loop, lifecycle, task_id, run_id, runner)
            controller = ControlService(store, StateWriter(store, actor="qa-probe"), _QueueDouble(), _DispatcherDouble(), owner="qa-probe")
            controller.set_review_lifecycle(lifecycle)
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                if upstream.gate.opened.is_set() and lifecycle.is_reviewing(task_id, run_id):
                    break
                await asyncio.sleep(0.02)
            out["stream_opened"] = upstream.gate.opened.is_set()
            out["reviewing"] = lifecycle.is_reviewing(task_id, run_id)
            stop_t0 = time.monotonic()
            outcome = await controller.stop(task_id, "cancel")
            out["control_stop_elapsed_s"] = round(time.monotonic() - stop_t0, 3)
            out["control"] = outcome.to_dict()
            # Observe WITHOUT releasing: does the turn stop on its own because of
            # the product stop request? (It should not.)
            await asyncio.sleep(6.0)
            out["reviewing_6s_after_stop"] = lifecycle.is_reviewing(task_id, run_id)
            out["resource_stop_report_6s_after_stop"] = dict(resource_stop_report)
            out["upstream_saw_client_gone"] = upstream.gate.client_gone.is_set()
            out["future_done_6s_after_stop"] = future.done()
            out["run_state_6s_after_stop"] = store.read("run", run_id).entity.get("state")
            out["task_phase_6s_after_stop"] = store.read("task", task_id).entity.get("phase")
            upstream.gate.release.set()
        finally:
            upstream.close()
        return out


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/lg022-lingering.json")
    result = asyncio.run(_main())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
