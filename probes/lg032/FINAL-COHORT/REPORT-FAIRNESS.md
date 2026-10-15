---
title: "LG-032 FAIRNESS-CORRECTION 续接执行报告（REPORT-FAIRNESS）"
doc_type: report
category: engineering
status: "IN-PROGRESS (pre-fake initial版); real provider 0; independent-method audit NOT done"
experiment_id: lg032-fair-ablation-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort-ready
branch: qa/lg032-cohort-ready
head_at_start: "dee0248"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort-ready（续接 owner）"
---

# LG-032 公平性纠正续接执行报告（REPORT-FAIRNESS 初版）

> **不篡改旧证据**：`REPORT-COHORT-READY.md` / 旧 4-combo fake / raw / worktrees 逐字节保留。
> 本报告只记录**公平性纠正续接包**的现状。**真实 provider 生成 = 0**。**本包不称正式 cohort 重跑**。

## 0. 本续接包目标（据 PM 授权）

仅**续接公平性改动的验证/归档**，不重新调查产品。纠正设计见 `FAIRNESS-CORRECTION.md`：
A/B 使用**同一 3 节点计划**、**同一 seed commit SHA**，**唯一差异 = 协作开关**。

## 1. 核实的起始状态（先 git 核，不盲目重放 edit）

- `git status --short`（本包开始时）：

  ```
   M probes/lg032/FINAL-COHORT/harness/run_attempt.py
  ?? probes/lg032/FINAL-COHORT/FAIRNESS-CORRECTION.md
  ```

- HEAD = `dee024812140ba4f78c9ac5b4859bb8e9a29ba1c`；`git diff --stat` 仅
  `run_attempt.py`（+173/-71）。产品源**只读未改**（`backend/lightgravity/**` 无 diff）。
- **前 owner 的公平性 edit 已大部分完成并保留**：
  - `_FrozenPlanner`：A/B 统一为同 3 节点 `alpha`/`beta`/`verify`（旧 A=1 合并节点已删）。
  - `_seed_repo` / `_ensure_seed` / `_init_repo`：per-sample 持久只读 seed，
    derived 仓库 clone seed 且 `HEAD` 必须 == seed SHA，否则 `SystemExit`。
  - `_authorize_task_checks` + `FROZEN_TASK_CHECKS`：授权产品**自有注册**机器检查。
  - `run_attempt` 结果新增 `seed_head`；accept 前 truth 门（machine+reviewer+session+teardown）已在。
- **未发现前 owner 已跑**新的 s1A/s2A fake：
  - `fixtures/*/seed.git` **不存在**；最新 offline 产物为 `07:24`，`freeze-candidate.manifest.json` 为 `07:27`，
    均**早于** `FAIRNESS-CORRECTION.md`（`07:30`）。⇒ 公平性 edit 为**中途状态**，未验证。
- 无残留 `run_attempt`/`fake_upstream`/`pytest` 进程；系统仅有 owner 的 `8123`（**不动**）及无关服务。

## 2. 本续接包所做的最小 harness 改动（仅这几个小点）

1. `FROZEN_TASK_CHECKS` 由 `("evidence-present", "artifacts-in-workspace")`
   **收敛为 `("evidence-present",)`**。
   - 依据：`CheckReport.satisfied` 对**空授权**返回 True（vacuous pass），故**必须**授权至少一个**真实注册**检查，
     使产品实际运行机器检查（无 evidence 则 fail）——满足 FAIRNESS-CORRECTION §5。
   - `artifacts-in-workspace` 是**更严的路径解析检查**，**非 graph evidence-present 门所必需**，
     依 PM「有必要别强塞不适用于 graph」的指示**不强制**，留作 follow-up。
2. 新增 `harness/fairness_selftest.py`：**局部单测**（无网络/无 provider/无 fake），仅校验三个不变量：
   - canonical plan hash **A == B**（两样本）；
   - **只有**协作开关分支（静态）；
   - seed commit SHA **arm 无关**（首建==复建==derived A==derived B）。
   - **保留边界**：只在唯一临时根内写；**不触碰真实 fixture / attempt 输出 / 产品源**。

**未做（明确留白）**：未改 PLAN/预算；未改产品源；未新 binding 到 accept 之外；未跑全套测试。

## 3. 公平性不变量自测结果（本包，0 real）

命令：`.venv/bin/python probes/lg032/FINAL-COHORT/harness/fairness_selftest.py` ⇒ **FAIRNESS-SELFTEST PASS**

| 不变量 | s1_units | s2_pipeline | 结论 |
|---|---|---|---|
| plan hash A | `4611722…3d545` | `df60b54…f319d` | |
| plan hash B | `4611722…3d545` | `df60b54…f319d` | **A==B ✅** |
| 节点 | alpha,beta,verify | alpha,beta,verify | 同 3 节点 ✅ |
| 仅协作开关 diff | — | — | ✅（2 个 arm-B gate 均属同一开关：启用 + 守卫） |
| seed SHA | `53458ac742b5aa4fd6913000aeeb69ae94cc80c1` | （同型，由 seed helper 保证） | 首建==复建==derived A==derived B ✅ |

> 注：`53458ac7…` 是自测**临时 fixture 副本**下的 seed SHA；正式 seed SHA 将在首次真实/认证 fake 前由
> `_ensure_seed` 在 `fixtures/<sample>/seed.git` 固定并记录。**SAMPLE_SPEC 未变**，故两样本 seed 结构一致。

## 4. harness 指纹（本包改动后，未提交前）

| 文件 | sha256 |
|---|---|
| `harness/run_attempt.py` | `d19949480e17d9fe457ac1b87448052f31bdb6edf017f60206ba641933d50d64` |
| `harness/fairness_selftest.py` | `d9ded00acf896ae22af3476ee81f3e0a6403268902b39de0a72cc0f8f77f74d1` |
| `harness/fake_upstream.py`（未改） | `de9d7a3547dd0a99e615d8cf1f2d899cf31e5d82f34a47fbb482db15a515a045` |
| `harness/final_cohort_config.py`（未改） | `a04a8f309a72626c5b039039198feab03f143966e6634bf1fe5228ff0834a117` |
| `harness/run_dry.py`（未改） | `f792da2842def8edd6accb14fd09eb0a32b8063d7a2186972fbec8da676ac559` |

## 5. 新 0-fake 授权运行（已执行：s1A + s2A，各一次；共 2 次，用尽本包上限）

> 调用：`run_dry.py --sample <s> --arm A`（`fake-upstream` loopback，dummy credential；`LG032_DRY_NONCE` 唯一）。
> 输出 UTC nonce 唯一、stdout/SDKDB/SoT 持久；**未 rm/rmtree/reset/clean/TMD/覆盖**。
> 前 owner 未跑过 ⇒ 本包执行。**两次均 PASS**。

| 项 | s1_units__A | s2_pipeline__A |
|---|---|---|
| rc | 0 | 0 |
| stdout | `offline/fairness-s1A-20261015T203344Z-s1A-fair.stdout` | `offline/fairness-s2A-20261015T203351Z-s2A-fair.stdout` |
| data root | `…-data-dry-s1_units-A-20261015T203344Z-s1A-fair` | `…-data-dry-s2_pipeline-A-20261015T203351Z-s2A-fair` |
| `task_checks_authorized` | `('evidence-present',)` ✅ | `('evidence-present',)` ✅ |
| `check_records`（accept 绑定） | `[{check_id: evidence-present, status: passed, detail: 4 evidence ref(s) recorded}]` ✅ | 同 ✅ |
| machine gate | 5/5 ✅ | 7/7 ✅ |
| `run_reached_awaiting_acceptance` | ✅ | ✅ |
| session refs（真实 3 节点） | 3（alpha/beta/verify）✅ | 3 ✅ |
| reviewer teardown | confirmed ✅ | confirmed ✅ |
| accept confirmed_bound | ✅ | ✅ |
| accept idempotent（同 request_id） | ✅ | ✅ |
| accept wrong_target | 409 rejected ✅ | 409 rejected ✅ |
| `initial_head == seed_head` | `53458ac7…` ✅ | `6fa0fd00…` ✅ |
| fake 相位分类（capture） | exec4/verify2/review1（无 selection 空转）✅ | exec4/verify2/review1 ✅ |

**关键结论**：
- **同 3 节点计划**在 arm A 下正确执行（`alpha`→`beta`→只读 `verify`），产物为 per-node 真实 diff。
- accept 门**绑定真实机器 truth**：`check_records` 不再是空 `[]`，而是真实运行的 `evidence-present`（无 evidence 则 fail）；
  accept 仅在 machine+reviewer+session+teardown 全绿时发生，wrong-target 409，idempotent 不重复决策。
- **seed SHA**：per-sample 持久 seed 固定（`s1=53458ac7…` tree `119aaa4d…`；`s2=6fa0fd00…` tree `bc96ccc4…`），
  `initial_head == seed_head` 证明 derived 仓库与 seed **同一实际 commit 对象**。
- **A/B 同 seed**：因 `_ensure_seed(sample)` 对两 arm 返回**同一持久 seed**，B 亦将 clone 同一对象；
  本包受「至多 2 fake」限制**仅跑 A**，未跑 B（**不超预算**）。A/B 同 seed SHA 的 harness 局部证据见 §3 自测
  （derived A == derived B == seed）。

**诚实留白**：本包**未**跑 arm B fake，故 B 的候选池自主路径本包**未再证**；旧 4-combo B fake 属旧(非法)计划，
**不可直接引用**，须独立方法 audit 或后续（预算内）重验。

## 6. 结果 / 未做 / 门

- **真实 provider 生成：0**（本包全程 fake/offline，dummy credential，loopback）。
- **新 fake：2/2 已用**（s1A、s2A 各一次，均 PASS）。**不超上限**。
- **新增 harness 指纹（已含本包改动）**：`run_attempt.py` sha256 =
  `d19949480e17d9fe457ac1b87448052f31bdb6edf017f60206ba641933d50d64`（以提交为准）。
- **未做**：未跑正式 4×48；未 freeze approved；未 mark done；未 main merge / push / deploy / publish；
  未嵌套代理；未碰 `8123`；未改产品源；未跑 arm B。
- **剩余门（须独立方法 audit）**：
  1. fake-upstream 相位分类 vs 产品真实相位的独立方法 audit（**NOT DONE**）；
  2. arm B 候选池自主路径在**新计划**下的重验（本包未做）；
  3. A/B 同质性 / 同 seed SHA 的**独立**复核（本包自测为 harness 局部，非独立）；
  4. 正式预算 4×48（**尚未开始，0**）。
- **不计入**：本包不占正式预算（4×48/192 仍 0）。

## 7. 修订历史

- 2026-10-16（真实 provider=0）：续接 owner 先核 git（未盲目重放前 owner edit），确认公平性 edit 大部分已完成且未验证；
  收敛 `FROZEN_TASK_CHECKS` 至 `evidence-present`；新增 `fairness_selftest.py` 并通过；初版落盘于执行新 fake 前（round < 8）。
- 2026-10-16（真实 provider=0）：执行并记录**新 s1A/s2A fake 各一次**（均 PASS）；补齐 §5/§6；
  `check_records` 显示真实 `evidence-present` passed，accept 门绑定真实机器 truth。**不改产品源、不占正式预算**。
