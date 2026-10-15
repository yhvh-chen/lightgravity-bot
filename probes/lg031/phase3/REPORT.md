---
title: "LG-031 phase3 — REPORT（真实 SDK 两 worker 自主闭环：partial，兼容缺陷已修）"
doc_type: report
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg031-r3"
branch: "fix/lg031-r3"
base: "0144eb7"
---

# LG-031 phase3 — REPORT（**partial**）

- Owner：`agent:pi-lg031-r3`（pi + env DeepSeek；主代理只 PM，**无嵌套派工/推送/部署/发布**）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg031-r3`（branch `fix/lg031-r3`）。
- 基点：整合候选 `0144eb7`（含 core 第二轮返修：持久 generation ledger、权威 StopConfirmation、
  非空 `session_refs`、`reviewer_cleanup`、async review 生命周期）。
- 输入：`probes/lg031/{R2-REPORT,R2-STATUS}.md`、`r2_worker_claim_probe.json`、
  `probes/batch-20261016/INTEGRATION-7.md`、PM 预算决定
  `~/.cache/lightgravity-bot/checkpoints/2026-10-15/pm-budget-lg031-phase3-20261016.txt`。

## 0. 一句话结论

驱动**真实产品 `GraphDispatcher` 路径**（而非 R2 的手搓 harness）后，暴露并修复了两个真实
缺陷（产品未接自主 claim 开关；受限 claim 工具的发现投影缺 `objective`）；离线用确定性
fixture 已证明**产品路径**下 2 worker 自主 discover→claim→程序原子授权→带 hash 交接→完整
候选可闭环。**但真实 DeepSeek 链在本 phase3 只跑到 produce worker 的自主 claim**，因
14 次真实请求硬上限用尽，**硬条件 4/5（带 hash 交接、完整候选独立 review passed）未闭合**。
**不写 done、不伪称；无偷偷重开账本归零。**

## 1. 真实请求计数（不重置、不猜）

- 旧累计（前两阶段）：原包 1 + R1 3 + R2 6 = **10/10**（保留为失败/partial 成本）。
- 本 phase3：**14/14 用尽**；运行 1/2/3 分别 **4 / 5 / 5**。
- **旧 10 + 新 14 = 24**（PM 批准全局已知上限 ≤24）。
- 单一权威事实源：`probes/lg031/phase3/ledger/generation/`（契约 1.10 持久账本，转发前持久预留）；
  最终快照 `count=14, limit=14, remaining=0, corrupt=false, persistent=true`。
- 跨进程/重启可靠性**转发前已验证**：进程 1 预留 5 → 新进程预留 12 只再成功 9（合计 14）→
  第三个进程读到 `count=14`（不归零）→ 损坏快照 `raise`（**绝不当 0**，拒绝转发）。
- SDK/API retry **0**；单 HTTP ≤120s；并发 ≤2；每请求输出 ≤12000 tokens。
- usage：所有 reviewer `{"unknown":["usage"]}`；worker token 明细未由 SDK 事件暴露，记 **unknown**（不当 0）。

## 2. 真实链实际发生了什么（诚实）

| 运行 | 真实转发 | 结果 | 关键观察 |
|---|---|---|---|
| 1 | 4 | produce worker `MAX_MODEL_CALLS_EXCEEDED`；reviewer `unavailable` | 派工预算 `max_model_calls=3` 太紧，worker 未写到文件 |
| 2 | 5 | produce worker 跨 per-worker proxy cap（4）被 429；reviewer `unavailable` | **真实 worker 自主**调用 `discover_and_request_claim()`→`discover_and_request_claim(node_ref)`，经产品 router |
| 3 | 5 | produce worker 6 次工具调用后 429；reviewer `unavailable` | worker 反复发现/claim 但**学不到要建哪个文件**（见 §3 G2） |

- Run2/Run3 的 `adapter.tool_call` 事件链（`autonomous_claim_chain`）证明**是 worker 自己**通过
  受限工具发起 discovery/claim，**不是程序先选节点代领**。
- 三次 reviewer 均真实调用 1 次，但因候选不完整**诚实返回 `unavailable`**（未降级门、未伪造 passed）。

## 3. 发现并最小修复的真实缺陷（离线先证）

### G1 — 产品 bootstrap 未接自主 claim（wiring）

`api/bootstrap.py` 默认 `GraphDispatcher` **从不传** `autonomous_claim` / `grant_registry`，
也**不读** `decentralized_claim_enabled` 开关 ⇒ 产品路径即使打开开关也**无法启用**自主 claim 工具。
R2 探针因此**绕过产品协调器**（手搓 pool grant/claim callback），其“闭环”**不是产品路径**。

**修复**（加性、可回退）：`build_runtime` 读 `ClaimPolicyReader` → 开关开启时
`autonomous_claim=True` + 装配进程全局 `ExecutionGrantRegistry`；关闭/缺省完全走旧确定性路径
（无工具、无 grant）。测试：`tests/startup/test_lg031_r3_bootstrap_autonomous.py`（2 项）。

### G2 — 受限 claim 工具的发现投影缺 `objective`（compat defect）

`make_restricted_claim_tool` 的发现投影只回 `node_ref`/`capability`/`key`。经产品 planner，
`key` 必须是 slug（`PlanValidator._KEY_RE` 拒绝路径），所以 worker **无法**得知“要创建哪个文件”；
`candidate.key` 只是 `"produce"`。R2（手动建 subtask，`key=文件路径`）恰好掩盖了该缺陷。

**修复**（加性、非秘密）：投影增加程序拥有的 `objective` 与 `write`，使产品路径 worker 能据
objective 判定其节点产物。测试：`tests/collaboration/test_lg031_r3_product_path_closure.py`。

### 离线证明（无模型/无网络）

`test_lg031_r3_product_path_closure.py` + 本地 sim 复现正确序列
（`discover→按 objective 选节点→claim→create_file`）穿过**真实 `GraphDispatcher`**：

- 2 worker，各在**独立真实 git worktree**（`ws!=base`）；
- 两次 claim 均 `ok=True, state=granted, fence=1`，receipt **无 token 泄漏**；
- 依赖节点获得 **versioned+hashed** 交接（`subtask@sha256:out/produce.txt`）；
- 每 worker 在其**自有** worktree 写出产物；
- 执行停止后 `active_grants()==0`（身份不留存）。

## 4. 检查（真实退出码）

| 命令 | 结果 |
|---|---|
| `uv run mypy` | **Success: no issues found in 137 source files** |
| `uv run pytest -q -p no:randomly`（全量一次） | **775 passed, 5 skipped**（84.16s） |
| `pytest tests/collaboration tests/coordinator tests/settings ... -q` | **249 passed** |

> 与 INTEGRATION-7 基点（775 passed, 2 skipped）一致；多出的 3 个 skip 为条件门（真实向量质量 /
> 真实 DeepSeek 需显式 env），非回归。

## 5. 真实硬条件达成（不夸大）

| # | 条件 | 结果 |
|---|---|---|
| 1 | ≥2 真实 SDK worker，各自独立 worktree | ⚠️ 仅 produce worker 真跑；integrate 未达 |
| 2 | worker 自主 discovery→申请原子授权 claim | ✅ 真实 worker 自主工具调用链（产品 router） |
| 3 | 程序验证并原子授权 + lease/fencing | ✅（离线产品路径证实 grant/fence=1/脱敏） |
| 4 | 受控带 hash 同伴交接 | ❌ 未达 |
| 5 | 完整候选独立 ModelReviewer + 机器门 | ❌ 未达（候选不完整；reviewer 诚实 unavailable） |
| 6 | 默认关闭/回退、身份程序注入、无全局 token | ✅ |

## 6. 每 worker 证据 / 隔离 / 交接 / 候选 / 停止 / 版本

- **工具**：`discover_and_request_claim`（`X-LG-Execution-Grant` 仅头部身份；body 永不认证）+
  受限 `request_peer`。
- **隔离**：`GraphWorkspaceProvider(WorktreeManager)` 真实 per-node worktree（离线证实 `ws!=base`）。
- **交接**：程序 `encode_handoffs` 生成 `<subtask>@<sha256>:<artifact>`（离线证实 64 hex）。
- **候选 review**：产品 `verify.review.ModelReviewer` + `validate_findings` 机器门（真链 3 次真实
  调用，均诚实 `unavailable`）。
- **停止证据**：`AntigravityExecutor` 在 `execute.finally` 关 session + 停 loopback 代理；
  grant 在执行结束即 revoke（离线 `active_grants()==0`）。
- **输入与源码版本**：base `0144eb7`（契约 `1.10.0`，SDK `google-antigravity==0.1.22`，
  `LocalOpenAIAgentConfig`/`openai-compat` → loopback 认证代理 → DeepSeek `deepseek-v4-flash`）。

## 7. 成本（已知/未知，不 pesavings）

- 旧 10：原包 1 reviewer（usage unknown）；R1 worker A 6880 + B 6923 + reviewer unknown；
  R2 worker A 20587 + B 3361 + reviewer unknown。
- 新 14：worker token 明细 unknown（SDK 未暴露）；reviewer 全部 unknown。
- **未知单列，不当 0；不宣称节省 token**（本 phase3 非 LG-032 收益比较）。

## 8. 剩余门 / 交接

- **未闭合**：硬条件 4/5（integrate worker 自主 claim+写、带 hash 交接、完整候选 reviewer `passed`）。
- **根因**：真实预算 14 用尽 + worker 回合效率（每次工具调用约 1 个模型轮）。
- **已就绪**：G1/G2 修复 + 离线产品路径闭环测试；下一次真实 phase（若 PM 另批）可在预算内
  用**修正后的 prompt（worker 据 objective 判产物）**直接闭合，无需改门/降级。
- **不扩原 10**：本包未擅自扩原上限，仅用 PM 批准的 phase3 14；已用尽即停，不偷偷归零。
- 独立集中 QA（LG-032）与全生命周期成本对比**不在本包**；031 保持 **in-progress / partial**。

## 9. 边界与保护

- 全部旧 worktree/分支/实验/失败证据/`probes/lg031/R1_*`、`dev/lg031`、`fix/lg031-r1` 原 dirty
  一律**未触碰**；未 reset/clean/整树覆盖/删 worktree；未在旧 dirty `lg031-r1` 写入。
- 主 worktree 的 2026-10-15 uvicorn（端口 8123，非本包）**未 kill、未接线、未复用其 dataRoot**。
- 未 push/部署/发布；未改 `sources/vectors/frontend`；未碰 022 worktree。
- 默认关闭/旧确定性回退保留；未知副作用 `recovery_required` 不重放；`session_refs` 不删除；
  1.10 持久账本仍为唯一生成限额事实源。
