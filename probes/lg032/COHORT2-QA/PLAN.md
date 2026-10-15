---
title: "LG-032 COHORT2 独立 serial 方法 QA — PLAN"
doc_type: plan
category: engineering
status: "in-progress; independent serial QA (SERIAL-R1); 0 real provider; 032 NOT done; no main merge"
experiment_id: lg032-cohort2-qa-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-qa
branch: qa/lg032-cohort2
base_commit: "8098514"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort2-qa（独立 serial 方法 QA；非源/harness 作者；不修 harness）"
---

# LG-032 COHORT2 独立 serial 方法 QA — PLAN

> 独立 serial 方法 QA。复核 `fix/lg032-mode-isolation@8098514` 的 harness mode 隔离修复。
> 产品源 / 旧 harness 只读。本包只新增 `probes/lg032/COHORT2-QA/**` 与冻结 manifest 补遗。
> **0 real provider**；不 mark 032 done、不 main merge、不 push/deploy/publish。
> **失败不自修**：发现 harness/装配 bug ⇒ REPORT 交 PM 另派，QA 不修。

## 0. 背景（已认定，只读引用）

- 旧 cohort1（`qa/lg032-method-final@379c089`）formal 4 attempt 真实转发 **87 = 21+26+19+21**，
  已由 PM 判 **AB invalid**：`s2_pipeline__A` session refs=6（=B-like）⇒ shared settings 下 B 先写
  `decentralized_claim_enabled=True`、A 后从未写 `False`，A 继承 B 模式。**source 非 bug**（产品读真值）。
- 旧 87 reports/evidence/SDK/ledger 全部保留，不修后补旧 cohort，不把失败成本当有效 AB。
- 新 cohort2（将来正式）预定同 `2 sample × A/B × 1 = 48 each / 总 192`。若执行，**032 已知真实总上限 279
  = 旧 87 + 新 192**，前失败成本单列不洗。

## 1. 独立集中门 SERIAL-R1（0 fake 真 provider 之外，全部 0 real）

### R1.1 每个 attempt 显式装配 + 真 bootstrap 后断言 + 恢复 off
- 真 `build_runtime` **之前** 每 attempt 必须显式写 A=`False` / B=`True`（经产品受控 settings 服务）。
- 真 bootstrap **之后** 断言：持久三 flags + 实际 `GraphDispatcher` active modes
  （`_autonomous_claim`/`_autonomous_pool`/`_decentralized_enabled()`）。
- 结束 private-phase 恢复 off。
- 对错 mode 注入必须在**任何 SDK/model forward 之前** fail-closed；不能只看 env 字串 / constant True。
- 不得宽 root / monkeypatch stop / 手写状态。
- 连接 pin / evidence / token / lease / fence 与产品 source 全无改变。

### R1.2 一个实际 shared settings.data_dir，正式顺序 s1A→s1B→s2A→s2B 四次完整链
- 四次 actual `normal CoordinatorWorkerLoop` + 真 SDK loopback fake 完整链，**仅 mode 变量不同**。
- 使用已冻结同 3 nodes / 2 Member / seedSHA / 工具 / 计划输入 / 机器 truth / caps。
- 每次独立 workspaceRef/Task 但**同 phase physical JSONL**（不像旧独立 nonceSettingsRoot 掩盖污染）。
- B 有真实 selection 且 6 worker refs；A-after-B 有 3 refs 且无 selection。
- SDK + reviewer teardown 实际 confirmed；evidence-present 实际 checkrecords passed；外部语义 truth 5/5 或
  7/7 / real pernodehash / 绑定 accept 幂等错 target；同 ledger 连续累加；全部原件持久。
- **至多四新 fake attempt，各一次**；失败立刻 REPORT 不自修/补跑替换。
- QA 自身实现可写**独立 driver overlay** 保持正式 driver 字节只读；原 harness path/actual cfg 对象必须
  真正被调用，不能独立仿造 setting helper。

### R1.3 source/driver/input truth/model/seed/policy 公平 hash 独立核
- 两 arm 同 seed actual SHA 与同 canonical plan，仅模式开关。
- bootstrap assert 和恢复 off 不能改变关键权限。
- 以前 METHOD-FINAL 真实 proxy 重启硬 cap/corrupt 门已 pass 且产品无改可引用；核新 overlay/driver 仍同
  counter 实际注入与 same actual phaseRoot / 48 guard / global 192 不过配置漂移（必要局部验证，非大规模重测）。

### R1.4 新正式 cohort2 root 固定
- 新正式 cohort2 root 固定 `/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort2-data`，**本包不能创建**。
- 固定 4 formalIDs 与正式日志目录同 rootlabel；不能误写 METHOD-FINAL 旧 formal。
- fresh phase 允许不是逃总额，旧 87 永久报告；新 formal 准备与 protocol hash / 实际 full-absolute 入口
  command 全部冻清。

## 2. 交付物

| 项 | 路径 |
|---|---|
| PLAN | `probes/lg032/COHORT2-QA/PLAN.md` |
| STATUS（每 15 round）| `probes/lg032/COHORT2-QA/STATUS.md` |
| REPORT 初版（40 round 前）| `probes/lg032/COHORT2-QA/REPORT-SERIAL-R1.md` |
| QA driver overlay（独立，不改正式 driver）| `probes/lg032/COHORT2-QA/overlay/**` |
| 冻结 manifest 补遗 | `probes/lg032/COHORT2-QA/manifest-addendum.json` |
| cohort2 formal freeze（门全 pass）| `probes/lg032/COHORT2-QA/COHORT2-FORMAL-FREEZE.md` |
| 证据（700/600）| `probes/lg032/COHORT2-QA/evidence/**` |

## 3. 硬边界

- 不嵌套代理 / 不 push / 不 deploy / 不 publish / 不 main write。
- 禁 `rm`/`rmtree`/`reset`/`clean`/TMD/覆盖；新输出唯一命名；私有原件 `700/600`；raw SDK / secret 不入 repo。
- fake 只 dummy loopback；0 real provider；不碰 `8123` / 他包进程。
- 不创建 `lg032-cohort2-data`（正式 root）；不误写 METHOD-FINAL 旧 formal。
- 旧 cohort1 全部原件逐字节保留，不修不补跑。
- 成本：旧 87 单列无效；新 192 未开始；本包 pi 开发/失败 cost = **unknown**（不记 0）。
- wall 600 / maxround 130 / noncache 170k / idle 150 / retry 0。

## 4. 阶段

1. **round 1–8**：PLAN/STATUS；独立只读核 source/driver hash；建 QA 独立 overlay；R1.1 静态+动态。
2. **round 9–40**：R1.2 四次 fake serial 链（≤4 attempt，各一次）；R1.3 公平 hash；REPORT 初版。
3. **round 40–70**：REPORT 收敛；门全 pass 则写 COHORT2-FORMAL-FREEZE；否则 FAIL 交 PM。
4. **round 70 前**：阶段判断保存，不早退无交接。
