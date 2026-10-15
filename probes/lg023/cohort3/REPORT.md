---
title: "LG-023 cohort-3 方法修复/正式评估 REPORT"
doc_type: report
category: engineering
experiment_id: lg023-cohort3-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg023-cohort2
branch: eval/lg023-cohort3
base_commit: "1d6d45c"
product_base_commit: e0a8cec
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
model: deepseek-v4-flash
protocol_hash: "c8f83417766ad0f036166591fe76feab8b885817ae6474534967174582e207f2"
harness_commit: "cdeda1d"
updated: "2026-10-16"
owner: "agent:pi-lg023-cohort3"
---

# LG-023 cohort-3 方法修复/正式评估 REPORT

> **状态：COMPLETE（4/4 attempts 全部真实交付）。** cohort-2 的 harness 计量缺陷 D1 已修复，
> 经离线硬门（真 `build_runtime`/`create_app` 启动链 ×2 + 真 `LocalAuthProxy` + 本地 fake 上游）验证后，
> 在 PM 预注册的 4 attempts 下正式采样完成，**全部落在单一 phase 持久账本**。真实生成 16/48。

## 0. 结论一句话

**LG-023 cohort-3 冻结协议完整执行：4/4 attempts 在相同机器门 + 独立 reviewer + 版本验收门 + 真实停止门下全部真实交付
（机器门 6/6、reviewer `passed`、accept 绑定），全部真实生成请求落在同一持久 phase 账本（16/48），D1 修复在真实 runtime 上成立。**
**就现有两小型样本、单模型、强制程序计划下：单 worker（A）与两依赖 worker（B）均 100% 完成；A 总真实生成 6、B 总 10；
A 总 elapsed 25.17s、B 总 33.43s。** 据此**不声称组队收益**：B 在完成率上无增益且成本更高；样本小、单模型、强制计划、
usage/cost `unknown`，**不足以**作统计性收益结论，也**不能**就此删除产品编排/评审能力。

## 1. 起点与 D1 修复（harness，非产品）

- 起点：`eval/lg023-cohort2@1d6d45c`（clean）；本包在其 worktree 内新建 `eval/lg023-cohort3`。
  cohort-2 分支/目录/`runs/`/`evidence/`/attempt ledger、旧 45、METHOD-AUDIT、全部旧原件**保留、未 reset/clean/覆盖**；
  产品/共享 docs 只读、未改。
- **D1**：`build_runtime` 无条件 `configure_generation_ledger(settings.data_dir)`，而 cohort-2 driver 把
  `settings.data_dir` 设为每个 attempt 各自的 `<attempt>/data`，**覆盖**了 driver 事先设的
  `LIGHTGRAVITY_GENERATION_LEDGER_DIR`，导致每次 attempt 各自 ledger（phase ledger 不存在）。
  **这是 driver 接线错误，不是产品 persistent ledger 缺陷**（产品 `PersistentGenerationLedger`/`LocalAuthProxy`
  计量在 `qa/lg022-stream` 与离线证明中均正确）。
- **采用 PM 指定的修法**：全串行 attempt/服务**共用同一真实 phase `settings.data_dir`**（`lg023-cohort3-data`），
  让产品自身的 `configure_generation_ledger(settings.data_dir)` **自然续读同一账本**；
  每 attempt 的隔离放在 `attempts/<attempt-id>/{workspaces,secrets}` + 不同 `workspace_ref`。
  **未**在 `build_runtime` 前重复设同一 env、**未**在 `build_runtime` 后重 pin counter、**未**改产品源、
  **未**用 CounterHelper 测试当实际服务验证、**未**清上个 Task/Run 来“隔离”、**未**重写旧 Root/ledger。
- 附带修：settings 播种在跨 attempt 复用时传 `expected_revision`（产品要求），使同一 `data_dir` 复用幂等。
- dry 与 formal **同一代码路径**，只换受控上游/基目录（dry 用 sibling `lg023-cohort3-data-dry`）；dry 不跳过 bootstrap，
  且**不**写正式 `evidence/`（dry 证据只落 dry 目录）。

## 2. 离线硬门（真实 DeepSeek 0，先于任何正式请求；全过）

证据：`evidence/offline/{offline_proof,hard_gate,dry_run_proof,protocol_manifest}.json`。

- **P1 fixtures**：两样本 `initial/` 0/6 必败、`reference/` 6/6 必过。
- **P2 冻结合法 plan**：A=1 节点、B=2 依赖节点，均过真实 `PlanValidator`。
- **P3**：worker agent 过真实 `ResourceCompiler`（view/create/edit 三工具）。
- **P4**：真 `LocalAuthProxy` + 本地 fake upstream：每 attempt 12 **转发前**强制、13th→429、worker/reviewer 同账本、count 非 0。
- **P5**：真 `GraphDispatcher` + 真 `VerifyService` + 真 `StoreResourceStopper`：teardown 齐 → `awaiting_acceptance`；缺 → `unconfirmed`。
- **P6（D1 修复硬门）** `hard_gate.py`：真 `build_runtime`/`create_app` **≥2 次顺序 runtime 启动**（同一 phase data_dir）；
  worker（start1）+ reviewer（start2）实际转发都落**单 phase 物理路径** `…-gate-sandbox/gate-phase/generation/generation.jsonl`，
  count **3→6 跨启动累加**；**attempt 超限**（12 次后第 13 → 429，ledger 停 12）与**总超限**（3 次后第 4 → 429，ledger 停 3）
  都在**转发前**拒绝；**损坏 fail-closed**（reserve 拒绝、`corrupt=true`、`count=None` 绝不当 0）；
  断言 runtime counter 对象附加 ledger 的 `_history` 路径 == 冻结物理 JSONL。
- **P7 dry-run** `dry_run_proof.py`：真 driver 两 arm 用本地 fake upstream 跑通，物理 ledger 落**单一** dry phase 路径、
  跨 arm **2→5 累加**、**无** per-attempt data_dir ledger、reviewer teardown confirmed。

## 3. 正式结果（4/4 attempts，全部真实交付）

| attempt | 样本/arm | 计划写节点 | 机器门 | 独立 reviewer | 停止门 | accept | 真实生成 | elapsed |
|---|---|---|---|---|---|---|---|---|
| `s1_independent__A` | S1 / A | 1 | **6/6** | `passed`(findings 0) | `confirmed` | accepted | **3** | 11.95s |
| `s1_independent__B` | S1 / B | 2 依赖 | **6/6** | `passed`(findings 0) | `confirmed` | accepted | **5** | 15.92s |
| `s2_interface__A` | S2 / A | 1 | **6/6** | `passed`(findings 0) | `confirmed` | accepted | **3** | 13.22s |
| `s2_interface__B` | S2 / B | 2 依赖 | **6/6** | `passed`(findings 0) | `confirmed` | accepted | **5** | 17.51s |

- 全部 `final_phase=awaiting_acceptance`，`sample_delivered=true`，`first_round_machine_pass=true`。
- session refs：A=1（单 worker）、B=2（两依赖 worker）——与计划写节点数一致；reviewer 均为独立会话。
- 每 attempt 的 `counter_ledger_matches_frozen=true`：runtime counter 附加 ledger == 冻结物理路径
  `lg023-cohort3-data/generation/generation.jsonl`（**单一** phase 账本，`find` 确认全 phase 只有这一个 `generation.jsonl`）。
- 账本跨 attempt 累加：attempt1 start=0→3，attempt2 start=3→8，attempt3 start=8→11，attempt4 start=11→**16**。
- 每 attempt 真实生成 ≤12；全 phase 16 ≤48。**无** per-attempt ledger。

候选 plan hash（绑定 accept）：
A=S1 `177c833c…`、B=S1 `5a466bae…`、A=S2 `a42ec8df…`、B=S2 `ebe85baf…`。

## 4. 成本与计数（准确，未知不当 0）

| 阶段 | 真实生成 | 说明 |
|---|---|---|
| **本 cohort-3** | **16/48** | 4 attempts：3+5+3+5；单 phase 持久账本累计 16 |
| 旧 LG-023 cohort 1 | **45/48** | protocol-deviation 失败成本，单列、不清零、不并入 |
| LG-023 cohort 2 | **4** | harness 缺陷 D1 停止，单列、不清零、不并入 |
| 旧 LG-022 | unknown+6+8+5/10 | 单列 |
| 旧 LG-031 | 34/40 | 单列 |

- 已知 eval 真实生成实际上限 **45+4+48 = 97**；本包实际 16。
- **usage/费用**：provider 未回传可核 usage（`rework.model_usage={'unknown':['usage']}`）⇒ 记 **`unknown`，不当 0**；
  SDK session DB（`lg023-cohort3-data/native-sessions/**/*.db`，含 `gen_metadata`）**已持久保留**，供后续恢复，
  本包**不**用失败/局部样本中位数推断收益。
- 开发/controller 侧成本（修 driver/硬门/harness）**单列/shared**，不当 runtime 收益。

## 5. 判定（按预注册规则）

- **单 worker 足够候选（就本两样本）**：A 两样本均完成且总真实生成（6）与总 elapsed（25.17s）**低于** B（10 / 33.43s）。
- **不声称组队收益**：B 在两样本上完成率与 A 相同（均 100%），但成本更高（用于交接的第二 worker 与 reviewer 之外的
  额外生成/时长）；样本小（2）、单模型、强制冻结合法 plan、usage/cost unknown ⇒ **不支持统计性收益结论**。
- 任一 arm 未发生真实失败；但**负/零收益仍是有效结论**：本 cohort 数据**不支持**“两依赖 worker 相对单 worker 有收益”。
- **不宣整产品 pass**；不删除产品编排/评审能力；最终 done 由主代理按授权决定。

## 6. 局限（明确）

- **样本小（2 样本 × 2 arm × 1 次）、单模型、强制冻结合法 plan**：不声称统计显著性；不推广到其它任务类型。
- 结论**仅**限两小型代码样本、强制程序计划；**不测** UI/恢复/取消/长会话/真实工程规模。
- 单 worker 标签**不含**共同 reviewer；机器门 + 独立 reviewer + 版本验收门为**两 arm 共有**，不计作组队收益。
- **workspace 隔离两 arm 一致关闭**（见 PLAN §3）：明确冻结的实验设置，不代表产品隔离能力。
- usage/费用 `unknown`（provider 未回传）；SDK session DB 保留供恢复，本包未逐 attempt 拆分 usage。
- 未宣整产品 pass；最终 done 由主代理按授权决定。

## 7. 产物与证据索引

- PLAN / STATUS / REPORT：`probes/lg023/cohort3/{PLAN,STATUS,REPORT}.md`。
- Driver / 配置 / 硬门：`harness/{run_attempt,cohort3_config,hard_gate,offline_proof,dry_run_proof,protocol_manifest,fake_sse_upstream}.py`。
- 离线证据：`evidence/offline/{offline_proof,hard_gate,dry_run_proof,protocol_manifest}.json`；protocol hash `c8f83417…`。
- 汇总：`evidence/aggregate.json`；逐 attempt：`evidence/<attempt-id>.json`、`runs/<attempt-id>/**`（不可变）。
- 持久 runtime + 唯一 ledger：`lg023-cohort3-data/generation/generation.jsonl`（16 行）、`lg023-cohort3-data/attempts/**`、
  `lg023-cohort3-data/native-sessions/**`。
- 旧 cohort 原件（`probes/lg023/{cohort2,METHOD-AUDIT}`、`dev/lg023`、`fix/lg023-method`）**保留、未改**。
- 冻结基点：worktree 内 `eval/lg023-cohort3`；harness commit `cdeda1d`（manifest 绑定）；产品锚定 `e0a8cec`。

**不推送 / 不部署 / 不发布。LG-023 结论由主代理按授权决定。**
