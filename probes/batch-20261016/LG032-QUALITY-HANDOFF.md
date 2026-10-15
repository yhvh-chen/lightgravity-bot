---
title: "LG-032 质量验收交接（排期与阶段划分）"
doc_type: handoff
category: engineering
task: "LG-032"
owner: "agent:pi-lg032"
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
updated: "2026-10-16"
---

# LG-032 质量验收交接

> 本文件由主代理（只 PM，无嵌套派工/推送/部署/发布）在 **阶段 A 开工前** 落盘，用于把 LG-032 的范围、
> 依赖判定、两阶段门与预算边界交接给持久 worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg032`
> （branch `qa/lg032`）中的执行者。**本包产品真实生成 0**：未运行产品代码/测试、未执行 QA、未跑真实模型。

## 1. 开工事实（真实核对）

- 主工作区 `main@03c7db6` **clean**。
- `dev/lg023@fa9401d`、`fix/lg023-method@fa9401d` 均 clean；**LG-023 方法审计独立 worktree 本包未触碰**。
- backlog 专用根：`validate` → `OK 41 tasks, no diagnostics`；`digest` → complete=true；`ready` → **LG-032**。
- `/home/yhvh/code/lightgravity-bot-worktrees/lg032` 开工前**不存在**；创建前已核，不覆盖。
- 契约 **`1.10.0`**、SDK **`google-antigravity==0.1.22`**、自主模式**默认 off** 未改。

## 2. 依赖判定（不机械等 LG-023）

- LG-032 `depends_on: [LG-031, LG-022]`，二者**均已 `done`**（LG-022 门内 done；LG-031 done 待 032）。
- **LG-032 不依赖 LG-023**。两者是**不同评估**：
  - LG-023 = 单 agent vs 组队**实施 worker** 的开发对照（受控代码样本、单模型）。
  - LG-032 = 去中心化**版本 QA** + **程序调度基线 vs 新协作路径**的全生命周期成本对比。
  - **032 不重用 023 的对照数据**。
- **LG-024 `depends_on: [LG-022, LG-023]` 仍 `todo`**，因 023 未完成评估而等待；与本包无关，本包**不解锁 024**。

## 3. LG-023 状态如实（保持 in-progress）

首 cohort **45/48** 真实生成后发生**预算冻结**；已确认三项：

1. **提示/工具在 bring-up 中被变更**（worker 提示修正 + 加 `edit-file`）。
2. **样本结果被新 attempt 覆盖**（早前 S1/A 结果被最终 attempt 覆盖）。
3. **版本验收 stopgate 未闭合**（`cleanup='pending'`，两 arm 共有）。

组队 arm 与 S2 未在最终 harness 下取得可比结果。**新方法审计只做 0 真实生成**，**不合并未经完成的
`fa9401d` 评估记录、不解锁 024**。详见 `backlog/tasks/LG-023.md`、worktree `fix/lg023-method` 的
`probes/lg023/{REPORT,STATUS}.md`（本包不修改其内容）。

## 4. 两阶段划分（**先 A，不提前跑成本样本**）

### 阶段 A — 独立机制/语义质量 QA（产品真实生成 0）

- 执行者须**独立于实施者**（031 实施者不得自审）；经 pi 派出。
- 覆盖：竞争领取、原子授权与 fence、过期租约、崩溃恢复、取消、权限/身份、带 hash 交接、
  有界返修与复验、默认关闭回退、事件可重放 / 重启不重复副作用。
- 证据用**只读/离线/替身**，**不运行产品生成样本**，**不预注册成本样本、不预设节省**。
- 发现阻断须**另行派返修后复验**（QA 不自修、不自判 done）。

### 阶段 B — 全生命周期成本对照（**另行冻结，且必须先验证 harness**）

- **前置**：阶段 A 机制/语义**无阻断**后，PM **另行冻结**固定样本/次数/费用上限与成功门。
- **先验证实验 harness**：起点/任务/模型/预算/验收门/重复策略一致；单一持久 ledger 全 stage 共用、
  跨重启不归零、损坏**绝不当 0**、**转发前持久预留**、usage 未知记 `unknown`（不当 0）。
- 比较**程序调度基线 vs 新协作路径**；逐样本记录成功率、耗时、执行+QA+返修+复验+失败尝试 token、人工介入。
- **未完成样本不计作已交付成本**。
- **旧 LG-023 混淆数据不能代替本对照**（提示/工具变更 + 结果覆盖，臂间不可比）。
- 只有**质量不退化且结果支持收益**才建议默认启用；否则保留可选开关/回退并记录结论，**不以投入成本强行宣布成功**。

## 5. 预算与运行边界（本轮草案，采样前另行冻结）

- 阶段 A 产品真实生成 **0**。
- 阶段 B 派工/运行上限草案：**wall 400s / maxround 100 / noncache 100k / idle 120s / retry 0**。
- **样本与费用上限仍须阶段 B 另行冻结**；不预先宣称节省，不据 023 结果改额。
- 契约 `1.10.0`、SDK `0.1.22`、自主模式默认 off 不动；不扩状态。

## 6. claim / worktree

- backlog 根 `validate`/`digest`/`ready` 确认 complete、无诊断后，CLI **原子 claim
  `LG-032 --as agent:pi-lg032`**（不绕 claim）。
- 全新持久 worktree `/home/yhvh/code/lightgravity-bot-worktrees/lg032`（branch **`qa/lg032`**），
  基于最终 main/claim commit。
- 保留全部旧 dirty/worktrees/probes；**不 reset/clean/重复 pick**；LG-023 方法审计 worktree 不碰。

## 7. 本轮交付边界

本主代理包只更新 `tasks`/git relation/PM 文档并落盘本交接报告；**不运行产品代码/测试、不执行 QA、
不跑真实模型、不推送/部署/发布**。
