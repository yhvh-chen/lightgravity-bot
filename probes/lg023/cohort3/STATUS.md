---
title: "LG-023 cohort-3 方法修复/正式评估 STATUS"
doc_type: status
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg023-cohort3"
---

# LG-023 cohort-3 STATUS

- Owner：`agent:pi-lg023-cohort3`（新独立 pi 上下文；**非** cohort-1 owner、**非** cohort-2 owner、
  **非** 方法审计 owner；主代理只 PM；无嵌套派工/推送/部署/发布）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg023-cohort2`（本包在该 worktree 内新建分支
  `eval/lg023-cohort3`；cohort-2 分支 `eval/lg023-cohort2@1d6d45c` 及其全部目录/原件**完整保留、未 reset/clean/覆盖**）。
- 本包目录：`probes/lg023/cohort3/**`（唯一 owner 写入范围；产品/共享 docs **只读**）。
- 产品快照：沿用已通过核心产品树 `e0a8cec`（契约 `1.10.0`）；**不拉取** F1/F2/pool 中途改动。
- SDK `google-antigravity==0.1.22`；模型 `deepseek-v4-flash`。
- **本包先零模型修复 + 硬门验证；真实 DeepSeek 生成 0 直到硬门全绿。**

## 进度

- [x] 核 worktree/claim/dirty（clean）、main 基点、产品只读边界、旧原件保留。
- [x] 读 AGENTS/agent、LG023、cohort2/{PLAN,STATUS,REPORT}、evidence/cohort2-D1、METHOD-AUDIT、qa/lg022-stream 装配。
- [x] 建 `eval/lg023-cohort3` 与 `probes/lg023/cohort3/**`（cohort2 目录完整保留）。
- [ ] 增量记录 D1 + 旧 45+4 已知成本（本文件 + REPORT §成本）。
- [ ] **修 driver**：全串行 attempt 用**同一 phase `settings.data_dir`**（`PHASE_DATA_DIR`），让产品
      `configure_generation_ledger(settings.data_dir)` 自然续读同一账本；每 attempt 独立 Task/Run/workspace，
      不再把 `data_dir` 随 attempt 换。**不**在 build_runtime 前重复设同一 env、**不**改产品源。
- [ ] 硬门：真 `build_runtime`/`create_app` 启动链，**≥2 次顺序 runtime 启动**，真 `LocalAuthProxy` + 本地 fake 上游，
      worker+reviewer 实际转发都落**单 phase 物理路径**且跨启动累加、同 cap 总/attempt 超限转发前拒绝、损坏 fail-closed。
- [ ] 断言 runtime 诊断 ledger 路径 / realcounter 对象 / 物理 JSONL 与冻结路径一致，**FIRST FORMAL REQUEST 之前**核对。
- [ ] dry 与 formal 同一代码路径（只换受控上游/基目录），dry 不跳过 bootstrap。
- [ ] hash 写定 PLAN/代码/配置提交后才正式采样（4 attempts）。

## 真实生成计数（防洗数，不归零）

| 阶段 | 真实生成请求 | 状态 |
|---|---|---|
| 旧 LG-023 cohort 1（`dev/lg023`） | **45/48** | protocol-deviation 失败成本，单列 |
| LG-023 cohort 2（`eval/lg023-cohort2@1d6d45c`） | **4**（attempt 1：worker 3 + reviewer 1） | **STOPPED**（harness 计量缺陷 D1），单列 |
| 旧 LG-022 | unknown+6+8+5/10 | 单列 |
| 旧 LG-031 | 34/40 | 单列 |
| **本 cohort-3** | **0（进行中；硬门未绿前不发实时请求）** | 未开始 |

- 旧 45+4 保留为已知失败/方法成本，**不清零、不并入**本 cohort-3 新账本。
- 已知 eval 真实生成实际上限 **97**（45 + 4 + 48）。

## 关键设置

- 唯一自变量 = 计划写节点数（A=1，B=2 依赖）。
- 旧程序调度路径 / 新自主开关 **off**；workspace 隔离两 arm **一致关闭**。
- **全 stage 单一持久 phase ledger**（`<worktree 旁>/lg023-cohort3-data/generation/`，limit 48）；每 attempt ≤12，
  **转发前**硬限；跨 attempt 续读同一账本。
- 真 `build_runtime`/`create_app`/Coordinator/Graph/VerificationService + 真实 stopgate（`confirm_stopped`）。
- 4 attempts、每个 1 次；不可变 attempt-id 输出 + 一次性 guard；harness/断言/装配/计量错误 → **整 cohort 停止**。
