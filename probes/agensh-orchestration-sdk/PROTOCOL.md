---
title: "agensh SDK 编排对比实验 — 冻结协议"
doc_type: protocol
experiment_id: agensh-sdk-20261015
branch: experiment/agensh-sdk-20261015
worktree: /tmp/lightgravity-worktrees/agensh-sdk-20261015
base_commit: 9987d4f643b3ad02618d0c45fa35f8eb6ae84eef
sdk: google-antigravity==0.1.22
frozen_at_utc: "2026-10-15"
status: frozen
formal_runs: 6
---

# 冻结协议（正式运行前）

本文件在本轮正式运行前冻结。正式启动后不再修改参数 / 提示 / 执行逻辑 / fixture / 验收；
致命 bug 则停止并保存证据。冻结清单与哈希见 `evidence/FREEZE_MANIFEST.txt`。

## 1. 目标与分组（单变量）

| 组 | 独立编排模型 | 其余完全相同 |
|---|---|---|
| B | 运行开始时 **恰好 1 次** planner SDK turn（结构化输出） | 程序化认领、同轮消息、工具权限、每轮 base、两轮、验收 |
| C | **无**独立编排模型 | 同上 |

B 的 planner 输出经与认领同一套程序校验；无效计划记为规划失败并置空，不人工修好。
两组 worker 收到相同的系统规则与 objective 模板（仅 `_plan_block` 因组而异）。

## 2. 任务与目标

- `t1_independent`：实现 `src/slugs.py`、`src/ranges.py`。
- `t2_interface`：实现 `src/geometry.py`、`src/report.py`（共享 shape 接口）。
- `t3_evolving`：第 1 轮实现 `src/stats.py`（单文件）；第 2 轮新增 `mode`/`stdev`。
- 目标文本与 r2 完全相同（见 `driver/experiment.py` `T1_GOAL/T2_GOAL/T3_GOAL1/T3_GOAL2_ADD`）。

## 3. 轮次结构（每 run 2 轮，每轮 2 worker）

1. 冻结本轮 base：整合工作区快照 + `base_revision = sha256(路径+内容序列)`。
2. **认领阶段**（顺序，先认领者按 repeat：repeat0=w1，repeat1=w2；两组同 repeat 一致）：
   每 worker 1 次 claim SDK turn（`agent_ref=claim-worker`，`allowed_tools=("view-file",)`，
   `response_schema=ClaimSchema`）。程序原子校验后授予每人 ≤1 个可写文件；写
   `subtasks/r{n}-{worker}.md`（safe YAML，未认领 `lease_path: null`）。前一 worker 的
   claim/message 对后一 worker 同轮可见。
3. **编辑阶段**：每 worker 1 次 edit SDK turn（`agent_ref=edit-worker`，
   `allowed_tools=("view-file","create-file","edit-file")`，`response_schema=EditSchema`），
   在**独立 staging**（base 的完整拷贝）内由 SDK 真实写文件。评审者（无租约）同样跑 SDK 但
   程序拒绝其任何写入。编辑阶段顺序执行（w1 后 w2），二者对同一冻结 base；隔离 staging 保证
   公平性与无共享 writer。
4. **程序整合**：只接受租约路径的改动；越权/删除/语法错误拒绝并记录事件。写入整合工作区。
5. **验收**：`fixtures/<task>/acceptance.py --workspace <ws> [--stage N]`，`clean_env()`，30s 超时。
6. 下一轮注入本轮 program feedback。

每轮每文件仅 1 名 writer；单人最多 1 个租约；单文件任务另一人只 review。

## 4. 提示（逐字，frozen）

系统指令（`driver/host.py` `_AGENT_BODIES`，三段：claim-worker / edit-worker / planner）
与 objective 模板（`driver/experiment.py` `_claim_objective` / `_edit_objective` /
`_planner_objective`）随代码冻结。关键规则逐字包含：

- claim：`claim` 为相对路径或 null；≤1 个；≤240 字符 message；≤3×160 findings；
  不得读写工作区外；不得修改控制/验收。
- edit：仅当持有租约时用文件工具实际写入该文件，否则只复核；finish 返回 summary/findings。
- planner：输出 `{plan:[{worker,objective,files}],interface_notes,findings}`；文件不重叠；
  不得替 worker 写整份实现。

`response_schema` 由 SDK `finish` 工具承载；结构化 JSON 从 emitted `finish` 工具调用
`output_string` 取回（executor 本身不返回 structured 对象）。

## 5. 中继变换规则（两组同一常量）

链路：`SDK/harness → LocalAuthProxy(注入 Bearer) → MeteringRelay(127.0.0.1) → api.deepseek.com`。

中继**唯一**改写并逐请求记录 before/after：

- `max_tokens := 8192`（harness 默认不发送）；
- `thinking := {"type":"disabled"}`（harness 默认不发送）；
- `stream_options := {"include_usage": true}`（计量所需，原样记录改写）。
- 其余参数（`model`、`temperature`、tools、messages）不动；`temperature` 由 harness 决定
  （观测为未发送），两组一致，作为不可控变量如实记录。

中继不伪造模型输出、不压制 SDK 重试；记录每次 HTTP 的 `response_model`、`finish_reason`、
`usage`、`reasoning_content` 出现与否。**绝不**记录/落盘 Authorization 或密钥。

## 6. 预算（硬界）

### 校准（独立，已完成）
≤6 逻辑 turn / ≤24 HTTP / ≤100,000 reported tokens / ≤300s；实测见 `CALIBRATION.md`
（7 turn 偏差另记）。

### 正式
- 逻辑 SDK turn：6 run ×（8 worker + B planner 若干）= 6×8 + 3 = **51**（B 组 3 个 planner）。
- 真实 upstream HTTP：**≤350**（relay 计数，含 SDK 内部重试）。
- reported tokens：**≤1,500,000**（usage 缺失则显式 unknown，按 `prompt/4+8192` 保守预留，
  不宣称精确硬上限）。
- 墙钟：**≤1800s**（自首个请求起）。
- 每 turn：`max_model_calls=6`、`max_tool_calls=8`、总超时 90s，真实 cancel/close 清理。
- 基础设施重试：仅 executor 级，累计 ≤6 实际请求且计入 350；连续 3 次 upstream 基建失败即停。
- 预算不足的样本计失败，不额外补跑；所有失败纳入预定分母。

## 7. 判定规则（冻结后不改）

候选门：C 所有预定 run 均通过；每类质量不低于 B；0 额外越权 / 标准 YAML / SoT 问题；
所有 worker 真实停止；0 截断；相对 B 中位 run tokens 或耗时改善 ≥15%，另一指标中位数
不恶化 >10%；且所有任务类有实际 SDK 文件读写工具证据。

满足 → 建议“明确目标的小型任务可取消强制独立编排步骤，保留按需规划”；不声称可删除全部
规划能力或完整产品已验收。未满足 → 按实际指标给不确定/保留建议，不倒推。

## 8. SoT 与证据

- 每实体独立 Markdown frontmatter，`safe YAML` 序列化 + 标准解析（拒绝重复键）；
  未认领为合法 `null`。当前 lease / revision 为权威；JSONL 仅历史/消息/发现；SDK 原生
  session 归 SDK；`results.json` / summary 为派生。
- 证据：`turns/*.json`（真实 SDK 工具事件、finish、hook decisions）、relay per-call 记录、
  staging↔base 文件 diff、验收输出、停止/预算、`FREEZE_MANIFEST.txt`。
- 分析必须能从原始 usage/events/current state 重算；验证所有 frontmatter 标准可解析且无重复键。

## 9. 诚实边界

实验 host + 产品 adapter（`AntigravityExecutor`/`LocalAuthProxy`/`LocalOpenAIAgentConfig`）
+ 官方 SDK/harness；**非** UI、**非**完整产品运行时端到端、**非**沙箱逃逸保证、**未**覆盖
大工程 / 模糊需求 / 长会话 / 跨 turn resume。仅 openai-compat/DeepSeek。

## 10. 冻结决策（校准后、正式前）

- 正式样本：**6 runs**（每类每组 1 次，小样本），依据见 `CALIBRATION.md`。
- `max_model_calls/turn=6`，`max_tool_calls/turn=8`。
- 每 turn 新 SDK 会话（不复用 conversation_id）；两组一致；跨 turn resume 未覆盖。
- fixture / 提示 / 验收 / 中继变换 / 预算 / 判定 已由 `FREEZE_MANIFEST.txt` 哈希固定。
