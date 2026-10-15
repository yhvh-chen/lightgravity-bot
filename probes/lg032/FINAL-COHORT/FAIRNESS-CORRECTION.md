---
title: "LG-032 fair-ablation 最小纠正（FAIRNESS-CORRECTION）——同 3 节点计划、仅比较调度/自主协作机制"
doc_type: correction
category: engineering
status: "CORRECTION-AUTHORED (pre-first-real-request); harness/PLAN to be corrected; 0 real provider; independent-method audit NOT done"
experiment_id: lg032-fair-ablation-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort-ready
branch: qa/lg032-cohort-ready
base_commit: "dee0248"
product_tree_commit: "a29e94f"
product_fix_commit: "0814b80"
source_of_truth: "DeepSeek provider real generation = 0 (formal never run)"
updated: "2026-10-16"
owner: "agent:pi-lg032-cohort-ready（续接 owner；主代理仅 PM）"
---

# LG-032 公平性最小纠正（FAIRNESS-CORRECTION）

> **本文件在首个正式真实请求之前**纠正 harness/PLAN 的实验设计。**产品源不改、无真实 provider、不 main merge。**
> 旧报告 `REPORT-COHORT-READY.md` **逐字节保留**（连同所有失败/raw/worktrees）；本文件**只新增补遗**，**不篡改旧证据**。
> **旧「唯一变量 2 个」的协议不合法**；本纠正**在首真实调用前**有权修订。**本包不称「正式 cohort 重跑」。**

## 0. 一句话原因

- 旧 `REPORT-COHORT-READY.md` §4 与旧 `PLAN.md` §1.2 把 **两个变量混合**：
  - **变量①**：实施写节点数（**arm A = 1 合并写节点 `deliver`** vs **arm B = 2 独立写节点 `alpha`+`beta`**）；
  - **变量②**：arm B 的候选池自主选择机制（`autonomous_pool`）。
- **主 PM 明确拒绝该协议，不准据此正式采样**，且**不以旧 PLAN 覆盖新 PM 指令**。
- 用户/PM 依 LG023 已另评拆分结论（见 `probes/lg023/METHOD-AUDIT/`）：**node 数差异是混淆变量**，
  故 **LG-032 必须只比较「调度 / 自主协作机制」**，而 **A 与 B 使用同一个 3 节点计划**。

## 1. 纠正后的协议（唯一自变量 = 协作开关）

**同一个 3 节点计划（A 与 B 完全相同）**：

| 节点 | capability | write | depends_on | 产物 |
|---|---|---|---|---|
| `alpha` | `implementation` | true | — | `file1`（样本第一个 stub） |
| `beta` | `implementation` | true | — | `file2`（样本第二个 stub） |
| `verify` | `verification` | **false（只读）** | `alpha`, `beta` | 只读报告，无写 |

- `alpha` 写**独立 file1**，`beta` 写**独立 file2**，`verify` **只读依赖两者**。
- **arm A = 程序调度**：同一 3 节点计划，`decentralized_claim`/`autonomous_pool` **OFF**，
  由确定性 `GraphDispatcher` 程序调度（`max_parallel=1` ⇒ `alpha`/`beta` 串行，再 `verify`）。
- **arm B = 候选池自主协作**：同一 3 节点计划，`decentralized_claim_enabled=true` + `autonomous_pool=true`，
  worker 以真实 SDK 工具 `discover_and_request_claim` **真实自主选择合法候选**，程序原子授权所选 node。
- **A/B 唯一差异 = 该协作开关**。除此之外一切都相同（见 §2 同质性清单）。

> **注意**：arm A 的 `alpha`/`beta` 使用**同一 `implementation` Member**（`lg032-worker`），
> 与 arm B 候选池的同一 Member 完全一致；`verify` 使用独立的只读 `verification` Member（`lg032-verifier`）。
> 这样 A 与 B 的**计划、Member、工具、objective、acceptance 完全一致**，仅"谁做调度/协作"不同。

## 2. A/B 同质性清单（必须逐项一致；剔除必要生成 ID）

| 维度 | 要求 | 纠正后实现 |
|---|---|---|
| 3 节点计划 | 同 | `alpha`+`beta`+`verify`（见 §1） |
| 每 node objective | 同 | 同 `SAMPLE_SPEC` 的 `objective_a`/`objective_b`/verify objective |
| 每 node acceptance | 同 | 同 `SAMPLE_SPEC["acceptance"]` |
| Task input（objective/acceptance/workspace_ref） | 同 | 同 `SAMPLE_SPEC` |
| Member / capability / role catalog | 同 | `implementation→[lg032-worker]`、`verification→[lg032-verifier]` |
| permission / tools | 同 | worker 写工具、verifier 只读（同 `_seed_resources`） |
| 机器 truth | 同 | 同 `fixtures/<sample>/acceptance.py` 子进程隔离 |
| 独立 ModelReviewer | 同 | 真 `verify.review.ModelReviewer` |
| 停止门 | 同 | `StoreResourceStopper(session_confirmer=executor.confirm_stopped)` |
| output / http / retry / parallel | 同 | 16000 / 120s / 0 / 1 |
| **初始仓库 Git commit SHA** | **同一实际 commit SHA** | 由**固定 seed repo** 复制/clone（见 §3） |
| 协作开关 | **唯一差异** | A: OFF（程序调度）；B: ON（pool selector/execution） |

**公平维度 hash**：对上述 plan 相关字段（节点 key/capability/write/depends_on/objective/acceptance/
Task input/role catalog/tool refs/truth 脚本哈希/初始 tree+commit）计算**规范化哈希**，
**剔除**必要生成 ID（task_id/run_id/member_id/subtask_id/session_ref/时间戳/nonce/dry-root 路径）。
A/B 该哈希**必须相等**；报告记录两者 hash 与差异项（应仅协作开关）。

## 3. 初始仓库同一实际 Git commit SHA（修复 LG023 A5 缺陷）

- **缺陷回顾**（`probes/lg023/METHOD-AUDIT/REPORT.md` §A5）：旧 cohort 每 arm 各自
  `git init` + `commit`，**内容 tree 相同但 commit 对象不同**（提交时间戳等元数据差异），
  且原 commit 对象随 `TemporaryDirectory` 删除 ⇒ 只能记 `unknown`。
- **纠正**：每个 sample **只固定一个持久 seed repo**，其初始 commit **首个真实请求前固定并记录 SHA**；
  - 每 sample 一个 seed：`<phase data 或 cohort 旁持久路径>/seeds/<sample>/seed.git`（**只读**，首建后不可改）；
  - 每 attempt/arm 从 seed **复制/clone** 出隔离工作域，derived 仓库的 `HEAD` **必须 == seed SHA**；
  - **禁止** worker/reset 写 seed；**禁止** `git init`+新 commit 生成各 arm 不同对象；
  - derived 各工作域（per-node worktree）**隔离**，互不覆盖；**无 reset/删除/覆盖任何旧目录**。
- 记录：seed repo `git rev-parse HEAD`、`git tree` hash、对象校验、derived `HEAD`。
  A/B **同一 seed SHA** ⇒ 满足"同一个实际 Git commit SHA"。

> seed/object/input/hash 初次生成后**不可改**；原种子**不被 worker 写**。
> 如实现需为每 attempt 复制/clone 只读 seed，则复制产物只读、隔离，不影响 seed。

## 4. 计量 / 预算 / 硬门（不变）

- **正式预算仍 = 4 attempt，各 48，总 192**（`2 samples × A/B × 1`）；所有 roles/repair/failure 同 ledger；
  **未 formal 0**。**本纠正不改变预算**，只是**在首真实请求前**修正计划构造。
- **真实唯一 phase 实际 `settings.data_dir`** 不因不同 arm/attempt 变；现成 ledger gate 供后续审计；
  **本包正式仍 0**。
- **本包新增 fake 上限 = 至多 2 次新 fake**（纠正后 **A 两样本 s1A/s2A 各一次**）；
  **不增产品 caps / 不宽 root / 不改 readonly source**。
- **禁止** `rm`/`rmtree`/`reset`/`clean`/`TMD`/覆盖旧输出；失败全保留；输出 UTC nonce 唯一。

## 5. 授权检查 evidence-present + 外部语义 truth

- **必须至少授权产品已有检查 evidence-present 并记录 `checks`**：
  - 机器 truth 的通过**必须**来自**产品已有检查**（`evidence-present`）并把 `checks` 记入结果；
  - **不能**用 `Task checks` 空值冒充机器 pass；
  - 外部语义 truth 针对 **per-node 真实 artifact diff/哈希**构成同候选；
  - **不能**在 truth fail 后 accept。
- 已归档 arm B 的 fake 行为按原 3 节点**基本可引用**，但**当前 driver 改动后需独立方法审计**决定是否重验。

## 6. 本包执行范围（0 fake A 两样本）

1. **保存本文件**（15 round 前）——完成。
2. **保留**旧报告逐字节 / 所有失败 / raw / worktrees——不动。
3. 在**当前 isolated worktree** 仅修改 FINAL-COHORT 配置 / driver 计划构造，使 A/B 完全相同（§1/§2/§3）。
4. 运行**新 0fake s1A / s2A 各一次**，输出 UTC nonce 唯一 / stdout / SDKDB 保全。
5. 检查同 3 节点候选链与 fake 终止；失败都保留。
6. 写 REPORT/STATUS + 公平维度 hash + 精确 commit，**交独立方法 audit**；**不 self-mark ready/done**。

## 7. 非目标 / 硬边界

- **不改产品源**（`backend/lightgravity/**` 只读）；**无真实 provider**；**不 main merge / push / deploy / publish**。
- **不嵌套代理**；凭证仅 controlled 环境；**0 外网 POST**。
- **不称正式 cohort 重跑 / 不 mark 032 done / 不占正式预算**。
- wall 360 / maxround 80 / noncache 100k / idle 120 / retry 0；每 8 round STATUS，40 round 前 report，完成后 STOP。

## 8. 修订历史

- 2026-10-16（**首个正式真实请求之前**，真实 provider=0）：因旧 §4/PLAN 混合两个变量，PM 拒绝旧协议；
  作者在首真实调用的纠正窗口内新增本文件，将 A/B 统一为**同 3 节点计划**、**同一 seed commit SHA**、
  **唯一差异 = 协作开关**；明确 evidence-present / 外部语义 truth 门与 2 次新 fake 上限。**不篡改旧证据。**
