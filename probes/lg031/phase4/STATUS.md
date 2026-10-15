---
title: "LG-031 phase4 — STATUS（持久，实时）"
doc_type: status
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg031-r3"
branch: "fix/lg031-r3"
base: "faacb90"
---

# LG-031 phase4 — STATUS

owner：`agent:pi-lg031-r3`（pi + env DeepSeek；主代理只 PM）。分支 `fix/lg031-r3` @ 基点 `faacb90`。

## 状态

**partial / in-progress**。零模型定位 phase3 失败点 + 加性最小修复已离线先证（硬门全绿），
并用真实产品 `RuleBasedPlanner` 路径跑了**一次**完整真实闭环 attempt：dispatcher `succeeded`、
2 个真实 SDK worker 各自自主 claim、真实独立 ModelReviewer + 机器门 `passed`/`passed`、候选完整。
但**真实 handoff 原文未被探针捕获**（提取 bug），且 16 上限内（已用 10）**未重跑**补证 ⇒
**硬条件 4 的真实原文证据缺失**，诚实 partial，不写 done。

## 真实调用计数（单一事实源，不重置、不猜）

- 旧累计（前三阶段）：原包 1 + R1 3 + R2 6 + phase3 14 = **24**（保留为失败/partial 成本）。
- 本 phase4 批准新增上限：**16**；全局已知工程累计上限：**40**。
- 已用（本 phase4）：**10 / 16**（一次真实 attempt；worker ≈9 + reviewer 1）；剩余 6。
- 全局已知工程累计：24 + 10 = **34 / 40**。
- 持久账本固定路径：`probes/lg031/phase4/ledger/generation/`
  （env `LIGHTGRAVITY_GENERATION_LEDGER_DIR`），转发前持久预留、跨进程/重启、损坏绝不当 0。
- 每请求输出 ≤12000 tokens；单 HTTP ≤120s；并发 ≤2；SDK/API retry 0；usage 未知记 unknown。

## 步骤进度

- [x] 核 HEAD/clean/dirty/旧资源（HEAD `faacb90` clean；旧 24 已核；uvicorn 8123 非本包不触碰）
- [x] 写 phase4 PLAN/STATUS/LEDGER 与旧成本
- [x] §A 零模型 forensics：定位 phase3 真实失败点（见 PLAN §A；两类 per-worker 上限，
      run1 `MAX_MODEL_CALLS_EXCEEDED`、run2/3 proxy 429；integrate worker 从未调度）
- [x] §A 必要最小修复（adapter 上限对齐 + fixture prompt 收敛）+ 离线先证
      （`backend/lightgravity/adapter/executor.py`；`tests/adapter/test_lg031_r3_generation_ceiling_alignment.py` 5 项）
- [x] 离线硬门 1–7 全绿（全 stage 硬限 / 两 worker 权限 / objective 明确 / 依赖交接 /
      真实 bootstrap & Graph 配置 / 产品路径闭环 / 上限对齐）——证据 `OFFLINE-GATES.md`
- [x] 精确本地 commit（离线阶段 `75e1487`）
- [x] §B 一次完整真实产品闭环 attempt（10/16；dispatcher succeeded；reviewer passed）
- [x] REPORT / 证据 / LEDGER（真实行）
- [ ] 精确本地 commit（真实阶段）

## 真实硬条件达成（本 phase4）

| # | 条件 | 结果 |
|---|---|---|
| 1 | ≥2 真实 SDK worker | ✅ 2（deliver 写 + verify 只读）；deliver 在独立真实 worktree |
| 2 | worker 自主 discovery→申请原子授权 claim | ✅ 真实 4 条工具调用，产品 router `GraphDispatcher._claim_for_worker` |
| 3 | 程序验证并原子授权 + lease/fencing | ✅ fence=1、脱敏（离线回归断言无 token） |
| 4 | 受控带 hash 同伴交接 | ⚠️ **真实已发生但原文未捕获**（探针 bug）；离线机制已证 |
| 5 | 完整候选独立 ModelReviewer + 机器门 | ✅ 真实 `passed`/`validated=passed`，候选可复源 |
| 6 | 默认关闭/回退、身份程序注入、无全局 token | ✅ |
| 7 | Task 预算含 review/repair/failures | ✅ 单一持久账本 10/16；usage 未知不 0 |

## 未达成（诚实，不伪称）

- **硬条件 4 的真实 handoff 原文未捕获**（探针提取 bug；产品交接已发生、离线机制已证）。
  一次完整复验需 ≈10 转发，本包剩余 6，**不重跑同一 fixture**。
- phase3 的硬条件 4/5 已在本 phase4 实质改善（dependent worker 已真实自主 claim 运行、真实候选
  `passed`）；仅手条件 4 的真实字符串证据仍缺。
- 完整 checkpoint skip 仍未实现（沿用既有边界，本包不夸大）。
- LG-032 独立集中 QA 与全生命周期成本对比**不在本包**。
- ~~**LG-031 保持 `in-progress`**~~ → **已由同次运行证据恢复取代**（见 `SALVAGE-REPORT.md`/`SALVAGE-STATUS.md`）：
  硬条件 4 的真实交接原文已从存活 SDK session DB 只读复原并离线 hash 核对（match=true），**新增真实调用 0**；
  **硬条件 1–7 真实成立，LG-031 更新为 `done`（待 LG-032 独立集中 QA）**，不制造待 032 循环。

## 边界

默认关闭/旧确定性回退保留；身份只由程序冻结注入；worker 无全局 token；过期≠停止；
旧 fence 不可写；未知副作用 `recovery_required` 不重放；实际停止后才回收权限。
未 push/deploy/发布；未改 sources/vectors/frontend；未碰 022 worktree 与旧 dirty；
未碰主目录集成者；与 core 独立 QA 的 0 请求补证互相隔离。
