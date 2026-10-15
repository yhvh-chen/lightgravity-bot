# LG-031 INTEGRATION — 交唯一集成 owner / LG-032

owner: `agent:pi-lg031`，branch `dev/lg031`，base `e4cef4a`。

本包是 LG-029/030 的**运行时整合层**：把已冻结的发现/领取/租约/fencing 与受控同伴
协议接入真实执行与验证返修闭环，并补上**程序冻结的执行身份**。所有改动加性、
默认关闭、可回退。

## 1. 接线点（已在 `dev/lg031` 完成）

| 位置 | 变更 | 说明 |
|---|---|---|
| `api/bootstrap.py` | `GraphDispatcher(..., collaboration=CollaborationService(store, policy=ClaimPolicyReader(store).read()))`；`create_app(..., worker_identity=resolve_worker_identity)` | 开关关闭时 `collaboration.enabled=False`，图调度不变 |
| `api/app.py` | `create_app` 加性参数 `worker_identity` 并写入 `ApiContext` | 默认 `None` ⇒ 同伴端点默认拒绝 |
| `coordinator/graph.py` | 加性 `collaboration`/`grant_registry`；`_claim_decentralized`/`_peer_tools_for`/`_revoke_grant` | 仅当 `collab.enabled` 才走 fenced 领取与受限工具 |
| `adapter/execution.py`+`sdk_config.py`+`executor.py` | `ExecuteRequest.execution_grant`/`custom_tools`，SDK `tools=` | 默认空 ⇒ 无自定义工具 |
| `settings/**` | 三开关读写 | 缺省/非法回落关闭 |

## 2. 关键安全语义（不得弱化）

- **身份由程序冻结**：`ExecutionGrantRegistry.mint()` 产生不透明 token，绑定
  `(task,run,subtask,member,fence,授权节点集合,协作预算)`；进程内、非持久、重启即失效。
  旧持有者 token 在新 fence 领取时被 revoke。
- **body 永不认证**：`resolve_worker_identity` 只读 `X-LG-Execution-Grant`；body 的
  `from_member_ref`/`owner`/`fence` 不作为认证。同伴工具的身份来自 grant。
- **最小授权**：受限工具只能访问本 Run 已授权节点，预算由程序冻结计数；越权/预算耗尽/
  grant 失效一律确定拒绝。
- **过期≠停止**：`reclaim_expired` 只使租约可重新授予；`write=true` 或有未知副作用进
  `recovery_required`，不自动重放；只有确认停止（adapter confirmed）才回收执行权限。
- **旧 fence 写入拒绝**：`guard_write_back`/`assert_current` 在任何写入前校验当前 fence。
- **默认回退**：三开关任一关闭 ⇒ 与现状一致（确定性 `plan_source=rules`，无自定义工具）。

## 3. 交 LG-032 的集中 QA 清单

1. 真实 SDK 多 worker 进程内工具注入的端到端（本包用真实 Git + 进程内 fake executor）。
2. 全生命周期成本：执行/review/repair/recheck/failures，`usage` 未知项计 `unknown`，
   与程序调度基线在相同基点/任务/模型/预算/验收门下对比。
3. `not_discoverable` vs `held_by_other` 的竞争原因竞争需在 QA 中固定判定口径
   （见 `probes/lg031/STATUS.md` 已知缺陷；未改 LG-029 已验收测试）。
4. 完整 checkpoint skip 仍未实现，恢复仅依赖已落盘证据。

## 4. 不改动的既有验收

- 未改 `store/**`、`verify/**` 核心、`contracts/**` 枚举、`sources/**`、前端。
- 未改 LG-029 discovery/lease 语义；未改 LG-017 rework 语义。
- `docs/08` 仅本包 owner 加性说明，无版本/字段/端点/枚举变化。
