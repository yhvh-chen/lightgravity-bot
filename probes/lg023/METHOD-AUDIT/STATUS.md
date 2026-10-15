---
title: "LG-023 实验方法审计与 harness 返修 STATUS"
doc_type: status
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg023-method-audit"
---

# LG-023 方法审计与 harness 返修 STATUS

- Owner：`agent:pi-lg023-method-audit`（新独立 pi 上下文；**非**前 LG023 操作者；主代理只 PM；无嵌套派工/推送/部署/发布）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg023-method`（branch `fix/lg023-method`），base `fa9401d`。
- 前 owner worktree `lg023`（`dev/lg023@fa9401d`）：**保留、未 reset/clean/覆盖**；审计后仍 clean。
- **真实产品/DeepSeek 生成：0**（不跑旧/新真实 fixture，不消耗剩余 3，不新建 ledger）。
- 产品代码 `backend/**`：**只读**，未改。

## 进度

- [x] 核当前数据/进程/dirty/全部 worktree；确认前 owner 退出且 `lg023` clean。
- [x] 读 AGENTS/agent、LG023 原文、`probes/lg023/{PLAN,STATUS,REPORT}`、原始 runs/evidence/ledger、
      CORE-QA-CLOSE、LG-023 backlog、docs06、qa/lg022-stream 已通过装配。
- [x] 创建全新 worktree `lg023-method`（`fix/lg023-method`，基于 `fa9401d`；旧分支/worktree 全保留）。
- [x] 保全/恢复旧原件：17 个真实 SDK session DB + 恢复的 per-generation usage + owner dispatch 转录，
      私有持久化并 hash/cmp 验证（`~/.cache/.../lg023-survivors/`）。
- [x] 完成 A1–A9 审计并落证据：`METHOD-AUDIT/evidence/*.json`。
- [x] 修 harness 而非产品：离线复现证明 stopgate 本身正确，`_accept` 接线在记录结果后补上且**从未真实运行**。
- [x] 修计量守卫：离线用**真实 proxy + 本地 fake upstream**证明旧 guard 生产 `count=0`（缺陷复现）+
      新 wiring 在转发前强制每 attempt 12、reviewer 共享全局账本。
- [x] 未来协议草稿 + 离线自检。
- [ ] **未来真实 cohort**：需 PM 先预注册 budget/样本 PLAN（本包不执行）。

## 真实生成计数（防洗数，不归零）

| 阶段 | 真实生成请求 | 状态 |
|---|---|---|
| 旧 LG-023 cohort（`dev/lg023@fa9401d`） | **45/48**（旧 ledger 可核总数；逐 attempt 归因不可信） | **全部保留为 protocol-deviation 失败成本** |
| 本审计包（`fix/lg023-method`） | **0** | 纯离线；不消耗剩余 3 |

- 旧 022（unknown+6+8+5/10）与 031（34/40）单列、不并入、不洗 0。**未新建 ledger，未复用旧 phase 48**。

## 关键判定速览（详见 REPORT）

- 旧 cohort **不能称“冻结正式对照完成”**：A1（冻结后改提示/工具集）、A2（S1/A 反复真实重跑）、
  A3（S1/A 结果路径被覆盖）、A4（逐 attempt 归因不可信）。
- **stopgate 不是产品 bug**：离线同型号 fake-session executor + 真 `GraphDispatcher` + 真
  `StoreResourceStopper` 在 teardown 事实齐时**到达 `awaiting_acceptance`**；旧记录 `unconfirmed`
  来自 harness 在用**无 confirmer 的旧 `_accept`** 时记录，`executor=` 接线此后才加且未真实运行。
- **计量缺陷已复现**：旧 guard 的 `count=0` 是 `bool` 上取 `.granted` 的真实 bug；新 wiring 正确。
- 两 arm 起始 commit hash 不同但 **tree（内容）相同**；原 commit 对象随 `TemporaryDirectory` 丢失，
  「同初始版本」在**内容层**成立、在**原 commit 对象层**记 `unknown`。
- 恢复真实 usage：17 个 session DB 的 per-generation token 计数已恢复（补旧 `unknown` 一部分）。
