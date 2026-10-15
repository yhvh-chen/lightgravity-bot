# LG-029 集成接线说明（交集成 owner 串行处理）

> owner：`agent:pi-lg029`。本文件说明 LG-029 已交付的**独立模块**如何在
> `api/app.py`、settings 写入与 coordinator 中接线。**这些共享文件不由 LG-029 修改**
> （LG-019/LG-025 及 docs08 单 owner），因此以下内容只给出**最小补丁**与证据，
> 未装配前状态如实“待集成”。所有改动均为**加性、默认关闭**，不改变确定性调度路径。

## 1. 已交付、可直接接入的模块

| 文件 | 作用 | 依赖 |
|---|---|---|
| `backend/lightgravity/collaboration/{models,errors,discovery,lease,service}.py` | 发现投影、原子领取、租约、fence、幂等、默认关闭策略 | 仅 `store`/`contracts`，不改 store schema |
| `backend/lightgravity/collaboration/peer.py` | LG-030 预留独立边界（未实现，`PEER_MODULE_IMPLEMENTED=False`） | 无 |
| `backend/lightgravity/api/collaboration.py` | 冻结端点 `GET /runs/{run_id}/discoverable`、`POST /runs/{run_id}/claim_requests`、`POST /subtasks/{id}/lease/renew`、`POST /subtasks/{id}/lease/release` | FastAPI、`ApiContext` |
| `tests/collaboration/**` | 真实文件 Store 并发竞争、权限/能力/依赖/预算拒绝、过期 fencing、cancel/restart、默认关闭、API 层 | pytest |

## 2. 最小装配补丁（交集成 owner）

### 2.1 挂载路由（`backend/lightgravity/api/app.py`，LG-019 owner）

在 `create_app` 内、其他 `include_router` 之后加入：

```python
from .collaboration import build_collaboration_router
...
app.include_router(build_collaboration_router(), prefix=API_PREFIX)
```

无需新增依赖注入：`build_collaboration_router()` 通过 `get_context(request)`
读取现有 `ApiContext.store`，并在每次请求时用 `ClaimPolicyReader(ctx.store)`
读取当前开关。`api/app.py` 已注册的 `AppError` 处理器会把
`claim_refused`/`stale_lease` 映射为 409 错误信封（`contracts.ERROR_HTTP_STATUS`
已含这两个码）。

### 2.2 开关写入（`settings/**`，LG-025 owner）

`docs/08` §6.5 新增三个设置项：`decentralized_claim_enabled`（默认 `false`）、
`collab_requests_enabled`（默认 `false`）、`claim_lease_seconds`（默认 `300`）。
它们属于 `settings/SETTINGS.md` 的**非秘密**字段。

- **读取**：已由 `collaboration.service.ClaimPolicyReader` 直接 `Store.read("settings","settings")`
  实现，缺失或非法值一律回落为**关闭** + 300 秒，因此即使 settings 层尚未写入这些字段，
  行为也已经是“默认关闭”。
- **写入**：需要 `settings` 服务（`ConnectionRepository`/`SettingsService`）在 allow-list 中
  接受这三个字段并可 `Store.write` 到 `SETTINGS.md`。若 settings 层用固定字段白名单，
  加入这三个键即可；**不需要**新增实体或端点语义。LG-029 不修改 `settings/**`。

### 2.3 Subtask `fence` 的 schema 校验（`store/entities.py`，LG-004 owner；可选）

`fence` 是加性可选字段。当前 Store 的 `merge_maps` 会**保留未知字段**，所以
`LeaseManager` 写入的 `fence` 已经能正确落盘与读取；`fence_of()` 对缺失/非法值按 `0`
处理并给诊断语义。若希望 `validate_subtask_static` 也内建校验，最小补丁为：

```python
# store/entities.py :: validate_subtask_static
_validate_int(data, "fence", "subtask", diagnostics, minimum=0)
```

这是**可选增强**：不加也不影响本任务全部验收（测试覆盖了 legacy 无 fence 与非法值的降级路径）。
不需要新增枚举，`docs/08` §6.3 的 `state`/`acceptance.status` 枚举保持不变。

### 2.4 执行身份（worker owner）来源

当前 `POST /runs/{run_id}/claim_requests` 的 `owner` 由请求体提供，与
`docs/08` §4.3 注记“worker 侧调用须经受控执行身份，不接受浏览器直接指定任意
`owner`”存在差距。本任务的可运行部分是**程序权限/租约/fencing 权威**；受控执行身份
需要在 executor 接入时（LG-031）由协调器把已认证 Member 身份注入，而不是取自浏览器。
在此之前，端点的访问边界仍由既有 `AccessPolicy`（loopback + 必要时 `X-LG-Token`）承担。

### 2.5 与图调度的关系（不接线即可保持默认路径）

`collaboration` 默认关闭时：

- `GET /discoverable` 返回 `enabled=false` 与空列表；
- `POST claim_requests` 抛 `claim_refused`（`feature_disabled`）；
- `GraphDispatcher`/`SubtaskClaimer`（`coordinator/**`，018 owner）保持原样，
  仍由程序按 `plan_source=rules` 顺序调度，未被本包替换。

**未做**：把 `LeaseManager` 替换 `coordinator.scheduler.SubtaskClaimer`。这属于
`coordinator/**`（018 owner）与 LG-031 的整合范围；LG-029 只保证两者不冲突：
`fence` 写入同一 Subtask frontmatter，`owner`/`lease_expires_at` 语义与既有
`SubtaskClaimer` 一致。

## 3. 未接线 / 未装配事实（不得当作完成）

- `api/app.py` **未挂载** collaboration 路由（本轮测试用等价最小 App 挂载证明可接线）。
- `settings/**` **未**接受/写入三个开关字段（读取已容错为关闭）。
- `coordinator/**` **未**改用 `LeaseManager`（默认路径不变）。
- Subtask `fence` schema 校验为**可选**，未加入 `store/**`。
- LG-030 peer 模块为**预留空壳**，未实现。
- 受控 worker 执行身份注入未实现（见 2.4）。

## 4. 建议集成顺序

1. `settings/**` 加三键写入（2.2）；
2. `api/app.py` 挂载路由（2.1）；
3. 可选加 `fence` 静态校验（2.3）；
4. 由 LG-031 在协调器接入执行身份与 `LeaseManager`（2.4/2.5）；
5. 之后才可声称去中心化端点已装配；集中 QA 归 LG-032。
