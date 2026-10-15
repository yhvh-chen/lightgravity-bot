# LG-022 第 1 轮返修（REFIX-R1）— STATUS

- Task：LG-022「执行首版端到端与故障验收」第 1 轮返修（D1/D2/D3）。
- Owner：本包 LG-022 返修 owner（pi + 既有 env DeepSeek）；主代理只 PM。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-r1`（branch `fix/lg022-r1`）。
- 基点：main `ca27160`（LG-022 QA merge `8e81089` 之后；LG-041 PMdirty 保留在 root main）。
- 独立 QA 证据：`probes/lg022/REPORT.md`（候选 `bf7851c`，fail；D1/D2 阻断、D3 诚实性）。

状态：**in-progress（返修自检完成，待新的独立复验 QA）**。本包不宣称版本通过。

## 进度日志（逐条追加）

- [T0] 受控 owner 交接完成：读取 AGENTS/agent/PROJECT/PROGRESS/docs06/08、LG-017/016/022、
  qa/lg022 的 probes/REPORT/QA-PLAN/evidence、SDK/现有源码必要范围。
  只读核验 LG-031 R1 wrapper（`bounded-26vw_kwk`，PID 1741666/1741667）处于 assistant-pending、无 inflight 工具；
  在安全边界向其唯一 PID SIGINT，确认其自有进程组退出、无残留。031 dirty 原样保留；tracked diff/untracked/
  wrapper 日志备份至受保护 checkpoint。**本包真实产品模型调用 0。**
- [T0] 合并 `qa/lg022@8e81089`（仅 QA 证据/任务记录）到 main，精确保留 LG-041 PMdirty；建持久
  `fix/lg022-r1` worktree 基于主线最新整合候选。
- [T1] 落盘本 STATUS + `R1-PLAN.md`（先写计划再实现）。
- [T2] 实现 D1（`_run_coro_sync` 私有 loop/工作线程）、D2（`ReviewLifecycle` + `_pending_auto_verify`/`_auto_verify_async` + control 复核停确认/两步停位 + `verifying`/`repairing → recovery_required`）、
  D3（成功 Run 不写 `fail_reason`）、全局生成计数（`GenerationCounter` 转发前计数 + `GET /api/v1/diagnostics/generation`）。
- [T2] 契约 1.7.0 → 1.8.0 加性 MINOR：constants + docs08 + README/agent/docs06/PROJECT + contracts 断言。
- [T3] 新增测试与确定性探针（0 真实模型调用）：`tests/verify/test_verify_review_lifecycle.py`、
  `tests/coordinator/test_lg022_review_lifecycle.py`、`tests/adapter/test_lg022_generation_budget.py`、`tests/api/test_health.py` diagnostics 回归、
  `probes/lg022/harness/r1_review_lifecycle_probe.py` → `probes/lg022/evidence/r1-review-lifecycle.json`。
- [T3] 检查：完整后端 `pytest -q` **706 passed, 4 skipped**（73.9s，退出码 0）；相关子集 444 passed；6 个改动文件 `mypy` clean。
- [T4] 落盘 `R1-REPORT.md`（含 D1/D2/D3 修复、真实/替身声明、未测清单、031 handoff 绝对路径与调用计数、剩余预算/复验计数器用法）。
- [T4] 精确本地 commit（不含未知/秘密文件）；LG-031 dirty/checkpoint 原样未合并；LG-022 保持 in-progress 待独立 QA。

## 结论速览

- D1/D2/D3 + 全局生成计数：**已实现并本地自检通过（替身/确定性证据，真实模型调用 0）**。
- 真实 DeepSeek running-loop 端到端：**未测**，留独立复验。
- 旧 QA 真实请求数：**unknown**（单列，不 reset 成本）。
- 详见 `R1-REPORT.md`。
