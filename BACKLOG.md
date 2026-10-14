---
title: "LightGravity Bot 开发任务入口"
doc_type: index
category: planning
updated: "2026-10-14"
---

# LightGravity Bot 开发任务入口

> 创建：2026-10-14。开发任务由 Olav Tasks 管理，schema 为 `olav.tasks/v1`，编号 LG。状态以单项 Markdown frontmatter 为准，本索引不重复维护状态。

本目录的任务是**开发 LightGravity Bot 的工作**，与未来产品的 Task/Run/Member 文件及 `lightgravity.bot/v1` 完全分开。

## 排期与执行原则

- [滚动排期](docs/06-roadmap.md)：按验收门推进，未承诺日历日期。
- P0：核心接口、SDK 风险与最小可操作闭环；P1：首版工作入口与设置、恢复和完整质量门。优先级不是权限，不代表依赖可跳过。
- 计划保持 todo；实际执行再 claim/更新状态。ready 是候选快照，不能作为任务已被领取或可自动后台执行的证据。
- 每项任务正文有验收与证据要求；未解决重要失败不置 done。

## A. 基础与探针

- [LG-001 冻结首版接口与状态契约](backlog/tasks/LG-001.md)
- [LG-002 建立可运行工程骨架](backlog/tasks/LG-002.md)
- [LG-003 验证 Antigravity SDK 核心能力](backlog/tasks/LG-003.md)
- [LG-004 实现 Markdown 事实源与可靠写入](backlog/tasks/LG-004.md)
- [LG-011 实现左侧导航与统一前端壳层](backlog/tasks/LG-011.md)

## B. 最小真实闭环

- [LG-005 实现角色与 SDK 资源配置编译](backlog/tasks/LG-005.md)
- [LG-006 实现 Antigravity Executor Adapter](backlog/tasks/LG-006.md)
- [LG-007 实现常驻消息路由与 Task 队列](backlog/tasks/LG-007.md)
- [LG-008 实现自动组队与依赖调度](backlog/tasks/LG-008.md)
- [LG-009 实现产物验证与人工验收](backlog/tasks/LG-009.md)
- [LG-010 验收最小真实开发闭环](backlog/tasks/LG-010.md)
- [LG-012 实现查询 API 与持久事件订阅](backlog/tasks/LG-012.md)

## C. 工作入口与设置

- [LG-025 实现模型设置与凭证后端接口](backlog/tasks/LG-025.md)
- [LG-026 实现底部 Settings 与模型接入页面](backlog/tasks/LG-026.md)
- [LG-013 接入 Task Chat 与真实看板](backlog/tasks/LG-013.md)
- [LG-014 实现 Files 与任务证据预览](backlog/tasks/LG-014.md)
- [LG-015 实现 Team 与 Resources 管理视图](backlog/tasks/LG-015.md)

## D. 恢复与质量

- [LG-016 实现暂停取消与中断恢复](backlog/tasks/LG-016.md)
- [LG-017 实现独立 QA 与有限返修](backlog/tasks/LG-017.md)
- [LG-018 实现隔离 worktree 与并行整合](backlog/tasks/LG-018.md)
- [LG-019 完善网页通知与断线重连](backlog/tasks/LG-019.md)
- [LG-020 实现启动检查与本地分发入口](backlog/tasks/LG-020.md)

## E. 首版验收

- [LG-027 验收模型设置与凭证生命周期](backlog/tasks/LG-027.md)
- [LG-021 完成前端状态与响应式验收](backlog/tasks/LG-021.md)
- [LG-022 执行首版端到端与故障验收](backlog/tasks/LG-022.md)
- [LG-023 完成单 agent 对照评估](backlog/tasks/LG-023.md)
- [LG-024 整理首版交付文档与发布准备](backlog/tasks/LG-024.md)

## CLI

当前机器 PATH 未发现 olav-tasks，可使用已存在的本地构建，不为本次规划安装包：

```bash
node /home/yhvh/code/olav-tasks/dist/cli.js tasks list /home/yhvh/code/lightgravity-bot --json
node /home/yhvh/code/olav-tasks/dist/cli.js tasks ready /home/yhvh/code/lightgravity-bot --json
node /home/yhvh/code/olav-tasks/dist/cli.js tasks digest /home/yhvh/code/lightgravity-bot --json
node /home/yhvh/code/olav-tasks/dist/cli.js tasks validate /home/yhvh/code/lightgravity-bot --json
```

绝对路径是当前开发环境入口，不是产品运行依赖。其他环境使用已安装的 `olav-tasks` 执行同等命令。
