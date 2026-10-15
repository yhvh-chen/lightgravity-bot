---
title: "在真实 Antigravity SDK 内对比「B 仅初始规划 vs C 无独立编排」——实验结果报告"
doc_type: experiment-report
experiment_id: agensh-sdk-20261015
branch: experiment/agensh-sdk-20261015
base_commit: 9987d4f643b3ad02618d0c45fa35f8eb6ae84eef
sdk: google-antigravity==0.1.22
generated_at_utc: "2026-10-15T06:55:00Z"
status: formal-complete; candidate gate NOT met; B arm invalid
---

# 结果报告：真实 SDK 内 B/C 编排对比

> **执行者局部验证，不是独立版本 QA。** 本报告只描述本包执行范围：实验 host（driver/租约/
> 整合/验收）+ 产品 adapter（`AntigravityExecutor`/`LocalAuthProxy`/`LocalOpenAIAgentConfig`）
> + 官方 SDK/harness。**不是** UI、**不是**完整产品运行时端到端。

## 0. 结论先行

1. **真实 SDK agent loop 可用且已计量**：每个逻辑 turn 都由产品 `AntigravityExecutor.execute`
   驱动真实 SDK；模型实际调用 `view_file` / `edit_file`（上游 `write_to_file` /
   `replace_file_content`）/ `finish`，文件由 SDK 工具写入隔离 staging，再由程序按租约整合。
   6/6 正式 run 全部通过验收。
2. **但预注册候选门未满足（PASS=false）**，且 **B 组实验臂无效**：
   - 目标指标改善不足：C 相对 B 中位 run tokens 为 **−3.6%（更差）**，中位耗时 **+4.3%（更好）**，
     均未达 **≥15%**。
   - 有 13 次「越权」事件（B 6 / C 7），全部是模型在**自己 staging 内**写的临时校验脚本，
     程序已拒绝整合、未进入工作区；但按门定义仍非 0。
   - **B 的 planner 计划从未生效**：3/3 的 B planner 输出都被程序判为无效计划
     （字段名不符 `worker`/`objective`/`files`，且部分被 executor 的 2000 字符事件截断）。
     worker 在 B 组收到的文本与 C 组完全相同（“本轮没有提供计划”）。因此 B ≡ C + 1 次
     被丢弃的 planner 调用，**本轮的 B/C 对比不成立**。
3. **建议**：**不**主张取消独立编排步骤。保留规划能力，等修复 planner schema/结构化输出
   回收后再重跑对比。本次不作为“删除规划”的依据。

## 1. 用量（校准与正式分开）

| 阶段 | 逻辑 SDK turn | 真实 upstream HTTP | reported tokens | 墙钟 | 上限 |
|---|---|---|---|---|---|
| 校准（主 6 turn + 无 skill 复验探针 1 turn） | 7 | 20 | 93,658 | 38.9s | 6 turn /24 /100k /300s |
| 正式（6 run） | 51（48 worker + 3 planner） | **158** | **837,630** | **405s** | ≤51 /≤350 /≤1.5M /≤1800s |
| 合计 | 58 | 178 | 931,288 | 444s | ≤374 /≤1.6M |

- HTTP 由中继逐请求计数（含 SDK 内部重试）；token 为上游 reported usage 之和。
- 校准偏差：无 skill 复验探针使逻辑 turn 合计 7，超过 6-turn 软上限 1 次（HTTP/token/墙钟均在限内），
  已在 `CALIBRATION.md` 记录。
- 参数统一只在中继发生：harness 默认**不发送** `max_tokens`/`thinking`；中继强制
  `max_tokens=8192`、`thinking={"type":"disabled"}`、`stream_options.include_usage=true`，
  并逐请求记录 before/after。全程 `reasoning_content_seen=false`、`thought_tokens=0`。
  工具回合 `finish_reason=tool_calls`（正常），**0 次 length 截断**。

## 2. B/C 质量与成本

| 指标 | B（仅初始规划） | C（无独立编排） |
|---|---|---|
| run 数 / 全通过 | 3 / 3 | 3 / 3 |
| 最终验收 | 21/21 | 21/21 |
| 第一轮验收 | 17/17 | 17/17 |
| 中位 run tokens | 132,376 | 137,124 |
| tokens 合计 | 428,085 | 409,545 |
| HTTP 合计 | 82 | 76 |
| 中位 run 耗时 | 67.7s | 64.8s |
| 越权事件（已拒绝） | 6 | 7 |
| `budget_exhausted` turn | 1 | 3 |
| `failed` turn | 1 | 0 |
| length 截断 | 0 | 0 |
| 标准 YAML / SoT 问题 | 0 | 0 |
| 真实 SDK 文件读写工具证据 | 有 | 有 |

分类（每类 1 次）：三类 B/C 均 100% 通过。`t2_interface` C 明显更省（133,881 vs 167,820 tokens），
`t1`/`t3` B 略省；样本量 n=1/类，不可外推。

## 3. 预注册候选门判定

| 条件 | 结果 |
|---|---|
| C 所有预定 run 通过 | ✅ |
| 每类质量 ≥ B | ✅ |
| 0 额外越权 / YAML / SoT 问题 | ❌（13 次 staging 内越权事件，虽已拒绝） |
| 所有 worker 真实停止 | ✅（无泄漏 harness；每 turn executor 清理） |
| 0 截断 | ✅（0 length 截断；但有 budget_exhausted turn） |
| C 中位 tokens 或耗时改善 ≥15% | ❌（tokens −3.6%，耗时 +4.3%） |
| 另一指标不恶化 >10% | ✅ |
| 所有任务类有真实 SDK 文件读写证据 | ✅ |
| **总判定** | **PASS = false** |

额外有效性缺陷：**B 臂无效**（planner 计划全部程序判无效，worker 未收到计划），
使 B/C 对比退化为“C vs C+被丢弃的 planner 调用”。

## 4. 真实 SDK 工具 / 停止 / 隔离证据

- **真实文件读写**：51 个 turn 中，worker turn 均出现 emitted `view_file` 与 `edit_file`；
  中继请求 tool 列表含 `write_to_file` / `replace_file_content`。生产文件的实际写入经
  staging↔base 文件 diff 与 `accepted` 路径互相印证（见各 run `turns/*.validate.json`）。
- **writer 利用率**：所有 run 的 `writer_utilization` 均为 2/2（持租约者确有实际写入）。
- **隔离**：每 worker 每轮独立 staging 目录（base 的完整拷贝），无共享代码并发 writer；
  程序只整合租约路径；控制文件/验收/参考解从不进入 staging。
- **路径钩子**：每 turn 注册 `pre_tool_call_decide` 白名单，只允许 staging 内路径；
  绝对路径越界/denylist 由离线 canned 断言验证（未对真实秘密路径探测）。
- **停止/回收**：每 turn executor `finally` 关闭 agent 并停止 loopback proxy；运行后
  `/proc` 无 `localharness` 进程（comm 精确匹配 = 0）；中继已 stop。
  *限制*：per-turn proxy-stop 确认未单独持久化，只有聚合无泄漏检查。
- **凭证**：key 在 spawn 前读入内存并 `InMemoryCredentialResolver`，随后从进程环境移除；
  harness/验收子进程继承不到；日志/证据无密钥（`evidence/` 无 Authorization）。

## 5. 标准 YAML 与 r2 证据缺口

- **r2 缺口（只读复核，不改旧数据）**：r2 用自定义逐行解析，掩盖了非法标量。
  用标准 safe YAML 重审 `probes/agensh-orchestration-r2` 的 108 个 frontmatter 文件，
  **12 个 subttask 文件非法**（全部是 T3“无认领 reviewer”的 `lease_path: -`，
  `ScannerError: block sequence entries are not allowed`）；其余 96 个可解析。
  以可解析文件为准，parsed lease 与 `events.jsonl` 的 `claim_result` **一致**。
  因此 **r2 “全部 frontmatter 可解析”的候选门未被证实**；本报告不沿用其“全通过”说法。
  证据：`evidence/r2_yaml_audit.json`。
- **本轮**：所有 SoT 用 safe YAML 序列化（未认领为合法 `null`），标准解析 + 重复键拒绝。
  正式 36 个 frontmatter 文件 **0 解析错误、0 重复键**（`evidence/formal_yaml_audit.json`），
  且与 events/claim/ref/状态一致。

## 6. 关键失败与偏差（全部如实记录）

1. **B 臂无效（最重要）**：`PlanSchema.plan` 使用 `list[dict]`，未约束 item 字段；模型输出
   `assigned_files`/`owns_files`/`assignee` 等字段，程序校验失败 → `plan=None`。
   离线从 SDK 原生 session DB 恢复完整 planner 输出（`evidence/planner_recovery.json`）证实
   3/3 均程序无效；即便字段正确，executor 对 emitted 工具参数 **2000 字符截断**
   也会使冗长计划在事件流中损坏（t1/t3 planner 的 `output_string` 恰为 2000 且 JSON 不完整）。
   worker 因此收到与 C 相同的“无计划”提示。
2. **`finish` 结构化回收限制**：`ExecutorResult` 不返回 structured 对象；本实验从 emitted
   `finish` 工具调用 `output_string` 取回，受 `_bounded(2000)` 限制。51 turn 中 5 turn
   `finish_parse_error`（2 planner + 3 worker）；worker turn 仍可能完成实际写入。
3. **校准超 1 turn**：见 §1。
4. **无 skill 修复未在正式前用真实模型完整复测**：仅用 1 次真实探针 + 离线工具面断言确认，
   完整 6-turn 均值未重测。
5. **顺序敏感性未覆盖**：6-run 全部 repeat0 → 先认领者恒为 w1，未做 w2-first 变体。
6. **单样本/类**：每类每组仅 1 次，统计功效低；中位/配对差异应视为噪声级别。

## 7. 未覆盖 / 边界

- 非 UI、非完整产品运行时端到端；无 coordinator / MCP / Triggers / 真实工程规模。
- 仅 openai-compat / DeepSeek；`temperature` 由 harness 决定（观测为未发送），
  作为不可控变量两组一致。
- 无沙箱逃逸保证；`sandbox` 只是 SDK 上报状态。
- 未覆盖跨 turn resume / 长会话 / 大语料 / 模糊需求；每 turn 新会话（两组一致）。

## 8. 结论与建议

- 真实 SDK 工具循环 + 程序化租约/消息/隔离/整合/验收在本实验 host 中**可运行且可计量**。
- **候选门未通过，且 B 臂无效**，因此**不能**得出“可取消强制独立编排步骤”的结论；
  也**不能**据此删除规划能力。
- 修复方向（下一轮，不在本包改动）：把 planner 输出 schema 收紧为嵌套 pydantic 模型
  （强制 `worker`/`objective`/`files`），并从 SDK 原生 session/structured output 直接回收
  计划而非经 emitted 工具事件（或降低输出长度），然后重跑 B/C；同时把 staging 内临时校验
  文件纳入合法产出或提示禁止，以区分“越界”与“自测草稿”。
