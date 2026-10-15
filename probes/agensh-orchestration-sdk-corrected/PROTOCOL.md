---
title: "agensh SDK 编排对比实验（纠正版）— 冻结协议"
doc_type: protocol
experiment_id: agensh-sdk-corrected-20261015
branch: experiment/agensh-sdk-corrected-20261015
worktree: /tmp/lightgravity-worktrees/agensh-sdk-corrected-20261015
probe_dir: probes/agensh-orchestration-sdk-corrected
base_commit: 9987d4f643b3ad02618d0c45fa35f8eb6ae84eef
sdk: google-antigravity==0.1.22
frozen_at_epoch: 1792048031
frozen_at_utc: "2026-10-15T07:07:11Z"
status: frozen
formal_runs: 6
order_seed: 20261015
---

# 冻结协议（正式运行前）

本文件在纠正版正式运行**之前**冻结，精确冻结时刻为 Unix epoch `1792048031`
（`2026-10-15T07:07:11Z`）。正式启动后不再修改参数 / 提示 / 执行逻辑 / fixture /
验收；致命 bug 则停止并保存证据。冻结清单与 sha256 见 `evidence/FREEZE_MANIFEST.txt`
（manifest 头部记录同一 epoch/UTC）。

## 0. 与首轮的关系（纠正理由）

首轮 SDK 实验（`agensh-sdk-20261015`）因 **B 组 3/3 计划无效**（产品 executor 把发射的
工具参数截到 2000 字符 + 计划键名不符）而导致 B≡C，对比无效；此外 read guard 因真实
wire 键 `AbsolutePath` 未被识别而存在盲区，`max_completion_tokens=65535` 未被改写。
本纠正版只修复这些测量/有效性问题，不修改首轮结果、不修改产品源码。首轮失败证据见
`evidence/AUDIT.source.md`（来源哈希见 `evidence/SOURCE_COPY.sha256`）。

## 1. 目标与分组（单变量）

| 组 | 独立编排模型 | 其余完全相同 |
|---|---|---|
| B | 运行开始时 **恰好 1 次** planner SDK turn（严格结构化输出） | 程序化认领、同轮消息、工具权限、每轮 base、两轮、验收 |
| C | **无**独立编排模型 | 同上 |

B 的 planner 输出由 `PlanSchema`（受限子模型）与程序规则双重校验；无效即判 `baseline_invalid`，
停止，绝不静默以 `plan=None` 继续跑 C。正式任一 B plan 无效 → 本轮比较失败停止。

## 2. 任务与目标

- `t1_independent`：实现 `src/slugs.py`、`src/ranges.py`。
- `t2_interface`：实现 `src/geometry.py`、`src/report.py`（共享 shape 接口）。
- `t3_evolving`：第 1 轮实现 `src/stats.py`（单文件）；第 2 轮新增 `mode`/`stdev`。

目标文本与首轮完全相同（`driver/experiment.py` `T1_GOAL/T2_GOAL/T3_GOAL1/T3_GOAL2_ADD`）。

## 3. 轮次结构（每 run 2 轮，每轮 2 worker）

1. 冻结本轮 base：整合工作区快照 + `base_revision = sha256(路径+内容序列)`。
2. **认领阶段**（顺序；repeat0 先 w1，repeat1 先 w2；两组同 repeat 一致）：每 worker 1 次
   claim SDK turn（`claim-worker`，只读，`ClaimSchema`）。程序原子校验后授予每人 ≤1 个可写
   文件；写 `subtasks/r{n}-{worker}.md`（safe YAML，未认领 `lease_path: null`）。
3. **编辑阶段**：每 worker 1 次 edit SDK turn（`edit-worker`，读写工具；`EditSchema`），在
   **独立 staging** 内由 SDK 真实写文件。评审者（无租约）同样跑 SDK 但钩子在执行前拒绝其任何
   写入。编辑基于同一冻结 base。
4. **程序整合**：只接受租约路径的改动；越权/删除/语法错误/超限拒绝并记录事件。
5. **验收**：`fixtures/<task>/acceptance.py --workspace <ws> [--stage N]`，`clean_env()`，30s。
6. 下一轮注入本轮 program feedback。

## 4. planner 严格 schema 与程序规则

`PlanItem`（pydantic，`extra="forbid"`）：

- `worker: Literal["w1","w2"]`；
- `objective: str`，`min_length=1`、`max_length=400`；
- `files: list[str]`，每项 `max_length=1`（每 assignment 最多 1 文件）。

`PlanSchema`（`extra="forbid"`）：`plan: list[PlanItem]`（1..4）、`interface_notes: str`
（≤600）、`findings: list[str]`（≤3）。程序额外要求：恰好 w1+w2 各一次；当前全部相对可写
文件恰好各分配一次；同路径不重复 writer；`files` 必须来自当前可写相对文件。任一项不满足即无效。

该 pydantic 模型同时作为 SDK `response_schema`（`AgentConfig` 会转成 JSON schema：
`additionalProperties:false`、`enum`、`maxItems:1`），因此模型侧与程序侧同时受限。planner
提示逐字包含全部可写文件、单 writer、单文件 reviewer（`files=[]`）规则，且不写实现代码。
worker objective 注入 `plan_id`（校验后 canonical JSON 的 sha256 前 16 位），驱动逐 turn
断言 `plan_id` 出现在对应 worker prompt 中（`plan_injected`）。

## 5. 无损 structured output 与停止证据

- **finish**：产品 `executor._bounded` 会把发射的工具参数截到 2000 字符，因此控制数据一律
  取 **SDK 原生 `pre_tool_call` 钩子**收到的完整 `ToolCall.args`（`output_string`），并记录
  来源/长度/sha256；SDK 原生 session DB 完整负载作为离线交叉核对（`session_db_matches_hook`）。
  发射的（有损）负载只作诊断并比较 `emitted_truncated`。禁止从有损摘要取控制数据。
- **hook 真实 file 字段**：识别 `AbsolutePath`（view_file）、`TargetFile`（写）等真实 wire
  键；未知 file 参数 **fail-closed**（`unknown_file_argument` deny）。读限授权根（fixture/staging），
  写限持有 lease 路径；无 lease reviewer 无写权；拒绝 root 外、控制/验收/参考解/秘密文件。
- **停止**：每 turn 记录 `proxy.stop()` 返回值与停止后 `is_running`、`auth_proxy_stopped`
  check 记录、`agent.__aexit__`（`ensure_closed`）返回、localharness PID 前后集合、代理端口
  是否仍可连接。缺正向证据即 `unknown`，不释放 lease、不通过门。

## 6. 中继变换（两组同一常量）

链路：`SDK/harness → LocalAuthProxy(注入 Bearer) → MeteringRelay(127.0.0.1) → api.deepseek.com`。

中继**唯一**改写并逐请求记录 before/after：

- **删除** `max_completion_tokens`（首轮观测到 65535 别名）；
- `max_tokens := 8192`；
- `thinking := {"type":"disabled"}`；
- `stream_options := {"include_usage": true}`。

改后断言实际发送只有一种输出上限（`output_limit_fields == ["max_tokens"]`），否则报错。
其余参数（`model`、`temperature`、tools、messages）不动；`temperature` 沿用 harness 值
（观测为未发送，两组一致）并如实记录。`finish_reason=tool_calls` 属正常；`length` 才是输出截断。

## 7. 校准（独立小 fixture，正式前已完成）

独立两文件 fixture（`src/alpha.py`、`src/beta.py`），**不属任何正式类**：

1. 1 次 planner：两文件严格有效 plan、完整无损 payload；
2. 1 次 edit：`view_file` + 真实写入租约文件 + `finish`，真实非空路径 hook + 正向停止证据。

硬界：**≤2 逻辑 turn、≤12 真实 HTTP、≤60,000 reported tokens、≤180s**；全部尝试计入，不额外复验。
结果：2 turn / 6 HTTP / 26,628 tokens / 12.2s，全部前置检查通过（详见
`evidence/phaseB/CALIBRATION_RECHECK.json`）。若校准失败或关键缺口未闭环则停止失败报告，不绕开真实 SDK。

## 8. 正式运行与随机化

3 类 × B/C × 各 1 = 6 run；2 worker、2 轮。固定配对随机化：任务类顺序随机、每类 B/C 先后随机，
seed=`20261015` 并记录实际顺序；同 pair worker 先后相同。B 仅 1 次初始 planner，C 无独立 planner；
其余程序 claim、同轮消息、worker 模板/工具权限、先顺序 claim 再 staging edit、验收、第二轮
evolving 补要求，两组一致。每 run 独立会话、独立初始 hash，不跨 run 泄漏，不参考先前结果选择输出。

每 turn `max_model_calls=6`、`max_tool_calls=8`（沿用校准冻结值）。

## 9. 正式硬界

51 逻辑 SDK turn（48 worker + 3 planner）、220 真实 upstream HTTP（含所有 SDK 重试）、
1,300,000 reported tokens、900s（首个正式请求起）。HTTP 重试最多 6 且含在 220 内；连续 3 次
基础设施失败停止。达到预算暂停并保留失败分母，绝不自动扩容，不在看到成绩后补跑。

## 10. 候选门与指标（纠正版；不修改首轮规则）

- **有效性前置**：所有 B 计划有效且真实注入；所有组有实际 SDK 工具读写证据；无损 structured
  输出；标准 YAML 合法无重复键；每 turn 停止有正向证据；0 输出 `length` 截断；真实参数单一
  输出上限。未满足即“对比无效/未完成”，不套成本门。
- **正确性**：C 预定 3 run 全通过；每类不低于 B。
- **权限**：0 实际越界读/写或未授权整合；钩子对未知字段拒绝。被拦截尝试单列次数与原因，不混同
  已发生越界。SDK 尝试写测试脚本应由钩子在执行前拒绝并计数，不放宽权限帮助过关；所有
  unauthorized diff 仍拒绝；C 额外违反控制状态或 root 读则失败。
- **收益**：相对 B 中位 run tokens 或中位耗时改善 ≥15%，另一指标中位数不恶化 >10%；计入
  plan/claim/edit/被拒工具/所有 HTTP 重试总成本。若品质/权限成立但未达收益门，结论
  “可编排运行，收益未达门，不支持仅凭成本删除”，不强行正结论。
- 每类 n=1 仅信号，不统计非劣，不推广大工程/模糊需求/长会话。全部验收条目、首轮/最终、
  turn/HTTP/usage/cache/reasoning/finish_reason、planner/claim/edit 分项、工具/diff/lease/消息/
  身份/顺序、拒绝/越界、停止/端口/PID、YAML/SoT 均按 run/类报告。

## 11. 预算诚实

- 所有时间来自实际 UTC 时钟；禁止手填未来时刻/占位符。
- 校准单独 2 turn/12 HTTP/60k，合计与正式 ≤232 HTTP / ≤1,360,000 tokens；pi 开发用量另计。
- 并发预留输入+输出 token；usage 缺失按 unknown 保守计数，不声称精确 budget。

## 12. 输入/来源哈希

冻结输入（driver、fixtures、产品 adapter 只读引用、SDK 版本与 localharness 二进制）逐文件
sha256 记录于 `evidence/FREEZE_MANIFEST.txt`。源实验目录只读，来源哈希见
`evidence/SOURCE_COPY.sha256`。
