# LG-018 progress (persistent checkpoint)

- Task: LG-018 隔离 worktree 与并行整合
- Worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg018 (branch dev/lg018)
- Base commit: 141809daf8552fd43371baccd5d3f95697e955d0
- Runner: pi + DeepSeek (deepseek-v4-flash), no nested dispatch, no push/deploy.
- Owner files: backend/lightgravity/workspaces/**, coordinator/graph.py,
  tests/probes/lg018. NOT touched: service.py / verify / api/tasks.py (LG-017),
  api/app.py / frontend (LG-019), shared docs08/README/PROJECT/PROGRESS.

## Result: implementation complete (pending version QA)

1. [done] Read AGENTS/agent/PROJECT/PROGRESS/BACKLOG/docs06/08/09, LG-018 task.
2. [done] backend/lightgravity/workspaces: git.py (hook-free allow-list runner),
   manager.py (real worktrees, frozen base commit, integrate, conflict pause,
   retention/cleanup, path/symlink/.git rejection), provider.py (dispatcher seam).
3. [done] GraphDispatcher wiring: additive `workspaces=` param; write nodes get
   isolated worktree workspace_path in the real ExecuteRequest; `_writer_key`
   allows 2 isolated writers in parallel; un-isolated stays serial.
4. [done] Real-git tests (tests/workspaces, 14 passed): parallel isolation,
   non-conflicting/conflicting integration, dirty HEAD preserved, stop lock,
   recovery retention, hooks/secret-env/.git/symlink boundaries, dispatcher
   parallel-wiring test.
5. [done] mypy clean (95 files); full pytest 496 passed, 4 skipped; targeted
   coordinator+control 139 passed.
6. [done] probes/lg018/INTEGRATION.md for api/bootstrap.py assembly point.
7. [done] Real-git probe passed=true, evidence JSON written.
8. [done] Commit, report, task marked done pending version QA.

## Evidence
- probes/lg018/reports/LG-018-report.md
- probes/lg018/INTEGRATION.md
- probes/lg018/evidence/lg018-worktree-evidence.json
- tests/workspaces/** (14 real-git tests)

## Notes
- Model calls this package: 0 (real SDK left to LG-022).
- Default remains conservative: no provider => serial writes; max_parallel not raised.
- Commit: see git log for dev/lg018.
