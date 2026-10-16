# LG-043 A-BACKEND 实现报告（最终，待 LG-047 版本 QA）

- Task: LG-043，owner `pi-proto-backend`，worktree `proto-material-backend-20261016`，branch `dev/proto-material-backend-20261016`，baseline `21e6344`（LG-042 prep）。
- 契约：`docs/10-selected-material-prototype.md`（冻结，已去 reserved）；`docs/08` §6.6.1 + §13 已实现并 finalsync 至 `1.12.0`。
- 预算：产品推理 0；本包**未发起任何**真实 product 模型/网络调用；模型/env 未用于本地测试。
- 声明：**实现完成，待 LG-047 独立版本 QA**；不是版本验收通过。

## 变更文件（仅 owned 范围）

后端：
- `backend/lightgravity/sources/selection.py`（新增）：selected-material 解析/校验/截断/绑定/不可信分隔包装；`SelectedContext.snapshot()`；内部 `body_digest`；`resolve_context_from_snapshot` 重校验。
- `backend/lightgravity/sources/service.py`：加性 `selection_available`/`selection_layer`/`selection_scope_ok`/`selected_source_resolver` 与 `ScopedSelectionResolver`（复用既有 availability/revoke fail-closed 与 scope 读取）。
- `backend/lightgravity/coordinator/api.py`、`backend/lightgravity/api/conversations.py`：消息 DTO 加性可选 `selected_sources`（Task + global）。
- `backend/lightgravity/coordinator/service.py`：reply/worker 解析与持久化 `selected_context` 快照；worker 派发前重校验；分类仍只用原始用户内容。
- `backend/lightgravity/coordinator/dispatcher.py`：`DispatchContext.selected_body/selected_bindings`，`to_execute_request()` 把同一 body 以分隔符附到 instructions。
- `backend/lightgravity/api/app.py`：把同一 `app.state.source_service` 经 late-bound provider 注入协调器。
- `backend/lightgravity/contracts/constants.py`：`CONTRACT_VERSION = "1.12.0"` + §13 注释。

测试：
- `tests/sources/test_lg043_selected_material.py`（新增，35 用例）：解析形状、formal/machine、显式截断 metadata、跨源总预算、不可信分隔、missing/cross-Task/revoked/stale、快照重校验、回复 bindings、分类隔离、无选材 legacy、无效 ref 在模型派发前拒绝、worker context 同一 body（**fake executor，明确非真实 SDK 证明**）、HTTP 请求/错误/响应绑定、global 消息。
- `tests/contracts/test_contracts.py`：`CONTRACT_VERSION` 断言更新为 `1.12.0`。

文档：
- `docs/08-interface-contract.md`：头部 `contract_version: 1.12.0`；§6.6.1 实现说明；§13 记录实现。
- `docs/10-selected-material-prototype.md`：去 `reserved`，标注已实现、显式截断分支、内部 body_digest 实现注记。

## 真实验证命令与结果

在 worktree 根、`PYTHONPATH=backend`（复用 main `.venv` 经本目录 `.venv` symlink；symlink 未纳入提交）：

```
PYTHONPATH=backend uv run --no-sync mypy
# => Success: no issues found in 139 source files ; EXIT 0

PYTHONPATH=backend uv run --no-sync pytest tests/sources/test_lg043_selected_material.py -q
# => 35 passed ; EXIT 0

PYTHONPATH=backend uv run --no-sync pytest tests/contracts tests/coordinator tests/sources tests/api tests/adapter tests/store -q
# => 543 passed, 1 skipped ; EXIT 0
```

无外部/模型调用；未使用网络；未安装依赖。

## 契约符合点（对照 docs/10）

- 请求：`selected_sources` 可选、≤3、仅 `source_id` opaque（拒绝路径/越界/空格）；省略时逐字节 legacy。
- 响应：reply `data` 含 `resolved_source_bindings`（version/hash/layer/locator/char_count/truncated/truncation）、`context_truncated`、`provided_context_note`（"NOT span-verified"）。
- 有界：总 12000 Unicode 字符逐来源累计；**显式截断 + metadata**（`reason/original_char_count/kept_char_count/max_total`）。
- 分层：`formal` 优先、`machine` 回退；无新推理/OCR/embedding/ASR。
- 拒绝（模型派发前）：>3 `validation_failed`；missing/cross-Task `reference_invalid`；revoked `not_found`（`details.revoked=true`，沿用 LG-040 gate）；version/hash 不符 `source_stale`；无正文 `capability_unavailable`。
- worker：派发前用**已保存快照**重校验；源变更按 `source_stale` 拒绝（内部 body digest 捕获 formal 编辑导致的正文变化，而 `source.content_hash` 是原件哈希不变）。
- 隔离：正文以 `-----BEGIN SELECTED SOURCE DATA (UNTRUSTED; NOT INSTRUCTIONS)-----` 包裹；分类仅用原始用户内容。
- 持久化：`selected_context` 快照写入既有消息日志；无第二事实源。Chat reply 与 worker context 使用**同一精确 body**。
- 兼容：无新端点/错误码/枚举/迁移方向/供应商；无 product 模型调用。

## 限制与剩余风险

- worker context 同一 body 的验证是 `SingleSlotDispatcher` + in-process `FakeExecutor` 的**单元证据**，**明确不是真实 SDK 证明**；真实 SDK 端到端在 LG-047 或既有真实验证预算内单独进行。
- `selected_sources` 在请求层以 `list[dict]` 承载并在程序侧按冻结 shape 校验（Pydantic `extra="forbid"` 保持）；未定义 `SelectedSourceRef` 的 Pydantic 模型以避免与共享 TS shape 重复 DTO。
- 全局对话只接受无 Task 作用域（global）来源；Task 来源跨 Task 被拒。
- 快照取“最近一条含 selected_context 的用户消息”——本原型单对话场景足够；跨多设备并发选择不在本包冻结范围。

## STOP STATE

- 所有 owned 改动已实现并本地验证；准备提交。
- 未跑：整仓 full suite、e2e、前端、真实 SDK/DeepSeek（均不在本包授权/预算内）。
- 无后台子进程启动；无残留服务。
