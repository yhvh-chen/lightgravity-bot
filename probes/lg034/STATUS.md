# LG-034 STATUS — 原件接收与可恢复摄取作业

- 执行者：agent:pi-lg034；worktree `lg034`，分支 `dev/lg034`。
- 时间：2026-10-16。
- 契约基准：docs/08 `1.6.0`（§4.3/§5.1/§6.6 LG-033 资料线冻结接口）。
- 结论：**实现完成，待集成装配（in-progress，待版本 QA LG-040）**。API 已在真实
  `create_app` app 上实际接线并通过 HTTP 测试；`api/app.py`（他人 owner）的最终
  一行装配按 `probes/lg034/INTEGRATION.md` 交集成唯一 owner 串行接线。

## 1. 交付物（文件 owner 内）

| 文件 | 说明 |
|---|---|
| `backend/lightgravity/sources/__init__.py` | 包导出 |
| `backend/lightgravity/sources/models.py` | `source`/`intake_job` 类型化视图与枚举 |
| `backend/lightgravity/sources/store.py` | 文件 SoT（原件/来源/作业/收件区/回执/幂等与去重映射），复用 LG-004 原子写与 flock |
| `backend/lightgravity/sources/intake.py` | 接收、幂等/冲突、作用域去重、来源版本、取消/重试/重启恢复 |
| `backend/lightgravity/sources/service.py` | 程序侧归属/权限校验、读投影、受控收件区 |
| `backend/lightgravity/api/sources.py` | `build_sources_router()`（单行装配） |
| `tests/sources/**` | 21 项真实 API/文件集成测试（见 §3） |
| `probes/lg034/INTEGRATION.md` | 装配说明（交集成 owner） |
| `probes/lg034/STATUS.md` | 本文件 |
| `backlog/tasks/LG-034.md` | 验证记录与状态 |

未改：`api/app.py`、`api/*`（除新增 `sources.py`）、`frontend/**`、
`coordinator/**`、`verify/**`、`adapter/**`、`store/**`、`contracts/**`、
共享 docs。未 push/deploy/publish。参考仓库未改动。

## 2. 验收条件对照（LG-034 验收条件）

| 验收条件 | 实现 | 证据 |
|---|---|---|
| 全局资料进入受控收件区而非强建 Task | `POST /inbox/messages` 建/用受控 `inbox_ref`，返回 `task_created=false`/`run_created=false`；`POST /sources` 从不创建 Task/Run | `test_inbox_message_does_not_create_task`、`test_global_inline_source_creates_inbox_ref_not_task` |
| Task/Project 归属由授权与程序校验落实 | `task_ref` 经权威 Store 解析，未知 Task → `reference_invalid`；`project_ref` 无注册表 → 如实 `reference_invalid`；`scope` 至多一个目标 | `test_unknown_task_ref_is_refused`、`test_project_ref_is_refused_without_registry`、`test_scope_local_dedup_does_not_merge_across_tasks` |
| 请求幂等、负载冲突 | 同 `request_id` 同 payload 返回首次结果（不重复建来源）；同 key 异 payload → `source_conflict`（409，不覆盖） | `test_request_id_idempotent_and_payload_conflict` |
| 版本更新 | 内容 hash 变化才 `source_version +1` 并把 `index.lexical` 标 `stale`；仅 stat 变化不算新版本 | `test_source_version_increments_only_on_content_change` |
| 部分失败 | 回执逐文件如实 `failed`/`searchable=false`，失败不造成功正文 | `test_partial_failure_receipt_is_honest` |
| 取消/重启可复现 | `cancel` 未确认 → `cancellation_unconfirmed`（409）且保持 `queued`；确认后写 `cancelled`；重启扫描把 `running` 作业置 `recovery_required`（不自动重放）；torn JSONL 截断修复 | `test_cancel_requires_confirmation`、`test_running_job_is_not_auto_replayed`、`test_restart_marks_running_job_recovery_required`、`test_torn_receipt_tail_is_repaired_on_restart` |
| 先持久化原件再开始提取 | 先写 `sources/<id>/original/<name>`（原子+锁），再建 source/job；状态诚实停在 `received`/`extracting` | `test_workspace_path_intake_persists_original`、`test_rebuildable_state_matches_files`、`test_state_is_rebuildable_from_files_only` |
| 拒绝越界路径与未授权来源 | `..`/绝对路径/逃逸符号链接 → `path_outside_workspace`（403）；`resolve_path` 唯一收口 | `test_path_escape_and_symlink_escape_refused` |
| 外部正文不获得执行权限 | 上传 md frontmatter（伪 task/phase/enable_subagents）仅作为数据落盘，不产生 Task/Run，不改变实体执行字段 | `test_uploaded_frontmatter_grants_no_execution_permission` |
| 摄取不启动交付 Run/团队 | 全流程无 coordinator/queue 调用；测试断言 `/tasks` 为空 | 上述各例 |

## 3. 实际命令与结果（本机，真实运行）

| 命令 | 结果 |
|---|---|
| `uv run mypy` | `Success: no issues found in 97 source files` |
| `uv run pytest tests/sources -q` | `21 passed` |
| `uv run pytest tests/api tests/contracts tests/store -q` | `134 passed` |
| `uv run pytest -q`（全量后端） | `503 passed, 4 skipped, 1 warning in 69.34s` |

测试均为**真实的 HTTP + 真实 FileStore + 真实 app 生命周期**（httpx ASGITransport
驱动 `create_app` 并按集成方式 `include_router(build_sources_router(), prefix=...)`），
不是孤立 helper 单测。事件断言读取真实事件日志（`source.received`、
`intake.stage_changed`）。

## 4. 关键语义（与冻结契约一致）

- 幂等键是稳定接入 `request_id`，不是“同一 URL 永远跳过”；同 key 异 payload →
  `source_conflict`。
- 去重只在**同一作用域（task_ref / global）**内按内容 hash 识别；跨 Task/来源**不合并**，
  不共享授权（去重映射按 scope 分目录）。
- `content_hash`（内容）与 `stat_revision`（写入令牌，非密码学哈希）严格区分。
- 取消需确认停止；未知副作用中断不自动重放（`retry` 对 `running`/`recovery_required`
  返回 `illegal_transition` 并保持 `recovery_required`）。
- 文件是唯一事实源；请求映射与去重映射为**可重建缓存**（测试删缓存后仅凭文件重建）。
- 收件区/原件路径经 `resolve_path` 授权；越界一律 403。

## 5. 真实/替身说明

- 产品真实模型调用 **0**；外部服务调用 **0**；未下载模型；未启动产品服务。
- 本包无 OCR/向量/Chat UI，符合 LG-034 范围（后续 LG-035/036/037/038）。
- 测试中的 Task 由真实 `POST /api/v1/tasks` 创建（真实协调器/Store），非 mock。

## 6. 限制与未知

- **未完成 `api/app.py` 最终装配**：`create_app` 默认返回的 app **尚不含**
  `/api/v1/sources*` 与 `/api/v1/intake/*`、`/api/v1/inbox/messages`。本包通过
  在真实 app 上手动 `include_router` 完成等价接线与 HTTP 验证，最终一行装配归
  集成 owner（`INTEGRATION.md`）。**装配前不得宣称这些端点在产品默认 app 可用。**
- **`project_ref` 无注册表**：项目归属当前如实拒绝（`reference_invalid`），不伪造
  项目权限；项目注册表属后续任务/设计。
- **无提取/索引/向量**：`status` 诚实停在 `received`（未跑 LG-035 时不会进入
  `extracted/indexed`），`index.lexical=not_indexed`、`searchable=false`、
  `index.vector=disabled`。不假正文结果。
- **HTTP 安全策略**：沿用全局 `require_access`（loopback 默认可用）；本包不新增
  敏感前缀。若后续要求资料写接口也按敏感处理，属集成/安全决策。
- 单进程内服务实例缓存在 `app.state.source_service`；跨进程并发由 LG-004 flock 与
  原子写保证，未做分布式锁（符合单机首版边界）。
- 未运行：前端构建、浏览器端到端（LG-021/022/LG-040）、真实 OCR/检索质量。
- pi 开发 token/费用未知，未计量。

## 7. Git

- 仅本地提交，**未 push / 未 merge**。旧 worktree、分支与原始证据保留。
