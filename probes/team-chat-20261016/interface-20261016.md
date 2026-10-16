# LG-TEAM 最小加性接口约定（2026-10-16）

状态：**接口约定（未实现）**。两位执行者按本文件并行；不得各自另立协议。
适用范围：团队聊天 + 简单认证。仅在 team mode 显式开启时生效；**默认单用户行为逐字节不变**。

## 0. 基点与隔离

- 基点（base）：`main` HEAD `d873a36`（主工作区）。
- 后端 worktree：`/tmp/lg-team-backend-20261016`，分支 `feat/team-backend-20261016`。
- 前端 worktree：`/tmp/lg-team-frontend-20261016`，分支 `feat/team-frontend-20261016`。
- 主工作区 `PROGRESS.md`（dirty）与未跟踪 `backlog/tasks/LG-050.md` **保留不动**；两 worktree 均从 `main` 提交创建，天然不包含该 dirty/未跟踪内容。
- 不触碰主工作区已有常驻 uvicorn `:8123`（pid 3320750，非本包）、不复用其 dataRoot。验收冒烟用专用端口 + 专用 data root。
- 不读取真实 `.env`/密钥；后端不使用 `X-LG-Token` 作为 team 角色依据（见 §6）。

## 1. 配置变量（全部加性、默认关闭）

| 变量 | 默认 | 语义 |
|---|---|---|
| `LIGHTGRAVITY_TEAM_MODE` | `false` | `1/true/yes/on` 开启团队模式；否则保持单用户原行为 |
| `LIGHTGRAVITY_TEAM_ACCOUNTS` | `<data_dir>/team/accounts.json` | 账户事实源 JSON 路径（单独真相，不引入数据库） |
| `LIGHTGRAVITY_TEAM_SESSION_TTL_SECONDS` | `28800` | 服务端会话有效期（秒） |
| `LIGHTGRAVITY_TEAM_COOKIE_SECURE` | `false` | loopback http 默认 false；置 true 时 cookie 加 `Secure` |
| `LIGHTGRAVITY_TEAM_BOT_MENTION` | `@bot` | 触发原路由的全局消息前缀（team mode） |

解析规则：team mode 关闭时不得读取/创建 accounts 文件、不得改变任何现有端点行为。

## 2. 账户事实源（受控 JSON，单独真相）

路径：`LIGHTGRAVITY_TEAM_ACCOUNTS`。写入必须原子替换（复用 `store/atomic` 风格）+ 进程内锁。

```json
{
  "schema": "lightgravity.team/v1",
  "accounts": {
    "alice": {
      "username": "alice",
      "role": "admin",
      "password": {
        "algo": "pbkdf2_sha256",
        "iterations": 200000,
        "salt": "<base64>",
        "hash": "<base64>"
      },
      "created_at": "2026-10-16T00:00:00.000Z"
    }
  }
}
```

- `role ∈ {"admin","member"}`；未知字段保留，未知 `algo` 拒绝。
- 口令只存盐+哈希，永不落明文、永不入日志/argv/prompt/提交。
- 启动引导首个 admin 用 **CLI**（最简）：`lightgravity user add --username <u> --role admin`，口令经 `getpass` 从 stdin/tty 读取，**不进 argv**。附加只读命令 `lightgravity user list`（只打印用户名/角色/创建时间）。CLI 不打印哈希或口令。
- `accounts.json` 位于 dataRoot 内、gitignored；不得提交。

## 3. 认证 HTTP 端点（加性，前缀 `/api/v1`）

**GET `/api/v1/auth/me`** — 匿名允许。响应 200：
```json
{ "mode": "team", "authenticated": false, "username": null, "role": null }
```
已登录时 `authenticated=true`，`username`/`role` 为会话事实。team mode 关闭时返回
`{ "mode": "single", "authenticated": true, "username": null, "role": "admin" }`。
（前端据此决定是否显示登录页、是否开启轮询，无需猜。）

**POST `/api/v1/auth/login`** — 匿名允许。请求：
```json
{ "username": "alice", "password": "..." }
```
成功 200：
```json
{ "username": "alice", "role": "member" }
```
并 `Set-Cookie: lg_session=<opaque>; HttpOnly; SameSite=Lax; Path=/[; Secure]`。
失败一律 401（用户名不存在与口令错误返回同一信封，恒定时间比较，不泄露存在性）：
```json
{ "error": { "code": "unauthorized", "message": "invalid username or password",
  "details": {}, "retryable": false, "request_id": null } }
```
team mode 关闭时该端点返回 404（不注册）或 `not_ready`；本约定取 **404**，不改变单用户。

**POST `/api/v1/auth/logout`** — 需已登录（匿名返回 401）。成功 204（无 body）并清除 cookie
（`Set-Cookie: lg_session=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/`）。重复登出幂等返回 204。

会话：服务端进程内内存表 `session_id -> {username, role, expires_at}`；cookie 只放不透明随机 id。
重启失效，前端收到 401 后重新登录（如实，不伪造持久会话）。

CSRF/Origin：沿用 `HostGuardMiddleware` 的同源 `Origin` 拒绝；cookie `SameSite=Lax` 阻断跨站携带；
mutating 端点额外要求 `Host`/`Origin` 同源。不新增 token 表单/双重提交机制。

## 4. 角色与访问矩阵（team mode）

| 主体 | 业务只读 GET | 业务写 POST/PATCH | `/settings*`、`PATCH /resources/{kind}/{id}`、凭证 | `/auth/me`、`/auth/login` | `/health`、`/version` |
|---|---|---|---|---|---|
| 匿名 | 拒绝 401 | 拒绝 401 | 拒绝 401 | 允许 | 允许 |
| member | 允许 | 允许 | 拒绝 **403** | 允许 | 允许 |
| admin | 允许 | 允许 | 允许 | 允许 | 允许 |

- 业务面包括 tasks、conversations、files（含 upload/download/content）、sources、search、vector、
  resources/team 读、notifications、events/SSE、runs/subtasks 协作端点。
- 匿名对 SSE `GET /events/stream` 在建立流之前即拒绝 401（不得先 200 再断流）。
- 新增加性错误码 `forbidden`（HTTP 403，`retryable:false`）用于“已登录但无权限”。信封：
```json
{ "error": { "code": "forbidden", "message": "administrator role required",
  "details": { "required_role": "admin" }, "retryable": false, "request_id": null } }
```
该码需在 `contracts/enums.py`、`errors.py` 加性登记（由整合 owner 串行落，见 §8）。
- 越权写 settings 的判定路径：`is_sensitive_request` 与 `PATCH /resources/...` 都先过 role 检查，
  再走既有 `LocalAccessPolicy` 逻辑（既有 token 机制保留但不授权 team 角色）。
- 单用户模式：完全沿用现行 `LocalAccessPolicy`，矩阵与错误码不变。

## 5. 全局消息：author 与 @bot 路由

**POST `/api/v1/conversations/global/messages`**（team mode）请求体沿用现有字段；
不接受客户端 `author`（若传则 422 `validation_failed`，防伪造）。服务端按会话写入：
- 持久化消息新增加性可选字段：
  `"author": { "kind": "user", "username": "alice", "role": "member" }`
- 读取 `GET .../global/messages` 每个 item 的 `message` 内返回 `author`；旧的缺省 item 前端按
  “未知/历史”渲染，不编造。assistant 回复 `author = {"kind":"bot","username":"bot","role":"assistant"}`。

路由（team mode）：
- 普通消息：仅持久化，**不触发 bot/协调器**，无 model 调用、不建 Task。响应加性 `kind`：
```json
{ "kind": "recorded", "reply": null, "conversation_id": "conv_...",
  "data": { "intent": "recorded", "creates_task": false } }
```
- 仅当 content 去前导空白后以 `LIGHTGRAVITY_TEAM_BOT_MENTION`（默认 `@bot`）开头且其后为空白/结束/标点时：
  去掉该前缀，走**现有** `classify_message` + `_route_global` 原路径，结果形状与现契约一致。
- **Task 显式消息**（`POST /tasks/{id}/messages`）在两种模式下均走既有行为，不受 @bot 限制。
- **单用户模式**：全局消息仍走原路由（不要求 @bot），author 可省略；保证默认不变。

实现归属：author 注入与 @bot 门控在 `coordinator/service.py::submit_global_message`（后端 owner）；
`api/conversations.py` 仅做校验/透传与禁止客户端 author。

## 6. 反绕过约束（硬性）

- team mode 下 **`X-LG-Token` 不构成身份/角色**：新 `TeamAccessPolicy` 只信 HttpOnly 会话 cookie；
  携带任何 token 都不能提升为 admin 或绕过匿名拒绝。
- team mode 下前端 **不注入** `window.__LG_RUNTIME_TOKEN__`（`mount_frontend`/`/auth/me` 流程传空 token），
  使旧 HTML 内联 token 无法成为 admin 后门。
- 已登录身份只从服务端会话解析；请求体/头部自报 username/role 一律忽略或 422。
- 口令、会话 id、哈希不得出现在错误 `details`、日志、URL、Markdown。

## 7. 前端约定（前端 owner）

- `apiRequest`/各 fetch helper 加 `credentials: 'include'`（`frontend/src/api/client.ts` 及 files/settings/
  sources/chat 等直接 fetch 处），使同源 cookie 随请求发送。SSE 的 `EventSource` 同源自动带 cookie。
- 启动时调 `GET /auth/me`：`authenticated=false` → 显示登录页；登录成功后再进入工作台。
- `ChatMessage` 加性可选 `author?: { kind: string; username: string | null; role: string | null }`；
  视图按 author 显示发言人（无则“未知”）。客户端 `sendMessage` 不发送 author。
- 同步：team mode 下对当前全局会话做**轻量定时轮询**（建议 3–5s，页面隐藏时暂停），复用
  `readMessages({taskRef:null}, cursor)` 增量拉取，按 `message_id` 去重；不新增 SSE。
  普通消息（`kind==="recorded"`）不等待 bot 回复。
- 单用户模式不加轮询以外的行为变化，保持现有路径与测试。

## 8. 文件 owner（单一 writer）

后端 worktree（owner：后端执行者）：
- 新增 `backend/lightgravity/team/**`（accounts/hash/session/identity/policy）
- 新增 `backend/lightgravity/api/auth.py`（登录/登出/me 路由）
- 改 `backend/lightgravity/api/access.py`（team 分支；匿名放行清单；admin-only 判定）
- 改 `backend/lightgravity/api/app.py`（挂 auth 路由、注入 team 策略；`is_sensitive_request` 扩展）
- 改 `backend/lightgravity/api/conversations.py`（禁止客户端 author、透传）
- 改 `backend/lightgravity/coordinator/service.py`（author 注入、@bot 门控、recorded 结果）
- 改 `backend/lightgravity/runtime/bootstrap.py`、`runtime/frontend.py`（team 装配、禁止 token 注入）
- 改 `backend/lightgravity/cli.py`（`user add/list`，getpass）
- 改 `backend/lightgravity/config.py`（team 配置字段）
- 测试：`tests/team/**`、`tests/api/test_auth.py`

契约（`backend/lightgravity/contracts/**`，加 `forbidden`）：**整合 owner 串行落**；后端执行者提交
补丁说明或由整合者代改，不并行写同一文件。

前端 worktree（owner：前端执行者）：
- 新增 `frontend/src/views/auth/**`、`frontend/src/api/teamAuth.ts`
- 改 `frontend/src/api/client.ts`、`auth.ts`（credentials/身份）、`chat.ts`（author 类型）
- 改 `frontend/src/views/chat/useChat.ts`（定时增量轮询）
- 改 `frontend/src/App.tsx`（登录门）
- 测试：`frontend/tests/team-auth.test.tsx`、`chat-author.test.tsx`

共享面（`api/access.py`、`app.py`、`coordinator/service.py`、`frontend/src/api/chat.ts`）由各自
worktree 内单一执行者修改；两 worktree 间通过本文件的请求/响应格式对齐，不互相直接改文件。

文档：`docs/08-interface-contract.md` 变更由 docs08 owner 串行（加性 MINOR，登记 `forbidden`、
auth 端点、author 字段、team 开关）。本次准备不改产品代码。

## 9. 验收最小点（两执行者各自冒烟）

- team 关闭：现有测试不回归；`/auth/login` 404；全局消息原路由。
- team 开启 + 无 cookie：业务 GET/POST/文件/SSE 全部 401；`/auth/me` 200 匿名；`/health` 200。
- `lightgravity user add` 后登录：member 写 settings → 403 `forbidden`，读允许；admin 写允许。
- 全局普通消息：仅持久化、返回 `kind:"recorded"`、带 `author`、不建 Task/不调模型；
  `@bot ...` 才进入原分类路由。
- 旧 HTML 注入的 `X-LG-Token` 在 team mode 下不能访问业务或提升为 admin。
- 前端：登录 → 工作台；两浏览器窗口定时轮询互相看到新全局消息；单用户模式无回归。
