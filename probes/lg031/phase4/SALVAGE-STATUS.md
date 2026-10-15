---
title: "LG-031 phase4 — SALVAGE-STATUS（同次运行证据恢复完成，硬条件 4 闭合）"
doc_type: status
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg031-r3"
branch: "fix/lg031-r3"
base: "8073830"
---

# LG-031 phase4 — SALVAGE-STATUS

owner：`agent:pi-lg031-r3`（pi + env DeepSeek；主代理只 PM）。分支 `fix/lg031-r3` @ `8073830`（clean）。

## 状态

**恢复完成 · 硬条件 4 已闭合 · LG-031 可据真实单次运行证据进入 `done`（待 LG-032 独立 QA）**。
本包 **新增真实模型调用 0**；未重跑真实 fixture；未写回原 store；原始证据字节保留。

## 关键事实

- **同一次运行** `run_01M5079F4W8V37RHRTN7W6WWV6` / `task_01M5079F4WRHPVMVHGM1NS7FK9` 的
  **SDK session DB（3 个）与原 stdout 存活**，`sha256` 与恢复 JSON **逐一相符**。
- **真实交接原文已复原**（产品构建的 verify 节点 prompt，`Upstream artifacts:` 块）：
  `subtask_01M5079F7MS9XM6AJRDJD4D7HM@1a6053…a64d:out/deliver.txt` 及带
  `@sha256:820a554a…` 的 diff 证据引用。
- **离线 hash 核对**：diff patch `@sha256:820a554a…` 重算 **match=true**（69B）。
- **授权**：源/目标节点均 `fence=1`、程序原子授权、脱敏（`sandbox_set_has_secret=false`）。
- **reviewer**：真实 1 次，`outcome=passed`、`validated=passed`、`findings=[]`、usage `unknown`。

## 硬条件核对（真实证据）

| # | 条件 | 结果 | 真实依据 |
|---|---|---|---|
| 1 | ≥2 真实 SDK worker、隔离 worktree | ✅ | 2 worker session；候选 worktree `/tmp/tmp839xikyn/workspaces/candidate-ws` |
| 2 | worker 自主 discovery→申请原子授权 | ✅ | 4 条 `discover_and_request_claim`；router `GraphDispatcher._claim_for_worker` |
| 3 | 程序验证并原子授权 + lease/fencing | ✅ | 源/目标 `granted, fence=1`，receipt 脱敏 |
| 4 | 受控带 hash 同伴交接 | ✅ **本恢复闭合** | 版本化 ref + 独立 `@sha256:820a…` 离线匹配 |
| 5 | 完整候选独立 ModelReviewer + 机器门 | ✅ | 真实 1 次；`passed`/`validated=passed`；候选完整 |
| 6 | 默认关闭/回退、身份程序注入、无全局 token | ✅ | `sandbox_set_has_secret=false`；默认关闭路径保留 |
| 7 | Task 预算含 review/repair/failures | ✅ | 持久账本 `count=10/limit=16`；usage `unknown` 不当 0 |

## 缺口（诚实，不伪造）

- 同 run 的 `data/`/`store`/`worktrees` 因探针 `TemporaryDirectory` 被删（**取证保全缺口**）。
- `content_hash 1a6053…a64d` 的**原始字节**（`SUBTASK.md`）随临时目录删除：值可作**已记录事实**复原，
  **不能**离线重算；**非伪造**，且**不削弱**硬条件 4（ref 已承载版本/hash）。
- 未来 probe 须**持久运行目录 + 关闭 auto-clean**（不重跑旧写入）。

## 计数与边界

- 真实调用：本包 **0**；全局已知累计 **34/40**（旧 24 + phase4 10，不重放、不归零）。
- 未 push/deploy/发布；产品不改；未碰 022、主集成者、8123、旧 dirty/worktree。
- 未降低任何复核/机器门/停止/验收门；未改契约、未删断言。

## 结论

硬条件 1–7 **按 docs08 冻结契约在真实单次运行证据上全部成立**。据此可将 LG-031 更新为
**`done`（待 LG-032 独立集中 QA 复验版本级行为）**，**不制造待 032 循环**。详见 `SALVAGE-REPORT.md`。
