# LG-031 phase4 — 离线硬门证据（真实调用前）

owner：`agent:pi-lg031-r3`；branch `fix/lg031-r3` @ `faacb90`；日期 2026-10-16。
全部为**零模型/零网络**的离线证据（真实调用前必须先全绿）。

## 1. 全 stage 硬限（持久账本跨进程/重启、损坏不当 0）

命令：`uv run python /tmp/ledger_check*.py`（离线 scratch，详见下方退出事实）

| 检查 | 结果 |
|---|---|
| 初始账本 | `count=0, limit=16, remaining=16, corrupt=false, persistent=true` |
| 本进程预留 5 | `count=5, remaining=11` |
| 子进程（独立进程）读到 | `count=5, remaining=11`（**不归零**），再预留 3 → `count=8` |
| 第三读（模拟重启） | `count=8, remaining=8`（**不归零**） |
| 损坏权威 `generation/generation.jsonl` | `count=None, corrupt=true, reason='history line 1 is not valid JSON'`；`GenerationCounter.count == -1`；`reserve() == False`（**拒绝转发，绝不当 0**） |
| 缺失账本目录 | 全新 `count=0, remaining=16`（合法空账本） |
| 快照 `generation.count.json` 损坏但 history 有效 | 由 history 重建（`max(history, snapshot)`），不归零 |

请求参数固定：每请求输出 ≤12000 tokens；单 HTTP ≤120s；并发 ≤1（本探针串行）；SDK/API retry 0。

## 2. 两 worker 权限（body 永不认证、越权/预算确定拒绝）

既有 phase3 集成证据 + 本包回归：`tests/collaboration/test_lg031_integration.py`
（11 项，含身份伪造 body 不作认证、越权节点 `node_not_scheduled_for_worker` 拒绝、
过期≠停止、旧 fence 写入拒绝、竞争一个赢家）。
本包新增真实 planner 闭包（下 §6）再次证实：每个 candidate 的 claim receipt 为
`granted/fence=1`，`json.dumps(receipt)` **不含 token**。

## 3. 节点 objective 明确（G2 回归）

`tests/collaboration/test_lg031_r3_product_path_closure.py` 与
`tests/collaboration/test_lg031_r4_real_planner_closure.py` 均断言 discovery 投影携带
程序拥有的 `objective`（与 `write`）；worker 据 objective（**非 slug**）判定其产物。
真实 planner 下 key 为 `deliver`/`verify` slug，objective 才是产物路径来源。

## 4. 依赖交接（程序带 hash）

`test_lg031_r4_real_planner_closure.py` 断言依赖节点收到
`<subtask>@sha256:<64-hex>:<artifact>` 形式的 versioned+hashed handoff。

## 5. 真实产品 bootstrap & Graph 配置（G1 回归）

`tests/startup/test_lg031_r3_bootstrap_autonomous.py`（2 项）：
- 开关缺省/关闭 ⇒ `GraphDispatcher._autonomous_claim is False`、`_grant_registry is None`
  （旧确定性路径，无工具、无 grant）。
- 开关开启（经真实 `ConnectionService.update_settings`）⇒ `_autonomous_claim is True`、
  `_grant_registry is default_registry()`、`_collaboration.enabled is True`。
- 加性消费上限对齐：`tests/adapter/test_lg031_r3_generation_ceiling_alignment.py`（5 项，见 §7）。

## 6. 产品路径闭环（确定性 sim，真实 planner，无模型）

`tests/collaboration/test_lg031_r4_real_planner_closure.py`（1 项，新增）：
**不注入 planner**，真实 `RuleBasedPlanner` 产出 `deliver`（write）→ `verify`（依赖）；
2 个 worker 各自自主 discover→claim（`granted/fence=1`、脱敏）；`deliver` 在**独立真实
git worktree**（`ws != base`）写出 `out/deliver.txt`；`verify` 收到带 64-hex 的 handoff；
`registry.active_grants() == []`（身份不超执行存活）。

## 7. phase4 最小产品修复（上限对齐，离线先证）

**失败点**：phase3 里 SDK `BudgetConfig.max_model_calls` 与 loopback proxy `max_proxy_calls`
是**两个独立上限**；当 proxy 先耗尽时返回不透明 429，掩盖 SDK 的真实停止原因，多步 worker
在写入前被杀。

**最小修复（加性）**：`backend/lightgravity/adapter/executor.py` 的 `execute()` 在创建 proxy 时，
把 per-session 上限对齐到 coordinator 冻结的 per-request `budget.max_model_calls`
（取 `min(max_proxy_calls, remaining_cap, request_model_calls)`）；请求未设 model budget 时
行为完全不变。测试 `tests/adapter/test_lg031_r3_generation_ceiling_alignment.py`（5 项，全绿）：
- 请求 `max_model_calls=3`、构造上限 64 ⇒ proxy 实际上限 **3**；
- 构造上限 2、请求 10 ⇒ proxy 上限 **2**（最小值语义）；
- 无 model budget ⇒ 构造上限 **7** 不变（加性）；
- 非法值（字符串）⇒ 不放宽，保持 **9**。

## 8. 全量/局部命令（真实退出码，本包执行）

| 命令 | 结果 |
|---|---|
| `uv run mypy` | **Success: no issues found in 137 source files** |
| `uv run pytest tests/adapter -q -p no:randomly` | **102 passed** |
| `uv run pytest tests/collaboration -q -p no:randomly` | **77 passed** |
| `uv run pytest tests/coordinator -q -p no:randomly`（与 collaboration 同批） | **187 passed**（collaboration+coordinator） |
| `uv run pytest tests/startup -q -p no:randomly` | **39 passed, 4 skipped** |
| `uv run pytest tests/settings -q -p no:randomly` | **46 passed** |
| `uv run python -m py_compile probes/lg031/phase4/real_worker_closure_probe.py` | OK |

> 4 个 startup skip 为条件门（真实 DeepSeek 需显式 env / 真实前端 dist），非回归。

## 结论

离线硬门 1–7 **全绿**，真实调用前的接线、权限、objective、交接、bootstrap/Graph 配置均已
离线证实。真实调用（§B 单次尝试）随后进行，结果见 `REPORT.md` 与 `evidence/`。
