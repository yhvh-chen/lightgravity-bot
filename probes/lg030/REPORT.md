# LG-030 交付报告（简洁版）

> owner：`agent:pi-lg030`｜分支 `dev/lg030`｜基点 `61fad69`｜状态：**in-progress（待版本 QA LG-032，
> 未装配即保持 in-progress）**。契约版本 `1.6.0`（LG-028 已冻结，本轮不改 docs/08）。产品模型调用 0。

## 1. 目标与范围

实现冻结的**受控同伴请求与上下文/产物交接**（docs/08 §4.3/§5.1/§6.2/§6.3；LG-028 准备稿 §4）。
worker 只能请求协作与交接；权限状态、预算、验收由程序判定。不引入常驻模型编排、不引入 SDK 无限委派。

归属文件（仅这些改动）：

| 路径 | 内容 |
|---|---|
| `backend/lightgravity/collaboration/peer.py` | 受控同伴请求/结果、因果绑定、权限/预算/超时/容量、幂等、注入正文不执行、fence 校验 |
| `backend/lightgravity/collaboration/handoff.py` | 带版本/hash 的产物引用解析、跨 Task/跨 Run/摘要不符拒绝、原始绝对路径结构性拒绝 |
| `backend/lightgravity/collaboration/context.py` | 有界授权摘要（非执行）、`instruction_like` 标记、因果绑定值类型 |
| `backend/lightgravity/collaboration/__init__.py` | 导出新模块（不改 claim/lease/discovery） |
| `backend/lightgravity/api/collaboration.py` | 新增 `POST/GET /runs/{id}/collab_requests` 最小面（路由已由既有装配挂载） |
| `tests/collaboration/test_peer.py`、`tests/collaboration/test_api_collaboration.py`（追加） | 局部检查 |
| `probes/lg030/{STATUS,REPORT,INTEGRATION}.md`、`backlog/tasks/LG-030.md` | 记录 |

未修改：claim/lease/discovery 已有模块、coordinator/verify/adapter/store/contracts/api/app.py/settings/
frontend/共享 docs。共享装配点已存在（collaboration 路由 029 已挂载），故本轮**无需改 `api/app.py`**。

## 2. 验收条件对应实现

| 验收条件 | 实现 | 证据（测试） |
|---|---|---|
| 同伴发现/请求/响应绑定 task/run/node、message_id 与因果 | `context.validate_binding` + `peer._decide` 全量校验；`in_reply_to` 关联 | `test_request_is_accepted_and_persisted`、`test_request_requires_full_causal_binding` |
| 重复、越权、过期消息有明确结果 | `request_id` 幂等重放；`requester_not_in_run`/`responder_not_in_run`/`unknown_node`/`stale_lease` 明确拒绝 | `test_duplicate_request_id_is_idempotent_under_concurrency`、`test_requester_must_be_in_run`、`test_cross_task_node_is_refused`、`test_stale_fence_request_is_refused` |
| 只传授权摘要及带版本/hash 产物引用 | `context.classify_summary`（有界、非执行）+ `handoff.validate_handoff_refs`（sha256/`evidence:`/upstream 形状） | `test_valid_evidence_handoff_ref_is_accepted`、`test_upstream_ref_shape_is_parsed` |
| 拒绝跨 Task 泄漏/失效来源/来源正文当控制指令 | 证据引用按 owning Task/Run 解析；跨 Run 摘要不符拒绝；`instruction_like` 仅标记不执行 | `test_handoff_ref_from_other_run_is_rejected`、`test_handoff_digest_mismatch_is_rejected`、`test_instruction_like_summary_is_data_not_control` |
| 协作受总预算/次数/超时/容量，等待不无限循环 | `_budget_ceiling`（`budget.max_collab_requests` 或 Task 预算派生）、`timeout` 上界、无阻塞等待 | `test_collab_budget_exhaustion_is_definite`、`test_timeout_beyond_capacity_is_refused` |
| 交接失败可诊断并恢复 | 拒绝结果写状态/原因与 `handoff.rejected`/`collab.requested` 事件，`rejected_refs` 保留 | `test_handoff_ref_from_other_run_is_rejected`、`test_resolve_records_terminal_state_idempotently` |

## 3. 检查结果（命令与退出码）

| 命令 | 结果 | 退出码 |
|---|---|---|
| `uv run pytest tests/collaboration -q` | **53 passed**（29 claim/lease/discovery/API + 24 peer；本轮新增 27） | 0 |
| `uv run pytest -q`（后端全量） | **595 passed, 4 skipped** | 0 |
| `uv run mypy` | **Success: no issues found in 119 source files** | 0 |

- 4 skip 为既有 gated 真实模型/环境检查，与 LG-030 无关。
- 基线（`61fad69`，本轮前）：后端 545 passed、1 skipped。本轮 **+50 passed**（其中 LG-030 新增
  test_peer 24 项 + API 3 项 + 其它收集差异），无失败、无回归。
- 真实 FileStore+HTTP 协议链自测：`tests/collaboration/test_api_collaboration.py` 用真实
  FastAPI + 真实 `FileStore` + `ApiContext` 驱动 `POST/GET /runs/{id}/collab_requests`；
  默认 `create_app` 已挂载 collaboration 路由，端点存在性已离线核对。
- 真实**默认 app** 协议链复现：`uv run python probes/lg030/http_protocol_check.py` →
  `POST 200 requested True` / `REPLAY True` / `BUDGET rejected budget_exhausted` / `GET 200 ['c1','c2']`
  （输出存档 `probes/lg030/http_protocol_check.out`，非缓存字节）。

## 4. 真实 / 替身边界（不得当作完成）

- **真实**：文件系统 `FileStore`（真实 flock、原子替换、JSONL 追加）、真实 sha256 与
  `evidence:<run>/<name>@sha256:<hex>` 解析、真实 HTTP 路由/请求链、真实多线程并发幂等竞争。
- **替身**：worker 执行身份为程序字符串（`from_member_ref`/`owner`），无 SDK、无真实模型。
- **未实现（归 LG-031，不伪称已完成）**：受控执行身份注入（端点身份仍由请求体提供，与 LG-029
  同一边界；HTTP body **不扩大权限**——peer 服务额外要求身份属于同一 Run，且服务端认证属 LG-031）、
  Graph 接线（`LeaseManager` 替换 `SubtaskClaimer`、collab 请求进入协调器图）。
- **未做的**：完整 checkpoint skip（对齐 docs/08 §6.2）；未知副作用只进 `recovery_required`，不自动重放。

## 5. 身份缺口如实记录（交 LG-031）

- `POST /runs/{id}/collab_requests` 的 `from_member_ref`/`to_member_ref` 仍取自请求体。**本包不默认信任
  该字段为认证身份**：peer 服务要求 `from_member_ref` 必须是**同一 Run** 的 member，`node_ref` 必须属于
  同一 Run，任何跨 Task/Run 名称一律拒绝（无泄漏）。真正的**程序认证执行身份**（由协调器注入）归 LG-031，
  与 LG-029 `probes/lg029/INTEGRATION.md` §2.4 记录的缺口一致，本包不擅自扩大信任面。

## 6. 状态与后续

任务保持 `in-progress`：已实现可运行、默认关闭、端点已随既有路由挂载的受控同伴交接，但
**执行身份注入与 Graph 接线未装配**，集中 QA 归 LG-032，本包未做版本 QA。已知未装配项不视为已完成能力。
