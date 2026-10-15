# LG-030 集成接线说明（交唯一集成 owner 串行处理）

> owner：`agent:pi-lg030`。本文件说明 LG-030 已交付模块的**装配状态**与**交 LG-031 的接线点**。
> 所有改动为**加性、默认关闭**，不改变确定性调度路径。LG-030 **不修改** `api/app.py`、
> `coordinator/**`、`settings/**`、`store/**`、`contracts/**`、共享 docs。

## 1. 已交付、可直接接入的模块

| 文件 | 作用 | 依赖 |
|---|---|---|
| `backend/lightgravity/collaboration/handoff.py` | 带版本/hash 的产物引用解析与 Task/Run 授权（`evidence:` 与 `<subtask>@<hash>:<artifact>`） | `lightgravity.evidence` |
| `backend/lightgravity/collaboration/context.py` | 有界授权摘要（非执行）+ `instruction_like` 标记 + 因果绑定 | 无 |
| `backend/lightgravity/collaboration/peer.py` | `PeerService`：受控同伴请求/结果、幂等、权限/预算/超时/容量、fence 校验、JSONL 事实源 | `store`、`contracts` |
| `backend/lightgravity/api/collaboration.py` | 新增冻结端点 `POST/GET /api/v1/runs/{run_id}/collab_requests` | FastAPI、`ApiContext` |
| `tests/collaboration/test_peer*.py` | 局部检查 | pytest |

## 2. 装配状态（重要）

### 2.1 路由：**已装配**（无需改动）

`api/app.py` 已由 LG-029 集成时挂载 `build_collaboration_router()`（`app.include_router(...,
prefix=API_PREFIX)`）。LG-030 在该 router 内新增 peer 端点，因此**默认 app 已含**：

- `POST /api/v1/runs/{run_id}/collab_requests`
- `GET  /api/v1/runs/{run_id}/collab_requests`

无需再改 `api/app.py`。已离线核对默认 `create_app()` 的 `app.routes` 含上述两条。

### 2.2 开关：**读取已就绪，写入归 settings**

`peer.PeerService.enabled` 读取 `settings/SETTINGS.md` 的 `collab_requests_enabled`（经
`ClaimPolicyReader`，与 LG-029 共用）。默认缺失/非法 → **关闭**（`feature_disabled` 拒绝），
与 docs/08 §6.5 一致。settings 写入路径仍归 LG-025/LG-031（与 LG-029 INTEGRATION §2.2 相同），
LG-030 不修改 `settings/**`。

### 2.3 程序认证依赖接缝：**已加（集成 owner 兼容修复，默认拒绝）**

集成 owner 在合并时补上执行身份接缝，保护 030 协议边界：

- `ApiContext.worker_identity: WorkerIdentityResolver | None`（`(Request) -> str | None`），
  默认 `None`；`None` 或解析为 `None` 时 `POST collab_requests` **默认拒绝**
  （`state=rejected`、`reason=unauthenticated`，**不落盘、不消耗预算**）。
- `PeerService.request(..., authenticated_member_ref=...)` 要求**程序认证身份**等于 body 的
  `from_member_ref`；不符返回 `identity_mismatch`（同样不落盘）。**body 自报身份永不作为认证**。
- 真实 worker 身份注入（协调器把已认证 Member 注入，而非浏览器）仍归 **LG-031**；
  接缝已就位，030 不再因此阻塞。

## 3. 交 LG-031 的接线点（本包未做，不得当作已完成）

1. **受控执行身份注入**：接缝 `ApiContext.worker_identity` 已在（§2.3），LG-031 负责提供
   **程序认证**的实现（协调器把已认证 Member 身份注入，而非取自请求体）。**不得**把
   body 自报身份当认证通过。（此前版本此处写“身份仍取请求体”，已被 §2.3 的集成修复取代。）
2. **Graph 接线**：把 `PeerService` 的请求/结果接入协调器图节点（与 LG-029 的
   `LeaseManager` 替换 `SubtaskClaimer` 一并），使协作请求在真实执行中发起与消费。
3. **fence 复核**：`PeerService.request(..., fence=...)` 已校验当前 Subtask `fence`；Graph 接线时
   应把当前 holder 的 fence 传入，旧持有者请求按 `stale_lease` 拒绝。
4. **`recovery_required`**：对齐 docs/08 §6.2——过期后未知副作用不自动重放；协作**不**改变该语义。
5. **完整 checkpoint skip**：仍未实现，恢复仅依赖已落盘证据。

## 4. 事实源与事件

- 同伴请求事实源：`<data_dir>/collaboration/collab_requests.jsonl`（追加式，按 `request_id` 幂等；
  可重建，非第二套权威数据库）。合并了「先 load 后 append」为同一 per-Run `flock` 临界区，避免并发重复。
- 事件（写入 Run `events.jsonl`，`1.6.0` 冻结事件类型）：`collab.requested`、`collab.resolved`、
  `handoff.produced`、`handoff.rejected`。已在本包测试中实测产生。
- 不改 `contracts/**` 枚举（事件类型 `1.6.0` 已冻结存在）。

## 5. 建议集成顺序

1. LG-031 在协调器注入受控执行身份（含 member 校验），并接线 `LeaseManager`/`PeerService`；
2. 按需由 LG-025/LG-031 增加 settings 写入三开关；
3. 之后才可声称去中心化协作端点**已装配**；集中 QA 归 LG-032。
