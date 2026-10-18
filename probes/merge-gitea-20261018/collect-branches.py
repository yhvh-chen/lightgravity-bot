#!/usr/bin/env python3
"""Inventory local branches against current main for the 2026-10-18 Gitea merge.

Outputs branches.tsv and BRANCHES.md in this directory. Read-only except those files.
"""
from __future__ import annotations
import subprocess, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

def run(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True).stdout

def is_ancestor(rev: str, of: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", rev, of], cwd=ROOT).returncode == 0

# worktree map
wt: dict[str, str] = {}
for block in run("git", "worktree", "list", "--porcelain").split("\n\n"):
    lines = block.strip().splitlines()
    if not lines:
        continue
    path = lines[0].split(" ", 1)[1]
    for line in lines[1:]:
        if line.startswith("branch refs/heads/"):
            wt[line[len("branch refs/heads/"):]] = path

CANDIDATE = {
    "integration/google-native-asr-20261018",
    "qa/google-native-asr-20261018",
    "dev/google-native-asr-backend-20261018",
    "dev/google-native-asr-ui-20261018",
    "prep/google-native-asr-20261018",
    "test/lg233-readiness-20261018",
    "integration/demo-tasks-20261018",
    "qa/demo-tasks-20261018",
    "fix/demo-tasks-qa-r1-20261018",
    "dev/demo-tasks-core-20261018",
    "dev/demo-auth-20261018",
    "dev/demo-workspace-20261018",
    "dev/demo-history-20261018",
    "fix/demo-context-20261018",
}
EQUIV = {
    "test/lg233-readiness-20261018": "tree-identical to 539e622 (LG229/230 stage inside accepted candidate); superseded",
    "qa/demo-tasks-20261018": "product-equivalent to integrated 8d869ff; tree differs only in README public text",
    "fix/demo-tasks-qa-r1-20261018": "same tip as qa/demo-tasks; product-equivalent to 8d869ff",
    "feature/lg229-230-no-limits": "public/Gitea-side LG229/230 copy; not merged wholesale; content already in main",
}
FORBIDDEN = {
    "integration/lg214-remote-reader-candidate-20261018": "frozen remote-reader/frame line; explicitly excluded",
    "dev/lg176-reader-container-20261018": "reader-container line; frozen by user, not integrated",
    "dev/lg178-eg2-frame-service-20261018": "EG2 frame service; frozen/excluded",
    "dev/lg179-remote-reader-wiring-20261018": "remote encoder/frame wiring; frozen/excluded",
    "fix/lg180-reader-frame-count-20261018": "reader frame-count fix on frozen line; excluded",
}
FROZEN_ASR = {
    "dev/lg159-english-reader-20261018", "dev/lg160-english-asr-backend-20261018",
    "dev/lg161-english-asr-ui-20261018", "integrate/lg162-english-asr-20261018",
    "qa/lg163-english-asr-20261018", "qa/lg163-english-asr-r2-20261018",
    "fix/lg164-english-asr-ui-copy-20261018", "integrate/lg165-english-asr-repairs-20261018",
    "fix/lg166-english-reader-20261018", "investigate/lg167-upstream-asr-20261018",
}

CODE_PATHS = ["backend", "frontend", "e2e", "tests", "pyproject.toml", "uv.lock",
              "Makefile", "install.sh", "scripts", ".env.example"]

rows = []
for line in run("git", "for-each-ref", "--sort=-committerdate",
                "--format=%(refname:short)|%(objectname:short)|%(committerdate:iso8601)|%(subject)",
                "refs/heads").strip().splitlines():
    branch, tip, date, subject = line.split("|", 3)
    merged = is_ancestor(tip, "main")
    if branch == "main":
        merged = True
        plus = minus = code_files = 0
        category = "current main (this integration result)"
    elif branch == "integration/merge-gitea-20261018":
        merged = True
        plus = minus = code_files = 0
        category = "this task's integration branch (ancestor of main)"
    elif merged:
        plus = minus = code_files = 0
        category = "merged into main (historical; retained)"
    else:
        cherry = run("git", "cherry", "main", branch).strip().splitlines()
        plus = sum(1 for x in cherry if x.startswith("+"))
        minus = sum(1 for x in cherry if x.startswith("-"))
        code_files = len(run("git", "diff", "--name-only", f"main..{branch}", "--", *CODE_PATHS).strip().splitlines())
        if branch == "main":
            category = "current main (integration result)"
        elif branch in FORBIDDEN:
            category = "FORBIDDEN / frozen remote-reader-frame; do not merge"
        elif branch in FROZEN_ASR:
            category = "frozen old Reader/ASR line; quality FAILED; do not merge"
        elif branch in EQUIV:
            category = "equivalent/superseded alternative; no new product delta"
        elif branch in CANDIDATE:
            category = "candidate/contributor (accepted or parent of accepted candidate)"
        elif branch.startswith(("experiment/", "eval/", "lg/run_")):
            category = "experiment/run artifact; preserve, never merge"
        elif branch.startswith(("qa/", "test/", "investigate/")):
            category = "QA/evidence branch; no deliverable candidate"
        elif branch.startswith(("publish/", "delivery/", "ops/", "deploy/")):
            category = "publish/delivery/ops record; retained, not a code candidate"
        elif code_files == 0:
            category = "docs/evidence only; no product delta"
        else:
            category = "historical/superseded feature branch; not a candidate"
    rows.append(dict(branch=branch, tip=tip, date=date, subject=subject,
                     merged=merged, plus=plus, minus=minus, code_files=code_files,
                     worktree=wt.get(branch, ""), category=category))

# remote refs
remote = []
for line in run("git", "for-each-ref", "--format=%(refname:short)|%(objectname:short)|%(subject)",
                "refs/remotes/origin").strip().splitlines():
    remote.append(line.split("|", 2))

merged_count = sum(1 for r in rows if r["merged"])
unmerged = [r for r in rows if not r["merged"]]

with (OUT / "branches.tsv").open("w") as f:
    f.write("branch\ttip\tdate\tsubject\tmerged\tcherry_plus\tcherry_minus\tcode_files\tworktree\tcategory\n")
    for r in rows:
        f.write("\t".join(str(r[k]) for k in ("branch","tip","date","subject","merged",
                 "plus","minus","code_files","worktree","category")) + "\n")

def esc(s: str) -> str:
    return s.replace("|", "\\|")

with (OUT / "BRANCHES.md").open("w") as f:
    f.write("# Branch inventory — Gitea merge 2026-10-18\n\n")
    f.write(f"- Repo: `{ROOT}`\n- Current `main`: `{run('git','rev-parse','HEAD').strip()}`\n")
    f.write(f"- Local branches: **{len(rows)}**; merged/ancestor of main: **{merged_count}**; unmerged tips: **{len(unmerged)}**\n")
    f.write("- Remote refs fetched: **3 branches plus `origin/HEAD`** (`origin/main`, `origin/development/task-teams-20261018`, `origin/feature/lg229-230-no-limits`)\n")
    f.write("- This file is generated by `collect-branches.py`; `branches.tsv` has the same data.\n\n")
    f.write("## 1. Merge decision\n\n")
    f.write("Accepted product candidate: `integration/google-native-asr-20261018` tip `9592185` "
            "(frozen product commit `ecda49f`, tree `d96f22b`). It contains the accepted Tasks 1.21 "
            "integration (`8d869ff`) and the Google-native ASR backend/UI. Independent QA: LG-239 "
            "`PASS_WITH_LIMITATIONS`; LG-207 `PASS_WITH_LIMITATIONS`. The merge was performed on top of "
            "current main and the published `origin/main` history (tree kept from the newer internal main).\n\n")
    f.write("Merged result: product subtrees `backend`/`frontend`/`tests`/`e2e` are byte-identical to "
            "`ecda49f`; docs/management files were reconciled separately (contract 1.22.0, no usage limits preserved). "
            "No deployment, service restart, Google call, or Cloud resource was performed by this integration.\n\n")
    f.write("### Accepted / contributing branches\n\n")
    for b in sorted(CANDIDATE):
        r = next((x for x in rows if x["branch"] == b), None)
        if r:
            f.write(f"- `{b}` ({r['tip']}) — {'ancestor of main' if r['merged'] else 'unmerged tip'}; {EQUIV.get(b, 'accepted or parent of accepted candidate')}\n")
    f.write("\n### Explicitly excluded\n\n")
    for b, why in FORBIDDEN.items():
        f.write(f"- `{b}` — {why}\n")
    f.write("- The old EG2/Reader English-ASR line (quality **FAILED**) is retained only as history/evidence; do not merge it over the Google-native provider.\n")
    f.write("- Old failed/experimental/QA-only branches are retained, not deleted.\n\n")
    f.write("### Cherry-pick / tree equivalence notes\n\n")
    f.write("- `qa/google-native-asr-20261018` = frozen `ecda49f`; `integration/google-native-asr-20261018` adds only the LG-238 delivery report.\n")
    f.write("- `dev/google-native-asr-backend-20261018` (`26a87ad`) and `dev/google-native-asr-ui-20261018` (`f17b0d1`) are parents; `b5b7e39` is the exact cherry-pick of the UI tip.\n")
    f.write("- `8d869ff` (Tasks 1.21) contains cherry-pick equivalent commits for LG-219/LG-221/LG-205; `dev/demo-tasks-core` `84a20ce` was adapted during integration.\n")
    f.write("- `test/lg233-readiness-20261018` `84c33c1` has the same backend/frontend/tests/docs trees as `539e622` (LG229/230 stage inside the accepted candidate).\n")
    f.write("- `qa/demo-tasks-20261018` / `fix/demo-tasks-qa-r1-20261018` `b01e7ce` are product-equivalent to `8d869ff` (only public README text differs).\n")
    f.write("- `qa/google-native-asr-20261018` and the candidate are now ancestors of main; they are not separate branch tips to push.\n\n")
    f.write("### Remote divergence at fetch time\n\n")
    f.write("- `origin/main` was `164990f` (published 1.18 source snapshot). It is not an ancestor of the internal main; merge-base was `18de318`.\n")
    f.write("- The integration merged `origin/main` with `-s ours` to preserve the newer internal product tree while recording the published history. No remote-only file was discarded (remote tree is a subset plus older versions).\n")
    f.write("- Only `main` (and optionally the accepted candidate branch) should be pushed; no force, no branch deletion.\n\n")
    f.write("### Other late branches assessed (not merged)\n\n")
    f.write("After the accepted candidate, no other unmerged branch contains a newer completed product delivery with independent QA. "
            "The only recent alternatives are tree/patch equivalents already represented in main or in the accepted candidate:\n\n")
    f.write("- `test/lg233-readiness-20261018` `84c33c1` — same four product subtrees as `539e622`; no new code delta.\n")
    f.write("- `qa/demo-tasks-20261018` / `fix/demo-tasks-qa-r1-20261018` `b01e7ce` — product-equivalent to accepted `8d869ff`; only README public text differs.\n")
    f.write("- `feature/lg229-230-no-limits` `7c83abb` — Gitea/public-side copy of LG229/230; main already has the same behavior from `cd0e8c8`.\n")
    f.write("- Older feature/QA/integration branches (1.18 and earlier) are retained as history; their features are already in the 1.19/1.20/1.21/1.22 integration line, "
            "or they are failed/frozen ASR/reader experiments. They were not merged wholesale.\n\n")
    f.write("## 2. Full local branch table\n\n")
    f.write("Status `merged` means the tip is an ancestor of current main. For unmerged tips, `+/-` are `git cherry` counts; "
            "`code` is the number of changed files under backend/frontend/e2e/tests/build paths vs main. "
            "`-` in worktree means no worktree.\n\n")
    f.write("| # | branch | tip | date | status | +/− | code | worktree | category / recommendation |\n")
    f.write("|---:|---|---|---|---|---:|---:|---|---|\n")
    for i, r in enumerate(rows, 1):
        status = "merged" if r["merged"] else "unmerged"
        w = r["worktree"].replace("/home/yhvh/code/lightgravity-bot-worktrees/", "WT:")
        w = w.replace("/home/yhvh/code/lightgravity-bot/", "ROOT:")
        w = w.replace("/tmp/", "TMP:")
        w = w or "-"
        cherry = "-" if r["merged"] else f"+{r['plus']}/-{r['minus']}"
        f.write(f"| {i} | `{esc(r['branch'])}` | `{r['tip']}` | {r['date'][:16]} | {status} | {cherry} | {r['code_files'] if not r['merged'] else '-'} | `{esc(w)}` | {esc(r['category'])} |\n")
    f.write("\n## 3. Remote refs\n\n")
    f.write("| ref | tip | subject |\n|---|---|---|\n")
    for ref, tip, subj in remote:
        f.write(f"| `{ref}` | `{tip}` | {esc(subj)} |\n")
    f.write("\n## 4. Worktrees\n\n")
    f.write("Detached/branch worktrees are listed in `git worktree list`; no worktree was removed or cleaned by this inventory. "
            "The integration worktree for this task is `/home/yhvh/code/lightgravity-bot-worktrees/merge-gitea-20261018`.\n")

print(f"local={len(rows)} merged={merged_count} unmerged={len(unmerged)} remote={len(remote)}")
print("candidate unmerged:", [r['branch'] for r in unmerged if r['branch'] in CANDIDATE])
print("forbidden unmerged:", [r['branch'] for r in unmerged if r['branch'] in FORBIDDEN])
