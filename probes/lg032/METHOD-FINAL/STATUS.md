---
title: "LG-032 METHOD-FINAL 独立方法审计 STATUS"
doc_type: status
category: engineering
experiment_id: lg032-method-final-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-method-final
branch: qa/lg032-method-final
base_commit: "a4b4455"
product_tree_commit: "0814b80"
updated: "2026-10-16"
owner: "agent:pi-lg032-method-final（独立方法审计 owner；非 harness/产品作者）"
---

# LG-032 METHOD-FINAL — 独立方法审计 STATUS

> 本包只做**独立方法审计 + 0-fake method 门**；真实 provider 生成 = **0**。
> 不改产品源 / 不改既有 harness 逻辑；只在 `probes/lg032/METHOD-FINAL/**` 新增
> probes/evidence/logs，及冻结 manifest 与 PLAN 补遗。
> 旧报告字节保留，不写 done，不 merge main。

## 0. 硬边界（本包）

- 真实 provider 生成 **0**；**禁止正式采样**、禁止外网 POST、禁嵌套代理、禁发布。
- 产品源（`backend/lightgravity/**`）**只读**；既有 `probes/lg032/FINAL-COHORT/harness/**` **只读**。
- 禁 `rm`/`rmtree`/`reset`/`clean`/`TMD`/覆盖；保留所有 raw/失败/SDKDB/worktree。
- 每次唯一 UTC nonce 日志持久 `700`；secret 不入 repo / 提示词 / 日志。
- 正式 phase data_root **唯一持久**，跨 4 attempt；不 env-pin 又被 bootstrap 覆盖。
- 计量门只在独立 scratch 较小 cap 上做，与 formalRoot 无混淆。
- wall600 / round140 / noncache180k / idle150 / retry0。

## 1. 基线核对

- 新 worktree HEAD = `a4b4455`（`qa/lg032-cohort-ready`）；产品 tree = `0814b80`（与 main 同）。
- 独立 QA 边界提交 = `70a0fd5`（lg031-boundary），产品 hash 同 `0814b80`（只读）。
- 现有 formal data root（`lg032-cohort-ready-data`）**不存在** ⇒ formal 0 确认。
- 现有 seed pin：s1=`53458ac7…`（tree `119aaa4d…`）；s2=`6fa0fd00…`（tree `bc96ccc4…`）。
- `.venv` 本 worktree `uv sync --frozen` 新建；SDK `0.1.22`，contract `1.11.0`。

## 2. 本包审计计划（见 PLAN-FINAL-ADDENDUM.md）

1. **门A** 独立 canonical plan/profile/caps/objective/tools/truth-hash A==B + seed actual SHA 两 arm 同 pin。
2. **门B** 真实 `build_runtime` 跨 2 启动 + 真 worker/reviewer LocalAuthProxy → 同物理 ledger 实际累加；
   独立 scratch 做 `48` / `192` 转发前拒 + corrupt fail-closed（真代理实际 reserve/restart/corrupt 持久文件）。
3. **门C** 正常 productCoordinatorWorkerLoop 自动 finalize / 异步 ModelReviewer / stopgate /
   evidence-present.checkrecords / 全 session stop / 候选 diff hash / 绑定 accept / 错 target / 幂等。
4. **门D** 独立跑 B 的 s1/s2 各一次 0-fake 至多 2 新 B attempt；loopback fake，SDK 真 selection，
   输出/SDKDB/SoT 持久。
5. **门E** 全门 pass 才写 `FORMAL-FREEZE.md`；否则 FAIL 交 PM。

## 3. 当前进度

- [x] 基线核对 + 建 worktree/venv。
- [x] 门A 公平性独立复算 — **PASS**（evidence/gateA-20261015T203739Z.json）。
- [x] 门B 计量/ledger 边界（独立 scratch）— **PASS**（evidence/gateB-20261015T203840Z.json）。
- [x] 门C 产品收口/accept 绑定 — **PASS**（evidence/gateC-20261015T204020Z.json）。
- [x] 门D 独立 B s1/s2 0-fake — **PASS 2/2**（evidence/gateD-20261015T204123Z.json）。
- [x] 门F formal 路径冻结/唯一 attempt/无 env 覆盖 — **PASS**（evidence/gateF-20261015T204144Z.json）。
- [ ] 门E FORMAL-FREEZE 决策 + 报告。

## 4. 门A/门B 证据摘要（2026-10-16，real provider 0）

### 门A（`probes/gateA_homogeneity.py` → `evidence/gateA-20261015T203739Z.json`）

- canonical plan hash **A==B**：s1 `4611722753542c1a…`、s2 `df60b54828a62324…`；两 arm 均 3 节点
  `alpha/beta/verify`，2 写节点，verify 依赖两者。product `plan_hash` 仅因 arm tag 不同。
- 静态 AST：恰好 **2** 个 `arm=="B"` 分支，**均为**协作开关（`_enable_decentralized_pool`/
  `_autonomous_pool`），无其它 arm 分支。
- seed SHA 可复现：s1 `53458ac7…`（tree `119aaa4d…`）、s2 `6fa0fd00…`（tree `bc96ccc4…`），
  独立重建两次 == 已 pin `seed.sha256`。
- 共享身份哈希：sample objective/acceptance、truth 脚本、role catalog、worker/verifier 工具与
  提示、caps（12/32/1/16000/120/0/1）均 arm 无关。

### 门B（`probes/gateB_ledger_boundary.py` → `evidence/gateB-20261015T203840Z.json`）

独立 scratch（`lg032-method-final-boundary`，**formalRoot 未创建**）：

- **真实注入**：真 `build_runtime` → 真 `executor._make_proxy`（产品注入 `global_generation_counter`）
  3 次 → count 3 / JSONL 3 行；真 `verify.review.run_review_turn`（产品 `ModelReviewer` 同一函数）
  → count 4（**reviewer 共享同一物理 ledger**）；同 root 二次 `build_runtime`（restart）→
  start2 count=4（**持久累加不归零**），再 2 次 → count 6 / 6 行。
- **48 转发前拒**：真 `_AttemptGuard` + 真 `LocalAuthProxy`，48 次 200 后 index 48/49 → `429`；
  count 钉 48；物理 48 行（**denied 不 forward**）。
- **total cap 小等价**：cap=3 → index 3/4 `429`；count 钉 3。
- **corrupt fail-closed**：写坏物理 `generation.jsonl` 后真代理 200→`429`；snapshot
  `corrupt=true`、`count=null`（**绝不当 0**）；直连 ledger `reserve` 亦拒。

## 5. 真实生成计数

- **正式真实产品生成 = 0**。
- 本包 0-fake 运行计数与唯一 nonce 在 evidence 中记录；不占正式 4×48 预算。
- 旧 023（45/4/16）、旧 022、旧 031（86）单列保留，不并入、不清零。
- pi 开发 QA / shared 成本：**unknown**，不记 0。
