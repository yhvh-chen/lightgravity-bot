---
title: "编排角色对比实验（第二轮）REPORT"
doc_type: experiment-report
category: engineering
experiment_id: agensh-orchestration-r2-20261015
branch: experiment/agensh-r2-20261015
base_commit: 9987d4f643b3ad02618d0c45fa35f8eb6ae84eef
frozen_at_utc: "2026-10-15T05:53:15Z"
updated: "2026-10-15"
---

# 编排角色对比实验（第二轮）：结果与限制

> **先说边界。** 这是**受控编辑协作比较**：两组使用相同的确定性调度、文件 SoT、程序化原子认领/
> 同伴协商、权限、预算与验收，用标准库直接调用 OpenAI 兼容的 DeepSeek Chat Completions，模型只返回 JSON
> （认领/消息/发现，或文件内容），由程序完成租约、base hash/语法/越权校验、整合与验收。
> 它**不是**真实 SDK 的 Agent 工具循环，**不测**工具选择、长会话、恢复/取消、权限沙箱或真实工程规模。
> **无论结论如何，都不能据此直接删除产品中的编排/规划角色**；它只产出“下一轮产品 SDK 候选”。

## 1. 结论摘要（先结果）

- 正式运行 **18 个 run**（3 类任务 × B/C × 3 次独立重复），共 **153/153 次正常模型调用**，
  **0 次基础设施重试**，**0 次截断**，**0 reasoning token**，`total_tokens=179851`（<600000），
  墙钟约 **195s**（<1500s），usage 缺失 0 次。
- 最终全部验收通过：**B = 8/9、C = 9/9**；最终通过条目：**B = 60/63、C = 63/63**。
  按任务类（每类 3 run）：**t1 B 3/3、C 3/3；t2 B 3/3、C 3/3；t3 B 2/3、C 3/3**。
- 含全部开销的总成本：**B = 99451 tokens / 106.61s**，**C = 80400 tokens / 87.93s**。
  中位 run：token **B 11114 vs C 9081（C 改善 18.3%）**，耗时 **B 11.911s vs C 9.865s（C 改善 17.2%）**。
- 过程质量：两组 **0** claim/edit 冲突、**0** 越权、**0** 无效编辑、**0** 解析失败、**0** 截断、
  **0** SoT 一致性问题。
- **预注册判定 → “独立编排可移除候选 = 是”**：C 满足 9/9、每类不低于 B、0 额外 SoT/越权、0 截断，
  且中位 token 改善 18.3%、中位耗时改善 17.2%（另一指标不恶化）。**这只是一个下一轮产品 SDK 验证候选，
  不是自动淘汰依据。**
- ⚠️ **关键限制（必须与结论同读）**：每类仅 3 次重复；B 的唯一失败发生在 **t3（单可写文件任务）**，
  直接原因是 B 的规划把**同一个文件 `src/stats.py` 同时分给 w1（mean）和 w2（median）**，
  而两组共用的“每轮每文件仅一名 writer”程序规则无法兑现该拆分；先认领者两轮都占住 `src/stats.py`，
  第二轮又漏做 median → 6/9。C 没有规划，由一名 worker 自行完成整个文件，3/3 全过。
  **因此该质量差异来自“单文件任务 + 规划语义拆分 vs 程序一写者规则”的交互，不能外推为
  “独立编排普遍有害”。**

## 2. 两组设置（唯一自变量）

| 组 | 独立编排模型 | 调用 | worker 可见 |
|---|---|---|---|
| **B 仅初始规划** | 开头 1 次规划 | 每 run 1 次 planner | 目标 + 文件 + 共享发现 + 上轮反馈 + **B 计划文本** |
| **C 无编排模型** | 无 | 0 | 目标 + 文件 + 共享发现 + 上轮反馈（**无任何计划/语义分解**） |

两组其余**完全相同**：`deepseek-v4-flash`、`max_tokens=8192`、`temperature=0.0`、
`thinking.type=disabled`、2 worker、2 轮、每轮每 worker 2 次调用（claim + edit）、相同认领/租约规则、
相同提示模板、相同验收与整合规则。详细条件与冻结参数见 [PROTOCOL.md](PROTOCOL.md)
（冻结于 `2026-10-15T05:53:15Z`，manifest `a9fba8f0…a9311`）。

## 3. 主要结果

### 3.1 质量（最终验收；所有失败纳入分母）

| 组 | run | 全通过 run | 最终通过条目 | 首轮通过条目 | t1 | t2 | t3 |
|---|---|---|---|---|---|---|---|
| B | 9 | 8 | 60/63 | 46/51 | 3/3 | 3/3 | 2/3 |
| C | 9 | 9 | 63/63 | 51/51 | 3/3 | 3/3 | 3/3 |

逐 run（按实际运行顺序）：

| run | 先认领 | 首轮 | 最终 | tokens | 耗时 |
|---|---|---|---|---|---|
| t1_independent__B__r2 | w1 | 6/6 | **6/6** | 10825 | 12.36s |
| t2_interface__C__r2 | w1 | 6/6 | **6/6** | 9489 | 9.89s |
| t1_independent__C__r2 | w1 | 6/6 | **6/6** | 9081 | 9.59s |
| t1_independent__B__r1 | w2 | 6/6 | **6/6** | 11114 | 11.91s |
| t3_evolving__C__r0 | w1 | 5/5 | **9/9** | 8101 | 10.04s |
| t1_independent__C__r1 | w2 | 6/6 | **6/6** | 9242 | 9.22s |
| t2_interface__C__r1 | w2 | 6/6 | **6/6** | 9640 | 9.87s |
| t3_evolving__C__r1 | w2 | 5/5 | **9/9** | 8017 | 10.33s |
| t2_interface__B__r2 | w1 | 6/6 | **6/6** | 11958 | 11.66s |
| t1_independent__C__r0 | w1 | 6/6 | **6/6** | 9065 | 8.95s |
| t2_interface__C__r0 | w1 | 6/6 | **6/6** | 9688 | 10.18s |
| t3_evolving__B__r0 | w1 | 5/5 | **9/9** | 10069 | 11.67s |
| t3_evolving__B__r1 | w2 | 3/5 | **9/9** | 10186 | 12.07s |
| t1_independent__B__r0 | w1 | 6/6 | **6/6** | 11144 | 11.91s |
| t2_interface__B__r1 | w2 | 6/6 | **6/6** | 12180 | 11.42s |
| **t3_evolving__B__r2** | w1 | **2/5** | **6/9** | 10075 | 12.45s |
| t3_evolving__C__r2 | w1 | 5/5 | **9/9** | 8077 | 9.86s |
| t2_interface__B__r0 | w1 | 6/6 | **6/6** | 11900 | 11.15s |

### 3.2 成本与过程（含全部开销）

| 组 | 调用 worker/planner | tokens 总 | input | output | reasoning | cache hit | planner tok | claim tok | edit tok | 总耗时 | 中位 token | 中位耗时 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B | 72 / 9 | 99451 | 82333 | 17118 | 0 | 34048 | 7465 | 41500 | 50486 | 106.61s | 11114 | 11.911s |
| C | 72 / 0 | 80400 | 66420 | 13980 | 0 | 29440 | 0 | 36146 | 44254 | 87.93s | 9081 | 9.865s |

- 固定 worker 机会：两组各 72 次 worker 调用、36 claim + 36 edit。B 额外 9 次 planner。
- 真实 writer 利用率：两组均 **30/30** 个“持租约的 worker-轮次”，其中实际提交有效编辑
  **B 27/30、C 23/30**（其余为持租约但本轮无需改动而复核）；两组各 **6** 个 reviewer-轮次
  （均来自 t3 单可写文件：一名 writer、一名 reviewer）。**未把 2 worker 说成 2 并行 writer。**
- 冲突/越权/无效/解析失败/截断：两组均为 **0**。程序正确处理了所有路径，未出现无条件后写覆盖。
- SoT：18/18 run 一致性检查通过（frontmatter 状态、subtask 租约权威与 events claim 结果一致、
  base_revision 一致、应用文件存在、worker 未写控制状态）。

### 3.3 截断与 reasoning（本轮重点）

- 显式 `thinking={"type": "disabled"}` 被服务接受（无 4xx），153 次响应回显 `deepseek-flash`，
  `finish_reason` 全部为 `stop`，`reasoning_tokens=0`，**0 次 `finish_reason=length`**。
- 因此本轮**没有出现**第一轮那样被 reasoning 吃光 2048 预算的截断。
  **但本轮不声称已普遍消除截断**：这只是本配置（8192 + thinking disabled）下这 153 次调用的观察。

## 4. 关键现象分析

1. **B 的唯一失败 = 规划语义拆分与程序一写者规则冲突，而非“模型不会写”。**
   B 在 3 次 t3 规划中，每次都把 `src/stats.py` 同时分给 w1（mean）与 w2（median）。
   程序规则规定每轮每个文件只能有一名 writer；先认领者连续两轮占住该文件。
   - r0（w1 先）：w1 第一轮就做齐 mean+median（5/5），第二轮加 mode/stdev → 9/9。
   - r1（w2 先）：第一轮只 3/5，第二轮补齐 → 9/9。
   - r2（w1 先）：第一轮只做 mean（2/5），第二轮做了 mean+mode+stdev 但**漏掉 median** → 6/9。
   C 无规划，worker 自行认领后由一人完成整文件，3/3 全过。**观测**：在“只有 1 个可写文件”的任务上，
   独立规划倾向产生“同文件跨 worker 分工”，与共享的正确性/安全规则不兼容；**假设（本实验未单独受控验证）**：
   这是小样本下 B 失分的直接机制，但不能据此断言独立编排普遍有害，也不构成统计显著性结论。
2. **身份/顺序敏感性。** repeat 0/1/2 交替 w1/w2 先认领，同 repeat 的 B/C 一致。t3 的差异集中在
   单文件任务的 claim 顺序与“是否一次做齐”：r2 中 w1 先且两轮垄断；r1 中 w2 先且第一轮也未做齐但第二轮补齐。
   n=3 无法区分稳定的身份效应；仅记录该失败发生在 w1 先认领的 repeat 2。
3. **C 的两项改善都接近阈值边界。** token 改善 18.3%、耗时改善 17.2%，仅略高于 15% 门槛；
   在 n=3、且 B 的失败由单一行为事件驱动的情况下，**不能**把该幅度当作稳定效应。
4. **程序化认领显著降低了第一轮的弱基线冲突。** 第一轮 C 组在无编排下几乎全冲突失败；
   本轮加入原子认领/同伴协商后，两组冲突均为 0，C 也 9/9。这说明第一轮“C 不可行”的结论主要是
   **弱无编排基线（无认领、整文件冲突即拒绝）** 造成的，而非“无编排必然失败”。

## 5. 预注册规则判定（只用于下一轮候选）

| 条件（PROTOCOL §11） | 观察 | 满足? |
|---|---|---|
| C 9/9 全通过 | 9/9 | 是 |
| 每类 C ≥ B | t1 3≥3、t2 3≥3、t3 3≥2 | 是 |
| C 0 额外 SoT/越权 | SoT 0、overreach 0 | 是 |
| C 0 截断 | 0 | 是 |
| 中位 token 或耗时改善 ≥15% 且另一指标不恶化 >10% | token +18.3%、耗时 +17.2% | 是 |

**判定：列为“独立编排可移除候选（仅候选，非自动淘汰）”。**

**必须随判定阅读的边界：**

- 小样本（每类 n=3），`temperature=0` 不保证独立随机采样，**不声称统计显著性**，不推广到所有任务类型。
- B 的失败是“单文件任务 + 规划语义拆分”的交互，**不能**解释为“独立规划普遍无益”。
- C 的优势幅度贴近 15% 门槛，本轮**不足以**支持移除产品中的编排/规划角色；
  只能作为“下一轮产品 SDK 真实工具循环”的候选验证方向。
- 本轮仍**不是**产品真实 SDK 工具循环；认领/协商是有界两轮同步，不是任意多轮异步 Agensh。

## 6. 限制与未覆盖（必须随结果阅读）

- **不是产品端到端，也不是真实 SDK 工具循环。** 模型只做有界结构化编辑；未覆盖 SDK 工具选择、
  Agent loop、skills、长会话、session 恢复/取消、权限沙箱、hooks。
- **不能据此直接删除产品编排角色。** 只给“下一轮候选”。
- **样本极小。** 每类每组 n=3，共 18 run；无统计功效。
- **单文件任务的结构性限制。** 程序“每轮每文件一名 writer”使 t3 只有 1 名真实 writer + 1 名 reviewer；
  这不是 bug，但限制了该任务上 2 worker 的并行写作价值。
- **成本结论有限。** 无价格来源 → 费用 `unknown`；只报告 token 与墙钟代理量。
- **无基础设施重试实证。** 153 次全部成功，0 重试；重试/连续失败停止逻辑仅在离线 mock 验证。
- **无 reasoning 的结论只限本轮配置。** 本轮 `thinking.type=disabled` 生效，但未验证其它配置或模型。
- **实验专用 schema。** `TASK/RUN/SUBTASK/events` 是实验 schema，不声称产品 schema 已支持。
- **参考解与验收不进入模型上下文**；初始必败/参考必过、同版验收已离线验证（见 `evidence/offline/`）。

## 7. 可复现与证据路径

- 协议与冻结：[PROTOCOL.md](PROTOCOL.md)（文首冻结时刻/manifest；§13 运行后偏差记录）
- driver：`driver/run_experiment.py`、`driver/llm_client.py`、`driver/analyze_results.py`、
  `driver/validate_fixtures.py`、`driver/protocol_selftest.py`、`driver/offline_llm_selftest.py`、
  `driver/freeze_snapshot.py`、`driver/offline_checks.sh`
- fixtures/验收/参考解：`fixtures/t1_independent`、`fixtures/t2_interface`、`fixtures/t3_evolving`
- 离线证据：`evidence/offline/`（含源 fixture 哈希、冻结快照、config/prompt、离线日志）
- 正式证据（按权威性）：`runs/summary.json`、`runs/*/results.json`、`runs/*/events.jsonl`、
  `runs/*/subtasks/*.md`（持有租约权威）、`runs/*/raw/*.json`（原始脱敏请求/响应/usage/finish_reason）、
  `runs/*/calls/*.json`（逻辑调用日志）、`evidence/formal/analysis.json`（从 raw 重算）、
  `evidence/formal/consistency.json`（一致性/脱敏核对）、`evidence/formal/run_stdout.log`
- 复现命令（真实运行需进程环境注入 `DEEPSEEK_API_KEY`；不读取 .env）：
  ```bash
  cd probes/agensh-orchestration-r2
  bash driver/offline_checks.sh                 # 离线，无网络
  python3 driver/run_experiment.py              # 正式运行，写 runs/（--resume 不重复请求）
  python3 driver/analyze_results.py             # 从 raw usage 重算
  python3 evidence/finalize/finalize_checks.py  # 一致性/脱敏核对
  ```

## 8. 运行事实与残留

- 分支 `experiment/agensh-r2-20261015`，worktree `/tmp/lightgravity-worktrees/agensh-r2-20261015`，
  base commit `9987d4f`。未提交、未合并、未 push、未 deploy。
- 正式运行窗口：首请求 `2026-10-15T05:53:56Z`，最后事件 `2026-10-15T05:57:11Z`，约 195s。
- 预算实测：HTTP 153/162、正常调用 153/153、重试 0/9、`total_tokens=179851`（<600000）、
  `reserved_tokens=0`、`usage_unknown_calls=0`、无 fatal、无 abort。
- 运行后无残留 driver 进程；`runs/` 内无密钥/认证头（扫描 `Bearer`/`Authorization`/`sk-` 均 0）。
- 本轮数据与第一轮 `probes/agensh-orchestration/` **完全分离**，未混入统计；第一轮数据保留。
- 本报告不把 pilot 通过称为版本 QA。
