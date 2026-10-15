# LG-022 独立复验 R1 — REPORT（决定性收尾）

- 复验 owner：本包（pi + env DeepSeek 配置；主代理只 PM，无嵌套派工/push/deploy）。
- 复验 worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-r1`（branch `qa/lg022-r1`）。
- 开工 HEAD：`ec2420e`（= 整合候选 `9698e8a` + QA scaffold；产品树 == `9698e8a`）。
- 候选产品：`integrate/batch6` @ `9698e8a`，契约 `1.9.0`（门相关为 `1.8.0` 加性：review 生命周期 + 全局生成计数诊断）。
- 输入：`PLAN.md`（冻结输入/门/预算）、`../REPORT.md`（原 QA `bf7851c` FAIL D1/D2 + D3）、`../R1-REPORT.md`（返修自检，替身/0 真实）、`../R1-PLAN.md`。
- **判定：FAIL（未达成功门）**。LG-022 保持 `in-progress`；本包不自修产品、不自判通过。

> 结论一句话：真实主链在本 phase 消耗 **6/10** 真实生成后停在 `phase=verifying`，**未**到 `awaiting_acceptance`；
> 根因经本地确定性复现定位为**产品缺陷（stop gate 死锁）**，非测试 deadline/transport 抖动；另有**生成计数跨重启不持久**未满足计量硬门。

## 1. 计量边界（先列，避免洗数）

| 阶段 | 真实生成请求 | 证据 |
|---|---|---|
| 旧 QA（原 LG-022 首轮，`bf7851c`） | **unknown**（单列保留；含 429 后 rerun；不视为 0） | `PLAN.md` §2，`../REPORT.md` |
| 本复验 R1 phase（`ec2420e`） | **6/10**（含 Settings/直答/worker/reviewer；`remaining=4`） | `evidence/real-chain.json` `generation_readings` / `final_generation` |
| 本续接收尾（新上下文） | **0**（仅本地确定性探针，0 网络） | 本 REPORT §3；`evidence/stopgate-repro.json` `real_model_calls: 0` |

- 本 phase 未超预算：`final_generation = {count:6, limit:10, remaining:4}`（`real-chain.json`），**剩余真实预算 4**，本收尾未使用。
- 不把未知旧量洗成 0；不宣称整个 LG-022 累计 <20 等无证据总数；失败/未完成样本不计交付成本。

## 2. 决定性发现：真实主链停在 `verifying` 未到 `awaiting_acceptance`

### 2.1 原始真实快照（`evidence/real-chain.json`，未改写）

- `steps[run_reached_awaiting_acceptance].ok = false`，`phase = "verifying"`，`phases_seen = ["executing","verifying"]`。
- Run（`run_01M5031MJ7J6FV1GYW0W3S8GS7`）：`state = "verifying"`、`cleanup = {"status": "pending"}`、
  `session_refs = ["sess_57ee21e998c3411889ddebfba03cac09","sess_a392d9dc258d4fb98df9595c1aed14b1"]`（2 个真实 SDK session）。
- `task_after_run.acceptance.status = "pending"`，但 Task phase 仍 `verifying`。
- `accept_response.error = {code:"illegal_transition", message:"task phase 'verifying' has no pending acceptance decision"}`。
- `run_md_fail_reason = ""`，`executor_model_calls = 5`，`max_status_latency_s = 1.313`。

### 2.2 真实 reviewer 原因判定：**产品缺陷**，非测试等待窗口/transport/预算/无效输出

逐项排除：

| 假设原因 | 证据 | 判定 |
|---|---|---|
| deadline/等待窗口太短 | `run_reached_awaiting_acceptance` 轮询上限 200s，`status_query_not_blocked_during_run.ok=true`（`max 1.313s < 2.0`） | 排除 |
| transport/proxy 故障 | 无 5xx/429；`generation count` 稳定于 6；`run_md_fail_reason` 空 | 排除 |
| 预算耗尽 | `remaining:4`，未触发 429 | 排除 |
| 无效模型输出 | worker/verify 子任务均 `node_state:"passed"`，产出 `out/result.txt` 与其 diff 证据 | 排除 |
| **stop gate 资源未确认停止** | Run 有 2 个 session 且 `cleanup.status="pending"`；`StoreResourceStopper` 要求 `not session_refs or cleanup=="done"` | **命中（根因）** |

### 2.3 根因（产品代码，只读定位）

`backend/lightgravity/verify/stopgate.py::StoreResourceStopper.stop`：

```python
sessions_stopped = not session_refs or cleanup_status == "done"
```

- 正常成功 Run 的真实路径会记录 `session_refs`（2 个 SDK session），但**没有任何正常成功路径把 `cleanup` 写成 `done`**：
  - `backend/lightgravity/coordinator/graph.py` / `dispatcher.py`：仅有 `grep` 命中 0 处的 cleanup/session close 写入；
  - `coordinator/service.py`：`cleanup={"status":"pending"}` 在开 Run 时写入（L1282）；`done` 仅在
    **stale run**（L1500）、**recovery_required**（L1540）两个非成功路径写入；
  - `verify/service.py`：`cleanup=done` 仅在 **人工 accept 之后**（L463）写入。
- 于是 `verify_and_prepare` 走 `stop.confirmed == False` 分支 → 返回 `state="unconfirmed"`，Task 保持 `verifying`，
  **不打开 acceptance** → `POST accept` 返回 `illegal_transition`。这与真实链观察完全一致。

### 2.4 本地确定性复现（0 真实模型调用）

脚本：`harness/stopgate_repro.py` → 证据：`evidence/stopgate-repro.json`
（`evidence_kind: local-deterministic-stopgate`，`real_model_calls: 0`，`deadlock_reproduced: true`）。

| case | session_refs | cleanup | stop.confirmed | verify.state | verify.phase | task.phase |
|---|---|---|---|---|---|---|
| **real_chain_shape** | `[sess_a,sess_b]` | `pending` | **false** | `unconfirmed` | `verifying` | **`verifying`（死锁）** |
| control_no_sessions | `[]` | `pending` | true | `confirmed` | `awaiting_acceptance` | `awaiting_acceptance` |
| control_cleanup_done | `[sess_a,sess_b]` | `done` | true | `confirmed` | `awaiting_acceptance` | `awaiting_acceptance` |

`real_chain_shape` 的 `stop_report.problems = ["2 session(s) not confirmed closed (cleanup='pending')"]`。
对照组证明：只要 `cleanup=done`（或无需 session 清理），同一服务即可正常放行验收 —— 死锁只由“成功路径从不确认 session 关闭”引起。

### 2.5 精确最小复现

1. 用真实后端起服务，配默认 worker/reviewer（真 DeepSeek），建一个写文件的最小 Task 并执行到成功；
2. 成功 Run 落盘后其 `session_refs` 非空、`cleanup.status=="pending"`；
3. 观察 Task 停在 `phase=verifying`（无 `awaiting_acceptance`），`GET /tasks/{id}` 的 `acceptance.status` 为 `pending`；
4. `POST /tasks/{id}/accept` → `409 illegal_transition "task phase 'verifying' has no pending acceptance decision"`。

等价的零网络最小复现：`uv run python probes/lg022/reverify-r1/harness/stopgate_repro.py /tmp/out.json`
（`deadlock_reproduced: true`）。

## 3. 第二项硬门未过：生成计数不跨重启持久

`PLAN.md` §2 的计量硬门要求计数器“**跨 service/进程重启不归零（持久数据根落盘）**”。
`evidence/counting-proof.json`（本地伪上游，0 真实调用）实测：

- C1 计数随转发递增 ✅；C2 达上限后 `reserve()` 拒绝且不再转发（429）✅；C3 跨 session 共享 ✅；
- **C4 `persisted_across_restart = false`** ❌：`fresh_interpreter_snapshot = {count:0,...}`。

产品确认：`backend/lightgravity/adapter/proxy.py::GenerationCounter` 仅进程内内存（`self._count`），无落盘。
因此“跨重启精确计数”不成立。该缺口 R1-REPORT 未宣称已持久（仅称“进程全局”），但 **PLAN 将其列为硬门**，判 **fail 计量持久化子项**。
（进程内跨 session/reviewer 共享确实成立，如实分列。）

## 4. 成功门逐条裁定（`PLAN.md` §4）

| 门 | 结果 | 依据 |
|---|---|---|
| 1. 计量先行 + 真转发 ≤10 且可精确计数 | **部分 FAIL** | 计数/拒超限/共享 ✅；**跨重启持久 ❌**（§3）；本 phase 真转发 6/10 可计数 ✅ |
| 2. D1 全链到 `awaiting_acceptance` + accept 绑定/duplicate/stale | **FAIL** | 真实链停在 `verifying`（§2）；accept 409 `illegal_transition`；duplicate 亦 409 |
| 3. D2 reviewing 不阻塞 + stop/release 确认 + 未知保留槽 + restart 不重放 + 跨 Run 预算 | **FAIL（部分）** | 不阻塞 ✅（`max 1.313s`）；真实 stop/release 确认**未达**（stop gate 死锁）；其余未在真实链证实 |
| 4. D3 成功 Run 无 `fail_reason` | **PASS** | 真实链 `run_md_fail_reason=""`；`d3_success_run_no_fail_reason.ok=true` |
| 5. 真实/替身逐项标清、未测列明 | **PASS（本报告）** | 见 §5、§6 |

⇒ 成功门未全满足，**判 fail**。

## 5. 真实 / 替身逐项标注

| 项 | 类别 | 证据 |
|---|---|---|
| worker 真实写 task、产出 `out/result.txt` | **SDK-real / DeepSeek-real** | `real-chain.json` `node_sessions.*.handoff.artifacts` |
| reviewer 接线为 `model` / `deepseek-chat` | **real config** | `real-chain.json` `reviewer_wired_model` |
| 主链到 `awaiting_acceptance` | **未达**（真实链） | `real-chain.json` `run_reached_awaiting_acceptance.ok=false` |
| reviewing 期间状态查询不阻塞 | **real** | `max_status_latency_s=1.313` |
| D3 无伪 `fail_reason` | **real** | `run_md_fail_reason=""` |
| stop gate 死锁 | **local-deterministic（替身，非真模型）** | `stopgate-repro.json` |
| 计数 计数/拒超限/跨 session 共享 | **local-fake-upstream** | `counting-proof.json` C1–C3 |
| 计数跨重启持久 | **local-fake-upstream（FAIL）** | `counting-proof.json` C4 |

## 6. 本续接收尾的 QA 脚本修正与限制（不改产品代码）

- 修正 **QA 脚本缺陷**（非产品）：`harness/deterministic_probe.py` 的 dispatcher 替身
  `CancelResult(confirmed=True)` 缺必填 `state`，改为 `CancelResult(confirmed=True, state="cancelled", reason=...)`
  （`backend/lightgravity/adapter/execution.py::CancelResult` 要求 `state`）。
- 如实说明：修正后 `deterministic_probe.py` 可运行，但该探针的 dispatch 替身**未能持久化 `session_refs`**
  （场景里 `session_refs: []`、task 停在 `planning`），因此它**不构成**对真实 stop/release 生命周期的有效证据；
  以 `stopgate_repro.py` 的定向复现为准。该探针结果存 `evidence/deterministic-probe.json`（标注为低保真替身，不作通过依据）。
- **未**新增/未重跑任何真实 DeepSeek 请求；**未**重置 counter；**未**复用未知写入；**未**手改状态或绕过验收。

## 7. 需返修（交主代理另派，本包不自修）

组件（产品代码，按缺陷优先级）：

1. **`verify/stopgate.py` + 成功 Run 生命周期（阻断）**：成功 Run 在 `verifying` 前必须真实确认 session/执行资源已停止并写
   `cleanup.status="done"`（或由 adapter 提供更强的 `ResourceStopper` 确认），否则 `verify_and_prepare` 永远 `unconfirmed`，
   验收门对任何真实 session-bearing Run 死锁。
2. **`adapter/proxy.py::GenerationCounter` 持久化（计量硬门）**：如需满足“跨重启不归零”，计数需落盘到持久数据根并在启动时续读；
   否则 PLAN 计量门无法通过（须由主代理决定是收敛门还是修实现）。

最小复现、真实快照、本地控制组均在本目录 `evidence/` 与 `harness/`。修复后须由**新的独立 QA** 复验，本包不判通过。

## 8. 状态与剩余预算

- **LG-022：保持 `in-progress`**（真实全部门未满足）。
- 本 phase 真实预算：**已用 6/10，剩余 4**；本续接**未使用**（0 真实请求）。
- 旧 phase 真实调用：**unknown**（单列，未 reset）。
- 未测项（明确未证实）：真实 reviewer 在真实 loop 下的通过/降级；真实 stop/release 确认与超长 review 取消；
  restart 不重放的真实链路；跨 Run 预算；浏览器/HTTP 全路径版本门；`source`/`vectors` 新路径质量（不在本门）。

## 9. 证据与脚本路径

- 原始真实快照：`probes/lg022/reverify-r1/evidence/real-chain.json`（本收尾未改写）。
- 计量：`evidence/counting-proof.json`；干跑：`evidence/dry-run.json`。
- stop gate 定向复现：`evidence/stopgate-repro.json`（脚本 `harness/stopgate_repro.py`）。
- 低保真替身：`evidence/deterministic-probe.json`（脚本 `harness/deterministic_probe.py`，已修 QA 导入缺陷）。
- 计划/输入：`PLAN.md`、`../REPORT.md`、`../R1-REPORT.md`、`../R1-PLAN.md`、`../evidence/r1-review-lifecycle.json`。
  - 注：`../evidence/r1-review-lifecycle.json` 在上轮 QA owner 处已被**本地重跑刷新**（仅 `elapsed`/`loop_served_latency` 计时数值变化，机制结论不变），本收尾**未 overwrite**，原样保留并注明。
