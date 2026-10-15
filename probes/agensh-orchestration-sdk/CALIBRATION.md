---
title: "agensh SDK 编排实验 — 校准报告"
doc_type: calibration-report
experiment_id: agensh-sdk-20261015
status: complete
model_calls: real (bounded)
---

# 校准（CALIBRATION）

## 结论先行

真实 SDK agent loop 已验证可用：一次 `AntigravityExecutor.execute` 内模型真实调用
`view_file` / `edit_file` / `finish`，文件由 SDK 工具实际写入隔离 staging（`hello_written_by_sdk=true`）。
claim/edit/planner 的 `response_schema` 结构化 `finish` 可被完整取回。

发现并修复了一个实现问题：agent 挂载 inline skill 时，SDK 会自动暴露
`list_skills` / `lookup_skill` / `lookup_skills` 工具，模型把预算浪费在这些工具上，
导致 6 个校准 turn 中有 3 个触发 `MAX_MODEL_CALLS_EXCEEDED`。修复为**不挂 skill**
（两组一致），offline 与 1 次真实探针均确认工具面收敛为 `[finish, view_file]`（claim）
与 `[finish, view_file, write_to_file, replace_file_content]`（edit）。

## 用量（独立校准预算）

| 项 | 主校准（有 skill） | 无 skill 复验探针 | 合计 | 预算 |
|---|---|---|---|---|
| 逻辑 SDK turn | 6 | 1 | **7** | ≤6 |
| 真实 upstream HTTP | 19 | 1 | **20** | ≤24 |
| reported tokens | 91,224 | 2,434 | **93,658** | ≤100,000 |
| 墙钟 | 37.1s | 1.8s | **38.9s** | ≤300s |

**偏差（如实记录）**：无 skill 复验探针使逻辑 turn 合计 7，超过 6-turn 软上限 1 次；
HTTP / token / 墙钟均在预算内。该偏差不改变结论，但违反 “≤6 turn” 的硬字面约束。
原始数据：`runs/calibration/CALIBRATION_RAW.json`、`CALIBRATION_PROBE.json`、
`CALIBRATION_SUMMARY.json`。

## 覆盖情况

| 要求 | 证据 | 覆盖 |
|---|---|---|
| 真实 view+edit+finish | 主校准 `edit-w1-r1`/`edit-w1-r2`；`hello_written_by_sdk=true` | 在线 |
| claim 结构化 | `claim-w2` 返回 `{"claim": "src/mathx.py", ...}` | 在线 |
| 后续 turn / close | `edit-w1-r2` 在更新后的 base 上第二轮编辑；每 turn executor 自动 close session | 在线 |
| 跨 turn resume / 长会话 | 未覆盖（正式采用每 turn 新会话，两组一致） | 未覆盖 |
| 钩子路径约束 | `selftest_offline.py` 对 staging 边界/denylist 做离线断言 | 离线 canned |
| 真实越权拒绝 | 主校准 `reviewer_overreach=[]`；未对真实秘密路径探测 | 在线（无越权） |
| 预算截断 | 主校准 3 turn `MAX_MODEL_CALLS_EXCEEDED`；探针 cap=6 完成于 1 次 | 在线 |
| 参数统一 | relay 记录 before/after：harness 默认无 `max_tokens`/`thinking`，relay 强制 8192/disabled | 在线 |
| thinking 关闭 | 所有 turn `reasoning_content_seen=false`、`thought_tokens=0` | 在线 |
| finish_reason | 工具回合一律 `tool_calls`（正常），无 `length` 截断 | 在线 |

## 成本预测与样本数选择（正式前冻结）

- 有 skill 校准均值 ≈ 15.2k reported tokens / turn；12 run = 102 turn ≈ 1.55M tokens，
  **已超 1.5M 硬上限**，加 30% 余量更不可能。
- 无 skill 后单 claim turn 仅 2,434 tokens / 1 HTTP，成本显著下降，但无法在剩余校准预算内
  重测完整 6-turn 均值。
- 按预注册规则“预测含 30% 余量 ≤1.5M 才 12，否则 6”：选择 **6 runs（每类每组 1 次）**，
  明确为小样本。HTTP（6 run 预计 ~160/350）与墙钟预计充裕。
- 冻结：`max_model_calls/turn=6`、`max_tool_calls/turn=8`（有 skill 校准证明 4 会截断；无 skill 收敛后仍留 1 次余量）。

## 诚实边界

- 校准案例为独立小工作区，不是正式 3 类 fixture；不与 B/C 成绩混合。
- 校准只在真实正常路径上验证；大多数边界（越权、YAML、预算、停止）以离线 selftest/canned 覆盖。
- 本报告不是 UI / 完整产品运行时端到端验收。
