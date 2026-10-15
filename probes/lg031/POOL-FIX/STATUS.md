---
title: "LG-031 POOL-FIX — STATUS（多候选自主选择实施）"
doc_type: status
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg031"
branch: "fix/lg031-pool"
base: "834b262"
---

# LG-031 POOL-FIX — STATUS

owner：`agent:pi-lg031`（pi + env DeepSeek；主代理只 PM；无嵌套派工/推送/部署/发布）。
worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg031-pool`（branch `fix/lg031-pool`，基点 `834b262`）。
产品真实 DeepSeek 生成请求：**0**。

## 状态

**机制实现完成 + 离线验证通过；LG-031 保持 `in-progress`**（真实双 worker SDK 自主多候选/隔离绑定未闭合，
待 PM 单独冻结真实证明 phase）。默认 off / 旧确定性路径与旧单节点自主路径**完全保留、可回退**。

## 变更（owner 范围）

- `backend/lightgravity/collaboration/execution_grant.py`
- `backend/lightgravity/adapter/execution.py`
- `backend/lightgravity/coordinator/graph.py`
- `backend/lightgravity/api/bootstrap.py`（装配开关；未改 api/collaboration.py 与其它 api 源）
- `tests/collaboration/test_lg031_pool_selection.py`（新增 9 项）
- `probes/lg031/POOL-FIX/**`
- `docs/08-interface-contract.md`（§6.5 加性实现说明，无版本变化）
- `backlog/tasks/LG-031.md`（POOL-FIX 记录）

## 检查（真实退出码）

- `uv run mypy` → **Success, 137 files**。
- `uv run pytest tests/collaboration -q -p no:randomly` → **77 passed**（既有）。
- `uv run pytest tests/collaboration/test_lg031_pool_selection.py -q` → **9 passed**（新增）。
- `uv run pytest tests/collaboration tests/coordinator tests/adapter tests/settings tests/api -q` → **409 passed**。
- 探针 `probes/lg031/POOL-FIX/probe_pool_selection.py`：真 4 进程竞争同 node → **1 granted / 3 held_by_other /
  fence=1**；非首项选择 granted 且 binding 指向所选 node；越池拒绝；loser 领取剩余候选；无 claim 不写；脱敏。

## 未测 / 限制

- 真实 SDK 双 worker 端到端**未做**；会话按所选 node 绑定隔离 workspace 的两阶段适配**未实现**。
- 完整 checkpoint skip 未实现；LG-032 集中 QA 与成本对比未做。
