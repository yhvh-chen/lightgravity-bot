# LG-031 STATUS

owner: `agent:pi-lg031`
branch: `dev/lg031`
base commit: `e4cef4a`

## 状态

实现完成，**待版本 QA（LG-032）**；本包不自评整体 pass。默认确定性调度路径保留，
新增去中心化执行/身份/复核接线**默认关闭、可回退**。

## 已交付（真实代码）

- `backend/lightgravity/collaboration/execution_grant.py`（新增）：
  程序冻结的不透明 execution grant（进程内、非持久、非全局管理 token）、
  受限同伴请求工具 `make_restricted_peer_tool`、HTTP 身份解析
  `resolve_worker_identity`（仅读 `X-LG-Execution-Grant`，永不读 body）。
- `coordinator/graph.py`：`collaboration`/`grant_registry` 加性注入；开关开启时
  经 fenced `CollaborationService` 领取节点（能力/依赖/预算/可发现性程序检查）、
  按节点冻结 grant、绑定受限同伴工具；停止即回收（revoke）；开关关闭时完全走原
  `SubtaskClaimer` 路径且不附加自定义工具。
- `adapter/execution.py`、`adapter/sdk_config.py`、`adapter/executor.py`：
  `ExecuteRequest.execution_grant`/`custom_tools` 加性字段，经 SDK `tools=` 注入
  进程内受限工具（`enable_subagents` 仍为 false）。
- `settings/{models,repository,service,router}.py`：三个去中心化开关的读写路径
  （缺省/非法回落关闭；未提供字段保留当前值）；`_write_settings_content` 保留开关。
- `api/app.py`/`api/bootstrap.py`：`worker_identity` 接线、`CollaborationService`
  装配、`create_app(..., worker_identity=...)`——真实身份由**程序**注入。
- `docs/08`（本包 owner）：§4.3 状态与 §6.5 实现说明（加性、无字段/端点/版本变化）。

## 检查（真实退出码）

- `uv run mypy` → **Success, 125 files**。
- `uv run pytest -q` → **665 passed, 4 skipped**（连续两次一致）。
- 新增 LG-031 测试：`tests/collaboration/test_lg031_integration.py`（11）、
  `test_lg031_real_workers.py`（3，真实 Git worktree/合并/冲突）、
  `tests/coordinator/test_lg031_review_closure.py`（3）、
  `tests/settings/test_lg031_switches.py`（4）。
- 真实模型探针：`probes/lg031/review_real_probe.py` → **1 次真实 DeepSeek 调用**，
  `reviewer_kind=model`、`outcome=passed`、`validated_outcome=passed`、
  `usage={"unknown":["usage"]}`（未知计 unknown，不当 0）。

## 未达成 / 缺口（不伪称）

- 完整 checkpoint skip 未实现（沿用既有边界）。
- 真实 SDK worker **进程内注入**受限工具已接线，但真实 SDK 端到端多 worker 运行
  归 LG-022/LG-032；本包用的是真实 Git + 进程内 fake executor。
- 独立集中版本 QA（LG-032）未做，成本对比也未做。
- 已知非本包缺陷：`tests/collaboration/test_claims.py::test_two_owner_race...`
  在完整套件中偶发被判 `not_discoverable`（既有 discovery/lease 原因竞争），
  单跑与连续两次全量均通过；未修改该已验收 LG-029 测试语义。
