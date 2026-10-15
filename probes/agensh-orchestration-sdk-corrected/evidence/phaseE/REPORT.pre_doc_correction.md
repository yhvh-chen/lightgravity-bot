---
title: "agensh SDK 编排对比实验（纠正版）— 结果报告"
doc_type: report
experiment_id: agensh-sdk-corrected-20261015
status: complete
first_model_sample_utc: "2026-10-15T07:05:00Z"
formal_start_utc: "2026-10-15T07:07:30Z"
formal_end_utc: "2026-10-15T07:13:42Z"
sdk: google-antigravity==0.1.22
---

# 结果报告（纠正版）

## 0. 一句话结论

纠正版**有效性前置全部成立**（3/3 B 计划有效且真实注入、无损 structured 输出、每 turn 停止
正向、0 输出截断、真实参数单一输出上限、标准 YAML 合法），**权限门成立**（15 次写入被钩子在
**执行前**拒绝，0 次实际越界写或未授权整合）；但**收益未达门**：C 相对 B 的中位 relay tokens
改善 8.84%、中位耗时改善 3.16%，均 < 15%。因此结论为
**“无编排可运行，收益未达门，不支持仅凭成本删除独立编排”**。纠正版**不**把首轮的无效 B/C
对比洗成成功，也**不**强行正结论。

## 1. 背景与纠正范围

首轮（`agensh-sdk-20261015`）的真实 SDK 工具循环/文件写入/验收/写防护可用，但 B 组 3/3 计划
无效（产品 executor 把发射工具参数截到 2000 字符 + 计划键名不符）使 B≡C，B/C 对比无效；read
guard 因真实键 `AbsolutePath` 未识别存在盲区；`max_completion_tokens=65535` 未被改写。纠正版
只修测量/有效性问题，不修改首轮结果、不修改产品源码、不修改 `PROJECT.md`。

## 2. 有效性前置（全部满足）

| 前置 | 结果 | 证据 |
|---|---|---|
| 所有 B 计划有效 | 3/3 | `results.json` `plan_valid=true` |
| B 计划真实注入 worker prompt | 3/3（每 run 8 个 worker turn 全 `plan_injected=true`） | `results.json` `plan_injection.all_true`，turn 记录 `plan_id` |
| 无损 structured 输出 | 所有**产生 finish 的 turn** 来源=`hook` 且与原生 session DB 一致、`emitted_truncated=false` | turn `finish_source`/`session_db_matches_hook` |
| 标准 YAML 合法无重复键、`lease_path: null` | 6/6 run `sot_issues=[]` | `check_sot` + `sotyaml` |
| 每 turn 停止正向证据 | 51/51 turn `stop=confirmed` | `stop_evidence`（proxy.stop 返回 True、`is_running_after=false`、`auth_proxy_stopped=passed`、`ensure_closed=true`、harness PID 退出、端口关闭） |
| 0 输出 `length` 截断 | 0 | relay `finish_reasons` 全为 `tool_calls` |
| 真实参数单一输出上限 | 全部请求 `output_limit_fields=["max_tokens"]` | relay before/after（`max_completion_tokens` 被删除） |

> 说明：6 个 run 中各有若干 turn 因每 turn `max_model_calls=6` 触顶而 `budget_exhausted` /
> `failed`，这些 turn **未产生 finish**（`no_finish_call`），已如实记入分母；这不影响
> “产生 finish 的 turn 均无损”。它们是真实的 agent-loop/限额结果，不是测量缺陷。

## 3. 逐类正确性（n=1，仅信号）

| 类 | B 首轮/最终 | C 首轮/最终 | B relay tokens | C relay tokens | B 耗时 s | C 耗时 s | B HTTP | C HTTP |
|---|---|---|---|---|---|---|---|---|
| t1_independent | 6/6 → **6/6** | 6/6 → **6/6** | 126,594 | 126,961 | 55.97 | 55.83 | 24 | 24 |
| t2_interface | 6/6 → **6/6** | 6/6 → **6/6** | 144,758 | 131,961 | 57.65 | 55.28 | 25 | 24 |
| t3_evolving | 5/5 → **5/9** | 5/5 → **9/9** | 170,348 | 144,601 | 73.96 | 72.96 | 30 | 27 |

- C 预定 3 run **全通过**（t1 6/6、t2 6/6、t3 9/9）。
- 每类 C 不低于 B：t1、t2 相等；t3 C(9/9) > B(5/9)。（若按“B 不低于 C”读，则 t3 不成立；
  本报告两种读法都列出。）
- t3 B 第 2 轮：负责 `src/stats.py` 的 writer 触顶 `budget_exhausted`，未加入 `mode`/`stdev`，
  故最终 5/9；第 1 轮 `mean`/`median` 全部通过。C 同轮完成 9/9。

## 4. 权限与越权（关键纠正点）

| 指标 | B | C | 合计 |
|---|---|---|---|
| 钩子调用决策数 | 99 | 95 | 194 |
| **执行前拒绝**（`allow=false`） | 8 | 7 | **15** |
| 实际越界写（staging 已写后拒绝整合） | 0 | 0 | **0** |
| 未授权整合 diff | 0 | 0 | **0** |
| 成功整合的租约写 | 6 | 6 | 12 |

15 次执行前拒绝的原因分布：

- **非租约 staging 写**（模型想写自测脚本，如 `_check_slugs.py` / `_verify.py` / `stats_check_tmp.py`）：
  在本轮中由钩子**在执行前**拒绝（首轮是“先写入 staging、再在整合阶段拒绝”，本轮改为前置阻断）。
- **root 外写/读**：`/tmp/check_report_w2.py`、`/tmp/stats_check.py`、`/proc/<pid>/fd/pipe:[...]`
  等，均因 `escapes the authorized root` 拒绝。
- **无租约 reviewer 写**：`verify_review.py`，因 `caller holds no lease` 拒绝。

注意：本报告**不**把首轮的 13 次临时文件改口为“前置阻断”——那是首轮 staging 真写后拒绝整合的
历史数据；本轮实测为 0 实际越界、15 前置拒绝。

## 5. 收益门

| 指标 | B 中位 | C 中位 | 改善 | 门 |
|---|---|---|---|---|
| relay reported tokens / run | 144,758 | 131,961 | **8.84%** | ≥15% ✗ |
| 墙钟 / run | 57.653 s | 55.829 s | **3.16%** | ≥15% ✗ |

- 另一指标未恶化 >10%：tokens 与耗时 C 均优（正改善）。
- 计入 plan/claim/edit/被拒工具/所有 HTTP 重试的总成本后，收益仍未达 15% 门。
- 因此**不**支持“仅凭成本删除独立编排”。

### 分项成本（relay tokens，中位/合计）

| 组 | planner | claim | edit | 合计 |
|---|---|---|---|---|
| B | 3,442（中位）/ 10,090 | 38,000（中位） | 103,289（中位） | 441,700 |
| C | 0 | 35,545（中位） | 97,373（中位） | 403,523 |

（B 的 planner 开销约占 2.3%。）

## 6. 停止证据

51/51 turn 正向：`proxy.stop()` 返回 `True`、`is_running_after=false`、`auth_proxy_stopped`
check=`passed`、`agent.__aexit__/ensure_closed` 返回 `True`、逐 turn 前后 localharness PID 集合
核对（无残留，PID 探测按 `/proc/<pid>/exe` basename 匹配真实二进制，避免误匹配命令行文本）、
代理端口停止后不可连接。`stop_confirmed` 产品字段在正常完成路径仍为 `null`（产品只在
cancel/timeout 设置），本报告不据此假写 `true`，而以实验侧正向观测为准。

## 7. 费用（旧新分开；未知不猜）

| 批次 | 逻辑 turn | 真实 HTTP | reported tokens | 墙钟 | 备注 |
|---|---|---|---|---|---|
| 首轮 formal（审计口径） | 51 | 158 | 837,630 | 约 405 s（事件跨度 06:41:07Z–06:47:52Z） | B 计划全无效，对比不成立 |
| 首轮 calibration（审计） | 7（6+1） | 未知 | 未知 | 未知 | 违反当时 ≤6 字面约束（事后软化措辞，保留披露） |
| 纠正 calibration | 2 | 6 | 26,628 | 12.17 s | 独立 fixture；离线复核通过 |
| 纠正 formal | 51 | 154 | 845,223 | 372 s | 有效 |
| **纠正合计** | 53 | **160** | **871,851** | ~384 s | 在 232 HTTP / 1,360,000 tokens 合计界内 |

首轮校准的 HTTP/token 未知，不猜测。pi 开发用量不计入。

## 8. 限制

- 每类 n=1，仅信号；不做统计非劣检验，不推广到大工程、模糊需求或长会话。
- 每 turn `max_model_calls=6`（校准冻结沿用）导致部分 turn `budget_exhausted`；B 的 t3 因此
  低于 C。这是受控但会影响结论的 agent-loop 现象，已如实计入。
- `temperature` 未由 harness 发送（两组一致，如实记录，未私自优化）。
- 本实验不是独立版本 QA、不是 UI 完整产品端到端；只比较“独立编排模型”这一单变量。

## 9. 结论

在有效、无损、可审计的前提下：两组都能真实运行 SDK 工具循环并完成文件写入与验收；权限前置
阻断有效；但独立 planner 编排在本次 n=1 信号下**没有带来 ≥15% 的 token 或时间收益**（8.84% /
3.16%），且在 t3 反而更低（tokens 更高、得分更低）。故**不支持仅凭成本删除独立编排**；同时
也不主张编排必然更优（样本极小）。

## 10. 证据索引

- `evidence/AUDIT.source.md`：首轮只读审计（失败证据，来源哈希见 `SOURCE_COPY.sha256`）。
- `evidence/phaseA/`：0 模型离线返修；`offline_replay.json`（6110/1196/7690 字符恢复 + 新 schema 拒绝）、`selftest_offline.stdout.txt`（全过）、`COMMANDS.txt`。
- `evidence/phaseB/`：校准 raw stdout、`CALIBRATION_RECHECK.json`（19 项全过）。
- `evidence/phaseD/analysis.json`：逐 run/类全部指标（无 runner 重算）；`formal.stdout.txt`。
- `runs/formal/*/turns/*.json`：每 turn 无损 `finish_payload`、`captured_calls`、`stop_evidence`、`hook_decisions`、`relay_calls`。
- `runs/formal/*/sessions/*.db`：SDK 原生 session DB（原始证据）。
- `evidence/FREEZE_MANIFEST.txt`：正式前冻结（epoch `1792048031`）。
- `evidence/EVIDENCE.sha256`：逐文件哈希清单。
