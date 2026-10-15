---
title: "左侧导航、Team 与 Resources 视图设计"
doc_type: design
category: frontend
updated: "2026-10-15"
---

# 左侧导航、Team 与 Resources 视图设计

> 日期：2026-10-14。阶段：设计。用户要求主要入口采用 Olav OS 风格的左侧导航，取代上方一级 tab。当前仓库没有已实现网页，本次确定布局与交互契约。

## 1. 布局依据与范围

参考 Olav OS 的固定窄图标栏、资源栏、主内容区和 Agent 对话栏。保留 LightGravity Bot 的单用户、Task 主入口和临时团队设计，不引入组织、岗位和长期员工系统。

参考：[Olav OS 四栏反馈](../../olav-os/ideas/ce/20260926-workbench-four-pane-and-global-chat-feedback.md)、[左侧导航 renderer](../../olav-os/experiments/t-37-human-ai-swarm-skeleton/navigation-defaults/renderers/left-sidebar/renderer.css)。参考的是布局与交互原则，不意味着复制其插件导航运行时或其全部页面。

## 2. 桌面壳层

```text
┌──────┬──────────────────────────────────────────────────────────┐
│ Logo │ LightGravity Bot · 全局 / Task 标题    资源栏 对话 通知  │
├──────┼──────────────┬───────────────────────┬───────────────────┤
│ Chat │ 上下文资源栏 │ 主内容区              │ Bot 对话栏        │
│ Board│              │ 看板 / 文件预览 /     │ 当前 Task 或      │
│ Files│ 历史、任务、 │ 成员详情              │ 全局会话          │
│ Team │ 文件、角色   │                       │                   │
│ Res. │ 配置资源     │                       │                   │
│      │              │                       │                   │
│ Set. │ 模型设置     │                       │                   │
└──────┴──────────────┴───────────────────────┴───────────────────┘
```

最左一级导航固定为窄栏，只显示图标；hover/focus 显示文字提示，当前项明确高亮，并提供可访问名称。建议初始宽度 56px，属于候选视觉参数，需按真实页面验证。

顶栏只提供品牌、当前范围/任务、资源栏与对话栏开关、通知入口。不再放 Chat／Board／Files／Team／Resources 一级横向 tabs。Task 选择器不是必须先选择 Project 的入口。

资源栏和对话栏可折叠；桌面具备空间时允许拖动宽度。优先确保主内容可读，最小宽度与断点实现时验证；不能为追求四栏在窄屏强行压缩内容。栏宽/显隐属于 UI 偏好，不能写进 Task 业务状态。

## 3. 左侧一级入口

| 顺序 | 入口 | 建议图标 | 资源栏 | 主内容 |
|---|---|---|---|---|
| 1 | Chat | message-circle | 全局会话与 Task 历史 | 对话工作区及关联任务摘要 |
| 2 | Board | columns-3 | 任务范围与阶段筛选 | Task 卡片，展开 Run/Subtask |
| 3 | Files | folder-open | 当前 Task 文件列表/目录 | 文件预览、产物与证据 |
| 4 | Team | users-round | 待招募／已招募的纵向选择及列表 | 角色或临时成员详情 |
| 5 | Resources | boxes | Connections／Session Profiles／Hooks／MCP／Tools／Triggers／Skills 纵向分类 | 配置、引用、诊断与实际可用性 |
| 底部 | Settings | settings | Models & Providers | 模型连接、凭证、默认选择与测试 |

图标为设计候选，保持五个工作入口与底部设置入口易区分。Agent 不另设一级入口，统一在 Team 管理；其余能力收束到 Resources，首版不增加工单、岗位、办公室入口。

Chat 入口聚焦当前会话并展开对话工作区；其他入口可以同时保留右侧 Chat。Chat 页面主内容与右侧栏是同一个对话组件的布局切换，不显示两份相同聊天，不生成额外 session。切换 Board／Files／Team／Resources 不取消任务、不重置会话。

### 3.1 Chat 与 Files：资料接入目标与当前实现差异（待实现，见 docs/09）

**目标交互（未实现）**：

- Chat 是唯一常规资料接入入口，支持上传、拖拽、粘贴链接；未来文件夹/邮箱从对话发起，选择器/授权页完成选择后**返回同一对话**。Task Chat 内资料默认归属该 Task，全局上传**不强建 Task**。
- Files 不承担常规上传入口，负责预览/浏览/来源追溯/归档调整/校订/重处理/下载，**不新增一级知识库入口**。邮箱资料连接器不同于模型 Connection，不暗加到冻结 schema。

**当前实现（诚实差异）**：

- Chat 仍为壳层占位：消息发送未接线（LG-007/LG-013），发送不伪造消息也不创建 Task，尚无资料上传/拖拽/链接入口。
- Files 已挂载工作区只读浏览/预览/下载与历史上传 API/UI（LG-014）：上传需运行时 token，无 token 时如实返回 `unauthorized`；它不提供来源追溯/校订/重处理/摄取回执，也不是目标接入入口。
- **迁移未开始**：不应把现有 Files 上传当作目标交互，也不应据此声称资料接入/检索已实现。目标与分层见 [资料接入与检索设计](09-source-intake-and-retrieval.md)。

## 4. 全局与 Task 范围

顶栏显示“全局”或明确 Task ID/标题。选择 Task 后，Board、Files、Team 和 Chat 共享 task_ref；切换左侧入口保留该范围，并保留必要的 Run 选择。Task 详情不以浏览器当前文件路径临时推断身份。

- 全局 Chat 可以普通问答或创建交付需求；历史含 Task 导航。
- 全局 Board 显示 Task 列表，打开卡片进入该 Task。
- 全局 Files 显示获准任务目录入口，进入 Task 后显示其文件；不暴露任意系统文件树。
- 全局 Team 默认进入待招募角色目录；已招募展示各 Task 当前成员并标明归属，提供 Task 筛选。
- Task Team 默认进入当前 Run 的已招募列表；可以切到待招募查看候选角色。
- Resources 默认展示获准的共享配置目录；进入 Task 后保留 task_ref，可筛选该任务实际引用的资源。查看共享资源不自动把该资源授予当前 Task，也不把配置正文直接当作任务指令。

从通知、任务卡、历史或文件入口进入同一 Task 应解析到同一稳定 ID。退出 Task 返回全局时，不将当前任务文件默认为全局聊天上下文。

## 5. Team：待招募与已招募

Team 的二级切换也放在左侧资源栏，以纵向“待招募／已招募”呈现，不重新在顶栏建立全局 tabs。名称中的“待招募”表示候选角色库，不是所有角色正在排队等待加入。

| 视图 | 权威来源 | 展示字段 | 生命周期 |
|---|---|---|---|
| 待招募 | resources/agents/*.md 及引用资源 | 角色名称、职责、能力标签、skills、工具、来源版本与可用性 | 长期角色模板 |
| 已招募 | Task/Run 的 team/*.md | memberId、角色、Task/Run、分派 Subtask、会话状态、结果与可取得的用量 | 临时实例与历史 |

SDK Agent 的配置模板合并到“待招募”，SDK Agent 会话由“已招募”成员承接；用户只面对角色与成员，不需要再到另一个 Agent 页面招募。默认协调角色在模板中标明系统用途，不算作当前 Run 的已招募 worker。角色详情显示 Connections、Session Profile、Skills、Hooks、MCP、Tools、Triggers 的声明引用；成员详情显示本次实际解析版本、有效权限、可用性与会话记录。

模板缺少工具、技能或后端时显示“不可用”与原因，不能因为 Markdown 文件存在就显示可执行。待招募角色不是空闲 worker，不占运行资源。

临时成员建议状态：`recruiting → ready → running → released`，分支为 `waiting_user`、`failed`。这是 Member 状态，不覆盖 Subtask 验收状态。暂停且已关闭 session 的实例显示已释放，其恢复配置和历史保留；恢复时创建新成员实例并记录来源。

招募中、招募失败、任务执行与已释放都在已招募详情中可观察。当前队伍计数不含已释放成员；“查看历史”筛选可以查看旧 Run 的成员，旧 Run 明确标识。交付待验收时当前队伍可能为零，但历史名单与成果必须可查看。

自动组队通过 Recruiter/调度器生成成员记录。首版页面以查看为主：从角色卡“请求用于当前任务”可以打开 Task Chat 并表达意图，不绕过计划校验直接创建 SDK worker；没有 Task 时先在 Chat 明确目标。导入角色、编辑模板、复杂招募表单暂缓。

## 6. Markdown 渲染与数据边界

Team 复用 schema/kind renderer：Agent 卡读取角色模板 frontmatter，Member 卡读取运行成员 frontmatter，正文显示职责/执行说明。能力与资源引用可导航到详情，但不为七类 SDK 资源都增加一级 tab。

导航配置首版可以是程序内固定五个工作入口与底部 Settings，不建立动态插件加载器。Team/Resources 列表、运行状态和通知从持久文件/事件刷新，解析失败显示诊断，不能渲染假成功成员。

页面路由必须保留 view、task_ref、run_ref 和选中资源。深链刷新可恢复这些范围；会话和执行事实来自文件，导航选中项、滚动和栏宽来自 UI 偏好。

### 6.1 Resources 二级导航与归属

Resources 二级入口放在左侧资源栏，主内容显示选中资源的 frontmatter 字段、Markdown 正文、引用关系和诊断。不是每个 SDK 模块一个一级 tab。

| 二级入口 | 权威来源 | 管理对象与展示 |
|---|---|---|
| Connections | resources/connections/*.md | 已支持的 adapter、模型、认证引用、区域及连接健康 |
| Session Profiles | resources/conversations/*.md | 上下文、压缩、存储与 continuation 的会话配置模板 |
| Hooks | resources/hooks/*.md | 已注册生命周期 handler、策略和参数 |
| MCP | resources/mcp/*.md | stdio/HTTP 服务配置、工具选择、连接状态与工具发现 |
| Tools | resources/tools/*.md | SDK builtin/已注册函数描述，MCP 工具目录以所属服务关联展示 |
| Triggers | resources/triggers/*.md | 事件/时间规则、作用域、启用状态和最近触发记录 |
| Skills | resources/skills/*/SKILL.md 及获准项目技能 | 工作方法、引用文件、脚本与依赖 |

Session Profiles 管理 Conversation 的配置，不管理聊天消息。真实用户对话在 Chat/Task，成员 SDK Conversation 在已招募详情与 Run 历史。Resources 只链接到关联会话，不复制日志或维护第二份聊天状态。

Skills 的原生 SKILL.md 格式与应用资源 frontmatter 需要显式映射；不能为了网页渲染强行添加会破坏 SDK 发现的字段。身份、版本及来源可通过受控索引/描述引用展示，但内容以 canonical 文件为准，索引可重建。

MCP 动态发现的工具在 Tools 中作为服务派生项展示，来源、名称与所属服务明确；不能把相同工具再复制成独立 callable 配置。未连接时显示缓存/未知可用性，不伪装实时健康。

所有资源区分声明启用、解析有效、依赖齐备、运行可用四种信息。声明 enabled 不等于已建立连接，更不意味着在后台启动 Trigger/MCP。健康检查、启用与运行走获准接口，不能由页面预览或文件解析自动执行。

### 6.2 Team 与 Resources 关联及修改

从待招募角色或已招募成员点击资源引用，进入 Resources 对应详情，保留 Task/Run/Member 的返回位置。返回 Team 仍是原成员；跨页面只改变查看位置，不变更实际绑定。

首版提供列表、详情、诊断和关联导航。普通资源更改通过 Chat 请求受控写入，明确修改的是共享模板还是当前任务约束；涉及两种范围时不自动猜测。模型接入与凭证通过 Settings 的受保护表单，是必要例外；Connections 提供同一资源的详情与编辑导航。程序校验引用、权限与版本后保存，其他复杂编辑表单与批量导入暂缓。

模板修改只影响后续招募；已招募成员固定本次配置版本与哈希。正在运行的任务若确需变更，经过协调器暂停、修订和重新绑定，不能静默热替换。删除/禁用被引用资源应提示受影响模板和任务，首版可阻止删除，不留下悬空引用。

成员运行记录中的 SDK session、解析后参数和用量是运行事实，不能把它们回写到共享配置模板。凭证只显示引用和是否配置，不显示真实值。

## 7. 窄屏与状态反馈

Settings 的入口、字段、凭证管理、分层连接测试及与 Resources/Team 的共享引用见 [模型设置设计](07-settings-and-models.md)。Settings 是全局配置页，保留返回当前 Task 的位置；进入设置不把当前 Task 授权或模型绑定自动改成全局默认。

窄屏保留左侧一级入口或可打开的侧边抽屉，资源栏改为抽屉，对话与详情一次显示一个主要面板。导航从左侧打开，不退回上方五个一级 tabs。面板切换保留输入草稿，并提供返回当前 Task 的明确入口。

每个页面需设计加载、空态、解析错误、资源不可用与断线状态。Team 空态区分“没有角色模板”“还未组队”“队伍已释放”和“当前 Run 招募失败”。通知徽标只反映未读记录，不把队伍数量当作通知数量。

## 8. 验收条件

- 桌面一级入口在最左侧固定展示，无重复顶栏 tabs；键盘、tooltip 和选中状态有效。
- Task 内跨五个入口保持相同 task_ref，不改变运行或意外新建会话。
- Chat 页面与右侧 Chat 只呈现一个活动对话，切换后草稿和历史保持。
- Team 待招募读模板，已招募读实例；自动招募、失败和释放真实反映在页面。
- 当前名单排除已释放实例，历史可导航到正确 Run 与证据。
- Agent 只在 Team 展示模板/实例；其余七类配置在 Resources 有对应分类，真实 Conversation 留在 Chat/成员详情。
- 角色/成员的资源引用能导航到正确版本和返回原位置；模板修改不改变正在运行的成员配置。
- 无效、未安装、未连接或禁用资源可区分；预览不启动连接/触发器，凭证不泄露。
- 左导航底部能进入 Settings，Connections 的编辑指向同一 Connection；默认变更不热切换活跃成员，凭证不经聊天/Markdown。
- 深链刷新恢复所选 Task/Run/成员；不能串到另一个任务。
- 窄屏能完成对话、查看任务、打开文件与成员详情，面板不相互覆盖。

当前只完成设计，不代表上述页面或交互已交付。
