---
title: "agensh SDK 纠正版 — 校准记录"
doc_type: calibration
experiment_id: agensh-sdk-corrected-20261015
frozen_at_epoch: 1792048031
frozen_at_utc: "2026-10-15T07:07:11Z"
status: passed
---

# 校准记录（纠正版）

## 目的

在启动正式 6-run 对比前，用**独立小 fixture**（不属于任何正式任务类）确认纠正后的真实 SDK
链路满足协议，并测量每 turn 的 HTTP/token/时间以证明正式硬界可行。校准只做 2 个逻辑 turn：
1 个 planner（必须形成**两文件严格有效 plan** 且无损 payload）+ 1 个 edit（实际 `view_file` +
真实写入租约文件 + `finish`，真实非空路径 hook + 正向停止证据）。安全 canary 拒绝检查全部
离线重放（见 `driver/selftest_offline.py` / `evidence/phaseA/`），不浪费模型额度。

## 硬界

| 项 | 上限 | 实测 |
|---|---|---|
| 逻辑 SDK turn | 2 | **2** |
| 真实 upstream HTTP | 12 | **6** |
| reported tokens | 60,000 | **26,628** |
| 墙钟 | 180 s | **12.17 s** |

所有尝试计入；未做任何额外复验，未扩大预算。

## fixture

独立两文件工作区（非正式三类）：`src/alpha.py`（`add` 桩）、`src/beta.py`（`multiply` 桩）。

## 过程与结果

| turn | agent | HTTP | tokens | finish 来源 | payload 字符 | session DB 与 hook 一致 | 停止 |
|---|---|---|---|---|---|---|---|
| planner | planner | 2 | 6,515 | hook | 882 | 是 | confirmed |
| edit-w1 | edit-worker | 4 | 20,113 | hook | 861 | 是 | confirmed |

- planner 产出严格有效 plan（`plan_id=fd3a2a8f6135d226`）：w1→`src/alpha.py`、w2→`src/beta.py`，
  每项 1 文件，覆盖全部可写文件，额外字段被 schema 拒绝。
- edit-w1 持有 `src/alpha.py` 租约，钩子记录 `view_file`（非空路径，allow）与 `edit_file`
  （非空路径，allow）；真实写入后文件内容为 `def add(a, b): return a + b`。
- worker prompt 注入了 `plan_id`（`plan_injected=true`）。
- 真实上游同时出现 `max_completion_tokens=65535` 与 `max_tokens=8192`；中继**删除**别名后
  只发送 `max_tokens=8192`（`output_limit_fields=["max_tokens"]`），`thinking.disabled`，
  `stream_options.include_usage`；`temperature` 未发送（如实记录）。
- `finish_reason` 均为 `tool_calls`（正常），0 次 `length`。

## 校准实现 bug 与离线复核（诚实披露）

首次校准的 acceptance helper 误同时检查了 `alpha.py` 与 `beta.py` 两个文件，而单次 edit turn
只持有一个租约、只写一个文件，故 `passed=false`（`AssertionError: None`）。这是**校准 harness
的 bug，不是模型/协议缺口**：planner 有效、注入成立、真实写入正确、停止确认。

修正 helper 仅检查**租约文件**后，对磁盘上已存在的校准产物做**离线复核**（0 模型调用、
不新增样本、不改写 `CALIBRATION_RAW.json`），结果见 `evidence/phaseB/CALIBRATION_RECHECK.json`：
全部 19 项前置检查通过。校准一次尝试即满足预算（2 turn / 6 HTTP / 26,628 tokens / 12.17 s）。

## 原始证据

- `runs/calibration/CALIBRATION_RAW.json`：原始 turn/injection/stop/relay 记录。
- `evidence/phaseB/calibration.stdout.txt`：首次校准运行 stdout（`passed=false`，原样保留）。
- `evidence/phaseB/CALIBRATION_RECHECK.json` / `.stdout.txt`：离线复核（`all_passed=true`）。
- `runs/calibration/sessions/`、`runs/calibration/staging/`：原生 session DB 与最终 staging。

## 结论

校准通过。正式运行可启动，采用每 turn `max_model_calls=6`、`max_tool_calls=8`。
