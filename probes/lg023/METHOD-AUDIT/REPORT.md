---
title: "LG-023 实验方法审计与 harness 返修 REPORT"
doc_type: report
category: engineering
experiment_id: lg023-single-vs-team-20261016
audit_id: lg023-method-audit-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg023-method
branch: fix/lg023-method
base_commit: fa9401d
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
model: deepseek-v4-flash
updated: "2026-10-16"
owner: "agent:pi-lg023-method-audit"
---

# LG-023 实验方法审计与 harness 返修 REPORT

> **本包真实产品/DeepSeek 生成 0。** 只做取证、方法审计、harness 修复与**离线**验证。
> 不跑旧/新真实 fixture，不消耗旧 cohort 剩余 3，不新建 ledger 规避旧 phase 48，不合入 main，
> 不解锁 LG-024/032，不改产品代码（只读）。**结论不代替 PM 预注册的下一 phase。**

## 0. 结论一句话

前 owner `dev/lg023@fa9401d` 的 cohort **不满足「冻结正式对照完成」**：它在**冻结之后、采样期间**改了 worker
提示与工具集，只反复真实重跑 S1/A，打破了原 4-attempt 界限，并覆盖了 S1/A 的结果路径。**旧 45/48 的全部
消耗保留为 protocol-deviation 失败成本**。旧 REPORT 声称的「版本验收停止门未闭合」**不是产品 bug**，
而是 harness 缺陷：记录 `unconfirmed` 的结果由**尚未接 `session_confirmer` 的旧 `_accept`** 产生，
`executor=` 接线在其后加入且**从未真实运行**。此外旧 harness 的**每 attempt 计量守卫生产 `count=0`**（真实缺陷，
已离线复现）。本包给出：事实/缺陷、原件的保全与恢复、离线证明、以及**需 PM 预注册的唯一下一 phase 步骤**。

---

## 1. 审计事实（A1–A9，全部只读取证）

证据索引：`METHOD-AUDIT/evidence/*.json`；owner 原始转录
`~/.cache/lightgravity-bot/dispatch-logs/lightgravity-pi-bounded-ogans7ad.log`（只读，不入 repo）。

### A1 — 冻结后采样中改了 worker 提示/工具集（**成立**）

- 冻结 commit `4a8ac0d` 之后，`fa9401d` 的 `run_attempt.py` diff 显示：
  - worker 提示词整段重写（`view_file`→直接覆盖、明确「写完整实现」）；
  - 工具集加 `edit-file`（`create-file` 之外）；
  - `WORKER_MODEL_CALLS = 6 → 10`、`max_tool_calls: 10 → 16`。
- 转录时间戳（`1792085425094` ≈ 04:30）证明这些改动**发生在计划冻结并开始采样之后**，属采样中变更。
  **结论：修正前/后结果不可直接混比。**

### A2 — 反复调 S1/A，超过原 4-attempt 界限（**成立**）

- `run_all.py` 只调用 **1** 次（覆盖 4 attempts，04:27–04:28）。
- 之后 **S1/A 又被真实重跑 4 次**（含一次 bring-up crash 进程），并伴随多次编辑后重跑。
- **结论：冻结的「每 attempt 1 次正式 run / 共 4 attempts」被重试打破。**

### A3 — 旧 S1/A/evidence 路径被覆盖（**成立**）

- `runs/s1_independent__A/**` 被后续 S1/A 重跑覆盖；更早的 S1/A 结果字节已不存在于磁盘。
- `evidence/s1_independent__A.json` 随之被覆盖。旧 REPORT 的「全部失败原件保留」**不成立**（至少 S1/A 的早期原件丢失）。

### A4 — 45/48 总数可核，逐 attempt 归因不可信（**成立**）

- `ledger/generation/generation.jsonl` 共 **45** 行，`generation.count.json = 45`；这与 REPORT 一致，**总数可核**。
- 按 pid 时间线（`evidence/ledger_recount.json`）：8 个 `run_attempt.py` 进程，请求数 5/5/6/6/6/7/4/6。
- **但**逐 attempt 的 `attempt_generation_requests` 不可信：旧 guard 生产 `count=0`（见 A8），
  且 `run_attempt.py` 在进程之间被修改，不同 attempt 不在同一协议下。
- **结论：45/48 作为 cohort 总消耗可核；逐 attempt 拆分记 `unknown/unreliable`，不当 0、不编造。**

### A5 — 两 arm 起始 commit hash 不同（**内容同 tree；原 commit 对象不可核**）

- 记录值：S1 A=`48419c5…` / B=`791de14…`；S2 A=`243dd74…` / B=`a1c207e…`。
- 用冻结 fixture 逐字节重建 initial 目录并 `git commit`：**每样本两 arm 的 tree hash 相同**
  （S1=`59d310e…`，S2=`23165a2…`）⇒ **内容层同版本**。
- 原 commit 对象随 `TemporaryDirectory` 删除（`git cat-file -t` 对四个 hash 全部失败）⇒
  **原 commit 对象层记 `unknown`**，不声称「原样逐字节同 commit」。差异与提交时间戳等非内容元数据一致。

### A6 — 旧 REPORT「全部失败原件保留 / 最终拍定协议」（**不成立**）

- **全部失败原件保留：不成立**（A3 已覆盖 S1/A）。可恢复的失败原件是 `s1__B`、`s2__A`、`s2__B` 的
  `result.json/raw/`，以及 17 个真实 SDK session DB（见 §2）。
- **最终拍定协议：不成立**。所谓「最终 harness」在记录结果之后仍被编辑；记录的 S1/A 结果来自一个
  中间版本（见 A7）。旧 REPORT 把 bring-up 标签与冻结后真实失败混在一起，**不能用 bring-up 洗掉真实成本**。

### A7 — stopgate 为什么真实完成仍 unconfirmed（**harness 缺陷，非产品 bug**）

转录 `_accept` 的四次编辑（时间戳，`evidence/protocol_violation_timeline.json`）：

| ts | `_accept` 版本 | 有 `session_confirmer` | 有 `executor` 形参 |
|---|---|---|---|
| 1792085247092 (04:27:27) | 初版（`load_candidate` 字段检查） | 否 | 否 |
| 1792085470854 (04:31:10) | 接入 `VerificationService` | **否** | 否 |
| **1792085511564 (04:31:51)** | 加 `StoreResourceStopper(session_confirmer=executor)` | **是** | **是** |

- **记录的 `runs/s1_independent__A/result.json`（含 `verify_state/verify_messages`）由 04:31:10 的版本产生**，
  其 `VerificationService(store)` 未接 confirmer ⇒ 消息为
  `"1 session(s) not confirmed closed (cleanup='pending')"`（**无 `adapter=[…]` 细节**，正是无 confirmer 的特征）。
- `executor=` 接线在 04:31:51 加入，但**预算耗尽，从未用真实请求运行**。
- **离线复现（`harness/offline_repro.py` A7）**：用**同型号的 fake session-lifecycle executor**（无 SDK/无网络）
  + **真实** `GraphDispatcher` + **真实** `PlanValidator`（冻结合法 plan）+ **真实** `VerificationService`
  + **真实** `StoreResourceStopper`：
  - teardown 事实齐（`close_ok=True`）：`verify_state=confirmed` → **`awaiting_acceptance`（accept_reachable=true）**；
  - teardown 缺一条（`close_ok=False`）：`unconfirmed`，且消息带 `adapter=['1 session(s) not confirmed closed by the adapter']`。
- **结论：停止门本身正确。** LG-023 的 `unconfirmed` 是「用一个还没接 confirmer 的 `_accept` 记录结果」所致，
  **不能归咎旧 LG-022 R2 停止门产品缺陷**。产品侧 `executor.confirm_stopped` 与 `StoreResourceStopper` 是好的。

### A8 — 计量/协议守卫（**旧 harness 真实缺陷，已离线复现**）

- 旧 `_accept` 之前的守卫：把 counter 的 `reserve` 包成 `_guarded_reserve`，但检查
  `getattr(result, "granted", False)`；而 `GenerationCounter.reserve()` 返回 **`bool`**，`bool` 上没有 `.granted`
  ⇒ **`guard.used` 永远 0**，即使真实 proxy 已经转发。
- **离线用真实 `LocalAuthProxy` + 本地 fake SSE upstream（loopback）复现（`offline_repro.py` A8）**：
  - 旧 wiring：6 次真实转发，`guard_used=0`、`ledger=6` ⇒ **每 attempt 上限完全未生效**（与旧 result.json 的
    `attempt_generation_requests: 0` 一致）；
  - 新 wiring：`guard_used=12`，13th 转发在**转发前**返回 429、`ledger` 不增 ⇒ 上限生效；
  - reviewer 风格 proxy（**无显式 budget**）与 worker 共享同一全局 counter（`ledger` 6→12）⇒ **全 stage 同账本成立**。
- 旧离线 `ledger_proof.py` 的 L1–L7 只测 **`PersistentGenerationLedger` 与未被真实 proxy 调用的 helper**，
  **没有**证明真实 `begin_call()→reserve()` 转发前扣减；这正是「测未被调用的 helper 然后生产 count=0」。
- **结论：旧 harness 的每 attempt 12 上限与逐 attempt 归因失效；全局 48 上限（持久 ledger）本身有效。**

### A9 — 旧 runtime 是否被 `TemporaryDirectory` 删除（**是，且造成关键缺口**）

- `_run_attempt` 用 `with tempfile.TemporaryDirectory()` 承载 `FileStore`（Task/Run/Subtask/Member 控制状态）、
  候选 git 工作区与初始 commit、secrets。**进程结束即删除**（如 `/tmp/tmpcugnc8bx`、`/tmp/tmp7ber8xy_`）。
- **幸存**：SDK 的 `/tmp/antigravity_*/**.db`（真实 session 轨迹 + per-generation 元数据）与 owner dispatch 转录。
- **缺口（记 `unknown`，不推断补造控制状态）**：原始 Task/Run 实体、candidate worktree/diff、raw proxy 请求日志。
- 旧 REPORT 的「`runs/`、`evidence/`、`ledger/` 保留全部失败原件」**只对部分 attempt 成立**（A3）。

---

## 2. 原件保全与恢复（只读；不覆盖旧字节；不因取证重跑真实任务）

私有持久目录（`700`/`600`，`sha256sum` + `cmp` 验证，源文件不删除，**不入 repo/prompt/输出 body/secret**）：

```
/home/yhvh/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/lg023-survivors/
  20261016T043718+1100-sdk-session-dbs/
    MANIFEST.sha256                    # 17 db + 1 recovered-usage json
    RECOVERED-gen-usage.json
    antigravity_<dir>__<id>.db  x17    # 真实 SDK session 轨迹（LG023 运行窗口 04:27–04:31）
```

- **恢复范围**：
  - **17 个真实 SDK session DB**（worker + reviewer 会话）：含原始 worker/reviewer 提示、tool calls、
    以及**真实的 per-generation token 用量**（`gen_metadata` protobuf 字段，已恢复为 `RECOVERED-gen-usage.json`）。
  - 这**补上旧 `unknown` 的一部分 usage**；但**不可**完全还原逐 attempt 拆分（A4）。
  - owner 原始转录 `dispatch-logs/lightgravity-pi-bounded-ogans7ad.log`（只读）——审计 A1/A2/A3/A7 的一手依据。
- **不可恢复（明确记录缺口）**：原始 FileStore 控制状态、candidate worktree/diff/初始 commit 对象、
  raw proxy 日志。**不推断、不补造控制状态或收据。**
- 旧 attempt 输出**不覆盖**：本次只读；旧 `runs/`、`evidence/`、`ledger/` 原字节保留
  （我在旧 worktree 误写一字节的 `harness_selftest.json` 已**还原为原 sha256** `4c37fdf6…`）。

---

## 3. 修复（harness，而非产品）

产品代码未改。修复落在**新建的未来协议 **草稿 harness**（`METHOD-AUDIT/harness/`）与对旧文 markdown 的
**追加**说明；不覆盖旧 harness。

### 3.1 accept 停止门正确接线（目标形态）

未来 attempt 采用**完整 ApiContext/Coordinator 装配**（参考已通过的 `qa/lg022-stream/harness/main_chain.py`）：
Task 经真实 `POST /tasks` 完成后由真实 `Coordinator`/`VerificationService` 走 `verifying → awaiting_acceptance`
与 `decide(accept)`；`create_app` 已把真实 `executor.confirm_stopped` 接成 `StoreResourceStopper` 的
`session_confirmer`（`backend/lightgravity/api/app.py`），**不需要也不可能**手工预填 `cleanup=done`、
删 refs、造 confirmed 或跳 SDK 停门。离线复现证明：只要 teardown 事实齐，同线装配即达 `awaiting_acceptance`。

### 3.2 计量/协议守卫（目标形态）

- **单一持久 ledger**：全 phase 一个 `phase data_dir`；worker/reviewer/失败/返修共用。
- **每 attempt 12 在真实转发前强制**：把有界 guard 装在**全局 counter** 上（并 `_GLOBAL_GENERATION_COUNTER=…`），
  使 worker 与 reviewer 的 `LocalAuthProxy.begin_call()→counter.reserve()` 都受同一上限；
  **返回 `bool` 语义**（不是 `.granted`），离线用真实 proxy + 本地 fake upstream 证明。
- **总 48 不可绕**：持久 ledger 硬上限；超限/损坏 fail-closed、绝不当 0。
- **attempt 总数 4、每个只 1 次正式 run**：由外层 runner 编排；任何 harness 错误 → **整 cohort 停止并报告偏差**，
  **不得**改提示/工具/测试真值/样本/预算后继续沿用冻结 protocol。
- **输出只创建不覆盖**：按不可变 `attempt-id` 命名；SDK 资料 / Run/Task/Subtask 原始 SoT / worktree
  放**项目旁持久目录**（**严禁 TemporaryDirectory 承载关键运行/未交付 diff**）。

### 3.3 冻结新协议（草稿）

未来 cohort 沿用：两样本（S1 independent / S2 interface）、双 arm（A 单 worker / B 双 worker 带 hash 交接）、
**双方同模型/预算/工具/提示模板/初始 Git tree/验收门**。差异**仅**为计划写节点数（A=1，B=2 依赖）。
- **可写入未来新协议的提示效率修正**（来自前 cohort 真实观测，但**必须双方完全相同**且**在首个新真实请求前冻结**）：
  直接覆盖 stub、最小 turn、`edit-file`/`create-file` 允许。
- **工具调用 cap**：已知 10 过低（前 cohort `MAX_TOOL_CALLS_EXCEEDED`）。未来需在**首个新真实请求前**为**双方**
  冻结一个相同、有实际依据的足够值（依据：真实双 worker 链约 10 生成 + 观察到的 tool-call 上限）。
  **不增加产品默认容量**。
- **明确旧 45 全部为 protocol-deviation 失败成本保留**，不与未来 cohort 混算。
- **强制合法 plan** 若继续使用：明确**只比较「计划写节点数」**，不冒称产品自动规划能力。
- **不对未知 gain 作正面选择性结论**。

## 4. 离线证明（**真实模型 0**）

| 证明 | 脚本 | 结果 |
|---|---|---|
| stopgate：teardown 齐→`awaiting_acceptance`；缺→`unconfirmed` | `METHOD-AUDIT/harness/offline_repro.py` A7 | pass |
| 计量：新 wiring 上限生效、13th 转发前 429、reviewer 共享账本 | 同上 A8 | pass |
| 计量：旧 wiring 生产 `count=0`（缺陷复现） | 同上 A8-old | pass |
| fixtures 初始必败 / reference 必过 | 旧 `harness/validate_fixtures.py`（离线） | pass |
| 冻结合法 plan 过真实 `PlanValidator` + attempt guard | 旧 `harness/selftest_offline.py`（离线） | pass |
| 持久 ledger L1–L7（硬上限/跨进程/损坏 fail-closed） | 旧 `harness/ledger_proof.py`（离线） | pass |

证据：`METHOD-AUDIT/evidence/offline_repro.json` 及旧 `probes/lg023/evidence/offline/*.json`。
**未用 fake executor 过门冒充实验成功**：A7 的 fake 只用于证明 harness 接线，不代表真实 cohort 结果。

## 5. 成本与计数（准确，未知记 unknown，不归零）

- **旧 LG-023 cohort 真实生成：45/48**（总数可核）。逐 attempt 归因**不可信**（A4）。**全部保留为失败成本。**
- **本审计包真实生成：0**。开发侧 pi dispatch token/time **单列/shared**（非 runtime 账本），不当 0、不混算。
- **usage**：旧 `unknown` 部分由 17 个 SDK session DB 的 per-generation token 计数**恢复**（非全量）；
  费用仍 `unknown`（无可核费率）。**不据失败样本中位数推断收益。**
- 旧 022（unknown+6+8+5/10）、031（34/40）单列。

## 6. 缺陷清单（最小 repro，交 PM；不自修自验）

| # | 级别 | 描述 | 归属 | 最小 repro |
|---|---|---|---|---|
| D1 | harness（非产品） | `_accept` 未接 `session_confirmer` 时记录 `unconfirmed`，被误标「停止门未闭合」 | 旧 harness | `offline_repro.py` A7（broken_close） |
| D2 | harness | attempt guard 在 `bool` 上取 `.granted` ⇒ 每 attempt 上限不生效、`count=0` | 旧 harness | `offline_repro.py` A8-old |
| D3 | 方法 | 冻结后改提示/工具集、反复重跑 S1/A、覆盖结果路径、`TemporaryDirectory` 删关键运行 | 旧 cohort | `evidence/protocol_violation_timeline.json` |

- **产品代码未发现须立即修复的缺陷**：stopgate/`confirm_stopped`/`LocalAuthProxy` 计量与
  `qa/lg022-stream` 已通过的主链一致。**若未来复现疑似产品缺陷，报最小 repro 交 PM，不自修自验。**

## 7. 明确的结论（限定）

- 旧 cohort **不能作为「冻结正式对照完成」**；**不支持**任何组队 vs 单 worker 的 token/成本收益结论。
- 可核实：**单个真实 SDK worker 能完成一个小型两文件交付并过机器门 + 独立复核**（旧 #4 的机器门 6/6 +
  reviewer passed 仍有效），但**其版本验收门结果无效**（A7），且该 attempt 处于已变更协议下。
- **组队 arm 仍缺最终协议数据**；需**新预算 phase**，且**先由 PM 预注册** budget/样本/门。

## 8. 需要 PM 预注册的唯一下一 phase 步骤

**在发出任何新真实请求之前**，PM 须先书面预注册（本包不执行）：

1. **样本与门**：沿用 S1/S2、A/B 双 arm、双方同模型/预算/工具/提示/初始 tree/验收门。
2. **预算两级规则**：总真实生成上限 **T** 与**每 attempt 上限 P**（建议 P ≥ 观察到双 worker 链所需，避免
   一方被预算误判），**全 stage 单一持久 ledger**，超限/损坏 fail-closed。
3. **attempt 总数 = 4，每个只 1 次正式 run**；任何 harness 错误 → 整 cohort 停止报告偏差。
4. **持久目录**：`phase data_dir`、候选 worktree、SoT、输出均放项目旁持久目录；
   输出按不可变 attempt-id **只创建不覆盖**。
5. **工具 cap**：为**双方**冻结同一有依据的足够 tool-call cap（不改产品默认）。
6. **旧 45 明示**为 protocol-deviation 失败成本，不入新账本、不洗 0。
7. **验收**：机器门 + 独立 reviewer + 版本验收门（真实 stopgate 接线）齐，才可 `awaiting_acceptance` + bind accept。

本包已把可复现 harness 与离线证明就绪；**下一 phase 的启动取决于 PM 预注册，而非本报告**。

## 9. 证据索引

- 审计原文/计划：`probes/lg023/METHOD-AUDIT/{PLAN,STATUS,REPORT}.md`。
- 审计证据：`METHOD-AUDIT/evidence/{offline_repro,arm_start_tree_check,ledger_recount,protocol_violation_timeline,survivors_index}.json`。
- 离线复现：`METHOD-AUDIT/harness/offline_repro.py`。
- 私有幸存原件：`~/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/lg023-survivors/**`（`700`/`600` + `MANIFEST.sha256`）。
- 旧 cohort 原件（保留，未覆盖）：`probes/lg023/{runs,evidence,ledger}/**`、`harness/**`。
- 产品只读参考（未改）：`backend/lightgravity/verify/{service,stopgate}.py`、`adapter/{executor,proxy}.py`、
  `api/{app,bootstrap}.py`；`qa/lg022-stream/harness/main_chain.py`。

**不推送/不部署/不发布。LG-023 保持 `in-progress`。**
