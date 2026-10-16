"""LG-047 R2 classifier fix probe: observed finding + regressions (no model calls).

Runs the deterministic classifier only; classifies the ORIGINAL user input.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

from lightgravity.coordinator.classification import classify_message  # noqa: E402

ORION = (
    "Create a Markdown file orion-summary.md using only the selected brief. "
    "Include project name, programme owner, primary launch date, total approved "
    "budget, project ID, and change ticket. Return the file as the deliverable."
)
CORRECTED = (
    "Create the deliverable orion-summary.md (Markdown) using only the selected "
    "brief. It must contain the project name, programme owner, primary launch "
    "date, total budget, project ID, and change ticket. Return the file as the "
    "deliverable."
)

CASES: tuple[tuple[str, str, str], ...] = (
    (ORION, "delivery", "observed finding goal"),
    (CORRECTED, "delivery", "QA corrected goal (no 'approved')"),
    ("Who approved the budget?", "answer", "derived word in question"),
    ("What is the approval status?", "status_query", "noun 'approval'"),
    ("Create acceptance.md", "delivery", "filename acceptance.md"),
    ("Create approved-budget.md", "delivery", "filename approved-budget.md"),
    ("Create a doc explaining the cancellation policy", "delivery", "noun 'cancellation'"),
    ("Please approve the current candidate.", "decision", "explicit approve"),
    ("Please accept the current candidate", "decision", "explicit accept"),
    ("reject the current candidate", "decision", "explicit reject"),
    ("cancel the running task", "control", "explicit cancel"),
    ("pause the running task", "control", "explicit pause"),
    ("resume the task", "retry", "explicit resume"),
    ("How do I create file?", "answer", "question not write auth"),
    ("Create a file accept.md listing the results", "delivery", "filename accept.md"),
    ('Create a file with the text "approve" inside', "delivery", "quoted control word"),
    ("取消那个修改任务", "control", "existing Chinese control"),
    ("读这个文件并解释一下", "bounded_read", "existing Chinese read"),
    ("现在进度如何？", "status_query", "existing Chinese status"),
    ("修改示例页面并验证登录功能", "delivery", "existing Chinese delivery"),
)


def main() -> int:
    results = []
    failures = 0
    for text, expected, label in CASES:
        out = classify_message(text)
        ok = out.intent.value == expected
        failures += 0 if ok else 1
        results.append(
            {
                "label": label,
                "text": text,
                "expected_intent": expected,
                "intent": out.intent.value,
                "next_action": out.next_action,
                "matched": list(out.matched),
                "ok": ok,
            }
        )
    payload = {"cases": results, "failures": failures, "total": len(results)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
