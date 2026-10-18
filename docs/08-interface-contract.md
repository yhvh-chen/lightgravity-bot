---
title: "首版接口与状态契约（v1）"
doc_type: specification
category: architecture
contract_version: "1.19.0"
updated: "2026-10-18"
---

# 首版接口与状态契约（v1）

> **契约 1.19.0 冻结（2026-10-18，LG-140；仅契约准备，未实现）**：本节新增资料摄取 v2 的加性请求/响应字段、独立回执分支、能力门、媒体直接 embedding、持久服务端摄取、配额/重试/取消/重启与显式重建边界，见 §20。**源码与运行服务仍为 1.18.0**；在 LG-141～LG-143 实现、LG-144 串行集成并由 LG-145 独立验收前，不得修改 `CONTRACT_VERSION`、`/health` 新能力或宣称自动索引已可用。旧客户端不发送新字段时保持 1.18.0 行为；Team Personal 私有附件隔离与 ASR 不可用边界不变。

> **LG138部署状态（2026-10-18）**：1.18.0候选已通过有界独立QA并部署8123；任务执行保留关闭。下方冻结时的“待QA/8123仍1.17”已由[最新部署](../probes/chat-task-teams-20261017/lg138/deploy-LG138-DELIVERY.md)与最终独立报告补齐。


> **上一契约1.17.0（2026-10-17，LG-104已实现/独立R2 QA PASS/本地8123交付）**：加性新增Connection可选provider认证/本地模型字段、能力描述、受保护草稿测试及按版本/引用保护删除，支持弹窗先测试再保存。仅扩展配置/显式手动测试，native Task执行与默认选择不扩大；不改变旧saved-test语义和实体状态迁移。详见§18与[独立QA](../probes/provider-setup-20261017/qa-r2/QA-R2.md)；下方1.16.0为此前版本说明。

> **当前契约 1.16.0（2026-10-17，LG-066 全局查询/澄清的加性 MINOR）**：在既有全局会话消息端点上加性新增 `query`/`clarify` 响应与只读状态 `data` 快照；按消息内显式合法 Task ID 解析，缺失、非法、未知或出现多个不同 ID 时诚实澄清，绝不猜测目标；成功查询只读持久状态并返回 `creates_task=false`/`creates_run=false`，不创建 Task/Run/worker、不调用模型；回复写入共享全局会话，Personal 仍仅聊天且按身份隔离。范围与精确响应见 §17。无新端点、请求字段、错误码、实体 schema、状态/阶段/验收枚举、迁移方向、角色、招募流程或执行预算。默认单用户与 1.15 团队行为保持；前端最低兼容仍为 `>=1.13,<2`（加性兼容，无需提高）。
>
> **上一契约 1.15.0（2026-10-17，LG-062 账户管理命名里程碑的加性 MINOR）**：团队模式新增管理员账户管理端点（列表／新增／启用禁用／角色／重置口令）与所有登录用户的自助改密端点 `POST /account/password`；账号事实源加性新增 `enabled`／`revision`／`session_version`；`GET /api/v1/health` 加性新增可选 `capabilities.accounts`。改密／重置、禁用与角色变更使目标旧会话在下一请求失效，既有 SSE 流约 2 秒重校验关闭；末位可用管理员在存储锁内受保护。范围与安全边界见 §16。默认单用户与 1.14 团队行为保持不变；独立最终 pi QA PASS；主目录 b6c738d 与冻结 dbf7b0c 的 backend/frontend/tests/e2e 树一致，已本地部署至 0.0.0.0:8123，实际普通浏览器 27 项检查通过。[账户管理证据](../probes/accounts-20261017/README.md)。未远端推送，用户最终验收待定。

> **上一契约 1.14.0（2026-10-17，LG-054 加性 MINOR，LG-051 技术验收通过）**：新增当前身份的 Personal 消息端点与可选 `personal_chat` 能力，团队私聊与共享 Task／资料分离；默认单用户保留原任务和资料能力。§15 规定身份及兼容边界。独立 QA **PASS_WITH_LIMITATIONS**（1004 后端通过／5 跳过、171 前端通过、50 Chromium Playwright 场景通过）；主目录 `ea6da80` 与候选 `602c7af` 产品树一致，本地支持的启动入口 `http://127.0.0.1:8123` 另有 30 项实际检查通过。[完整记录](../probes/ui-repair-20261017/README.md)。本轮未调用真实产品模型，用户最终验收待定、未推送。

> **上一契约 1.13.0（2026-10-16，LG-050 加性 MINOR）**：新增显式启用的共享团队模式、账号会话端点、服务端消息作者及 `forbidden` 错误码。范围见 §14；已本地合入并通过独立 QA（PASS_WITH_LIMITATIONS，含真实 HTTP、CLI 与 Firefox 双用户上下文端到端），[证据](../probes/team-chat-20261016/qa/QA-REPORT.md)。用户最终验收待定。默认单用户行为保持；下方长段版本记录自 1.12.0 起为历史沿革，不是当前版本号。

> 性质：LG-001 冻结的候选实现契约。它把 [产品与架构设计](01-design.md)、[Task 与 SDK 资源契约](02-task-and-sdk-resources.md)、[Bot 行为契约](04-bot-behavior.md)、[SDK 能力审计](03-sdk-capability-audit.md)、[导航设计](05-navigation-and-team.md)、[模型设置](07-settings-and-models.md) 收敛到可实现的接口与状态边界，不新增产品能力，也不代表功能已实现或经过运行时验证。
>
> 契约版本 `1.12.0`（2026-10-16 MINOR：LG-042 冻结、LG-043 **实现**的“手动选定已摄取资料”快速原型——消息信封加性可选 `selected_sources`（≤3 来源、`{source_id, source_version?, content_hash?}`）与结果 `data` 加性可选 `resolved_source_bindings`/`context_truncated`/`provided_context_note`；总 12000 Unicode 字符有界、显式截断 metadata、正式优先机器回退、派发前 stale/revoked/cross-Task 拒绝、不可信数据隔离、不跨 Task 携带；实现采用显式截断分支并以内部非客户端 body digest 在 worker 派发前重校验；**绑定修正（R1）** 另加性新增可选 Task/Run 实体字段 `selected_trigger={message_id,snapshot}`（实体序列化可达、非秘密），使 Run 只用自身触发消息的精确选定而非“最近消息”启发式，无选材不继承、重启保持。仅新增可选请求/响应字段与加性可选实体字段，无端点/错误码/枚举/迁移方向变化，见 §6.6.1、§13。此前 `1.11.0`（2026-10-16 MINOR：LG-031 runtime/API/SDK 集成落地后，按实际公开兼容变化保守登记的加性 MINOR，取代此前 `1.10.0` 的“实现说明增补（无版本变化）”口径。此前 R1 观察 O3 指出两处公开兼容变化：① 四个去中心化端点（`GET /runs/{run_id}/discoverable`、`POST /runs/{run_id}/claim_requests`、`POST /subtasks/{subtask_id}/lease/renew`、`POST /subtasks/{subtask_id}/lease/release`）的请求体 `owner` 由 1.6.0 冻结时事实采用的 **required/端点采用** 放宽为 **optional/兼容校验、不再具有授权含义**（原值被程序冻结 grant 取代）；② `ExecutionGrant` 加性新增进程内非持久字段 `lease_owner`（程序冻结租约权威身份，`effective_lease_owner = lease_owner or member_ref`）。二者均为**向后兼容的公开请求字段语义放松 + 加性内部字段**：旧客户端继续传 `owner` 仍可用（但不获授权），不传也可用；无端点/枚举/错误码/实体 schema/迁移方向变化，未认证/default-deny 与不落盘边界不变。按 docs/08 §13「新增向后兼容字段/语义放宽为 MINOR」保守记为 `1.11.0`（不沿用历史拟议的 `1.6.0`）。**精确行为/回退/安全边界**见 §4.3「发现/领取/续租/释放执行身份边界」。此前 `1.10.0`（2026-10-16 MINOR：LG-022 第二轮针对性返修（REFIX-R2）的加性 MINOR，全部为**加性可选、非秘密**变更。① **停止门可接受真实停止事实**（§9）：成功 Run 记录真实 `session_refs`/reviewer 资源时，`cleanup` 常为 `pending`；停止门现在除 `cleanup=done` 外也接受**权威适配器停止确认事实**（SDK session 的 `Agent.__aexit__` / loopback 代理的真实关闭结果）作为 session/reviewer 已停止的证明，`run` 实体加性新增可选 `reviewer_cleanup`（`{status,confirmed,...}`，默认缺省即无事实）。未知/仍活跃/关闭失败/损坏一律保持 `unconfirmed` 与保留 `session_refs`，**不假装已停止、不伪造 `cleanup=done`**。② `GET /api/v1/diagnostics/generation`（§4.3）加性新增 `persistent`（及持久账本损坏时的 `corrupt`/`reason`）字段：全局生成计数改为**受控 dataRoot 下的持久账本**（append-only JSONL 事实源 + 可重建原子计数快照），**转发前持久预留**，跨 worker/reviewer/session/进程重启不归零；账本损坏/不可读时**拒绝转发并报 unknown，绝不当 0**；仅记计数与最小非秘密元数据，不落输入/prompt/header/凭证/grant。**不新增端点、枚举、迁移方向或错误码**，不改变 `state`/`phase`/`acceptance` 枚举；不新增供应商、秘密表单或常驻编排 agent。此前 `1.9.0`（2026-10-16 MINOR：首版 review 生命周期返修后的串行集成收拢，全部为**加性可选、非秘密**变更。① `source` 实体新增加性布尔字段 `archived`（默认 `false`）与 `POST /sources/{id}/actions` 新增 `archive`/`unarchive` 两个**可逆整理**动作（§4.3、§6.6）：归档**保留**来源/作用域/权限/检索与打开能力，仅把资料移出默认列表；它**不是**使资料不可用的 `revoke`（后者仍写 `status=archived` 并失效命中）。动作请求体新增可选 `expected_revision`（乐观并发，冲突 `409 revision_conflict`）。② 新增只读/显式可选向量端点 `GET /vector/status`、`GET /vector/search`、`POST /vector/rebuild`（§4.3、§6.6），默认禁用、后端仅由环境变量配置、候选仍回源核对；向量不可用时词法检索与原件查看照常可用。**不改变** `revoke`/`delete` 既有语义，不新增事件类型，不改变 `state`/`phase`/`acceptance`/`source.status` 枚举，不新增供应商、秘密表单或常驻编排 agent。此前 `1.8.0`（2026-10-16 MINOR：LG-022 首版集中 QA 阻断项 D1/D2 返修 R1。① **状态迁移加性扩展**：新增合法方向 `verifying → recovery_required` 与 `repairing → recovery_required`（§6.1），用于独立复核/返修阶段进程重启后未知副作用诚实进入人工恢复，**不重放、不假终态**；既有方向与语义不变。② 新增只读诊断端点 `GET /api/v1/diagnostics/generation`（§4.3），报告**进程全局**上游生成请求计数 `{count, limit, remaining}`（`limit` 来自 `LIGHTGRAVITY_MAX_GENERATION_CALLS`，`None` 仅计数不设上限），覆盖全部 worker session/independent reviewer/SDK 重试，**转发前计数**，使集中 QA 可真实约束与观测全局硬上限而非 unknown；不暴露凭证/prompt。D1（reviewer turn 在运行中事件循环内 `asyncio.run` → `unavailable`）为**实现修复**（reviewer turn 移出协调器循环），D2（复核阻塞循环、无 reviewer 生命周期）为**实现修复 + 生命周期确认**，二者不改变端点/错误码/既有字段语义。**不新增供应商、秘密表单或供应商切换。** 此前 `1.7.0`（2026-10-16 MINOR：LG-017 返修 R1，全部为**加性可选、非秘密**变更——新增设置角色/字段 `default_reviewer_connection_ref`（§6.5，独立复核者默认连接，默认 `null`）、Task 返修账本加性字段 `reviewer`/`reviewer_kind`/`model_usage`（§6.1）、review/rework 事件加性 payload `reviewer_kind`/`model_calls`/`usage`（§5.1，未知用量计 `unknown`、**不得当 0**），并明确独立复核语义（§9：`verifying` 须经独立 reviewer 才进入 `awaiting_acceptance`；程序机器检查是机器门，**不等于**独立复核；无可用真实 reviewer 时报告 `unavailable` 并**阻止 accept**，不消耗返修轮、不假 pass；模型输出经程序 `validate_findings` 绑定可解析候选证据，**不能直接判 done**）。**不新增/改变端点、错误码、`state`/`phase`/`acceptance` 枚举、迁移方向与既有字段语义；不新增供应商、秘密表单或供应商切换。** 此前 `1.6.0`（2026-10-16 MINOR：串行冻结 LG-028 去中心化协作与 LG-033 资料摄取/检索两条**尚未实现**的新线契约，全部为**加性可选**字段、端点、事件与错误码，**默认关闭**且不改变既有 `state`/`phase` 枚举、迁移方向与错误码语义；`fence`、`claim_request`/`collab_request`、`source`/`intake_job` 及相应端点/事件/错误码**仅冻结接口，不代表已实现或可用**；去中心化版本（LG-032）与资料版本（LG-040）集中 QA 前不得宣称通过，见 §4.3、§5.1、§6.2、§6.3、§6.6、§13）。此前 `1.5.0`（2026-10-15 MINOR：登记 LG-020 的**加性、非秘密**字段 `connection_pin`（Run 与 Member 实体，§6.2、§6.4），用于在 Run 招募时冻结默认 worker 连接（ref + revision + content_hash + 不透明 `credential_version`），使活跃 Run 内默认连接或凭证轮换不得在下一 Subtask 静默换用（漂移按 `config_invalid` 失败，新 Run 重新解析）；**不落盘任何秘密**，既有端点语义、错误码、事件类型、枚举与状态迁移均未变化，向后兼容。此前 `1.4.0`（2026-10-15 MINOR：登记 LG-015 Team/Resources 的**加性**受控写入端点 `PATCH /resources/{kind}/{id}`、只读端点 `GET /team/available`/`GET /team/members`，以及 Task 消息信封新增可选字段 `resource_proposal` 与回写 `resource_result.status`（§4.3、§5.2），用于把有界资源修改提议经 Task 对话由协调器程序校验后调用 `ResourceService.update`；**既有端点语义、错误码、事件类型、枚举与状态迁移均未变化**，向后兼容）；此前 `1.3.1`（2026-10-15 PATCH：将 `1.3.0` 登记的 `POST /files/upload`/`GET /files/download` 由 **planned** 标记为**已实现**（§4.3，revision 语义与外部改动复核限制见该节），并明确机器检查证据引用的解析语义——workspace 相对引用仅按授权 workspace 根解析，executor 产物证据由协调器导入 Task/Run 拥有的 evidence 根并以 `evidence:<run_id>/<name>@sha256:<hex>` 规范化解析，原始绝对路径一律拒绝）；此前 `1.3.0` 登记 LG-009 的加性 Task `checks` 授权字段与 `acceptance` 绑定字段 `candidate_ref`/`candidate_plan_hash`/`check_records`/`note`（§6.1），新增只读端点 `GET /tasks/{task_id}/acceptance`、LG-025 设置端点 `GET /settings/connections/{id}` 与 `PATCH /settings`、全局对话 `GET/POST /conversations/global/messages`（§4.3、§5.2）；`1.2.0` 登记 LG-008 自动组队与依赖调度使用的加性实体字段——Run `plan`/`plan_hash`/`plan_source`，Subtask `objective`/`capability`/`key`/`write`/`config_hash`/`owner`/`lease_expires_at`/`fail_reason`/`blocked_by`，见 §6.2、§6.3；`1.1.0` 明确首版唯一真实执行后端为已验收的 OpenAI-compatible `LocalOpenAIAgentConfig` → DeepSeek 路径并补充本地认证代理与凭证边界，见 §8.1；变更记录见第 13 节）。实体 schema 命名空间 `lightgravity.bot/v1`；HTTP API 前缀 `/api/v1`。变更规则见第 13 节。实现与本文冲突时以本文为准；本文未定义的行为一律视为“不支持”，实现不得自行扩展语义。运行时未知字段按“保留但不赋予执行语义”处理。

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

> **LG-051 前端兼容范围（2026-10-17，已通过独立 QA）**：当前 UI 所需契约下界为稳定版 1.13.0，上界为 2.0.0（不含），并校验 schema 与核心工作台能力。健康接口 200 不足以证明 Task／Files／Team／Settings／全局对话可用；缺少 SDK／模型配置单独显示，不作为核心只读页面不兼容。缺少 `/auth/me` 不再直接推断单用户管理员身份。团队 Personal 另按 §15 要求 >=1.14,<2 与明确 personal_chat 能力；不支持时禁用私聊入口并说明，不把 404 当作可用。此为前端支持范围与启动诊断说明，不改变既有认证权限。

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
| `POST /api/v1/settings/connections/test-draft` | 受保护的不落盘连接草稿测试，§18 | LG-109 | 1.17已实现，独立QA通过 |
| `DELETE /api/v1/settings/connections/{id}` | 按revision与有效引用保护删除，保留共享秘密，§18.4 | LG-111/113 | 1.17已实现，并发修复后独立QA通过 |
| `PUT/DELETE /api/v1/settings/credentials/{ref}` | 凭证引用写入/移除（不回显秘密） | LG-025 | 冻结 |
| `GET/POST /api/v1/notifications` | 未读通知列表与标记已读 | LG-019 | 冻结 |
| `GET /api/v1/conversations/global/messages` | 全局对话消息（游标；仅 singleton global） | 整合/LG-007 | 冻结 |
| `POST /api/v1/conversations/global/messages` | 追加全局消息（幂等：`message_id`/`request_id`） | 整合/LG-007 | 冻结 |
| `GET /api/v1/settings` | 默认连接引用与偏好 | LG-026/LG-025 | 冻结 |
| `GET /api/v1/runs/{run_id}/discoverable` | worker 可发现候选投影（只读，按 Member 过滤） | LG-029 | 已实现并运行时接线（默认关闭；程序 grant 身份接线于 F2 返修；待版本 QA LG-032） |
| `POST /api/v1/runs/{run_id}/claim_requests` | 提交候选领取请求（幂等 `request_id`；body `owner` 为兼容可选字段，非授权） | LG-029 | 已实现并运行时接线（默认关闭；程序 grant 身份接线于 F2 返修；待版本 QA LG-032） |
| `POST /api/v1/subtasks/{subtask_id}/lease/renew` | 续租（`owner`+`lease_seconds`；身份取程序 grant） | LG-029 | 已实现并运行时接线（默认关闭；程序 grant 身份接线于 F2 返修；待版本 QA LG-032） |
| `POST /api/v1/subtasks/{subtask_id}/lease/release` | 主动释放（仅持有者或程序；身份取程序 grant） | LG-029 | 已实现并运行时接线（默认关闭；程序 grant 身份接线于 F2 返修；待版本 QA LG-032） |
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
> **资料摄取 v2（`1.19.0`，§20）**：不新增路径；`POST /sources` 加性可选 `intake_mode`，消息请求/持久化加性可选 `source_refs`，`GET /sources/{id}/receipt` 加性返回 `receipt_version:2` 与分支对象，`GET /intake/jobs/{id}` 加性返回摄取边界字段。所有新字段缺省时行为与 1.18.0 一致；新客户端必须通过 `material_intake_v2` 能力门。
>
> **1.6.0 冻结但未实现的新线端点**：上表“冻结接口（未实现…）”行是 LG-028 与 LG-033 的**契约冻结点**——只固定路径与最小语义，**端点可能尚未注册或返回 `not_ready`/`404`**，不得假定已可用；去中心化端点默认关闭（见 §6.3 开关）。实现分别归 LG-029/030（去中心化）与 LG-034～038（资料）；集中 QA 前不得宣称通过。worker 侧调用须经受控执行身份，不接受浏览器直接指定任意 `owner`；资料端点不创建交付 Task/Run。
>
> **执行身份边界（`1.7.0` 集成澄清，无字段/端点变化）**：`POST /runs/{run_id}/collab_requests`（LG-030）要求**程序认证的**执行身份：`ApiContext.worker_identity` 接缝解析出的已认证 Member 必须与请求体的 `from_member_ref` 一致，否则**默认拒绝**（`claim_refused`，`reason=unauthenticated`/`identity_mismatch`，不落盘、不消耗预算）。**请求体自报身份永不作为认证**。真实 worker 身份注入（协调器注入已认证 Member）属 LG-031；接缝已就位，默认拒绝保护边界。所有去中心化端点**默认关闭**，关闭时行为与确定性 `plan_source=rules` 调度一致。
>
> **发现/领取/续租/释放执行身份边界（`1.11.0` 加性 MINOR，公开请求字段语义放松，无端点/枚举/错误码/实体 schema 变化）**：`GET /runs/{run_id}/discoverable`、`POST /runs/{run_id}/claim_requests`、`POST /subtasks/{subtask_id}/lease/renew`、`POST /subtasks/{subtask_id}/lease/release` 同样**不从请求体取授权**。`ApiContext.worker_grant` 接缝（由 bootstrap 接线 `X-LG-Execution-Grant`）解析出**程序冻结的 execution grant**，端点仅从 grant 推导：principal（`member_ref` → 冻结的 `lease_owner`）、Run/Task scope（`grant.run_id` 必须等于路径 `run_id`）、可发现/领取节点（`authorized_node_refs` 的子集）、以及 fence（续租/释放只允许 `grant.fence`）。请求体 `owner` 为**兼容字段**：存在且不等于程序认证 principal ⇒ `claim_refused`/`identity_mismatch` 且**不落盘**；无 resolver / 无有效 grant ⇒ `claim_refused`/`unauthenticated`；**未配置/未认证一律 default-deny 且不写业务状态**。body `capability`/`write`/`scope` **不得**授予或扩大能力/范围（capability 由程序 grant 与 discovery 决定）。认证 A 不能冒 B 或跨 TaskRun；只读身份不能写。此为实现对齐 §4.3 note「不接受浏览器直接指定任意 `owner`」与 §2.4（授权不依赖 worker 自报身份）；peer（LG-030）端点语义不变。
>
> **claim/lease 端点的 `owner` 兼容语义**：因冻结端点历史上接受 `owner`，为向后兼容该字段**保留但仅为可选**；它不再具有授权含义，仅作一致性校验。
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
- **资料摄取 v2 加性 payload（`1.19.0`，§20.12）**：不新增事件类型。`source.attributed` 可含 `text_status`；`source.indexed`/`source.invalidated` 可含 `branch ∈ {keyword, semantic}` 与 `kind ∈ {text, image, audio}`；`intake.stage_changed`/`intake.failed` 可含 `branch`/`branch_status`。未知 payload 字段照常忽略；未产生的事件仍不得假定。

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
- 全局/Team 状态查询（`1.16.0`，§17）：对既有 `POST /conversations/global/messages` 的**加性响应扩展**——成功返回 `kind:"query"` 与只读持久状态 `data` 快照；缺失、非法、未知或出现多个不同 Task ID 返回 `kind:"clarify"` 与对应非秘密标记。两者都不创建 Task/Run/worker、不调用模型；普通未 mention 的团队消息仍为 `kind:"recorded"`、`reply:null`。请求 schema 不变，`task_ref` 不是客户端字段。
- 资料接入消息（`1.6.0`/`1.19.0`）：资料消息可复用现有 `attachments`（`{path, media_type}`）；`resource_proposal` 仅用于受控资源写，不用于资料摄取。`1.6.0` 不新增资料专用字段；`1.19.0` 加性新增 `source_refs`（§20.3），它只把消息关联到已接收资料以恢复回执/溯源，**不是**模型上下文、不自动选材、不与 `resource_proposal` 混淆。上传文件/消息的 frontmatter **不是**受信 Task/资源配置或指令，未知字段保留但**不获得执行语义**（不得 import/eval、不得启动 MCP/Trigger、不得改控制状态，§6.6）。

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
- **撤销 fail-closed 实现说明（LG-040 R1 返修，无契约版本变化）**：`revoke` 写 `status=archived`（与可逆 `archived` 布尔标志不同），该值即撤销标记。已撤销来源的**全部读取与再处理路径一律 fail-closed**：`GET /sources/{id}/content`（`auto`/`formal`/`machine`）、`GET /sources/{id}/download`（`original`/`formal`/`machine`）、`POST /sources/{id}/actions`（`reprocess`）与 `POST /sources/{id}/formal` 均拒绝，**不返回任何原始/正式/机器正文或字节、不重索引**；撤销来源的 `status` 不被 `reprocess`/正式校订覆盖而复活。拒绝使用**既有** `not_found`（HTTP **404**，§4.2）并在 `error.details` 附 `{source_id, status, revoked:true}`，使客户端/诊断可区分撤销与删除而不泄露正文。原始字节/机器派生/人工正式版本/历史**保留在磁盘**（`revoke`≠`delete`，不删除证据、不回滚归档语义）；`GET /sources/{id}` 元数据/状态诊断视图保留。可逆 `archive`/`unarchive` 仍保持检索/打开/下载与 `status` 不变。此为实现对齐既有 §6.6 语义，不新增端点/枚举/错误码/实体 schema，`revoke` 语义不变；独立重测预期状态码 = **404（`not_found`，`details.revoked=true`）**。
- 取消需**确认停止**（`cancel.confirmed`）才写 `cancelled`；未知副作用的中断**不自动重放**（对齐 §9 与 LG-016）。
- 失败**不造空成功正文**，失败说明**不作为知识正文参与检索**。
- 向量为**可选派生**，不是摄取/OCR/词法索引的前提；向量服务不可用时词法检索与原件查看仍可用；**embedding ≠ OCR/ASR**，不得用一条通路推断另一条。
- 收件区与资料路径必须经 `Store.resolve_path` 授权（拒绝 `..`/绝对路径/逃逸符号链接）。

> 迁移兼容：现有 `POST /files/upload`、`GET /files/download` 等（§4.3）语义不变，是当前唯一相关实现；资料接入目标交互逐步收拢到 Chat，**当前尚未迁移**。新增资料 schema/端点/事件属 MINOR；若改既有 Files/Chat 端点语义或有损迁移则属 MAJOR（须 `/api/v2`，§4.1）。

**实现说明（OCR 渲染尺度，无契约版本变化）**：OCR 处理路径的 PDF 渲染尺度为可选、非秘密的组合配置，经既有环境配置入口 `LIGHTGRAVITY_OCR_SCALE` 读取并传到产品 `ProcessingEngine` → `PdfiumRasterizer`。PDF 用户单位为 1/72 英寸，缺省 `2.0`（约 144 DPI）保持既有默认行为；显式值须为有限正数且不超过已记录安全上限（`MAX_OCR_SCALE=4.0`，约 288 DPI），非法值显式报错、不静默夹取为通过。此为**加性可选环境变量，不新增/改变端点、错误码、实体 schema、枚举、迁移方向与请求/响应字段**，按 docs/08 §13 属“实现说明增补（无版本变化）”，**不机械升版**；契约版本保持 `1.11.0`。

**实现说明（OCR 可选表格模式，无契约版本变化）**：OCR 处理路径新增**可选、默认关闭**的表格模式，经既有组合配置入口 `LIGHTGRAVITY_OCR_TABLE_MODE` 读取（缺省/空值 = 关闭）。接受值仅为不区分大小写的开/关拼写：开 = `1`/`true`/`yes`/`on`，关 = `0`/`false`/`no`/`off`；**其它任意值显式报错**（`validation_failed`，`details.accepted` 列出规范拼写 `0`/`1`/`false`/`true`），不静默当作关闭。开启时，程序先用**模型无关、有界、纯像素/几何**的版面分类器判断该页是否**确有带横线、多列一致 gutter 的表格网格**；**仅**对置信判为真实表格的页改用显式 Markdown 表格提示词，普通页（清晰页、印刷页、扫描页、非 PNG 输入等）**始终使用未改动的默认提示词**。判定所需的行数、列数、横线数与逐行列一致性为**已记录的固定比率常量，非逐页调参**；分类输入不含文件名、fixture 哈希、页码或任何人工真值。该模式**不新增/改变任何端点、错误码、实体 schema、枚举、迁移方向、状态迁移或请求/响应字段**；其判定记录（`prompt_kind`/`prompt_sha256`/`table_classification`）**只写入不透明本地派生证据** `derivative/ocr_evidence.jsonl` 与 per-version `source_derivative` pages 文档，**不进入** §6.6 冻结的 `source` 顶层字段或 `source.derivatives` 条目形状（`{kind, path, source_version, content_hash, model_version}`）。页数与输入上界沿用既有处理边界（`ProcessingConfig` 的 `max_pages`/`max_tokens_per_page`），无新增无界输入路径。按 §13 属“实现说明增补（无版本变化）”，**不机械升版**；契约版本保持 `1.11.0`。

**资料摄取 v2 回执（`1.19.0`，§20.6）**：`GET /sources/{id}/receipt` 保留既有条目字段，并加性新增 `receipt_version:2`、逐条 `text`/`keyword`/`semantic` 分支对象与顶层 `partial`。分支状态只投影真实文件/索引状态，不新增第二状态库；旧客户端忽略新字段时仍可读取 `status`/`stage`/`searchable`。

### 6.6.1 选定资料快速原型（selected-material，`1.12.0` MINOR；LG-042 冻结、LG-043 实现）
`1.12.0` 登记**加性、可选、非秘密**的“手动选定已摄取资料”契约，用于 Chat 回答与单 worker 交付。完整字段定义、共享 TS shape 与错误映射见 [docs/10 选定资料快速原型契约](10-selected-material-prototype.md)；本节只登记与 docs/08 冻结面的交界。

**实现说明（LG-043，A 后端 owner；绑定修正 R1）**：已按本版契约落地，实际采用**显式截断 + metadata** 分支（不选用“沿用既有 limiter 拒绝”分支）；`selected_sources` 由 `backend/lightgravity/sources/selection.py` 解析，经 `POST /tasks/{id}/messages` 与 `POST /conversations/global/messages` 的加性可选字段进入；总预算 12000 Unicode 字符逐来源累计；正式（formal）优先、机器派生（machine）回退；正文以不可信数据分隔符包裹；解析/拒绝发生在任何 product 模型派发之前；解析结果以 `selected_context` 快照写入既有消息日志，worker 派发前经同一快照 + 内部 body digest **再次校验**（源已变按 `source_stale` 拒绝，不静默换用新内容）。`source` 原内容哈希在 formal 编辑后不变，故新增**内部** body digest 检测实际正文变化；该 digest 仅用于程序侧重校验，**不作为客户端字段**暴露。**不新增**端点/错误码/枚举/迁移方向/供应商；旧客户端省略字段时行为不变。

**Run/消息绑定修正（R1，取代首版“最近消息”启发式）**：Run 使用**其自身触发消息**的精确选定快照，而非“最近一条含 `selected_context` 的用户消息”。触发消息在入队前由程序写入 Task 实体内部字段 `selected_trigger = {message_id, snapshot}`（`snapshot` 为程序侧 `selected_context` 形态；无选材即 `null`），Run 打开时复制到 Run 实体并在派发前按该快照重校验。**实体字段口径（诚实）**：`selected_trigger` 落在 **Task 与 Run 实体**，经 `GET /tasks/{task_id}` 的实体序列化（`_embedded` = `dict(versioned.entity)`）**可达**，因此登记为 `1.12.0` 下**加性、可选、非秘密的实体字段**，**不按“无实体字段变化”口径**；不改既有字段语义、不新增端点/错误码/枚举/迁移方向，**前端 `selected_sources` wire 无变化**。无选材触发 ⇒ 该 Run **不继承**更早消息的选材（`snapshot=null`）。

- **请求侧（加性可选）**：既有消息信封（§5.2 Task 消息、§4.3 全局消息）新增可选字段 `selected_sources`，数组 ≤ **3** 项，每项 `{source_id, source_version?, content_hash?}`。**省略时行为与现状逐字节一致**；请求体不能授予执行权限。
- **响应侧（加性可选）**：结果 `data`（reply/Run 上下文）新增 `resolved_source_bindings`（`{source_id, source_version, content_hash, layer, locator, char_count, truncated, truncation}`）、`context_truncated`、`provided_context_note`。程序解析，**不声称模型引用已验证**；UI 标签 `Sources`，**不虚构 verified 权威**。
- **有界与截断**：最多 3 来源、总 **12000 Unicode 字符**、有界读取；超长**显式截断并附 `truncation` metadata**，或**沿用既有 limiter 拒绝**（由实现注记声明实际分支）。正式（`formal`）优先、机器派生（`machine`）回退；**仅用已信任机器**，**无 OCR/重处理/新推理**。
- **派发前拒绝（复用 §4.2 既有错误码，不新增码）**：stale/revoked/missing/unreadable/cross-Task 在**模型派发前**显式拒绝；worker 派发前**再次校验**。撤销来源沿用 §6.6 的 `not_found`（404，`details.revoked=true`）fail-closed 语义。
- **不可信数据**：选定正文以分隔符隔离、**不作为指令**；Chat reply 与 worker context 使用**同一精确正文**；持久化 version/hash 引用 + 有界上下文快照，恢复/重放**不解析不同内容**。
- **作用域**：`global` 或单个 Task；**不跨 Task 携带**；切换 Task 清空。
- **持久化/绑定**：选定 version/hash 引用 + 有界上下文快照写入既有受控 SoT：消息日志存 `selected_context` 快照；Task/Run 实体新增加性可选字段 `selected_trigger = {message_id, snapshot}` 作为 Run 的触发绑定（Run 打开时从 Task 复制），worker 派发前按该绑定快照重校验。恢复/重放使用已保存快照，**不解析不同内容**。
- **兼容/变更控制**：请求/响应为**加性可选字段**，另加性新增 Task/Run 实体可选字段 `selected_trigger`（非秘密、实体序列化可达）；无新端点/错误码/枚举/迁移方向，既有字段语义不变 ⇒ 按 §13 属 **MINOR `1.12.0`（已实现）**。实现由**单一后端 owner** 同步常量与测试版本并做 docs finalsync。

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
- **执行器共享计数接线（`1.11.0`，LG-031 R2，无字段/端点变化）**：执行器支持加性可选的共享计数注入；默认产品装配（`api/bootstrap`）在 `configure_generation_ledger` 之后把同一**持久账本**注入真实执行器，使每个 worker/reviewer 的 loopback 认证代理都消费**同一持久硬上限**，不会按 worker/session 重置或回退为非持久内存计数。契约字段、端点不变。
- **产品路径自主 claim 接线（`1.11.0`，LG-031 phase3，无字段/端点变化）**：`api/bootstrap` 默认装配从 `decentralized_claim_enabled` 开关决定是否启用 `GraphDispatcher(autonomous_claim=True)` 并注入进程内 `ExecutionGrantRegistry`（关闭/缺省保持旧确定性 `plan_source=rules`、无工具、无 grant）；受限 claim 工具的发现投影加性补充程序拥有的 `objective`/`write`（内部 SDK 工具投影，非 HTTP 契约字段），使真实 worker 能据程序投影判定其节点产物。**不新增端点/枚举/错误码/字段，不改既有 `state`/`phase`/`acceptance` 语义，不新增供应商/秘密表单/常驻编排 agent。**
- **多候选自主选择（`1.11.0`，LG-031 POOL-FIX，无字段/端点变化）**：关闭开关时行为完全不变；开关开启时，程序不再把 worker 预绑定到**唯一** `scheduled_node`，而是按 Run 授权/worker 成员能力/依赖就绪/预算/容量/单 writer **计算合法 ready 候选集合**（`state=pending|ready|repairing`、能力被该成员覆盖、`depends_on` 全 `passed`、未超并行/写作限度），冻结为一个**多候选 pool grant**（进程内、非持久、非全局 token，授权集合与 claim 预约次数有界）。worker 经受限 `discover_and_request_claim(node_ref=...)` **真实选择**集合中任一 node 并申请领取；程序在 claim 时刻**重新基于已持久化的 Run/Subtask 事实**校验所选 node 仍在合法集合内（拒绝越 Task/Run、越能力、越 write/scope、已终态、已被其他 owner 持有、非池内节点），经 fenced 租约权威**原子授权所选 node**（恰好一个 winner，loser 得 `held_by_other` 等确定拒绝且可重新发现剩余合法候选），随后绑定所选 node 的**隔离 workspace / 上游版本化 hash 上下文 / 成员配置**，执行结果 / manifest / 状态 / 交接均归属**所选 node**；未 claim 的候选不写任何控制状态，有界尝试耗尽后保持 pending 并以 `claim_required` 诚实非成功（不伪造 `passed`）。身份仍由程序推导（`owner` 不依赖 worker 自报），worker 不能直接改状态/预算/验收。**不新增端点/枚举/错误码/字段，不改既有 `state`/`phase`/`acceptance` 语义与迁移方向，不新增供应商/秘密表单/常驻编排 agent/组织平台；默认并行容量不改变。** 已验证层面：真 FileStore + 真多进程 + 真 git worktree（provider-substitute，产品真实生成 0）；真实 SDK 端到端双 worker 属后续单独冻结的真实证明 phase，此处不宣称。
- **受控两阶段 SDK 生命周期与冻结 lease owner（`1.11.0`，LG-031 runtime/API 集成）**：候选池路径的 worker slot 拆为两个**真实 SDK 会话阶段**，均在程序冻结的同一 Task/phase 预算与进程全局生成账本之内：① **选择会话**（phase 1）运行在专用**选择 scratch workspace**（非产品 workspace、非所选 node 的隔离 worktree），`allowed_tools=()` 不下发任何成员写工具，只附带受限 `discover_and_request_claim`，因此**选择前无写权限、不产生产物**；worker 自行选择候选并请求 claim。② 程序在 claim 时刻原子授权**所选 node** 并铸造 frozen execution grant；③ **执行会话**（phase 2）是由程序按**所选 node** 的隔离 workspace/objective/acceptance/上游版本化 hash 上下文与**该 node 的成员权限**构建的**另一个** SDK 会话；结果/manifest/状态/交接只归所选 node，故 B 结果不可能写成 A。选择会话的 pool grant 在选中后立即 revoke，不承当执行身份；执行会话不带 claim 工具。**禁止**新增常驻 selector/orchestrator：选择会话按需在 slot 执行内创建，不常驻。执行 grant 加性携带程序冻结的 **`lease_owner`**（worker 实例身份，非共享成员/调度器 owner），使两个真实 worker 竞争同一 node 时 fenced 权威恰好一 winner（loser `held_by_other`），且 HTTP renew/release 解析同一冻结 owner；`member_ref` 仍为认证身份。所有 SDK 会话结束/历史保留并参与 stopgate（`confirm_stopped` 真实确认；未确认保持 held）。离线真 SDK 0.1.22 + 本地受控 fake 上游（provider-substitute）端到端探针已证两阶段/非首项选择/隔离绑定/一 winner；真实 DeepSeek 正式验证留后续 PM 独立预算，本包产品真实生成 0。
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

- [ ] 契约版本与 `/api/v1`、`lightgravity.bot/v1` 在本文一致声明（LG-001 冻结 `1.0.0`；当前 `1.16.0`，变更记录见第 13 节）。
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
| `1.20.0` | 2026-10-18 | MINOR | 英文Reader转写及Settings/Chat/Files接入（§21）；UI与后端由LG168部署1.20，ASR关闭、质量QA失败保留 | 加性english_asr配置/处理能力/机器provenance；默认关闭，Personal隔离不变，30秒/无时间戳；处理可用不等于质量通过 |
| `1.19.0` | 2026-10-18 | MINOR | LG-140 冻结资料摄取 v2（§20）：`POST /sources` 加性 `intake_mode`（默认 `sync`）、消息加性 `source_refs`、`source`/`intake_job` 加性摄取边界字段、`GET /sources/{id}/receipt` 的 `receipt_version:2` 与独立 `text`/`keyword`/`semantic` 分支、健康能力 `material_intake_v2`/`semantic_search`/`media_direct_embedding`；明确发送前不摄取/不索引、后端持久工作、媒体直接 embedding、无自动重试、取消确认、重启不重放、搜索/保存设置不隐式全库重建，`POST /vector/rebuild` 收紧为管理员/受保护写入。**1.19功能已实现、独立QA通过，并已包含于LG168部署的1.20**；英文ASR保持关闭/质量门失败 | 仅新增可选请求/响应/实体/事件 payload 字段与三个默认 false 的能力；旧客户端缺省字段行为不变；不新增端点、错误码、Task/Run/Member/Subtask `state`/`phase`/`acceptance` 枚举或迁移方向；Personal 私有附件、ASR 不可用、既有 `selected_sources` 权限与 Task/Run 门不变 |
| `1.17.0` | 2026-10-17 | MINOR | LG-104连接弹窗与SDK provider配置/测试（§18），已实现/独立R2 QA通过 | 新增草稿测试/引用保护删除端点、Connection可选认证/本地模型字段/capabilities/last_test、TestResult可选draft标记；旧端点兼容、不迁移旧文件、不扩大native任务执行或任意custom host放行 |
| `1.16.0` | 2026-10-17 | MINOR | LG-066 全局/Team 状态查询与澄清的契约登记（实现随 generic 候选集成，§17）：既有 `POST /api/v1/conversations/global/messages` 加性新增响应 `kind:"query"`/`kind:"clarify"`、只读 `data` 快照与澄清标记；只按消息内显式合法 Task ID 唯一解析，缺失/非法/未知/多个不同 ID 时澄清，不猜测；成功查询不创建 Task/Run/worker、不调用模型，回复写入共享全局会话；Personal 仍 `switch_to_team` 且按身份隔离。**不新增**端点、请求字段、错误码、实体 schema、`state`/`phase`/`acceptance` 枚举、迁移方向、角色、招募流程、执行预算或供应商。普通团队消息仍 `recorded`；未知 `kind`/加性 `data` 可忽略。前端最低契约保持 `1.13.0`。 |
| `1.15.0` | 2026-10-17 | MINOR | LG-061／LG-062 账户管理命名里程碑：团队模式新增管理员账户管理端点与自助改密端点；账号事实源加性新增 `enabled`/`revision`/`session_version`；`GET /api/v1/health` 加性新增 `capabilities.accounts`；改密/重置/禁用/角色变更使目标旧会话在下一请求失效，SSE 约 2 秒重校验；末位可用管理员在存储锁内受保护。见 §16 | **仅新增团队模式端点、加性可选账号字段与健康能力**；不改变单用户行为、既有端点语义、错误码、`state`/`phase`/`acceptance` 枚举或迁移方向；不新增实体 schema；口令只存盐+哈希，响应/日志/校验错误不回声 |
| `1.14.0` | 2026-10-17 | MINOR | LG-054 当前身份 Personal 私聊端点及可选 `personal_chat` 能力，见 §15；LG-051 界面与兼容性修复已通过独立 QA | 新增 GET/POST `/conversations/personal/messages` 与健康能力字段；服务端推导身份、按用户／频道幂等，团队 Personal 不创建共享 Task／资料。单用户保留旧工作流，不改变实体 schema 或状态迁移 |
| `1.13.0` | 2026-10-16 | MINOR | LG-050 共享团队模式**实现**（接口范围见 §14）：显式、默认关闭的团队模式；新增 `/api/v1/auth/me|login|logout` 会话端点；消息加性可选 `author:{kind,username,role}`（服务端按会话写入）；新增 `forbidden`（403）错误码；`GET /auth/me` 以 `mode:"single"|"team"` 供前端判别。详见 [probes/team-chat-20261016](../probes/team-chat-20261016/README.md) | **仅新增可选端点、加性可选消息字段与一个新的错误码**；不改变既有端点、`state`/`phase`/`acceptance` 枚举或迁移方向；默认单用户逐字不变；`X-LG-Token` 不构成团队身份；团队模式匿名业务访问 default-deny。无秘密，账号仅存盐+哈希 |
| `1.9.0` | 2026-10-16 | MINOR | 首版返修后的串行集成收拢（唯一集成 owner）：① 新增加性可逆归档——`source` 加性布尔字段 `archived`（默认 `false`，§6.6）、`POST /sources/{id}/actions` 新增 `archive`/`unarchive` 动作与可选 `expected_revision`（§4.3、§6.6）；② 挂载 LG-037 可选向量端点 `GET /vector/status`、`GET /vector/search`、`POST /vector/rebuild`（§4.3、§6.6，默认禁用、仅环境变量配置、候选回源核对） | **仅新增可选非秘密字段、两个可逆动作与三个可选端点**；不改变 `revoke`/`delete` 语义（撤销仍 `status=archived` + 失效命中），不新增事件类型，不改变 `state`/`phase`/`acceptance`/`source.status` 枚举；向量默认关闭，不可用时词法/原件仍可用；不新增供应商、秘密表单或常驻编排 agent |
| `1.10.0` | 2026-10-16 | MINOR | LG-022 第二轮针对性返修（REFIX-R2）：① 停止门可接受**真实停止事实**（§9）——成功 Run 的 `cleanup` 常为 `pending`，停止门除 `cleanup=done` 外接受权威适配器停止确认（SDK session `__aexit__` / loopback 代理真实关闭），Run 加性新增可选 `reviewer_cleanup`（`{status,confirmed,...}`）；未知/仍活跃/关闭失败保留 `unconfirmed` 与 `session_refs`，不伪 `done`。② `GET /api/v1/diagnostics/generation` 加性新增 `persistent`（及损坏时 `corrupt`/`reason`）——全局生成计数改为受控 dataRoot 下持久账本，转发前持久预留，跨重启不归零，损坏绝不当 0 | **仅新增可选非秘密字段/诊断字段与停止门事实来源**；不新增端点、错误码、`state`/`phase`/`acceptance` 枚举或迁移方向；不改远端 exactly-once 语义；不新增供应商/秘密表单/常驻编排 agent |
| `1.11.0` | 2026-10-16 | MINOR | LG-031 runtime/API/SDK 集成落地后按实际公开兼容变化保守登记（取代 `1.10.0` 的“实现说明增补（无版本变化）”口径）：① **公开请求字段语义放松**——四个去中心化端点（`GET /runs/{run_id}/discoverable`、`POST /runs/{run_id}/claim_requests`、`POST /subtasks/{subtask_id}/lease/renew`、`POST /subtasks/{subtask_id}/lease/release`）的请求体 `owner` 由 `1.6.0` 冻结时事实采用的 **required/端点采用** 放宽为 **optional/兼容校验、不再具有授权含义**；② **加性内部字段**——`ExecutionGrant` 加性新增进程内非持久 `lease_owner`（程序冻结租约权威身份，`effective_lease_owner = lease_owner or member_ref`）。**精确行为**：四端点 principal/scope/fence 仅从 `ApiContext.worker_grant`（`X-LG-Execution-Grant`）解析的程序冻结 grant 推导；body `owner` 存在且不等于认证 principal ⇒ `claim_refused`/`identity_mismatch` 且不落盘；无 resolver/无效 grant ⇒ `claim_refused`/`unauthenticated`；body `capability`/`write`/`scope` 不授予权限。**回退**：旧客户端传 `owner` 仍被接受作一致性校验（不获授权），不传亦可用；认证 A 不能冒 B/跨 TaskRun；只读身份不能写。**安全边界**：未配置/未认证一律 default-deny 且不写业务状态；仍不接受浏览器直接指定任意 `owner`；`lease_owner` 不进入 HTTP/实体 schema（进程内非持久）。 | **仅公开请求字段语义向后兼容放松 + 加性进程内字段**；不新增/删除端点、错误码、`state`/`phase`/`acceptance` 枚举或迁移方向；不改变实体 schema、去中心化默认关闭与确定性 `plan_source=rules` 回退；不新增供应商/秘密表单/常驻编排 agent |
| `1.10.0`（实现说明增补，已被 `1.11.0` 取代保留） | 2026-10-16 | 无版本变化（历史口径） | LG-031 runtime/API/SDK 集成（唯一串行 owner）：① **多候选自主选择 + 受控两阶段 SDK 生命周期**（§6.5）——选择会话（选择 scratch workspace、`allowed_tools=()`、仅受限 claim 工具）→ 程序原子授权所选 node → 独立执行会话绑定**所选 node** 的隔离 workspace/objective/上游 hash 与成员权限；pool grant 选中后即 revoke；不新增常驻 selector/orchestrator；执行 grant 加性携带程序冻结 `lease_owner`（worker 实例身份）使两 worker 竞争同 node 恰好一 winner。② **F2 execution-identity 实现对齐**（§4.3）——四端点经 `ApiContext.worker_grant` 从程序冻结 grant 推导 principal/scope/fence；body `owner` 降为**兼容可选、非授权**；未配置/未认证 default-deny 且不落盘；body `capability`/`write`/`scope` 不授予权限。**此行的公开字段语义放松已被 `1.11.0` MINOR 行取代**（保留以如实记录历史口径，不重写旧日志） | **仅实现对齐与加性内部语义澄清**；`owner` 字段保留为可选兼容（旧客户端仍可传同名值但不获授权）；不新增供应商/组织平台/常驻编排 agent；不改变 `state`/`phase`/`acceptance` 语义与迁移方向 |
| `1.8.0` | 2026-10-16 | MINOR | LG-022 首版集中 QA 阻断项 D1/D2 返修 R1：① 状态迁移加性新增 `verifying → recovery_required` 与 `repairing → recovery_required`（§6.1），用于独立复核/返修阶段重启后未知副作用诚实进入人工恢复；② 新增只读诊断端点 `GET /api/v1/diagnostics/generation`，报告进程全局上游生成请求计数 `{count, limit, remaining}`（§4.3、§9），覆盖 worker/reviewer/重试，转发前计数 | 新增两个合法迁移方向（纯加性，不改既有方向）；新增一个只读端点；不改变既有端点语义、错误码、既有 `state`/`phase`/`acceptance` 取值与既有字段语义；不新增供应商/秘密表单 |
| `1.7.0` | 2026-10-16 | MINOR | LG-017 返修 R1：新增加性设置角色/字段 `default_reviewer_connection_ref`（§6.5，独立复核者默认连接），Task 返修账本加性字段 `reviewer`/`reviewer_kind`/`model_usage`（§6.1），review/rework 事件加性 payload `reviewer_kind`/`model_calls`/`usage`（§5.1），以及独立复核语义（§9：无可用 reviewer ⇒ `unavailable` 并阻止 accept；机器门不等于独立复核） | **仅新增可选非秘密字段与加性 payload**；不新增/改变端点、错误码、`state`/`phase`/`acceptance` 枚举、迁移方向与既有字段语义；不新增供应商、秘密表单或供应商切换 |
| `1.6.0` | 2026-10-16 | MINOR | 由**单一 docs08 owner 串行冻结**两条**尚未实现**新线契约：① LG-028 去中心化协作——Subtask 加性可选字段 `fence`（§6.3）与租约/fencing/过期语义、发现/领取/续租/释放/协作端点（§4.3）、事件 `subtask.lease_*`/`subtask.claim_refused`/`collab.*`/`handoff.*`（§5.1）、错误码 `stale_lease`/`claim_refused`（§4.2）、设置开关 `decentralized_claim_enabled`/`collab_requests_enabled`/`claim_lease_seconds`（均默认关闭，§6.5）、协作预算与 `recovery_required` 说明（§6.2）；② LG-033 资料摄取/检索——新实体 `source`/`intake_job`（§6.6）与 ID 前缀（§3.1）、端点 `sources`/`intake`/`search`/`inbox`（§4.3）、事件 `source.*`/`intake.*`（§5.1）、错误码 `source_conflict`/`source_stale`/`index_unavailable`（§4.2） | **仅新增可选实体/schema/字段、端点、事件与错误码**；不改变既有 `state`/`phase`/`acceptance` 枚举、迁移方向、既有端点与既有错误码语义；去中心化端点默认关闭。新端点/实体**仅冻结接口，尚未实现**；`source`/`intake_job` 展示状态**不加入** §6.1 Task `phase` 枚举。既有 Files 上传/下载语义不变。完整 checkpoint skip 仍**未实现**，恢复仅依赖已落盘证据 |
| `1.12.0` | 2026-10-16 | MINOR | LG-042 冻结、LG-043 实现“手动选定已摄取资料”快速原型接口（§6.6.1，详见 [docs/10](10-selected-material-prototype.md)）：消息信封加性可选 `selected_sources`（≤3 来源、`{source_id, source_version?, content_hash?}`）；结果 `data` 加性可选 `resolved_source_bindings`/`context_truncated`/`provided_context_note`；总 12000 Unicode 字符有界、显式截断 metadata、正式优先机器回退、派发前 stale/revoked/cross-Task 拒绝、不可信数据隔离、不跨 Task 携带。实现采用显式截断分支；持久化 `selected_context` 快照 + 内部 body digest 用于 worker 派发前重校验。**绑定修正（R1）**：新增加性可选 Task/Run 实体字段 `selected_trigger = {message_id, snapshot}`（触发消息在入队前冻结、Run 打开时复制、派发前按该快照重校验），取代首版“最近一条含 selected_context 消息”启发式，使 Run 只用自身触发的精确选定、无选材不继承、重启保持 | **新增可选请求/响应字段 + 加性可选实体字段 `selected_trigger`（实体序列化可达，非秘密） + 内部非客户端快照（消息 `selected_context`、body digest）**；不新增端点/错误码/枚举/迁移方向；无秘密；旧客户端省略字段行为不变；前端 `selected_sources` wire 无变化 |
| `1.12.0`（预留登记，保留历史口径） | 2026-10-16 | MINOR（预留） | LG-042 冻结“手动选定已摄取资料”快速原型接口（§6.6.1，详见 [docs/10](10-selected-material-prototype.md)）：消息信封加性可选 `selected_sources`（≤3 来源、`{source_id, source_version?, content_hash?}`）；结果 `data` 加性可选 `resolved_source_bindings`/`context_truncated`/`provided_context_note`；总 12000 Unicode 字符有界、显式截断 metadata、正式优先机器回退、派发前 stale/revoked/cross-Task 拒绝、不可信数据隔离、不跨 Task 携带。**仅登记预留**，`contract_version` 值在实现集成时由 A 后端 owner 同步 | 仅新增可选请求/响应字段；不新增端点/错误码/枚举/迁移方向；无秘密；登记时本文件头部版本值暂不变 |
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
| 资料摄取 v2：发送前草稿/发送后持久摄取、独立回执分支、自动媒体直接 embedding、配额/重试/取消/重启、搜索/设置不隐式重建、Personal 隔离（§20） | LG-141、LG-142、LG-143、LG-144 串行集成、**LG-145（独立版本/浏览器 QA）** |
| 全局/Team 状态查询：唯一合法 Task ID、澄清、只读快照、不建 Task/Run、Personal/团队权限（§17） | LG-096（独立 QA）、LG-097 分类修复串行集成后最终复验 |

## 14. 共享团队模式（1.13.0，LG-050，独立 QA 通过、有限制）

团队模式显式开启，一个共享工作区，所有登录成员共享聊天、Task 和资料。此模式不承诺私聊、私有资料或多租户隔离；默认关闭，原单用户路由保持。**实现已完成并串行集成到候选 `feat/team-integration-20261016`；已由独立 QA 验证真实 HTTP、CLI 及 Firefox 双用户上下文（PASS_WITH_LIMITATIONS），证据见 [QA 报告](../probes/team-chat-20261016/qa/QA-REPORT.md)；用户最终验收仍待定。**

### 14.1 配置与账号

- `LIGHTGRAVITY_TEAM_MODE` 默认 false；`1/true/yes/on` 开启。
- `LIGHTGRAVITY_TEAM_ACCOUNTS` 默认受控数据根下 `team/accounts.json`；账号配置是独立事实源，不能由 Files 接口读取。只存口令盐与哈希，原子写入，不能再另维护一份权威配置。
- `LIGHTGRAVITY_TEAM_SESSION_TTL_SECONDS` 默认 28800；会话暂存服务端内存，服务重启后重新登录。
- `LIGHTGRAVITY_TEAM_COOKIE_SECURE` 默认 false（本地 HTTP）；HTTPS 使用时可显式开启。cookie `lg_session` 使用 `HttpOnly; SameSite=Lax; Path=/`，配合同源 Host/Origin 守卫。
- `LIGHTGRAVITY_TEAM_BOT_MENTION` 默认 `@bot`，匹配消息首部（允许前导空白，后接空白、标点或结束）。
- 本地账号管理由 CLI 提供 `user add` / `user list`，口令经交互输入，禁止放到命令行参数、错误或日志。账号角色仅 `admin`、`member`。

### 14.2 HTTP 端点与授权

| 端点 | 请求与响应 |
|---|---|
| `GET /api/v1/auth/me` | 匿名可读；`{mode:"team",authenticated:false,username:null,role:null}`；已登录填真实用户名/角色。单用户模式返回 `{mode:"single",authenticated:true,username:null,role:"admin"}` |
| `POST /api/v1/auth/login` | `{username,password}`；成功 `{username,role}` 并设置不透明会话 cookie；无此用户与口令错误统一 `401 unauthorized`。单用户模式 404 |
| `POST /api/v1/auth/logout` | 撤销会话并清 cookie，204；重复操作幂等 |

团队模式匿名访问所有业务 API（含历史、文件、下载、事件）均 401；`auth/me`、`auth/login` 与健康检查除外。已登录成员可以协作普通任务、读写共享资料。系统管理写（模型连接、秘密凭证、Settings、资源配置，含 Task `resource_proposal` 间接路径）仅管理员；非管理员返回 `403 forbidden`，沿用统一错误信封、`retryable:false`。`X-LG-Token` 与请求体自报角色不能替代用户会话或提升权限。团队模式前端不注入运行时管理 token。

### 14.3 消息与同步

- 消息新增加性可选 `author:{kind,username,role}`：服务端取登录身份写入，禁止客户端伪造。人类 `kind:"user"`，bot 回复 `kind:"bot"`；旧消息无 author 时保留原样，前端标为历史未知作者。
- 团队全局普通消息仅持久化，返回 `kind:"recorded"`、`reply:null`、`data:{intent:"recorded",creates_task:false}`，不调用模型或新建 Task。
- 仅显式 mention 的全局消息去除前缀后进入原分类与任务路由。Task 内显式消息沿既有行为，不要求 mention。
- 持久化与请求幂等、并发序号保持；bot 回合有序处理。全局消息同步先采用约 3 秒轮询既有读取接口，游标补齐、按消息 ID 去重；页面隐藏暂停，失效登录返回登录界面。不把全局轮询宣称为新增 SSE 事件流。
- 默认单用户模式不要求 mention，旧客户端省略加性字段时保持现有行为。不修改 Task/Run 状态枚举或迁移方向。真实 SDK 执行能力沿原验收记录，本次不能以认证测试替代真实 SDK 验收。

本节记录契约与实现边界；运行命令、精确实现偏差和测试证据见 [probes/team-chat-20261016](../probes/team-chat-20261016/README.md)。下表为集成时确认的**精确实现偏差/补充**，均为加性且不改变默认单用户行为：

- `forbidden` 错误码（HTTP 403，`retryable:false`）；`/settings*` 的**全部方法（含 GET）**为 admin-only，`PATCH/PUT/DELETE /api/v1/resources/{kind}/{id}` 与含 `resource_proposal` 的 Task 消息同样 admin-only。
- 登录失败限流：同一 `(client-host, username)` 在 60s 滚动窗口内 5 次失败后返回 429 `budget_exhausted` 并带 `Retry-After`；成功清除计数（这是加性实现，不新增专用错误码）。
- `/auth/logout`：无 cookie 为匿名 `401 unauthorized`；携带任意（含已失效）cookie 为幂等 `204` 并清 cookie。已登出会话的既有 SSE 流在约 2s 内被关闭。
- 团队模式静态前端/资源路径匿名可加载（以便渲染登录门），但**页面注入的运行时 token 为空字符串**；`X-LG-Token` 不能构成团队身份或提权。
- `AccessPolicy.authorize` 加性新增关键字 `admin: bool = False`（单用户策略忽略）；`is_sensitive_request` 加性覆盖资源变更；Files 在团队模式额外拒绝解析到受控 `<data>/team/` 内路径。
- 前端启动探测 `/auth/me` 为显式三态：探测中显示 Loading；仅**明确 `mode:"single"` 或 legacy `404`** 进入单用户工作台；网络/服务端错误显示可重试错误，绝不乐观降级为单用户绕过登录。团队匿名才显示登录门。

LG-050 已本地合入并通过独立技术 QA；限制和真实证据见上述报告。本次未重验真实模型/SDK 交付链路，未发布部署。

## 15. 个人私聊通道（1.14.0，LG-054，独立 QA 通过、有限制）

> 加性 MINOR：602c7af 已通过独立版本 QA 并以一致产品树整合到主目录 ea6da80，实际启动入口亦已更新。验证边界见文首与完整交付记录。

- `GET /api/v1/conversations/personal/messages`：读取**当前登录身份**的私有会话历史；`after`/`limit` 与全局会话一致，响应含 `items`/`next_cursor`。
- `POST /api/v1/conversations/personal/messages`：`{message_id,content,role?,attachments?,correlation_id?,request_id?}`。`extra="forbid"`，因此客户端自报 `owner`/`author` 为 422；owner 只取服务端会话身份（团队模式）或单用户标识。
- 私有会话 id 由登录用户名单向哈希派生的稳定 `conv_<ULID>` 表示，落盘在 `<data>/conversations/<id>/messages.jsonl`，与共享全局会话文件隔离；私有消息端点只读取当前服务端身份；Files 和资料路径接入同时保护 conversations 与保存私有回复的 coordinator 内部日志，覆盖成员及管理员。此处不承诺操作系统进程或任意执行工具的多租户隔离。
- 团队模式下 Personal 为**纯聊天**：直接问答走既有 responder 接口；交付/控制/重试等请求返回 `kind:"switch_to_team"` 与明确提示，绝不创建 Task/Run、绝不写共享全局/Task 日志或事件、绝不接入共享资料。`attachments`/`selected_sources`/`workspace_ref`/`agent_ref` 返回 `503 capability_unavailable`，`details.hint="switch_to_team"`。
- 幂等键按 `personal:<owner>:message:<message_id>` 命名空间隔离，避免跨用户/跨通道碰撞。
- 单用户模式复用既有全局会话 id 与行为（含交付建 Task），Personal 即旧全局会话；团队模式未启用时前端 Team 标签可见但禁用，并给出真实启用提示，不伪造团队。
- `GET /api/v1/health` 加性新增 `capabilities.personal_chat`（可选；团队 Personal 须稳定版 >=1.14,<2 且该能力明确为 true；缺失时禁用并说明，保存的 Personal 入口退回 Team，不能请求不存在的私聊端点。核心共享／默认单用户仍支持稳定版 >=1.13,<2，单用户保留旧全局／Task／资料能力）。不新增实体 schema、枚举或迁移方向；团队匿名访问仍为 default-deny。

## 16. 账户管理（1.15.0；LG-061 默认管理员 + LG-062 管理界面）

> 加性 MINOR、团队模式专属；单用户模式不挂载任何账户管理路由，保留原有 Models & Providers 行为。LG-061 首次初始化（空账号库）按用户指定种子 `admin`/`admin123`，只经既有 PBKDF2 盐+哈希路径写入；任何非空账号库或用户改密后的重启都不覆盖。LG-062 提供 Settings 管理界面与自助改密。独立最终 pi QA PASS，本地运行与限制见上述证据。

### 16.1 端点与授权

| 端点 | 授权 | 请求与响应 |
|---|---|---|
| `GET /api/v1/accounts` | 管理员 | `{accounts:[{username,role,enabled,created_at,revision}]}`；不含口令/盐/哈希 |
| `POST /api/v1/accounts` | 管理员 | `{username,password,role:"admin"\|"member"}`；`201` 返回同一白名单；重复用户名 `400 invalid_request` |
| `PATCH /api/v1/accounts/{username}` | 管理员 | `{role?,enabled?,expected_revision?}`；成功写入使 `revision+1` |
| `POST /api/v1/accounts/{username}/password` | 管理员 | `{password,expected_revision?}`；重置目标口令并使目标旧会话失效 |
| `POST /api/v1/account/password` | 任意已登录用户 | `{current_password,new_password,confirmation}`，只改自己；成功 `200 {username,signed_out:true}` 并清 cookie |

- 权限在服务端强制：全局策略把 `/api/v1/accounts*` 的**全部方法（含 GET）**标为 admin-only；非管理员 `403 forbidden`，匿名 `401 unauthorized`。端点级再校验一次。前端隐藏不是授权边界。
- `expected_revision` 存在且不等于当前 `revision` ⇒ `409 revision_conflict`（旧写入不覆盖新状态）；禁用/降级末位可用管理员 ⇒ `409 illegal_transition`（`details.reason="last_active_admin"`）。该守卫在同一存储锁内复核，两个并发降级/禁用不可能同时观察到“还剩一个”。
- 用户名不可变；不提供删除、邀请或邮件自助注册。

### 16.2 账号事实源（加性字段）

- 受控写入先取得同路径稳定侧文件 `accounts.json.lock` 上的既有 POSIX flock，再完成读取、版本／末位管理员检查与原子替换；CLI 与服务跨实例／进程共用该锁，保留未知字段及 0600 文件模式。锁竞争超时使用既有 `409 lock_conflict`（可重试），不静默覆盖。单主机协作写入保证不扩展为分布式事务。
- 沿用 `<data>/team/accounts.json` 单一事实源，不建立第二份权威账号数据。加性字段 `enabled`（默认 `true`）、`revision`（默认 `0`）、`session_version`（默认 `0`）；旧账号缺字段按此默认读取，未知字段在受控写入后保留。
- 口令仍为 PBKDF2-HMAC-SHA256（每账号随机盐）；响应/日志/URL/浏览器持久存储不含口令、盐或哈希；`422` 校验错误亦不回显提交值。
- 账号库为空（首次初始化）时团队模式种子 `admin`/`admin123`；已有账号、自定义角色或改密后重启**绝不**被覆盖；单用户模式不读取/创建该文件。

### 16.3 会话与失效

- 会话记录签发时的账号 `session_version`；每次请求与既有 SSE 重校验（约 2s）读取存储中的当前 `enabled`/`role`/`session_version`，绝不信任会话缓存的旧角色。
- 改密/重置、禁用、角色变更使 `session_version+1`，目标旧会话在下一请求失效，SSE 流约 2 秒重校验后关闭；重新启用不会复活旧 cookie；管理员改自己的口令也回到登录门。
- 服务重启仍使内存会话失效（1.14 既有语义）。

### 16.4 前端与兼容

- Settings 子区：`Models & Providers`（管理员）、`Accounts`（管理员）、`My Account`（所有登录用户）。成员只挂载 `My Account`，不请求 Models/Connections，也不请求管理员账户列表。
- `GET /api/v1/health` 加性新增可选 `capabilities.accounts`；后端缺少该能力或为单用户模式时前端不展示账户子区并如实说明。单用户保留 `Models & Providers` 原有行为。

## 17. 全局/Team 状态查询与澄清（1.16.0，LG-066 实现与 generic 集成的契约登记）

> 加性 MINOR，**不是新功能授权**：HTTP 行为与前端 `reply` 渲染已在 generic 集成候选中；本节只把已实现的公开行为登记到 docs/08。未新增端点、请求字段、错误码、实体 schema、状态/阶段/验收枚举、迁移方向、角色、招募流程、执行预算或供应商。默认单用户与 1.15 团队模式保持。

### 17.1 请求、身份与目标解析

- 复用 `POST /api/v1/conversations/global/messages` 与既有 `GlobalMessageRequest`；请求字段不变（`message_id`、`content`、`role`、`attachments`、`correlation_id`、`request_id`、`workspace_ref`、`agent_ref`、`selected_sources`）。**不新增** `task_ref`/`task_id` 客户端字段；`extra="forbid"` 保持，客户端自报 `author`/`owner` 等仍为 `422`。
- Team 模式：匿名 `401 unauthorized`；已登录 `member`/`admin` 均可查询同一共享工作区的 Task。仅显式 `@bot`（`LIGHTGRAVITY_TEAM_BOT_MENTION`）消息进入分类与查询路由；未 mention 的普通消息仍只持久化。Personal 通道不执行此查询：状态查询作为非聊天请求返回 `kind:"switch_to_team"`，不创建 Task/Run、不写共享全局/Task 日志或事件、不跨用户可见。
- 单用户模式：沿用既有全局入口，无需 mention；Personal 复用同一全局会话，行为与旧单用户全局对话一致。
- Task 目标只来自消息正文中的**精确合法** `task_<26 位 Crockford Base32>` token（§3.1）；内部调用提供的合法 `task_ref` 可作为唯一目标。**没有**“最近/唯一活跃 Task”猜测，也不做跨实例全局解析：另一实例未持有的合法 ID 仍按未知澄清。
- 任何 task 形状但不符合精确语法的 token 均记为非法；非法 token 与合法 token 同时出现时仍先澄清非法值，不执行部分解析。

### 17.2 响应与只读状态快照

成功（唯一合法且存在的 Task）沿用既有结果信封，加性扩展如下；示例由当前实现组装，**不是**新增 JSON Schema：

```json
{
  "kind": "query",
  "reply": "Task task_...: status=done phase=completed queue=... run=... 只读查询，未创建或启动 Task/Run。",
  "task_id": "task_...",
  "run_id": null,
  "conversation_id": "conv_...",
  "queue_state": null,
  "candidates": [],
  "data": {
    "task_id": "task_...",
    "status": "done | in-progress | todo",
    "phase": "<现有 TaskPhase>",
    "revision": 3,
    "queue": {"state": "<队列状态|null>", "order": 1, "owner": "<owner|null>"},
    "active_run": "run_...|null",
    "run_state": "<现有 RunState|missing|null>",
    "archived": false,
    "acceptance_status": "<现有 acceptance.status|null>",
    "candidate_ref": "<当前候选引用|null>",
    "artifact_refs": ["evidence:<run_id>/<name>@sha256:<hex>"],
    "creates_task": false,
    "creates_run": false
  }
}
```

- `status`/`phase`/`run_state`/`acceptance_status` 只使用既有 §6 取值；`run_state` 额外允许 `missing` 表示 `active_run` 指针指向已不存在的 Run。`queue_state`/`run_id`/`queue`/候选/验收/产物字段可为 `null` 或空。`artifact_refs` 是持久化字符串引用列表（沿用既有 canonical evidence 引用），不新增产物实体。
- `data` 是**读取时快照**，可能立即过期；它不是租约、锁、预留或执行授权。查询只读持久 TASK/RUN 状态，不打开 worker/session、不创建或调度 Run、不调用模型、不修改 Task/Run/队列/验收状态。
- 查询回复以确定性 assistant 消息写入**同一共享全局会话**，所有登录成员可见；相同 `message_id` 幂等，不重复追加。

澄清（`kind:"clarify"`、`task_id:null`、`reply` 说明原因并明确未创建/启动任何任务）：

| 情况 | `data` 加性标记 |
|---|---|
| 没有 Task ID | `{intent, missing_task_id:true}` |
| 非法 Token | `{intent, invalid_task_ids:[...]}` |
| 多个不同合法 ID | `{intent, ambiguous:true, task_ids:[...]}` |
| 合法但未知 | `{intent, unknown_task_id:"task_..."}` |

澄清回复同样持久化到共享会话，但绝不创建 Task/Run/worker、不调用模型；`candidates` 不用于这类查询澄清（仍保留给既有控制目标解析）。普通 Team 消息保持 `kind:"recorded"`、`reply:null`、`data:{"intent":"recorded","creates_task":false}`，不做查询、不写 assistant 回复。

### 17.3 兼容、边界与版本判定

- **为什么是 MINOR**：既有端点与请求 schema 不变，普通消息行为不变；仅新增 `kind` 取值与 `data` 加性键。不知道 `query`/`clarify` 的客户端仍有 `reply`/`task_id`，并可忽略未知 `data`。无新错误码，失败沿用既有 `unauthorized`/校验语义。未新增 health capability；前端最低兼容仍为 `>=1.13,<2`，通过既有 `reply` 路径渲染，不做版本门控。按 §13“新增向后兼容字段/事件类型为 MINOR”记为 `1.16.0`。
- **不构成 MAJOR**：旧全局查询曾可能落入未冻结的通用回退（`data.record_seq` + 通用 reply），但该形状从未写入 §5.2/§14.3；docs/04 已要求显式目标与不猜测。本节冻结校正后的行为，因此不属于改动已冻结字段语义。
- **分类边界**：查询入口仍使用既有分类器；包含状态词汇的交付描述仍可能被分类为查询，这是独立的分类器缺陷（LG-097），本节不修、不新增优先级规则，也不代表其已修复。
- **验证边界**：确定性 coordinator/HTTP 测试与前端渲染属于 generic 候选证据；独立版本 QA 仍待 LG-096，LG-097 串行修复后需最终复验。本节不声称真实 SDK/模型验证。

## 18. Provider配置与连接草稿测试（1.17.0，LG-104；已实现/独立QA通过）

本节优先于早期首版只允许DeepSeek保存/测试的限制，保留执行边界。实现验收范围见 [MODAL-CONTRACT](../probes/provider-setup-20261017/MODAL-CONTRACT.md)，本节为公开接口事实源。

实现状态：main df53ead/产品7fe66d8，独立R2真实前后端8场景通过，已本地更新8123；真实供应商验证与LiteRT硬件推理未做。首轮真实引用/删除竞态已由native修复、pi集成后独立复验。详情见[交付](../probes/provider-setup-20261017/qa-r2/DELIVERY.md)。

### 18.1 Connection加性字段和能力

Connection前后端create/update/view及编译配置加性允许可选非秘密字段：`auth_mode: api_key|adc|proxy_api_key|none`、`project`、`location`、`model_path`、`litert_backend: CPU|GPU|NPU`。更新允许可选`backend`，验证合并后完整状态；省略保留、null清空，旧记录省略时按既有含义解析，不迁移旧文件或删除秘密。provider切换不得静默把旧密钥发到新provider/endpoint，保存路径保留引用和显式移除/版本检查语义，不声称跨文件原子事务。

响应可选`capabilities`对象，各可选boolean字段`configurable`、`testable`、`executable`、`vendor_verified`分别表明存储、测试路径、任务执行及真实厂商验证事实，不能相互推导。Gemini API和Vertex Express是API key路径；Vertex Standard是project/location+ADC且不与key混填；LiteRT为model_path+runtime backend，测试只做包/文件/配置检查，不自动安装/下载/推理；OpenAI-compatible继续经loopback代理注入Key。native Task executor/default选择仍不开放；custom endpoint保存不等于host获准或协议已验收。实际SDK固定0.1.22。

### 18.2 草稿测试请求和响应

`POST /api/v1/settings/connections/test-draft`，与现有设置写入/测试使用相同管理员、运行token、Host/Origin保护。成员403、未认证401；路由不得被动态connection ID吞掉。请求：

```json
{
  "connection": {
    "backend": "openai-compat",
    "model": "deepseek-v4-flash",
    "base_url": "https://api.deepseek.com/v1",
    "auth_mode": "proxy_api_key"
  },
  "credential_value": "write-only optional value",
  "existing_connection_id": "optional saved ID",
  "expected_revision": 0,
  "allow_network": false
}
```

`connection`只接收backend/model/base_url及§18.1认证/本地参数，不接受客户端任意credential_ref。新建草稿省略existing_connection_id/expected_revision；编辑可提供两者以沿用同一连接秘密，必须服务端核实revision及backend/auth/endpoint origin等接收凭据身份未改变，否则要求新Key或拒绝测试，不把旧秘密发送到另一个目标。版本错误沿用既有409 revision_conflict；字段错误沿用validation语义，错误响应不得包含提交秘密或框架校验的原始input。

返回沿用既有安全分层TestResult，加性`draft:true`；沿用既有字段名`connection_id`、`connection_revision`，未保存时可为null，不引入平行connection_ref别名。保留六个已有分层名，静态SDK构造结果可归config_parse；仍区分静态有效、请求成功与工具/结构化能力。响应不回显明文秘密、秘密哈希、secret-derived fingerprint或SDK配置；不将草稿测试成功提升为持久版本的verified。前端按当前弹窗实例和草稿generation绑定结果，修改字段/密钥后失效，关闭/重开/切换后迟到结果不能回填。

### 18.3 不落盘、预算及兼容

草稿测试不创建/修改Connection，不写secret store、持久测试诊断、defaults、Task/Run/队伍；秘密仅当前请求内存。真实请求的全局生成计数预留及必要脱敏操作日志允许持久化，不记录请求正文/Key/SDK config。旧`/{id}/test`继续绑定已保存revision/credential version并保存安全诊断，旧客户端无需迁移。

只有用户显式点击才设置allow_network=true；缺省false只做静态检查。每次最多一个最小模型请求，无tools/subagents/自动重试，有超时和实际停止确认；native测试同样使用全局持久账本，cap0或账本损坏时不请求，不可绕过计数。当前服务用户已取消全局调用次数上限（环境变量缺省，limit=null只计数）；这不取消单次测试边界，不授权开发验证擅用真实凭据。ADC静态检查不触发metadata或gcloud；LiteRT不做推理。重复点击测试不能被进程累计一次额度永久阻止，保存仍独立于测试结果。

新增端点、可选字段与能力为向后兼容MINOR，不改变既有state/phase/acceptance枚举、Task权限、默认热替换规则或最低兼容1.13。真实厂商验证、SDK本地协议验证、静态构造与浏览器交互分别记录，不能互相替代。

### 18.4 列表测试摘要与删除连接（LG110接口澄清）

ConnectionView加性可选`last_test`：null或`{test_id?,overall,finished_at,connection_revision?,credential_version?}`。只读取既有saved-test安全诊断的最新记录，不把draft写入该字段，不把测试状态复制成另一份配置权威；版本/凭据版本不匹配显示stale，缺失显示Not tested。

新增`DELETE /api/v1/settings/connections/{id}`，JSON body为`{expected_revision:number}`，采用相同管理员/运行token/来源保护；成功200返回`{deleted:true,id}`，不存在404、版本过期409 revision_conflict。被默认/Agent等有效引用时服务器拒绝，沿用既有冲突/校验信封并安全给出引用；不得只靠前端预检查，不修改其他引用、不留下悬空默认。读版本/引用检查与删除遵既有受控写入/锁/并发规则。删除连接不自动删除secret-store值，避免破坏共享凭据；真实用户连接不作为开发测试数据。此1.17.0加性端点已实现并通过修复后独立QA。

并发实现/验收：受支持的ConnectionService删除与默认引用修改、ResourceService Agent引用修改共享dataRoot引用flock，并在实体锁前获取，串行化引用验证/写入与删除guard/unlink。独立R2对两个胜出顺序、真实HTTP及默认200轮/Agent120轮验证零悬空。它不是跨文件ACID或对raw低层Store/外部文件编辑的事务保护；绕过受控service的写入不在此保证内。§18.4已实现并通过修复后独立QA，不再等待集成。


> **2026-10-18最终状态**：隔离候选94571a0/契约1.18.0已通过LG123独立QA的有界真实样本验收。下文“待QA”为集成冻结时的历史门描述，已由[最终独立报告](../probes/chat-task-teams-20261017/qa-LG123-final/REPORT.md)补齐；8123仍1.17.0，未部署更新。

## 19. 1.18.0加性契约（LG-122；隔离完整候选已实现，待LG-123独立QA）

> **状态与门**：LG-117、LG-119、LG-120、LG-121已串行集成到隔离完整候选，`CONTRACT_VERSION`已在本候选内升为`1.18.0`；相关端点由真实`api/app.py`挂载，能力由真实装配声明，并通过局部整合检查。LG-123独立版本/浏览器QA**尚未执行**，因此任何页面/报告仍不得写“已交付”或生产可用；公开8123服务仍为1.17.0且未更新。允许的能力门为：`team_groups`（LG-121）、`private_attachments`（LG-119）、`embedding_settings`（LG-117）、`capacity_v2`（LG-121）；缺失能力的前端必须禁用入口并说明，不能靠404猜测。

### 19.1 范围与不变量

- 只新增向后兼容的只读投影、可选请求/响应字段、可选实体字段和受保护端点；不新增Task/Run/Member/Subtask `state`/`phase`/`acceptance`取值，不新增迁移方向。
- 同一Task仍最多一个非终止Run；`_open_run`、控制停止门、`recovery_required`与“不自动重放未知副作用”规则不变。容量只决定**何时**允许已合法的工作继续，绝不绕过这些门。
- 队列仍是FIFO；并发只允许已入队Task在容量内重叠，不把排队Task伪装成执行中。
- 私有附件、共享资料与Task/Team消息是不同作用域；身份授权在服务端执行，管理员也不能借Files/搜索/猜ID读取他人私有附件。

### 19.2 Team分组只读投影（LG-121）

`GET /api/v1/team/groups?view=all|active|history&task_ref=<id>&limit=1..200&cursor=`

- 认证/授权与既有`GET /tasks`一致：团队模式要求有效session；单用户沿用本地策略；匿名`401 unauthorized`。显式`task_ref`非法/不存在返回`404 not_found`；`view`非法返回`400 invalid_request`。
- 返回项只组合持久化事实，不写任何文件、不创建Run/worker、不调用模型：

```json
{
  "items": [{
    "task": {"id":"task_...","title":"...","status":"...","phase":"...","revision":1,"requirements_revision":1,"deliverable_revision":0,"archived":false,"active_run":"run_...|null","last_run":"run_...|null","queue":{"state":"...","order":1,"queued_at":"...","owner":null,"waiting_reason":null}},
    "active_run": {"id":"run_...","state":"...","attempt":1,"plan_source":"rules","plan_hash":"...","team_refs":["member_..."],"subtask_refs":["subtask_..."],"session_refs":["sdk-session-..."],"cleanup":{"status":"pending"},"reviewer_cleanup":null,"ended_at":null,"fail_reason":null,"waiting_reason":null},
    "runs": [{"id":"run_...","state":"failed","attempt":1,"plan_source":"rules","plan_hash":"...","team_refs":[],"subtask_refs":[],"session_refs":["sdk-session-..."],"cleanup":{"status":"pending"},"reviewer_cleanup":null,"ended_at":"...","fail_reason":"...","waiting_reason":null}],
    "members": [{"id":"member_...","run_ref":"run_...","role_ref":"...","role_category":"...","selection_reason":"...","state":"released","template_version":"1","connection_ref":null,"skill_refs":[],"capabilities":[],"assigned_subtask_refs":["subtask_..."],"assigned_subtasks":[{"id":"subtask_...","key":"...","capability":"implementation","state":"passed","depends_on":[],"blocked_by":[],"assignee_member_ref":"member_...","waiting_reason":null,"acceptance":{"status":"passed"},"fail_reason":null}],"config_hash":"...","fail_reason":null}],
    "subtasks": [{"id":"subtask_...","key":"...","capability":"implementation","state":"passed","depends_on":[],"blocked_by":[],"assignee_member_ref":"member_...","waiting_reason":null,"acceptance":{"status":"passed"},"fail_reason":null}]
  }],
  "next_cursor": null
}
```

- 实际候选在R2示例之外加性返回现有持久事实`run.session_refs`、`run.subtask_refs`、`member.role_category`与`member.selection_reason`，用于权威停止推导与招募来源展示；它们不是第二份状态源。
- `runs`按`attempt`/ID稳定排序；`active_run`可从`runs`中排除或标记，但不得把旧Run成员混入当前队伍。`released`不新增字段，由前端按§19.5的确定规则从`phase`/`queue.state`/成员状态推导。`members[].assigned_subtasks`与`subtasks[]`是真实Subtask字段的只读副本，不是第二份状态。
- 该端点只读；控制仍使用既有`POST /tasks/{id}/actions`。`GET /team/available`加性返回角色`role_category`/`capabilities`/`agency_source`/`recruitable`，失败原因沿用`availability.reasons`。

### 19.3 Personal私有附件（LG-119；隔离完整候选已实现，待LG-123）

**存储与所有权（隔离完整候选已实现）**：`<data>/private-attachments/<owner_digest>/<attachment_id>/ATTACHMENT.json` + `content.bin`。`owner_digest = sha256("lightgravity:private-attachments:v1:" + owner)`；`owner`只取服务端身份（团队session用户名或单用户`single`）。目录`0700`、文件`0600`；响应与消息不回显路径。所有权/哈希/状态只在文件SoT，消息只引用`attachment_id`。

`POST /api/v1/attachments/private?attachment_id=att_<ULID>&filename=<name>&media_type=<type>`：原始字节体，最大10,000,000字节；需同源/loopback受保护写与当前身份。同一owner同一`attachment_id`同字节幂等返回200；不同字节`409 revision_conflict`。成功201/200：

```json
{"attachment":{"attachment_id":"att_...","filename":"...","media_type":"...","size":123,"sha256":"...","status":"stored","created_at":"...Z"}}
```

- `GET .../private/{id}`返回同一规范元数据；`.../content`返回`{content,encoding,media_type,size,revision}`（文本或base64，边界同Files预览）；`.../download`流式返回字节并附stat型`revision`。所有读取先按服务端身份解析owner目录；未知/跨owner一律`404 not_found`（不泄露存在性）。
- `DELETE .../private/{id}`仅允许`status=stored`；成功204。已附加到消息或跨owner：已附加`409 illegal_transition`，跨owner/未知`404 not_found`。
- Personal消息端点只接受`attachments:[{attachment_id}]`；服务端逐个验证owner+`status=stored`，把规范化快照写入消息并把附件标记`attached`（附`message_id`）。快照加性包含`context_status ∈ {included,truncated,unsupported_type,binary_unsupported,too_large,unavailable}`与`context_chars`，供UI诚实显示模型上下文是否包含。任何`path`字段`422 validation_failed`；Task/Team消息继续只接受`path`，出现`attachment_id`为`422 validation_failed`。
- 权限矩阵：

| 操作 | 单用户 | 团队owner | 团队其他成员（含admin） | 共享Files/`/sources`/`/search`/`/vector/search` |
|---|---|---|---|---|
| upload/read/download/delete | 允许（owner=`single`） | 允许 | 404，禁止 | 不适用 |
| Personal消息引用 | 允许 | 允许 | 404/422，禁止 | 不适用 |
| 写入共享资料/索引 | 禁止 | 禁止 | 禁止 | 私有根必须被拒绝 |
| 模型上下文 | 仅owner；仅包含有界支持的文本附件 | 仅owner；仅包含有界支持的文本附件 | 禁止 | 永不进入共享上下文 |

- **共享边界**：`Files._is_protected`与`sources`路径摄入必须把`<data>/private-attachments`列为受保护根（即使workspace/data重叠、符号链接或管理员访问）；共享`/search`/`/vector/search`只读`source`索引，私有附件不登记为`source`。
- **模型上下文/处理（R2，必须实现）**：LG-119必须把**有界支持的文本附件内容**送入当前身份的Personal responder模型上下文；不是只存储。解析器只读私有根并逐次校验owner，不调用OCR/ASR/embedding/网络，也不登记共享`source`/索引。支持类型为`text/plain`/`text/markdown`/`text/csv`/`application/json`/`application/yaml`/`application/x-yaml`及`.txt/.md/.markdown/.csv/.json/.yaml/.yml/.log`扩展；每消息最多3个附件、每文件最多64 KiB原始字节、总上下文最多12,000 Unicode字符。超总量时显式截断并附`attachment_context_truncated`；二进制（NUL/UTF-8解码失败）或非支持类型不进入上下文，消息与回复必须说明`binary_unsupported`/`unsupported_type`/`too_large`，不得假装模型已读。上下文以不可信数据分隔符包裹，明确“不是指令”。解析失败/服务不可用回复诚实`unavailable`，仍可保留消息和附件。
- **实际调用链（隔离完整候选已实现）**：`api/conversations.py`（当前身份→`attachments`服务解析/快照）→`coordinator/service.py::submit_personal_message(..., attachment_context=...)`/`_route_personal`（独立kwarg，不写入`_global.append`的用户消息）→`coordinator/dialogue.py`（`ModelDialogue.answer(text, attachment_context=...)`组合有界prompt）→`api/bootstrap.py`（注入Personal responder）。不得把附件正文拼成用户`content`持久化，也不得让共享Team/global responder看到。
- 错误只复用既有码：`unauthorized`(401)、`not_found`(404)、`validation_failed`(422)、`invalid_request`(400大小/缺字段)、`revision_conflict`(409)、`illegal_transition`(409)、`capability_unavailable`(503旧后端/能力缺失)。

### 19.4 独立Embedding配置（LG-117；隔离完整候选已实现，待LG-123）

`SETTINGS.md`加性可选块（非秘密；与默认连接分离）：

```yaml
embedding:
  enabled: true
  base_url: "https://..."
  model: "embeddinggemma-2-Q8_0"
  credential_ref: "embedding-api"   # 服务端分配的稳定引用；可选
  timeout_seconds: 60
  cold_timeout_seconds: 150
```

- `GET /settings`加性返回`embedding`视图：`{enabled,base_url,model,timeout_seconds,cold_timeout_seconds,source:"settings"|"environment"|"none",credential:{ref,configured,source,version},cache:{compatible,reason,vector_model}}`；不含密钥。`enabled`只在已保存块存在时以保存值为准。
- `PUT /settings/embedding`（管理员/受保护settings）body：`{expected_revision,enabled,base_url,model,credential_action:"keep"|"set"|"remove",credential_value?,timeout_seconds?,cold_timeout_seconds?}`。`credential_value`只写不读；服务端固定/复用`credential_ref="embedding-api"`并走既有secret store；保存后清空。`revision_conflict`/`validation_failed`语义沿用既有settings。
- `POST /settings/embedding/test-draft` body：`{base_url,model,credential_value?,use_existing_credential:false,allow_network:false,timeout_seconds?,cold_timeout_seconds?}`。不写Connection/SETTINGS/secret/defaults/diagnostics/Task；`allow_network=false`只做静态校验，true才允许一次最小embeddings请求。返回`{draft:true,overall,requested_model,reported_model,dim,latency_seconds,finished_at,credential_source,checks:[{name,status,detail}],error|null,cache_impact}`；`reported_model`/`dim`必须来自真实响应，不能拿聊天响应或配置值冒充。
- **优先级（实现必须一致）**：① 已保存`embedding`块存在时，`enabled/base_url/model/timeouts`以保存值为准；`enabled:false`显式禁用且忽略环境变量。② 无保存块时，回退`LIGHTGRAVITY_VECTOR_BASE_URL`/`MODEL`/`TOKEN`/`TIMEOUT_SECONDS`/`COLD_TIMEOUT_SECONDS`，`source="environment"`。③ 已保存`credential_ref`时只解析secret store；secret缺失即未配置，不静默改用环境token。④ 未保存`credential_ref`时可按既有`SecretStoreCredentialResolver`顺序回退环境token并报告source。⑤ `LIGHTGRAVITY_VECTOR_DIM`若存在只作预期提示，实际维度以响应为准。
- **缓存/降级**：保存后若`enabled/base_url/model`变化，旧测试结果失效；向量缓存若模型不兼容，`/vector/status`报告`model_mismatch_rebuild_required`，UI提示重建，不混用旧向量；禁用/不可用仍保留词法检索与原件查看。测试连通/维度成功不等于检索质量通过。

### 19.5 多任务容量、等待与停止/恢复（LG-121）

**配置（环境变量，非秘密；启动时校验，非法即`config_invalid`并不启动执行）**：

| 变量 | 默认 | 语义 |
|---|---|---|
| `LIGHTGRAVITY_MAX_ACTIVE_TASKS` | `2` | 同时被准入且持有执行资源的Task数（从claim到`awaiting_acceptance`/终止/暂停/recovery释放） |
| `LIGHTGRAVITY_MAX_GLOBAL_SESSIONS` | `3` | 全局同时活跃SDK session总数，**包含worker节点与独立reviewer** |
| `LIGHTGRAVITY_MAX_REVIEWER_SESSIONS` | `1` | reviewer session子上限；须`max_active_tasks <= max_global_sessions - max_reviewer_sessions` |
| `LIGHTGRAVITY_MAX_PARALLEL_NODES_PER_TASK` | `2` | 每Task节点上限；实际同时不超过`task.budget.max_parallel` |

**共同计算规则（禁止每Task各自无限扩张）**：

0. **验收承诺（R2）**：本版本以`2 active Tasks / 3 total sessions / 1 reviewer / 2 nodes per Task`作为初始有界测试设计；LG-123必须让两个Task真实重叠执行并记录时间戳/隔离证据。不得把降级为`1/1`串行运行报告为并发验收通过；若环境只能串行，结论必须是“未验证/受阻”，而不是配置默认失败。

1. `TaskQueue`仍按FIFO选Task；只有全局active Task名额可用时才claim。名额满时Task保持`queued`，加性写`queue.waiting_reason="active_task_limit"`；获得claim时清空。
2. 每个准入Task最多一个非终止Run（既有`_open_run`）；Run内节点启动还须同时满足：本Task运行数<`min(task.budget.max_parallel, LIGHTGRAVITY_MAX_PARALLEL_NODES_PER_TASK)`、全局活跃session数<`LIGHTGRAVITY_MAX_GLOBAL_SESSIONS`。否则Subtask保持`pending`并写`waiting_reason="global_session_limit"`，不得启动或伪造`running`。
3. 独立reviewer从同一全局session池取1个，且不超过reviewer子上限；取不到时Run保持`verifying`并写加性`run.waiting_reason="reviewer_limit"`，不得假通过或提前验收。
4. 同一真实workspace路径的写节点在跨Task范围使用全局writer锁；拿不到锁的写Subtask保持`pending`并写`waiting_reason="workspace_write_conflict"`。默认Task工作区为`tasks/<task_id>`；只有能提供独立worktree时才允许真正并行写，文件白名单不替代隔离。
5. 释放条件：worker/reviewer session只有在适配器/停止门**确认停止**后才归还全局名额；`pausing`/`cancelling`未确认时保留名额并显示Stop unconfirmed，其他Task/成员不受影响。
6. 崩溃/重启：容量名额是进程内准入，不持久化；重启后先跑既有RecoveryScanner，所有未知副作用的非终止Run进入`recovery_required`/释放stale claim，不自动重放、不重复占名额。单进程假设；多进程需另立契约。
7. 单Task停止只取消其Run/session；其他Task的Run、成员、workspace、事件游标和产物不得被释放或改写。

**派生展示规则（无平行状态；R2 authoritative stop mapping）**：

- `worker_sessions_stopped = (run.session_refs为空) OR (run.cleanup.status=="done") OR (phase ∈ {awaiting_acceptance,completed} 且验收是由既有停止门打开的)`。`awaiting_acceptance`只有在`StopReport.confirmed=true`（所有worker session/代理停止、成员已释放、Task槽已释放、reviewer_cleanup若有则confirmed）后才可能被写入。
- `reviewer_sessions_stopped = run.reviewer_cleanup缺失 OR run.reviewer_cleanup.confirmed==true`。缺失表示没有真实reviewer session；存在但未confirmed不得释放。
- `all_current_members_terminal = run.team_refs的每个Member状态均为released|failed`（无成员=true）；`slot_free = queue.state=="not_queued"`。
- `Released = worker_sessions_stopped AND reviewer_sessions_stopped AND all_current_members_terminal AND slot_free`。
- `History = Released AND phase ∈ {awaiting_acceptance,completed,failed,cancelled}`；`Active` otherwise。`paused`可显示Released badge但仍是Active。`recovery_required`**永不**仅凭`cleanup=done`或终止phase显示Released（该路径的cleanup是停车/释放槽，不是所有session的权威停止证明）。
- `failed`/`cancelled`仅是终态：`run.cleanup.status!="done"`且存在`session_refs`时显示“Failed/Cancelled · Cleanup unconfirmed”，不得进入History Released；`pausing`/`cancelling`、成员非终态或队列仍占用时显示Releasing/Stop unconfirmed。
- `run.cleanup.status=="done"`只在控制停止确认或等价停止门事实后写入；不得由UI/前端推断或由普通状态写入伪造。UI只消费上述持久字段，不把`member.state`单独当作释放证明。

### 19.6 角色库来源、许可与能力适配（LG-120；隔离完整候选已实现，待LG-123）

- **固定来源**：`https://github.com/msitarzewski/agency-agents`，已核实pin `652b2692f8d8ec2b1f1a38e559073e287dfdc469`，MIT，`Copyright (c) 2025 AgentLand Contributors`。完整角色库随产品分发，不运行远程安装脚本、不在运行时克隆；每个文件记录upstream path、git blob、SHA-256与许可证，manifest + MIT notice随包/发布归档。
- Agent资源计划加性可选元数据：`role_category`、`capabilities`（受控能力词表）、`agency_source:{commit,path,blob_sha,sha256,license}`、`seed:{version,content_hash}`、`recruitable`。未知字段仍保留；角色正文仍只是指令，不授予工具/MCP/联网/预算/执行权限。
- 能力词表最小集：`research|design|implementation|verification|writing|review`。`load_role_catalog`优先显式catalog；否则由已启用且有`capabilities`的agent构建；无映射的角色仍可浏览但`recruitable=false`并给出`unsupported: no scheduler capability mapping`，不得静默删除。LG-121规划器只能发出catalog存在的capability；缺角色/连接时诚实失败。
- 工具适配按能力给最小集合（当前可用文件工具`view-file`/`create-file`/`edit-file`）：verification/review只读；design/implementation/writing可写；research无web工具时标不可执行。所有角色默认`connection_ref:null`，使用当前默认worker连接；实际可执行性仍以编译与连接解析为准。
- 升级幂等：只补齐缺失模板，不覆盖用户编辑/停用/既有成员；仅当当前正文仍等于上次seed哈希时才更新内置内容，否则保留并标`update_available`。模板变更只影响后续招募。

### 19.7 兼容、迁移与实现门

- **兼容性**：全部为加性只读端点/可选请求响应/可选实体字段；旧客户端不使用即行为不变。`attachment_id`与Team groups只在新能力`private_attachments`/`team_groups`声明时启用；`embedding_settings`同理。`GET /api/v1/health`在1.18.0隔离完整候选中加性声明`capabilities.team_groups`/`private_attachments`/`embedding_settings`/`capacity_v2`（boolean，缺省=false），且只在真实挂载/装配后为true；前端最低兼容仍为`>=1.13,<2`；新功能缺少能力时禁用并说明，不能把404当可用。
- **迁移**：不重写旧Task/Run/Member/Subtask/Connection/SETTINGS文件；缺省`waiting_reason=null`；没有`embedding`块时走环境回退；没有托管角色时由LG-120幂等补齐。私有附件目录为新增受控根，不迁移旧Files/Sources。
- **实现owner/门**：LG-117 → settings/embedding；LG-119 → attachments/Personal；LG-120 → runtime/roles；LG-121 → team groups/capacity；共享`api/app.py`、`api/bootstrap.py`、`coordinator/**`、`frontend` Chat/Team由单一集成owner串行接线。LG-123未通过前本节不得改为已实现。



## 20. 资料摄取 v2 与自动索引（1.19.0；LG-140 契约冻结，LG-156 最终候选，第二轮独立 QA 通过）

> **状态与门**：本节只冻结公开加性契约、兼容边界和实施归属，**冻结时**不代表已实现或运行支持。冻结时源码 `CONTRACT_VERSION` 仍为 `1.18.0`；LG-141～LG-143 实现、LG-144 串行集成后，才可把常量与 `GET /api/v1/health` 的三个新能力改为真实装配结果，并由 LG-145 独立版本/浏览器 QA 验收。未通过前不得在 UI、README 或交付记录宣称“上传后自动索引/自动媒体向量”已交付。Task/Run/Member/Subtask 的 `state`/`phase`/`acceptance`、迁移方向、默认单用户/Team 身份和权限均不改变。
>
> **LG-144 集成实现说明（2026-10-18，worktree 候选，非版本 PASS）**：LG-141/142/143 已按冻结字段串行集成到隔离候选；`CONTRACT_VERSION` 升为 `1.19.0`，真实 `create_app` lifespan 启动单一 `IntakeWorker`，两个消息路由调用 `SourceService.resolve_message_source_refs` 持久化服务端快照，`POST /vector/rebuild` 已按受保护/管理员写入分类，`/health` 三个新能力只在真实装配后为 true。LG147 原生修复 `4476ebb` 已串行集成：逐 embedding 输入取消/截止检查、嵌入超时 `recovery_required`、回执真实 `job_id` 关联均已落地。候选仍需 LG-145 独立版本 QA；公开 8123 服务、部署、Task 状态和版本 PASS 均未改变。

### 20.1 范围与不变量

- Chat 仍是常规资料接入入口；Files 负责预览、来源追溯、校订、重处理、下载；不新增主导航或第二常规入口。
- 一次 Chat 发送最多绑定一组已接收资料；后端保存原件、`source` frontmatter 与可恢复 `intake_job`，再独立运行文字、词法、语义分支。**不创建交付 Task/Run/团队、不占交付执行槽、不扩大工具权限**。
- 原件、`SOURCE.md` 与人工正式版是事实源；词法/向量/回执是投影或可重建缓存。任何失败都不得伪造正文或把错误说明写成知识正文。
- 分支独立：文字失败不抹掉已成功的语义索引；语义关闭/失败也不阻止词法检索与原件查看。
- 既有 `selected_sources` 的显式选材、12000 字符上限、跨 Task/撤销/过期拒绝和 worker 派发前重校验保持不变。新的 `source_refs` 只表示“该消息关联了哪些已接收资料”，**不授予模型上下文、不自动选材、不扩大任何授权**。
- Team Personal 的私有附件仍是 owner-only 隔离路径，不进入共享 `source`/词法/向量/搜索；ASR 仍完全不可用。

### 20.2 能力门（`GET /api/v1/health`）

`1.19.0` 加性声明三个可选 boolean；缺省或旧后端一律按 `false` 处理，不能以 `404` 猜测可用：

| 能力 | 为 `true` 的必要条件 | 语义 |
|---|---|---|
| `material_intake_v2` | `intake_mode=deferred`、持久摄取 worker、receipt v2 分支、全局/Task 消息 `source_refs` 均真实装配 | 新 Chat/Files 摄取体验可用；旧后端继续使用 1.18 流程 |
| `semantic_search` | `/vector/status`、`/vector/search`、显式 `/vector/rebuild` 与 embedding 设置已装配 | Semantic 入口可显示；**不等于 embedding 已配置**，实际可用性仍读 `/vector/status.enabled` |
| `media_direct_embedding` | 向量服务具备 `image/*`、`audio/*` 原始媒体直接输入路径 | 仅表示产品代码路径存在；单个来源真实结果仍以回执 `semantic.kinds`/失败为准 |

前端最低核心兼容仍为稳定契约 `>=1.13,<2`；新的资料摄取 UI 另要求 `>=1.19` 且 `material_intake_v2===true`，Semantic 切换另要求 `semantic_search===true`，媒体直接索引徽标另要求 `media_direct_embedding===true` 且该来源回执确实报告 `image`/`audio` kind。任一能力缺失时禁用对应入口并说明，回退到既有上传/词法搜索；不得把 404、空结果或构建成功当作可用。

### 20.3 Chat 发送生命周期（发送前不摄取、不索引）

1. 文件选择、拖拽、粘贴只形成**本地草稿**：显示文件名、类型、大小、缩略图/音频标识与移除；**不得调用 `POST /sources`、OCR、词法或 embedding**。移除/切换 Task/频道只清理本地草稿。
2. 点击发送时冻结当前身份、频道、真实 `task_ref` 和共享作用域；对每个草稿文件以稳定 `request_id` 调用 `POST /sources`，请求体加性 `intake_mode:"deferred"`。服务端只在原件、`source`、`intake_job` 持久化后返回，**不在响应前**运行 OCR/词法/语义。
3. 所有草稿摄取接受后，再提交现有消息端点（`POST /tasks/{task_id}/messages` 或 `POST /conversations/global/messages`），加性携带 `source_refs`。任一文件摄取被拒时整次发送不提交，草稿与失败原因保留；用户移除失败文件后可重试。消息提交失败时保留草稿与已接收资料，重试沿用同一 `source_refs`，不得重复建 source。
4. 消息提交成功后清空草稿；权威回执从 `GET /sources/{id}/receipt` 读取，刷新/重连按消息中的 `source_refs` 恢复。页面关闭不取消已接收的持久摄取。
5. 团队 Personal 不调用本流程：`source_refs` 在 Personal 为 `503 capability_unavailable`（`details.hint="switch_to_team"`），不写共享日志/事件、不建 source；私有附件继续走 §19.3。

请求侧字段（Task 消息与全局/Team 消息共用）：

```json
{
  "source_refs": [{ "source_id": "source_01J..." }]
}
```

- 最多 **10** 项，去重；请求只接收 `source_id`。未知/非法 id ⇒ `reference_invalid`；已撤销 ⇒ `not_found` 404 且 `details.revoked=true`；跨作用域 ⇒ `reference_invalid`；超过 10 项或重复 ⇒ `validation_failed`。
- 作用域规则：全局/Team 消息只接受全局来源（`scope.task_ref/project_ref/inbox_ref` 均为 `null`）；Task 消息接受 `scope.task_ref` 等于该 Task 或全局来源。不得把其他 Task 来源挂到当前 Task。
- 服务端校验后把消息中的 `source_refs` 规范化为只读快照；客户端提交的 version/hash/scope 不作为授权：

```json
"source_refs": [
  {
    "source_id": "source_01J...",
    "source_version": 1,
    "content_hash": "sha256-hex",
    "scope": { "task_ref": null, "project_ref": null, "inbox_ref": null }
  }
]
```

- `source_refs` 与 `selected_sources` 完全独立：前者只驱动回执/溯源，后者仍是用户显式选材并走 §6.6.1 的预算、隔离与派发前校验。旧客户端省略 `source_refs` 时消息与 1.18 完全一致。

### 20.4 `POST /sources` 加性请求与响应

请求新增可选字段：

| 字段 | 取值 | 默认 | 语义 |
|---|---|---|---|
| `intake_mode` | `sync` \| `deferred` | `sync` | `sync` 保持 1.18 行为（原生文本可同步提取；OCR 仍需显式 `reprocess`）；`deferred` 只在持久化原件/实体/作业后返回，由服务端 worker 继续 |

`deferred` 响应沿用既有 `source`/`job`/`deduplicated`/`created`/`receipts`，加性顶层 `intake_mode:"deferred"`；不新增路径、不改变 `sync` 响应。旧后端不认识该字段时返回 `422 validation_failed`，新前端必须先经 `material_intake_v2` 能力门。

### 20.5 `intake_job` 加性字段与预算

`intake_job` frontmatter 加性可选字段（旧作业缺省按 `sync`/`null` 读取）：

```yaml
intake_mode: deferred          # sync | deferred；旧作业缺省 sync
queued_at: "2026-10-18T00:00:00Z"
started_at: null
finished_at: null
deadline_at: null
waiting_reason: null           # null | worker_limit | cancelling
budget:
  max_model_calls: 102         # 100 OCR 页 + 2 个 embedding 输入的上界
  timeout_seconds: 900
  max_retries: 1               # 初始 attempt=1；最多再手工重试 1 次
  max_original_bytes: 10000000
  max_native_text_bytes: 2000000
  max_ocr_pages: 100
  max_tokens_per_page: 2000
  max_embedding_calls: 2
  max_media_embedding_bytes: 10000000
```

- `GET /intake/jobs/{job_id}` 加性返回上述字段；`attempt` 从 1 开始，重试后为 2，超过 `1+max_retries` 的请求返回 `budget_exhausted`。
- `max_model_calls` 是 OCR 页调用与 embedding 输入调用的总上界；原生文本不调用 OCR。它不替代单次 embedding 的 `timeout_seconds`/冷启动超时，也不把未知费用当 0。
- 既有 `budget.max_model_calls`/`timeout_seconds`/`max_retries` 字段保留；旧作业不补写新键，读取时按上述默认解释，不迁移旧文件。

### 20.6 独立回执（receipt v2）

`GET /api/v1/sources/{source_id}/receipt` 保留 `source_id`/`revision`/`status`/`source_version`/`items`/`latest`，加性返回 `receipt_version:2`、顶层 `partial`，并在每个条目中新增可空 `job_id`（同步/延迟接收及 worker 回执保存实际产生该条目的作业 ID，读取时核对作业属于该 source/content hash；旧条目或无法核实的关联为 `null`，不得猜测；`latest` 同样返回）及三个分支对象：

```json
{
  "source_id": "source_01J...",
  "revision": 4,
  "status": "extracted",
  "source_version": 1,
  "receipt_version": 2,
  "partial": true,
  "items": [
    {
      "source_id": "source_01J...",
      "filename": "meeting.mp3",
      "status": "extracted",
      "stage": "done",
      "detail": null,
      "searchable": false,
      "original_path": "original/meeting.mp3",
      "formal_path": null,
      "content_hash": "sha256-hex",
      "source_version": 1,
      "at": "2026-10-18T00:00:00Z",
      "error_code": "capability_unavailable",
      "text": {
        "status": "unavailable",
        "reason": "asr_unavailable",
        "error_code": "capability_unavailable"
      },
      "keyword": {
        "status": "no_text",
        "reason": "no_trusted_body",
        "error_code": null
      },
      "semantic": {
        "status": "searchable",
        "reason": null,
        "error_code": null,
        "model": "embedding-model-id",
        "kinds": ["audio"],
        "failed_kinds": []
      }
    }
  ],
  "latest": { "source_id": "source_01J...", "text": {}, "keyword": {}, "semantic": {} }
}
```

分支状态精确取值：

| 分支 | 取值 | 含义 |
|---|---|---|
| `text` | `pending` / `extracting` / `ready` / `unavailable` / `failed` | 未开始；提取中；存在可信正文；该媒体无文字路径或 ASR 不可用；已尝试但失败/超限/非 UTF-8 |
| `keyword` | `pending` / `indexing` / `searchable` / `no_text` / `failed` | 未开始；写入词法缓存；可词法检索；无可信正文未索引；索引损坏/写入失败 |
| `semantic` | `pending` / `indexing` / `searchable` / `disabled` / `unsupported` / `failed` | 未开始；写入向量缓存；至少一个 kind 可语义检索；embedding 未启用/未配置；无 text/image/audio 可嵌入输入；已尝试但失败、超时、模型不兼容或缓存损坏 |

- `text.status=ready` 可附 `reason:"partial_pages"`；仍是可信正文，但 `partial` 为真时 UI 必须显示部分成功。
- `semantic.status=searchable` 可同时有非空 `failed_kinds`（例如文本向量成功、媒体向量失败）；`kinds` 只列真实写入的 `text`/`image`/`audio`。全部输入失败才是 `failed`；不得把失败 kind 写成成功。
- `semantic.status=unsupported` 只用于“没有可嵌入输入”或能力路径缺失，不用于供应商拒绝/超时；后者必须 `failed`，绝不伪造 `unsupported` 作为通过。
- 旧字段映射：`searchable` 保持“词法可检索”旧含义；`error_code` 按 `text→keyword→semantic` 顺序取第一个非空错误；`status`/`stage` 仍是 source/job 展示状态。旧客户端忽略分支对象时行为不变。
- 顶层 `partial=true` 当且仅当至少一个分支成功（`text=ready` 或 `keyword=semantic=searchable`）且至少一个已尝试分支未成功（`unavailable`/`failed`/`unsupported`）。`pending`/`indexing` 不构成 partial。
- 回执是真实文件/索引状态的投影，不另建回执状态库；每次读取都重新核对 source/index，不返回悬空成功。

### 20.7 持久摄取与分支编排

`deferred` 作业由单一进程内的有界 `IntakeWorker` 驱动，复用既有 `IntakeService`、`ProcessingEngine`、`LexicalSearchService`、`VectorSearchService`，不新增通用 job 框架、数据库或外部队列：

1. worker 按 `created_at`/ID 的 FIFO 取 `queued` 作业，在文件锁/修订校验下写 `running`；已被其他 worker 领取则不重复执行。
2. 文字分支：原生 UTF-8 文本直接解码；图片/PDF 走既有 OCR；音频/Office/未知二进制不调用 OCR/ASR，`text.unavailable`。OCR 失败/部分成功按既有 `ProcessingEngine` 结果写入，不伪造正文。
3. 词法分支：仅对可信正式版/机器派生版建索引；无正文为 `no_text`；索引失败为 `failed`，不阻断语义分支。
4. 语义分支：embedding 未启用/未配置 ⇒ `disabled`；启用时对可信文本和原始 `image/*`/`audio/*`（≤10,000,000 字节）分别尝试直接 embedding，**媒体不先转文字**。每个输入一次调用、无自动重试、有超时；成功写现有向量缓存与 `source.index.vector`，失败只标记对应 kind。
5. 模型/缓存不兼容：不得自动清空或混用旧缓存。配置模型与缓存模型不一致或缓存损坏时，语义按 `failed` 诚实报告并等待显式 `POST /vector/rebuild`；缓存文件缺失时允许为当前来源初始化一个**仅含该来源**的缓存，但不得把它当作全库重建，也不得删除其他来源数据；旧来源需显式重建。**不得在摄取、搜索或保存设置时隐式全库重建**。
6. 每个阶段结束更新回执与 `intake.stage_changed`；终态写 `succeeded`/`partial`/`failed`/`cancelled`。回执读取可随时发生，不要求页面存活。

### 20.8 媒体支持与边界（精确）

| 输入 | 存储 | 文字/词法 | 语义 | 上界/说明 |
|---|---|---|---|---|
| `text/plain`、`text/markdown`、`text/x-markdown`、`text/x-log`、`application/x-ndjson` | 原件落盘 | 原生 UTF-8，模型无关；可信正文建词法 | 若启用则文本 embedding | 原生正文 ≤ **2,000,000** 字节；超限/非 UTF-8 为 `text.failed` |
| `image/png`、`image/jpeg`、`image/webp`、`image/gif`、`image/bmp` | 原件落盘 | 既有 OCR；成功/部分成功才建词法 | 启用时原始图片直接 embedding（另加文本向量，若存在） | 原件 ≤ **10,000,000** 字节；OCR ≤ **100** 页、每页 ≤ **2000** tokens；每页一次调用、无自动重试 |
| PDF（按字节签名识别，不依赖扩展名） | 原件落盘 | 光栅化后逐页 OCR | 启用时只嵌入可信 OCR 文本，不直接嵌入 PDF 字节 | 同上；未配置 OCR 时 `text.failed`/`unavailable`，原件保留 |
| `audio/*`（任意容器/编码） | 原件落盘 | **无 ASR；所有语言 `text.unavailable`，不生成转写** | 启用时原始音频直接 embedding；无转写也可语义命中 | 原件 ≤ **10,000,000** 字节；关键词不承诺检索讲话内容；不得把 embedding 称为转写 |
| Office/未知二进制/无文字图片以外的媒体 | 原件落盘 | `text.unavailable`；`keyword.no_text` | 无 text/image/audio 输入 ⇒ `unsupported` | 不假装支持；不抓取、不执行内容 |
| 链接（`origin.kind=link`） | 仅记录，`fetched=false` | 不抓取、不成文 | 不索引 | 不因“已记录”显示为可检索 |

- 超限在接收前返回 `validation_failed`/`invalid_request`，不落半个原件；已接收后的提取超限按分支失败记录。
- 媒体向量是独立 kind，检索命中必须回源核对 source 版本/哈希/权限；不支持视频、Office 正文、音频转写或任意新供应商协议。
- 任何 OCR/ASR/embedding 的模型/服务不可用都只影响对应分支；词法、原件预览、下载与既有 `selected_sources` 仍可用。

### 20.9 配额、重试、取消与重启

以下重试/取消/重启语义适用于 `intake_mode=deferred` 作业；1.18 的 `sync` 旧作业保持既有行为，不补写新字段。

- **并发/队列**：每进程最多 **2** 个 `deferred` 作业同时运行；其余保持 `queued` 并写 `waiting_reason:"worker_limit"`。队列是持久 `intake_job` 的 FIFO 投影，不使用无界内存队列；单进程假设，多进程需另立契约。
- **自动重试**：无。OCR 每页、embedding 每输入最多一次；供应商/超时错误只记录，不自动重放。
- **手工重试**：仅 `failed`/`partial` 可 `POST /intake/jobs/{id}/actions {"action":"retry"}`；`attempt+1`，超过 `1+max_retries` ⇒ `budget_exhausted`；`running`/`recovery_required` ⇒ `illegal_transition`，不重放未知副作用；重试不覆盖人工正式版，已成功分支可复用，失败分支重建。
- **取消**：`confirmed=false` 只写 `cancel.requested=true` 并返回 `409 cancellation_unconfirmed`，不写终止。`queued` 作业在 `confirmed=true` 时可立即写 `cancelled`（尚无副作用）；`running` 作业即使 `confirmed=true` 也只记录请求并返回 `409 cancellation_unconfirmed`，worker 在 OCR 页间和每个 embedding 输入前检查，确认已停止后才写 `cancelled`。在途调用无法取消时保持未确认；终态取消幂等，不复活。
- **超时**：达到 `budget.timeout_seconds` 或 embedding 超时 ⇒ 该作业 `recovery_required`（结果未知，不自动重放），保留原件与已完成派生；不伪造成功。
- **重启**：启动先运行既有 `IntakeService.recover()`；`queued` 继续、`running` 一律 `recovery_required`，不自动重放；`request_id` 幂等保证重复提交不重复建 source；人工正式版与历史保留。
- **关闭**：优雅停止不得把运行中作业写成成功；无法证明无副作用的运行中作业按 `recovery_required` 停车，`queued` 保留待下次启动。

### 20.10 搜索、显式重建与设置

- 顶部 Search 保持既有布局、当前 Task/共享范围、Enter 查询、Escape 关闭与焦点返回；面板新增 `Keyword`（默认）/`Semantic` 切换，两类结果**分开展示**，不混合未评估分数。Semantic 不可用时明确说明并可切回 Keyword。
- `GET /search` 与 `GET /vector/search` 在 `rebuild_if_missing` 省略或 `false` 时**只读**，不得写 source/index 或调用全库 embedding。`rebuild_if_missing=true` 仅作为 1.18 旧客户端的显式兼容参数保留并标记 deprecated；它是下述 POST 之外唯一的旧版显式重建例外，必须在查询/重建前接受同等管理员/受保护写授权（单用户运行 token；Team 管理员），未授权返回 `401`/`403`，不调用 embedding、不写缓存/source；即使缓存已存在也不豁免该显式请求。新前端不得发送，改由用户显式重建。
- `POST /vector/rebuild` 是常规客户端唯一全库重建入口（旧客户端显式 GET 例外及同等授权见上条），只由显式用户动作触发；`1.19` 起要求与 Settings 相同的管理员/受保护写授权（单用户运行 token；Team 管理员），非授权返回 `401`/`403`，不得由搜索、摄取、保存设置或页面渲染调用。
- `PUT /settings/embedding` 只保存配置；**不调用 embedding、不重建缓存、不改变既有来源**。保存后仅影响后续摄取；模型/地址/维度变化使旧测试结果失效，`/vector/status` 报告 `model_mismatch_rebuild_required`，旧向量不得混用。
- `GET /vector/search` 命中加性返回 `kind ∈ {text,image,audio}` 与 `basis`/locators；每个候选仍按 source 版本/哈希/权限回源核对；`source_stale`/撤销/删除不返回悬空命中。Semantic 命中音频只代表媒体向量，不代表有转写。
- 搜索/页面渲染不隐式修复缓存；缓存缺失/损坏/模型不兼容时返回 `index_unavailable` 或重建提示，词法与原文件仍可用。

### 20.11 事件实际产生矩阵

`1.19.0` 不新增事件类型；以下 payload 为加性，消费方必须忽略未知字段/类型：

| 事件 | 产生方 | 1.19 加性 payload | 说明 |
|---|---|---|---|
| `source.received` | `IntakeService.receive` | 既有 `deduplicated` | 接收/去重；不表示已提取 |
| `source.version_changed` | `IntakeService.record_version` | 既有 `source_version` | 内容 hash 变化才产生 |
| `intake.stage_changed` | `IntakeService.set_stage` | `branch`、`branch_status`（可选） | 阶段变化；队列/worker 状态仍以 job 为准 |
| `source.attributed` | `ProcessingEngine` | `text_status` | 文字成功/部分成功 |
| `source.indexed` | 词法/向量服务 | `branch ∈ {keyword,semantic}`、`kind`（语义） | 只表示对应分支真实写入 |
| `source.invalidated` | 词法/向量服务/撤销删除 | `branch`、`reason` | 旧命中失效；`source.deleted` 仍不单独产生 |
| `intake.failed` | `IntakeService`/`ProcessingEngine` | `branch`、`reason` | 失败不造正文 |
| `intake.cancelled` | `IntakeService.cancel` | 既有 `job_ref` | 仅确认停止后产生 |
| `intake.receipt` | 无 | — | 1.19 仍不产生；回执是读取投影 |

### 20.12 Team Personal 隔离与 ASR

- Team Personal 的 `attachments` 仍只接受服务端 owner 校验后的 `{attachment_id}`；私有根 `<data>/private-attachments` 继续被 Files、`POST /sources` 路径、`/search`、`/vector/search` 拒绝，管理员也不能借共享界面读取。
- Personal 不调用共享摄取/OCR/ASR/embedding，不登记 `source`，不进入共享索引；`source_refs` 在 Personal 返回 `503 capability_unavailable` 并提示切到 Team。需要共享时由用户切换 Team 后重新提交，不做跨作用域复制。
- **ASR 在任何语言、任何团队模式下均不可用**：不存在新的转写端点、模型调用或隐式音频转文字。音频只能保留原件并（在启用且后端支持时）做直接媒体 embedding；UI 必须显示 `Transcription unavailable`，不得把语义命中写成转写成功。LG-041 质量门保持。

### 20.13 兼容、权限、迁移与实现门

- **兼容性**：全部为加性可选请求/响应/实体/事件 payload 字段与三个默认 `false` 的能力；`intake_mode` 缺省 `sync` 保持旧行为，`source_refs` 缺省不写消息，receipt v2 旧字段保留，旧客户端忽略新对象即可。无新端点/错误码/Task/Run 枚举/迁移方向；不重写旧 `source`/`intake_job`/消息/索引文件。
- **权限收紧**：`POST /vector/rebuild` 及旧客户端显式 `GET /search?rebuild_if_missing=true`、`GET /vector/search?rebuild_if_missing=true` 从 1.19 起要求管理员/受保护写；这是对可选全局模型操作的收紧，旧客户端未授权时收到 `401`/`403`，不得重试为成功。除该收紧外，不扩大任何身份、Task、资料或个人附件权限。
- **实现门**：LG-141 后端摄取/worker/回执；LG-142 Chat/Files 体验；LG-143 词法/向量/搜索/重建；LG-144 共享 `api/app.py`、`api/bootstrap.py`、`api/health.py`、`api/access.py`、`contracts/constants.py`、前端 `types.ts`/`sources.ts`/`backendCompatibility.ts`/shell/settings 串行集成；LG-145 独立真实浏览器/媒体 QA。三 feature owner 不得互相修改 owner 文件；共享类型/客户端由 LG-144 先落契约再接线。
- **规划不是运行时支持**：在 LG-145 通过前，源码、`/health`、README、UI 和交付记录都不得声称 1.19 自动索引已实现；`CONTRACT_VERSION` 只在 LG-144 真实装配完成后改为 `1.19.0`。

> **当前部署（LG168）**：2026-10-18用户明确“更新”后，8123/5173已提供1.20.0，根main1ab4d7b；73项公共部署冒烟通过，账号/数据/no-executor保留。英文ASR关闭/未配置，质量FAILED不变；认证后线上管理页面未登录验证，复用相同产品源码的独立UI证据。历史“未部署/1.18”描述为当时记录，当前以本补充及[部署交付](../probes/english-asr-20261018/lg168/DELIVERY.md)为准，无远端推送。

## 21. 共享英文音频机器转写（1.20.0；隔离候选已装配，独立质量QA失败）

> **状态与门**：本节冻结公开加性契约、兼容边界、失败语义与文件归属。LG-162 已在隔离完整候选把 160 的 ASR 服务/worker 与 161 的 Settings/Chat/Files UI 串行接入真实 `api/app.py`、health 和 settings 路由，并在真实装配后把 `CONTRACT_VERSION` 升为 **1.20.0**；公开 8123 服务仍为 **1.18.0**，未部署/推送。**LG-163首轮独立QA质量FAILED**；功能/UI/权限/持久化路径通过，LG164/LG166修复已由LG165集成、R2针对性检查通过，整体质量仍FAILED，不宣称版本验收或生产可用。
>
> **配置能力与处理可用性分开**：`GET /health.capabilities.english_asr` 只表示处理可用性（已启用、固定文件/hash 有效、可选运行时可用），默认 false；它不是配置权限。既有受保护 `GET /settings.english_asr` 视图只要 160/162 已装配 ASR 设置服务就存在，即使 `enabled=false`、模型缺失或运行时不可用，管理员仍可配置/启用；前端以视图是否存在判断表单，不因 `capabilities.english_asr=false` 锁死。旧后端缺少该视图时隐藏表单，不探测新端点、不把 404 当可用。关闭/模型缺失/运行时不可用不隐藏或删除已生成且仍获授权的机器转写、来源 provenance、下载和关键词命中；读取既有机器正文永不运行模型。
>
> **质量门如实**：LG-159 原型证明了 `16 kHz audio -> EmbeddingGemma 2 audio tower -> reader v2/CTC -> 非空英文` 的真实路径：官方 LibriSpeech fixture 归一化 WER **0.04167**。第一组授权的 CosyVoice3 服务对文档化请求返回 HTTP 500，改用本地 espeak-ng 兜底后 3 条固定合成样本平均 WER **0.24735**，关键事实不全，保留为 cohort1 **FAIL**。PM 修订 1 明确授权的 cohort2 使用同一 3 条原文、同一归一化/门、同一 EG2+Reader checkpoint，以固定的 Piper 1.8.0 + `en_US-ljspeech-high`（LJSpeech public domain）生成：单条 WER 0、0.04167、0.07407，平均 **0.03858 <= 0.20**；但 `s3-domain` 把 `scanned report` 识别为 `scan report`，关键事实 3/4（全组 12/13），因此“平均 WER<=20% **且**全部关键事实”的预注册门仍为 **FAIL**。PM 接受该词形误差为实施就绪的非阻塞已知限制，但原始 `gate_pass:false` 不能改写为 PASS。没有改句、改归一化、换音色、挑最好片段或消耗 QA reserve；全部证据与 cohort1 checkpoint 保留在 `probes/english-asr-20261018/`。LG-163 独立 QA 使用自己的 holdout/TTS（分配见同里程碑累计账本），不能用开发样本冒充 QA。

### 21.1 范围与不变量

- 仅**英文音频**、仅**共享资料**（`source`/Team 共享范围）。不新增导航、上传入口、TTS 或直接 Reader 客户端调用；复用 Chat/Files/Settings。
- ASR 是既有 intake `text` 分支的加性能力：原件先落盘，机器转写是派生正文，人工正式版仍是权威；失败不得伪造正文、不得把错误说明当知识正文。
- 默认关闭。只有管理员显式配置、本地固定模型文件校验通过且 in-process 运行时可用时，`capabilities.english_asr` 才为 true；否则旧行为不变，音频仍保留、直接媒体 embedding 仍可独立工作。
- Team Personal、私有附件、非英文/多语、口音/噪声/真人质量、自动下载/安装/训练、远端 ASR、任何 TTS 均**不在**本能力内；1.19 §20.12 的 Personal 隔离与“ASR 不可用”边界对这些路径继续有效。
- 不使用 Whisper/SenseVoice 或 pooled 768 维检索向量冒充帧级特征/转写。模型/Reader 版本、许可、hash 固定；不依赖开发机 probe 脚本或绝对路径。
- 时间戳只有在真实解码器提供且验证后才展示；当前 released reader/CTC **不提供**，故 `timestamps=null`，不伪造。

### 21.2 模型与运行时固定

本版只允许 LG-159 验证的公开固定对：

| 角色 | 工件 | revision | SHA-256 | 许可 |
|---|---|---|---|---|
| audio encoder | `google/embeddinggemma-2` | `914f7f89142e33e77833254d9c9b90c3cef7303b` | `model.safetensors` `197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79` | Apache-2.0（公开 model card，gated=false） |
| reader v2 | `mlboydaisuke/EmbeddingGemma-2-Transcribe-Reader` | `de224fd8fa4ed4519fdddd9aa4154432d46a1bd3` | `reader.pt` `d605f6fba8687497be6b5fd717ea6c51beaee5d5f69c30a64225da96ebe0d8c2` | Apache-2.0 |
| word table / vocab / config | 同一 reader 仓库/版本 | 同上 | `word_table.npy` `b2d0b13c...faa8`、`vocab.txt` `bb3b3c70...a68`、`reader_config.json` `3aede371...0ed` | Apache-2.0 |

运行时契约：16 kHz mono -> 128-bin log-mel（frame 320, hop 160）-> EmbeddingGemma 2 audio tower + `embed_audio`（25 soft tokens/s, 512 维）-> reader v2（6 层 pre-LayerNorm, 19,573,762 参数）-> 每 token 768 维单位向量 + blank logit -> greedy CTC（blank logit 高于 top-1 词则 blank；合并重复、丢弃 blank）-> 小写英文词，无标点/语言模型。`/v1/embeddings` 的 pooled 向量与通用 `/v1/audio/transcriptions` 不是本路径。

部署只允许**一个可选 in-process CPU 运行时**（160 实现为可选依赖/惰性装配）：默认关闭；管理员显式配置本地目录；启动/健康只做文件与 hash 校验，不自动下载、安装、训练或加载多个编码器；并发固定 1；超时 180 s；单条音频上限 30 s / 10,000,000 字节。内存不足/模型加载失败必须诚实降级，不得 OOM 整个 intake 进程。

### 21.3 能力、设置与配置

`GET /api/v1/health` 加性可选 boolean：

```json
{ "capabilities": { "english_asr": false } }
```

缺省/旧后端按 false 处理。true 的必要条件：设置 enabled、固定模型文件存在且 hash 匹配、in-process 运行时 import 成功。它不保证每个音频成功；单条真值以 receipt 为准。health 不含路径、正文或音频。

`GET /api/v1/settings`（既有管理员/受保护 settings 读）加性 `english_asr` 视图：

```json
{
  "english_asr": {
    "revision": 3,
    "content_hash": "sha256-hex",
    "enabled": false,
    "runtime": "inprocess",
    "configured": false,
    "available": false,
    "reason": null,
    "language": "en",
    "timestamps_supported": false,
    "models": {
      "encoder": { "id": "google/embeddinggemma-2", "revision": "914f...", "sha256": "197a...", "license": "apache-2.0" },
      "reader": { "id": "mlboydaisuke/EmbeddingGemma-2-Transcribe-Reader", "revision": "de224...", "sha256": "d605...", "license": "apache-2.0" }
    },
    "limits": { "max_audio_seconds": 30, "max_audio_bytes": 10000000, "timeout_seconds": 180, "max_concurrency": 1 }
  }
}
```

`reason ∈ {null,disabled,model_missing,model_hash_mismatch,runtime_unavailable,invalid_config,resource_unavailable}`。视图不返回 `model_dir`/`reader_dir`、凭证或正文。

`english_asr.revision` 与 `english_asr.content_hash` 是**该能力实际读取的规范设置文档**的版本/哈希：若 `english_asr` 块保存在独立规范文件中，就取该文件自己的 revision/content_hash；若保存在全局 `SETTINGS.md` 中，则取该全局文件的 revision/content_hash。首次创建前为 `revision:0`、`content_hash:""`。前端从常规 `GET /settings` 的 `english_asr.revision` 读取下一次写入的 `expected_revision`，**不得**用顶层全局 settings 的 `revision` 猜测。保存成功后新配置对下一次语义/文本操作直接生效，不需要额外 GET/探活 primer。保存 response 的顶层 `revision`/`content_hash` 与 `english_asr` 内的值一致，表示同一次规范文档写入。

`PUT /api/v1/settings/english_asr`（与 settings 相同的管理员/受保护写、Host/Origin 规则）：

```json
{
  "expected_revision": 3,
  "enabled": true,
  "runtime": "inprocess",
  "model_dir": "<absolute local dir>",
  "reader_dir": "<absolute local dir>",
  "device": "cpu",
  "threads": 4,
  "timeout_seconds": 180,
  "max_audio_seconds": 30,
  "max_audio_bytes": 10000000
}
```

- `expected_revision` 必填整数；首次创建必须为 `0`，已有配置必须等于当前 `english_asr.revision`；冲突 `409 revision_conflict`。`runtime` 仅 `inprocess`、`device` 仅 `cpu`；`threads` 1-8；超界/未知值 `422 validation_failed`。
- `model_dir`/`reader_dir` 是**只写**字段，GET 视图永不返回。**省略**（字段不存在）表示保留当前已存路径，供已配置后的 enable/disable 或普通更新使用；**不提供**通过空串/`null` 清除路径的语义。显式 `null`、`""` 或纯空白 -> `422 validation_failed`，绝不静默清空。首次 enable（尚无已存路径）必须同时提供两个有效绝对本地目录。
- 目录必须为绝对本地目录；服务端核对固定文件名与 SHA-256，拒绝 URL/压缩包/下载/逃逸符号链接。**只要本次请求提供了某路径**，该路径就必须通过存在性/hash 校验，否则 `422 validation_failed`，不保存无效配置。省略路径时保留已存值；若 `enabled=true`，保留的路径也必须重新校验通过；若 `enabled=false`，允许在模型文件缺失/hash 不匹配时保存禁用配置（用于安全停用），但 `available` 必须为 false 且 `reason` 如实为 `model_missing`/`model_hash_mismatch`，绝不伪造可用或触发下载。
- 保存只校验文件/hash 与持久化设置，**不加载模型、不推理、不改资料、不自动重处理**。模型配置变化不重写旧机器转写；旧转写保留其 provenance，新作业用新配置。无 delete/install/train/test-inference 端点；Settings 不出现下载/安装/训练/测试推理按钮。
- 成功保存返回：

```json
{
  "revision": 4,
  "content_hash": "sha256-hex",
  "english_asr": { "revision": 4, "content_hash": "sha256-hex", "enabled": true, "runtime": "inprocess", "configured": true, "available": false, "reason": "model_missing", "language": "en", "timestamps_supported": false, "models": { }, "limits": { } }
}
```

顶层 `revision`/`content_hash` 是本次写入后的规范文档版本；`english_asr` 内是同一值的完整视图（字段与 GET 相同，实际内容以 GET 视图的完整字段为准）。前端下一次 PUT 只使用 `english_asr.revision`。
- 保存成功后，新配置对**下一次**语义/文本操作生效，无需先 GET 探活或调用额外接口。已经开始的操作持有不可变的配置/模型快照，不因中途保存而换模型；完成时按实际使用的快照记录 provenance。配置变化不追溯改写旧转写，也不自动重建索引。
- 无效路径/hash 只能返回校验失败或（禁用时）`available=false` + 如实 reason；**永远**不把 `available` 置 true，不自动下载/安装，不把 404 或校验失败当可用。

### 21.4 `source`、receipt 与 machine content

`source` 加性可选字段（投影，不是第二状态库）：

```yaml
language: "en"          # 仅 text.status=ready 时为 "en"，否则 null
text_status: pending    # pending|extracting|ready|unavailable|failed，与 receipt.text.status 同枚举
```

ready 时 `derivatives` 加性条目：

```json
{ "kind": "transcript", "path": "<internal relative path>", "source_version": 1,
  "content_hash": "sha256-hex", "model_version": "eg2-reader-v2+embeddinggemma-2@914f7f89" }
```

非音频保持原有 text/OCR 行为；音频原件始终保留；转写是机器派生，不是 formal。

`GET /api/v1/sources/{source_id}/receipt` 的 `text` 分支加性扩展：

```json
{
  "status": "ready", "reason": null, "error_code": null,
  "language": "en",
  "machine": {
    "engine": "eg2-reader-v2",
    "encoder": { "id": "google/embeddinggemma-2", "revision": "914f...", "sha256": "197a...", "license": "apache-2.0" },
    "reader": { "id": "mlboydaisuke/EmbeddingGemma-2-Transcribe-Reader", "revision": "de224...", "sha256": "d605...", "license": "apache-2.0" },
    "runtime": "inprocess",
    "model_version": "eg2-reader-v2+embeddinggemma-2@914f7f89",
    "content_variant": "machine",
    "generated_at": "2026-10-18T00:00:00Z"
  },
  "timestamps": null
}
```

- `machine` 仅在 `text.status=ready` 时非 null；它只是 provenance，正文通过 content 读取。`language` 仅在 ready 时为 `"en"`。
- `timestamps` 1.20 固定 `null`；未来只有真实解码器验证后才可为 `[{start_seconds,end_seconds,text}]`，不得伪造。
- `reason` 加性取值：`asr_disabled`、`asr_unavailable`、`asr_failed`、`asr_timeout`、`asr_unsupported_language`、`audio_too_long`、`audio_decode_failed`、`model_incompatible`、`resource_exhausted`、`asr_stop_unconfirmed`、`cancelled`。禁用/不可用/不支持/开始前取消 -> `text.unavailable`；**已确认停止**的失败/超时/内存不足 -> `text.failed`；停止未确认 -> 保持非终态 `text.status=extracting` + `reason=asr_stop_unconfirmed`，由整个 job 进入 `recovery_required`，不得写成 `text.failed` 终态。复用既有 `error_code`，不新增 HTTP 错误码。
- 转写作为 `source` 既有 machine 派生正文持久化（`derivative/machine.v{source_version}.md`，加性 `derivatives` 条目 `kind:"transcript"` 记录 provenance），由既有 `GET /sources/{id}/content?kind=machine` 的 `content` 字段返回（`media_type` 保持既有 `text/markdown; charset=utf-8`，纯文本合法）；`download?kind=machine` 返回同一正文。非 ready 返回既有 `404 not_found` + `details.reason`，不得空 200；撤销/删除/越权沿用既有 fail-closed。正文不重复塞进 receipt/health。
- 事件 payload 仅加性：`source.attributed` 可带 `language`/`model_version`；`intake.stage_changed` 可带 `branch:"text"`/`branch_status`；`intake.failed` 可带 `branch:"text"`/`reason`。不新增事件类型，未知字段忽略。

### 21.5 生命周期、上限、取消与重启

- ASR 属于既有 intake `text` 分支：持久化原件 -> `text.status=extracting` -> 运行 -> 持久化 `transcript` 派生 -> `ready` -> 词法/可选文本 embedding 可使用；直接音频 embedding 仍独立。ASR 失败不阻断原件、词法、直接音频向量；失败说明不入索引。
- 单进程单模型实例、惰性加载、并发 1；单条 <=30 s、<=10,000,000 字节、超时 180 s；无自动重试、无 warmup、无并发加载 full/lowmem 两套编码器。超长/超大在模型调用前失败（`audio_too_long`/`validation_failed`）。
- `intake_job.budget` 加性可选 `max_asr_calls`：1.20 新作业默认 `1`，ASR 关闭/旧作业缺省 `0`；`GET /intake/jobs/{id}` 返回。它只计 ASR 尝试（失败也计），不改变既有 `max_model_calls`（OCR 页 + embedding 输入）的口径。
- 每个 job 一次尝试；手工 `reprocess` 走既有 action/attempt 语义，是新的一次有界尝试，不是自动重放。失败尝试保留并计数。
- 超时/取消/整个 job 截止都必须先判断**运行时是否已确认停止**；仅收到 deadline/超时异常本身**不构成**停止确认，尤其不能证明进程内的 CPU 模型调用已经结束。
  - **已确认停止**（调用/线程/进程真实返回或安全终止，资源释放，且无隐藏写入）：超时 -> `text.failed`/`asr_timeout`；取消 -> `cancelled`；丢弃迟到输出，不持久化部分正文；可按 1.19 语义继续或终止该 job。
  - **未确认停止**（真实 CPU 模型可能仍在运行）：整个 job 进入 `recovery_required`，取消保持 `unconfirmed`（沿用 1.19 `409 cancellation_unconfirmed`），receipt 保持 `text.status=extracting` + `reason=asr_stop_unconfirmed`，不写终态、不写 `text.failed`/`cancelled`、不重试、不自动或手工重放，直到有真实停止确认。迟到输出一律丢弃，不得隐藏写入派生/索引/formal。
- 不得在真实 CPU 模型仍在运行时标记 terminal、重试、重新派发或声称已取消。手工 `reprocess` 也必须等待停止确认；确认后才是新的有界 attempt 并计数。
- 开始前取消：不调用模型，`text.unavailable`/`cancelled`（或 job cancelled），不产生部分转写。
- 重启：running -> `recovery_required`（1.19 语义），不自动重放；queued 继续；手工 reprocess 可重新开始并计数。
- 幂等：同一 source version/content hash + 同一模型配置 -> 同一转写；派生按 source version + model_version 键控。配置变化产生新 model_version，不覆盖 formal、不静默替换旧 provenance。
- 模型加载/推理 `MemoryError`/运行时错误 -> 该分支 `text.failed`/`asr_unavailable`/`resource_exhausted`，worker 存活；不得崩溃整个 intake 或伪造正文。

### 21.6 搜索、Chat、隐私与兼容

- ready 的转写作为机器派生正文，可进入既有词法索引与可选文本 embedding；未 ready 时 `keyword=no_text`，直接音频向量仍可为 `kind:"audio"`，绝不把语义命中写成转写成功。`selected_sources` 的 formal 优先/机器回退、12000 字符、不可信数据包裹、派发前重校验不变；选材/Chat 派发不触发 ASR。
- 本地 in-process、无网络 ASR、无凭证；模型由管理员预置，不自动下载/安装。音频/转写在 source 同 scope/权限下落盘；health/日志/错误体不含正文；只记录 hash/model/latency/status。机器转写必须明确标注 provenance，不呈现为人工正式版。
- Team Personal/私有附件不进入共享 ASR；Personal UI 不提供该能力。1.20 对共享英文音频的加性能力不改变 Personal 的不可用边界。
- 1.20.0 为加性 MINOR：旧客户端忽略新字段；旧后端缺少 `GET /settings.english_asr` 视图时前端隐藏配置表单并说明，不探测新 settings、不把 404 当可用。**不得因为 `capabilities.english_asr=false` 而禁用已存在视图的配置表单**：该能力仅表示处理可用性。不新增导航、Task/Run/Member/Subtask 或 `source.status` 枚举、迁移方向或 HTTP 错误码。
- **实现文件 owner（互斥）**：160 拥有 `backend/**`（新增 ASR 模块、settings/source/receipt/text 分支、backend tests、`pyproject.toml`/`uv.lock` 的仅可选 `english-asr` 依赖组），但**排除** 162 的共享文件与集成测试；161 拥有全部 `frontend/**`；162 只拥有 `backend/lightgravity/api/app.py`、`api/bootstrap.py`、`api/health.py`、`contracts/constants.py`、`docs/08` 版本/状态、README/PROJECT 版本说明、`tests/integration/**`/e2e 与串行装配；163 只用独立测试/证据，不改产品代码。160/161 不得互相修改 owner 文件，也不得改 162 的共享文件。
- **160 必须提供的后端装配缝**（名称可等价，但语义必须稳定且不要求 162 改实现）：
  - `build_english_asr_service(settings_repository, *, env=None, runtime_factory=None)`：返回带 `view(settings)`、`update(expected_revision, payload, actor)`、`capability()`、`snapshot()`、`transcribe(...)` 的服务对象；所有路径/hash/配置校验在该服务内完成。
  - `build_english_asr_router(service, *, require_admin, safe_origin)`：返回只含新增 settings/能力路由的 router；由 162 在 `api/app.py` include，160 不改 `api/app.py`。
  - `english_asr_capability(service)`：纯只读能力/原因计算；162 在 `api/health.py` 调用，160 不改 health 文件。
  - 配置快照与真实停止确认由 service 暴露给 162 的 bootstrap/worker 装配；共享 `api/bootstrap.py` 只做注入，不复制校验逻辑。
- `CONTRACT_VERSION` 已由 LG-162 在真实装配并通过局部整合检查后改为 `1.20.0`；公开服务仍 1.18.0，LG-163 独立 QA 未完成前不得宣称版本交付。
- **质量门如实**：cohort1 的 3 条 espeak 样本平均 WER **24.735%**，FAIL；cohort2 的 3 条固定 Piper/LJSpeech 高音质样本 WER 0、0.04167、0.07407，平均 **3.858% <= 20%**，但 `s3-domain` 的 `scanned report` 被识别成 `scan report`，关键事实 12/13，按预注册的“平均 WER<=20% 且全部关键事实”仍 **FAIL**。PM 接受该词形误差为实施就绪的非阻塞已知限制，但不改写原始 `gate_pass:false`。没有改句/归一化/音色/挑片段，cohort2 也**不是 PASS**，不得只引用 3.858% 宣称通过。官方 human fixture 4.17% 只证明模型路径；cohort2 的 reference 是 TTS 输入文本（nominal truth），不是独立人工/ASR 转写，TTS 可能读错；163 的 holdout/TTS 与 **2 TTS + 8 Reader + 6 embedding** QA reserve（PM 修订 1）的实际使用见累计账本，不能拿开发样本冒充 QA。
- **派工门**：LG-160/161 已按 PM 实施就绪决定完成并串行装配；LG-163 用新 holdout 独立复验，当前独立质量门为FAILED，最终修复复验已完成且整体质量仍FAILED。

> **2026-10-18 独立结果补充**：LG163新留出样本WER8%/21.739%，关键实体8/11，平均14.869%不代表通过，原质量门FAILED。LG167上游完整float32 H2实际运行与候选逐字相同、WER21.739%，H1原版因加载分配保护未验证；固定整词词表缺eastside。直接复用不会解决已测H2的质量失败，不能声称所有音频等价。language=en表示当前Reader输出语言，不提供输入语言识别。累计Reader30/36、TTS9/10、embedding7/20、OCR0，所有失败计入且0open；后续文案/PCM32修复复验计划0模型。证据：[首轮QA](../probes/english-asr-20261018/lg163/REPORT.md)、[原版对照](../probes/english-asr-20261018/lg167-reference-qa/DELIVERY.md)。

2026-10-18最终复验补充：候选2fbff57/tree5be57d3，LG163-R2独立46/46浏览器检查、PCM32修复、31秒前模型拒绝边界通过；0新推理、同账本77条hash98a5b466不变。整体质量FAILED，历史未跑startup/lifespan选择仍INCOMPLETE。自有QA进程/端口已关闭，未部署，见[最终报告](../probes/english-asr-20261018/lg163-r2/REPORT.md)。

## 22. 不限制模型与 API 用量（LG-230/LG-229，行为变化；分支实现，待合入并统一定版本号）

用户 2026-10-18 决定产品不对模型和 API 用量设限。分支 `dev/lg229-google-demo-provider-20261018` 实现以下公开行为变化，合入时与资料摄取/ASR 团队的升版串行，统一分配契约版本号：

- **主机**：取消 OpenAI 兼容主机白名单。任意带主机名的 `openai-compat` 连接 `capabilities.executable=true`，可设为默认，代理向其转发该连接自己的凭证；`vendor_verified` 仍只对端到端核实过的 `api.deepseek.com` 为 `true`（只是事实展示）。§18 中“仅 DeepSeek 可执行/设默认”的约束作废。
- **调用次数**：执行器每 session 代理默认上限（原 8）、对话与独立复核的单次调用上限（原 1）、代理默认上限（原 64）均改为不设上限；仅当请求显式给出 `budget.max_model_calls` 或运维显式配置时才生效。协作请求不再按 worker/返修预算推算上限，只认显式 `max_collab_requests`。
- **资料摄取**：§20.5 `intake_job.budget` 的 `max_model_calls`、`max_ocr_pages`、`max_embedding_calls` 新作业为 `null`（不限）；PDF OCR 处理全部页面（原 100 页截断）。旧作业保留原值不迁移。
- **向量端点**：`base_url` 已带路径（如 `https://generativelanguage.googleapis.com/v1beta/openai`）时请求 `<base_url>/embeddings`，仅主机时保持 `<base_url>/v1/embeddings`。
- 保留：计数与用量展示、超时、取消与真实停止确认、并发容量、`max_retries`、连接测试与 ASR 每作业一次转写的语义、可选运维环境变量 `LIGHTGRAVITY_MAX_GENERATION_CALLS`（默认不设即只计数）、OCR 单页 `max_tokens_per_page`。

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

### 资料上传与自动索引体验规划引用（2026-10-18，非契约变更）

新增设计见 [docs/14](14-material-intake-and-auto-index.md)，任务 LG-139～145。LG-140 已按本文件变更控制冻结 **1.19.0** 加性契约（§20）；隔离候选已实现并完成局部回归，LG145第二轮独立QA已通过，根源码/运行服务仍为 **1.18.0**，未新增端点、错误码或 Task/Run 枚举，未部署前不代表线上已获得自动索引/媒体向量能力。既有 Personal 私有附件禁止共享索引/OCR/ASR/embedding 的边界保持；在 LG-145 独立验收前不得据规划宣称已有上传自动索引能力。

LG150/151实现补充（隔离候选，独立QA通过）：下一语义操作按当前有效enabled/base_url/model解析后端，在途操作保持快照；缓存持久记录非秘密endpoint/model身份，缺失或不匹配拒绝混用并返回既有`model_mismatch_rebuild_required`，不隐式重建。单来源显式重建保留其他来源缓存，失败如实报告。首轮QA FAILED保留，最终候选c3796ab经LG156冻结。

最终实施验收：LG145-R2对LG156冻结的c3796ab/tree1cd44bf独立QA **PASS**，见[报告](../probes/material-intake-20261018/lg145-r2/REPORT.md)。上方LG144等“待QA”是历史阶段说明，当前以此结果为准；无部署，根main/8123仍1.18。真实媒体与未跑检查限制按报告保留，不将本地QA当线上能力。
