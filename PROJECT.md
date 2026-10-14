---
title: "LightGravity Bot 项目手册"
doc_type: handbook
category: project
updated: "2026-10-15"
---

# LightGravity Bot 项目手册

> 更新：2026-10-15。阶段：LG-001 契约已冻结，LG-002 工程骨架可运行，LG-003 SDK 探针完成（核心能力经真实 DeepSeek 实测通过；产品首版 Gemini 后端因本环境缺凭证未认证，`search_web` 不可用），LG-004 存储层与局部测试完成，LG-005 角色/SDK 资源配置编译完成（已将 `google-antigravity==0.1.22` 锁定为产品依赖），LG-011 前端壳层完成并整合到 `main`（6 项均**待版本 QA**）。产品真实 executor（LG-006）当前 **`blocked_by`：首版 Gemini 缺少认证**；协调器、查询 API 等业务接线尚未实现。27 项任务见 BACKLOG.md；人员、预算、日历日期与部署目标未确定。代码仓库已于 2026-10-14 初始化 Git 并推送 `main` 到内部 Gitea。

## 目标

做一个比 Olav OS 更轻量的 AI 任务助手：用户通过对话提出目标，系统按需组队、执行、验证、交付，在项目目录中保存可复核的结果。

首版用开发任务验证闭环；研究、文档和运维是后续扩展方向，不作为当前已支持能力。

## 优先级原则

1. 先跑通真实任务和交付闭环，再扩展角色、并行度与后端。
2. 保留有效设计思想，组件复用由依赖和成本决定；不因旧代码存在而强制复用，也不为重写而重写。
3. 项目文件是持久事实源，看板与查询索引可重建。
4. 任务执行、验证通过、人验收分别记录，不能相互替代。
5. 小规模临时组队优先，不引入长期员工与复杂组织治理。
6. Task 是派发与用户对话入口；Markdown＋frontmatter 是任务与资源配置事实源，Run 为内部执行尝试。

## 完成的定义

实现完成至少需要：消息分类与轻路径有效；交付指令形成可校验计划；团队按需创建；任务按依赖执行；产物、diff 和验证结果可查看；失败能够进入有限返修或等待用户；待验收时释放执行资源、人工验收后记录完成；下一次指令可以继续原 Task 或创建新 Task。队列、执行中控制消息、网页断线重连与待决通知需要实际验证。

取消、超时、进程异常、并发写入与恢复行为需要明确验证。文档、界面、模拟 executor 或 worker 的成功回复，都不能单独证明闭环已完成。

## 工作约定

- 2026-10-14 本轮工作范围是保存设计与开发约束，尚未开始实现；后续实施按用户的新指令推进，不能把此阶段记录作为永久授权限制。开发规则以根目录 agent.md 为准。
- 写明确认事项、建议默认值和待验证假设，不能把候选接口写成已交付能力。
- 原始资料与运行证据保留；清理临时队伍不得删除未交付成果。
- 实施前核查待复用文件的依赖、许可与署名要求，固定依赖版本。
- 产品运行时的 SDK worker 与开发本项目时使用的代理是两件事；本设计不规定宿主开发代理的派工方式。
- 项目已于 2026-10-14 初始化 Git，默认分支 `main`，并推送设计文档、开发 backlog 与 `.agents/skills/` 技能文件；提交历史自该次初始入库开始。尚无产品代码、构建或运行产物。

## 决策日志

### 2026-10-15：整合 LG-011 前端壳层并记录批次阻塞

- 通过 pi 在独立 worktree 完成 LG-011（左侧导航与统一前端壳层），提交 `75107f0` 已完成且 worker 退出。主工作区核对干净后以 `cherry-pick` 精确带回 `main`（`1987874`），无冲突、无内容丢失、未清理任何 worktree/分支，只整合该任务成果。本批未新增镜像测试、未做独立 QA（遵 [agent.md](agent.md) 第 1 节与 [docs/06](docs/06-roadmap.md) 版本 QA 门约定）。
- LG-011 交付 `frontend/src/app/`（`AppShell`/`TopBar`/`NavigationRail`/`ShellProvider`/`uiState`/`tokens.css`/`shell.css` 等）、`frontend/src/components/` 共享组件层、`frontend/src/api/`（`types` 对齐 docs/08、`client`、`/health` 探测）与 `frontend/src/views/` 入口/占位；五工作入口靠左、底部 Settings、顶栏无一级 tabs。
- 整合检查证据：`cherry-pick` 干净；`make check-all` 通过（后端 `mypy` 无问题、pytest **133 passed**；前端 `tsc --noEmit` 无错、vitest **19 passed**）；`make frontend-build` 成功（`dist/index.html` 0.40 kB、CSS 16.59 kB、JS 171.08 kB）；`olav-tasks tasks validate` 退出码 0（**27 tasks, no diagnostics**）；任务计数 done **6**（LG-001～005、011）/ todo **21**。
- LG-011 执行者局部证据：19 个 vitest、**23/23** 无依赖真实 Chrome 浏览器检查（1440／1024／390px 抽屉，含焦点/键盘/窄屏/空错态）、`tsc`/`vite build` 通过；**未做真实后端联调**（无后端时显示真实 `Backend not connected`/`network_error`，业务端点为空态/未接入）。截图保留在 `/tmp/lg011-evidence/`（临时目录，不提交二进制）。本批活动进程核查：LG-011 预览（Vite preview `127.0.0.1:4173`）已不在运行，无本批预览服务需清理；未杀其它进程、未清理 worktree/分支。
- **阻塞与待决（不改产品契约）**：本环境 `.env` 已确认可用 DeepSeek 凭证（开发/探针用），但产品首版 Gemini Developer API／Vertex 无凭证**未认证**；用户关于“保持产品 Gemini 或把产品也改为 DeepSeek”的选择**仍未回复**。不擅自切换产品后端。LG-006 保持 `todo` 并写入 `blocked_by`（首版 Gemini 缺少认证）；未派发 LG-006，不代表不可做不依赖凭证的静态代码。
- 未知成本/耗时：pi worker 的 token/成本在本批次不可得，记录为未知；批次墙钟耗时未由执行器上报，不推算。
- 同步 README 顶部阶段事实与进展表、[docs/06](docs/06-roadmap.md) 顶部阶段、`frontend/README.md` 壳层目录与真实未接入状态；未修改 docs/08 冻结契约、未新增共享依赖、未推送、未部署。LG-011 成果标注“待版本 QA”，不代表版本验收通过。

### 2026-10-15：实现 LG-005 角色与 SDK 资源配置编译

- 按用户授权在 `backend/lightgravity/adapter/` 与 `tests/adapter/` 实现资源配置编译：解析 `skills.source/refs`、已注册 tools/hooks、connection/session profile；按 revision + content_hash 固定每个解析到的资源版本，并输出整体 `config_hash`。
- 权限不扩大：有效工具 = agent `tool_refs` ∩ Task `allowed_tools`（约束只能删不能加），预算取最严格值；MCP、Triggers、`search_web` 与 SDK 内部委派一律标记 `unavailable` 且不挂载；未注册 handler/不存在引用按 `reference_invalid`/`config_invalid` 拒绝。
- 秘密只引用：资源只允许 `credential_ref`，frontmatter 出现明文秘密字段即以 `secret_in_resource` 拒绝；编译输出经脱敏，凭证值从不落盘、日志或响应。
- 固定 SDK 版本 `google-antigravity==0.1.22`（与 LG-003 一致）加入根 `pyproject.toml`/`uv.lock`；因该 wheel 无 `py.typed`，为 `google.*` 增加 mypy `ignore_missing_imports` 覆盖。`executable` 与能力声明明确区分“配置可编译”和“后端已验证/可执行”：Gemini/Vertex 仍标记未验收，缺凭证不阻塞静态编译。
- 未改动 docs/08 冻结契约语义，未修改 `contracts`（仅 import 引用）；未实现 LG-006 executor 或 LG-007 coordinator。adapter 面向 LG-006 的编译结果接口记录在 `backend/lightgravity/adapter/README.md`。
- 局部验证：`uv run pytest tests/adapter` 51 passed、全量后端 133 passed、`uv run mypy` 无问题（34 files）。成果标注“待版本 QA”；真实 Gemini adapter 与闭环仍待具备凭证环境。本地提交，未推送、未部署。

### 2026-10-15：整合 LG-003 SDK 探针与 LG-004 存储层

- 通过 pi 并行工作包完成 LG-003、LG-004（LG-011 仍在独立 worktree 执行，本批未触碰）。两份成果提交在各自 worktree 干净；主工作区核对干净后以 `cherry-pick` 精确带回 `main`，无冲突、无内容丢失、未清理任何 worktree/分支，只整合这两个任务成果。
- LG-003：固定 `google-antigravity==0.1.22`（x86_64 Linux wheel，原生 runtime 握手成功）。核心能力以真实 DeepSeek（OpenAI-compatible 本地代理注入 bearer）有界实测通过：文件工具、结构化输出、工具事件、预算停止、取消、会话保存/恢复、skills（文件与 inline）、`read_url_content`，并记录真实沙箱状态 `SandboxStatus(available=true)`；证据与限制见 [LG-003 探针报告](probes/lg003-antigravity/reports/LG-003-report.md)。产品首版 Gemini（Developer API / Vertex）后端因本环境无 `GEMINI_API_KEY`/Vertex 凭证**未验收**；`search_web` 在非 Gemini 端点被调用但无可结果，实际不可用。DeepSeek 只是探针可达路径，**不改变 docs/08 冻结的首版 Gemini 产品契约**。
- LG-004：交付 `backend/lightgravity/store/` 与 `tests/store/`，覆盖 frontmatter 保留/重复键拒绝、Task/Run/Subtask/Member 校验与状态迁移、路径越界与符号链接逃逸、`flock` 锁/租约、原子替换与 JSONL 尾部恢复、事件 `seq` 单调与消息幂等、可重建索引。整合后局部 `pytest tests/store` 69 passed、全量后端 82 passed、`mypy` 无问题。
- 两项成果均标注“待版本 QA”，不代表版本验收通过；本次整合为执行与证据核对，主代理未做代码审查。
- 后续：LG-005 可基于 LG-004 的 `Store` 接口与 LG-003 探针结论进行角色/SDK 资源配置编译；LG-006 真实 Gemini adapter 与 LG-010 最小真实闭环仍需具备 Gemini 凭证的环境完成认证后才能验收。
- 同步 README 阶段事实；未修改产品契约、未新增共享依赖、未推送、未部署。

### 2026-10-15：建立可运行工程骨架（LG-002）

- 按用户授权完成 LG-002：建立后端 Python 3.12 + FastAPI/uvicorn/Pydantic/ruamel.yaml、前端 React 18 + TypeScript + Vite 的最小工程；依赖精确锁定在 `uv.lock` 与 `frontend/package-lock.json`。
- 新增 `backend/lightgravity/contracts`：契约常量、状态枚举、错误码与 HTTP/重试映射、错误信封、health/version DTO；作为共享只读模块供后续任务引用，不各自复制。
- 真实端点 `GET /api/v1/health`、`GET /api/v1/version` 与统一错误信封经 uvicorn 实际启动并 curl 验证；前端占位壳经 Vite dev server 启动验证。未安装 Antigravity SDK，未实现 store/adapter/coordinator/verify/settings 业务。
- 统一入口 `Makefile`：`make check`（mypy + pytest）、`make frontend-check`（tsc + vitest）、`make check-all`、`make frontend-build`。数据根 `LIGHTGRAVITY_DATA_DIR`（默认 `./bot-data`）与源码分离并 gitignore；`.env.example` 无真实凭证；路径默认相对工作目录，可分发。
- 局部实测：后端 pytest 13 passed、mypy 无问题；前端 tsc 通过、vitest 1 passed、vite build 成功。已知限制：前端 dev 依赖在 vitest 2/vite 5 范围内有 npm audit 告警，修复需升级到契约未冻结的大版本，故保留并记录。
- 为 `probes/`（LG-003）、`backend/lightgravity/store` 与 `tests/store`（LG-004）、`frontend/src` 业务子目录（LG-011 及后续）保留明确边界，未写入他人 owner 路径。成果标注“待版本 QA”。本地提交，未推送、未部署。

### 2026-10-15：冻结首版接口与状态契约（LG-001）

- 按用户授权完成 LG-001：产出 [首版接口与状态契约](docs/08-interface-contract.md)，契约版本 `1.0.0`、API 前缀 `/api/v1`、实体 schema `lightgravity.bot/v1`，冻结运行时 ID/时间约定、HTTP API 与错误语义、事件/消息契约、Task/Subtask/Run/Member 状态机与合法组合、Store 与 SDK Adapter 接口、工作区授权和后续文件归属。
- 最小技术栈选定：后端 Python 3.12 + FastAPI/uvicorn/Pydantic/ruamel.yaml（uv 管理），前端 React 18 + TypeScript + Vite，事件用 SSE，测试用 pytest/vitest/Playwright；依赖来自 PyPI/npm，精确版本由 LG-002 锁定。本次未安装依赖、未写产品代码。
- 源目录定为 `backend`、`frontend`、`probes`、`tests` 并明确所有权：LG-003 owner `probes` 与独立探针环境，LG-004 owner `backend/.../store` 与独立测试，LG-011 owner `frontend`；共享依赖/根工程文件由整合执行者（首任 LG-002）串行维护，`backend/lightgravity/contracts` 为共享只读模块。
- 在 [docs/06](docs/06-roadmap.md) 区分产品运行时顺序验证与开发并行，并定义版本 QA 门：LG-010 为原型大版本 QA 门，LG-021／022／027 为首版版本集中 QA；基础任务只做局部检查，不追加逐任务独立 QA。
- 同步 README、agent.md 的文档入口。契约与实现层的运行时验证标记为“待版本 QA”，不声称功能已验证。
- 提交本任务精确范围文档（docs/08、README、agent.md、docs/06、PROJECT、LG-001），本地提交，未推送、未部署。

### 2026-10-14：初始化 Git 并推送文档与技能

- 按用户授权在 `/home/yhvh/code/lightgravity-bot` 初始化 Git，默认分支 `main`，将设计文档、27 项 backlog 任务与 `.agents/skills/` 技能文件作为初始提交入库。
- 远端 `http://192.168.8.50:3000/admin/lightgravity-bot.git` 此前为空仓库（`empty: true`，默认分支 `main`），本次为首次推送；未 force push，未覆盖任何历史。
- 提交身份取自 Gitea 认证用户 `admin <admin@admin.com>`，仅写入仓库本地配置；未修改全局 Git 配置。
- 推送使用只从环境读取密钥的临时 askpass（权限 700），关闭持久凭证 helper，密钥不进入 URL、命令行、日志或 Git 配置，结束后清理临时文件。
- 新增最小 `.gitignore`，排除 `.env`、`.env.*`（保留 `.env.example`）、编辑器交换/备份文件、凭证与临时日志；`.env` 与 `.env.swp` 保持未跟踪。
- 提交前核对暂存文件，未发现秘密或临时文件。本次仅做文档与技能初始入库及必要检查，未开发产品功能，未执行代码审查或新增产品测试。

### 2026-10-14：项目管理与 pi 并行开发

- 用户明确要求主代理只做项目管理，不改代码、不审查代码；所有执行任务通过 pi 派出，使用 env 中的 DeepSeek API 配置。
- 开发采用并行工作包与快速原型，小任务保留必要的局部检查，大版本整合后才集中独立 QA；主代理跟踪证据与待 QA 状态。
- 具体协作规则统一维护在 agent.md 第 1 节，优先于已安装技能的原生子代理与逐任务 QA 默认流程；产品运行时的 Antigravity SDK 与验收契约保持原设计。
- 此次仅更新管理规则，未启动 pi、读取凭证或执行开发任务。

### 2026-10-14：安装项目级 Olav Tasks 技能

- 按用户要求从 `http://192.168.8.50:3000/admin/olav-tasks.git` 安装仓库提供的 6 个技能到 `.agents/skills/`，供本项目开发代理发现。
- 固定来源 commit `ab252888bd9e6dc9185a71bcf02b241484e0d4f6`，保留引用文件、MIT 许可证及逐文件 SHA-256；安装内容与来源逐文件核对一致。
- 此次安装技能文件；未安装 Olav Tasks CLI 或 SDK，未启动开发任务。

### 2026-10-14：项目建立与设计落盘

- 用户要求在 `/home/yhvh/code` 新建 `lightgravity-bot`，保存本轮讨论设计。
- 名称采用 LightGravity Bot，仓库目录采用 `lightgravity-bot`。
- 长期定位为通用 AI 助手，首版定位为按需组队的开发任务助手。
- 按轻量重设计推进，参考 Olav OS 与 Olav Tasks，不预设完整复用旧底座。
- 采用文件即事实源，提供 Chat、Board、Files 三个项目视图。
- 执行流程为分析、计划、临时组队、调度、SDK 执行、验证、有限返修、人工验收、释放队伍。
- Antigravity SDK 和 agency-agents 为拟采用组件，实际集成未验证。
- 首版建议限制为一个活跃运行、三个 worker、两个并行任务、一轮返修；不是已验收容量。
- 比赛资格未确认，产品设计与参赛判断分开管理。

### 2026-10-14：补充 skills 与基础工具设计

- 用户要求将 skills、基本文件读写与网页搜索能力写入设计。
- Role 定义职责，Skill 定义工作方法，Tool 提供实际操作；自动组队时分别绑定，技能内容不扩大权限。
- 优先使用 Antigravity SDK 原生 `skills_paths`／`inline_skills` 及内置文件、命令、搜索和 URL 读取工具，不重复实现通用能力。
- SDK 当前源码与官方示例已经核对；安装版本、runtime、技能资源访问与工具执行尚未实测。
- worker 修改工作成果；领取、状态、验收、团队释放等持久控制数据由调度器统一写入。

### 2026-10-14：Task 入口与 Markdown 资源契约

- 用户要求把 Task 目录、任务对话，以及 SDK 的 Agent、Connections、Conversation、Hooks、MCP、Tools、Triggers 纳入设计。
- Task 是用户工作单元，Subtask 是派发节点，Run 是一次执行尝试，Project 是可选的长期背景。Task 不再定义为仅存在于 Run 内的节点。
- 每个 Task 有独立目录和 TASK.md；同一任务的补充、返修与继续执行保留任务 ID 和用户对话。
- 任务、运行、团队成员、子任务和资源描述使用 Markdown＋YAML frontmatter；JSONL 用于消息与事件，SDK 原生存储用于会话恢复，不维护重复当前状态。
- frontend 按 schema/kind 渲染；adapter 校验引用与权限后把描述编译为 SDK 配置，不能把任意 Markdown 当作可执行配置。
- SDK 模块提供执行基础，业务调度、资源生命周期和持久任务状态仍由 LightGravity Bot 控制。详细契约见 docs/02。

### 2026-10-14：SDK 核心能力审计

- 用户要求核对 SDK 核心能力覆盖及 frontmatter 抽象管理的可行性。
- 核对源码快照 `91dc5f84565bb505577ac9524f107f453a6e8d1f` 与示例，补充模型配置、结构化输出、预算、重试、压缩、多模态、观测、取消和委派等映射，详见 docs/03。
- 七类资源保留，额外能力归入配置块或运行操作，不扩张成新的管理平台。
- frontmatter 管理声明和引用，adapter 承接代码与原生 session；展示配置不等于执行能力已验证。
- skills 路径/inline 在核对版本的本地后端互斥；默认能力因配置类型而不同，Bot 需要显式配置。
- 沙箱必须核对实际状态，取消必须确认真实停止；API 重试、输出重试、业务返修与 Task 总预算分别管理。
- 尚未安装 SDK 或测试 runtime；审计不扩大首版范围。

### 2026-10-14：项目更名

- 用户确定项目名为 LightGravity Bot，目录为 `/home/yhvh/code/lightgravity-bot`。
- 同步文档中的项目名、目录名、候选 schema 命名空间与技能配置目录；Olav OS、Olav Tasks 等参考项目名称保留。

### 2026-10-14：补齐常驻 Bot 行为

- 用户要求完善整体设计；新增 docs/04，补齐消息分类、直接回复/工具问答/交付执行三条路径、任务队列、需求变更、暂停取消与重连通知。
- 首版设计采用单用户本地网页入口与常驻后端，浏览器断开不取消任务；外部聊天渠道、云端公开访问与自主触发暂缓。
- 新交付需求才创建 Task，实际写操作关联 Task/Run；简单只读问答不强制组队。
- 待验收前确认 worker 停止并释放执行资源，人工验收保留为独立决定；返修按需重建团队。此决定取代早期“验收后才释放”的流程。
- Task 保留三态 status，Board/活动统计使用详细 phase；队列与验收版本以 TASK.md 为权威。
- Agent 技能字段统一为 skills.source/refs，Member 保存解析后的 skillRefs。
- 此次仅完善文档，实际能力、配置编译、进程恢复与隔离仍待实现验证。

### 2026-10-14：左侧导航与招募视图

- 用户要求一级 tab 采用 Olav OS 风格左侧布局；首版固定窄图标栏提供 Chat、Board、Files、Team，取代上方一级 tabs。
- Team 左侧资源栏提供待招募/已招募纵向入口；候选角色来自长期模板，临时成员来自 Task/Run 队伍记录。
- 当前成员与已释放历史分开显示，全局和 Task 范围有明确默认行为。
- 顶栏负责范围、面板开关与通知；资源栏、主内容和 Chat 按屏宽折叠，页面切换不重置 Task 或会话。
- 参考旧布局，不引入岗位、组织或动态插件运行时；详细交互与验收见 docs/05，仅完成设计。

### 2026-10-14：Agent 合并 Team，资源管理入口落盘

- 用户要求保存 Agent 并入 Team、其他 SDK 模块集中管理的设计。
- 左侧一级入口更新为 Chat、Board、Files、Team、Resources，取代早期四入口设计。
- Team 待招募管理 Agent 模板，已招募管理 Task/Run 临时 Member 实例；不另建 Agent 一级入口。
- Resources 左侧分类为 Connections、Session Profiles、Hooks、MCP、Tools、Triggers、Skills。Session Profiles 只管理会话配置，真实 Conversation 留在 Chat/Task/成员详情。
- 资源继续采用 Markdown/frontmatter 与 canonical 技能文件；模板声明、依赖有效与运行可用分开显示。
- 角色/成员资源引用可导航并返回，运行实例固定配置版本；资源修改不静默影响已招募队伍。
- 同步 README、docs/01、docs/02、docs/05；仅文档设计，未新增运行配置或实现页面。

### 2026-10-14：开发约束

- 用户要求根目录增加 agent.md 约束项目开发。
- agent.md 为唯一规则正文；AGENTS.md 作为自动发现入口引用它，不复制规则。
- 约束首版范围、模块职责、Markdown/frontmatter 事实源、SDK 与资源配置、执行恢复、左侧导航、验证和文档同步。
- 更新历史“当前授权”措辞为阶段记录，避免阻止后续已授权实现。此次仅写规则与文档入口。

### 2026-10-14：补充代码参考清单

- 在 agent.md 明确列出 code 下的 Olav OS、Olav Tasks、Olav 以及在线 Antigravity SDK、agency-agents。
- 记录调度、持久化与导航的具体调查入口和复用用途，要求核查依赖、实际版本与许可。
- 参考位置不成为产品运行依赖；本项目修改不自动授权修改参考仓库。此次仅补充文档。

### 2026-10-14：前端开发与风格约束

- 用户要求在根目录增加 design.md，约束前端开发与风格。
- 采用克制浅色工作台、统一 tokens/组件、固定左侧五入口与可折叠多栏；像素尺寸和颜色为实施起始建议，需实际验证。
- 首版界面标签采用英文，用户输入与产物保留原语言；默认浅色，暗色后续扩展。
- 补齐页面交互、真实状态反馈、窄屏、键盘与浏览器验收要求。
- agent.md 管总体开发规则，design.md 管前端细节；AGENTS.md 与 README 链接到两者，不复制规则。
- 仅完成约束文档，未选定/安装前端框架，也未实现或测试网页。

### 2026-10-14：Olav Tasks 首版排期

- 用户要求开始使用 olav-tasks 写排期；通过本地现有 CLI 的 tasks new 创建 LG-001～024，全部保持 todo。
- 开发任务采用 olav.tasks/v1，存放 backlog/tasks；与未来产品 lightgravity.bot/v1 的 Task/Run 目录分开。
- 建立 BACKLOG.md 和 docs/06 滚动排期，按基础探针、最小真实闭环、左侧五入口、恢复质量、完整验收组织。
- P0 优先暴露 SDK/接口风险并跑通最小闭环；P1 完成管理页、恢复与首版质量门。未分配负责人、工期或模型档位。
- 当前按阶段滚动排期，不假定每日产能或强行写日历日期；若指定演示期限需同时收敛范围。
- 首个实施候选 LG-001；SDK 真实探针需认证与预算，后续以实际情况记录阻塞。
- 此次只规划与验证任务格式/依赖，不 claim、不执行任务、不安装 SDK、不部署服务。

### 2026-10-14：文档元数据与索引补齐

- 按用户要求为 12 份普通 Markdown 补入 title、doc_type、category、updated；不使用任务或产品资源 schema，不改变文档生命周期与执行事实。
- README 补入 AGENTS.md 的链接，任务目录继续由 BACKLOG 索引；不额外建立重复总索引。
- 24 项开发任务的 ID、状态、依赖与正文保持原样。

### 2026-10-14：Settings 设计与排期

- 用户要求补入 Settings 与模型接入排期；左导航底部增加齿轮入口，五个工作入口保留。
- Models & Providers 使用类型化受保护表单，是普通资源通过 Chat 修改的例外；与 Connections 共用权威文件，默认只保存引用，秘密由独立后端管理。
- 首版先 Gemini，其他 SDK 后端标验证状态；模板/默认更改不热切换活跃 Member。
- 新增 LG-025（后端配置/凭证/测试）、LG-026（设置页）、LG-027（专项验收），总计 27 项，全部 todo。
- LG-020 接入 LG-026 的首次配置路径，LG-021 依赖 LG-027，LG-022 增加模型接入覆盖；LG-011/015 同步导航与共享引用要求。
- 新设计文档 docs/07 有文档 frontmatter，并从 README/导航/资源契约索引；任务依赖须经 CLI 校验。未保存真实密钥或启动测试。
