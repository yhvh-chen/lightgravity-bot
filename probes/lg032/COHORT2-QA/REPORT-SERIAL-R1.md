---
title: "LG-032 COHORT2 独立 serial 方法 QA 报告（SERIAL-R1，0 real provider）"
doc_type: report
category: engineering
status: "SERIAL-R1 门1/2/3 PASS；门4 PARTIAL（缺 cohort2 正式入口 runner）；推荐正式 ready 但本包不采样；032 NOT done；no merge"
experiment_id: lg032-cohort2-qa-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa
branch: qa/lg032-cohort2
base_commit: "8098514"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort2-qa（独立 serial 方法 QA；非源/harness 作者；不自修 harness）"
---

# LG-032 COHORT2 独立 serial 方法 QA 报告（SERIAL-R1）

> 独立于 `fix/lg032-mode-isolation` 实施者的 serial 方法 QA。**0 real provider**（fake 只 dummy loopback）。
> 产品源 / 旧 harness 只读；本包只新增 `probes/lg032/COHORT2-QA/**`。**不 mark 032 done、不 main merge、
> 不 push/deploy/publish。**

## 0. 结论（先给判断）

- **SERIAL-R1 门 1/2/3 PASS**；**门 4 PARTIAL**（发现一处**前置缺口**：修复包无「cohort2 正式入口 runner」）。
- 修复**真实、可复现、fail-closed**：ONE shared `settings.data_dir` 四次正式顺序链 s1A→s1B→s2A→s2B 全部正确，
  旧 cohort1 的污染（`s2_pipeline__A`=6 refs B-like）**已修**（本 QA 复现为 **3 refs 且无 selection**）。
- 产品 source **无改**（tree `55e4de56…` == base == main）；旧 cohort1 原件逐字节保留；formal cohort2 root **未创建**。
- **推荐正式 ready**，但**本包不采样**；正式入口 runner 补齐并冻结后方可执行正式 4 attempt。
- **LG-032 仍 in-progress**；不 mark done；不 merge。

## 1. 独立身份核（只读）

| 项 | 值 | 判定 |
|---|---|---|
| QA worktree / branch | `lg032-cohort2-qa` / `qa/lg032-cohort2`@`8098514` | clean |
| 产品 tree `backend/lightgravity` | `55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f` | == base == HEAD == main(`5df1956`) ✅ |
| `git diff 379c089 8098514 -- backend` | （空） | 产品源未改 ✅ |
| fix 分支 HEAD | `8098514` | 与交接一致 ✅ |
| 修复仅改 | `FINAL-COHORT/harness/{run_attempt.py,fairness_selftest.py}` + 新增 `MODE-ISOLATION/**` | 旧 METHOD-FINAL/cohort-ready 未碰 ✅ |
| 依赖 | `google.antigravity==0.1.22`（QA 独立 venv） | ✅ |

**注（文档精度，非 bug）**：`REPORT-MODE-FIX.md` §4.3 引用的 driver hash `4c564836…→7fc515ef…` 是
**git blob id**，对应 base `379c089` 与 extract commit `c433ffc`；最终 HEAD `8098514` 的 blob 为
`b1cc6c55…`（late `_safe()` restore hardening）。功能上前者严格更安全；仅报告引用未更新到最终 blob。
本 QA 以 HEAD `b1cc6c55…` 实测。

## 2. 门 R1.1 — 显式装配 / 真 bootstrap 后断言 / 恢复 off / fail-closed（PASS）

**静态调用顺序**（`probes/lg032/FINAL-COHORT/harness/run_attempt.py`）：

| 行 | 调用 | 说明 |
|---|---|---|
| 588 | `mode_snapshot_before = _set_mode(settings, arm)` | **build 前**经产品受控 `ConnectionService.update_settings` 写 A=`False`/B=`True` |
| 590 | `build_runtime(...)` | 真产品装配 |
| 630 | `_assert_active_mode(settings, dispatcher, arm)` | 真 bootstrap 后读**实际** dispatcher + 三持久开关 |
| 646 | `uvicorn.Config(...)` | **断言之后**才启动 HTTP/Coordinator loop |
| 727 | 创建 Task | 断言之后 |
| 882 | `results["mode_restore"] = _safe(lambda: _safe_restore_mode(settings))` | `finally` 恢复 off |

- `_assert_active_mode` 读 `dispatcher._autonomous_claim` / `_autonomous_pool` / `dispatcher._decentralized_enabled()`
  与持久 `settings` 实体三开关；**非 env 字串、非 constant True**；不一致即 `SystemExit`。
- **动态 fail-closed（QA 独立）**：持久写 A(`False`) 断言 arm B ⇒ `SystemExit`；持久写 B(`True`) 断言 arm A
  ⇒ `SystemExit`；正确极性通过；`_safe_restore_mode` 恢复 `False`。因断言在 uvicorn/Task **之前**，
  **任何 SDK/model forward 之前即 fail-closed**。
- 未见宽 root / `monkeypatch` stop / 手写状态；连接 pin / token / lease / fence 与产品 source 无改
  （仅 harness 文本注释出现 "monkeypatch" 字样）。

## 3. 门 R1.2 — 一个实际 shared `settings.data_dir` 四次正式顺序完整链（PASS）

`qa_serial_chain.py`：ONE shared QA phase root（`lg032-cohort2-qa-data-20261015T210510Z`，**非**正式 root），
顺序 **s1A→s1B→s2A→s2B**，各用 fresh loopback `FakeUpstream`（dummy credential），真产品路径
（真 `build_runtime` + 真 `GraphDispatcher` + 真 `CoordinatorWorkerLoop`（uvicorn lifespan）+ 真 verify/reviewer）。

| attempt | refs | selection | pool | steps | 机器门 | reviewer teardown | accept | 幂等 | 错 target | ledger after |
|---|---|---|---|---|---|---|---|---|---|---|
| `s1_units__A` | **3** | 无 | False | 14/14 | 5/5 | confirmed | 200 绑定 | 200 | 409 | 7 |
| `s1_units__B` | **6** | **有** | True | 14/14 | 5/5 | confirmed | 200 绑定 | 200 | 409 | 23 |
| `s2_pipeline__A` | **3** | **无** | False | 14/14 | 7/7 | confirmed | 200 绑定 | 200 | 409 | 30 |
| `s2_pipeline__B` | **6** | **有** | True | 14/14 | 7/7 | confirmed | 200 绑定 | 200 | 409 | 46 |

- **关键**：`s2_pipeline__A`（旧 cohort1 污染位）= **3 refs 且无 selection**，与正确确定性 A 一致；B 均 6 refs + selection。
- 同一物理 JSONL 严格递增 0→7→23→30→46；`one_physical_ledger=true`；每次 `restored_off=true`。
- evidence 绑真实 `check_records`（`{check_id: evidence-present, status: passed}`，4 refs）；per-node candidate diff
  `subtask_*-lg006-diff.patch@sha256:…`（s1 与 s2 各自稳定）。
- 未用独立 nonce `settingsRoot` 掩盖污染（四次 attempt **共用**一个 actual `settings.data_dir`）。
- 证据：`evidence/serial-chain-20261015T210510Z.json`（600）。

## 4. 门 R1.3 — source/driver/input truth/model/seed/policy 公平 hash 独立核（PASS）

| 项 | 值 |
|---|---|
| canonical plan hash **A==B** | s1 `4611722753542c1a37247ea72ac0c5f4cd8b40ca4e211e496b21e75f4943d545`；s2 `df60b54828a6232471b8d1cde6a4e0da9504bc91f02207ab3abce30741f7319d` |
| 同 3 nodes | `alpha` / `beta` / `verify`（A 与 B 同） |
| seed actual SHA | s1 `53458ac742b5aa4fd6913000aeeb69ae94cc80c1`；s2 `6fa0fd006ff058a7299f5e6dc42013fa051303de`（与冻结一致） |
| 机器 truth | s1 `d39d906c…`；s2 `06e2352f…`（与 FORMAL-REPORT 冻结一致） |
| caps | 192 / 48 / 16000 / 120s / retry 0 / concurrency 1 —— **无漂移** |
| 身份 | SDK `0.1.22` / contract `1.11.0` / `deepseek-v4-flash` @ `https://api.deepseek.com/v1` |

- 仅模式开关为自变量；bootstrap assert 与恢复 off **不改变** plan/members/tools/truth/caps/权限。
- 复引用 METHOD-FINAL 已 pass 的真实 proxy 硬 cap/corrupt 门（产品无改）：本 QA 只做**必要局部**验证，未大规模重测。
- driver 逐字节 hash：`run_attempt.py` `503a807f…`（fix 改）；`fake_upstream.py` `de9d7a35…`、
  `final_cohort_config.py` `a04a8f30…`、`hard_gate.py` `0067af1c…`、`run_dry.py` `f792da28…`（均未变）。
  见 `manifest-addendum.json`。

## 5. 门 R1.4 — 新正式 cohort2 root / 固定 formalIDs / 正式入口冻清（PARTIAL）

- ✅ 正式 root 固定 `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-data`；**本包未创建**
  （`exists=False`，逐次核）。fix overlay `MODE-ISOLATION/mode_config.py::PHASE_DATA_DIR` 指向该 root。
- ✅ 固定 4 formalIDs 与顺序（`s1_units__A/B`、`s2_pipeline__A/B`）与 METHOD-FINAL 一致，冻结在 config
  `ATTEMPTS`；正式日志目录同 rootlabel。
- ✅ 不误写 METHOD-FINAL 旧 formal：正式 root 与旧 `lg032-method-final-data` 不同名不同目录。
- ⚠️ **缺口（REQUIRED-BEFORE-FORMAL）**：修复包提供 cohort2 overlay，但**无正式入口 runner**
  （对应 METHOD-FINAL 的 `probes/run_formal.py`）。直接 `python harness/run_attempt.py --sample … --arm …`
  会用**冻结 cohort-ready root**，**不会**加载 cohort2 overlay。未来正式采样需一个等价 runner：
  ```python
  import mode_config as MC; C = MC.install()
  import run_attempt as R
  return R.run_attempt(sample, arm, dry_run=False)   # real DEEPSEEK_API_KEY from env
  ```
  并冻清其 full-absolute 入口 command 与 protocol hash。**本 QA 不自建该 runner**（非本包范围，且避免
  以 QA 身份新增正式路径）；交 PM 另派作者补齐后再冻结。

## 6. 旧 cohort1 保留 / 成本

- 旧 cohort1@`379c089` 的 87 = 21+26+19+21 已判 **AB invalid**（shared settings 下 B 写 True、A 无 False ⇒
  `s2_pipeline__A` 继承 B）。旧 reports/evidence/SDK/ledger 87 **逐字节保留**（fix 未碰 METHOD-FINAL，
  见 §1 diff）；未修后补跑旧 cohort；未以失败成本当有效 AB。
- 新 cohort2（将来）预算同 2 sample × A/B × 1 = 48 each / 总 192；**032 已知真实总上限 279 = 旧 87 + 新 192**，
  前失败成本单列不洗。本包 0 real provider。
- 本包 pi 开发/fake 成本 = **unknown**（**不记 0**，不预设省 token）。

## 7. 正/负边界

- **0 real provider**：无任何真实 provider 请求；`real_provider_generation=0`（两证据均记录）。
- 未 `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖；新输出唯一命名；私有证据 `600`。
- 未 nested proxy / push / deploy / publish / main write；未碰 `8123` 或他包进程。
- 未创建 formal cohort2 root；未改旧 cohort1 字节；未 mark 032 done / 未 main merge。
- 未自修 harness：门 4 缺口如实上报，不自行新增正式入口。

## 8. 推荐与交接

- **推荐正式 ready**（mode 修复经独立 4-attempt serial 链验证 PASS、fail-closed、无污染、公平 hash 一致）。
- **前置条件**：补齐并冻结 **cohort2 正式入口 runner**（§5）后，方可由 PM 另派执行正式 4 attempt。
- 本包不采样、不 mark 032 done、不 main merge。若 PM 判定 §5 缺口为阻断，另派处理。

## 9. 修订历史

- 2026-10-16（round 1–8）：建 QA worktree/branch；只读核产品源/driver/旧 formal；建 QA overlay；PLAN/STATUS。
- 2026-10-16（round 9–35）：SERIAL-R1 门 1/2/3 PASS；门 4 PARTIAL（缺正式入口 runner）；单 A 冒烟 14/14 PASS；
  4-attempt serial 链 PASS；公平 hash 核；REPORT 初版 + manifest addendum。**不采样 / 不 done / 不 merge。**
