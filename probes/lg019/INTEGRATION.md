# LG-019 集成说明（供唯一集成 owner 串行处理）

本文只描述 **LG-019 新增/依赖的共享装配点与 docs/08 契约提案**。所有共享文档
（docs/08、README、PROJECT、PROGRESS、agent、docs06）由集成 owner 串行维护；
本文不直接修改它们。

## 1. 本包 owner 的文件

| 文件 | 说明 |
|---|---|
| `backend/lightgravity/notifications/**` | 新包：投影 `projection.py`、持久 read 状态 `store.py`、服务 `service.py`、模型 `models.py` |
| `backend/lightgravity/api/notifications.py` | 新路由 `GET/POST /api/v1/notifications` |
| `backend/lightgravity/api/context.py` | 加性字段 `ApiContext.notifications` + `get_notifications`（本包最小改动） |
| `backend/lightgravity/api/app.py` | 仅最小装配：构造 `NotificationService` 并 `include_router(build_notifications_router())` |
| `tests/api/test_notifications.py`、`tests/api/api_helpers.py`（新增 `create_bare_task`） | 后端测试 |
| `frontend/src/api/notifications.ts`、`frontend/src/app/cursorStore.ts`、`useNotifications.ts`、`useEventStream.ts` | 前端 client / store / SSE 游标 |
| `frontend/src/app/TopBar.tsx`、`frontend/src/components/NotificationList.tsx`、`frontend/src/app/shell.css` | 真实壳通知接线 |
| `frontend/tests/notifications.test.tsx` | 前端测试 |
| `probes/lg019/**` | 证据与冒烟脚本 |

**未修改**（遵守 owner 边界）：`coordinator/service.py`、`verify/**`、`api/tasks.py`、
`graph/scheduler/dispatcher/adapter`。

## 2. 集成点：无需共享 hook

通知是 **durable 事件流的只读投影**：`projection.py` 扫描各 Task 的
`events/<stream_id>/events.jsonl`（`task.phase_changed` / `decision.requested`），
映射为 `task.failed` / `task.waiting_user` / `task.awaiting_acceptance` /
`task.recovery_required`。事件仍是“先落盘、后广播”（既有
`BroadcastingStore.append_event`），因此：

- 不需要在 `coordinator/service.py` 或 `verify/**` 增加写入 hook；
- 不需要新的 `notification.created` 写入路径（该事件类型保留给未来显式通知）；
- 投影是确定性的，`notification_id` 由 `(stream_id, seq, kind)` 派生，重启后
  重新投影仍解析到同一记录与其持久 read 状态。

若未来要写显式 `notification.created` 事件，调用点应放在
`StateWriter.transition_task` 同层（`coordinator/state.py`，**不是本包 owner**），
并保持先落盘后广播；届时通知投影需与显式事件去重。当前实现不依赖该 hook。

## 3. docs/08 契约提案（集成 owner 统一升版）

`GET/POST /api/v1/notifications` 已在 docs/08 §4.3 冻结（LG-019），本包按该路径
实现，**未新增端点**。仅建议在 §4.3 补充响应字段（加性、非破坏）：

```
GET /api/v1/notifications?unread_only=&task_ref=&limit=
  200 {
    "items": [{
      "notification_id": "notif_<ULID-like sha 前缀>",
      "kind": "task.failed|task.waiting_user|task.awaiting_acceptance|task.recovery_required",
      "title": str, "body": str, "at": iso8601, "severity": "info|success|warning|error",
      "task_ref": "task_...", "run_ref": "run_...|null",
      "event_id": "evt_...", "stream_id": "task_...", "seq": int,
      "candidate_ref": "run_...|null",
      "requirements_revision": int|null, "deliverable_revision": int|null,
      "reason": str|null, "read": bool, "read_at": iso8601|null
    }],
    "next_cursor": null,
    "unread": int        # 全量未读数，非分页计数
  }
POST /api/v1/notifications
  { "notification_ids": ["notif_..."], "request_id": "req_...|null" }
  200 { "marked_read": [...], "unknown": [...], "unread": int }
```

- 未知 `notification_id` 进 `unknown`，**不伪造**记录。
- `POST` 不在 `/api/v1/settings` 前缀下，因此按现有 access policy 属普通写；它只
  写 read 标志，不含秘密。集成 owner 若要把标记已读提升为 sensitive，请统一在
  access 层处理，本包不复制该逻辑。
- 若契约要求 `GET/POST` 命名或包结构不同，以正式契约为准，本实现可随之调整。

## 4. 与 LG-016/018 的边界复用

- 反重放/停止确认由 LG-016 在 verify/coordinator 内维护；通知不复制其状态，
  仅在事件投影上呈现 `recovery_required` / `failed`。
- 版本绑定（overdue/重复回复不得作用新版本）由既有 verify `_assert_fresh` 的
  `expected_requirements_revision` / `expected_deliverable_revision` 保证；本包
  在通知项里携带同一 binding，前端点击回到准确 Task/Run/candidate/version。
- 若 LG-018 的 worktree/整合改动了 `api/app.py` 或 `api/context.py`，请以本包
  加性改动为准合并（`notifications` 字段与 router 挂载）。

## 5. 未测限制

- 真实模型调用 **0**（本包明确预算）；SSE/通知冒烟不触发模型。
- 真实 SDK 集成验收留 LG-021/022；本包只证明真实 HTTP/SSE 与真实 Firefox UI。
- 通知投影只覆盖 4 个需提醒的 phase；`budget` 停止若表现为 `failed` 会被覆盖，
  但专门的预算事件类型未来加入时需扩展投影映射。
