---
title: "LG-032 MODE-ISOLATION 返修报告（harness 串行 mode 污染；产品源不改）"
doc_type: report
category: engineering
status: "PARTIAL — 协议失败认定完成；harness 隔离修复实现中；real provider 0；032 NOT done"
experiment_id: lg032-mode-isolation-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-mode-isolation
branch: fix/lg032-mode-isolation
base_commit: "379c089"
owner: "agent:pi-lg032-mode-isolation（独立返修 owner；主 PM 仅 PM）"
updated: "2026-10-16"
---

# LG-032 MODE-ISOLATION 返修报告

> 本文为 LG-032 首正式 cohort（`probes/lg032/METHOD-FINAL/runs`）串行 mode 污染的真实返修报告。
> **产品 source 不判 bug，问题在独立 QA harness**：4 个 attempt 共享同一 `settings.data_dir` 下唯一
> `settings/settings` 实体，arm B 写 `decentralized_claim_enabled=True` 后 arm A **从未写 `False`**，
> 于是 A 继承 B 模式（`s2_pipeline__A` show 6 refs = 同 B）。**本包 real provider 0，不新增正式请求。**

## 0. 先落明确协议失败认定（前 8 round）

**主 PM 已拒绝首正式 cohort 87 真实请求的 A/B 成本对照资格。** 真实数据（旧 `FORMAL-REPORT.md` §3，逐字节保留）：

| # | attempt | arm | 真实 requests | session refs | 应然 mode | 实际 mode（复算） |
|---|---|---|---|---|---|---|
| 1 | `s1_units__A` | A | **21** | **3** | A（deterministic，pool off） | A ✅ |
| 2 | `s1_units__B` | B | **26** | **6** | B（autonomous pool on） | B ✅ |
| 3 | `s2_pipeline__A` | A | **19** | **6** | A（pool off，应 3 refs） | **B ❌ 继承** |
| 4 | `s2_pipeline__B` | B | **21** | **6** | B | B ✅ |

- **认定：协议失败（serial mode pollution）。** `s2_pipeline__A` 的 session refs=6（而非 A 的 3）表明其
  runtime 实际以 arm B 的横向协作模式（`autonomous_pool=True`）运行；其 `19` 请求数与 A(21)/B(26) 的
  **A/B 成本对照**均**不可用于任何成本结论**。
- **归因（harness，非产品）**：`_seed_resources` 每次都以受控 `ConnectionService.update_settings` 覆写
  worker/coordinator/reviewer ref，但**不显式设定** `decentralized_claim_enabled`（`_UNSET` ⇒ 保持现值）。
  仅 arm B 调 `_enable_decentralized_pool` 写 `True`；arm A **无显式 `False`**。共享 `settings.data_dir`
  的持久 `settings` 实体于是把 B 的 `True` 带给后续 arm A。**产品 `build_runtime` 行为正确**，其读到的
  就是持久实体里那个 `True`。
- **产品 source 不判 bug**：`ClaimPolicyReader.read()` 与 `bootstrap.py:444/450`（`autonomous_claim=decentralized`
  /`autonomous_pool=decentralized`）行为符合契约；**source 默认 off 不变**（`settings/models.py:88` 默认 `False`）。

**旧产物全部保留**：旧报告 / 成本 / Run / SDK / raw / ledger 87 **逐字节保留**；**不改旧字节、不修后补跑
旧 formal、不 main write**。

## 1. 本包目标（返修范围）

只改**独立 QA harness**（`probes/lg032/**`），**不改产品 `backend/lightgravity/**`**：

1. **所有 attempt 显式设定模式**：A ⇒ `decentralized_claim_enabled=False`；B ⇒ `True`，且经产品**现有受控
   settings API/服务**（`ConnectionService.update_settings`）合法设置，**非直接伪造 Run 结果**。
2. **在产品真正 `build_runtime`/`CoordinatorWorkerLoop` 之前完成装配**（读回 settings ⇒ build）。
3. **真实 bootstrap 后断言并记录 active dispatcher mode + settings 三开关**与期望一致；**不能只 assert
   字符串 env**；**不能 A 继承 B**。
4. **phase 结束恢复 private-candidate 设置为 off 并记录**；source 默认 off 不变。
5. **必要新协议/overlay 使用全新独立 cohort2 持久 root**：预定 `lg032-cohort2-data`；未来同 4 attempt IDs
   只在新 cohort2；已知首 cohort87 列协议失败成本。
6. **0 验证**：真正共享同一 actual `settings.data_dir`，真实 bootstrap 依次 **A→B→A→B**（非各 nonce 独立
   settingsRoot 掩盖污染）。
7. 记录 source 行为未变 `55e4de56`、driver hash 变化、真正 mode 快照 / selector refs / 账本 before/after /
   机器 checks / accept；**不宣 formalReady、不 mark 032 done、不 main merge**。

## 2. 硬边界（全程）

- **不嵌套代理 / 不 push / 不 deploy / 不 publish / 不 main write**。
- **禁 `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖旧输出**；新输出唯一命名，全部持久 `700/600`。
- 0 real provider：只 loopback fake（真 SDK loopback + actual normal Coordinator），**禁外网 POST / 真实
  credentials 用于 fake**。
- 旧 87 + 未来 cohort2 预算**先后单列**；所有 pi 开发/失败 cost **unknown**，**不 0、不预设省 token**。
- 采样/seed/3nodes/权限/模型/预算 48 each 总 192 **不变**；**本包 0 真，不授权新 formal**。
- wall600 / maxround130 / noncache170k / idle150 / retry0；REPORT 每 15 round 更新；70 round 前保存阶段判断。

## 3. 修订历史

- 2026-10-16（round 1–8）：建 `fix/lg032-mode-isolation`（基 `qa/lg032-method-final@379c089`）；认定协议失败；
  落本 REPORT + STATUS；real provider 0；未改产品源。
