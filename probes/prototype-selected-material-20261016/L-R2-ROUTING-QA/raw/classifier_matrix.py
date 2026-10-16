#!/usr/bin/env python3
"""Independent deterministic classifier probe for the sole J product delta.

Own probe (independent of J's probe). Pure `classify_message` calls — no model,
no network, no SDK, no filesystem. Prints a JSON report to stdout and exits
non-zero if any expectation fails.

Run (own PYTHONPATH binding, main venv interpreter):
  PYTHONPATH=$WT/backend python probes/.../L-R2-ROUTING-QA/raw/classifier_matrix.py
"""

from __future__ import annotations

import json
import sys

from lightgravity.coordinator.classification import MessageIntent, classify_message

# Exact observed-file goal from the R2 QA finding (must route delivery/create_task).
OBSERVED_GOAL = (
    "Create a Markdown file orion-summary.md using only the selected brief. "
    "Include project name, programme owner, primary launch date, total approved "
    "budget, project ID, and change ticket. Return the file as the deliverable."
)

# (label, text, expected_intent, expected_next_action)
CASES: list[tuple[str, str, str, str]] = [
    # --- the sole finding: "approved" must not fire the decision keyword ----
    ("observed_goal_total_approved_budget", OBSERVED_GOAL, "delivery", "create_task"),
    (
        "corrected_goal_no_approved",
        "Create the deliverable orion-summary.md (Markdown) using only the selected "
        "brief. It must contain the project name, programme owner, primary launch "
        "date, total budget, project ID, and change ticket. Return the file as the "
        "deliverable.",
        "delivery",
        "create_task",
    ),
    # --- derived nouns / incidential stems must not become control ----------
    ("derived_word_question_who_approved", "Who approved the budget?", "answer", "direct"),
    ("noun_approval_status", "What is the approval status?", "status_query", "query"),
    ("noun_cancellation_policy", "Create a doc explaining the cancellation policy", "delivery", "create_task"),
    ("noun_acceptance_record", "Create a record of the acceptance decision", "delivery", "create_task"),
    # --- filenames carrying control/decision tokens must not misroute -------
    ("filename_acceptance_md", "Create acceptance.md", "delivery", "create_task"),
    ("filename_approved_budget_md", "Create approved-budget.md", "delivery", "create_task"),
    ("filename_accept_md", "Create a file accept.md with the checklist", "delivery", "create_task"),
    # --- quoted approval token must not execute as a decision ---------------
    ('quoted_approve_literal', 'Create a file with the text "approve" inside', "delivery", "create_task"),
    # --- ordinary questions must NOT authorize write ------------------------
    ("ordinary_how_create_file", "How do I create a file?", "answer", "direct"),
    ("ordinary_what_can_you_do", "What can you do?", "answer", "direct"),
    # --- genuine English control/decision commands KEEP their route ---------
    ("genuine_approve", "Please approve the current candidate.", "decision", "decision"),
    ("genuine_accept", "Please accept the current candidate", "decision", "decision"),
    ("genuine_reject", "reject the current candidate", "decision", "decision"),
    ("genuine_cancel", "cancel the running task", "control", "control"),
    ("genuine_pause", "pause the running task", "control", "control"),
    ("genuine_stop", "stop the running task", "control", "control"),
    ("genuine_resume", "resume the running task", "retry", "retry"),
    ("genuine_continue", "please continue the delivery", "retry", "retry"),
    # --- existing Chinese examples preserved --------------------------------
    ("zh_cancel", "取消那个修改任务", "control", "control"),
    ("zh_accept", "接受这个交付", "decision", "decision"),
    ("zh_read", "读这个文件并解释一下", "bounded_read", "bounded_read"),
    ("zh_status", "现在进度如何？", "status_query", "query"),
    ("zh_delivery", "创建一个说明文件", "delivery", "create_task"),
]


def main() -> int:
    results = []
    failures = 0
    for label, text, exp_intent, exp_action in CASES:
        c = classify_message(text)
        ok = c.intent.value == exp_intent and c.next_action == exp_action
        if not ok:
            failures += 1
        results.append(
            {
                "label": label,
                "text": text,
                "expected_intent": exp_intent,
                "expected_next_action": exp_action,
                "intent": c.intent.value,
                "next_action": c.next_action,
                "matched": list(c.matched),
                "requires_target": c.requires_target,
                "creates_work": c.creates_work,
                "ok": ok,
            }
        )
    report = {
        "probe": "L-R2-ROUTING-QA/classifier_matrix",
        "total": len(CASES),
        "failures": failures,
        "component_only": True,
        "no_model_no_network_no_sdk": True,
        "cases": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
