# LG-029 F2 返修 — PLAN

> owner：`agent:pi-lg029-auth`（F2 唯一实施 owner，独立质量门由另 pi 集中复验，本包不自判 LG-032 通过）
> 分支 `fix/lg029-auth`，worktree `lightgravity-bot-worktrees/lg029-auth-fix`，基点 `834b262`（clean）
> 产品真实 DeepSeek/生成请求：**0**（本包全程）。不派工、不推送、不部署。

## 1. 独立确认的 F2 缺陷

- 契约：docs/08 §4.3 note「worker 侧调用须经受控执行身份，不接受浏览器直接指定任意 `owner`」；
  `docs/contracts/LG-028-preparation.md` §2.4「授权结果必须不依赖 worker 自报身份：`owner` 由程序按已注册 Member 推导」。
- 现状：`backend/lightgravity/api/collaboration.py` 的四个 LG-029 冻结端点
  （`GET /runs/{run_id}/discoverable`、`POST /runs/{run_id}/claim_requests`、
  `POST /subtasks/{id}/lease/renew`、`POST /subtasks/{id}/lease/release`）从 **请求体 `owner`** 取身份，
  **未使用** `ctx.worker_identity`；而 `POST /runs/{run_id}/collab_requests`（LG-030 peer）已使用程序身份接缝并 default-deny。
- 影响：已认证的执行者可自报任意 `owner`（冒充他人 / 抢同伴 lease / 扩大可发现范围 / 跨 TaskRun）。

## 2. 复用的既有程序绑定能力（不新造组织/平台层）

- `collaboration/execution_grant.py` 已有程序冻结的 worker 执行身份：
  `ExecutionGrantRegistry.mint(...)` 由 graph dispatcher 按 **(run, subtask, member, fence, authorized_node_refs)** 铸造不透明 token，
  `resolve_worker_identity(request)` 从 **`X-LG-Execution-Grant` 头**解析为程序记录的 member（body 永不参与认证），
  未配置/无 token/过期/撤销一律 `None`（default-deny）。
- `api/bootstrap.py` 已把 `resolve_worker_identity` 接到 `ApiContext.worker_identity`，且 dispatcher 与 API 共用
  `default_registry()`。
- `peer.py::PeerService.request(..., authenticated_member_ref=...)` 已实现 default-deny + `identity_mismatch` 语义，可对齐。

## 3. 修复设计（只改我持有的文件）

1. **`collaboration/execution_grant.py`**：新增 `resolve_worker_grant(request, registry=...) -> ExecutionGrant | None`，
   返回完整 grant（供 scope/fence 校验），`resolve_worker_identity` 保持兼容（内部复用）。
2. **`api/context.py`**（仅在确有必要时，复用既有 seam）：`ApiContext` 加性新增
   `worker_grant: GrantResolver | None = None`（`Callable[[Request], ExecutionGrant | None]`），
   语义 = 程序冻结的完整执行授权（成员 + run + subtask + fence + authorized nodes）。
3. **`api/bootstrap.py`**：把 `resolve_worker_grant` 一并接到 `worker_grant`（与既有 `worker_identity` 并存，不破坏 peer 路径）。
4. **`api/collaboration.py`**（F2 核心）：
   - discover/claim/renew/release 一律先经 `ctx.worker_grant`（回退 `ctx.worker_identity` 仅用于身份、但 scope 仍需 grant）解析 **程序身份**；
     未配置解析器 / 无有效 grant ⇒ `claim_refused(reason=unauthenticated)`，**不落业务状态**。
   - `owner` **只取 grant.member_ref**；body `owner`（兼容保留）若存在且 != grant.member_ref ⇒ `claim_refused(reason=identity_mismatch)`，不落盘。
   - **scope**：`grant.run_id` 必须等于路径 `run_id`；发现/领取的 `subtask_ref` 必须在 `grant.authorized_node_refs`；
     renew/release 只允许 grant 自己持有的 `subtask_id`，且 `fence` 必须等于 `grant.fence`（旧 fence / 抢同伴 ⇒ 拒绝）。
   - body 的 `capability`/`lease_seconds` **不得**用于授予 capability/write/scope；仅作提示，能力/范围由程序 grant 与 discovery 决定。
   - 默认关闭：策略仍由 `ClaimPolicyReader` 控制，关闭时保持 `feature_disabled`，不回归。
5. **`tests/collaboration/test_api_collaboration.py`**（我持有）：改用程序注入身份（grant registry / header），
   覆盖：未认证拒绝、错误 principal 拒绝、未配置解析器拒绝、owner 伪造拒绝、fence 陈旧拒绝、
   跨 run/subtask scope 拒绝、capability/write 不可升权、正常同 owner 流程、续租/释放、幂等、竞争、默认关闭回退。
   所有拒绝断言 **服务状态未写**（不只状态码）。

## 4. 明确不做

- 不写 docs/08、PROJECT.md、README.md、agent.md、docs06（契约变更精确变化写入 REPORT，交唯一 docs08 owner F1 串行登记）。
- 不改 `coordinator/**`、`store/**`、`settings/**`、collaboration engine（F1 owner）。
- 不新增产品生成、不跑真实 SDK 模型探针；真实 ASGI HTTP 允许无模型。
- 不 reset/clean/覆盖/重复 pick；保留所有原始记录与 worktrees；root PM dirty / 旧 worktree / 8123 / 其它 owner 不动。
- 不修改 peer（LG-030）既有认证语义，仅复用。

## 5. 验收命令

- `uv run pytest tests/collaboration -q`（局部）
- `uv run mypy backend/lightgravity/api/collaboration.py backend/lightgravity/api/context.py backend/lightgravity/collaboration/execution_grant.py`（改动模块）
- 不跑无关全量。
