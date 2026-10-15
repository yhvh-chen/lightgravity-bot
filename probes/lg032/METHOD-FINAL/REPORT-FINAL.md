---
title: "LG-032 METHOD-FINAL 独立方法审计报告"
doc_type: report
category: engineering
status: "PASS (recommend Ready for formal 4-attempt); formal NOT run; real provider 0; 032 still in-progress"
experiment_id: lg032-fair-ablation-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final
branch: qa/lg032-method-final
base_commit: "a4b4455"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-method-final（独立方法审计 owner；非 harness/产品作者）"
---

# LG-032 METHOD-FINAL 独立方法审计报告

> 本报告 = **独立方法审计**（新 pi context，非 harness/产品作者）的完整结果。
> **正式采样 0**；不改产品源 / 既有 harness 逻辑；只新增 `probes/lg032/METHOD-FINAL/**` 与冻结
> manifest / PLAN 补遗。旧报告字节保留；**不写 done**；**不 merge main**。

## 0. 结论（先给判断）

- **审计结果：PASS**（门A/B/C/D/F 全过）。
- **是否够进入正式 4 attempt：够**（`recommend Ready`）。**但本包不执行正式采样**，须 PM 另派 owner。
- **LG-032 仍 in-progress**；产品真实 provider 生成 **0**；正式 `lg032-method-final-data` **不存在**。
- **正式入口**：`probes/lg032/METHOD-FINAL/probes/run_formal.py`（先装 overlay，再走字节同 cohort-ready 的冻结驱动）。

## 1. 基线与身份核对

| 项 | 值 |
|---|---|
| 本 worktree / branch | `/home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final` / `qa/lg032-method-final` |
| base | `a4b4455`（`qa/lg032-cohort-ready`） |
| 产品 tree 对象 | `55e4de56…`（**== main == `0814b80`**，逐字节同；只读未改） |
| 独立边界 QA | `lg031-boundary@70a0fd5`（产品 tree 同 `55e4de56…`） |
| SDK / 契约 / 模型 | `google-antigravity==0.1.22` / `1.11.0` / `deepseek-v4-flash` @ `https://api.deepseek.com/v1` |
| seed pin（实际 commit） | s1 `53458ac7…`（tree `119aaa4d…`）、s2 `6fa0fd00…`（tree `bc96ccc4…`） |
| 本 worktree `.venv` | `uv sync --frozen` 新建（SDK `0.1.22` 已核） |

- 核 `git status` 开始时干净；产品与既有 harness **无 diff**；formalRoot 不存在 ⇒ formal 0 确认。

## 2. 独立方法门与证据

### 门A — A/B 同质性 + seed SHA（`probes/gateA_homogeneity.py`）

- canonical plan hash **A==B**：s1 `4611722753542c1a…`、s2 `df60b54828a62324…`；两 arm 均
  `alpha(impl,write)`+`beta(impl,write)`+`verify(verification,read-only,depends both)`；
  product `plan_hash` 仅因 arm tag（source/notes）不同（不影响公平维度）。
- 静态 AST 分类：恰好 **2** 个 `arm=="B"` 分支，**均为**协作开关（`_enable_decentralized_pool` /
  `_autonomous_pool`）；无任何其它 arm 分支改 plan/member/tool/objective/caps/truth。
- **seed 实际 SHA 可复现**：从 `fixtures/<s>/initial` 用固定身份/时间戳独立重建两次，均 `==` 已 pin 的
  `seed.sha256`（s1 `53458ac7…`、s2 `6fa0fd00…`）；故 A/B 从**同一实际 commit 对象**出发。
- 共享身份哈希：sample objective/acceptance、`acceptance.py` truth、role catalog、worker/verifier
  工具与提示、caps（12/32/1/16000/120/0/1）均 arm 无关。

证据：`evidence/gateA-20261015T203739Z.json`（`ok=true`）。

### 门B — 真实注入 + 单物理 ledger + 边界（`probes/gateB_ledger_boundary.py`）

独立 scratch `lg032-method-final-boundary`（**formalRoot 未创建**）：

- **真注入**：真 `build_runtime` → 真 `executor._make_proxy`（产品注入 `global_generation_counter()`）
  3 次 → count **3** / 物理 JSONL **3** 行；真 `verify.review.run_review_turn`（产品 `ModelReviewer`
  实际调用的同一函数）→ count **4**（**reviewer 与 worker 共扣同一物理 ledger**）；同 root 二次
  `build_runtime`（restart）→ start2 count **4**（**持久不归零**），再 2 次 → count **6** / 6 行。
- **48 转发前拒**：真 `_AttemptGuard`（冻结驱动的逐 attempt 上限）+ 真 `LocalAuthProxy`：48 次 `200` 后
  index 48/49 均 `429`；count 钉 **48**；物理 **48** 行 ⇒ **denied 不 forward**。
- **total cap 小等价**：cap=3 → index 3/4 `429`；count 钉 **3**。
- **corrupt fail-closed**：写坏物理 `generation.jsonl` 后真代理 `200`→`429`；snapshot `corrupt=true`、
  `count=null`（**绝不当 0**）；直连 `PersistentGenerationLedger.reserve()` 亦拒。

> 关键：计数对象是**产品自身注入**的 counter（非 helper 伪造），且实际经**真 executor/reviewer 代理**转发。

证据：`evidence/gateB-20261015T203840Z.json`（`ok=true`）。

### 门C — 机器 truth 绑定 + 无伪造（`probes/gateC_truth_binding.py`）

- **空 authorized checks 危险已证**：`CheckReport.satisfied` 对空结果为 **vacuous True**（若用空 Task checks
  即冒充机器 pass）——故冻结驱动**必须**授权产品自有 `evidence-present`。
- `evidence-present` 在**产品默认 registry** 下：无证据 ⇒ `failed`（阻塞）；有证据 ⇒ `passed`。
- `VerificationService.verify_and_prepare`（真服务）：无证据 ⇒ `unconfirmed` **不开 acceptance**；
  有证据+真 stop 门 ⇒ 开 `awaiting_acceptance` 且 acceptance **绑定真实 `check_records`**
  （`{check_id: evidence-present, status: passed}`）。
- **静态无伪造**：驱动经真 HTTP `/tasks/{id}/actions` accept；无手写 `phase=awaiting_acceptance` /
  `cleanup=done` / `state=accepted`；无 monkeypatch stop/root；`LG032_WIDEN_EXEC_ROOT` 为**响亮拒绝**；
  `FakeExecutor` 不存在；accept 门 gated on real truths（machine+reviewer+session+teardown）。

证据：`evidence/gateC-20261015T204020Z.json`（`ok=true`）。**审计副产品**：证明驱动用 `evidence-present`
授权是**必要**且**有效**的机器门，而非空 checks 冒 pass。

### 门D — 独立跑 B 的 s1/s2 各一次 0-fake（`probes/run_method_dry.py` + `probes/gateD_independent_B_audit.py`）

真产品入口 + 真 SDK `0.1.22` + loopback fake 上游（dummy 凭证，**无真实出网**）：

| 项 | s1_units__B | s2_pipeline__B |
|---|---|---|
| rc / ok | 0 / **true** | 0 / **true** |
| 机器门 | **5/5** | **7/7** |
| session refs（真） | 6 | 6 |
| reviewer teardown | `confirmed=true` | `confirmed=true` |
| review validated | `passed` | `passed` |
| candidate diff | 2（per-node，非碰撞 run 级） | 2 |
| evidence-present check_record | `passed`（4 refs） | `passed`（4 refs） |
| accept | bound `confirmed` | bound `confirmed` |
| 幂等（同 request_id） | confirmed | confirmed |
| 错 target | `409` 拒 | `409` 拒 |
| `cleanup.status` | **`pending`**（但真 adapter stop 确认使其过门） | **`pending`** |
| seed_head == initial_head | `53458ac7…` | `6fa0fd00…` |
| requests | 16（≤48） | 16 |
| generation_final | persistent count 16 | persistent count 16 |

- **fake 相位分类独立核对**：每条 fake 请求的 phase 与其**产品真实信号**一致 —— `selection` 带产品冻结
  哨兵 `PHASE 1` 且无写工具；`execution` 带写工具；`verify` 带 `view_file` 且无写工具；`review` 无工具。
  s1/s2 各 `{selection:9, execution:4, verify:2, review:1}`，**0 misclassified**。此即旧 `missing_gates`
  中 "fake-upstream phase classification vs real product phases (NOT DONE)" 的独立闭环。
- **`cleanup.status=pending` 仍到 accept** ⇒ 停止门由**真适配器 `confirm_stopped`** 授权，而非手写 `cleanup=done`。

证据：`evidence/gateD-20261015T204123Z.json`（`ok=true`），完整 stdout `evidence/logs/s1B-*.stdout`、
`evidence/logs/s2B-*.stdout`（600），captures `evidence/dry_captures/*-B.json`。

### 门F — formal 路径冻结（`probes/gateF_formal_freeze.py`）

- 正式 phase root = `/home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final-data`（**唯一、尚未创建**）。
- env pin（`LIGHTGRAVITY_GENERATION_LEDGER_DIR`/`LIGHTGRAVITY_DATA_DIR`）与产品
  `configure_generation_ledger(settings.data_dir)` **同指一个目录**（驱动把 phase root 直接作 `settings.data_dir`）
  ⇒ **不存在 env pin 又被 bootstrap 覆盖**。
- attempt id 不可变（存在即拒）；4 个固定 id；`_AttemptGuard`=48、env total=192；`runs`/`evidence`
  输出重定向到 `METHOD-FINAL/**`（不写只读 `FINAL-COHORT`）。

证据：`evidence/gateF-20261015T204144Z.json`、`evidence/gateF-20261015T204245Z.json`（`ok=true`）。

## 3. A 证据引用（精确 hash 一致前提）

- 本 worktree `run_attempt.py` sha256 = `d1994948…`，与 `qa/lg032-cohort-ready@a4b4455` **逐字节相同**。
- 故 `s1_units__A`（`20261015T203344Z-s1A-fair`）与 `s2_pipeline__A`（`20261015T203351Z-s2A-fair`）
  的 0-fake A 证据**可引用**（同 driver、同 3 节点 plan、同 seed）。
- **旧 B 证据不可引用**（旧 driver `fbbbb81e…` / 旧混淆 4-node 计划）；本包已用新驱动**重跑 B**（门D），
  **不改 pin、不洗旧失败**。

## 4. 正式采样冻结（详见 `FORMAL-FREEZE.md` + manifest）

- 4 attempt：`s1_units__A`、`s1_units__B`、`s2_pipeline__A`、`s2_pipeline__B`（各一次）。
- 唯一 phase root 贯穿 4 attempt；per-attempt 48 / total 192 **转发前硬拒**；失败同 ledger。
- caps：`output≤16000`、`HTTP 120s`、`SDK retry 0`、`max_parallel=1`、worker 12/32、reviewer 1、
  至多 1 业务 repair（两 arm 同）。
- 唯一自变量 = 协作开关；`decentralized_claim_enabled`/`autonomous_pool` 默认 **off**。

## 5. 准确计数 / 未知（不洗 0）

- **本包真实 provider 生成 = 0**（全程 loopback fake / dummy 凭证）。
- **正式预算 4×48=192 仍为 0**（formalRoot 不存在）。
- 本包 0-fake：门A(1) + 门B(独立 scratch) + 门C(本地) + 门D(2 个 B attempt，各 16 fake 请求) + 门F(静态)。
- **旧成本单列不清零**：旧 LG-031 工程 **86**；旧 023 cohort1 **45** / cohort2 **4** / cohort3 **16**；
  023 eval **65**；core **unknown**。
- **unknown 不记 0**：所有 pi 开发 QA / shared 成本 = **unknown**。

## 6. 未做 / 边界

- **未做**：正式采样、freeze *approved*（仅 candidate）、mark 032 done、main merge/push/deploy/publish、
  嵌套代理、碰 `8123`、改产品源/caps/root、改既有 harness 逻辑。
- 保留所有 raw/失败/SDKDB/worktree；未 `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖。
- secret 不入 repo/提示词/日志；日志 `600`。

## 7. 修订历史

- 2026-10-16（真实 provider=0）：独立方法审计门 A/B/C/D/F 全 PASS，撰写本报告与 FORMAL-FREEZE，
  recommend Ready 进入正式 4 attempt；不执行、不 done。
