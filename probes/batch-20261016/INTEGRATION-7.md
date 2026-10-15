---
title: "batch-20261016 第七批集成报告（LG-022 R2 持久停止/账本 + LG-031 R2 自主领取/共享计数整合）"
doc_type: report
category: engineering
updated: "2026-10-16"
---

# 第七批集成报告（唯一串行集成 owner）

唯一集成 owner（pi，现有 env DeepSeek，主代理只 PM，无嵌套派工/推送/部署/发布）。
本包只做**安全合并 + 最小共享装配兼容核对 + 契约/文档一致性 + 持久 QA/续接 worktree 准备 + 准确本地提交**；
**未运行产品真实模型/外部服务（本包产品调用 0）**，未推送/部署/发布，未 reset/clean/覆盖/重复 pick。

## 0. 基点与保护

- 集成前 `main` HEAD `29ffbb6`（`prep: record persistent worktree handoff…`），clean；主代理本轮无 PM dirty。
- 开工条件核对：无残留执行者占用两源 worktree（`ps` 仅见本集成 wrapper）。
  - `fix/lg022-r2` @ `e59e12a` clean（含 QA 复验 R1 证据合并 `f3da9fc`）。
  - `fix/lg031-r2` @ `3821620` clean。
- **保留**全部旧分支/worktree/probes/原始证据/dirty：`fix/lg031-r1` 原 dirty、`dev/lg031`、旧 QA 失败样本、
  `probes/batch-20261016/PERSISTENT-HANDOFF.md` 等全部保留。**未 reset/clean/整树覆盖/重复 pick/删 worktree**，未复制 `.env`。

## 1. 安全逐分支合并（`integrate/batch7`，自 `29ffbb6` 起）

| 来源 | 合并提交 | 结果 |
|---|---|---|
| `fix/lg022-r2@e59e12a` | `8a92439` | 无冲突；带入停止门真实停止事实、`reviewer_cleanup`、持久生成账本（契约 1.10.0）+ QA reverify R1 证据 |
| `fix/lg031-r2@3821620` | `0144eb7` | **2 处文本冲突**（见 §2），其余自动合并；带入自主 claim 时序修复、共享计数注入、能力匹配 |

- `git merge-base`：两者均自 `29ffbb6`（batch6 的 main 候选）。
- 冲突全为**两侧加性文本**，逐条保留并改写为一致语义（非整树覆盖）。

## 2. 冲突处理（唯一集成 owner）

### 2.1 `backend/lightgravity/adapter/__init__.py`
- 022 加 `configure_generation_ledger` export，031 用 `global_generation_counter`。两侧均为 proxy 导出。
- 解决：同时保留 `GenerationCounter`、`configure_generation_ledger`、`global_generation_counter`（import 与 `__all__` 各一份），
  去掉自动合并产生的重复 `GenerationCounter`。

### 2.2 `docs/08-interface-contract.md` §9
- 022 追加「持久生成账本（1.10.0）」，031 追加「实现接线（1.9.0）」。
- 解决：**保留 1.10 持久账本为唯一生成限额事实源**，把 031 说明改写为「执行器共享计数接线（`1.10.0`，LG-031 R2，无版本/字段/端点变化）」，
  明确默认装配在 `configure_generation_ledger` **之后**注入同一**持久**账本，不按 worker/session 重置、不回退非持久内存计数。
- 契约版本保持 **`1.10.0`**（031 未新增版本）；不机械升版。

## 3. 共享装配兼容核对（单一生成限额事实源）

- `api/bootstrap.py`：`build_runtime` 先 `configure_generation_ledger(settings.data_dir)`（022），
  再 `AntigravityExecutor(..., generation_budget=global_generation_counter())`（031）。
  两者顺序天然正确——031 注入的是**已被 022 换成持久账本**的全局计数，**不发生旧内存计数覆盖**。
- 真实进程内冒烟（`build_runtime(settings, wire_real_executor=True)`，本地替身，无真实模型）：
  `global_generation_counter().snapshot()` → `{'count':0,'limit':7,'remaining':7,'corrupt':False,'persistent':True}`；
  `reserve()` → `True`、`count` → `1`、`snapshot2` remaining 6；`<data_dir>/generation/` 账本文件已真实创建。
- 结论：**1.10 持久代际账本仍是唯一生成限额事实源**，031 的共享注入只是把同一持久计数接到每个 worker/reviewer proxy。

## 4. LG-031 实际修复保留（不被旧 dirty 覆盖）

- `coordinator/graph.py`：自主路径 claim 检查从**执行前**移到**执行后、revoke 前**；程序只授权该 worker 被排度节点
  （`node_not_scheduled_for_worker`）；`_mint_pool_grant`/`_claim_for_worker`/`_claim_tools_for` 完整并入。
- 此前在整合候选与原 base 均失败的
  `tests/collaboration/test_lg031_integration.py::test_autonomous_worker_tool_claim_grants_node` **现已通过**（本包实跑 1 passed）。
- 未读取旧 dirty `fix/lg031-r1` 覆盖当前；原 dirty 原样留存。

## 5. 集成检查（真实退出码，绑定 `0144eb7`）

| 检查 | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 后端类型 | `uv run mypy` | 0 | **Success: no issues found in 137 source files** |
| 后端全量 | `uv run python -m pytest -q` | 0 | **775 passed, 2 skipped**（79.7s） |
| 定向（adapter 预算/账本 + verify + coordinator + contracts + collaboration） | `uv run pytest tests/adapter/test_lg022_generation_budget.py tests/adapter/test_lg022_r2_generation_ledger.py tests/verify tests/coordinator tests/contracts tests/collaboration -q` | 0 | **274 passed** |
| 031 自主领取定向 | `pytest …::test_autonomous_worker_tool_claim_grants_node -q` | 0 | **1 passed**（原失败项已闭合） |

- 跳过 2 项为既有条件门（LG037 真实向量质量需显式授权、LG020 真实 DeepSeek 需显式 env），非本包回归。
- 相对于 LG-022 R2 自报基线（765 passed/5 skipped）与 LG-031 R2（子集 383 passed），本整合候选为 775/2。
- **本包产品真实模型/外部服务调用 0**（已有结果只引用不重跑）。
- **UI 未改**（本批无前端改动），未重复整套前端 type/test/build。

## 6. 独立 QA 与续接 worktree 准备（本包不执行 QA/真模型）

两个**全新持久 worktree**，均基于最终整合候选 `0144eb7`，开工前核对路径/分支不存在（先核不覆盖）：

| 用途 | 路径 | 分支 | HEAD |
|---|---|---|---|
| LG-022 独立复验 R2 | `/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-r2` | `qa/lg022-r2` | `0144eb7` |
| LG-031 续接 R3 | `/home/yhvh/code/lightgravity-bot-worktrees/lg031-r3` | `fix/lg031-r3` | `0144eb7` |

- 旧 `lg022-qa-r1`/`fix/lg022-r2`/`fix/lg031-r2`/`fix/lg031-r1` 等全部保留。
- **未执行 QA、未发真实模型请求、未接真模型**。

## 7. 任务状态（如实，不自判 022/031 验收通过）

- **LG-022**：`in-progress` —— R2 返修已并入整合候选；**待独立 QA（新 `qa/lg022-r2`）**，本包不自判 pass。
- **LG-031**：`in-progress` —— R2 已修复自主领取时序并实测到 partial；**真 2 worker+交接+候选 review 仍缺**（真实预算 10/10 用满），
  续接分支 `fix/lg031-r3` 已备；不 claim 依赖未过的 LG-023/032。
- **LG-023**：`todo`，未 claim（对照实验依赖）。
- **LG-032**：`todo`，未 claim（反依赖 LG-031 真实硬条件）。
- **LG-035 / LG-037**：保持 `in-progress`（质量门/端点不可达），不假 done。
- **LG-040 / LG-041**：`todo`，**不解锁**（依赖未过 / ASR 质量门）。
- backlog 专用根校验：`validate` → 41 tasks, no diagnostics；`digest` → **32 done / 4 in-progress / 5 todo**，complete=true。

## 8. 成本与历史账本（准确，不重置、不洗白）

- **LG-031 累计真实产品生成请求**：原包 1（reviewer）+ R1 3（2 worker + 1 reviewer）= 4；
  R2 单次运行 `GenerationCounter count=6/limit=6`（worker A 4 + worker B 发现 1 + reviewer 1）= 6；
  **累计 10 / 10，剩余 0**。主代理本 phase3 另行授权**最多 14**（新工程验证 phase），
  **合计上限 24**；此上限**不是** LG-032 的对照实验（032 反依赖 031 真实闭环，样本/基点/模型/预算/门需另定）。
- **LG-022 首轮 QA 实际真实总数 unknown**（代理曾 429 rerun，未证明在 10 次全局上限内）；
  **R1 新阶段 6/10**；**两轮失败记录都保留**（`probes/lg022/REPORT.md` 首轮 FAIL、`probes/lg022/reverify-r1/REPORT.md` R1 FAIL）。
- **本包实际产品请求 0**。
- 旧 031 交接日志 `turn_end=114` / model 响应 224 是**开发 pi 事件**，不计入产品请求。

## 9. 边界、未测与风险

- LG-022 停止门真实停止事实（`session_refs` 非空成功 Run → `awaiting_acceptance`）与账本跨**两次真实重启**计数：本包只做机制整合与进程内冒烟，**未在真实模型链/真实服务重启验证**，交 `qa/lg022-r2`。
- LG-031 真 2 worker 自主 claim + 带 hash 交接 + 完整候选 reviewer `passed`：**仍未闭合**，交 `fix/lg031-r3`（新预算内，不扩原 10）。
- 完整 checkpoint skip 仍未实现；`test_claims.py::test_two_owner_race…` 既有偶发竞争未改其已验收测试。
- 保留所有 stop/token/pin/证据授权/幂等/反重放边界；去中心化默认 off；1.9 归档/向量/检索/UI 语义未回退。
- `main` 未推送。

## 10. 分支与候选

| 用途 | 分支 | HEAD | 说明 |
|---|---|---|---|
| 整合候选 | `integrate/batch7` | 本提交 | `--no-ff` 合 022-r2 + 031-r2，共享装配核对 |
| 022 复验 | `qa/lg022-r2` | `0144eb7` | 基于整合候选；**未执行 QA** |
| 031 续接 | `fix/lg031-r3` | `0144eb7` | 基于整合候选；**未接真模型** |
| 旧 022 R2 | `fix/lg022-r2` | `e59e12a` | clean，未动 |
| 旧 031 R2 | `fix/lg031-r2` | `3821620` | clean，未动 |
| 旧 031 R1 | `fix/lg031-r1` | `af6640e`（dirty） | 原样保留 |

- 本包结束时先写持久 REPORT，再精确本地 commit；`main` 未推送。
