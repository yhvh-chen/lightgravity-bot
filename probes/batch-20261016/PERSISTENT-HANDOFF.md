---
title: "batch-20261016 持久目录迁移交接（lg022-qa-r1 / lg031-r2）"
doc_type: report
category: engineering
updated: "2026-10-16"
---

# 持久目录迁移交接（受控 worktree 隔离准备）

本包为**受控隔离准备**（pi，现有 env DeepSeek；主代理只 PM，无嵌套派工/推送/部署/发布）。
**只做 Git metadata / 持久目录迁移 / 简短管理报告**：不编写产品、不运行模型/测试/安装，
**产品真实调用 0**。

## 0. 前置核对

- 第六批集成进程已结束：`ps` 核对无残留执行者；本包只见到自身 wrapper。
- `main` HEAD 迁移前后均为 `03cc4b882f7a3847451822401d79523e2d5121ae`（`batch6: record main
  candidate HEAD 62ec7e4 in INTEGRATION-6`），未动。
- 参考报告：第六批 `probes/batch-20261016/INTEGRATION-6.md`；LG-031 交接证据
  `probes/lg031/{INTEGRATION.md,REPORT.md,STATUS.md}` 与 `probes/lg031/r1_worker_claim_probe.json`。
- 两准备 worktree 开工前均**无本包以外执行者**使用：无进程 cwd 落于其上，`lsof` 无打开文件。
- 开工前实际 HEAD/dirty：
  - `/tmp/lg022-qa-r1-prep` @ `ec2420e`（`qa/lg022-r1`），clean（tracked+untracked），tracked 2726，ignored 0。
  - `/tmp/lg031-r2-prep` @ `38e257a`（`fix/lg031-r2`），clean（tracked+untracked），tracked 2728，ignored 5030。

## 1. 迁移结果（目标为项目旁持久目录）

`git worktree move` 因 `/tmp` 与 `/home` **跨设备**（`Invalid cross-device link`）失败；改用
**等价安全流程**：`mv` 原目录（保留全部 tracked/untracked/ignored 与文件模式）→
`git worktree repair` 修正 gitdir 元数据（**未复制整树、未 reset/clean、未删旧 worktree**）。

| 工作区 | 新路径 | 分支 | HEAD |
|---|---|---|---|
| LG-022 R1 独立复验 | `/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-r1` | `qa/lg022-r1` | `ec2420e` |
| LG-031 续接 R2 | `/home/yhvh/code/lightgravity-bot-worktrees/lg031-r2` | `fix/lg031-r2` | `38e257a` |

旧 `/tmp/lg022-qa-r1-prep`、`/tmp/lg031-r2-prep` 已不存在（被 mv 到新路径，非删除）。

### 迁移前后一致性核对（原样保全）

- `lg022-qa-r1`：HEAD `ec2420e` / branch `refs/heads/qa/lg022-r1`；tracked 2726；untracked 0；
  ignored 0；`git status --porcelain` 空（clean）。**与迁移前一致。**
- `lg031-r2`：HEAD `38e257a` / branch `refs/heads/fix/lg031-r2`；tracked 2728；untracked 0；
  ignored 5030；`git status --porcelain` 空（clean）。**与迁移前一致。**
- gitdir 元数据已由 `git worktree repair` 修正（原 `lg022-qa-r1-prep` / `lg031-r2-prep` 目录名不变，
  仅内部 `gitdir` 指向新路径）。

## 2. base / claim / WIP 保全

- `qa/lg022-r1` base = 父提交 `17abd78`（`integrate/batch6`）；`git merge-base` 与 main 为 `17abd78`。
- `fix/lg031-r2` 为 `1981db8` 之上的精确 WIP commit（`38e257a`）；`git merge-base` 与 main 为 `17abd78`。
- **022 原 claim 保持** `assignee: agent:pi-lg022`（`backlog/tasks/LG-022.md`，`in-progress`，本包未改）。
- **031 原 claim 保持** `assignee: agent:pi-lg031`（`backlog/tasks/LG-031.md`，`in-progress`，本包未改）。
- **原始 WIP 保全**：旧 `fix/lg031-r1` @ `af6640e` **原样 dirty 保留**（4 个 tracked 修改 +
  4 个 untracked `probes/lg031/R1-*`），本包**未触碰**。旧 `/tmp` 其它 worktree（`lightgravity-worktrees/*`
  含 lg003…lg027、experiments 等）一律未动。

## 3. 交付/交接状态（可直接派发）

- **LG-022 独立复验**：在新持久路径
  `/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-r1`，分支 `qa/lg022-r1` @ `ec2420e`
  （基于整合候选 `17abd78`），clean。脚手架 `probes/lg022/reverify-r1/{PLAN,STATUS}.md`；
  待非实施者复验 D1/D2/D3 + 真实链 + 全局请求计数。**未执行复验，未发真实请求。**
- **LG-031 续接**：在新持久路径
  `/home/yhvh/code/lightgravity-bot-worktrees/lg031-r2`，分支 `fix/lg031-r2` @ `38e257a`
  （基于 `17abd78`），clean。真实产品调用累计 **4/10（剩 ≤ 6）**；
  已知未闭合：`tests/collaboration/test_lg031_integration.py::test_autonomous_worker_tool_claim_grants_node`
  在整合候选与原 R1 base 上均失败（`plan_validation failed: config_invalid`，R1 自身未完成项，
  非整合回归）。**本包未运行任何测试/模型，未重放未知 031 动作。**

## 4. 边界与说明

- 无 `.env` 复制；未安装依赖、未 `uv sync`。若执行者需依赖修复，**由执行者自行 `uv sync`**，本包不包装。
- `lg031-r2` 的 ignored 项（`.venv/`、`__pycache__/`、`.pytest_cache/`）随 mv 原样保留（5030 项），
  系迁移前既有状态，本包未创建/删除/重建。
- **精确本地提交仅此 PM 报告**（`probes/batch-20261016/PERSISTENT-HANDOFF.md`）；其余 dirty
  一律原样保留、归属原 owner（未纳入本提交）。
- 未改任何产品或其它包证据；未推送/部署/发布；未按名字广泛 kill；未自动重放任何测试/模型调用。
- 真实产品调用：**0**。成本：**unknown 单列**。
