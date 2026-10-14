---
title: "LightGravity Bot"
doc_type: overview
category: project
updated: "2026-10-15"
---

# LightGravity Bot

> 更新：2026-10-15。设计与 27 项首版开发任务已落盘，首版接口契约（docs/08，契约版本 1.5.0）已冻结；用户已确认首版先用 DeepSeek，首版真实执行后端为已验收的 OpenAI-compatible（`LocalOpenAIAgentConfig`）+ loopback 认证代理接 DeepSeek，此前的 Gemini 认证阻塞已解除。LG-001～009、LG-011、LG-012、LG-014、LG-015、LG-020、LG-025、LG-026 共 16 项已完成并整合到 `main`（均为**待版本 QA**）：工程骨架可运行、SDK 探针、存储层、资源配置编译、左侧导航壳层、正式 executor + loopback 认证代理、常驻消息路由与 Task 队列、自动组队与依赖调度、模型设置与凭证后端、产物验证与人工验收、查询 API 与持久事件订阅、Settings 模型接入页面、Team/Resources 管理视图与受控资源写入、本地启动/停止与一体分发入口。集成后已把验证服务与资源停止接口注入 `create_app`，accept/reject 合并进 API actions，并新增只读 `GET /tasks/{id}/acceptance` 与单例全局对话 `GET/POST /api/v1/conversations/global/messages`。主前端构建现已挂载 Settings、Files、Team 与 Resources 视图，分别接线 `/api/v1/settings*`、`/api/v1/files*`、`/api/v1/team/*` 与 `/api/v1/resources/*`；Files 上传复用 LG-026 运行时 token helper 注入 `X-LG-Token`，无 token 时上传如实返回 `unauthorized`。Team/Resources 受控修改经 Task 对话提议：`POST /api/v1/tasks/{id}/messages` 携带 `resource_proposal` 时执行 sensitive 授权，`message_id` 幂等、`expected_revision` 版本检查，实际结果写回同一 Task 对话；该路径不创建 Run、不等待代码 worker，也不热替换活跃 Member 配置（docs/08 1.4.0 登记 `PATCH /resources/{kind}/{id}`、`GET /team/available`、`GET /team/members`）。LG-020 已提供 `lightgravity start/stop/status/init` 与一体分发：默认 loopback、`data/workspace/secret/dist` 隔离、首个启动在内存握手运行时 token 并注入 `index.html`（`__LG_RUNTIME_TOKEN__`，前端 `auth.ts` 读取后自动带 `X-LG-Token`），敏感写默认拒绝、缺认证可读历史/设置；首次启动幂等种子 `lg-default-worker`（仅 `view-file`/`create-file`/`edit-file` 三个 workspace 受限工具，无 `run-command`/web 无边界工具），Settings-only 建连接/存凭证/静态测试/设 worker 默认后新 Task 可用默认 worker，Run/Member 在招募时冻结非秘密 `connection_pin`（docs/08 1.5.0）。同时注册 canonical evidence 产物在 Task 产物 API 的预览/下载：`GET /tasks/{id}/artifacts`、`.../artifacts/content`、`.../artifacts/download`，仅接受 `evidence:<run_id>/<name>@sha256:<hex>` 并经 Task/Run evidence resolver 授权，拒绝原始绝对路径/跨 Task/跨 Run/摘要不符。敏感写仍由后端 `LocalAccessPolicy` 默认拒绝，Chat/Board 仍为占位/未接入，不宣称全部页面可用。LG-006 以真实 DeepSeek（实际发送 `deepseek-v4-flash`，上游返回 `deepseek-flash`）在临时授权工作区跑通文件写入/diff、结构化结果、用量、预算停止、会话恢复与确认取消，真实模型调用总数 12（硬上限 12），进程无残留；证据见 [tests/adapter/evidence](tests/adapter/evidence/README.md)。LG-009/LG-012 的真实 SDK 端到端与浏览器验收仍未完成，分别留 LG-010 与 LG-021/LG-022。LG-010 首轮独立 QA 报告两项阻断（executor 绝对 `diff_ref` 被机器检查误判为 workspace 相对路径；交付完成后未自动触发验证），已按两项返修、新增回归并集成 LG-014，但尚未经独立 QA 复验，LG-010 保持 in-progress/blocked；未部署。

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

## 当前进展（截至 2026-10-15）

| 任务 | 状态 | 实际证据与限制 |
|---|---|---|
| LG-001 契约 | done | [docs/08](docs/08-interface-contract.md) 首版契约已冻结（LG-001 为 1.0.0，2026-10-15 MINOR 升至 1.1.0，首版后端改为 DeepSeek） |
| LG-002 工程骨架 | done | 后端 health/version、前端占位壳、check 入口可用 |
| LG-003 SDK 探针 | done（带限制） | 固定 `google-antigravity==0.1.22`；文件工具、结构化输出、工具事件、预算停止、取消、会话保存/恢复、skills（文件与 inline）、`read_url_content` 经真实 DeepSeek 实测通过；Gemini Developer API／Vertex 未验收（非首版路径，不作默认）；`search_web` 在非 Gemini 端点不可用。见 [LG-003 报告](probes/lg003-antigravity/reports/LG-003-report.md) |
| LG-004 存储层 | done（待版本 QA） | `backend/lightgravity/store/` + `tests/store/`；整合后局部 69 passed、全量后端 82 passed、mypy 无问题 |
| LG-005 资源编译 | done（待版本 QA） | `backend/lightgravity/adapter/` + `tests/adapter/`；refs/skills/tools/hooks/connection/session 解析、权限不扩大、秘密脱敏、unsupported 标记 unavailable、SDK 配置可编译；局部 51 passed、全量后端 133 passed、mypy 无问题 |
| LG-011 前端壳层 | done（待版本 QA） | `frontend/src/app/` 壳层与路由、`components/` 共享组件、`api/` 客户端与 `/health` 探测、`views/` 入口与占位；局部 19 vitest、23/23 无依赖 Chrome 浏览器检查、`tsc`/`vite build` 通过；**未做真实后端联调**，业务端点显示未接入/空态 |
| LG-006 Executor Adapter | done（待版本 QA） | `backend/lightgravity/adapter/` 正式 executor + loopback 认证代理 + 稳定边界类型；真实 DeepSeek 跑通文件写入/diff、结构化结果、用量、预算停止、会话恢复、确认取消，真实调用 12（上限 12），进程无残留；证据 [tests/adapter/evidence](tests/adapter/evidence/README.md) |
| LG-007 消息路由与队列 | done（待版本 QA） | `backend/lightgravity/coordinator/`（classification/logs/queue/state/dispatcher/service/api）；局部 30 passed、全后端 187 passed、mypy 无问题；执行证据用 in-process `FakeExecutor`（mock），真实 SDK 端到端留 LG-010 |
| LG-008 自动组队与依赖调度 | done（待版本 QA） | `backend/lightgravity/coordinator/`（planner/recruiter/scheduler/graph）；局部 coordinator 57 passed、全后端 247 passed、mypy 无问题（58 files）；默认 `max_parallel=1`，真实并行写代码留 LG-018 |
| LG-025 模型设置与凭证后端 | done（待版本 QA） | `backend/lightgravity/settings/`；局部 33 passed、全后端 189 passed、mypy 无问题（46 files）；分层连接测试 `overall=verified`（`tool_probe`/`structured_output`=skipped） |
| LG-026 Settings 模型接入页面 | done（待版本 QA，已挂载） | `frontend/src/views/settings/**`、`frontend/src/api/settings.ts`、`frontend/src/api/auth.ts`（运行时 token helper）；已由整合 owner 挂到 `views/registry.tsx` 既有 Settings 入口并删除旧占位；局部 `tsc` 通过、vitest 32 passed、`vite build` 成功（主构建含 Settings：CSS 20.29 kB / JS 193.02 kB）；真实接口证据为执行者临时 server + 1 次 DeepSeek 调用；敏感写默认拒绝、首次启动 token 握手未实现（LG-020），浏览器 QA 留 LG-021/027 |
| LG-009 验证与人工验收 | done（待版本 QA） | `backend/lightgravity/verify/`；局部 26 passed、全后端 273 passed、mypy 无问题（64 files）；机器检查只跑程序已注册且 Task `checks` 授权的项，停止门未确认不释放，accept/reject 绑定 requirements/候选版本并按 `request_id` 幂等；真实 SDK 端到端留 LG-010 |
| LG-012 查询 API 与事件订阅 | done（待版本 QA） | `backend/lightgravity/api/`；局部 30 passed、全后端 246 passed、mypy 无问题（61 files）；tasks/resources/files/SSE/settings 路由真实装配，事件先落盘再广播、游标重放去重、断线不取消 Run；SSE 用进程内 ASGI 驱动验证，真实 uvicorn/浏览器留 LG-021/022 |
| LG-014 Files 上传/下载与证据预览 | done（待版本 QA，已挂载） | `backend/lightgravity/api/files.py`（有界上传/下载、`expected_revision`、原子替换、越界/secret 拒绝，docs/08 §4.3 自 1.3.1 标为实现）、`frontend/src/views/files/**`；已由整合 owner 挂到 `views/registry.tsx` 并删除旧占位；上传默认复用 LG-026 运行时 token helper，无 token 时只读可用、上传如实 `unauthorized`；上传 token 首次启动握手归 LG-020，浏览器 QA 留 LG-021 |
| LG-015 Team 与 Resources 管理视图 | done（待版本 QA，已挂载） | `backend/lightgravity/resources/**`（目录/诊断/引用/受控写入）、`api/resources.py` 的 `PATCH /resources/{kind}/{id}` 与 `GET /team/available`/`GET /team/members`、`coordinator/resource_commands.py` 与 `service.py` 的消息级 `resource_proposal` 分支；`frontend/src/views/{team,resources}/**` 与数据驱动 `Context` 资源栏；整合后前端类型/测试/构建通过；契约 1.4.0 登记 3 个新端点与消息加性字段；无 Task 时只引导不假写，资源健康如实 unknown，浏览器/E2E 留 LG-021/022 |
| LG-020 启动检查与本地分发入口 | done（待版本 QA，已整合） | `backend/lightgravity/runtime/**`、`api/bootstrap.py`、`cli.py`/`__main__.py`、`pyproject` scripts、`Makefile` targets；`lightgravity start/stop/status/init`，默认 loopback、token 内存握手与 `index.html` 注入、Host/Origin 守卫、敏感写默认拒绝、缺认证可读历史/设置；首启幂等种子 `lg-default-worker`（**有界**文件工具 `view-file`/`create-file`/`edit-file`，无 `run-command`/web）；Settings-only 建连接/存凭证/静态测试/设默认后新 Task 可达 executor，Run/Member 固定非秘密 `connection_pin`；真实 dist 子进程 start→握章→stop 验证；真实 DeepSeek 2 次（同一 gated 用例，硬上限各 1）；docs/08 1.5.0 登记 `connection_pin` 与 evidence 预览/下载端点；待首版 QA（LG-021/022/027） |

- 上述 done 为执行者局部证据，**不是版本 QA 结论**；LG-003 已实测的 DeepSeek（OpenAI-compatible）路径是 docs/08 v1.5.0 确定的首版真实后端，LG-006 已在该路径上实现正式 executor + 产品侧 loopback 认证代理。LG-001～009、011、012、014、015、020、025、026 均待 LG-010／LG-021／LG-022／LG-027 等版本 QA 门集中验证。
- 下一步：LG-010 在同一 DeepSeek 路径上验收最小真实闭环（真实验证服务接线与停止确认），已返修两项阻断、**待独立 QA 复验**；LG-015 已整合，其受控资源写入为敏感授权、版本检查、不等 worker 的程序化路径，前端/浏览器与真实资源健康检查留 LG-021/LG-022；LG-020 已整合（本地启动/停止、首次启动 token 握手、默认连接 pin、canonical evidence 预览/下载），待首版 QA。

## 本地运行与检查（工程骨架）

工程骨架由 LG-002 建立，LG-004 已加入后端存储层，LG-005 已加入 adapter 资源配置编译并把 Antigravity SDK `0.1.22` 锁定为产品依赖，LG-006 已实现正式 executor + loopback 认证代理（真实 DeepSeek 路径，见 [tests/adapter/evidence](tests/adapter/evidence/README.md)），LG-007/LG-008 已实现 coordinator 消息路由、队列与自动组队调度，LG-009/LG-012 已实现验证/验收与查询 API，并由 `create_app` 装配 `FileStore`→`BroadcastingStore`→`Coordinator`、挂载 `/api/v1` 全部路由、lifespan 启停常驻 Coordinator。默认执行器仍是诚实的 `UnavailableExecutor`（不伪装可执行）；真实 SDK executor 由 LG-010 注入。前端壳已存在；Settings、Files、Team 与 Resources 视图已挂载并分别接入 `/api/v1/settings*`、`/api/v1/files*`、`/api/v1/team/*`、`/api/v1/resources/*`（敏感写与受控资源提议在 LG-020 握手前默认拒绝，只读可用），Chat/Board 仍为占位。

### 版本要求

| 组件 | 要求 | LG-002 已验证版本 |
|---|---|---|
| Python | `>=3.12,<3.13`（`.python-version` 为 `3.12`） | 3.12.13 |
| uv | `0.12.x` | 0.12.1 |
| Node.js | 22 LTS | v22.23.2 |
| npm | 10.x | 10.9.8 |
| GNU make | 统一入口 | `/usr/bin/make` |

### 启动后端

```bash
uv sync                # 创建 .venv 并按 uv.lock 安装
make run               # 默认 127.0.0.1:8000，仅监听 loopback
curl http://127.0.0.1:8000/api/v1/health
```

### 启动前端壳

```bash
npm --prefix frontend ci      # 按 package-lock.json 精确安装
make frontend-dev             # http://127.0.0.1:5173，/api 代理到后端
```

### 测试、类型与构建入口

```bash
make check            # 后端 mypy + pytest
make frontend-check   # 前端 tsc --noEmit + vitest run
make check-all        # 二者合并
make frontend-build   # 前端生产构建
```

### 配置与数据

- 复制 `.env.example` 为 `.env` 并按需修改；示例文件不含真实凭证，仓库不保存秘密。
- 运行数据根 `LIGHTGRAVITY_DATA_DIR`（默认 `./bot-data`）与源码分离并已 gitignore；工作区根与秘密存储边界见 docs/08 §10。
- 路径默认相对进程工作目录，克隆后无需开发机绝对路径即可运行。

## 文档入口

- 项目开发技能位于 `.agents/skills/`：已安装 Olav Tasks 的 6 个技能，来源版本与文件哈希见 [.agents/skills/olav-tasks-source.json](.agents/skills/olav-tasks-source.json)，许可证见 [.agents/skills/OLAV-TASKS-LICENSE](.agents/skills/OLAV-TASKS-LICENSE)。
- [开发约束](agent.md)：项目范围、架构、SDK 接入、状态写入、验证与交付规则；[AGENTS.md](AGENTS.md) 提供自动发现入口。
- [前端约束](design.md)：视觉 tokens、左侧多栏布局、组件、页面交互、响应式与浏览器验收。
- [开发看板](BACKLOG.md)：27 项首版开发任务，使用 `olav.tasks/v1` 管理。
- [滚动排期](docs/06-roadmap.md)：阶段、依赖、验收门与当前未定的日历安排。
- [模型设置](docs/07-settings-and-models.md)：Settings、Connection 事实源、凭证、分层测试和默认模型。
- [首版接口与状态契约](docs/08-interface-contract.md)：冻结的最小技术栈、API/事件/实体状态、Store/Adapter 边界、错误语义、工作区授权与后续文件归属（契约版本 1.5.0）。
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
- 使用 SDK 原生 skills 加载与基础文件、命令、网页工具；按成员绑定角色、技能、工具权限与工作区，不重建通用技能执行层。首版为 `google-antigravity==0.1.22` 的 OpenAI-compatible（`LocalOpenAIAgentConfig`）→ DeepSeek 路径（LG-003 已实测，LG-006 实现产品侧代理）；`search_web` 标记不可用；Gemini/Vertex 未验收，待各自探针通过后开放。
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
