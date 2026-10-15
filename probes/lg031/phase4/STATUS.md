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

**in-progress**（phase4 进行中）。目标：先零模型定位 phase3 失败点 + 最小修复离线先证，
再做**一次**完整真实产品闭环 attempt（一个固定 fixture，含其所有 stage/role）。

## 真实调用计数（单一事实源，不重置、不猜）

- 旧累计（前三阶段）：原包 1 + R1 3 + R2 6 + phase3 14 = **24**（保留为失败/partial 成本）。
- 本 phase4 批准新增上限：**16**；全局已知工程累计上限：**40**。
- 已用（本 phase4）：**0 / 16**（离线阶段，尚无真实转发）。
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
- [x] 持久 PLAN/STATUS/LEDGER/OFFLINE-GATES 已写
- [ ] 精确本地 commit（离线阶段）
- [ ] §B 一次完整真实产品闭环 attempt
- [ ] REPORT / 证据 / LEDGER（真实行）
- [ ] 精确本地 commit

## 未达成（诚实，不伪称）

- 尚无真实转发；phase4 真实硬条件未做。
- phase3 硬条件 4/5 仍未闭合（integrate worker 未自主 claim+写、无带 hash 交接、无完整候选 `passed`）。
- 完整 checkpoint skip 仍未实现（沿用既有边界，本包不夸大）。
- LG-032 独立集中 QA 与全生命周期成本对比**不在本包**。
- **LG-031 保持 `in-progress`**；真实门未齐前不宣称 done，也不制造待 032 的循环。

## 边界

默认关闭/旧确定性回退保留；身份只由程序冻结注入；worker 无全局 token；过期≠停止；
旧 fence 不可写；未知副作用 `recovery_required` 不重放；实际停止后才回收权限。
未 push/deploy/发布；未改 sources/vectors/frontend；未碰 022 worktree 与旧 dirty；
未碰主目录集成者；与 core 独立 QA 的 0 请求补证互相隔离。
