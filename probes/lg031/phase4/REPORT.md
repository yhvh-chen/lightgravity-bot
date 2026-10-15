---
title: "LG-031 phase4 — REPORT（单次真实产品闭环：核心通过，交接原文未捕获 ⇒ 诚实 partial）"
doc_type: report
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg031-r3"
branch: "fix/lg031-r3"
base: "faacb90"
---

# LG-031 phase4 — REPORT

- Owner：`agent:pi-lg031-r3`（pi + env DeepSeek；主代理只 PM；**无嵌套派工/推送/部署/发布**）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg031-r3`（branch `fix/lg031-r3`）。
- 基点：`faacb90`（phase3 诚实 partial 检查点）。离线修复提交 `75e1487`。
- 输入：`probes/lg031/phase3/{REPORT,LEDGER,STATUS}.md` 与 `evidence/run{1,2,3}_*`、
  `probes/lg031/{R1,R2}-*`。

## 0. 一句话结论

零模型定位了 phase3 的真实失败点（两个 per-worker 上限不一致导致多步 worker 被不透明 429 杀死、
dependent worker 从未调度），做了**加性最小修复**（proxy 上限对齐冻结的 per-request
`budget.max_model_calls`），离线硬门全绿后，用**真实产品 `RuleBasedPlanner` 路径**跑了**一次**
完整真实闭包：**2 个真实 SDK worker 各自自主 discover→claim（经产品
`GraphDispatcher._claim_for_worker`），程序原子授权（fence=1、脱敏），dispatcher `succeeded`，
真实独立 ModelReviewer + 机器门 `passed`/`passed`，候选完整可复源**。但本探针的**交接字符串
提取有 bug**（`subtasks/*.md` 而非 `subtasks/<id>/SUBTASK.md`），真实运行写入的
`upstream_artifact_refs` **未被捕获**；在 16 调用上限内（已用 10）**未重跑**补证。故
**硬条件 4 的真实原文证据缺失** ⇒ 本包**诚实 partial**，不写 done、不伪称。

## 1. 真实请求计数（不重置、不猜）

- 旧累计（前三阶段）：原包 1 + R1 3 + R2 6 + phase3 14 = **24**（保留）。
- 本 phase4：**一次**真实 attempt，用 **10 / 16**（其中 worker ≈ 9 轮 + 独立 reviewer 1 轮）。
- **全局已知工程累计 = 24 + 10 = 34（≤ 40 上限）**。
- 单一权威事实源：`probes/lg031/phase4/ledger/generation/`
  （持久账本；`generation.jsonl` 10 条 reserved；快照 `count=10, limit=16, remaining=6,
  corrupt=false, persistent=true`；pid 1968580）。
- SDK/API retry 0；单 HTTP ≤120s；并发 1（本探针串行）；每请求输出 ≤12000 tokens。
- usage：worker token 明细 SDK 未作为事件暴露，记 `unknown`；reviewer `{"unknown":["usage"]}`（**不当 0**）。

## 2. §A 零模型 forensics（phase3 失败点）与最小修复

**失败点**（证据：`phase3/evidence/run{1,2,3}_*`、`phase3/ledger/generation/generation.jsonl`）：
- Run1：SDK `StopReason.MAX_MODEL_CALLS_EXCEEDED`（`budget.max_model_calls=3` 太紧）。
- Run2/Run3：loopback proxy `429 local auth proxy call budget exhausted`（per-worker proxy
  `max_proxy_calls` 先耗尽）。
- 两次的共同点：SDK `BudgetConfig.max_model_calls` 与 proxy `max_proxy_calls` 是**两个独立上限**；
  proxy 先 429 时**掩盖** SDK 的真实停止原因；`deliver`/produce worker 反复探索工具调用，
  在写入前被杀，dependent worker 从未调度。

**最小修复（加性，`backend/lightgravity/adapter/executor.py`）**：`execute()` 创建 per-session
proxy 时，把上限对齐到 coordinator 冻结的 `request.budget.max_model_calls`
（取 `min(max_proxy_calls, remaining_lifetime_cap, request_model_calls)`）。未设 model budget
时行为完全不变。离线测试 5 项（`tests/adapter/test_lg031_r3_generation_ceiling_alignment.py`）
覆盖对齐/最小值/加性/非法值。

`phase3` 的 G1（bootstrap 接自主 claim）/G2（发现投影带 `objective`/`write`）已修，本包回归验证。

## 3. §B 一次真实产品闭环（结果）

探针：`probes/lg031/phase4/real_worker_closure_probe.py`（**不注入 planner**，用真实
`RuleBasedPlanner` → `deliver`(write) → `verify`(依赖)）。证据：
`probes/lg031/phase4/real_worker_closure.json`、`evidence/run_real_worker_closure.json`。

| 项 | 真实结果 |
|---|---|
| dispatcher | **succeeded** — "all 2 subtask(s) passed; candidate handed to verification" |
| 真实 SDK worker | 2（developer `deliver` + verifier `verify`），经产品 loopback 认证代理 → DeepSeek |
| 自主 claim | ✅ **4** 条 `discover_and_request_claim` 工具调用（deliver: 无参 discover + `node_ref` claim；verify: 无参 discover + `node_ref` claim），router = `GraphDispatcher._claim_for_worker` |
| 程序原子授权 | ✅ fence=1、receipt 脱敏（离线回归断言 `json.dumps` 无 token） |
| 真实 worktree | deliver 写节点在程序 provision 的独立真实 git worktree（离线 r4 断言 `ws != base`） |
| 依赖带 hash 交接 | ⚠️ **真实运行已发生但本探针未捕获原文**（见 §4） |
| 独立 ModelReviewer | ✅ 真实 1 次；`reviewer_kind=model`；`outcome=**passed**`、`validated_outcome=**passed**` |
| 机器门 | ✅ `validate_findings` 通过，候选证据可复源（`out/deliver.txt` + diff patch `@sha256:820a…`） |
| 停止 | ✅ `AntigravityExecutor` finally 关 session + 停 loopback 代理；离线断言 `active_grants()==0` |
| 耗时 | 25.07s |

真实运行**产物完整**：reviewer `resolved_evidence` =
`["evidence:run_…/subtask_…-lg006-diff.patch@sha256:820a554a…", "out/deliver.txt"]`
（程序整合候选含 diff 与文件，机器门通过）。

## 4. 未闭合项（诚实，不伪称）

**硬条件 4「受控带 hash 同伴交接」的真实原文证据缺失**（探针 bug，非产品缺陷）：

- 探针从 `store.data_dir / "subtasks" / "*.md"` 提取 handoff，但 Subtask 实体实际位于
  `subtasks/<id>/SUBTASK.md`（子目录），故 `handoff_refs` 恒为 `[]`。
- **产品侧交接真实发生**：真实 claim 链包含 verify 节点的 `discover_and_request_claim`
  （verify 节点只有在 deliver 通过、依赖满足后才可发现/领取），deliver 产出
  `out/deliver.txt`（reviewer 证据可见）并被 `verify` 执行请求接收。
- **离线已证交接机制**（真实 hash）：
  `tests/collaboration/test_lg031_r4_real_planner_closure.py` 断言依赖节点收到
  `<subtask>@<64-hex>:out/deliver.txt`；独立 dump 复现
  `subtask_…@2b5893db…68d6:out/deliver.txt`。
- **未重跑补证**：一次完整 attempt 需 ≈10 转发，本 phase4 仅剩 **6**（16 − 10），**不重跑同一
  fixture**（PM 明确不得默默重跑）。探针提取 bug 已修复（改扫 `subtasks/<id>/SUBTASK.md` 并
  记录每个 worker 请求的 `upstream_artifact_refs`），留作后续 phase 的**唯一**一次复验依据。

**结论：LG-031 保持 `in-progress / partial`。** 真实 loop **闭合**（dispatcher succeeded +
reviewer passed），但硬条件 4 的真实字符串证据缺失，不写 done。**未降低任何复核/机器门/停止/验收门**：
reviewer 真实调用且诚实；未为探 reviewer 能否过而重复调用；未伪造 passed。

## 5. 检查（真实退出码）

| 命令 | 结果 |
|---|---|
| `uv run mypy` | **Success: no issues found in 137 source files** |
| `uv run pytest tests/adapter -q -p no:randomly` | **102 passed** |
| `uv run pytest tests/collaboration -q -p no:randomly` | **77 passed** |
| `uv run pytest tests/coordinator -q -p no:randomly`（含 collaboration 同批） | **187 passed** |
| `uv run pytest tests/verify tests/api -q -p no:randomly`（含 adapter 同批） | **233 passed** |
| `uv run pytest tests/startup -q -p no:randomly` | **39 passed, 4 skipped** |
| `uv run pytest tests/settings -q -p no:randomly` | **46 passed** |
| 持久账本跨进程/重启 + 损坏拒绝 | 见 `OFFLINE-GATES.md` §1（不归零；损坏 `corrupt=true` 且拒绝转发） |

## 6. 成本（已知/未知，不 pesavings）

- 本 phase4：worker ≈9 轮 + reviewer 1 轮 = **10** 真实转发；worker/reviewer usage 均 **unknown**（不当 0）。
- 旧 24 保留（原 1 + R1 3 + R2 6 + phase3 14）。
- **不宣称节省**（本包非 LG-032 收益比较）。

## 7. 边界与保护

- 全部旧 worktree/分支/实验/失败证据/`probes/lg031/{R1,R2,phase3}` 原样保留；未 reset/clean/覆盖/
  删 worktree；未在旧 dirty 工作区写入。
- 主 worktree 的 uvicorn（端口 **8123**，非本 worktree、非本包）**未 kill/接线/复用 dataRoot**。
- 未 push/部署/发布；未改 `sources/vectors/frontend`；未碰 022 worktree 与 core 独立 QA 的 0 请求补证；
  未碰主目录集成者。
- 默认关闭/旧确定性回退保留；身份只由程序冻结注入；worker 无全局 token；过期≠停止；旧 fence 不可写；
  未知副作用 `recovery_required` 不重放；实际停止后才回收权限。
- 1.10 持久账本 / stopconfirmation / reviewer_cleanup / 非空 session 历史 / 反重放 / token / pin /
  验收幂等 / 资料 1.9 兼容均保留。

## 8. 剩余门 / 交接

- **未闭合**：硬条件 4 的**真实 handoff 原文**（机制与离线证据已在，真实运行已发生，探针未捕获）。
- **已就绪**：修复后的探针（正确提取 handoff + 记录每 worker 请求 objective/upstream）；上限对齐修复；
  真实 planner 路径离线闭环回归。
- 下一次（若 PM 另批）只需**一次**复验 run（预算需 ≥10；本包剩余 6 不足），即可在真实证据中直接
  记录 `<subtask>@<64hex>:out/deliver.txt`，无需改门/降级。
- 独立集中 QA（LG-032）与全生命周期成本对比**不在本包**；**031 保持 partial**，不制造待 032 循环。
