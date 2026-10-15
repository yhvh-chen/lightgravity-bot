---
title: "LG-023 未来对照 cohort 协议草稿（需 PM 预注册后才生效）"
doc_type: experiment-protocol-draft
category: engineering
status: draft-awaiting-pm-preregistration
audit_id: lg023-method-audit-20261016
updated: "2026-10-16"
owner: "agent:pi-lg023-method-audit"
---

# LG-023 未来对照 cohort 协议草稿

> **本文件是草稿，不是已冻结协议。** 只有在 **PM 书面预注册预算/样本/门**、且本 harness 经离线自检后，
> 才可在**首个新真实请求之前**冻结。**旧 45/48 为 protocol-deviation 失败成本，不入本 cohort 账本。**

## 0. 与旧 cohort 的关键差异（修复项）

| 项 | 旧 cohort（缺陷） | 未来 cohort（修复） |
|---|---|---|
| 冻结后改动 | 采样中改提示/工具集 | **冻结后不得改任何提示/工具/测试/样本/预算**；错误则整 cohort 停止 |
| attempt 数 | S1/A 多次重跑 | **恰 4 attempts，每个 1 次正式 run** |
| 输出 | 覆盖 `runs/<s>__<arm>/` | **不可变 attempt-id 目录，只创建不覆盖** |
| 计量 | guard 生产 `count=0` | 每 attempt 12 **在真实转发前**强制；全 stage 单持久 ledger |
| 存储 | `TemporaryDirectory` 删关键运行 | **项目旁持久目录**承载 SoT/worktree/diff |
| accept 门 | 旧 `_accept` 未接 confirmer | **完整 Coordinator 装配 + 真实 stopgate** |

## 1. 样本与 arm（沿用，双方完全相同）

- S1 independent（两文件独立修复）；S2 interface（跨模块依赖交接）。
- arm A：1 个计划写节点（单 worker）；arm B：2 个依赖写节点（双 worker + 带 hash 交接）。
- 两 arm 相同：初始 Git tree、需求文本、机器门、独立 reviewer、版本验收门、模型、预算、工具、提示模板。
- **唯一自变量 = 计划写节点数**。冻结合法 plan **只用于比较计划写节点数**，不冒称自动规划能力。

## 2. 预算（数值由 PM 预注册；此处为占位）

- 总真实生成上限 **T**、每 attempt 上限 **P**（P 需 ≥ 双 worker + reviewer 一条链的真实所需；依据前 cohort
  真实链约 10 生成 + 观察到的 tool-call 上限）。
- **全 stage 单一持久 ledger**；转发前扣减；超限/损坏 fail-closed，绝不当 0。
- output ≤ 16000/请求；HTTP 120s；retry 0；并发 ≤ 2。

## 3. 计量守卫（必须离线证明真实接线）

- 有界 guard 装在**全局 `GenerationCounter`**（并 `_GLOBAL_GENERATION_COUNTER=counter`），
  使 worker 与 reviewer 的 `LocalAuthProxy.begin_call()→reserve()` 都受同一 attempt 上限；
  **返回 `bool`**（不是 `.granted`）。
- 离线证明：真实 `LocalAuthProxy` + 本地 fake SSE upstream；旧 wiring 复现 `count=0`，新 wiring 13th 转发前 429。
  见 `harness/offline_repro.py` A8。

## 4. 停止门 / 验收（完整装配）

- 走真实 `build_runtime(...)` / `create_app(...)`：Task → 真 worker → 真异步 reviewer → `verifying`
  → 真实 `VerificationService.verify_and_prepare`（stopgate 由 `executor.confirm_stopped` 确认）
  → `awaiting_acceptance` → `decide(accept)` 绑定 requirements/candidate/plan-hash。
- **不预填 `cleanup=done`、不删 refs、不造 confirmed、不跳 SDK 停门。**
- 参考已通过装配：`qa/lg022-stream/harness/main_chain.py`。
- 离线证明（fake executor + 真 GraphDispatcher + 真 stopgate）：teardown 齐 → `awaiting_acceptance`；
  缺 → `unconfirmed`。见 `harness/offline_repro.py` A7。

## 5. 持久化与输出

- `phase data_dir`、候选 worktree、SDK 资料、Run/Task/Subtask SoT 全部放**项目旁持久目录**。
- 每 attempt 输出 `runs/<attempt-id>/`（创建即不可变）；失败/bring-up 也保留。
- 记录每 attempt：完成率、首轮通过率、全周期 elapsed、执行/QA/返修/复验/失败请求数、
  input/cache/output/usage/cost（缺失 `unknown` 不为 0）、人工干预。

## 6. 结论口径

- 样本小/单模型/强制计划 ⇒ 不声称统计显著性；不对未知 gain 作正面选择性结论。
- 未完成样本不计已交付成本；不用失败中位数推益。
- 旧 45 明确为 protocol-deviation 失败成本，单列、不并入、不洗 0。
