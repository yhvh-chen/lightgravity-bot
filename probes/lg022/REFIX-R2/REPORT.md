# LG-022 第二轮针对性返修（REFIX-R2）— REPORT（原 owner 等价续接收尾）

- Owner：`agent:pi-lg022-r2`（pi + env DeepSeek；主代理只 PM，**无嵌套派工/推送/部署/发布**）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-r2`（branch `fix/lg022-r2`）。
- 输入：独立 QA 复验 R1 `qa/lg022-r1` @ `6228474` 的 `probes/lg022/reverify-r1/REPORT.md`（判定 **FAIL**）；本包 `PLAN.md` / `STATUS.md`。
- 前序上下文：上一原始进程（`bounded-lrc7m73u`）到 **140 轮上限**退出（`stop_reason=max_rounds_reached`，`side_effects_unknown=true`，`rounds=140`，非缓存 185,961 tokens）；末尾正在做契约 `1.9.0 → 1.10.0` 升级且**已落盘** `constants.py`/`tests/contracts`，但**未**跑验收、未写 REPORT、未 commit。本续接**不盲目重放**、不重做已完成的 A/B 代码与测试、不重跑 031/真实 phase6；只核必要未完成项（doc 一致性、新测试实跑、REPORT、commit）。
- **本包产品真实模型调用 0**（全部本地替身/确定性测试；未重放任何真实请求）。独立真实复验另派。
- LG-022 仍 **`in-progress`**；本包**不自判 pass**，须新独立 QA 复验。

## 0. 本续接判定（一句话）

两个目标 A/B 的产品代码与新增测试均已完成，本续接补跑新测试（发现并修正 1 处测试自身时序替身缺陷）、同步 `1.10.0` 契约文档、跑 mypy + 局部回归 + 一次全量 `pytest`（全绿）并精确本地 commit。
**A、B 的验收可达性由本地确定性测试证明；未在真实模型链上复验**，故只报“代码完成 + 本地证据”，不宣称成功门 pass。

## 1. 目标 A：session_refs 非空的真实形态资源成功链

### 1.1 实现（已完成，本续接未重做）

- `adapter/execution.py`：新增 `StopConfirmation` 事实类型（`confirmed` 仅在每个 session 均被证明关闭且 proxy 已停时为真）+ `ResourceStopConfirmer` 端口。
- `adapter/executor.py`：`_ExecutionHandle.ensure_closed` 仅在 `Agent.__aexit__` 真正成功后才置 `closed=True`（失败保持未关闭，不伪成功）；`AntigravityExecutor` 记录 `_closed_sessions`（session_id→run_id）与 `_proxy_stopped_runs`，并实现 `confirm_stopped(run_id, session_refs)`（in-flight/缺失/unclosed ⇒ unknown ⇒ `confirmed=False`）。
- `verify/stopgate.py`：`StoreResourceStopper` 增加可选 `session_confirmer`（`SessionStopConfirmer` 端口）；`sessions_stopped = not session_refs or cleanup=="done"` **或** 权威 `confirm_stopped` 事实为 `confirmed`；reviewer 资源另有事实门（`run.reviewer_cleanup.confirmed is True`）。
- `verify/rework.py` + `verify/review.py`：reviewer 真实 teardown 事实经 `ReworkResult.reviewer_stop_fact` 暴露；`coordinator/service.py::_record_reviewer_stop` 持久化到 `run.reviewer_cleanup`（`status=done` 仅当 `confirmed`）。
- `api/app.py`：`create_app` 在注入 `executor` 且其具有 `confirm_stopped` 时自动构造带 `session_confirmer` 的默认 `StoreResourceStopper`。

**不变量**：`session_refs` **从不删除**；`cleanup` 不被伪造为 `done`；unknown/仍活跃/close 失败 ⇒ 保持 `unconfirmed`（hold）。

### 1.2 本续接实跑与修正

新增测试 `tests/verify/test_lg022_r2_stopgate_resources.py`（4 项）、`tests/coordinator/test_lg022_r2_resource_chain.py`（3 项）。

- 实跑发现 `test_session_bearing_run_reaches_acceptance_via_real_stop` **失败**（停在 `verifying`）与 `test_open_session_keeps_run_unconfirmed` 反例**误通过**。根因是**测试替身缺陷**（非产品缺陷）：替身 dispatcher 在 `dispatch` 返回后才异步关 session，而真实 `AntigravityExecutor` 在 `execute` 的 `finally` 中**先关后返回**，verification 因此看到已关闭。替身时序与真实不符，导致成功例竞争失败、失败例被无条件关闭。
- 修正：`SessionRecordingDispatcher` 增加 `close_on_dispatch` 开关，**成功例在 dispatch 返回前关闭 session（模拟真实 finally 顺序）**；反例保持 session 常开。修正后 7 项全绿（见 §5）。
- 未改任何产品代码（产品 A 实现经核无缺陷）。

### 1.3 停止证明来源

真实停止事实来源 = 适配器 `AntigravityExecutor.confirm_stopped`：`Agent.__aexit__` 成功记录的 `_closed_sessions` + `_stop_proxy` 成功记录的 `_proxy_stopped_runs`。测试中由 `_StopConfirmer` 按“session 是否 open”镜像该事实；**未触碰真实模型/网络**。

## 2. 目标 B：GenerationCounter 受控 dataRoot 持久账本

### 2.1 实现（已完成，本续接未重做）

- 新增 `backend/lightgravity/adapter/generation_ledger.py`：`PersistentGenerationLedger`
  - **文件 SoT**：append-only `generation.jsonl`（每条含 `kind`（`reserved`/`forwarded`）、`count`、`reserve_id`、`pid`、`ts`）+ 可重建原子计数快照 `generation.count.json`；读取取 `max(history, snapshot)`，撕裂写不会少计。
  - **转发前持久预留**：`reserve()` 持跨进程 `LockManager`（key `generation-budget`）→ 读当前 → 未超限则 append 预留 + fsync + 原子写快照 → 返回 `LedgerReservation(granted,...)`。
  - **损坏不当 0**：不可读/非法 JSON/负值/非法快照 ⇒ `GenerationLedgerCorrupt` ⇒ `reserve` 拒绝（`granted=False, corrupt=True`）；`count()` 在 `GenerationCounter` 层损坏时返回 `-1` 表示 unknown。
  - **只最小元数据**：不写输入/prompt/header/凭证/grant。
- `adapter/proxy.py`：`GenerationCounter(limit, ledger=...)` 委托账本；`snapshot()` 加性 `persistent`（持久账本 `True`）及损坏时 `corrupt`/`reason`；`_default_generation_counter()` 从 `ledger_root_from_env()` 建账本；新增 `configure_generation_ledger(root, limit)`。
- `api/bootstrap.py`：`build_runtime` 启动时 `configure_generation_ledger(settings.data_dir)`——**受控 dataRoot 注入**，proxy 启动前配置，跨 worker/reviewer/session/重启同一事实源。
- **账本路径**：`<data_dir>/generation/generation.jsonl`、`<data_dir>/generation/generation.count.json`（`_LEDGER_SUBDIR=("generation",)`）。测试/运维可用 `LIGHTGRAVITY_GENERATION_LEDGER_DIR` 覆盖，`LIGHTGRAVITY_DATA_DIR` 为回退。

### 2.2 本续接实跑

新增 `tests/adapter/test_lg022_r2_generation_ledger.py`（7 项，含 `test_two_processes_share_one_ledger` 真子进程、`test_corrupt_ledger_is_never_zero`、`test_ledger_writes_only_counts_no_inputs`）——全绿。`tests/api/test_health.py` 断言加性 `persistent`。未改产品代码。

## 3. 安全收编与原证据保全（未回退）

- `probes/lg022/evidence/r1-review-lifecycle.json`：工作树已恢复 **R1 原始字节**（sha256 `9853bca4dc67…`，与 `d07a4a6` 一致）；QA 刷新版（sha256 `feb2d1e49be0…`）另存于 `probes/lg022/reverify-r1/evidence/r1-review-lifecycle-refreshed.json`。两版本均可核、未 `reset`/`restore` 覆盖。
- 旧 `1.9.0` 来源/可逆归档/search/vector 描述全部**保留**（文档以“此前 …1.9.0…”链式追加，不覆盖）。旧 `refs`/候选/pin/token/预算/恢复反重放语义未改。

## 4. 契约与文档一致性（本包唯一 owner）

- 契约 `1.9.0 → 1.10.0`（加性 MINOR）：`backend/lightgravity/contracts/constants.py`、`tests/contracts/test_contracts.py`、`docs/08`（frontmatter `contract_version`、§0 版本说明、§4.3 端点行、§9 账本说明、§13 变更表、检查清单）。
- `README.md`、`PROJECT.md`、`agent.md`、`docs/06-roadmap.md` 同步 `1.10.0` 并保留历史版本链。
- **未新增端点/枚举/迁移方向/错误码**；`1.10.0` 仅加性字段（`run.reviewer_cleanup`、诊断 `persistent`/`corrupt`/`reason`）与停止门事实来源。

## 5. 实际命令 / 退出码 / 未测

| 命令 | 退出码 | 结果 |
|---|---|---|
| `.venv/bin/python -m pytest tests/verify tests/coordinator tests/adapter/test_lg022_r2_generation_ledger.py tests/adapter/test_lg022_generation_budget.py tests/contracts tests/api/test_health.py -q` | 0 | 200 passed |
| `.venv/bin/python -m pytest -q -p no:randomly`（全量一次） | 0 | **765 passed, 5 skipped**, 76.19s |
| `.venv/bin/mypy <9 个改动后端模块>` | 0 | Success: no issues found in 9 source files |
| 新 A 测试首跑 | 1 | 1 failed（**测试替身时序缺陷**，见 §1.2）→ 修正后 green |

**未测 / 须独立 QA 覆盖**：

- **A 未在真实模型链验证**：`awaiting_acceptance` 可达性仅由本地确定性替身证明；真实 DeepSeek 成功 Run（`session_refs` 非空、`cleanup=pending`）→ `awaiting_acceptance` 待独立真实复验（本包真实调用 0）。
- **B 跨重启真实服务验证**：持久化由真子进程单测 + 注入路径覆盖；未做真实 `lightgravity start` 两次重启的端到端计数核对、未做真实共享 proxy/worker/reviewer 出站硬 cap 的并发实测。
- 未测 `reviewer_cleanup` 在真实 reviewer SDK teardown 故障（`__aexit__` 抛错）下的端到端 hold 行为。
- `-p no:randomly` 已用于全量以避免已知随机序 race flake；未反复 stash 复跑。

## 6. 提交 HEAD 与后续独立 QA 最小清单

- 本包 commit：见 `git log -1 --format=%H`（branch `fix/lg022-r2`）；仅本包归属改动，无 secrets，保留 `main`/旧 031 dirty/所有 worktree 与原始日志。
- 独立 QA 最小清单（建议）：
  1. 真实（非替身）成功 Run 到 `awaiting_acceptance`：确认 `session_refs` 保留、`cleanup` 未伪 `done`、停止门经适配器事实放行；关闭失败的 session 仍 hold。
  2. 真实重启两次进程：`GET /api/v1/diagnostics/generation` 的 `count` 不归零、`persistent=true`；手工损坏 `<data_dir>/generation/*.json*` 后 `count` 报 unknown/`corrupt` 且**拒绝**转发（不当 0）。
  3. 跨 worker/reviewer 共享出站硬 cap：`limit=N` 时第 N+1 次预留被拒。
  4. 复核 `reviewer_cleanup` 只在真实 reviewer teardown 事实存在时写 `done`。
  5. 契约 `1.10.0` 与 docs/08/README/PROJECT/agent/docs06 一致，旧 1.9 链未回退。

## 7. 预算

- 本续接产品真实模型调用 **0**；未重放任何旧 phase6/031 试验；API 重试 0。
- 未修改 `sources/frontend/collaboration` 非必要自治逻辑；未回退 search/vector/可逆归档。
