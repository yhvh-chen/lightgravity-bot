---
title: "首版接口与状态契约（v1）"
doc_type: specification
category: architecture
contract_version: "1.10.0"
updated: "2026-10-16"
---

# 首版接口与状态契约（v1）

> 性质：LG-001 冻结的候选实现契约。它把 [产品与架构设计](01-design.md)、[Task 与 SDK 资源契约](02-task-and-sdk-resources.md)、[Bot 行为契约](04-bot-behavior.md)、[SDK 能力审计](03-sdk-capability-audit.md)、[导航设计](05-navigation-and-team.md)、[模型设置](07-settings-and-models.md) 收敛到可实现的接口与状态边界，不新增产品能力，也不代表功能已实现或经过运行时验证。
>
> 契约版本 `1.10.0`（2026-10-16 MINOR：LG-022 第二轮针对性返修（REFIX-R2）的加性 MINOR，全部为**加性可选、非秘密**变更。① **停止门可接受真实停止事实**（§9）：成功 Run 记录真实 `session_refs`/reviewer 资源时，`cleanup` 常为 `pending`；停止门现在除 `cleanup=done` 外也接受**权威适配器停止确认事实**（SDK session 的 `Agent.__aexit__` / loopback 代理的真实关闭结果）作为 session/reviewer 已停止的证明，`run` 实体加性新增可选 `reviewer_cleanup`（`{status,confirmed,...}`，默认缺省即无事实）。未知/仍活跃/关闭失败/损坏一律保持 `unconfirmed` 与保留 `session_refs`，**不假装已停止、不伪造 `cleanup=done`**。② `GET /api/v1/diagnostics/generation`（§4.3）加性新增 `persistent`（及持久账本损坏时的 `corrupt`/`reason`）字段：全局生成计数改为**受控 dataRoot 下的持久账本**（append-only JSONL 事实源 + 可重建原子计数快照），**转发前持久预留**，跨 worker/reviewer/session/进程重启不归零；账本损坏/不可读时**拒绝转发并报 unknown，绝不当 0**；仅记计数与最小非秘密元数据，不落输入/prompt/header/凭证/grant。**不新增端点、枚举、迁移方向或错误码**，不改变 `state`/`phase`/`acceptance` 枚举；不新增供应商、秘密表单或常驻编排 agent。此前 `1.9.0`（2026-10-16 MINOR：首版 review 生命周期返修后的串行集成收拢，全部为**加性可选、非秘密**变更。① `source` 实体新增加性布尔字段 `archived`（默认 `false`）与 `POST /sources/{id}/actions` 新增 `archive`/`unarchive` 两个**可逆整理**动作（§4.3、§6.6）：归档**保留**来源/作用域/权限/检索与打开能力，仅把资料移出默认列表；它**不是**使资料不可用的 `revoke`（后者仍写 `status=archived` 并失效命中）。动作请求体新增可选 `expected_revision`（乐观并发，冲突 `409 revision_conflict`）。② 新增只读/显式可选向量端点 `GET /vector/status`、`GET /vector/search`、`POST /vector/rebuild`（§4.3、§6.6），默认禁用、后端仅由环境变量配置、候选仍回源核对；向量不可用时词法检索与原件查看照常可用。**不改变** `revoke`/`delete` 既有语义，不新增事件类型，不改变 `state`/`phase`/`acceptance`/`source.status` 枚举，不新增供应商、秘密表单或常驻编排 agent。此前 `1.8.0`（2026-10-16 MINOR：LG-022 首版集中 QA 阻断项 D1/D2 返修 R1。① **状态迁移加性扩展**：新增合法方向 `verifying → recovery_required` 与 `repairing → recovery_required`（§6.1），用于独立复核/返修阶段进程重启后未知副作用诚实进入人工恢复，**不重放、不假终态**；既有方向与语义不变。② 新增只读诊断端点 `GET /api/v1/diagnostics/generation`（§4.3），报告**进程全局**上游生成请求计数 `{count, limit, remaining}`（`limit` 来自 `LIGHTGRAVITY_MAX_GENERATION_CALLS`，`None` 仅计数不设上限），覆盖全部 worker session/independent reviewer/SDK 重试，**转发前计数**，使集中 QA 可真实约束与观测全局硬上限而非 unknown；不暴露凭证/prompt。D1（reviewer turn 在运行中事件循环内 `asyncio.run` → `unavailable`）为**实现修复**（reviewer turn 移出协调器循环），D2（复核阻塞循环、无 reviewer 生命周期）为**实现修复 + 生命周期确认**，二者不改变端点/错误码/既有字段语义。**不新增供应商、秘密表单或供应商切换。** 此前 `1.7.0`（2026-10-16 MINOR：LG-017 返修 R1，全部为**加性可选、非秘密**变更——新增设置角色/字段 `default_reviewer_connection_ref`（§6.5，独立复核者默认连接，默认 `null`）、Task 返修账本加性字段 `reviewer`/`reviewer_kind`/`model_usage`（§6.1）、review/rework 事件加性 payload `reviewer_kind`/`model_calls`/`usage`（§5.1，未知用量计 `unknown`、**不得当 0**），并明确独立复核语义（§9：`verifying` 须经独立 reviewer 才进入 `awaiting_acceptance`；程序机器检查是机器门，**不等于**独立复核；无可用真实 reviewer 时报告 `unavailable` 并**阻止 accept**，不消耗返修轮、不假 pass；模型输出经程序 `validate_findings` 绑定可解析候选证据，**不能直接判 done**）。**不新增/改变端点、错误码、`state`/`phase`/`acceptance` 枚举、迁移方向与既有字段语义；不新增供应商、秘密表单或供应商切换。** 此前 `1.6.0`（2026-10-16 MINOR：串行冻结 LG-028 去中心化协作与 LG-033 资料摄取/检索两条**尚未实现**的新线契约，全部为**加性可选**字段、端点、事件与错误码，**默认关闭**且不改变既有 `state`/`phase` 枚举、迁移方向与错误码语义；`fence`、`claim_request`/`collab_request`、`source`/`intake_job` 及相应端点/事件/错误码**仅冻结接口，不代表已实现或可用**；去中心化版本（LG-032）与资料版本（LG-040）集中 QA 前不得宣称通过，见 §4.3、§5.1、§6.2、§6.3、§6.6、§13）。此前 `1.5.0`（2026-10-15 MINOR：登记 LG-020 的**加性、非秘密**字段 `connection_pin`（Run 与 Member 实体，§6.2、§6.4），用于在 Run 招募时冻结默认 worker 连接（ref + revision + content_hash + 不透明 `credential_version`），使活跃 Run 内默认连接或凭证轮换不得在下一 Subtask 静默换用（漂移按 `config_invalid` 失败，新 Run 重新解析）；**不落盘任何秘密**，既有端点语义、错误码、事件类型、枚举与状态迁移均未变化，向后兼容。此前 `1.4.0`（2026-10-15 MINOR：登记 LG-015 Team/Resources 的**加性**受控写入端点 `PATCH /resources/{kind}/{id}`、只读端点 `GET /team/available`/`GET /team/members`，以及 Task 消息信封新增可选字段 `resource_proposal` 与回写 `resource_result.status`（§4.3、§5.2），用于把有界资源修改提议经 Task 对话由协调器程序校验后调用 `ResourceService.update`；**既有端点语义、错误码、事件类型、枚举与状态迁移均未变化**，向后兼容）；此前 `1.3.1`（2026-10-15 PATCH：将 `1.3.0` 登记的 `POST /files/upload`/`GET /files/download` 由 **planned** 标记为**已实现**（§4.3，revision 语义与外部改动复核限制见该节），并明确机器检查证据引用的解析语义——workspace 相对引用仅按授权 workspace 根解析，executor 产物证据由协调器导入 Task/Run 拥有的 evidence 根并以 `evidence:<run_id>/<name>@sha256:<hex>` 规范化解析，原始绝对路径一律拒绝）；此前 `1.3.0` 登记 LG-009 的加性 Task `checks` 授权字段与 `acceptance` 绑定字段 `candidate_ref`/`candidate_plan_hash`/`check_records`/`note`（§6.1），新增只读端点 `GET /tasks/{task_id}/acceptance`、LG-025 设置端点 `GET /settings/connections/{id}` 与 `PATCH /settings`、全局对话 `GET/POST /conversations/global/messages`（§4.3、§5.2）；`1.2.0` 登记 LG-008 自动组队与依赖调度使用的加性实体字段——Run `plan`/`plan_hash`/`plan_source`，Subtask `objective`/`capability`/`key`/`write`/`config_hash`/`owner`/`lease_expires_at`/`fail_reason`/`blocked_by`，见 §6.2、§6.3；`1.1.0` 明确首版唯一真实执行后端为已验收的 OpenAI-compatible `LocalOpenAIAgentConfig` → DeepSeek 路径并补充本地认证代理与凭证边界，见 §8.1；变更记录见第 13 节）。实体 schema 命名空间 `lightgravity.bot/v1`；HTTP API 前缀 `/api/v1`。变更规则见第 13 节。实现与本文冲突时以本文为准；本文未定义的行为一律视为“不支持”，实现不得自行扩展语义。运行时未知字段按“保留但不赋予执行语义”处理。

## 1. 范围

本版冻结：最小技术栈与依赖来源、目录布局、运行时 ID/时间约定、HTTP API v1 约定与错误语义、事件与消息契约、Task/Subtask/Run/Member 状态机与合法组合、Store 接口、SDK Adapter 接口、工作区授权、后续文件归属和 LG-001 验证清单。

本版不包含：具体规划/组队算法、UI 视觉实现、SDK 真实能力结论（LG-003 探针）、模型与凭证存储实现（LG-025）、部署与云端、多后端、多用户、外部渠道与自主触发。

资料/知识库接入的**接口**已于 `1.6.0` MINOR 冻结（LG-033）：新实体 `source`/`intake_job`（§6.6）、摄取/检索端点（§4.3）、事件（§5.1）与错误码（§4.2）。该冻结**只定义接口**，**不代表任何资料/摄取/检索/向量能力已实现或可用**；现有文件上传/下载端点（§4.3）语义不变，是当前唯一相关实现。实现分工见 §6.6 与 [资料接入与检索设计](09-source-intake-and-retrieval.md)。

去中心化协作的**接口**已于 `1.6.0` MINOR 冻结（LG-028）：Subtask 加性字段 `fence`（§6.3）、发现/领取/续租/释放/协作端点（§4.3）、事件（§5.1）与错误码（§4.2）；默认路径仍为程序确定性调度（`plan_source=rules`），去中心化路径**默认关闭**。该冻结**只定义接口**，**不代表发现/领取/协作/租约 fencing 已实现或可用**。

两条新线共享本文与 §4.3/§5.1/§6 相关段落，已由**单一 docs08 owner 串行冻结**；后续实现不得先于本版契约扩展语义。

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
kind ∈ { task, run, subtask, member, conv, msg, evt, notif, req, source, intake }
ULID = 26 个 Crockford Base32 字符（0-9、A-Z 去掉 I/L/O/U），按时间有序
```

- `msg_...` 由客户端生成，用于幂等；`evt_...`、`notif_...`、`req_...` 由服务端生成。`source_...`（资料记录）与 `intake_...`（摄取作业）为 `1.6.0` 新增类型前缀（LG-033，§6.6），实体前缀 `source`/`intake`。
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
- 本地认证：默认只监听 loopback；非 loopback 必须携带本地访问令牌（请求头 `X-LG-Token`），令牌来源由 LG-020 定义。凭证管理接口额外要求同源/受保护来源，不接受网页预览或普通聊天调用。令牌只由**运行时注入**（进程环境/启动注入，或服务启动时生成并只交给本机前端握手）；不写入仓库、文档、日志、URL、localStorage/IndexedDB 或 Markdown 正文。页面需要的只是运行时可用性（是否已配置、请求头名），不是令牌值。设置类写接口在未注入令牌时**默认拒绝**（`unauthorized`），前端不得通过开放该默认值来“打通”设置页。首次启动的前端握手与令牌交接**尚未实现**，归 LG-020；当前不得把“默认拒绝”或“本地可用”当作已完成启动接入。

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
| `stale_lease` | 409 | 否 | 写回携带的 `fence` 不等于当前租约 `fence`（旧持有者/过期回收后写回），拒绝且不落盘（§6.3，LG-028） |
| `claim_refused` | 409 | 否 | 候选领取请求被程序拒绝（能力不符/不可发现/竞争/非法），附稳定 `reason`（§6.3，LG-028） |
| `source_conflict` | 409 | 否 | 同一 `request_id` 的资料接入请求 payload 不同（§6.6，LG-033） |
| `source_stale` | 409 | 否 | 候选命中回源时源版本/内容哈希已变（§6.6，LG-033） |
| `index_unavailable` | 503 | 是 | 索引损坏或处理中；词法降级仍可用或明确不可用，不返回悬空结果（§6.6，LG-033） |
| `internal_error` | 500 | 未知 | 未预期错误，附 `request_id` |

### 4.3 核心端点（v1 冻结）

| 方法与路径 | 用途 | 归属任务 | 状态 |
|---|---|---|---|
| `GET /api/v1/health` | 进程存活、版本、能力概览 | LG-002 | 冻结 |
| `GET /api/v1/version` | 契约版本、schema 版本、构建信息 | LG-002 | 冻结 |
| `GET /api/v1/diagnostics/generation` | 持久全局上游生成请求计数 `{generation:{count,limit,remaining,persistent[,corrupt,reason]}}`（`limit` 来自 `LIGHTGRAVITY_MAX_GENERATION_CALLS`，`None` 仅计数；`persistent` 指示受控 dataRoot 下的持久账本，损坏时另报 `corrupt`/`reason`；仅计数/上限，不含凭证或 prompt） | LG-022 R1/R2 | 已实现（R1 `1.8.0`；R2 持久账本加性字段 `1.10.0`） |
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
| `GET /api/v1/tasks/{task_id}/artifacts` | 候选产物与证据引用（含 Store 拥有的 Task/Run evidence 根中的 canonical evidence） | LG-014/整合 | 冻结 |
| `GET /api/v1/tasks/{task_id}/artifacts/content` | 预览一个 canonical evidence 产物（`evidence_ref` 限定为 `evidence:<run_id>/<name>@sha256:<hex>`） | 整合 | 冻结 |
| `GET /api/v1/tasks/{task_id}/artifacts/download` | 下载同一 evidence 产物（附 stat 型 revision；拒绝原始绝对路径/跨 Task/跨 Run/摘要不符） | 整合 | 冻结 |
| `GET /api/v1/files`、`GET /api/v1/files/content` | 根目录受限的文件树与内容（只读） | LG-014 | 冻结 |
| `POST /api/v1/files/upload` | 有界二进制上传（`path`/`expected_revision`，授权目录内） | LG-014 | 冻结（revision 为 `size-mtime_ns` 变更令牌） |
| `GET /api/v1/files/download` | 有界文件下载（授权目录内，附 revision） | LG-014 | 冻结（revision 同上） |
| `GET /api/v1/resources/{kind}`、`GET /api/v1/resources/{kind}/{id}` | 资源列表与详情（读取/诊断） | LG-015 | 冻结 |
| `PATCH /api/v1/resources/{kind}/{id}` | 非 connection 资源的受控修改（allow-list 字段 + adapter schema 校验 + 引用解析 + `expected_revision`；connection 被拒并指向 Settings） | LG-015 | 冻结 |
| `GET /api/v1/team/available` | Agent 模板与编译可用性（只读） | LG-015 | 冻结 |
| `GET /api/v1/team/members` | Member 实例（当前与 released 历史，可按 `task_ref`/`run_ref` 过滤） | LG-015 | 冻结 |
| `GET/POST/PATCH /api/v1/settings/connections` | 连接配置（同一权威文件） | LG-025 | 冻结 |
| `GET /api/v1/settings/connections/{id}` | 单个连接详情（不回显秘密） | LG-025 | 冻结 |
| `PATCH /api/v1/settings` | 设置默认 coordinator/worker 连接引用（`expected_revision`） | LG-025 | 冻结 |
| `POST /api/v1/settings/connections/{id}/test` | 分层连接测试 | LG-025 | 冻结 |
| `PUT/DELETE /api/v1/settings/credentials/{ref}` | 凭证引用写入/移除（不回显秘密） | LG-025 | 冻结 |
| `GET/POST /api/v1/notifications` | 未读通知列表与标记已读 | LG-019 | 冻结 |
| `GET /api/v1/conversations/global/messages` | 全局对话消息（游标；仅 singleton global） | 整合/LG-007 | 冻结 |
| `POST /api/v1/conversations/global/messages` | 追加全局消息（幂等：`message_id`/`request_id`） | 整合/LG-007 | 冻结 |
| `GET /api/v1/settings` | 默认连接引用与偏好 | LG-026/LG-025 | 冻结 |
| `GET /api/v1/runs/{run_id}/discoverable` | worker 可发现候选投影（只读，按 Member 过滤） | LG-029 | 已实现并运行时接线（默认关闭；真实执行身份接线于 LG-031；待版本 QA LG-032） |
| `POST /api/v1/runs/{run_id}/claim_requests` | 提交候选领取请求（幂等 `request_id`） | LG-029 | 已实现并运行时接线（默认关闭；真实执行身份接线于 LG-031；待版本 QA LG-032） |
| `POST /api/v1/subtasks/{subtask_id}/lease/renew` | 续租（`owner`+`lease_seconds`） | LG-029 | 已实现并运行时接线（默认关闭；真实执行身份接线于 LG-031；待版本 QA LG-032） |
| `POST /api/v1/subtasks/{subtask_id}/lease/release` | 主动释放（仅持有者或程序） | LG-029 | 已实现并运行时接线（默认关闭；真实执行身份接线于 LG-031；待版本 QA LG-032） |
| `POST /api/v1/runs/{run_id}/collab_requests` | 受控同伴请求（幂等 `request_id`；须经程序认证执行身份） | LG-030 | 已实现并运行时接线（默认关闭；真实执行身份接线于 LG-031；待版本 QA LG-032） |
| `GET /api/v1/runs/{run_id}/collab_requests` | 协作请求与结果（只读，游标） | LG-030 | 已实现并运行时接线（默认关闭；真实执行身份接线于 LG-031；待版本 QA LG-032） |
| `POST /api/v1/sources` | 登记一次资料接入请求（幂等 `request_id`；只登记+落盘原件，不创建 Task/Run） | LG-034 | 已实现（待版本 QA LG-040；未实现提取/OCR/索引） |
| `GET /api/v1/sources` | 资料列表（分页/作用域过滤；只返回已授权资料） | LG-034 | 已实现（待版本 QA LG-040） |
| `GET /api/v1/sources/{source_id}` | 资料详情（状态/派生/正式版本引用；不回显越界路径） | LG-034 | 已实现（待版本 QA LG-040） |
| `GET /api/v1/sources/{source_id}/receipt` | 最近逐文件回执（与 Files 同一份状态） | LG-034 | 已实现（待版本 QA LG-040） |
| `GET /api/v1/sources/{source_id}/content` | 预览正式内容/原件（只读；经 `resolve_path` 授权，不执行脚本） | LG-035/036 | 已实现（LG-035；待版本 QA LG-040） |
| `GET /api/v1/sources/{source_id}/download` | 下载原件/正式内容（附 stat 型 revision，**非密码学哈希**） | LG-035/036 | 已实现（LG-035；待版本 QA LG-040） |
| `POST /api/v1/sources/{source_id}/actions` | 控制动作：`reprocess`/`cancel`/`archive`/`unarchive`/`revoke`/`delete`（`archive`/`unarchive` 为**可逆整理**，保留检索/打开与权限；`revoke` 使资料不可用并失效命中；`delete` 需确认；`reprocess` 不覆盖人工校订；可选 `expected_revision` 乐观并发） | LG-035/036/038 | 已实现（LG-035；`archive`/`unarchive` 于 `1.9.0` 加性实现；待版本 QA LG-040） |
| `GET /api/v1/vector/status` | 可选向量索引诚实状态（`enabled`/`model`/cache 元数据/不可用原因）；**不调用远端服务** | LG-037 | 已实现（`1.9.0` 集成挂载；默认禁用；待版本 QA LG-040） |
| `GET /api/v1/vector/search` | 可选向量检索 + 回源核对；后端/缓存不可用 → `index_unavailable`、`lexical_fallback=true`、`hits=[]`（词法/原件仍可用）；GET 只读 | LG-037 | 已实现（`1.9.0`；默认禁用；待版本 QA LG-040） |
| `POST /api/v1/vector/rebuild` | 从文件 SoT 删除并重建向量缓存（`?source_id=` 可选）；不启动独立向量库 | LG-037 | 已实现（`1.9.0`；默认禁用；待版本 QA LG-040） |
| `GET /api/v1/intake/jobs/{job_id}` | 摄取作业状态（逻辑视图，非第二套状态库） | LG-034 | 已实现（待版本 QA LG-040） |
| `POST /api/v1/intake/jobs/{job_id}/actions` | `cancel`/`retry`（未知副作用中断**不自动重放**） | LG-034 | 已实现（待版本 QA LG-040） |
| `GET /api/v1/search` | 词法优先检索（授权过滤；命中**必须回源核对**） | LG-036 | 已实现（2026-10-16 集成挂载；待版本 QA LG-040；无向量、无 Chat/Files UI） |
| `POST /api/v1/inbox/messages`（或复用全局对话） | 归属未知资料入受控收件区（全局上传**不强建 Task**） | LG-034/038 | 已实现（LG-034 受控收件区；待版本 QA LG-040） |

> `planned` 行只冻结将来的路径与最小语义，**当前实现不提供该端点**；调用方应以 `404`/`not_ready` 如实处理，不得假定已可用。本版无剩余 `planned` 行。
>
> **1.6.0 冻结但未实现的新线端点**：上表“冻结接口（未实现…）”行是 LG-028 与 LG-033 的**契约冻结点**——只固定路径与最小语义，**端点可能尚未注册或返回 `not_ready`/`404`**，不得假定已可用；去中心化端点默认关闭（见 §6.3 开关）。实现分别归 LG-029/030（去中心化）与 LG-034～038（资料）；集中 QA 前不得宣称通过。worker 侧调用须经受控执行身份，不接受浏览器直接指定任意 `owner`；资料端点不创建交付 Task/Run。
>
> **执行身份边界（`1.7.0` 集成澄清，无字段/端点变化）**：`POST /runs/{run_id}/collab_requests`（LG-030）要求**程序认证的**执行身份：`ApiContext.worker_identity` 接缝解析出的已认证 Member 必须与请求体的 `from_member_ref` 一致，否则**默认拒绝**（`claim_refused`，`reason=unauthenticated`/`identity_mismatch`，不落盘、不消耗预算）。**请求体自报身份永不作为认证**。真实 worker 身份注入（协调器注入已认证 Member）属 LG-031；接缝已就位，默认拒绝保护边界。所有去中心化端点**默认关闭**，关闭时行为与确定性 `plan_source=rules` 调度一致。
>
> 文件端点说明（1.3.1）：`POST /files/upload`/`GET /files/download` 已实现，上传为有界 body、`path`+`expected_revision` 冲突检测、原子替换并拒绝 `..`/符号链接/secret store 越界；下载为有界流式并在读取前复核 revision。`revision` 是 `size-mtime_ns` 变更令牌（**非密码学哈希**）；跨进程外部改动只在同一 `flock` 范围内、读取与替换前做二次复核，属**尽力而为**，不构成跨进程事务或强一致保证。
>
> 证据产物说明（1.5.0）：executor 产物由协调器导入 Store 拥有的 Task/Run evidence 根（`<data_dir>/tasks/<task_id>/artifacts/<run_id>/<name>`）并规范化为 `evidence:<run_id>/<name>@sha256:<hex>`；该根**不在 workspace 根下**，因此 `GET /tasks/{task_id}/artifacts` 独立列出它并附各自授权的引用，`.../artifacts/content` 与 `.../artifacts/download` 仅接受该 canonical 引用，经 Task/Run evidence resolver 校验 Task 归属、Run 归属、路径/符号链接包含与摘要后读取；原始绝对路径、跨 Task/跨 Run 或摘要不符一律拒绝。预览与下载共用同一 stat 型 `revision`。

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
- `1.6.0` 加性新增（LG-028 去中心化，默认关闭）：`subtask.lease_granted`、`subtask.lease_renewed`、`subtask.lease_expired`、`subtask.lease_revoked`、`subtask.claim_refused`、`collab.requested`、`collab.resolved`、`handoff.produced`、`handoff.rejected`；`payload` 可含 `subtask_ref`/`owner`/`fence`/`reason`（如适用）。
- `1.7.0` 加性 payload（LG-017 R1，`error.recorded` 的 review/rework 事件）：`mode`（`review`/`rework`）、`outcome`、`reviewer`、`reviewer_kind ∈ {program, model, unavailable}`、`model_calls`、`usage`（未知计 `unknown`）、`findings`/`unsubstantiated` 数量。仅新增加性 payload 字段，不新增事件类型、不改变既有字段语义。
- `1.6.0` 加性新增（LG-033 资料摄取，未实现）：`source.received`、`source.version_changed`、`source.attributed`、`source.indexed`、`source.invalidated`、`source.deleted`、`intake.stage_changed`、`intake.receipt`、`intake.failed`、`intake.cancelled`。**LG-034 已实现并实际产生** `source.received`、`source.version_changed`、`intake.stage_changed`、`intake.failed`、`intake.cancelled`；**LG-035 另已实现并实际产生** `source.attributed`（成功/部分提取）与 `intake.failed`（失败）；**LG-036 另已实现并实际产生** `source.indexed`（正式内容重建入库）与 `source.invalidated`（撤销/删除/校订后旧命中失效）；其余（`source.deleted`/`intake.receipt`）随 LG-037～038 实现，当前不得假定产生（`source.deleted` 不单独产生：实体移除时以 `source.invalidated` 加 `reason=deleted` 代替）。
- 新增事件类型属于 MINOR 变更（第 13 节）；消费方必须忽略未知类型而不是报错崩溃。去中心化事件（LG-028）与未实现资料事件**仍仅冻结**，实际未产生；实现前不得假定可消费。

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
- Task 消息信封可携带**加性可选字段** `resource_proposal`（`{kind, id, expected_revision, patch, body}`）：它是程序结构而非自然语言，只接受已认证的 `role=user` Task 消息。协调器在写入前完成 allow-list、adapter schema、引用解析与 `expected_revision` 校验，再调用 `ResourceService.update`；实际结果/冲突写回同一 Task 对话（`message.appended`，回写 assistant 消息附 `resource_result.status`，取值 `applied`/`conflict`/`rejected`/`invalid_proposal`/`unauthorized_source`），不创建 Run、不等待代码任务、不让 model/worker 直接写控制。连接类资源仍走 Settings。
- 全局对话（`GET/POST /api/v1/conversations/global/messages`）只暴露**单例 global 会话**；`POST` 以 `message_id` 幂等，可选 `request_id` 作为控制副作用第二道幂等键；`workspace_ref`/`agent_ref` 来源受限——只接受服务端已授权的 workspace（经 `Store.resolve_path` 限制在授权根内）与已知 agent 引用，越界或不存在返回 `path_outside_workspace`/`reference_invalid`，不允许浏览器直接指定任意执行身份。该端点只做消息持久与路由，不新建会话平台。
- 资料接入消息（`1.6.0`，LG-033，未实现）：资料消息可复用现有 `attachments`（`{path, media_type}`），**不新增**与 `resource_proposal` 混淆的字段；`resource_proposal` 仅用于受控资源写，不用于资料摄取。上传文件/消息的 frontmatter **不是**受信 Task/资源配置或指令，未知字段保留但**不获得执行语义**（不得 import/eval、不得启动 MCP/Trigger、不得改控制状态，§6.6）。

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
- `1.7.0` 加性 QA/返修账本（LG-017 R1，非秘密）：Task 加性可选字段 `rework`（`review_rounds`/`repair_rounds_spent`/`sdk_retries`/`outcomes`/`last_findings`/`last_candidate_ref`/`history`，以及本轮新增 `reviewer`/`reviewer_kind`/`model_usage`）与 `review_findings`（活跃返修 Run 的目标）。`reviewer_kind ∈ {program, model, unavailable}` 明确区分**程序机器门**与**真实独立模型复核**；`model_usage` 记录真实模型用量，未知计 `unknown`，**不得当 0**。`review_rounds` 由可选 `budget.max_review_rounds`（默认上限 8）约束；`repair_rounds_spent` 由既有 `budget.max_repair_rounds` 在**整个 Task 生命周期**约束，新 Run 不重置；`sdk_retries` 只计 SDK/适配器重试，不是业务返修轮。
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
connection_pin: null     # 加性、非秘密：本 Run 冻结的默认 worker 连接
team_refs: []
subtask_refs: []
session_refs: []
cleanup:
  status: pending          # pending | running | done | failed
ended_at: null
fail_reason: null
```

- 一个 Task 同时最多一个非终止 Run（`active_run`）。
- `plan`/`plan_hash`/`plan_source` 为加性可选字段：计划先经程序校验，校验通过的完整计划（含每个子任务的 `key`/`objective`/`capability`/`acceptance`/`depends_on`/`write`/`order`）才写入 `plan`，`plan_hash` 为该内容的规范化 SHA-256，`plan_source` 只记录来源、不赋予额外权限；未通过校验的提议不落盘。既有 `plan_ref`（计划文件引用）语义不变。默认计划由程序按明确目标生成（`plan_source=rules`，确定性最小计划、无模型调用）；可选的模型拆解提议是**有界按需**能力，当前未接线、无默认装配，仅在显式记录触发原因时采纳，候选计划仍经同一程序校验；该按需提议的**单 Run** 调用上限由程序按内部请求预算落实（失败尝试计入，重复派发同一 Run 不新开模型循环），不使用跨 Run 的实例全局计数。此为默认策略澄清，不新增字段/端点/事件，不改变本版既有语义。
- `connection_pin` 为加性可选字段（1.5.0）：Run 招募团队时解析一次当前默认 worker 连接并按 `{connection_id, revision, content_hash, credential_version}` 冻结，供该 Run 的所有 Subtask 复用；活跃 Run 内默认连接或凭证轮换不得在下一 Subtask 静默换用，检测到漂移按 `config_invalid` 失败，新 Run 才重新解析。该字段**永不包含秘密**，不改变既有连接选择优先级（显式模板 `connection_ref` 仍优先）。
- `completed` 与 `cancelled`/`failed` 是不同终态；team cleanup 状态独立记录，清理失败不得掩盖交付成功。
- `cancelling` → `cancelled` 仅在 adapter 确认停止后。
- 去中心化协作预算与恢复（`1.6.0`，LG-028，默认关闭）：协作/领取请求受 Task 总预算、`max_workers`/`max_parallel`/`max_repair_rounds` 与协作次数/超时约束，全部计入**同一** Task/Run 预算；worker 不得创建新 Run/Task 或无限递归协作。租约过期/崩溃后，对 `write=true` 或**未知副作用**的节点**不自动重放**，进入既有 `recovery_required`（该状态已在上述枚举中，**不新增迁移方向**）；恢复仅依赖已落盘证据，**完整 checkpoint skip 尚未实现**。

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
fence: 0                 # 加性（1.6.0，LG-028）：租约 fencing 计数，单调递增
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
- `fence` 为加性可选字段（`1.6.0`，LG-028）：整数，单调递增，每次成功授予/回收 `+1`；旧持有者写回、产物交接、事件 emit 与 Member 释放必须校验 `fence == 当前 fence`，不匹配返回 `stale_lease` 且不落盘（fencing 拒绝，**非 last-write-wins**）。**租约过期不等于执行已停止**：过期仅表示可重新授予，对有副作用的节点不得自动重跑，须进入 `recovery_required`。旧实体无 `fence` 时按 `fence=0` 处理并给诊断，不阻断执行。`owner`/`lease_expires_at`/`fence` 均为加性，不改变本节 `state`/`acceptance.status` 枚举与迁移方向。
- `fail_reason` 记录失败原因；`blocked_by` 列出使其阻塞的上游失败 Subtask 运行时 ID，被阻塞节点 `acceptance.status=blocked`，不得伪造 `passed`。
- 上述字段均为加性可选字段，不改变本节既有 `state`、`acceptance.status` 枚举与迁移语义。
- `evidence_refs` 的解析语义（1.3.1）：workspace 产物为相对授权 workspace 根的路径；executor 产物（如 diff）由协调器导入 `<data_dir>/tasks/<task_id>/artifacts/<run_id>/` 并记录为 `evidence:<run_id>/<name>@sha256:<hex>`。机器检查只解析这两类授权命名空间，并校验 Task/Run 归属、路径/符号链接包含与内容摘要；**原始绝对路径一律拒绝，不作为 workspace 相对路径解析**。

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
connection_pin: null   # 加性、非秘密：选中连接的 ref/revision/content_hash/不透明凭证版本
skill_refs: []
session_ref: null
tool_policy: {}
workspace_ref: null
assigned_subtask_refs: []
budget: {}
```

- 模板修改只影响后续招募；已招募 Member 固定解析后的 `connection_ref`、`skill_refs`、配置版本/哈希与 `tool_policy`。
- 加性字段 `connection_pin` 记录 Run 招募时选定的默认连接与不透明 `credential_version`（永不包含秘密）；活跃 Run 内默认连接或凭证轮换不得在下一 Subtask 静默换用，检测到漂移按 `config_invalid` 失败，新 Run 重新解析。
- `released` 为正常终止；`failed` 需保留 `fail_reason`。恢复时创建新 Member，并记录来源。

### 6.5 资源与设置

资源（Agent、Connection、Conversation 配置、Hook、MCP、Tool、Trigger、Skill）通用字段：`schema: lightgravity.bot/v1`、`kind`、`id`、`title`、`enabled`、`revision`。Connection 只保存 `credential_ref`，不保存秘密；全局默认引用在 `bot-data/settings/SETTINGS.md`（`kind: settings`，含 `default_coordinator_connection_ref`、`default_worker_connection_ref`、`default_reviewer_connection_ref`、`revision`）。资源 schema 细节沿用 [docs/02](02-task-and-sdk-resources.md)。

- `1.7.0` 加性设置项（LG-017 返修 R1）：`default_reviewer_connection_ref`（默认 `null`）。它是**独立复核者**的默认连接，对应与 `coordinator`/`worker` 并列的独立角色 `reviewer`，由 `ConnectionService.resolve_default("reviewer")` 解析。运行时据此装配真实、工具无关、必要时单轮模型调用的 reviewer；未配置时明确报告复核 `unavailable` 且**阻止 accept**（不把程序机器门当作独立复核）。仅新增可选非秘密字段，不改变既有默认角色语义。
- `1.6.0` 加性设置项（LG-028，去中心化，均**默认关闭**）：`decentralized_claim_enabled`（默认 `false`）、`collab_requests_enabled`（默认 `false`）、`claim_lease_seconds`（默认建议 `300`，可配置）。关闭时行为与现状完全一致（程序按 `plan_source=rules` 顺序调度，无发现/领取/协作端点副作用）；SDK 内部委派（`enable_subagents`）仍默认关闭，且**不因本扩展自动开启**。这些项写入 `bot-data/settings/SETTINGS.md`（**非秘密**）。

  **实现状态（`1.7.0`，LG-031 装配，无字段/端点变化）**：三个开关现可经 `PATCH /settings`（`decentralized_claim_enabled`/`collab_requests_enabled`/`claim_lease_seconds`）与 `ConnectionService.update_settings` 读写，缺省/非法值一律回落为**关闭**；未提供的字段保留当前值。真实 worker 执行身份由**程序冻结的不透明 execution grant**（进程内、非持久、`X-LG-Execution-Grant`）绑定到 `(run, subtask, member, fence)`，只授权本 Run/Task 节点与冻结协作预算；body 自报 `from_member_ref` 永远不作认证，worker 不持有全局管理 token。关闭开关时图调度器仍走确定性路径且不附加自定义工具。

### 6.6 资料实体（`1.6.0`，LG-033；接口冻结，未实现）

`1.6.0` 登记两个加性运行时实体 `source`（资料记录）与 `intake_job`（摄取作业），**只冻结接口，未实现**；实体前缀见 §3.1。文件（原件 + 资料 frontmatter + 正式内容）是资料层的**唯一事实源**，JSONL 保存历史；索引/向量只为**可重建缓存**。

```yaml
schema: lightgravity.bot/v1
kind: source
id: source_01J...
title: "…"
title_origin: user            # user | derived（派生标题不覆盖用户标题）
status: received              # received | processing | extracted | attributed | indexed | archived | partial | failed（展示层，不加入 §6.1 Task phase 枚举）
archived: false               # 1.9.0 加性：可逆整理标记，不改变 status/索引/检索/打开
revision: 0
scope: { task_ref: null, project_ref: null, inbox_ref: null }
origin: { kind: upload, external_ref: null, fetched: false }
content_hash: null            # 当前源版本内容 SHA-256（内容是否变化）
stat_revision: null           # 文件写入令牌（如 size-mtime_ns），**非密码学哈希**，与 content_hash 严格区分
source_version: 1             # 源版本序号；内容 hash 变化时 +1
original: { path: null, media_type: null, bytes: null, archived_at: null }
derivatives: []               # {kind, path, source_version, content_hash, model_version}
formal: { path: null, revision: null, edited_by: null }   # 人工正式版本，重处理不覆盖
index: { lexical: not_indexed, lexical_hash: null, vector: disabled, vector_model: null }
receipt_ref: null
created_at: null
updated_at: null
```

```yaml
schema: lightgravity.bot/v1
kind: intake_job
id: intake_01J...
source_ref: source_01J...
status: queued                # queued | running | succeeded | partial | failed | cancelled | recovery_required
revision: 0
request_id: req_01J...        # 幂等键
payload_hash: null            # 同 request_id 不同 payload → source_conflict
stage: received               # received → extracting → attributing → formalizing → indexing → done（展示用）
attempt: 1
budget: { max_model_calls: 0, timeout_seconds: null, max_retries: 1 }
cancel: { requested: false, confirmed: false }   # 只有确认停止才写 cancelled
fail_reason: null
created_at: null
updated_at: null
```

**写授权边界（冻结时不可弱化）**：在资料接入授权范围内，程序可直接写原件、资料记录、机器提取件、人工正式版本、索引/向量缓存与摄取事件，**不要求交付 Task/Run/团队**，不占执行槽、不排队交付。但摄取**不等于**工程写：`backend/**`、`frontend/**` 与共享依赖的修改仍必须走既有 Task/Run、验证与人工验收；摄取**不得**修改任何 Task/Run/Member 运行控制状态（`status`/`phase`/`queue`/`acceptance`/`active_run`），不领取工件、不释放队伍、不写验收决定；上传文件不自动创建交付 Task/Run/团队；有界工具问答仍只读。

**不可弱化的语义**（LG-033）：
- 幂等按稳定接入 `request_id`（**不是“同一 URL 永远跳过”**）；同 `request_id` 不同 payload → `source_conflict`。
- 去重只在**同一来源、同一授权范围**内按内容 hash 识别；**跨来源/跨 Task 不合并**，不自动合并授权、抹掉来源或扩大可见范围（去重存储，不去重权限）。
- 权限与归属**只能在文件 SoT**，不得只存在索引/向量；检索只返回已授权候选且**读取时回源核对**存在/哈希/版本/权限。
- 来源内容 hash 变化→ `source_version + 1` 并重建派生/索引/向量，旧命中失效（`source_stale`）；`stat_revision` 变化但内容 hash 不变**不**构成新源版本。
- 撤销/删除使命中失效，**不返回悬空结果**；重处理**不覆盖**人工正式版本（位置分离）。
- **整理归档≠撤销（`1.9.0`）**：`archive`/`unarchive` 是可逆整理，**保留**来源、作用域/权限、检索与打开能力，只将资料移出默认列表；只有 `revoke`/`delete` 使命中失效、资料不可用。不得以撤销（`revoke`）充当整理归档，也不得让 UI 的 archive 实际执行永久 revoke。
- 取消需**确认停止**（`cancel.confirmed`）才写 `cancelled`；未知副作用的中断**不自动重放**（对齐 §9 与 LG-016）。
- 失败**不造空成功正文**，失败说明**不作为知识正文参与检索**。
- 向量为**可选派生**，不是摄取/OCR/词法索引的前提；向量服务不可用时词法检索与原件查看仍可用；**embedding ≠ OCR/ASR**，不得用一条通路推断另一条。
- 收件区与资料路径必须经 `Store.resolve_path` 授权（拒绝 `..`/绝对路径/逃逸符号链接）。

> 迁移兼容：现有 `POST /files/upload`、`GET /files/download` 等（§4.3）语义不变，是当前唯一相关实现；资料接入目标交互逐步收拢到 Chat，**当前尚未迁移**。新增资料 schema/端点/事件属 MINOR；若改既有 Files/Chat 端点语义或有损迁移则属 MAJOR（须 `/api/v2`，§4.1）。

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
- 引用语义（1.3.1）：`artifact_refs` 为 workspace 相对产物路径；`diff_ref` 为 executor artifact sink 的引用，可能是本地绝对路径。协调器在写入 Subtask `evidence_refs` 前把本地 executor 产物导入 Task/Run 拥有的 evidence 根并记录为 `evidence:<run_id>/<name>@sha256:<hex>`；机器检查绝不直接解析原始绝对路径（见 §6.3）。
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
- **独立复核（`1.7.0`，LG-017 R1）**：`verifying` 先经**独立 reviewer**（独立角色/连接/上下文，默认 `default_reviewer_connection_ref`）才能进入 `awaiting_acceptance`；程序机器检查（LG-009）是机器门，**不等价**于独立复核。无可用的真实 reviewer 时报告复核 `unavailable`，Task 停在 `waiting_user`，**不消耗返修轮、不开放验收、不假 pass**。review `rework` 且有预算时进入 `repairing` 并开新 Run（重新招募/复验），旧候选与证据保留；模型输出只作报告，经程序 `validate_findings` 绑定可解析候选证据，**不能直接判 done**。
- **独立复核生命周期与停确认（`1.8.0`，LG-022 R1）**：独立复核与状态/控制请求**并发**可服务（reviewer turn 不在协调器事件循环内同步执行）。复核运行中的 `pause`/`cancel` 必须对 reviewer 有**真实 stop/释放确认**：确认停止后才写 `paused`/`cancelled` 并释放槽位（`verifying` 下 pause 经法定 `waiting_user → paused` 两步落位，候选与证据保留）；**未确认/超时**计 `unknown`，**不写终止状态、不释放槽、不重放未知副作用**。进程重启时处于 `verifying`/`repairing` 的 Run 若 worker 已消失，按 `recovery_required` 诚实停车（`1.8.0` 新增该迁移），旧候选保留，需人工决定后才开新 Run。
- **全局生成计数（`1.8.0`，LG-022 R1）**：所有 worker session、独立 reviewer turn 与 SDK 重试共享**同一进程全局**上游生成请求计数，在**转发前**预留；`GET /api/v1/diagnostics/generation` 报告 `count`/`limit`/`remaining`，用于集中 QA 约束并观测全局硬上限，不把未知当零。
- **持久生成账本（`1.10.0`，LG-022 R2）**：全局生成计数改为受控 dataRoot 下的**持久账本**（append-only JSONL 事实源 + 可重建原子计数快照），跨 worker/reviewer/session/进程重启不归零；**转发前持久预留**（保守预留与确认转发分列，不声称远端 exactly-once）；账本损坏/不可读时**拒绝转发并报 unknown，绝不当 0**。`GET /api/v1/diagnostics/generation` 加性新增 `persistent`（及损坏时 `corrupt`/`reason`）。账本仅保留计数与最小非秘密元数据（单调序号/时间戳/不透明预留 id），**不落输入/prompt/header/凭证/grant**。
- **执行器共享计数接线（`1.10.0`，LG-031 R2，无版本/字段/端点变化）**：执行器支持加性可选的共享计数注入；默认产品装配（`api/bootstrap`）在 `configure_generation_ledger` 之后把同一**持久账本**注入真实执行器，使每个 worker/reviewer 的 loopback 认证代理都消费**同一持久硬上限**，不会按 worker/session 重置或回退为非持久内存计数。契约字段、端点与版本不变。
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
| `backend/lightgravity/api/**`、`tests/api/**` | LG-012；LG-002 仅 health/version；LG-025 加 settings；LG-014 计划加 `api/files.py` 上传/下载 | 查询/事件/行动接口；`api/files.py` 的上传/下载扩展由 LG-014 在 LG-012 之后串行修改 |
| `backend/lightgravity/settings/**` | LG-025 | 连接与凭证后端 |
| `frontend/**` | LG-011 | 壳层、组件、API 客户端；视图由 LG-013/014/015/026 在 `src/views/` 内扩展 |
| `probes/**` | LG-003 | 独立探针环境，不进入主包 import 路径 |
| `tests/e2e/**` | LG-021、LG-022 | 浏览器与端到端验收 |
| `docs/08-interface-contract.md` | LG-001 | 契约变更按第 13 节流程 |
| 去中心化契约（LG-028） | docs08 owner 串行冻结；实现 LG-029（`store/**` 租约/fence、`coordinator/scheduler.py` 发现/领取、`api/**` 发现/领取端点）、LG-030（`coordinator/**` 协作路由/预算、`store/**` collab 持久、`api/**` collab 端点）、LG-031（`coordinator/**`/`verify/**`/`tests/e2e/**` 整合） | 共享 `coordinator/**`、`api/**`、`store/**` 与 docs/08 由**单一 owner 串行接线**；LG-029/030 可在独立 worktree 并行，接口以 §6.3/§4.3 冻结点为准 |
| 资料摄取/检索契约（LG-033） | docs08 owner 串行冻结；实现 LG-034（`POST/GET /sources`、原件落盘、收件区）、LG-035（派生/正式分层）、LG-036（词法索引/回源）、LG-037（可选向量）、LG-038（Chat/Files 整合） | 共享 Store/Coordinator/API/前端入口由**单一 owner 串行接线**；实现前必须已完成本版冻结 |

跨任务需要修改他人 owner 文件时，必须由整合执行者串行接线，或经主代理协调后指定临时 owner；不得并发改同一文件。

## 12. LG-001 验证清单

LG-001 自身的可机械/可复核检查（实现层验证属于后续任务与版本 QA）：

- [ ] 契约版本与 `/api/v1`、`lightgravity.bot/v1` 在本文一致声明（LG-001 冻结 `1.0.0`；当前 `1.10.0`，变更记录见第 13 节）。
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
| `1.9.0` | 2026-10-16 | MINOR | 首版返修后的串行集成收拢（唯一集成 owner）：① 新增加性可逆归档——`source` 加性布尔字段 `archived`（默认 `false`，§6.6）、`POST /sources/{id}/actions` 新增 `archive`/`unarchive` 动作与可选 `expected_revision`（§4.3、§6.6）；② 挂载 LG-037 可选向量端点 `GET /vector/status`、`GET /vector/search`、`POST /vector/rebuild`（§4.3、§6.6，默认禁用、仅环境变量配置、候选回源核对） | **仅新增可选非秘密字段、两个可逆动作与三个可选端点**；不改变 `revoke`/`delete` 语义（撤销仍 `status=archived` + 失效命中），不新增事件类型，不改变 `state`/`phase`/`acceptance`/`source.status` 枚举；向量默认关闭，不可用时词法/原件仍可用；不新增供应商、秘密表单或常驻编排 agent |
| `1.10.0` | 2026-10-16 | MINOR | LG-022 第二轮针对性返修（REFIX-R2）：① 停止门可接受**真实停止事实**（§9）——成功 Run 的 `cleanup` 常为 `pending`，停止门除 `cleanup=done` 外接受权威适配器停止确认（SDK session `__aexit__` / loopback 代理真实关闭），Run 加性新增可选 `reviewer_cleanup`（`{status,confirmed,...}`）；未知/仍活跃/关闭失败保留 `unconfirmed` 与 `session_refs`，不伪 `done`。② `GET /api/v1/diagnostics/generation` 加性新增 `persistent`（及损坏时 `corrupt`/`reason`）——全局生成计数改为受控 dataRoot 下持久账本，转发前持久预留，跨重启不归零，损坏绝不当 0 | **仅新增可选非秘密字段/诊断字段与停止门事实来源**；不新增端点、错误码、`state`/`phase`/`acceptance` 枚举或迁移方向；不改远端 exactly-once 语义；不新增供应商/秘密表单/常驻编排 agent |
| `1.8.0` | 2026-10-16 | MINOR | LG-022 首版集中 QA 阻断项 D1/D2 返修 R1：① 状态迁移加性新增 `verifying → recovery_required` 与 `repairing → recovery_required`（§6.1），用于独立复核/返修阶段重启后未知副作用诚实进入人工恢复；② 新增只读诊断端点 `GET /api/v1/diagnostics/generation`，报告进程全局上游生成请求计数 `{count, limit, remaining}`（§4.3、§9），覆盖 worker/reviewer/重试，转发前计数 | 新增两个合法迁移方向（纯加性，不改既有方向）；新增一个只读端点；不改变既有端点语义、错误码、既有 `state`/`phase`/`acceptance` 取值与既有字段语义；不新增供应商/秘密表单 |
| `1.7.0` | 2026-10-16 | MINOR | LG-017 返修 R1：新增加性设置角色/字段 `default_reviewer_connection_ref`（§6.5，独立复核者默认连接），Task 返修账本加性字段 `reviewer`/`reviewer_kind`/`model_usage`（§6.1），review/rework 事件加性 payload `reviewer_kind`/`model_calls`/`usage`（§5.1），以及独立复核语义（§9：无可用 reviewer ⇒ `unavailable` 并阻止 accept；机器门不等于独立复核） | **仅新增可选非秘密字段与加性 payload**；不新增/改变端点、错误码、`state`/`phase`/`acceptance` 枚举、迁移方向与既有字段语义；不新增供应商、秘密表单或供应商切换 |
| `1.6.0` | 2026-10-16 | MINOR | 由**单一 docs08 owner 串行冻结**两条**尚未实现**新线契约：① LG-028 去中心化协作——Subtask 加性可选字段 `fence`（§6.3）与租约/fencing/过期语义、发现/领取/续租/释放/协作端点（§4.3）、事件 `subtask.lease_*`/`subtask.claim_refused`/`collab.*`/`handoff.*`（§5.1）、错误码 `stale_lease`/`claim_refused`（§4.2）、设置开关 `decentralized_claim_enabled`/`collab_requests_enabled`/`claim_lease_seconds`（均默认关闭，§6.5）、协作预算与 `recovery_required` 说明（§6.2）；② LG-033 资料摄取/检索——新实体 `source`/`intake_job`（§6.6）与 ID 前缀（§3.1）、端点 `sources`/`intake`/`search`/`inbox`（§4.3）、事件 `source.*`/`intake.*`（§5.1）、错误码 `source_conflict`/`source_stale`/`index_unavailable`（§4.2） | **仅新增可选实体/schema/字段、端点、事件与错误码**；不改变既有 `state`/`phase`/`acceptance` 枚举、迁移方向、既有端点与既有错误码语义；去中心化端点默认关闭。新端点/实体**仅冻结接口，尚未实现**；`source`/`intake_job` 展示状态**不加入** §6.1 Task `phase` 枚举。既有 Files 上传/下载语义不变。完整 checkpoint skip 仍**未实现**，恢复仅依赖已落盘证据 |
| `1.5.0` | 2026-10-15 | MINOR | 登记 LG-020 的加性、非秘密字段 `connection_pin`（Run §6.2、Member §6.4），用于在 Run 招募时冻结默认 worker 连接（ref + revision + content_hash + 不透明 `credential_version`）；活跃 Run 内默认/凭证轮换不得在下一 Subtask 静默换用（漂移按 `config_invalid` 失败，新 Run 重新解析）。整合期登记只读端点 `GET /tasks/{task_id}/artifacts/content` 与 `GET /tasks/{task_id}/artifacts/download`，从 Task 产物 API 经 Task/Run evidence resolver 预览/下载 canonical evidence 产物（§4.3） | 仅新增可选实体字段与只读端点；不落盘秘密，既有端点语义、错误码、事件类型、枚举与状态迁移未变化 |
| `1.4.0` | 2026-10-15 | MINOR | 登记 LG-015 Team/Resources 的加性受控写入端点 `PATCH /resources/{kind}/{id}`、只读端点 `GET /team/available`/`GET /team/members`（§4.3），以及 Task 消息信封新增可选字段 `resource_proposal` 与回写 `resource_result.status`（§5.2）；该提议由协调器程序校验后调用 `ResourceService.update`，实际结果/冲突写回同一 Task 对话 | 仅新增可选消息字段与端点；既有端点语义、错误码、事件类型、枚举与状态迁移未变化 |
| `1.3.1` | 2026-10-15 | PATCH | 将 `1.3.0` 登记为 planned 的 LG-014 `POST /files/upload`/`GET /files/download` 标记为已实现（§4.3），明确其 `revision` 为 `size-mtime_ns` 尽力令牌与跨进程复核限制；明确证据引用解析语义：workspace 相对引用 vs Task/Run evidence 根的 `evidence:<run_id>/<name>@sha256:<hex>`，拒绝原始绝对路径（§6.3、§8） | 无新增/变更端点、错误码、事件类型与枚举；仅完成既定 planned 端点并澄清既有 `evidence_refs` 字符串格式，既有状态迁移未变 |
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
| 独立复核者配置/装配/无 reviewer 阻止 accept/真实 SDK reviewer 路径（§5.1、§6.1、§6.5、§9） | LG-017、**LG-022（集中 QA）** |
| 去中心化发现/领取/租约 fencing/协作/预算（§4.3、§5.1、§6.2、§6.3） | LG-029、LG-030、LG-031、**LG-032（集中 QA）** |
| 资料摄取/来源版本/去重/回源/索引失效与可选向量降级（§4.3、§5.1、§6.6） | LG-034～038、LG-039、**LG-040（集中 QA）** |

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
