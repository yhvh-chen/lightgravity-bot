---
title: "LightGravity Bot"
doc_type: overview
category: project
updated: "2026-10-14"
---

# LightGravity Bot

> 更新：2026-10-14。设计与 27 项首版开发任务已落盘，尚未实现、部署或完成运行验证。

**按需组队的 AI 任务助手。**

LightGravity Bot 接收问题和目标：简单问答直接处理，需要交付时创建任务并按需组队，执行、验证、保存成果；进入待验收时释放临时队伍，常驻服务继续等待指令。

长期定位是通用 AI 助手，首版聚焦开发任务：在一个明确的项目工作区里完成小型代码修改，留下代码差异、检查结果与交付说明。

## 为什么重新设计

LightGravity Bot 从 Olav OS 的使用经验中重新设计更小的产品。保留文件即事实源、对话管理项目、任务依赖、人机决策和可复核交付的思想，避免为了复用代码而连带引入完整组织系统、历史运行时和兼容逻辑。

它不是先复制一套 Olav OS 再裁剪，也不预设旧底座为运行依赖。组件是否移植，要根据实际依赖、许可证和维护成本决定。现有技术债的具体范围仍需调查，不能把重写天然视为更便宜。

## 用户入口

| 视图 | 用户用途 |
|---|---|
| Chat | 提出目标、补充信息、查看汇报、作出决定 |
| Board | 查看任务依赖、执行情况、验证结果与阻塞 |
| Files | 查看输入资料、工作成果和验收证据，上传与下载文件 |
| Team | 查看待招募角色和当前 Task／Run 的已招募成员 |
| Resources | 管理 Connections、Session Profiles、Hooks、MCP、Tools、Triggers 与 Skills |
| Settings | 底部齿轮入口，接入模型、管理凭证、测试连接和设置默认模型 |

五个工作入口采用 Olav OS 风格的固定左侧窄图标导航，底部另放 Settings；上方不再放一级 tabs。Agent 合并到 Team，其他配置集中到 Resources。Settings 与 Connections 使用同一份配置，不维护重复模型列表。顶栏显示任务范围、面板开关与通知。

Task 是主要操作入口：一项任务一个目录、一份 TASK.md、一条用户对话历史。工作视图围绕同一任务展示，Resources 提供共享配置与任务实际引用；Project 是可选的共享背景，Run 是内部执行尝试。

任务、角色及 SDK 资源采用 Markdown＋YAML frontmatter 描述与渲染，程序校验后编译为 SDK 配置。日志与 SDK 会话保持各自格式，不重复保存当前业务状态。

## 文档入口

- 项目开发技能位于 `.agents/skills/`：已安装 Olav Tasks 的 6 个技能，来源版本与文件哈希见 [.agents/skills/olav-tasks-source.json](.agents/skills/olav-tasks-source.json)，许可证见 [.agents/skills/OLAV-TASKS-LICENSE](.agents/skills/OLAV-TASKS-LICENSE)。
- [开发约束](agent.md)：项目范围、架构、SDK 接入、状态写入、验证与交付规则；[AGENTS.md](AGENTS.md) 提供自动发现入口。
- [前端约束](design.md)：视觉 tokens、左侧多栏布局、组件、页面交互、响应式与浏览器验收。
- [开发看板](BACKLOG.md)：27 项首版开发任务，使用 `olav.tasks/v1` 管理。
- [滚动排期](docs/06-roadmap.md)：阶段、依赖、验收门与当前未定的日历安排。
- [模型设置](docs/07-settings-and-models.md)：Settings、Connection 事实源、凭证、分层测试和默认模型。
- [项目手册](PROJECT.md)：目标、优先级、完成定义和已确认决策。
- [产品与架构设计](docs/01-design.md)：调度器、executor、组队、文件事实源、状态与首版交付顺序。
- [Task 与 SDK 资源契约](docs/02-task-and-sdk-resources.md)：任务目录、对话、frontmatter 渲染及 Agent／Connections／Conversation／Hooks／MCP／Tools／Triggers 的映射。
- [SDK 能力审计](docs/03-sdk-capability-audit.md)：核心能力覆盖矩阵、frontmatter 配置块、运行时边界及首版取舍。
- [Bot 行为契约](docs/04-bot-behavior.md)：消息路由、轻任务、队列、需求变更、通知、暂停取消、待验收与资源释放。
- [左侧导航、Team 与 Resources](docs/05-navigation-and-team.md)：四栏壳层、五个一级入口、招募视图、SDK 资源管理及关联导航。

## 首版边界

- 一个占用执行槽的交付 Run，其他 Task 可以排队；最多三个 worker、两个并行子任务、一轮自动返修，待运行验证后调整。已停止的待用户或待验收 Run 不占槽。
- 首个执行后端采用 Antigravity SDK，保留 adapter 边界，不同时实现多个 SDK。
- agency-agents 作为候选角色内容来源，从少量开发角色开始。
- 使用 SDK 原生 skills 加载与基础文件、命令、网页工具；按成员绑定角色、技能、工具权限与工作区，不重建通用技能执行层。源码能力已核对，真实运行待验证。
- 临时角色实例随运行创建和释放，项目与产物长期保存。
- 人工最终验收；worker 自报完成只能进入待验证。
- 单用户本地网页入口，简单问答不组队；后台执行独立于浏览器连接，支持 Task 队列与网页未读通知。云端入口、外部聊天渠道和自主触发另行推进。
- 先实现必要的文件树、预览、上传、下载和任务产物关联。

## 参考与参赛边界

- [Antigravity SDK](https://github.com/google-antigravity/antigravity-sdk-python)：执行与会话基础，接口、平台支持和云端运行须实测。
- [agency-agents](https://github.com/msitarzewski/agency-agents)：候选角色模板，不能替代调度与执行系统。
- [Olav OS](../olav-os/)：编排与工作台设计参考，不是本项目已确定的运行依赖。
- [Olav Tasks](../olav-tasks/)：Markdown 项目管理、看板和聊天集成参考，不是本项目已确定的运行依赖。

本项目首先按产品目标推进，不以参赛资格作为已确认事实。AI Builder Cup FAQ 明确限制赛前已有项目及基于已有项目的提交；未公开、新建目录、重新命名或重写实现均不能自动证明合格。复用既有代码、角色或其他资产的允许范围，应取得主办方明确答复。[官方 FAQ](https://aibuildercup.com/Faqs.html)
