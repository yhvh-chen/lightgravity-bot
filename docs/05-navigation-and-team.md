---
title: "左侧导航、任务入口与资源视图设计"
doc_type: design
category: frontend
updated: "2026-10-18"
---

# 左侧导航、任务入口与资源视图设计

> 2026-10-16 用户七项反馈取代旧四栏布局。LG-051 已完成技术交付：候选 602c7af 独立 QA PASS_WITH_LIMITATIONS，主目录 ea6da80 产品树一致，实际入口另有 30 项检查通过。当前实施与证据见 [LG-051](../backlog/tasks/LG-051.md) 和 [PROJECT](../PROJECT.md)。

## 1. 布局与范围

> **2026-10-18 用户决策（LG-202～205 已集成于隔离候选，待 LG-207 独立版本/浏览器 QA）**：删除 Chat 主页面，Files 更名 Tasks；右侧 Bot Chat 是唯一对话界面并绑定当前 Task。下方示意图与 §2～4 已按此更新，旧 Chat 主区描述作废。实现证据见 [LG-206 交付](../../probes/demo-tasks-20261018/lg206/DELIVERY.md)，生产 8123 仍为 1.20.0、尚未部署本候选。决策记录见 PROJECT.md。

LG-102 统一资源与底部Settings的线性SVG图标，18px尺寸与一致描边；LG-103 随后移除独立 Connections 入口，保留六类资源与 Settings，原 Chat／Board／Files／Team 图形保持。[图标交付](../probes/nav-icons-20261017/DELIVERY.md) · [连接入口收敛](../probes/settings-connections-20261017/DELIVERY.md)。

界面使用一个左侧导航、主内容与右侧 Bot Chat。删除第二上下文栏、对应显隐开关、resize 和窄屏资源抽屉。只挂载右侧一个活动对话，不产生重复 session。

```text
顶部：品牌 · [Search 可编辑搜索框，居中] · 对话开关 · 通知/账号
┌─────────────────┬─────────────────────────┬─────────────────────┐
│ Tasks           │ 主内容                  │ Bot Chat            │
│ Board           │ Task 工作区（文件/预览/ │ [Personal][Team] 🕘 │
│ Team            │ 产物）/ 看板 / AI 成员 /│ 绑定当前 Task，     │
│                 │ 资源详情                │ 无 Task 时为 Global │
│ Session Profiles│                         │                     │
│ Hooks / MCP     │                         │                     │
│ Tools / Triggers│                         │                     │
│ Skills          │                         │                     │
│ Settings（底部）│                         │                     │
└─────────────────┴─────────────────────────┴─────────────────────┘
```

导航项可在同一栏分组、滚动和折叠；文字与图标保持可辨认，选中状态、可访问名称和键盘操作明确。窄屏用单一导航抽屉与一个主面板；不恢复顶栏一级 tabs。具体尺寸由真实浏览器验收确认。

顶栏删除 Scope/Run 选择器。真实任务标题放在 Bot Chat 或 Tasks 工作区头部；Run 细节仍可在任务执行详情查看。界面入口简化不删除底层 Run、成员或验收记录。

## 2. 入口与主内容

| 入口 | 内容与边界 |
|---|---|
| 右侧 Bot Chat | 不占导航项；全局或当前 Task 对话、消息与交付结果；Personal／Team 右侧历史图标 |
| Tasks（原 Files） | 顶部固定 General；真实 Task 目录与 New task；选中后为该 Task 工作区文件树、预览、产物、证据与上下文材料选择 |
| Board | 真实 Task 卡片、阶段、队列与运行详情 |
| Team | AI 角色模板与实际运行成员，Available/Recruited 在主区切换 |
| Session Profiles | 会话配置模板，真实聊天仍由 Chat／成员详情承接 |
| Hooks / MCP / Tools / Triggers / Skills | 对应资源列表、详情、引用与诊断，复用现有 renderer |
| Settings | 左导航底部；Models & Providers 为完整连接管理唯一入口，另含 Accounts（管理员）和 My Account（所有团队登录用户） |

Board 的验收/拒绝只在当前 Task 的当前 Run 已完成验证、处于待验收、机器检查满足且候选/需求/交付版本与计划哈希一致时启用；按钮只是交互门，服务端仍复核。证据项通过 Task 范围 `/artifacts/download` 下载 canonical evidence，不暴露绝对路径或跨 Task 引用。

Session Profiles／Hooks／MCP／Tools／Triggers／Skills 六类资源直接从左导航到达，Resources 作为共用资源页面实现与业务归属保留，不要求经过中间分类页。Connection 仍是 canonical 资源，UI 管理统一归 Settings；Team／资源连接引用及旧 Connections 深链规范化到 Settings 并定位稳定 ID，保留 Task/Run/channel。其余旧资源深链继续解析到对应分类／详情。

## 3. Task 入口与导航状态

Tasks 通过受控任务 API 获取真实 id/title，形成任务目录（磁盘上即 `tasks/<id>/`）。点击后以稳定 task_ref 进入该 Task 工作区并把右侧对话切到该 Task；必要时加载该 Task 的授权 workspace 与产物。General 表示 task_ref 为空的 Global 对话。

- New task：弹窗输入标题，调用 `POST /tasks`（`request_id` 幂等，`objective` 默认取标题），由后端创建 `tasks/<id>/TASK.md` 与默认工作区，成功后进入新 Task。前端不直接创建目录；在 Global 对话中由协调器建 Task 的原路径保留。
- 上下文材料：工作区文件／材料行提供 Use as context，沿用现有选择状态与上限，范围仅限当前 Task 与全局材料（跨 Task 禁止，服务端复核）；右侧输入框以 chip 显示已选并可移除。原输入框 `+` 扩展面板与按路径引用文件输入删除。
- 历史图标（第一期）：在 Team 下列出 General 与有消息的各 Task 对话，按最近活动排序，点击即切换 task_ref；不新建会话。Personal 保持不挂 Task 的个人私聊；Task 内私聊、每 Task 多会话为第二期，需后端会话与权限设计。

- data_dir 下的 TASK.md 元数据目录与 workspace_root 文件树是不同边界，不直接把整个 data_dir 暴露给 Files。
- 不能根据普通文件夹名、任意 TASK.md 内容或模拟 ID 获得任务身份。
- Task 不存在、失效链接或无权限时提供可恢复说明，保留草稿，不持续向不存在的任务发消息。
- 打开 Task 同时更新 view、task、run/item 导航；沿用选 Task 时清理旧 run/item 的一致行为。
- 跨 Board、Files、Team 和资源入口保持有效 task_ref 与当前对话，不取消后台任务、不意外创建新 Run。
- 刷新、后退和旧链接按真实实体恢复；UI 偏好只保存导航、滚动、栏宽和草稿，不写业务状态。
- 退出任务返回全局后，不自动将旧任务资料当作全局上下文。
- 删除模拟 Scope/Run 业务选择；演示数据不可成为真实 API 请求的任务身份。

## 4. 顶部资料搜索与简化 Chat

Search 移到顶部，复用现有资料词法检索。当前查询范围与 Task／global 归属必须可理解；它尚不代表聊天历史、任意源码和全部任务的全局搜索。

LG-100 将搜索入口改为顶栏中部常显可编辑输入框，宽屏约360–460px居中，窄屏自适应无横向溢出。直接输入并按Enter打开真实结果面板，结果保留Files回链；Escape关闭面板、保留查询并返回搜索框焦点，不再要求先点击Search按钮或在两个输入框间重复填写。现有范围与过期响应处理保持。

- 结果显示来源与版本，可打开 Files；切换范围时清理或取消旧结果，迟到请求不得污染新范围。
- loading、empty、stale、index_unavailable、权限错误与网络失败保持可区分。
- 不因界面移动自动启用向量检索、扩大资料权限或新增模型调用。

本批 Chat 设计只呈现 Personal/Team（及其右侧历史图标）、消息、多行输入、框内附件按钮和右下角发送 icon；文件按钮直接打开文件选择器，不设扩展面板（2026-10-18），删除清单与输入框自适应规则见 [docs/13 §5](13-chat-and-task-teams.md#5-chat-和附件的确定交互)。已选附件、处理状态和失败信息仍可见；实现已进入隔离完整候选，待 LG-123 独立版本/浏览器 QA。

- 保留 IME 保护、Enter/Shift+Enter 行为、发送失败草稿与历史阅读位置。
- 保留来源数量上限、版本／哈希绑定和消息幂等。
- 来源绑定表示提供的上下文，不暗示引用已逐段核验。
- 暂停、取消、恢复和验收仍使用真实动作与反馈，不能以停止显示冒充后台停止。
- Chat 摄取是受控资料操作，不自动创建交付任务或团队。Files 继续负责浏览、预览、追溯与管理。

## 5. Personal / Team 对话头部

用户要求对话上方有个人／团队标签；2026-10-17 持续执行授权下，按已向用户说明的执行假设补齐 Personal 私聊／Team 共享聊天，见 [LG-054](../backlog/tasks/LG-054.md)。已整合并通过独立技术 QA，用户最终验收待定。

当前团队模式是一个共享工作区，global 与 Task 历史共享；人类账号与 Team 页中的 AI Member 不同。部署级 isTeam 不是可任意切换的会话权限。

Personal 私聊由服务端登录身份绑定并隔离读写，不把旧 shared global 历史迁移为某人的私人记录。仅在前端按 author 过滤不能构成隔离。草稿、附件、选材、游标和在途消息也须按身份和对话隔离。LG-054 历史交付限定问答；本批 LG-119 已确认增加仅本人私聊可用的附件，不隐式创建共享 Task 或把个人上传写为共享来源；Team 仍用共享资料与任务对话。私人附件已在隔离完整候选实现（权限与接口见 docs/08 §19.3），待 LG-123 独立 QA。

默认单用户部署保留原 global 问答、Task 创建、Files 任务对话与资料能力；不能因 Team 未开启导致核心交付不可用。团队模式打开共享 Task 时进入 Team，Personal 不假装提供私有 Task／资料。Team 页中的 AI 成员管理继续独立于人类群聊，不混写两个实体。

## 6. Team 与资源边界

本批详细线框、按任务队伍分组、状态操作、Active/History、自动解散与并发隔离见 [docs/13 §2～4](13-chat-and-task-teams.md#2-team-的信息架构与线框)，属于已确认需求的设计细化、尚未实现。

Available 读取长期 Agent 角色模板；Recruited 读取 Task/Run 的 Member 实例。默认协调角色不计作执行 worker。模板与实例展示职责、能力、配置引用、实际版本、可用性及结果。

当前名单排除已释放成员，历史名单与证据保留。队伍为空时区分未招募、已释放与招募失败。角色卡请求进入当前 Task Chat，不直接创建 SDK worker。

| 资源 | 权威来源 |
|---|---|
| Connections（Settings 管理） | resources/connections/*.md |
| Session Profiles | resources/conversations/*.md |
| Hooks | resources/hooks/*.md |
| MCP | resources/mcp/*.md |
| Tools | resources/tools/*.md |
| Triggers | resources/triggers/*.md |
| Skills | resources/skills/*/SKILL.md 及获准项目技能 |

资源引用进入正确分类／详情并保留返回位置。声明启用、解析有效、依赖齐备和实际可用分别呈现。预览不执行 handler、不连接 MCP、不启动 Trigger。MCP 派生工具保留服务来源，不复制为第二份 callable 配置。

Skills 沿用原生格式与显式映射。资源以 canonical 文件为准，索引可重建。普通配置按现有受控对话写入；模型／凭证走 Settings 受保护表单。真实密钥不进入对话、Markdown 或浏览器持久草稿。

模板修改仅影响后续招募，活跃 Member 固定实际配置版本；session 和用量不回写共享模板。禁用或删除引用资源时遵循既有引用校验。

## 7. 可用性与错误

运行版本、必要能力与实际接口应先验证，再显示系统就绪。只有 health 成功的旧骨架服务不能被视作完整工作台。

区分连接失败、后端不兼容、缺少模型配置、真实任务不存在、目录不存在与未授权。不能将所有 HTTP 404 显示为 Scope not found；不能通过认证降级绕过登录。每页覆盖实际适用的 loading、empty、error、unavailable 与 disconnected。

通知反映真实未读事件；恢复按游标补齐。Settings 保留当前任务返回位置，不改变其授权或热切换模型。

Settings 使用页内子区，不增设第二左侧栏。Accounts 管理新增、角色、启用／禁用及密码重置，用户名不可变、没有删除功能；My Account 只修改本人密码。普通成员不拉取 Models/Connections 或账户列表。末位可用管理员保护、口令写入后清空、会话撤销及旧后端能力降级按 [docs/08 §16](08-interface-contract.md)。LG-061／062 已完成独立 QA 与本地部署，见 [账户管理证据](../probes/accounts-20261017/README.md)。

Models & Providers 保留连接列表、新建编辑、凭据、连接测试及默认模型的完整表单。连接引用按 `settings:connection:<id>` 统一定位；未知目标明确提示且不选中／保存另一连接，跨 ID 迟到保存不改变当前选择。普通成员打开连接目标时只显示管理员管理提示和 My Account，不发起管理员配置请求。LG-103 已通过真实隔离管理员／成员与390宽度验证，原连接数据及后端 API 保持。

LG-104已交付列表＋紧凑新增/编辑弹窗，默认模型独立放列表下方；连接引用打开对应ID编辑弹窗，关闭后不因同一深链反复重开，未知目标仍提示。草稿测试不要求保存，结果只绑定当前草稿；主流程不展示SDK类名/代理/内部ID说明，DeepSeek预设地址收进Advanced，Custom地址主显。焦点/Escape/放弃修改/迟到响应边界见design.md，公开API见docs/08 §18。main df53ead/8123契约1.17.0，独立R2真实前后端8场景及1440/1024/390通过；旧常驻长表单为此前快照。[交付](../probes/provider-setup-20261017/qa-r2/DELIVERY.md)。

## 8. 验收与实现状态

LG-052／053 修复者提供必要局部类型、构建与非浏览器回归。串行集成与独立版本 QA 归 pi，Playwright 连接隔离数据和端口的真实前后端：

- 实际版本／接口就绪，所有入口到达真实 handler；团队匿名 401、管理员门禁保持。
- 无第二左栏和 Scope/Run，六类资源直接可达，Connections 统一由 Settings 管理；只挂一个活动对话。
- Files 真实 Task 打开对应历史，普通同名目录反例、失效链接、刷新／后退均有效。
- 顶部搜索到 Files 回链、范围切换、选材版本与失败草稿保持。
- 1440、1024、390 宽度以及长标题、键盘、导航滚动和抽屉。
- Personal/Team 按 LG-054 最终语义验证；若涉及私聊，覆盖两个身份的读写隔离与迟到结果。
- 截图、trace 与实际结果可追溯；构建、静态 mock 和局部测试不能替代真实浏览器验收。

实现、独立版本 QA 和本地实际入口更新均已完成，证据见 [LG-051 交付记录](../probes/ui-repair-20261017/README.md)。用户最终验收、远端推送及发布分别处理；本轮未推送。

## 资料上传与自动索引体验补充（2026-10-18，隔离候选QA通过）

[docs/14](14-material-intake-and-auto-index.md) 为 LG-139～145 的新增设计依据：Chat 是常规接入入口、逐文件回执显示独立处理状态；Files 预览/追溯/校订/重处理；顶部搜索面板提供 Keyword/Semantic 和回链，不增加主导航。团队 Personal 不写共享资料或调用媒体索引。已在隔离1.19候选实现并完成局部检查，LG145第二轮独立QA通过，线上仍1.18；排期见 [docs/06 §8](06-roadmap.md)。
