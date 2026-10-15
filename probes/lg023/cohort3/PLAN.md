---
title: "LG-023 cohort-3 方法修复/正式评估 PLAN（PM 预注册后冻结）"
doc_type: experiment-protocol
category: engineering
status: frozen-after-hard-gate
experiment_id: lg023-cohort3-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg023-cohort2
branch: eval/lg023-cohort3
product_base_commit: e0a8cec
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
model: deepseek-v4-flash
protocol_hash: "c8f83417766ad0f036166591fe76feab8b885817ae6474534967174582e207f2"
updated: "2026-10-16"
owner: "agent:pi-lg023-cohort3"
---

# LG-023 cohort-3 对照评估 PLAN

> 本文件在**任何正式真实 DeepSeek 请求之前**写定并冻结。采样后只允许追加“偏差/失败记录”。
> 若实际执行与本文不一致，必须如实记录；不得事后改样本、改门、改提示/工具/测试真值/预算、加额度。
> 本 cohort 的预算/样本/门由 PM 预注册（见 `probes/lg023/METHOD-AUDIT/REPORT.md` §8、`backlog/tasks/LG-023.md`）。
> 旧 cohort-1（45/48）与 cohort-2（4）为 protocol-deviation / harness 缺陷失败成本，**不并入本 cohort、不清零**。

## 0. 一句话问题

在**相同**机器门、**独立** reviewer 与**版本验收门**下，程序调度的**两依赖实施 worker**（arm B）
相对**单实施 worker**（arm A），在完成率、全周期 elapsed、token/usage 与人工干预上是否有可观测收益？

`single worker` 不包含共用 reviewer；机器门＋独立 reviewer＋版本验收门是**两 arm 共有**，**不能**把 reviewer
算作组队收益，**不能**以 agent 数量代替收益。**不预设**组队省 token。

## 1. 实验性质与边界

- **真实 SDK 产品路径**：真 `build_runtime`/`create_app` 装配 → 真 `AntigravityExecutor`（SDK 0.1.22）
  → loopback 认证代理 → 真 DeepSeek `deepseek-v4-flash`；真 Task/Run/Subtask；真 `Coordinator` + `GraphDispatcher`
  + `VerificationService` + `StoreResourceStopper`（`session_confirmer` = 适配器真实 `confirm_stopped`）；
  真独立 `ModelReviewer`；真机器门。
- **不是**产品端到端/浏览器验收；**不测** UI、恢复/取消、长会话、真实工程规模。
- 结论**仅**限两小型代码样本、单模型、强制程序计划；**不声称统计显著性**；不推广。
- **无论结果如何**不能据此删除产品编排/评审能力。

## 2. 样本（各 1 次/arm，共 4 attempts）

fixtures 逐字节复制自 cohort-2（已核 `diff -r` 相同；上游为 cohort-1 原件）：

| 样本 | 类型 | 初始文件 | 机器门 |
|---|---|---|---|
| **S1 independent** | 独立两文件修复 | `src/slugs.py`、`src/ranges.py` | `acceptance.py` 6 项 |
| **S2 interface** | 跨模块依赖交接 | `src/geometry.py`、`src/report.py` | `acceptance.py` 6 项 |

每 fixture：`initial/`（模型可见）、`acceptance.py`（**不进模型上下文**）、`reference/`（**不进**，仅离线自检）、`TASK.md`。

## 3. 两个 arm（唯一自变量 = 计划写节点数）

| arm | 计划写节点 | 实施 worker | 交接 |
|---|---|---|---|
| **A single** | 1（`deliver`） | 1 | 无 |
| **B team** | 2（`part_a → part_b` 依赖） | 2 | 程序 graph artifact 交接（含 hash） |

**两 arm 完全相同**：fixture/初始内容树、需求文本、机器门、独立 reviewer、版本验收门、模型、预算、工具集、
worker 提示模板、初始内容树 hash、权限、SDK 版本、验收门。
**差异仅**：计划写节点数。冻结合法 plan **只用于比较计划写节点数**，不冒称自动规划能力对照。

- 两 arm 均由 `_FrozenPlanner` 生成 plan，经**真实产品 `PlanValidator`**（真实 catalog 能力集、真实 workspace 边界）校验。
- **旧程序调度路径**：`autonomous_claim=False`、collaboration off（新自主 claim 工具**未开启、不要求**）。
- **workspace 隔离在两 arm 一致关闭**：产品 per-node git worktree 不会自动整合回 candidate，若开启会使机器门读到未改的
  base tree、两 arm 同时失效。关闭后两 arm 都在同一 shared candidate workspace 上按文档的保守单写者串行（与已通过的
  `qa/lg022-stream` 主链一致）。这是**明确冻结的实验设置**，不改产品默认。

## 4. D1 修复：全 phase 单一持久 data_dir / ledger

- **唯一 phase `settings.data_dir`** = `<worktree 旁>/lg023-cohort3-data`，**全部串行 attempt/服务启动共用**；
  产品 `build_runtime` 的 `configure_generation_ledger(settings.data_dir)` **自然续读同一账本**。
- **冻结物理账本** = `<phase>/generation/generation.jsonl`（产品自身布局）。
- 每 attempt **独立** Task/Run/workspace：`attempts/<attempt-id>/{workspaces,secrets}` + 不同 `workspace_ref`；
  **不**把 `data_dir` 随 attempt 换、**不**在 build_runtime 前重复设同一 env、**不**在 build_runtime 后重 pin counter、
  **不**改产品源、**不**用 CounterHelper 测试当实际服务验证、**不**清上个 Task/Run 来“隔离”。
- dry 与 formal **同一代码路径**，只换受控上游/基目录（dry 用 sibling `lg023-cohort3-data-dry`）；dry **不跳过** bootstrap。

## 5. 共用的机器门 + 独立 reviewer + 版本验收门（两 arm 一致）

1. **机器门（程序）**：子进程隔离 cwd、清理凭证 env、有界超时；`{checks, passed, total}`，**全过**才可能进验收。
2. **独立 reviewer**：真 `lightgravity.verify.review.ModelReviewer`（真 DeepSeek，独立上下文）+ `validate_findings`；
   `unavailable`/`failed` **不降级**为通过。
3. **版本验收门（程序）**：候选完整、机器门全过、reviewer `passed` ⇒ `verifying → awaiting_acceptance`，
   再按 requirements/candidate/plan-hash 绑定 accept。任一不满足 ⇒ 该 arm 该样本**失败**（如实计入）。
4. **停止门**：真实适配器 teardown 事实（SDK `Agent.__aexit__` + loopback proxy 停止）→ `confirm_stopped`；
   缺失保持 `unconfirmed` + held。**不预填 `cleanup=done`、不删 refs、不造 confirmed**。

## 6. 预算与硬界（PM 预注册；采样前冻结）

- **真实 DeepSeek 生成：总上限 48**（全 phase **唯一持久 ledger**）。
- **每 attempt 上限 12**（2 样本 × 2 arm × 1 repeat = **4 attempts**，≤48）。
- **全 stage 同 phase 持久 ledger**：worker/reviewer/返修/复验/失败**全部**同一账本；**转发前**扣减；超限/损坏 fail-closed。
- **output ≤ 16000 tokens/请求**；**HTTP timeout 120s**；**SDK/API retry 0**；**并发 ≤ 2**。
- **双方同 tool-call cap 32**；**每 worker 模型调用 ≤ 12 且同 attempt 总 12**（采样前固定；不改产品默认）。
- **attempt 总数 4，每个只 1 次正式 run**：不可变 attempt-id 目录（存在即拒绝）+ 一次性 guard。
- 429/预算不足 = 该 attempt 真实失败/partial；**不重跑同一 attempt**，**不追加额度**，**不换供应商**。
- **旧 45+4 为失败/方法成本，明示单列、不并入本 48、不清零**。已知 eval 实际上限 45+4+48=**97**。

### 6.1 开发/controller 侧硬界（与 runtime 分开记账）

- wall ≤ 1800s、模型轮 ≤ 300、非缓存 token ≤ 420k、idle ≤ 240s、开发 retry 0、单探针 ≤ 60/90s。
- 旧 022（unknown+6+8+5/10）与 031（34/40）**单列**，不并入、不清零。

## 7. 记录的指标（每 attempt）

- **完成率**：是否到达绑定 accept（机器门全过 + reviewer passed + 版本门 accept）。
- **首轮通过率**：第一次实施后即机器门全过。
- **全周期 elapsed**：该 attempt 首个真实请求到结束。
- **执行/QA/返修/复验/失败请求数**：真实生成拆分。
- **input/cache/output/usage/cost**：provider 值；缺失记 `unknown`，**不当 0**。
- **人工干预**：次数/内容；prompt 修正单列。
- **未完成样本不计已交付成本**；**不用失败中位数推收益**；**全部失败原件保留**。

## 8. 预注册判定规则（仅用于下一轮候选）

- **组队候选**：B 两样本均完成且总全周期成本（含交接/reviewer）不高于 A（或完成率更高）。
- **单 worker 足够候选**：A 两样本均完成且总成本低于 B。
- **不确定**：样本小、单模型、强制计划；不声称统计收益。费用/usage 不足 ⇒ 明确「不支持收益」。
- 任一 arm 未完成样本**照实计入**，不因失败排除。**负/零收益也可完成有效评估**；但 harness 偏差/协议未完成不能把 023 done。

## 9. 文件事实源与证据

- 每 attempt：`probes/lg023/cohort3/runs/<attempt-id>/`（`result.json`、`candidate.diff`、`git.txt`、一次性 guard），
  **创建即不可变**。
- `probes/lg023/cohort3/evidence/`：脱敏证据、机器门、review、验收门、计数、离线证明、protocol manifest。
- 持久 runtime：`lg023-cohort3-data/attempts/<attempt-id>/**`（SoT、workspace、SDK session、secrets）。
- 唯一持久 ledger：`lg023-cohort3-data/generation/`（limit 48）。
- 凭证只从环境读取，**不写入** prompt/日志/仓库/报告；私有原件 `700/600`。

## 10. 离线硬门（先于任何真实请求，全部通过才可采样）

- **P1** fixtures 初始必败 / reference 必过（6/6，两样本）。
- **P2** 两 arm 冻结合法 plan 过真实 `PlanValidator`（A=1 节点，B=2 依赖节点）。
- **P3** worker agent 过真实 `ResourceCompiler`（view/create/edit 三工具）。
- **P4** 真 `LocalAuthProxy` + 本地 fake upstream：每 attempt 12 **转发前**强制、13th→429、worker/reviewer 同账本、count 非 0。
- **P5** 真 `GraphDispatcher` + 真 `StoreResourceStopper`：teardown 齐 → `awaiting_acceptance`；缺 → `unconfirmed`。
- **P6 硬门（D1 修复证明）** `hard_gate.py`：真 `build_runtime`/`create_app` 启动链 **≥2 次顺序 runtime 启动**
  （同一 phase data_dir）、真 `LocalAuthProxy` + 本地 fake upstream，worker+reviewer 实际转发都落**单 phase 物理路径**
  且**跨启动累加**、**总/attempt 超限**转发前拒绝、**损坏 fail-closed**；断言 counter 对象附加 ledger 路径 == 冻结物理 JSONL。
- **P7 dry-run** `dry_run_proof.py`：真 driver 两 arm 用本地 fake upstream 跑通，物理 ledger 落**单一** phase 路径、跨 arm 累加、无 per-attempt data_dir ledger。

证据：`evidence/offline/{offline_proof,hard_gate,dry_run_proof,protocol_manifest}.json`。

## 11. 交付物

`PLAN.md`、`STATUS.md`、`REPORT.md`、harness（`run_attempt.py` 等）、fixtures、逐 attempt 原始脱敏证据、
准确计数/缺陷/局限、本地精确 commit。**不推送/不部署/不发布**。

## 12. 修订历史

- 2026-10-16（**首个真实请求之前**）：创建并冻结本 PLAN。修 cohort-2 D1（全 phase 单一 `data_dir`/ledger）；
  确立样本 S1/S2、arm A/B、共用门、总 48 / 每 attempt 12、toolcap 32、modelcall ≤12、output ≤16000 / HTTP 120 /
  retry 0 / 并发 ≤2、单一持久 ledger、workspace 隔离两 arm 一致关闭、旧程序路径/新自主开关 off。
  离线硬门 P1–P7 全过；protocol hash `c8f83417…`。

## 13. 偏差与失败记录（采样后只追加）

- 暂无（尚未发正式请求）。
