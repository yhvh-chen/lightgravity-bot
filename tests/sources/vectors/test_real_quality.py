"""Real-service retrieval-quality probe for LG-037 — **skipped by default**.

This is the ONLY test that would contact the authorized candidate service
``http://192.168.8.12:11434``.  It is skipped unless the operator explicitly sets
the vector env config *and* passes ``--run-real-vector``; even then it only runs
if the endpoint is reachable.  When it runs it reports **Recall@k, ranking and
negative-hit counts against the lexical baseline**, with the pre-registered
query set from ``probes/lg037/PLAN.md``.

It is skipped now because the endpoint is unreachable (single read-only probe:
connect failure) and no real quality metric may be produced.  The stand-in
mechanism tests in the sibling files are NOT a quality claim.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("LG037_RUN_REAL_VECTOR") != "1",
    reason=(
        "real vector quality probe requires explicit authorization "
        "(LG037_RUN_REAL_VECTOR=1) and a reachable authorized endpoint; "
        "LG-037 endpoint was unreachable, so no real quality metric is produced"
    ),
)


def test_real_query_set_recall_at_k():
    """Placeholder gated behind explicit authorization and endpoint reachability.

    When enabled, this must:
    1. load the pre-registered query set + relevance ground truth from
       ``probes/lg037/`` (fixed before any service call);
    2. run ``GET /api/v1/search`` (lexical baseline) and vector search;
    3. report Recall@1/3/5, MRR, top-1 accuracy and negative-hit counts;
    4. never claim quality from reachability alone, and never pass generic
       OpenAI string embeddings off as multimodal ability.
    """

    pytest.skip(
        "real service unreachable in this run; pre-registered plan and budgets are in "
        "probes/lg037/PLAN.md — no real quality metric is emitted"
    )
