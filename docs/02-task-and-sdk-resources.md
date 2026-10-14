---
title: "Task 与 SDK 资源契约"
doc_type: specification
category: architecture
updated: "2026-10-14"
---

# Task 与 SDK 资源契约

> 日期：2026-10-14。性质：设计。本文 frontmatter 是 LightGravity Bot 拟定义的应用格式，不是 Antigravity SDK 原生配置格式，也不是现有 Olav Tasks 契约。

## 1. Task 是主要入口

用户创建或继续 Task；Bot 在一次 Run 中拆成 Subtask 并派发。一个 Task 一个目录、一份权威 TASK.md、一条用户对话历史。Project 可选，负责共享规则、资料与代码仓库归属；Run 是内部尝试，不要求用户先创建它。

全局 Chat 收到新交付需求时创建 Task 并进入 Task Chat；普通问答、只读资料解释和状态查询不强制创建任务。消息路由见 [Bot 行为契约](04-bot-behavior.md)。任务卡、历史列表和文件树均能打开同一个 Task。直接指定 Task 目录时，程序解析 TASK.md 的稳定 ID 和根目录，读取必要输入、近期对话和运行摘要。

补充消息、返修和恢复保留 Task ID。需求发生实质变化时增加任务版本并使受影响验收失效；已验收任务继续工作需显式重新打开，保留旧交付版本，不能悄悄覆盖 done 的含义。不同任务的对话默认不合并，共享资料通过引用获得。

## 2. Markdown＋frontmatter 的边界

人需要阅读与管理的实体采用 Markdown＋YAML frontmatter：Task、Subtask、Run、Plan、临时成员与 SDK 资源。frontmatter 保存可校验字段，正文保存工作说明、指令、决策与验收条件。

只识别受支持的 `schema` 和 `kind`，普通 Markdown 仍作为文档预览。Markdown 渲染不能执行脚本、导入模块或启动进程。只有显式启动任务或启用已授权触发器后，程序才把有效描述编译成 SDK 配置。

消息和事件采用 JSONL；SDK session 保留原生格式用于恢复。两者不是重复的任务状态库。外部文件编辑需要校验，控制字段变更不能因为文件改了就立即产生执行或扩大权限。

解析建议使用安全 YAML、拒绝重复键和不支持的 schema，检查稳定 ID、类型、引用、循环依赖及路径范围。更新保留未知字段和正文，使用版本检查和原子替换；扩展字段可以保留，但不自动取得执行语义。无效资源显示诊断，不静默转换为可执行配置。

## 3. Task 示例与状态

以下仅为说明，不创建真实任务或宣称有实现结果：

```yaml
---
schema: lightgravity.bot/v1
kind: task
id: TASK-001
title: "为示例网站增加登录功能"
status: todo
phase: intake
revision: 1
requirements_revision: 1
project_ref: null
repository_ref: null
agent_ref: coordinator
depends_on: []
active_run: null
queue:
  state: not_queued
  order: null
  queued_at: null
archived: false
acceptance:
  status: pending
  deliverable_revision: null
  evidence_refs: []
budget:
  max_workers: 3
  max_parallel: 2
  max_repair_rounds: 1
---
```

正文建议包含目标、范围、输入、验收条件和交付要求。字段 `revision` 表示文件写入版本；`requirements_revision` 只在目标、范围或验收条件发生实质变化时增加。验收绑定 `deliverable_revision` 及其需求版本、候选产物和证据，状态写入导致 revision 增加不能自动使验收失效。

Task 的 `status` 使用 `todo/in-progress/done`；`phase` 表示 intake、queued、waiting_dependencies、planning、recruiting、executing、verifying、repairing、waiting_user、pausing、paused、cancelling、awaiting_acceptance、recovery_required、failed、cancelled 或 completed 等细节。只有人工验收通过置为 done；失败/取消的已启动任务保留 in-progress 并记录阶段，允许用户重试或归档。未启动任务取消可以保持 todo；归档与完成是不同字段，不把失败任务伪装成 done。

Board 和活动统计按 phase、有效执行租约及实际停止结果计算，不能把所有 in-progress 都算作活跃执行。队列与验收版本在 TASK.md 唯一维护；队列索引、待验收通知均引用它，不建立第二份状态。合法组合、暂停取消与恢复语义见 docs/04。

Subtask、Run、Member 使用各自 schema 的状态枚举，不强迫所有实体复用同一状态机。若接入 Olav Tasks，需做显式格式转换；本文件不能宣称其 CLI 已支持 `lightgravity.bot/v1`。

计划只在 PLAN.md 声明目标、任务引用、角色与约束；每个 Subtask 的依赖、状态、分配与验收条件以 SUBTASK.md 为权威，计划不重复维护第二份任务图。执行前固定计划和各子任务版本，运行中的修改走协调器。

## 4. 目录与对话

```text
bot-data/
├── resources/
│   ├── agents/<agent-id>.md
│   ├── connections/<connection-id>.md
│   ├── conversations/<profile-id>.md
│   ├── hooks/<hook-id>.md
│   ├── mcp/<server-id>.md
│   ├── tools/<tool-id>.md
│   ├── triggers/<trigger-id>.md
│   └── skills/<skill-id>/SKILL.md
├── projects/<project-id>/PROJECT.md
└── tasks/<task-id>/
    ├── TASK.md
    ├── conversation.jsonl
    ├── inputs/
    ├── artifacts/
    ├── deliverables/
    └── runs/<run-id>/
        ├── RUN.md
        ├── PLAN.md
        ├── team/<member-id>.md
        ├── subtasks/<subtask-id>/
        │   ├── SUBTASK.md
        │   └── outcome.md
        ├── events.jsonl
        ├── sdk/<member-id>/
        └── summary.md
```

Project 和 Task 都可引用经过授权的共享技能目录；原设计 `.lightgravity/skills/` 可作为项目资源位置，但 adapter 必须显式解析，不能假设 SDK 自动发现。本目录布局是候选约定，现阶段未创建运行实例。

用户对话属于 Task，成员 SDK 会话属于 Run/Member。SDK 原生会话恢复与用户对话呈现是两种用途，不能把渲染出的聊天文字视为可完整恢复 SDK 的原生状态。记录会话标识、后端、配置版本与存储引用，恢复能力必须实测。

Task 目录承载资料与证据；代码工作区采用关联仓库与隔离 worktree，不复制整个 Project。最终交付记录仓库基准与候选提交/diff。进入目录对话不自动授权读取整个父目录。

## 5. SDK 模块的资源映射

七类模块纳入一套资源描述与渲染机制，不为每类建立复杂管理系统。

| 模块 | Markdown 描述什么 | adapter/程序职责 | 界面展示 |
|---|---|---|---|
| Agent | 角色入口、指令、connection、skills、工具、策略与预算引用 | 构建配置并创建 SDK Agent | 角色卡、有效能力与健康状态 |
| Connections | 已实现的后端 adapter、模型和认证引用 | 选择传输与后端，连接检查 | 后端、模型、可用性 |
| Conversation | 会话配置、上下文/存储策略；实例记录会话引用 | 绑定 Task 用户对话与 Member SDK session，恢复验证 | 主对话、成员会话与执行详情 |
| Hooks | 已注册生命周期回调、策略与参数 | 挂载获准回调、处理工具许可与事件 | 生效策略、暂停原因与记录 |
| MCP | stdio/HTTP 连接、工具选择与凭证引用 | 建立 MCP 连接、解析可用工具、释放进程/连接 | 服务状态、工具清单 |
| Tools | 内置工具或已注册 Python callable 的描述 | 绑定真实函数、校验输入与授权 | 能力清单、调用结果 |
| Triggers | 显式启用的事件/时间规则、作用域与动作 | 注册触发、去重、进入任务队列 | 规则、下次执行、最近事件 |

这些是 LightGravity Bot 配置层的职责划分；SDK 原生类型和具体参数以固定安装版本为准。[官方 SDK](https://github.com/google-antigravity/antigravity-sdk-python)

资源通用字段建议包含 `schema`、`kind`、`id`、`title`、`enabled` 和 `revision`。秘密只保存 `credential_ref`，真实值从环境或凭证存储解析；渲染界面不展示解析后的秘密。

模型接入与 credential_ref 管理由底部 Settings 完成，Resources → Connections 读取同一文件并导航到设置编辑；默认连接引用保存 SETTINGS.md，不复制 Connection 参数。具体后端、表单与秘密存储边界见 [模型设置](07-settings-and-models.md)。其他资源仍通过受控对话修改。

七类模块之外的模型、结构化输出、预算、重试、压缩、观测、多模态及委派等能力，作为资源配置块与运行操作管理，完整映射见 [SDK 能力审计](03-sdk-capability-audit.md)。不把所有 SDK 对象都拆成新的管理模块。

### Agent 示例

```yaml
---
schema: lightgravity.bot/v1
kind: agent
id: developer
title: "开发者"
enabled: true
revision: 1
connection_ref: antigravity-primary
conversation_ref: task-worker
skills:
  source: paths
  refs: [implementation, test-report]
tool_refs: [view-file, create-file, edit-file, run-checks]
hook_refs: [task-policy, execution-events]
mcp_refs: []
trigger_refs: []
---
```

正文保存角色指令。标识都是应用资源引用，并非 SDK 工具名称；首版通过受控映射转换。Agent 统一使用 `skills.source/refs`，不再提供平行的 skill_refs 字段；Member 的 skillRefs 是解析后的运行记录，与模板字段用途不同。招募后的 Member 保存最终解析配置与引用哈希，模板后续修改不静默改变正在执行的成员。

### Connections 与 Conversation

Connections 不意味着首版实现全部传输后端，只注册已经验证的 Antigravity adapter；更换后端须检查工具、会话和能力是否兼容。

Conversation 资源是配置模板，不是另一份聊天日志。SDK 的 `conversation_id`、`save_dir` 和 continuation 等源码配置说明其存在会话/存储接口，但不能据此承诺任意中断都可恢复。[配置源码](https://github.com/google-antigravity/antigravity-sdk-python/blob/main/google/antigravity/connections/connection.py)

### Hooks、Tools 与 MCP

Hooks 可承担工具调用策略、事件记录和必要的用户确认。程序注册具体 handler，Markdown 只引用 handler ID 与有效参数，不执行正文或任意 import 路径。不可省略的基线策略由程序施加，资源文件不能悄悄移除。

Tools 区分 SDK builtin、获准的 in-process callable 与 MCP 工具；MCP 连接描述单独保存。资源描述存在不等于工具已安装或具备权限。命令工具与 stdio MCP 能执行进程，应限定部署允许的命令/参数；runtime 权限仍由实际隔离环境落实。

### Triggers

首版默认不启用自主后台触发；先提供描述、解析与展示边界。需启用时明确定义作用域、输入、去重键、预算、目标 Task 或任务创建规则。

外部 webhook、文件事件和长期定时可靠性由 Bot 入口及任务队列处理，不假定 SDK session 内的 TriggerRunner 是持久调度服务。队伍解散后 session trigger 结束；持续有效的触发由常驻服务管理，进入相同任务领取流程，不能绕过并发与验收规则。[SDK trigger 示例](https://github.com/google-antigravity/antigravity-sdk-python/blob/main/examples/getting_started/triggers.py)

## 6. 配置到运行的流程

1. 解析获准目录中的 frontmatter，按 schema/kind 校验。
2. 解析资源引用，检查路径、已注册 handler/adapter、工具与凭证引用。
3. 结合 Task 约束和运行基线，计算最终权限与预算；模板请求不能扩大 Task 授权。
4. 固定资源版本与技能哈希，生成运行配置。
5. 将本地技能路径、工具函数、策略、MCP 与触发器映射为 SDK 对象。
6. 建立 session，记录可观察事件与真实产物。
7. 验证后保存结果，释放成员；持久触发配置不随队伍一起删除。

SDK 自带子 agent/workflow 不得与外部 Scheduler 同时不受控地派发同一工作。首版外部 Scheduler 管理 Subtask；SDK 内部委派默认关闭或显式纳入同一预算与事件范围，具体开关待版本验证。

## 7. 渲染与验收

统一 renderer 按 kind 选择模板：Task 卡片与详情、Agent 角色卡、Connection/MCP 健康卡、Hook/Tool 能力卡、Trigger 规则卡、Run 执行详情。Agent 模板归 Team 待招募，Member 实例归已招募；Connections、Session Profiles、Hooks、MCP、Tools、Triggers、Skills 归 Resources。Conversation 配置模板和用户/成员真实会话分别管理。正文用 Markdown 渲染，引用转为可导航的资源链接。首版以读取和展示为主，配置修改由对话调用校验写入接口，暂不为每类资源建设复杂表单。布局与关联规则见 [导航设计](05-navigation-and-team.md)。

需要验证：

- 新 Task 能从目录、历史列表与看板打开同一对话，返修跨 Run 保留历史。
- Task/Subtask/Run 当前状态只有一份权威文件，无重复 JSON 状态；索引可重建。
- 未知 schema、无效引用与冲突修改可见，不触发静默执行。
- frontmatter 描述能映射到实际 SDK 配置；获准 skills、tools、hooks 与 MCP 在探针中真实生效。
- Trigger 默认不自行运行；启用后可去重、取消，并遵守相同任务预算和领取约束。
- 用户对话可显示，SDK 会话能否恢复按真实测试报告结论。

本文没有创建真实任务、资源实例、定时任务或后台服务。实现与部署另行推进。
