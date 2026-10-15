---
title: "编排角色消融 pilot 报告（agensh-ablation-20261015）"
doc_type: experiment-report
category: engineering
experiment_id: agensh-ablation-20261015
branch: experiment/agensh-ablation-20261015
base_commit: 9987d4f643b3ad02618d0c45fa35f8eb6ae84eef
updated: "2026-10-15"
---

# 编排角色消融 pilot：结果与限制

> **先说边界。** 这是一个**受控编辑协作 pilot**：满足全部组相同的确定性调度、文件 SoT、权限、预算与验收，
> 用标准库直接调用 OpenAI 兼容的 DeepSeek Chat Completions，模型只返回 JSON（文件内容 + 简短发现），
> 由程序做路径/base hash/大小校验、隔离 checkout、整合与验收。它**不是**真实 SDK 的 Agent 工具循环，
> **不测**工具选择、长会话、恢复/取消、权限沙箱或真实工程规模。
> **无论本报告结论如何，都不能据此直接删除产品中的编排/规划角色**；它只能产生“下一轮候选”。

## 1. 结论摘要（先结果）

- 正式 pilot 共 **9 个样本**（3 类任务 × 3 组），**45/45 次正常模型调用**，0 次基础设施重试，
  累计 provider `total_tokens = 106949`（< 200000），墙钟约 **180s**（< 900s），usage 缺失 0 次。
- 最终全部验收通过率：**A = 2/3、B = 3/3、C = 1/3**；最终通过条目：**A = 17/21、B = 21/21、C = 6/21**。
- 含编排开销的总成本（token / 墙钟）：**A = 48907 / 86.04s**、**B = 34589 / 55.45s**、**C = 23453 / 38.56s**；
  worker 固定 12 次调用机会三组相同，worker token 分别 A 33242、B 29207、C 23453。
- 按**预先注册**规则：
  - **去编排候选：否**。C 并非 3/3 通过（t1 0/6、t3 0/9）。
    但本实验的 C 只包含「两轮同步编辑提案」，缺少同轮开工前的协商与程序化原子认领往返，不是完整的
    Agensh 自组织；且冲突规则对同一路径的不同内容一律整文件拒绝。因此 C 的失败**不能证明**独立编排模型
    不可替代。下一轮应比较「无编排 + 程序化原子认领 / 同伴协商」形态。
  - **按需/初始规划候选：是（B，观测）**。B 质量不低于 A（21/21 ≥ 17/21）且总 tokens、总耗时都更低。
    但 A 组 3 次截断、B 组 0 次截断，该对比与截断混淆，**不能直接解释为“重新规划有害”的因果证据**，仅列为下一轮候选。
  - **保留依赖/变更任务的规划能力：支持**。T3（第二轮用户新增明确要求）中 C 全失败，而 B 9/9 全通过。
  - 其余为不确定。局部场景结论**不推广**到所有任务类型，也不声称统计显著性。
- ⚠️ **重要混淆**：本次 `max_tokens=2048` 与模型自身的 reasoning token 共享，45 次调用中 reasoning 占
  completion 的 **45.2%**，导致 **6 次调用在 2048 处被截断**（A 组 3 次、C 组 3 次，B 组 0 次）。A 组 t3 的失败
  和 C 组的部分失败**直接由截断造成**，因此 A/C 的质量差距被放大，**不能全部归因于“是否有编排”**。

## 2. 三组设置（唯一自变量）

| 组 | 编排模型 | 调用 | worker 可见 |
|---|---|---|---|
| A 全程编排 | 初始规划 + 第一轮后重新规划 | ≤2 | 目标 + 文件 + 共享发现 + 上轮程序反馈 + A 计划 |
| B 仅初始规划 | 初始规划 | ≤1 | 同上 + B 计划 |
| C 无编排 | 无 | 0 | 目标 + 文件 + 共享发现 + 上轮程序反馈（无任何任务分解） |

三组其余全部相同：`deepseek-v4-flash`、`max_tokens=2048`、`temperature=0.0`、2 worker、2 轮、
每轮每 worker ≤1 次逻辑调用、相同的验收程序与整合规则、worker 提示模板一致（仅身份标签不同）。
详细条件与 fixture 规范见 [PROTOCOL.md](PROTOCOL.md)（运行前冻结）。

## 3. 主要结果

### 3.1 质量

| 组 | 样本 | 全通过样本 | 最终通过条目 | 首轮通过条目 | 冲突(路径次) | 重复编辑 | 解析失败 | 截断调用 |
|---|---|---|---|---|---|---|---|---|
| A | 3 | 2 | 17/21 | 17/17 | 0 | 0 | 2 | 3 |
| B | 3 | 3 | 21/21 | 14/17 | 0 | 0 | 0 | 0 |
| C | 3 | 1 | 6/21 | 0/17 | 7 | 7 | 3 | 3 |

逐样本：

| 样本 | 首轮 | 最终 | 总耗时 | 编排耗时 | 备注 |
|---|---|---|---|---|---|
| t1_independent / B | 3/6 | **6/6** | 17.98s | 6.89s | 计划把两文件分给两 worker |
| t1_independent / C | 0/6 | 0/6 | 9.78s | 0 | 两 worker 都改两文件且内容不同 → 两轮均冲突，保持 base |
| t2_interface / C | 0/6 | **6/6** | 14.49s | 0 | 首轮两文件均冲突；次轮 w1 截断、仅 w2 提案 → 无冲突通过 |
| t2_interface / B | 6/6 | **6/6** | 15.23s | 7.31s | 接口依赖一次通过 |
| t1_independent / A | 6/6 | **6/6** | 27.24s | 14.59s | 两次计划 |
| t3_evolving / A | 5/5 | 5/9 | 37.80s | 17.94s | replan 截断 + 两 worker 截断 → 新需求未落地 |
| t3_evolving / B | 5/5 | **9/9** | 22.25s | 6.65s | 初始计划 + 次轮补 mode/stdev |
| t3_evolving / C | 0/5 | 0/9 | 14.29s | 0 | 两轮未产出有效实现 |
| t2_interface / A | 6/6 | **6/6** | 21.00s | 12.74s | 两次计划 |

### 3.2 成本（含编排开销；worker 机会三组相同）

| 组 | worker 调用 | 编排调用 | 总 tokens | input | output | reasoning | cache hit | worker tokens | 编排 tokens | 总耗时 | 编排耗时 | 重试 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 12 | 6 | 48907 | 25491 | 23416 | 8961 | 3968 | 33242 | 15665 | 86.04s | 45.28s | 0 |
| B | 12 | 3 | 34589 | 17859 | 16730 | 6249 | 2944 | 29207 | 5382 | 55.45s | 20.86s | 0 |
| C | 12 | 0 | 23453 | 8400 | 15053 | 9756 | 3328 | 23453 | 0 | 38.56s | 0 | 0 |

- B 相对 A：总 tokens 降 **29.3%**，总耗时降 **35.5%**，且质量更高。
- C 相对 A：总 tokens 降 **52.1%**，总耗时降 **55.2%**，但质量显著更差（不能作为去编排候选）。
- **费用：`unknown`**。本实验没有可核验的价格来源，不猜费率，只报告 token/时间代理量。

### 3.3 事实源与过程

- 文件 SoT：每个样本 `TASK.md/RUN.md/SUBTASK.md` frontmatter + 只追加的 `events.jsonl`；
  9/9 样本的 `check_sot` 一致性检查全部通过（无 worker 写控制状态、应用记录与文件对应）。
- 整合：每 worker 的提案先在隔离 staging checkout 应用校验，再按“唯一方 / 多方一致 → 应用；多方不一致 → 记冲突并保持 base”整合；
  C 组 7 次冲突全部保持 base，**没有无条件后写覆盖**。
- 脱敏：`raw/*.json` 只保存请求体（messages/payload）、响应文本与 usage；不含 Authorization/密钥（已扫描确认）。

## 4. 关键现象分析

1. **C 组失败机制 = 分工缺失导致的写冲突，而不是“模型不会写”。**
   C 组没有计划，两个 worker 在不知道对方做什么的情况下**都选择实现全部文件**；由于并行、彼此不可见，
   它们对同一文件给出不同内容，触发协议冲突规则，base 保持 stub，验收失败。t1/C 两轮均如此（4 次冲突）。
   t2/C 唯一的“通过”是因为次轮 w1 被截断而没有提案，只剩 w2 一家写，冲突偶然消失——这不是稳健协作。
   边界：本实验的 C 只是「两轮、每轮两名 worker 同步各提一次编辑、程序在整文件层面拒绝不同内容」的弱无编排
   基线，**没有**同轮开工前的同伴协商，也**没有**程序化原子认领（谁先认领路径、其余 worker 让出）的往返。
   因此上述冲突是「缺分工 + 弱冲突策略」的联合结果，不能外推为“任何无编排协作都不可行”。
2. **A 组 t3 失败 = 输出预算被 reasoning 吃光导致的截断。**
   t3/A 次轮：编排 replan `completion_tokens=2048`（截断，`orchestration_invalid`），w1、w2 也都
   `completion_tokens=2048`，JSON 被截断 → `no_valid_json` → 没有新编辑 → 新需求（mode/stdev）未落地。
   对照 t3/B：初始计划保持不变，w1 正常产出 → 9/9。**观测**：A 的 t3 低分与「第二轮上下文更长、编排 replan
   与两名 worker 同时截断」同时出现；**假设（本 pilot 未受控验证）**：更长的第二轮上下文可能伴随更多 reasoning
   token 而撞上 2048 上限。由于未控制上下文长度/thinking 开关，**不能**据此断言“第二次规划有害”或“更长上下文
   必然诱发更长 reasoning”。B 优于 A 在此样本中与截断混淆，只能作为下一轮候选，不构成因果关系。
3. **B 是本次最稳的形态。** B 用 1 次规划把文件边界定清楚，避免了 C 的冲突，又不像 A 在第二轮再引入
   一大段规划上下文（A 的编排 token 是 B 的近 3 倍），因此质量最高、总成本最低。
4. **worker 的“验证型”回复不可执行。** 多名 w2 在 findings 中大段声明“本角色无工具、无法运行用例”，
   只做静态审查——这是实验中“只有受控文件编辑、没有工具循环”的直接体现，也是本实验覆盖面之外的偏差来源。

## 5. 预注册规则判定（只用于下一轮候选）

| 规则 | 判定 | 依据 |
|---|---|---|
| 去编排候选（C 全通过 + 无额外 SoT 问题 + 较 A 任一指标改善 ≥20%） | **否** | C 仅 1/3 全通过 |
| 按需/初始规划候选（B 质量 ≥ A 且开销更低） | **是（B）** | B 21/21 ≥ A 17/21；tokens −29.3%、耗时 −35.5% |
| 关键依赖/变更任务保留规划能力（T2/T3 中 C 失败而 A/B 通过） | **支持** | T3：C 0/9，B 9/9；T2：C 6/6、A/B 6/6（T2 不构成保留理由，T3 构成） |
| 其余 | **不确定** | n=1/格，且存在截断混淆 |

**因此：下一轮可以优先验证“仅初始规划（B 形态）”或“按需规划”，但不能据此删除 A 形态能力，也不能据此删除编排角色。**

补充边界（必须随判定阅读）：

- B 优于 A 与 A 组 3 次截断相混淆，**不能**当作“重新规划有害”的因果结论。
- C 的失败**不能**证明“独立编排模型不可替代”：C 未实现同轮协商/程序化原子认领，且冲突规则对所有不同内容一律整文件拒绝。
- 下一轮若要检验去编排，应采用「无编排 + 程序化原子认领 / 同伴协商」形态，并控制 reasoning/输出预算以消除截断。

## 6. 限制与未覆盖（必须随结果阅读）

- **不是产品端到端，也不是真实 SDK 工具循环。** 模型只做有界结构化文件编辑；未覆盖 SDK 的工具选择、
  Agent loop、skills、长会话、session 恢复/取消、权限沙箱、hooks。
- **不能据此直接删除产品编排角色。** pilot 只给“下一轮候选”。
- **输出上限混淆（本次最重要）。** reasoning token 占 completion 45.2%，6 次调用撞 2048 上限被截断；
  未设置 `thinking.type=disabled`。A/C 的低分被截断放大。
- **样本极小、无统计功效。** 每格 n=1，共 9 次；不声称显著性，不推广到所有任务类型。
- **无成本结论。** 没有价格来源 → 费用 unknown；只报告 token 与墙钟。
- **无基础设施重试实证。** 45 次全部成功，重试/连续失败停止仅经离线 mock 验证。
- **实验专用 schema。** `TASK/RUN/SUBTASK` frontmatter 是实验 schema，**不声称**现有产品 schema 已支持。
- **参考解与验收不进入模型上下文**；fixture 初始态必失败、参考解必通过已离线验证（见 `evidence/offline/`）。

## 7. 可复现与证据路径

- 协议：[PROTOCOL.md](PROTOCOL.md)（含修订历史 §11、偏差/失败 §12）
- driver：`driver/run_pilot.py`（主流程）、`driver/llm_client.py`（有界 SSE 客户端）、
  `driver/analyze_results.py`（从原始 usage 重算指标）、`driver/offline_checks.sh`、`driver/validate_fixtures.py`
- fixtures/验收/参考解：`fixtures/t1_independent`、`fixtures/t2_interface`、`fixtures/t3_evolving`
- 离线验证证据：`evidence/offline/`（含 fixture 初始 hash、初始必败/参考必过、SSE 边界、mock 全流程）
- 正式 pilot 证据（现存，按权威性排序）：`runs/summary.json`、`runs/*/results.json`、`runs/*/events.jsonl`、
  `runs/*/raw/*.json`（原始脱敏请求/响应/usage）、`evidence/pilot/analysis.json`（由 raw usage 重算）。
  `evidence/pilot/run_stdout.log` 已保存（1954 bytes，含 pilot 进度与结尾 by_group 摘要），内容与上述证据一致；
  它只是运行日志，不作为独立事实来源。收尾复核另见 `evidence/finalize/`。
- 复现命令（真实 pilot，需进程环境已注入 `DEEPSEEK_API_KEY`）：
  ```bash
  cd probes/agensh-orchestration
  bash driver/offline_checks.sh             # 离线，无网络（是 bash，不是 python3）
  python3 driver/run_pilot.py               # 正式 pilot，写 runs/
  python3 driver/analyze_results.py          # 从 raw usage 重算
  ```

## 8. 运行事实与残留

- 分支 `experiment/agensh-ablation-20261015`，worktree `/tmp/lightgravity-worktrees/agensh-ablation-20261015`，
  base commit `9987d4f`。未提交、未合并、未 push、未 deploy。
- 主工作区 `/home/yhvh/code/lightgravity-bot` 在实验运行期间保持零改动；收尾集成时仅新增本目录
  `probes/agensh-orchestration/`（未跟踪、未提交），集成执行者未改动主工作区其他文件。
- 运行后无残留进程（`run_pilot`/探针均已退出）。
- 本报告不把 pilot 通过称为版本 QA。
