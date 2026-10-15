---
title: "LG-024 阶段 B：协作候选 integrate/lg031-runtime 单列记录（不并入本包）"
doc_type: note
category: engineering
task: "LG-024"
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
updated: "2026-10-16"
---

# 协作候选 `integrate/lg031-runtime@afcae82`（单列待版本 QA）

> **本记录仅归档候选状态，不把候选并入 LG-024 交付包。**
> 本 L0 包**只绑定已通过首版核心稳定 product tree `e0a8cec` / `main 66b2b10`**。
> 未来若需集成该候选，**另产新候选并单独版本 QA**；**不偷把本包改称最新协作已验版**。

## 1. 事实（实测，只读）

| 项 | 值 |
|---|---|
| worktree / branch | `lg031-runtime` / `integrate/lg031-runtime` |
| HEAD | `afcae82`（clean） |
| HEAD 提交标题 | `integrate(lg031-runtime): two-phase SDK lifecycle + program-frozen lease owner + F2 grant auth` |
| 前序 | `c4d4e87`（merge F2 `fix/lg029-auth` WIP，unverified）、`111667d`（merge F1 `fix/lg031-pool` 候选池机制） |
| 是否已合 `main` | **否**（`main` = `66b2b10`，候选基于更早 main，含 cohort2 等中间提交） |
| `git diff main afcae82` 产品路径 | 9 文件改动、**+2342 / -44**（`adapter/execution.py`、`api/app.py`、`api/bootstrap.py`、`api/collaboration.py`、`api/context.py`、`collaboration/execution_grant.py`、`coordinator/graph.py` + 2 测试） |
| `docs/08-interface-contract.md` | 候选相对 main 有 +11/-4 改动（属该 owner 的 docs/08 归属） |
| 状态 | **未合 main；独立 QA R1 进行中**（本包不参与该 QA） |

## 2. 为什么单列（不并入 LG-024 包）

- LG-024 **只依赖 LG-022 / LG-023**（均已 `done`），**不依赖 LG-031 协作线**，**不机械等待 LG-032**。
- 该候选**未合 main、独立 QA 未完成**：将其并入会把「未验协作实现」混入「首版核心稳定包」，违反「绑定已通过首版核心稳定树」。
- 该候选改动集中在协作/去中心化路径（`coordinator/graph.py`、`collaboration/*`、`api/collaboration.py`），与首版核心使用流程（Chat/交付 Task/Files/Resources）无必需依赖。

## 3. 后续处理（不由本包代行）

- 该候选的版本 QA → 返修 → 集成由**其独立 QA 与主代理串行收拢**决定。
- 若将来集成，需**另出新的 L0 候选包**并**重新绑定当时真实 product tree**；本包及其 sha256/manifest **不随之改称**。
- **本包不做 merge / push / deploy / upload / publish**。
