---
title: "LG-023 对照评估 PLAN（先冻结，后采样）"
doc_type: experiment-protocol
category: engineering
status: frozen-before-first-real-request
experiment_id: lg023-single-vs-team-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg023
branch: dev/lg023
base_commit: 03c7db6
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
model: deepseek-v4-flash
updated: "2026-10-16"
---

# LG-023 对照评估 PLAN（冻结于首个真实 DeepSeek 请求之前）

> 本文件在**任何正式真实 DeepSeek 请求之前**写定并冻结。正式采样后只允许追加“偏差/失败记录”。
> 若实际执行与本文不一致，必须如实记录；不得事后改样本、改门、加额度。
> 旧版 16/24/6 预算草稿**作废**（保留于派工历史，不构成本 phase 额度）。

## 0. 一句话问题

在**相同**的机器检查、**独立** reviewer 与**版本验收门**下，**组队实施**（程序调度的两 worker +
带 hash 交接）相对**单实施 worker**，在完成率、全周期 elapsed、token/usage 与人工干预上是否有可观测收益？

**关键口径**：`single worker` 标签**不含**共用 reviewer；独立 reviewer＋机器门＋版本验收门是**两 arm 共有**的部分，
**不能**把 reviewer 算作组队收益，**不能**以 agent 数量代替收益。**不预设**组队省 token。

## 1. 实验性质与边界（先声明）

- 这是**真实 SDK 产品路径**的对照评估：真实 `AntigravityExecutor`（google-antigravity 0.1.22）→ loopback
  认证代理 → 真实 DeepSeek `deepseek-v4-flash`；真实 Git 候选；程序机器门；真实独立 `ModelReviewer`。
  **产品执行不用 pi**（pi 仅是本评估的开发/controller 侧执行者，按 agent.md）。
- **不是**产品端到端/浏览器验收，**不测** UI、恢复/取消、长期会话、真实工程规模。
- 结论**仅**限两个小型代码样本、单模型；**不声称统计显著性**；不推广到所有任务类型。
- **无论结果如何**，不能据此删除产品编排/评审能力；只能产生“下一轮候选”。

## 2. 样本（真实小型代码交付，各 1 次/arm）

所有样本为**真实 Git 候选**：每样本从**固定初始 commit** 启动，注入**相同**需求与验收测试。
两个 fixture 复用既有 `probes/agensh-orchestration/fixtures` 的**语义**（经复核，见 §9），
但本 phase 建立**独立副本** `probes/lg023/fixtures/<id>/`，保证本 phase 独立可复现、不依赖旧实验目录的将来变更。

| 样本 | 类型 | 初始文件 | 验收（机器门，不进模型上下文） |
|---|---|---|---|
| **S1 independent** | 独立两文件修复 | `src/slugs.py`（`slugify` stub）、`src/ranges.py`（`clamp`/`in_range` stub） | `acceptance.py` 6 项 |
| **S2 interface** | 带依赖交接 | `src/geometry.py`（`area`/`perimeter` stub）、`src/report.py`（`describe` import geometry 且 stub） | `acceptance.py` 6 项 |

- 每个 fixture 目录：`initial/`（模型可见）、`acceptance.py`（**不进入模型上下文**）、`reference/`（**不进入**，仅离线自检）、
  `TASK.md`（需求文本，两 arm 相同）。
- 样本需求由 fixture `TASK.md` 固定，两 arm 完全一致。

## 3. 两个 arm（唯一自变量 = 实施 worker 数）

| arm | 实施方式 | 程序计划 | worker 数 | 交接 |
|---|---|---|---|---|
| **A single** | 1 个真实 SDK worker 完成全部文件 | 程序规则计划，1 个 write 节点 | 1 | 无 |
| **B team** | 2 个真实 SDK worker，程序调度依赖 | 程序规则计划，2 节点（write→dependent write） | 2 | 带 hash 的上游产物交接 |

**两 arm 完全相同**：fixture/初始 Git commit、需求文本、验收测试（机器门）、执行模型与参数、
独立 reviewer（同一 `ModelReviewer` 路径）、程序机器门、版本验收门、预算口径、权限规则、SDK 版本。

**差异仅**：A 由单 worker 产出全部文件；B 由程序调度两 worker（第二 worker 依赖第一的产物，经真实验证+hash 交接）。

### 3.1 机制与实验限制（**明确冻结**）

- 两个 arm 的计划都由 `_FrozenPlanner` 生成，并经**真实产品 `PlanValidator`**（真实 catalog 能力集、真实 workspace 边界）
  校验后才执行；**不是**手改控制状态、**不是**白名单绕过。
  - **arm A**：1 个 write 节点 `deliver`（覆盖全部文件）。
  - **arm B**：2 个 write 节点 `part_a -> part_b`（`part_b` 依赖 `part_a`），由 2 个真实 worker 执行。
- **实验限制**：产品默认 `RuleBasedPlanner` 只生成 `deliver`(+可选 verify)，不能直接生成两个写节点；
  因此用冻结的合法 plan 明确 arm 拆分（用户已允许“走程序校验与冻结合法 plan 并说明实验限制”）。
  这不改变程序对权限/状态/验收的权威，也不把冻结 plan 当产品隔离。
- **arm A 与 arm B 的 worker 提示/工具集/SDK/模型/权限/机器门/reviewer/验收门完全相同**；唯一差别是计划中的写节点数。
- **不把手改控制状态当产品隔离**；**不把冻结 plan 冒充为产品默认自动规划能力**。

- A 的 worker 提示：要求一次认领并写全部目标文件（与 B 的 worker 使用**同一工具集/同一 SDK/同一模型**）。
- B 的两个 worker 使用相同提示模板，仅身份/objective 不同；**不是** reviewer 也算 worker。

## 4. 共用的机器检查 + 独立 reviewer + 版本验收门（两 arm 一致）

1. **机器门（程序）**：对每 arm 的最终候选运行同一 `acceptance.py`（子进程、隔离 cwd、清理凭证 env、有界超时），
   输出 `{checks:[...], passed, total}`。**全部通过**才可能进入验收。
2. **独立 reviewer**：真实 `lightgravity.verify.review.ModelReviewer`（真 DeepSeek，独立于实施 worker 的上下文）
   + `validate_findings` 机器校验。reviewer `unavailable`/`failed` 不降级为通过。
3. **版本验收门（程序）**：候选完整、可复源（含 hash），机器门全过、reviewer `passed` ⇒ `awaiting_acceptance`，
   再按需求/候选/plan-hash 绑定 accept。任一不满足 ⇒ 该 arm 该样本**失败**（如实计入，不隐藏）。

## 5. 预算与硬界（采样前冻结；替代旧 16/24/6 草稿）

- **真实 DeepSeek 生成请求：总上限 48**（全 phase 唯一持久 ledger）。
- **每 attempt 二级上限 12**（2 样本 × 2 arm × 1 repeat = **4 attempts**，共 ≤48）。
- **全 stage 同 phase 持久 ledger**：worker/reviewer/返修/复验/失败**全部**从同一 `phase data_dir` 扣除；
  **不分账**。
- **output ≤ 16000 tokens/请求**；**HTTP timeout 120s**；**SDK/API retry 0**；**并发 ≤ 2**。
- 预算不足时保留不完整结果 / 限定结论，**不追加**新供应商/服务，不无限测试。
- 429/预算不足视为该 attempt 的真实失败或 partial，如实记录，不重跑同一 fixture（除非仍在同 attempt 预算内且属修复离线 bug）。
- **未知 usage 记 `unknown`，不当 0**。**未完成样本不得算作已交付成本**。

### 5.1 开发/controller 侧硬界（pi 派工，与 runtime 分开记账）

- wall ≤ 1800s、模型轮 ≤ 280、非缓存 token ≤ 380k、idle ≤ 240s、开发 API retry 0、命令 timeout 120s（长检查短轮询）。
- **SDK runtime 账本**与**开发派工 pi 账本**分别记账；不得把“只有 worker/reviewer runtime 的少 token”称完整收益。
- 独立 QA/返修若由 pi 发生，相关 dispatch token/time **单列**；无法可靠归 arm 则记 `shared`/`unknown`，**不当 0**。
- 本 phase 旧 022（unknown+6+8）与 031（34/40）工程成本**单列**，**不并入本 48，也不洗 0**。

## 6. 记录的指标（每 attempt）

- **完成率**：样本是否到达绑定 accept（机器门全过 + reviewer passed + 版本门 accept）。
- **首轮通过率**：第一次实施后即机器门全过（按实际样本计，不选成功）。
- **全周期 elapsed**：从该 attempt 首个真实请求到 attempt 结束（含执行/QA/返修/复验/失败）。
- **执行/QA/返修/复验/失败请求数**：真实生成请求拆分。
- **input/cache/output/usage/cost**：provider 报告值；缺失记 `unknown`。
- **人工干预**：人工介入次数/内容（prompt 修正不计为 worker 能力，需单列）。
- **未知项记 `unknown`，不计 0**；**未完成样本不得计为已交付成本**；**全部失败与返修原件保留**，不删不改。
- **不以失败样本中位数推断收益**。

## 7. 预注册判定规则（仅用于下一轮候选，非淘汰）

- **团队收益候选**：若 B 在两样本均完成且**总全周期成本（input+output，含交接/reviewer）不高于 A**（或完成率更高），
  记为“下一轮团队候选”。
- **单 worker 足够候选**：若 A 在两样本均完成且**总全周期成本低于 B**，记为“下一轮单 worker 候选”。
- **不确定**：样本小、单模型、强制程序计划；不声称统计收益。若费用/usage 不足以支撑收益，则结论明确为“不支持收益”。
- 任一 arm 未完成样本**照实计入**，不因失败而排除样本。

## 8. 文件事实源与证据

每个 attempt 目录（`probes/lg023/runs/<sample>__<arm>/`）：
`candidate/`（真实 Git 候选工作区）、`events.jsonl`（只追加）、`raw/`（脱敏请求/响应/usage）、
`result.json`（可重建结果）、`git.txt`（初始/候选 commit + diff）。
`probes/lg023/evidence/`：机器门、reviewer、验收门、计数快照、脱敏扫描。
`probes/lg023/ledger/`：唯一持久 generation ledger（本 phase limit=48）。

- **控制状态只由程序写**；worker 不写控制状态。
- **保留全部旧样本与失败**；不 `reset/clean` 覆盖，不删 worktree/diff。
- 凭证只从环境读取，**不写入** prompt/日志/仓库/报告。

## 9. fixture 语义复核（与既有实验一致性）

- S1/S2 直接复用 `probes/agensh-orchestration/fixtures/{t1_independent,t2_interface}` 的 `initial/`、`acceptance.py`、
  `reference/`，逐字节复制入 `probes/lg023/fixtures/`；不修改条目数（各 6 项）。
- 已核对该既有验收代码与旧 PROTOCOL §4.1–§4.2 条目一致（无偏差）。

## 10. 交付物

`PLAN.md`、`STATUS.md`、可复现 harness、fixtures（含 reference+acceptance）、逐 attempt 原始脱敏证据、
`REPORT.md`（中文，先结果后限制）、准确计数/缺陷/局限、本地精确 commit。**不推送/不部署/不发布。**

### 10.1 离线门（先于任何真实请求）

- `harness/validate_fixtures.py` → `evidence/offline/fixture_validation.json`：S1/S2 初始必败、reference 必过（各 6/6）。
- `harness/ledger_proof.py` → `evidence/offline/ledger_proof.json`：L1 全局硬上限 48、L2 第 49 次拒绝、L3 跨实例持久、
  L4 真跨进程持久、L5 损坏 fail-closed 绝不当 0、L6 attempt 二级上限 12、L7 全 stage 同一账本。
- `harness/selftest_offline.py` → `evidence/offline/harness_selftest.json`：两 arm 冻结合法 plan 过真实 `PlanValidator`、
  B 有真实依赖、attempt guard 拒绝第 13 次。

## 11. 修订历史

- 2026-10-16（**在首个真实请求之前**）：创建并冻结本 PLAN。确立样本 S1/S2、arm A/B、共用门、
  总 48 / 每 attempt 12 预算、output ≤16000 / HTTP 120s / retry 0 / 并发 ≤2、单一持久 ledger。
- 2026-10-16（**仍在首个真实请求之前**）：PM 预算最终修订落地于 PROJECT/PROGRESS/docs06/CORE-QA-CLOSE；
  本文件为执行依据。旧 16/24/6 草稿作废、不构成本 phase 额度。

## 12. 偏差与失败记录（采样后只追加）

（尚未开始正式采样。）
