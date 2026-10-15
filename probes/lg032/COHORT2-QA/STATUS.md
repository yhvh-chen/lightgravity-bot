---
title: "LG-032 COHORT2 独立 serial 方法 QA — STATUS"
doc_type: status
category: engineering
status: "round 9–36：SERIAL-R1 门 1/2/3 PASS；门4 PARTIAL（缺 cohort2 正式入口 runner）；REPORT 初版已落并 commit 41e0370；0 real provider；本包不采样"
commit: "41e0370（QA 包 commit）；base 8098514"
experiment_id: lg032-cohort2-qa-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa
branch: qa/lg032-cohort2
base_commit: "8098514"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort2-qa"
---

# LG-032 COHORT2 独立 serial 方法 QA — STATUS

## 当前阶段（round 9–35）

- 独立 QA worktree `lg032-cohort2-qa@8098514`（clean）；独立 venv（SDK `google.antigravity==0.1.22`）。
- **门 R1.1 PASS**（静态 + 动态）：`_set_mode`(588) → `build_runtime`(590) → `_assert_active_mode`(630，
  在 uvicorn 646 / Task 727 **之前**) → finally `_safe_restore_mode`。动态：错 mode 注入两向均 `SystemExit` STOP，
  正确通过，恢复 off；读真实 dispatcher 对象 + 三持久开关，非 env 字串。
- **门 R1.2 PASS**：ONE shared `settings.data_dir`，正式顺序 **s1A→s1B→s2A→s2B** 四次真 SDK loopback fake 完整链。
  - s1A=3refs/无 selection/pool off；s1B=6refs/selection/pool on；**s2A(after B)=3refs/无 selection/pool off**（旧污染已修）；
    s2B=6refs/selection/pool on。
  - 各 14/14 steps、机器门 5/5 或 7/7、reviewer teardown confirmed、accept 绑定/幂等 200/错 target 409、restore off。
  - 同 ONE physical JSONL 累加 0→7→23→30→46（严格递增）。
  - `evidence/serial-chain-20261015T210510Z.json`；`real_provider_generation=0`。
- **门 R1.3 PASS**：canonical plan hash A==B（s1 `461172…`、s2 `df60b5…`）；同 3 nodes alpha/beta/verify；
  seed SHA `53458ac7…`/`6fa0fd00…` 与冻结一致；truth `d39d906c…`/`06e2352f…`；caps 192/48/16000/120/0 无漂移。
- **门 R1.4 PARTIAL**：`lg032-cohort2-data` **未创建**（good）；固定 4 formalIDs 与顺序不变；
  **发现缺口**：修复包提供 cohort2 overlay（`mode_config.py`）但**无正式入口 runner**
  （对应 METHOD-FINAL 的 `probes/run_formal.py`）⇒ 正式 full-absolute 入口 command **尚未冻清**。
  非 mode 修复正确性 bug；为未来正式采样前置项，REPORT 列 REQUIRED-BEFORE-FORMAL。

## 产物

- [x] PLAN / STATUS / `manifest-addendum.json`（独立 hash）。
- [x] QA 独立 overlay `overlay/qa_mode_config.py`（正式 driver 字节只读，仅重定向路径常量）。
- [x] `qa_serial_chain.py` + `evidence/serial-chain-20261015T210510Z.json`。
- [x] REPORT 初版 `REPORT-SERIAL-R1.md`。

## 最终（round 36；<70 保存）

- 精确 commit `41e0370`（仅新增 `probes/lg032/COHORT2-QA/**`）；QA worktree clean；fix worktree 未碰。
- 产品 tree `55e4de56…` 不变；旧 cohort1 证据/报告 byte-identical（`s1_units__A`、`s2_pipeline__A`、`FORMAL-REPORT` blob 同）；
  旧 87 ledger 保留（`lg032-method-final-data` count=87，未碰）。
- 未创建 `lg032-cohort2-data`；未 mark 032 done；未 main merge。
- **不自修 harness**：门 4 缺正式入口 runner 如实上报，QA 不新增正式路径；交 PM 另派作者补齐后冻结。

## 阶段判断（round 30+；70 round 前保存）

**SERIAL-R1 门 1/2/3 PASS；门 4 因缺正式入口 runner 判 PARTIAL。** 推荐正式 ready（mode 修复真实、可复现、
fail-closed、无污染），但**本包不采样、不 mark 032 done、不 main merge**。cohort2 正式入口 runner
须由 PM 另派作者补齐后再冻结。若 PM 判该缺口为阻断，则另派，QA 不自修。

## 硬边界（全程）

不 nested proxy / push / deploy / publish / mainwrite；禁 rm/rmtree/reset/clean/TMD/覆盖；
0 real provider（fake 只 dummy loopback）；私有证据 600；不创建 `lg032-cohort2-data`；
旧 cohort1 逐字节保留；cost unknown 不 0。
