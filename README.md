---
title: "LightGravity Bot"
doc_type: overview
category: project
updated: "2026-10-15"
---

# LightGravity Bot

> 更新：2026-10-15。设计与 27 项首版开发任务已落盘，首版接口契约（docs/08，契约版本 1.0.0）已冻结；LG-002 工程骨架可运行，LG-003 SDK 探针、LG-004 存储层与 LG-005 资源配置编译已完成。SDK 核心能力经真实 DeepSeek 实测通过，但产品首版 Gemini 后端因缺凭证未验收，`search_web` 不可用；adapter 已将 `google-antigravity==0.1.22` 锁定为产品依赖，但真实 executor（LG-006）、协调器、查询 API 等业务接线尚未实现，未部署。

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
| LG-001 契约 | done | [docs/08](docs/08-interface-contract.md) 契约版本 1.0.0 已冻结 |
| LG-002 工程骨架 | done | 后端 health/version、前端占位壳、check 入口可用 |
| LG-003 SDK 探针 | done（带限制） | 固定 `google-antigravity==0.1.22`；文件工具、结构化输出、工具事件、预算停止、取消、会话保存/恢复、skills（文件与 inline）、`read_url_content` 经真实 DeepSeek 实测通过；**产品首版 Gemini Developer API／Vertex 因本环境无凭证未验收**；`search_web` 在非 Gemini 端点不可用。见 [LG-003 报告](probes/lg003-antigravity/reports/LG-003-report.md) |
| LG-004 存储层 | done（待版本 QA） | `backend/lightgravity/store/` + `tests/store/`；整合后局部 69 passed、全量后端 82 passed、mypy 无问题 |
| LG-005 资源编译 | done（待版本 QA） | `backend/lightgravity/adapter/` + `tests/adapter/`；refs/skills/tools/hooks/connection/session 解析、权限不扩大、秘密脱敏、unsupported 标记 unavailable、SDK 配置可编译；局部 51 passed、全量后端 133 passed、mypy 无问题 |
| LG-011 前端壳层 | in-progress | 在独立 worktree 执行中，未并入本批 |

- 上述 done 为执行者局部证据，**不是版本 QA 结论**；LG-003 的 DeepSeek 路径不改变 docs/08 冻结的“首版 Gemini 后端”产品契约。
- 下一步：LG-006 可基于 LG-005 的 `CompiledAgentConfig`/`build_sdk_config` 接口实现真实 executor；**LG-006 真实 Gemini adapter 与 LG-010 最小真实闭环仍需具备 Gemini 凭证的环境完成认证后才能验收**。

## 本地运行与检查（工程骨架）

工程骨架由 LG-002 建立，LG-004 已加入后端存储层，LG-005 已加入 adapter 资源配置编译并把 Antigravity SDK `0.1.22` 锁定为产品依赖；仍只提供后端 `GET /api/v1/health`、`GET /api/v1/version` 与前端占位壳，不含 HTTP 业务端点，也未实现真实 SDK 执行/会话。

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
- [首版接口与状态契约](docs/08-interface-contract.md)：冻结的最小技术栈、API/事件/实体状态、Store/Adapter 边界、错误语义、工作区授权与后续文件归属（契约版本 1.0.0）。
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
- 使用 SDK 原生 skills 加载与基础文件、命令、网页工具；按成员绑定角色、技能、工具权限与工作区，不重建通用技能执行层。LG-003 已用真实 DeepSeek 探针验证核心能力；产品首版 Gemini 路径与 `search_web` 仍待具备凭证的环境复验。
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
