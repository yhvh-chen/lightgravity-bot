# REPORT — LG-048 诊断选定资料交付预算与最小验证链（M-DELIVERY-DIAGNOSIS）

- 日期：2026-10-16
- 任务：LG-048（P0，`depends_on: [LG-046]`，owner/assignee `agent:pi-delivery-diagnosis`）
- 模式：**零模型调用、只读诊断**。本包不发起任何真实模型/网络请求，不改产品代码、测试、依赖、I 活动 worktree/campaign/ledger。
- 诊断仓库基线：`main` @ `0188ca2`（PM 文档提交）；产品代码只读自 `0188ca2` 树。
- 只读证据来源：I-R2 活动 QA worktree `proto-material-qa-r2-20261016`（`qa/proto-material-r2-20261016` @ `a9ba494`）的 REPORT/evidence/raw/campaign ledger。**未修改、未杀进程、未重跑。**

> 结论摘要：R2 的 429 是**进程全局持久 8 次硬上限**（`LIGHTGRAVITY_MAX_GENERATION_CALLS=8` + 持久账本），**不是** per-node 配额；默认确定性文件交付规则计划是 **deliver + verify 两个 SDK worker 节点**（非单 worker）；R2 attempt1 的 `1006` 是 **QA harness 提前关闭**（非产品缺陷）；R2 真实产出一个正确 deliverable 但被第二个（verify）SDK 节点耗尽全局预算后 `failed`，reviewer/stop-gate/accept 从未到达。recommended next task = **先做零模型确认，不改代码**（详见 §5）。

---

## 1. 问题 (a)：429 = 本地预算 / 全局持久 8 上限 / per-node 配额？

**判定：全局持久硬上限（8）在转发前拒绝，是唯一、具约束力的原因。**

代码/配置/raw 精确引用：

1. **拒绝点**：`backend/lightgravity/adapter/proxy.py`：
   - `LocalAuthProxy` 在转发前调用 `self.generator_budget.reserve()`，`False` 时返回
     `429 {"error":{"message":"local auth proxy call budget exhausted"}}`（`proxy.py` 第 382–383 行；`reserve` 咨询第 293 行）。
   - `GenerationCounter.reserve()`（`proxy.py` 第 ~118 行）：当挂载 `PersistentGenerationLedger` 时委托 `self._ledger.reserve().granted`；否则进程内 `_count >= _limit` 拒绝。docstring 明确：**该计数被每个 `LocalAuthProxy` 共享**、**转发前**咨询，覆盖 worker session、reviewer turn 与 SDK 重试；“per-proxy budgets reset for every session/reviewer/retry”，而全局计数不重置。
2. **上限来源**：`_limit_from_env()` 读 `LIGHTGRAVITY_MAX_GENERATION_CALLS`（`proxy.py` 第 165 行）。R2 QA harness 在启动产品前设置 `os.environ["LIGHTGRAVITY_MAX_GENERATION_CALLS"] = str(args.max_generation_calls)`，`--max-generation-calls` 默认 **8**（I-R2 `scripts/launch_app.py` 第 113–114 行、第 102 行）。
3. **持久性**：`api/bootstrap.py` 第 401–421 行：`configure_generation_ledger(settings.data_dir)` 后，真实执行器被注入**同一个** `global_generation_counter()`（持久账本），使每个 worker/reviewer 的 loopback 代理消费**同一持久硬上限**，跨重启不归零、不按 worker/session 重置。
4. **per-node / per-session 上限不是本次约束**：
   - `AntigravityExecutor(max_proxy_calls=8)`（`bootstrap.py` 第 120、414 行；`executor.py` 第 364 行默认 8）— 这是**每个 session 代理**的上限，会随 session/node 重置，**不是** 429 的原因。
   - `model_calls_cap` 默认 `None`（`bootstrap.py` 第 121 行），本 campaign 未设置。
   - 执行器会把 per-request `budget.max_model_calls` 收进 `min(ceilings)`（`executor.py` 第 587–600 行）。但 **attempt2 的 Run 实体没有 `budget` 字段**（`campaign/product-data/runs/run_01M522S1WSYE67ASEXF0T1YPNE/RUN.md` 未出现 `budget`；只有 `fail_reason`），因此节点**未冻结** `max_model_calls`，该 per-node 分支不会先于全局上限触发。
5. **raw 序列（决定性）**：`campaign/product-data/generation/generation.jsonl`：

   | count | pid | reserve_id | ts |
   |---|---|---|---|
   | 4 | 3932172 | `...-1792145133370-1` | 1792145133.37 |
   | 5 | 3932172 | `...-1792145135846-2` | 1792145135.85 |
   | 6 | 3932172 | `...-1792145138260-3` | 1792145138.26 |
   | 7 | 3932172 | `...-1792145140071-4` | 1792145140.07 |
   | 8 | 3932172 | `...-1792145143027-5` | 1792145143.03 |

   同 pid 3932172 在 ~10 秒内连续预留 5 次（count 4–8），把全局计数推到 **8**。下一次转发（verify 节点的首个模型调用）被 `reserve()` 以 429 拒绝。
   `generation.count.json = {"count":8}`；`campaign/history.jsonl` 已对账到 **8/8, remaining 0**（REPORT-I-R2 §4.2、§7）。

**因此**：deliver 节点自身消耗了约 4 次前向（count 4–7），第 5 次（count 8）把全局计数推满；verify 节点一开始就撞上**已满的全局 8 上限**。per-session/per-node/per-request 上限均非本次触发原因。

---

## 2. 问题 (b)：默认文件计划是单 worker 还是双节点？如何与既有设计相交？

**判定：默认确定性通用文件交付计划产出两个 SDK worker 节点（`deliver` + `verify`），不是单 worker。**

代码精确引用：

- `backend/lightgravity/coordinator/planner.py` `RulePlanner.plan`（第 299–338 行）：
  - 恒生成 `deliver`（`capability="implementation"`, `write=True`）。
  - `acceptance = declared or default_acceptance_criteria(context.objective)`；**当且仅当 `declared` 非空**，追加 `verify`（`capability="verification"`, `write=False`, `depends_on=("deliver",)`）。
  - 注释声称“derived default keeps the prototype's minimal single-worker plan (docs/10 §7)”——该“单 worker”仅在 **`declared` 为空**时成立。
- 但**普通 Chat 文件交付**的默认路径**永远声明**验收条件：`service.py` `_route_global` 的 `create_task` 分支调用 `_create_task_locked(default_delivery=True)`（`service.py` 第 693–705 行）；`_create_task_locked` 在 `default_delivery` 且 `acceptance` 为空时用 `default_acceptance_criteria(objective)` **填充**验收（第 559–566 行），并把该 `acceptance` 写入 Task（`_task_content(..., acceptance=acceptance)`）与 Run body。`_build_context` 从 Task body 读取 `acceptance_criteria`（`service.py` 第 1594–1617 行）→ `DispatchContext.acceptance_criteria` 非空 → `RulePlanner` 追加 `verify`。
- **raw 直接证实**：attempt2 的 `RUN.md` plan.subtasks 含 **两个**条目：`deliver`（order 0）与 `verify`（order 1，`acceptance` = 同一条 program-derived criteria，`depends_on: [deliver]`）；`plan_source: rules`，`plan.notes: "minimal rule plan: deliver + optional verify"`。`node_sessions` 有**两个真实 session**：deliver（`node_state: passed`）与 verify（`node_state: failed`，429）。两个节点都使用 `role_ref: lg-default-worker`（同一默认 worker 角色）。

与既有设计的关系：

- **verify 节点 ≠ 独立 ModelReviewer**。`verify` 是计划里的第二个 **SDK worker turn**（`capability: verification`），走同一 executor/同一 worker 连接（RUN.md `connection_pin` 单一 `conn-worker`），其结论只进入 `verifying` 阶段前的**程序机器门**（LG-009）。真正的**独立复核**是 `verifying` 阶段用**独立角色/连接** `default_reviewer_connection_ref` 的一次 reviewer turn（docs/08 §9、§6.5；`1.7.0`）。两者是不同的东西，不能互相替代。
- docs/10 §7 明说“保持既有**单 worker 原型默认规则计划**；不自动引入 search/project/MCP/ASR/Office/**模型 planner**”。当前实现与 §7 的“单 worker”措辞**存在张力**：当 Task 声明验收（普通交付必然如此，因为 R1 修复为让 PlanValidator 通过而派生验收）时，实际是双 SDK 节点，而非单 worker。
- **不得假定“移除 verify 节点”已被授权**：`verify` 是程序机器门/独立验证边界的一部分；把它删掉会**削弱**验证护栏，属于产品语义变更，需 PM/契约决策，不能作为诊断包的隐含结论。如果目标真的是“单 worker + ModelReviewer”的 rapid-prototype，正确方向应是：在**不弱化 guard** 的前提下，让 verify 从**独立的 SDK 模型节点**改为**程序机器检查**（LG-009 语义），或明确将 ModelReviewer 作为唯一独立验证，并同步 docs/10 §7 与契约。**本诊断不做该取舍，仅指出实现与文档的偏差。**

---

## 3. 问题 (c)：首个 SDK 1006 是 harness/测试提前关闭还是产品复现？

**判定：是 QA harness 缺陷（提前 kill），不是产品缺陷，也不是可复现的产品失败。**

`evidence/sdk_attempt1_harness_bug.json` + REPORT-I-R2 §4.0 精确记录：

- attempt1 仅运行 **2.28 s**。根因是 QA driver 的 poll 辅助函数在**第一次调用**就把任务 phase 当作终态（phase 字符串恒非空），于是 driver 在 worker turn 仍在运行时退出；`with_server.py` 的 `finally` 随即对服务器进程组 `killpg(SIGTERM)`，SIGTERM 到达 antigravity localharness **mid-turn**，WS 关闭码 **1006**，Run 失败。
- 产品侧当时已做对：分类 `delivery → create_task`、`plan_source: rules`、program-derived acceptance、授权 workspace、selected binding、`conn-worker` openai-compat。**产品无缺陷。**
- 这是**诊断后修正一次**（poll 真正终态再 teardown），不是盲目重试。attempt2 用修正后的 harness，SDK worker 正常产出 deliverable。

结论：`1006` 归因 **QA harness/测试提前关闭**；无产品侧复现证据。

---

## 4. 问题 (d)：真实 SDK toolcall/reviewer 最小/观测计数与安全有界后续预算

### 4.1 已观测的真实计数（来自 raw，不推断）

- R2 全局持久计数 **8/8**（`generation.count.json`）。8 次预留中：
  - count 1 = N4 意外真实直答（harness 误 payload，非计划内）。
  - count 2 = chatflow 真实 UI 提问（真实回答，4 事实正确）。
  - count 3 = SDK attempt1 的 1 次前向（被 1006 中断）。
  - count 4–8 = SDK attempt2 的 5 次前向（deliver 约 4 次 + 第 5 次推满全局上限；verify 首调被拒）。
- **deliver 单节点的真实模型调用约 4 次**（一次多步 worker turn）。**verify 节点调用数观测不到**（其首个前向即被 429 拒绝，计数为 0 成功前向）。
- **独立 ModelReviewer（`verifying` 阶段的 reviewer turn）在 R2 从未执行**：Task 在 verify 节点 429 后进入 `failed`，从未到达 `verifying`；因此**reviewer 的真实调用数在本次不可观测**。代码默认值是 `DEFAULT_REVIEW_MODEL_CALLS = 1`（`verify/review.py` 第 476 行）——这是代码默认，**不是**本次实测，须在后续 campaign 中真实观测。
- 停止门（stop-gate CONFIRMED）与 QA user accept 在 R2 **均未到达**，均为 **UNVERIFIED**（REPORT-I-R2 §4.4、§8）。

### 4.2 最小/安全的有界后续预算（提案，非授权）

给出**精确、可分项、可通过 429 观测**的提案（含失败与 reviewer）。关键：全局上限必须 ≥ 一次完整成功链（deliver 4 + verify 4 + reviewer 1 + 余量），才能在一次 campaign 内**到达** reviewer/stop-gate/accept，而不是在 verify 即耗尽。

建议把**全局持久硬上限**与**campaign 观察上限**分开：

| 项 | 建议值 | 依据 |
|---|---|---|
| deliver 节点（1 次多步 worker turn） | ≤ 5 | 实测约 4；+1 余量 |
| verify 节点（第 2 个 SDK worker turn，若保留） | ≤ 5 | 对称；实测未得，按同规模估 |
| 独立 ModelReviewer（1 次 reviewer turn） | ≤ 2 | 代码默认 1，留 1 余量 |
| 失败/重试余量（1 次失败尝试） | ≤ 3 | attempt1 观测 |
| **完整成功链一次性可完成所需全局硬上限** | **≥ 15** | 5+5+2+3 = 15 |
| **含 1 次可容忍整体失败重跑的 campaign 上限（若 PM 接受双尝试）** | **≥ 22**（15×1.5 取整） | 单次 15 + 半次 |

**如果 PM 选择做问题 (b) 的“不弱化 guard 的 verify→程序机器检查”收敛**（即 verify 不再消耗 SDK 调用，只留 1 个 deliver + 1 个 reviewer）：则一次成功链 ≈ deliver 5 + reviewer 2 = **7**，加失败余量 3 = **10**。此路线更省预算且更贴合 docs/10 §7 的“单 worker”，但**须先经 PM/契约决策**，本诊断不擅自定案。

> 硬约束：以上均为**提案**，需 PM 明确授权后才能写入下一 campaign。本包**不发起任何请求**。建议下一 campaign 的账本须能**分别记录** deliver/verify/reviewer/retry 的前向数（当前 429 只表明“全局满”，无法事后区分节点消耗；这是下一 campaign 应修补的观测缺口）。**未观测到 reviewer 与 accept 前，不得宣称 R3 通过，也不得宣称累积成本已知。**

---

## 5. 建议的下一任务（精确）

**若无需代码修复，明确说明：需要一处产品/文档取舍后才能谈“最小验证链”，但严格意义上“是否存在产品缺陷”尚未被证明——需先做零模型确认，不必立即改代码。**

1. **推荐（零模型、零产品改动，P0，可选本诊断的下一步）**：零模型确认任务 —— 用**现有代码库的单元/集成测试**（非真实模型）确认：
   - `RulePlanner` 在 `declared` 非空时确实追加 `verify`（已有/补测 `tests/coordinator/test_planner*.py`）；
   - `default_delivery=True` 路径确实给 Task 写入派生 `acceptance`，使普通 Chat 交付走双节点（`tests/coordinator/...`）。
   这两点是本诊断的核心断言，用**离线**测试即可钉死，无需任何模型前向。
2. **随后（PM 决策，非本包）**：决定 (b) 方向（保留双 SDK 节点并把全局上限提到 ≥15，或收敛为“1 worker + ModelReviewer”并同步 docs/10 §7/契约）。**移除/降级 verify 会削弱 guard，需显式授权**，不得由一个 QA/诊断包默认。
3. **再后（PM 授权的新 campaign，独立账本）**：以 §4.2 的全局上限跑**一次**完整链以到达 reviewer/stop-gate/accept；账本按节点分列。**授予前不发起任何请求。**

**本诊断的 scoped 分类**：
- **产品缺陷（已确证）**：无“会产生错误结果”的缺陷被确证。观测到的是**可靠性/预算边界限制**（一次成功交付可被第二个 SDK 节点耗尽全局预算后整 Task `failed`），以及**实现与 docs/10 §7“单 worker”措辞的偏差**。二者需 PM 处置，非“代码写错”。
- **QA/harness 缺陷**：attempt1 的 `1006`（driver 提前 teardown）、chatflow 19/20 的断言缺陷（断言 6 事实、问题仅问 4）均为 **QA harness 缺陷**，非产品缺陷。REPORT-I-R2 已如实标注。
- **分类器假阳性**（`approve` 命中 `approved`）：已由 J 在 `2352c52` 修复并合入 `7e433c3`，属**已修复**项；其独立复验仍归 LG-047 后续（本诊断不改代码、不宣告修复通过）。

### 重要剩余风险（important remaining risks）

1. **观测缺口**：全局 429 无法区分 deliver/verify/reviewer 消耗；下一 campaign 账本必须先补此分列，否则预算仍不可审计。
2. **reviewer/stop-gate/accept 完全未验证**：任何“交付链已通过”的说法目前不成立。
3. **verify 是 SDK 节点而非程序检查**：这使每个交付额外承担一个模型 turn 的预算与失败面，并与 docs/10 §7 的“单 worker”表述冲突；若不处置，任何正常交付都可能因第二个节点耗尽全局上限而 `failed`。
4. **累计成本未知**：产品未对每次前向报告 token；`cost unknown but non-zero`（REPORT-I-R2 §7）。不得把未知当 0，也不得据此推断全生命周期上界。
5. **R2 8/8 已耗尽，不可重跑**；不存在 R3 的既成事实。

### 本包不做什么（边界）

- 不发起任何真实模型/网络/浏览器请求；不跑 SDK 本地 stub 反复诊断；不碰 `8123`。
- 不改产品/测试/依赖/前端代码；不修改 I 的活动 worktree/campaign/ledger；不杀进程。
- 不宣告 R3 通过、不宣告累积成本已知、不宣告 LG-047 done。

---

## 附录：证据索引（只读引用，均未修改）

- I-R2 REPORT：`proto-material-qa-r2-20261016:probes/prototype-selected-material-20261016/I-R2-QA/REPORT-I-R2-20261016.md`（§4.0/§4.1/§4.2/§4.3/§7/§8）
- RAW attempt2：`.../I-R2-QA/raw/sdk-attempt2/{RUN.md,task-events.jsonl,generation.jsonl,driver.json,server.log,orion-summary.md}`
- RAW attempt1 harness bug：`.../I-R2-QA/evidence/sdk_attempt1_harness_bug.json`
- campaign ledger：`.../I-R2-QA/campaign/product-data/generation/{generation.jsonl,generation.count.json}`、`.../campaign/history.jsonl`、`.../raw/campaign_manifest.txt`
- 产品代码（`main` @ `0188ca2` 只读）：`backend/lightgravity/adapter/proxy.py`、`.../adapter/executor.py`、`.../adapter/generation_ledger.py`、`.../api/bootstrap.py`、`.../coordinator/planner.py`、`.../coordinator/service.py`
- 契约/设计：`docs/08-interface-contract.md` §9/§6.5/§13、`docs/10-selected-material-prototype.md` §7
