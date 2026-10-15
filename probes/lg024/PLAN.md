---
title: "LG-024 阶段 A 计划与交接（首版交付文档与发布准备；不写共享 docs）"
doc_type: plan
category: engineering
task: "LG-024"
owner: "agent:pi-lg024"
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
updated: "2026-10-16"
---

# LG-024 阶段 A 计划（首版交付与发布准备）

> 本文件由 LG-024 owner 在**新建持久 worktree** `/home/yhvh/code/lightgravity-bot-worktrees/lg024`
> （branch `dev/lg024`，基于最终 main/claim commit）中落盘。**阶段 A 只做 probes/本地产物/许可/启动烟测草案**；
> **共享 docs（README、docs/06、PROJECT、agent、docs/08）由 `integrate/lg031-runtime` owner 独占，未释放前本包不写**。
> **LG-024 不提前 done**：验收条件要求 README/设计/规则与实际行为一致，须阶段 B 串行落地共享文档并绑定准确候选。

## 1. 目标（来自 LG-024 卡片）

- README/设计/规则与实际行为一致，安装启动/任务/资源/恢复入口清楚。
- 准备本地分发和演示材料，来源许可完整，未实现能力不宣传可用。
- 对外发布/部署只准备可审阅结果，不自动执行；资格与云端另行处理。

## 2. 阶段划分（依赖 runtime owner 释放共享 docs）

### 阶段 A（本 worktree 可做，**只写 probes/本地产物**）

- [ ] **许可清单**：`pyproject.toml` 运行/开发依赖许可；参考来源（Olav OS / Olav Tasks / Olav）commit 与许可；
      SDK `google-antigravity==0.1.22` 许可与来源。落 `probes/lg024/`.
- [ ] **安装/启动烟测草案**（可审阅，不部署）：`make`/`lightgravity start|status|stop|init` 入口命令、默认 loopback、token 内存握手、
      未实现能力标注；以**当前产品树**实际行为为准，不宣传未实现能力。
- [ ] **本地分发/演示素材草案**：介绍、范围（已验 vs 待 QA）、局限、可审阅产物索引。
- [ ] **入口清单草稿**：安装/启动/任务/资源/恢复入口，待阶段 B 写入 README。

### 阶段 B（**等待** `integrate/lg031-runtime` owner 释放共享 docs）

- [ ] 串行落地 README / docs/06 / 必要的 PROJECT·agent·docs/08 一致性（按届时实际候选与契约）。
- [ ] **绑定准确候选**：以阶段 B 开工时的 main 实际产品树 / 契约 / SDK 版本为准，不预设；不提前宣称。
- [ ] 完成 LG-024 验收条件后再由主代理决定 mark done。

## 3. 边界与保护

- **不写共享 docs**：README、docs/06、PROJECT、agent、docs/08 归 `integrate/lg031-runtime` owner。
- **不碰** `integrate/lg031-runtime` 的 branch / 文件 / index；不 kill 主工作区 uvicorn(:8123)；不复用其 dataRoot。
- 产品树本阶段**不改**；如确需产品改动须另派并明确 owner，不在本包混合。
- **不推送/不部署/不发布**；对外动作只准备可审阅结果。**本阶段产品真实生成 0**。
- 旧实验 / worktree / 原始 probes / 旧 dirty 全部保留，不 reset/clean/覆盖/重复 pick；敏感原件不入 repo。

## 4. 状态

- LG-024：`todo → in-progress`（原子 claim `agent:pi-lg024`）；阶段 A 未完成、不 done。
- LG-023：评估门内 `done`（见 `probes/batch-20261016/LG023-CLOSE-LG024-PREP.md`）。
- 契约 `1.10.0`、SDK `0.1.22`、自主模式默认 off 不变。
