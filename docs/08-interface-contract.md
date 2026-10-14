---
title: "首版接口与状态契约（v1）"
doc_type: specification
category: architecture
contract_version: "1.3.0"
updated: "2026-10-15"
---

# 首版接口与状态契约（v1）

> 性质：LG-001 冻结的候选实现契约。它把 [产品与架构设计](01-design.md)、[Task 与 SDK 资源契约](02-task-and-sdk-resources.md)、[Bot 行为契约](04-bot-behavior.md)、[SDK 能力审计](03-sdk-capability-audit.md)、[导航设计](05-navigation-and-team.md)、[模型设置](07-settings-and-models.md) 收敛到可实现的接口与状态边界，不新增产品能力，也不代表功能已实现或经过运行时验证。
>
> 契约版本 `1.3.0`（2026-10-15 MINOR：登记 LG-009 验证/验收的**加性** Task `checks` 授权字段与 `acceptance` 绑定字段 `candidate_ref`/`candidate_plan_hash`/`check_records`/可选 `note`（§6.1），新增只读端点 `GET /tasks/{task_id}/acceptance`、LG-025 既有设置端点 `GET /settings/connections/{id}` 与 `PATCH /settings`、全局对话 `GET/POST /conversations/global/messages`（§4.3、§5.2），并登记 LG-014 **计划中、本轮未实现**的 `POST /files/upload` 与 `GET /files/download`；**既有端点语义、错误码、事件类型、枚举与状态迁移均未变化**，向后兼容。此前 `1.2.0` 登记 LG-008 自动组队与依赖调度使用的加性实体字段——Run `plan`/`plan_hash`/`plan_source`，Subtask `objective`/`capability`/`key`/`write`/`config_hash`/`owner`/`lease_expires_at`/`fail_reason`/`blocked_by`，见 §6.2、§6.3；`1.1.0` 明确首版唯一真实执行后端为已验收的 OpenAI-compatible `LocalOpenAIAgentConfig` → DeepSeek 路径并补充本地认证代理与凭证边界，见 §8.1；变更记录见第 13 节）。实体 schema 命名空间 `lightgravity.bot/v1`；HTTP API 前缀 `/api/v1`。变更规则见第 13 节。实现与本文冲突时以本文为准；本文未定义的行为一律视为“不支持”，实现不得自行扩展语义。运行时未知字段按“保留但不赋予执行语义”处理。

## 1. 范围

本版冻结：最小技术栈与依赖来源、目录布局、运行时 ID/时间约定、HTTP API v1 约定与错误语义、事件与消息契约、Task/Subtask/Run/Member 状态机与合法组合、Store 接口、SDK Adapter 接口、工作区授权、后续文件归属和 LG-001 验证清单。

本版不包含：具体规划/组队算法、UI 视觉实现、SDK 真实能力结论（LG-003 探针）、模型与凭证存储实现（LG-025）、部署与云端、多后端、多用户、外部渠道与自主触发。

组件边界（仅示意，不是部署图）：

```text
浏览器 ──HTTP/SSE──▶ API 层 ──▶ Coordinator/Scheduler ──▶ Store（Markdown/JSONL 事实源）
                                      │
                                      ├──▶ ExecutorAdapter ──▶ Antigravity SDK
                                      └──▶ 隔离工作区（Task 关联仓库的 worktree / 子进程）
```

## 2. 最小技术栈与依赖来源

### 2.1 选定栈

| 层 | 选择 | 版本线 | 来源 | 说明 |
|---|---|---|---|---|
| 后端运行时 | Python | `>=3.12,<3.13` | python.org / uv | 参考解释器 3.12；不使用系统默认 3.14 作为首版目标 |
| 依赖/虚拟环境 | uv | `0.12.x` | astral-sh/uv | 根目录 `pyproject.toml` + `uv.lock` 固定精确版本 |
| Web 框架 | FastAPI | `>=0.115,<0.116` | PyPI | REST + SSE，不引入 GraphQL/WebSocket |
| ASGI 服务器 | uvicorn | `>=0.30,<1` | PyPI | 默认只监听 loopback |
| 数据校验 | Pydantic | `>=2.7,<3` | PyPI | 请求/响应与 schema 校验 |
| YAML | ruamel.yaml | `>=0.18,<0.19` | PyPI | round-trip 解析、保留未知字段、拒绝重复键 |
| 后端测试 | pytest、pytest-asyncio、httpx | `pytest>=8,<9` 等 | PyPI | 单元与 API 测试 |
| 前端运行时 | Node.js | 22 LTS | nodejs.org | 参考版本 v22；`npm` 附带 |
| 前端框架 | React + react-dom | `^18.3` | npm | 函数组件 + hooks |
| 前端语言 | TypeScript | `~5.5` | npm | `strict` 开启 |
| 构建 | Vite | `^5.4` | npm | 开发服务器与生产构建 |
| 前端测试 | Vitest、@testing-library/react、jsdom | 对应 v2/v16 | npm | 组件与状态测试 |
| 浏览器 QA | Playwright | `^1.4x` | npm | 仅 LG-021/022 使用 |
| 事件推送 | Server-Sent Events（SSE） | HTTP 标准 | — | 服务端→浏览器单向；客户端操作走 REST |
| 进程模型 | 单 Python 进程（API+协调）+ worker 子进程 | — | Python stdlib | 不引入分布式调度/消息队列 |

明确不引入（首版）：数据库或 ORM（文件即事实源，索引可重建）、前端 CSS 框架或状态管理库（样式用 design.md 的 CSS variables，状态用 React context/hooks）、除 SSE 以外的实时通道、Celery/Redis 等外部队列。

### 2.2 依赖来源规则

- 所有后端依赖来自 PyPI，前端依赖来自 npm；不使用 Git 分支依赖、本地路径依赖或参考仓库直接 import。
- 精确版本写入根 `uv.lock` 与 `frontend/package-lock.json`，由整合执行者维护。
- Antigravity SDK 的固定版本与平台 wheel 由 LG-003 探针确认后，才允许加入依赖；在此之前 adapter 只定义接口，不导入 SDK。
- 任何新增依赖必须记录用途、许可证与来源；不得引入会把参考克隆或开发机绝对路径变成运行依赖的包。

### 2.3 目录布局与所有权

```text
pyproject.toml / uv.lock        # 整合执行者（Python 工程与共享依赖）
.python-version                 # 整合执行者（默认 3.12）
Makefile 或 justfile            # 整合执行者（统一 check 入口）
backend/lightgravity/
├── contracts/                  # 整合执行者：枚举、错误码、DTO（共享，禁止各自复制）
├── store/                      # LG-004：事实源解析、写入、索引、消息/事件
├── adapter/                    # LG-005/LG-006：配置编译与 Antigravity adapter
├── coordinator/                # LG-007/LG-008：消息路由、队列、调度、恢复
├── verify/                     # LG-009/LG-017：机器检查、复核与返修编排
├── settings/                   # LG-025：连接与凭证后端接口
└── api/                        # LG-012；LG-002 先放 health/version
frontend/
├── package.json / lock         # 整合执行者
└── src/
    ├── app/                    # LG-011：壳层、路由、tokens
    ├── components/             # LG-011：共享组件
    ├── api/                    # LG-011：客户端与类型（对齐本契约）
    └── views/                  # LG-013/014/015/026
probes/                         # LG-003 独占；独立探针环境，不在主 import 路径
tests/                          # 各任务拥有自己的子目录，见第 11 节
bot-data/                       # 运行数据，gitignore，不提交、不写入源码
docs/                           # 本项目设计/契约
```

- `bot-data/` 与源码分离；运行时通过 `LIGHTGRAVITY_DATA_DIR` 指定，默认 `./bot-data`（相对进程工作目录，必须 gitignore）。
- `probes/` 与 `tests/` 都不是产品包的一部分；`probes/` 可以有独立虚拟环境与依赖，不与 `backend/lightgravity/` 互相导入。
- 参考仓库（`../olav-os`、`../olav-tasks`）不作为运行依赖，也不进入 `sys.path`。

### 2.4 已核对的环境证据（LG-001 执行时）

以下为本次在本机实际观察到的版本，只证明环境可用性，不代表已安装依赖或已验证产品：

| 命令 | 实际输出 |
|---|---|
| `/home/yhvh/.local/bin/python3.12 --version` | `Python 3.12.13` |
| `uv --version` | `uv 0.12.1 (x86_64-unknown-linux-gnu)` |
| `node --version` | `v22.23.2` |
| `npm --version` | `10.9.8` |

## 3. ID、时间与命名约定

### 3.1 运行时实体 ID

运行时实体（会在用户操作/执行中动态产生）统一使用类型前缀 + ULID：

```text
<kind>_<ULID>
kind ∈ { task, run, subtask, member, conv, msg, evt, notif, req }
ULID = 26 个 Crockford Base32 字符（0-9、A-Z 去掉 I/L/O/U），按时间有序
```

- `msg_...` 由客户端生成，用于幂等；`evt_...`、`notif_...`、`req_...` 由服务端生成。
- 事件流 `stream_id` 复用其承载实体的 ID（如 `task_...`、`run_...`）。
- docs/02 §3 中的 `id: TASK-001` 是示意占位符，运行时按本节语法生成，记为 `<kind>_<ULID>`。

### 3.2 资源实体 ID

资源（可长期复用、由人或导入产生）使用稳定 slug：`[a-z0-9][a-z0-9-]{0,63}`，例如 `developer`、`antigravity-primary`。资源与新运行时实体通过 `*_ref` 字段互引，`ref` 必须能解析到存在的资源；禁止悬空引用。

### 3.3 时间与序列化

- 时间统一 ISO-8601 UTC，带 `Z` 后缀，秒级精度起（必要时毫秒），例如 `2026-10-15T00:00:00Z`。
- JSON 字段用 `snake_case`；枚举用小写 `snake_case` 字符串，不写中文或本地化文本。
- 用户可见文本（标题、消息、产物）保留原语言，不强制翻译。
- 版本号：`revision` 为实体文件写入版本，非负整数，每次成功提交 +1；`requirements_revision` 只在目标/范围/验收发生实质变化时 +1；`contract_version` 用 `MAJOR.MINOR.PATCH`。

## 4. HTTP API v1 契约

### 4.1 通用约定

- 基路径 `/api/v1`。破坏性变更只能发布 `/api/v2`，不得静默改字段语义。
- 成功响应返回资源或集合本身；集合分页用 `?limit=&cursor=`，响应含 `items` 与 `next_cursor`（`null` 表示结束）。
- 错误统一返回错误信封（见 4.2），HTTP 状态码与 `code` 对应。
- 修改型请求必须携带 `expected_revision`（乐观并发）；响应携带 `ETag: "<revision>"`。
- 幂等：客户端生成 `message_id`/`request_id`；服务端对相同键返回首次结果，不重复产生副作用。
- 本地认证：默认只监听 loopback；非 loopback 必须携带本地访问令牌（请求头 `X-LG-Token`），令牌来源由 LG-020 定义。凭证管理接口额外要求同源/受保护来源，不接受网页预览或普通聊天调用。

### 4.2 错误信封与错误码

```json
{
  "error": {
    "code": "revision_conflict",
    "message": "human readable",
    "details": { "expected_revision": 3, "actual_revision": 4 },
    "retryable": false,
    "request_id": "req_01J..."
  }
}
```

| code | HTTP | retryable | 语义 |
|---|---|---|---|
| `invalid_request` | 400 | 否 | 请求体/参数格式错误 |
| `unauthorized` | 401 | 否 | 缺少或无效本地访问令牌 |
| `path_outside_workspace` | 403 | 否 | 路径越界或符号链接逃逸 |
| `not_found` | 404 | 否 | 实体不存在 |
| `revision_conflict` | 409 | 否 | 乐观并发版本不匹配，须重读 |
| `lock_conflict` | 409 | 是 | 实体锁/任务租约被占用，退避重试 |
| `not_ready` | 409 | 否 | 依赖未满足或尚未排队 |
| `illegal_transition` | 409 | 否 | 非法状态/阶段组合或不允许的动作 |
| `cancellation_unconfirmed` | 409 | 是 | 请求的暂停/取消尚未确认停止 |
| `acceptance_stale` | 409 | 否 | 验收绑定的需求/交付版本已过期 |
| `config_invalid` | 422 | 否 | frontmatter/schema/重复键/字段组合非法 |
| `reference_invalid` | 422 | 否 | 引用不存在或类型不符 |
| `validation_failed` | 422 | 否 | 请求未通过 schema 校验 |
| `budget_exhausted` | 429 | 否 | 达到预算/时限/返修上限 |
| `capability_unavailable` | 503 | 是 | SDK/模型/沙箱等运行能力不可用 |
| `internal_error` | 500 | 未知 | 未预期错误，附 `request_id` |

### 4.3 核心端点（v1 冻结）

| 方法与路径 | 用途 | 归属任务 | 状态 |
|---|---|---|---|
| `GET /api/v1/health` | 进程存活、版本、能力概览 | LG-002 | 冻结 |
| `GET /api/v1/version` | 契约版本、schema 版本、构建信息 | LG-002 | 冻结 |
| `GET /api/v1/tasks` | Task 列表（分页/阶段筛选） | LG-012 | 冻结 |
| `POST /api/v1/tasks` | 创建 Task（幂等：`request_id`） | LG-007/LG-012 | 冻结 |
| `GET /api/v1/tasks/{task_id}` | Task 详情（含 phase/queue/acceptance） | LG-012 | 冻结 |
| `PATCH /api/v1/tasks/{task_id}` | 更新标题/范围等（`expected_revision`） | LG-012 | 冻结 |
| `POST /api/v1/tasks/{task_id}/messages` | 追加用户消息（幂等：`message_id`） | LG-007 | 冻结 |
| `GET /api/v1/tasks/{task_id}/messages` | 读取 Task 对话（游标） | LG-007 | 冻结 |
| `GET /api/v1/tasks/{task_id}/events` | 读取 Task 事件（`after_seq`/游标） | LG-012 | 冻结 |
| `GET /api/v1/events/stream` | SSE 事件订阅（`?cursor=`，支持 `Last-Event-ID`） | LG-012 | 冻结 |
| `POST /api/v1/tasks/{task_id}/actions` | 控制动作：入队/暂停/恢复/取消/重试/验收/拒绝/重开 | LG-009/LG-016 | 冻结（动作语义见第 9 节；accept/reject 由 verify 服务处理） |
| `GET /api/v1/tasks/{task_id}/acceptance` | 候选与验收快照（只读） | LG-009/LG-012 | 冻结 |
| `GET /api/v1/tasks/{task_id}/artifacts` | 候选产物与证据引用 | LG-014 | 冻结 |
| `GET /api/v1/files`、`GET /api/v1/files/content` | 根目录受限的文件树与内容（只读） | LG-014 | 冻结 |
| `POST /api/v1/files/upload` | 有界二进制上传（`path`/`expected_revision`，授权目录内） | LG-014 | **planned（尚未实现）** |
| `GET /api/v1/files/download` | 有界文件下载（授权目录内，附 revision） | LG-014 | **planned（尚未实现）** |
| `GET /api/v1/resources/{kind}`、`GET /api/v1/resources/{kind}/{id}` | 资源列表与详情（读取/诊断） | LG-015 | 冻结 |
| `GET/POST/PATCH /api/v1/settings/connections` | 连接配置（同一权威文件） | LG-025 | 冻结 |
| `GET /api/v1/settings/connections/{id}` | 单个连接详情（不回显秘密） | LG-025 | 冻结 |
| `PATCH /api/v1/settings` | 设置默认 coordinator/worker 连接引用（`expected_revision`） | LG-025 | 冻结 |
| `POST /api/v1/settings/connections/{id}/test` | 分层连接测试 | LG-025 | 冻结 |
| `PUT/DELETE /api/v1/settings/credentials/{ref}` | 凭证引用写入/移除（不回显秘密） | LG-025 | 冻结 |
| `GET/POST /api/v1/notifications` | 未读通知列表与标记已读 | LG-019 | 冻结 |
| `GET /api/v1/conversations/global/messages` | 全局对话消息（游标；仅 singleton global） | 整合/LG-007 | 冻结 |
| `POST /api/v1/conversations/global/messages` | 追加全局消息（幂等：`message_id`/`request_id`） | 整合/LG-007 | 冻结 |
| `GET /api/v1/settings` | 默认连接引用与偏好 | LG-026/LG-025 | 冻结 |

> `planned` 行只冻结将来的路径与最小语义，**当前实现不提供该端点**；调用方应以 `404`/`not_ready` 如实处理，不得假定已可用。

控制动作请求体（`POST .../actions`）：

```json
{
  "action": "cancel",
  "request_id": "req_01J...",
  "expected_revision": 7,
  "target_run_id": "run_01J...",
  "decision": null,
  "note": null
}
```

`action ∈ {enqueue, pause, resume, cancel, retry, accept, reject, reopen}`。响应返回控制记录：

```json
{ "action": "cancel", "state": "cancelling", "confirmed": false, "task_id": "task_01J...", "request_id": "req_01J..." }
```

`state ∈ {requested, confirmed, unconfirmed}`；取消/暂停只有在 `confirmed=true` 时才写终止阶段（见第 9 节）。

`accept`/`reject` 为加性请求字段 `expected_requirements_revision` 与 `expected_deliverable_revision`（可选）：决策绑定 Task 的 `requirements_revision`、`deliverable_revision` 与 `acceptance.candidate_ref`；不匹配返回 `acceptance_stale`，相同 `request_id` 幂等返回首次结果（见 §6.1、§9）。`GET /tasks/{task_id}/acceptance` 返回当前候选与验收快照（只读，无副作用）。

### 4.4 SSE 事件流

- `GET /api/v1/events/stream` 返回 `text/event-stream`，每帧 `id` 为不透明游标 `v1:<stream_id>:<seq>`，`event` 为事件类型，`data` 为事件 JSON。
- 断线重连：客户端带 `Last-Event-ID` 或 `?cursor=`，服务端从该游标之后补齐，不重复、不跳号（游标语义见 5.1）。
- 浏览器断开不取消后台任务；SSE 只是订阅通道，控制仍通过 REST。

## 5. 事件与消息契约

### 5.1 事件

事件写入 `events.jsonl`（每 Task/Run 一个流，追加写）。事件信封：

```json
{
  "schema": "lightgravity.bot/v1",
  "kind": "event",
  "event_id": "evt_01J...",
  "stream_id": "task_01J...",
  "seq": 42,
  "type": "task.phase_changed",
  "at": "2026-10-15T00:00:00Z",
  "actor": "coordinator",
  "task_ref": "task_01J...",
  "run_ref": null,
  "payload": { "from": "planning", "to": "executing" }
}
```

- `seq` 在单个 `stream_id` 内从 1 开始单调递增、无空洞；游标 `v1:<stream_id>:<seq>` 指向“已读到 seq”。
- 事件只追加、不修改、不删除；查询视图可重建。
- 事件类型（v1 冻结最小集）：`task.created`、`task.phase_changed`、`task.status_changed`、`task.requirements_changed`、`queue.enqueued`、`queue.claimed`、`queue.released`、`run.created`、`run.state_changed`、`subtask.state_changed`、`member.recruited`、`member.state_changed`、`member.released`、`message.appended`、`decision.requested`、`decision.resolved`、`artifact.produced`、`cleanup.updated`、`notification.created`、`error.recorded`。
- 新增事件类型属于 MINOR 变更（第 13 节）；消费方必须忽略未知类型而不是报错崩溃。

### 5.2 消息

用户与 Bot 消息写入 Task `conversation.jsonl`；全局对话写入 `bot-data/conversations/<conversation-id>/messages.jsonl`。消息信封：

```json
{
  "schema": "lightgravity.bot/v1",
  "kind": "message",
  "message_id": "msg_01J...",
  "task_ref": "task_01J...",
  "conversation_ref": "conv_01J...",
  "role": "user",
  "at": "2026-10-15T00:00:00Z",
  "content": "把示例页面改成…",
  "attachments": [{ "path": "inputs/a.png", "media_type": "image/png" }],
  "correlation_id": "req_01J...",
  "in_reply_to": null
}
```

- 幂等键为 `message_id`：同一 `message_id` 重复提交返回已存消息，不重复建 Task、不重复执行。
- 消息是历史事实，不承载当前状态；当前状态只在 TASK.md/RUN.md 等 frontmatter。
- 执行中的状态查询与控制消息不排队等待代码任务结束。
- 全局对话（`GET/POST /api/v1/conversations/global/messages`）只暴露**单例 global 会话**；`POST` 以 `message_id` 幂等，可选 `request_id` 作为控制副作用第二道幂等键；`workspace_ref`/`agent_ref` 来源受限——只接受服务端已授权的 workspace（经 `Store.resolve_path` 限制在授权根内）与已知 agent 引用，越界或不存在返回 `path_outside_workspace`/`reference_invalid`，不允许浏览器直接指定任意执行身份。该端点只做消息持久与路由，不新建会话平台。

## 6. 实体状态契约

状态机字段与枚举以本节为准；docs/01、02、04、05 的枚举与此一致。状态只在权威文件的 frontmatter 维护，索引/看板/通知不得另建状态。

### 6.1 Task

`status ∈ {todo, in-progress, done}`（沿用 [docs/02](02-task-and-sdk-resources.md) 的连字符写法；phase 用 snake_case）。
`phase ∈ {intake, queued, waiting_dependencies, planning, recruiting, executing, verifying, repairing, waiting_user, pausing, paused, cancelling, awaiting_acceptance, recovery_required, failed, cancelled, completed}`。

Task frontmatter（v1 冻结字段）：

```yaml
schema: lightgravity.bot/v1
kind: task
id: task_01J...
title: "为示例网站增加登录功能"
status: todo
phase: intake
revision: 0
requirements_revision: 1
project_ref: null
repository_ref: null
workspace_ref: null
agent_ref: coordinator
depends_on: []
active_run: null
deliverable_revision: 0
queue:
  state: not_queued        # not_queued | queued | claimed
  order: null
  queued_at: null
  owner: null
  lease_expires_at: null
acceptance:
  status: pending          # pending | awaiting | accepted | rejected
  requirements_revision: null
  deliverable_revision: null
  evidence_refs: []
  decided_at: null
  decision_ref: null
  candidate_ref: null         # 加性：候选 Run 引用，决策绑定到具体候选
  candidate_plan_hash: null   # 加性：候选计划的 plan_hash（若可取得）
  check_records: []           # 加性：机器检查结果（check_id/status/detail）
  note: null                  # 加性：人工决定备注（可选）
checks: []                  # 加性：授权运行的已注册机器检查 id 列表；未声明则无检查
budget:
  max_workers: 3
  max_parallel: 2
  max_repair_rounds: 1
archived: false
```

合法组合（`status + phase`）：

| status | 允许的 phase |
|---|---|
| `todo` | `intake`、`queued`、`waiting_dependencies`、`cancelled`（未启动即取消） |
| `in-progress` | `planning`、`recruiting`、`executing`、`verifying`、`repairing`、`waiting_user`、`pausing`、`paused`、`cancelling`、`awaiting_acceptance`、`recovery_required`、`failed`、`cancelled` |
| `done` | `completed` |

禁止组合示例：`done + executing`、`todo + executing`、`done + failed`。只有人工验收通过才能置 `done`；失败/取消的已启动任务保留 `in-progress`。

Task 阶段迁移（仅允许下列方向；`cancelling`/`pausing` 需确认停止后进入终态）：

```text
intake                → queued | waiting_dependencies | cancelled
queued                → planning | waiting_dependencies | cancelled
waiting_dependencies  → queued | cancelled
planning              → recruiting | waiting_user | failed | cancelling
recruiting            → executing | waiting_user | failed | cancelling
executing             → verifying | waiting_user | pausing | cancelling | failed | recovery_required
verifying             → repairing | awaiting_acceptance | waiting_user | failed | cancelling
repairing             → executing | waiting_user | failed | cancelling
waiting_user          → queued | planning | paused | cancelling | failed
pausing               → paused | cancelling | failed
paused                → queued | planning | cancelling
cancelling            → cancelled            # 仅确认停止后
awaiting_acceptance   → completed | repairing | cancelled
recovery_required     → planning | failed | cancelled
failed                → queued | cancelled
cancelled             → queued               # 仅显式重试
completed             → queued | planning    # 仅显式重开，requirements_revision +1
```

- `deliverable_revision` 在某个 Run 进入 `awaiting_acceptance`（产生候选交付）时 +1。
- 验收有效条件：`acceptance.status == accepted` 且 `acceptance.requirements_revision == task.requirements_revision` 且 `acceptance.deliverable_revision == task.deliverable_revision`。任一不等即失效；`requirements_revision` 增加时把 `status` 重置为 `pending`，保留旧证据。
- `checks` 为加性可选字段：只列出程序**已注册**的机器检查 id；Task 未声明时运行零个检查（如实为空，不将“无检查”当作通过），授权但未注册的检查记为 `unconfigured` 且不运行。`acceptance.candidate_ref`/`candidate_plan_hash`/`check_records`/`note` 为加性可选字段，分别记录候选 Run 引用、候选计划哈希、机器检查结果与决定备注；既有 `requirements_revision`/`deliverable_revision`/`evidence_refs` 绑定语义不变，决策必须同时匹配 `candidate_ref`。
- `queue.state` 与 phase 的关系：进入 `queued` 前置 `queue.state=queued` 并写 `order`/`queued_at`；领取成功后 `claimed` 并写 `owner`/`lease_expires_at`；进入终态或暂停时释放租约并回到 `not_queued`。`waiting_dependencies` 不入队。

### 6.2 Run

`state ∈ {planning, recruiting, executing, verifying, awaiting_acceptance, completed, waiting_user, pausing, paused, recovery_required, failed, cancelling, cancelled}`。

```yaml
schema: lightgravity.bot/v1
kind: run
id: run_01J...
task_ref: task_01J...
attempt: 1
state: planning
revision: 0
plan_ref: PLAN.md
plan: null               # 校验后的计划（source/notes/subtasks），dispatcher 写入
plan_hash: null          # plan 规范化 JSON 的 SHA-256，冻结派发时的计划版本
plan_source: null        # 计划来源标记（如 rules / model）
team_refs: []
subtask_refs: []
session_refs: []
cleanup:
  status: pending          # pending | running | done | failed
ended_at: null
fail_reason: null
```

- 一个 Task 同时最多一个非终止 Run（`active_run`）。
- `plan`/`plan_hash`/`plan_source` 为加性可选字段：计划先经程序校验，校验通过的完整计划（含每个子任务的 `key`/`objective`/`capability`/`acceptance`/`depends_on`/`write`/`order`）才写入 `plan`，`plan_hash` 为该内容的规范化 SHA-256，`plan_source` 只记录来源、不赋予额外权限；未通过校验的提议不落盘。既有 `plan_ref`（计划文件引用）语义不变。
- `completed` 与 `cancelled`/`failed` 是不同终态；team cleanup 状态独立记录，清理失败不得掩盖交付成功。
- `cancelling` → `cancelled` 仅在 adapter 确认停止后。

### 6.3 Subtask

`state ∈ {pending, ready, running, verifying, passed, repairing, waiting_user, paused, failed, cancelled}`。

```yaml
schema: lightgravity.bot/v1
kind: subtask
id: subtask_01J...
run_ref: run_01J...
state: pending
revision: 0
depends_on: []
assignee_member_ref: null
upstream_artifact_refs: []
objective: null          # 该 Subtask 的目标（来自已校验计划）
capability: null         # 所需能力；RoleCatalog 据此选择最小团队
key: null                # 计划内局部 slug（唯一），不是运行时 ID
write: false             # 是否写工作区；同一工作区 write 节点串行
config_hash: null        # 节点运行配置冻结哈希（节点定义 + 成员 config_hash）
owner: null              # 当前执行租约持有者
lease_expires_at: null   # 执行租约到期时间
fail_reason: null        # 失败/阻塞原因
blocked_by: []           # 阻塞它的上游失败 Subtask 运行时 ID
acceptance:
  status: pending          # pending | passed | failed | blocked
  criteria: []
  evidence_refs: []
```

`passed` 只表示子任务验证通过，不等于 Task 验收；依赖放行必须传递上游产物引用与版本/哈希。

- `objective`/`capability`/`key`/`write` 为加性可选字段，来自已校验计划；`key` 仅在计划内唯一，不是运行时 ID；`write=true` 的节点写工作区，同一工作区 write 节点串行（§7 单 writer）。
- `config_hash` 冻结节点运行配置（节点定义与 `member_config_hash` 的组合）；派发前重编译并比对，漂移按 `config_invalid` 失败，不静默换配置。
- `owner`/`lease_expires_at` 是 Subtask 执行租约，与 Task `queue` 租约是不同层面的租约：领取幂等、按 `owner` 互斥、过期可回收、终态拒绝领取。
- `fail_reason` 记录失败原因；`blocked_by` 列出使其阻塞的上游失败 Subtask 运行时 ID，被阻塞节点 `acceptance.status=blocked`，不得伪造 `passed`。
- 上述字段均为加性可选字段，不改变本节既有 `state`、`acceptance.status` 枚举与迁移语义。

### 6.4 Member

`state ∈ {recruiting, ready, running, released, waiting_user, failed}`。

```yaml
schema: lightgravity.bot/v1
kind: member
id: member_01J...
run_ref: run_01J...
role_ref: developer
state: recruiting
revision: 0
template_version: "1"
connection_ref: null
skill_refs: []
session_ref: null
tool_policy: {}
workspace_ref: null
assigned_subtask_refs: []
budget: {}
```

- 模板修改只影响后续招募；已招募 Member 固定解析后的 `connection_ref`、`skill_refs`、配置版本/哈希与 `tool_policy`。
- `released` 为正常终止；`failed` 需保留 `fail_reason`。恢复时创建新 Member，并记录来源。

### 6.5 资源与设置

资源（Agent、Connection、Conversation 配置、Hook、MCP、Tool、Trigger、Skill）通用字段：`schema: lightgravity.bot/v1`、`kind`、`id`、`title`、`enabled`、`revision`。Connection 只保存 `credential_ref`，不保存秘密；全局默认引用在 `bot-data/settings/SETTINGS.md`（`kind: settings`，含 `default_coordinator_connection_ref`、`default_worker_connection_ref`、`revision`）。资源 schema 细节沿用 [docs/02](02-task-and-sdk-resources.md)。

## 7. Store 接口（文件事实源）

Store 是唯一控制状态写入者；worker/adapter 不得直接编辑 TASK.md/RUN.md 等控制文件。接口以 Python `Protocol` 表达（LG-004 实现，LG-002 建骨架）：

```python
class Store(Protocol):
    def read(self, kind: str, entity_id: str) -> Versioned: ...
    def create(self, kind: str, entity_id: str, content: dict, *, actor: str,
               request_id: str) -> Versioned: ...
    def write(self, kind: str, entity_id: str, content: dict, *,
              expected_revision: int | None, actor: str) -> Versioned: ...

    def append_event(self, stream_id: str, event: dict) -> EventRecord: ...
    def read_events(self, stream_id: str, *, after_seq: int = 0,
                    limit: int = 500) -> list[EventRecord]: ...

    def append_message(self, task_id: str, message: dict) -> MessageRecord: ...  # 幂等：message_id
    def read_messages(self, task_id: str, *, after: str | None = None,
                      limit: int = 200) -> list[MessageRecord]: ...

    def claim(self, task_id: str, owner: str, *, lease_seconds: int) -> ClaimResult: ...
    def renew(self, task_id: str, owner: str, *, lease_seconds: int) -> bool: ...
    def release(self, task_id: str, owner: str) -> None: ...

    def list_tasks(self) -> list[TaskSummary]: ...
    def rebuild_index(self) -> IndexReport: ...
    def resolve_path(self, relative: str, *, write: bool) -> Path: ...  # 越界抛 PathOutsideWorkspace
```

`Versioned` 含 `entity`、`revision`、`content_hash`。语义约束：

- **原子写入**：同目录临时文件 + `fsync` + `os.replace`；提交时若 `expected_revision` 与当前不一致，抛 `RevisionConflict`，不覆盖。
- **锁/租约**：读-改-写期间对实体加短时文件锁（`fcntl.flock`）；任务领取用 `owner` + `lease_expires_at`。冲突抛 `LockConflict`（可重试），`expected_revision=None` 仅用于首次创建。
- **revision**：整数，每次成功提交恰好 +1；写 `requirements_revision` 由调用方显式控制，Store 不自动改。
- **部分写入恢复**：启动时清理残留临时文件；JSONL 尾部若为不完整行则截断到最后一条完整记录并记 `error.recorded`；不静默重放副作用不明确的任务。
- **索引**：内存/可重建索引只是派生视图，可从权威文件重建（`rebuild_index`）；不得成为第二份状态事实源。
- **路径授权**：`resolve_path` 拒绝 `..` 逃逸、越界绝对路径、解析后落在授权根之外的符号链接（`realpath` 检查）；只读/可写由调用方声明，且不得越过授权根。
- **未知字段**：写入保留正文与未知 frontmatter 字段，不因解析丢字段。

## 8. SDK Adapter 接口

adapter 是唯一导入 Antigravity SDK 的位置；Store 与上层不感知 SDK 类型。

```python
class ExecutorAdapter(Protocol):
    name: str
    version: str
    def capabilities(self) -> AdapterCapabilities: ...
    async def execute(self, request: ExecuteRequest, emit: EventSink) -> ExecutorResult: ...
    async def cancel(self, execution_ref: ExecutionRef) -> CancelResult: ...
    async def close(self, session_ref: SessionRef) -> None: ...
```

- `ExecuteRequest`（由协调器构造，非用户直接传入）：`task_id`、`run_id`、`subtask_id`、`attempt`、`objective`、`acceptance_criteria`、`instructions`、`upstream_artifact_refs`、`workspace_path`、`allowed_tools`、`skill_refs`、`connection_ref`、`timeout_seconds`、`budget`。
- `ExecutorResult`：`state ∈ {succeeded, failed, blocked, cancelled, budget_exhausted, timeout}`、`summary`、`artifact_refs`、`diff_ref`、`check_records`、`session_ref`、`failure{code,message}`、`usage`（实际可取得字段，取不到的键列入 `usage.unknown`）、`stop_reason`。
- `CancelResult`：`confirmed: bool`、`state`、`reason`。`confirmed=false` 时调用方不得写 `cancelled`（见第 9 节）。
- `AdapterCapabilities`：声明 `cancel`、`resume`、`usage`、`structured_output`、`sandbox`、`skills_paths`、`inline_skills`、`subagents` 等支持情况；未知即声明为 `false`/`unknown`，上层据此显示真实可用性，不假设所有后端一致。

边界规则：

- adapter 不写控制状态（领取、阶段、验收、队伍释放由 Store/协调器负责）；只通过 `emit` 上报规范化事件。
- worker 自报成功只进入验证，不得直接成为 done/passed。
- SDK 内部委派默认关闭；`enable_subagents` 未显式纳入同一预算/事件边界前不得开启。
- 同一 Agent 不能同时设置 `skills_paths` 与 `inline_skills`；adapter 负责校验并报 `config_invalid`。
- 沙箱：adapter 必须暴露实际 `sandbox_status`；不支持时如实报告，不静默降级后宣称隔离。
- SDK 原生 session 只作恢复参考，恢复能力以 LG-003 探针结论为准。

### 8.1 首版执行后端与本地认证代理（1.1.0）

- 首版唯一真实执行路径固定为 `google-antigravity==0.1.22` + `LocalOpenAIAgentConfig`（注册后端 `openai-compat`，只有 `base_url`、没有 `api_key` 字段）+ loopback 认证代理接 DeepSeek；不新增 SDK，不引入第二个执行框架，不新增通用多厂商平台。
- 本地认证代理由 LG-006 作为**产品代码**实现，是 executor adapter 的运行组件：只监听 loopback；只从进程环境或受控 secret store 的 `credential_ref` 解析凭证；不读取、不回显、不记录完整秘密；明确定义启动/停止/失败生命周期，停止需确认（stop confirmed）后才写终止状态，残留代理/worker 进程必须清理。
- 产品不得复制或依赖 LG-003 探针、参考仓库或开发机绝对路径作为运行必需依赖；产品认证代理是独立实现，不是探针脚本。
- 凭证来源只允许进程环境（如运行环境已注入的 DeepSeek key）或受控 secret store 的 `credential_ref`；不假设项目 `.env` 一定含可用 key。adapter 不把“config built”当作“已认证”；执行就绪以 `CompiledAgentConfig.executable`、实际 session 建立与认证结果共同判定。
- 首版首选模型为 `deepseek-v4-flash`；LG-006 必须记录并验证实际发送给 SDK 的 model ID 与 `base_url`。LG-003 SDK 探针当时使用 `deepseek-chat`，未实测的版本串（例如“4.1”）不得写成可用 API ID。
- `AdapterCapabilities` 首版声明 `probe_verified_backends=("openai_compat",)`、`unverified_backends=("gemini", "vertex")`、`search_web=false`；执行能力以 LG-003 实测为准。
- Gemini Developer API 与 Vertex 在该路径下未验收，不得作为默认可执行连接；`search_web` 继续标记 `unavailable`；Vertex、LiteRT、`custom_endpoint` 等其它后端未验收，不得默认执行。

## 9. 关键错误与动作语义

- **配置失败**：解析/校验失败时不写入任何状态，返回 `config_invalid`（附诊断列表）；Task/Run 保持不变。凭证值永不进入响应、日志、事件或错误详情。
- **并发冲突**：同一实体并发写返回 `revision_conflict`（附 `expected_revision`/`actual_revision`/最新 `ETag`），调用方必须重读合并，禁止 last-write-wins。任务领取/锁冲突返回可重试的 `lock_conflict`。
- **取消/暂停未确认**：动作先阻止新调度，再调用 adapter `cancel`。`confirmed=false` 或超时返回 `cancellation_unconfirmed`，Task 阶段保持 `cancelling`/`pausing`，绝不写 `cancelled`/`paused`，保留资源与恢复点，允许重试。只有 `confirmed=true` 才写终止阶段并释放槽位。
- **依赖未满足**：`not_ready`；不得提前领取或伪造 ready。非法 `status+phase` 或不允许的迁移返回 `illegal_transition`，不落盘。
- **能力不可用**：`capability_unavailable`（503）附缺失能力清单；`/health` 与页面区分致命故障与仅影响可选能力，缺模型认证仍可浏览历史。
- **预算停止**：达到预算/时限/返修上限写 `budget_exhausted`；停止原因不得解释为工作完成。
- **验收过期/重复**：`acceptance_stale` 或幂等返回；过期决定不作用于新版本；重复提交相同 `request_id` 幂等。
- **部分写入**：Store 保证单文件原子性；跨文件操作以写入标识/日志 + 恢复扫描处理，不宣称跨文件事务。

## 10. 工作区授权与安全边界

- 数据根 `LIGHTGRAVITY_DATA_DIR`（默认 `./bot-data`）与源码分离并 gitignore；秘密存储 `LIGHTGRAVITY_SECRET_STORE` 位于仓库与任务目录之外。
- 授权工作区根 `LIGHTGRAVITY_WORKSPACE_ROOT`（默认 `<data_dir>/workspaces`）；Task `workspace_ref` 必须解析到授权根内。
- 所有路径操作经 `Store.resolve_path`：拒绝绝对路径越界、`../` 逃逸、以及 `realpath` 落在根外的符号链接；不可访问返回 `path_outside_workspace`（403）。
- Files/预览只读，不获得执行权限；Markdown/HTML 预览不执行脚本、不连接 MCP、不启动 Trigger。
- executor 的写权限仅限其 worktree；共享目录不替代隔离，代码并行写用独立 worktree。
- 默认只监听 loopback；凭证接口不接受网页预览/跨站/聊天调用；`credential_ref` 只保存引用。
- 资源 `enabled: true` 只表示声明启用，不等于已连接/可用；健康检查与启用必须走获准接口，不因渲染或解析自动执行。

## 11. 后续文件归属

单一 writer 原则：同一文件同一时间只有一个执行者写入；共享文件由整合执行者串行维护。

| 范围 | Owner（任务） | 说明 |
|---|---|---|
| 根 `pyproject.toml`、`uv.lock`、`.python-version`、`Makefile`、`.gitignore` | 整合执行者（首任 LG-002） | 共享 Python 依赖与统一 check 入口 |
| `frontend/package.json`、`frontend/package-lock.json` | 整合执行者 | 共享前端依赖 |
| `backend/lightgravity/contracts/**` | 整合执行者 | 枚举/错误码/DTO，其他任务只读引用，禁止复制 |
| `backend/lightgravity/store/**`、`tests/store/**` | LG-004 | 事实源与独立测试 |
| `backend/lightgravity/adapter/**`、`tests/adapter/**` | LG-005、LG-006 | 配置编译与 Antigravity adapter |
| `backend/lightgravity/coordinator/**` | LG-007、LG-008 | 消息路由、队列、调度 |
| `backend/lightgravity/verify/**` | LG-009、LG-017 | 验证与返修编排 |
| `backend/lightgravity/api/**`、`tests/api/**` | LG-012；LG-002 仅 health/version；LG-025 加 settings | 查询/事件/行动接口 |
| `backend/lightgravity/settings/**` | LG-025 | 连接与凭证后端 |
| `frontend/**` | LG-011 | 壳层、组件、API 客户端；视图由 LG-013/014/015/026 在 `src/views/` 内扩展 |
| `probes/**` | LG-003 | 独立探针环境，不进入主包 import 路径 |
| `tests/e2e/**` | LG-021、LG-022 | 浏览器与端到端验收 |
| `docs/08-interface-contract.md` | LG-001 | 契约变更按第 13 节流程 |

跨任务需要修改他人 owner 文件时，必须由整合执行者串行接线，或经主代理协调后指定临时 owner；不得并发改同一文件。

## 12. LG-001 验证清单

LG-001 自身的可机械/可复核检查（实现层验证属于后续任务与版本 QA）：

- [ ] 契约版本与 `/api/v1`、`lightgravity.bot/v1` 在本文一致声明（LG-001 冻结 `1.0.0`；当前 `1.3.0`，变更记录见第 13 节）。
- [ ] ID 语法、时间格式、命名约定明确，且与 docs/02 资源示例的差异有说明。
- [ ] API 端点表覆盖首版所需路径，错误码表覆盖配置失败、冲突、取消未确认、能力不可用、验收过期。
- [ ] Task/Subtask/Run/Member 状态枚举、合法组合与迁移方向齐备，无 `done + executing` 类矛盾。
- [ ] Store 与 Adapter 接口、原子写入/恢复、职责边界明确。
- [ ] 工作区授权与安全边界明确（路径越界、只读预览、凭证引用、loopback）。
- [ ] 文件归属表覆盖 backend/frontend/probes/tests 与共享依赖。
- [ ] 最小技术栈含来源与版本线，且未安装任何依赖、未写产品代码。
- [ ] 文档内链接与 README/agent.md/docs/06 的契约引用可解析。
- [ ] `olav-tasks tasks validate` 退出码 0（见第 13 节证据）。

## 13. 变更控制与证据

- 契约版本：新增向后兼容字段/事件类型为 MINOR；改字段语义、枚举、状态迁移或删除端点为 MAJOR，必须同步 README、agent.md、docs/06 与相关设计，并记录迁移影响。
- 变更记录：

| 版本 | 日期 | 级别 | 变更 | API/实体字段影响 |
|---|---|---|---|---|
| `1.3.0` | 2026-10-15 | MINOR | 登记 LG-009 验证/验收的加性 Task `checks` 授权字段与 `acceptance` 绑定字段 `candidate_ref`/`candidate_plan_hash`/`check_records`/`note`（§6.1）；新增 `GET /tasks/{task_id}/acceptance`、`GET /settings/connections/{id}`、`PATCH /settings`、`GET/POST /conversations/global/messages`；登记 LG-014 planned 的 `POST /files/upload`/`GET /files/download`（§4.3、§5.2） | 仅新增可选实体字段与端点；既有端点语义、错误码、事件类型、枚举与状态迁移未变化 |
| `1.2.0` | 2026-10-15 | MINOR | 登记 LG-008 自动组队与依赖调度使用的加性控制字段：Run `plan`/`plan_hash`/`plan_source`；Subtask `objective`/`capability`/`key`/`write`/`config_hash`/`owner`/`lease_expires_at`/`fail_reason`/`blocked_by`（§6.2、§6.3） | 仅新增可选实体字段；端点、错误码、事件类型、枚举与状态迁移未变化 |
| `1.1.0` | 2026-10-15 | MINOR | 首版真实后端由未验收的 Gemini 改为已验收的 `openai-compat`（`LocalOpenAIAgentConfig`）→ DeepSeek 路径；新增本地认证代理与凭证/生命周期边界（§8.1）；Gemini/Vertex 标为未验收、不作默认 | 无：端点、错误码、事件类型、实体字段、枚举与状态迁移均未变化 |
| `1.0.0` | 2026-10-15 | — | LG-001 初始冻结 | — |

- 变更必须先更新本文件与受影响设计文档，再进入实现；实现不得先于契约扩展语义。
- 运行时行为、SDK 兼容性与界面验收分别记录实际证据；契约存在不等于功能已验证。LG-001 只交付契约文档与局部检查，不安装依赖、不写产品代码、不启动服务。
- 实现证据与版本 QA 记录在对应任务正文；本契约层的“待版本 QA”项：

| 待验证项 | 由谁验证 |
|---|---|
| API/错误码/幂等/SSE 契约符合实现 | LG-012、LG-022 |
| Store 原子写入、冲突、恢复 | LG-004、LG-022 |
| Adapter 能力声明、取消确认、沙箱状态 | LG-003、LG-006、LG-016、LG-022 |
| 状态机合法组合与看板展示一致 | LG-013、LG-021 |
| 凭证/设置边界与脱敏 | LG-025、LG-027 |

## 参考

- [产品与架构设计](01-design.md)
- [Task 与 SDK 资源契约](02-task-and-sdk-resources.md)
- [SDK 能力审计](03-sdk-capability-audit.md)
- [Bot 行为契约](04-bot-behavior.md)
- [左侧导航、Team 与 Resources](05-navigation-and-team.md)
- [滚动排期与验收门](06-roadmap.md)
- [Settings、模型接入与凭证管理](07-settings-and-models.md)
- [前端约束](../design.md)
- [开发约束](../agent.md)
