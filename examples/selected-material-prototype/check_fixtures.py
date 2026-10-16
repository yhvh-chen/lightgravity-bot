#!/usr/bin/env python3
"""Offline checks for the selected-material prototype demo assets (LG-045).

These checks are deliberately small. They do NOT mirror product tests, do NOT
call any model or network, and do NOT claim runtime QA. They only confirm the
fixture corpus is structurally sound:

  * every fixture parses as UTF-8;
  * every file referenced by expected-facts.json exists;
  * fixtures stay under a bounded word count;
  * the guide's Markdown links resolve to real files.

Exit code 0 = all checks passed, 1 = at least one check failed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
FIXTURES = HERE / "fixtures"
EXPECTED = HERE / "expected-facts.json"
GUIDE = REPO_ROOT / "docs" / "11-selected-material-demo.md"

# Bounded word counts: a source brief must stay well inside the 12000-char
# selected-material budget and must be short enough for a human to review.
MAX_FIXTURE_WORDS = 600

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}")
        FAILURES.append(message)


def main() -> int:
    print("== UTF-8 parse ==")
    fixture_paths = sorted(FIXTURES.glob("*"))
    check(bool(fixture_paths), f"found fixtures in {FIXTURES.relative_to(REPO_ROOT)}")
    texts: dict[str, str] = {}
    for path in fixture_paths:
        try:
            texts[path.name] = path.read_text(encoding="utf-8")
            check(True, f"{path.name} parses as UTF-8")
        except UnicodeDecodeError as exc:  # pragma: no cover - failure path
            check(False, f"{path.name} is not valid UTF-8: {exc}")

    print("== expected-facts.json parse and references ==")
    try:
        facts = json.loads(EXPECTED.read_text(encoding="utf-8"))
        check(True, "expected-facts.json parses as JSON")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        check(False, f"expected-facts.json does not parse: {exc}")
        return _finish()

    declared = facts.get("fixtures", {})
    for name in declared:
        check((FIXTURES / name).is_file(), f"expected-facts.json references existing {name}")

    print("== sample labelling ==")
    for name, meta in declared.items():
        check(meta.get("sample") is True, f"{name} is marked sample=true")
        check(meta.get("ocr_output") is False, f"{name} is marked ocr_output=false")
    note = str(facts.get("_note", "")).lower()
    check("not ocr" in note or "not measured" in note, "expected-facts.json carries a not-OCR/not-measured note")
    for name, text in texts.items():
        lowered = text.lower()
        check("sample" in lowered, f"{name} body is labelled SAMPLE")

    print("== bounded word counts ==")
    for name, text in texts.items():
        words = len(text.split())
        check(words <= MAX_FIXTURE_WORDS, f"{name} has {words} words (<= {MAX_FIXTURE_WORDS})")

    print("== guide Markdown links resolve ==")
    if not GUIDE.is_file():
        check(False, f"guide {GUIDE.relative_to(REPO_ROOT)} exists")
    else:
        guide_text = GUIDE.read_text(encoding="utf-8")
        links = re.findall(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)", guide_text)
        relative = [ln for ln in links if "://" not in ln]
        check(bool(relative), "guide contains relative Markdown links")
        for link in sorted(set(relative)):
            target = (GUIDE.parent / link).resolve()
            check(target.exists(), f"guide link resolves: {link}")

    return _finish()


def _finish() -> int:
    if FAILURES:
        print(f"\nFAILED: {len(FAILURES)} check(s)")
        return 1
    print("\nALL_OK: fixture checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
