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

### usage 核对（relay reported vs driver 快照，纯离线算术）

本核对只读已有 raw，不重跑、不改 driver；以原始中继 **reported usage** 为准。

以 `runs/formal/t2_interface__C__r0/turns/r1-edit-w2.json` 为例，该 turn 的 6 个
`relay_calls[].usage.total_tokens` 依次为 5,085、5,919、6,734、7,063、**7,997**、8,344，
求和 = **41,142**；同 turn SDK `usage.total_tokens` = **33,145**，差 **7,997**。相应地在总量上，
纠正版新总中继 **845,223** 与 driver 快照 **837,226** 的差同样是 **7,997**
（`evidence/phaseD/analysis.json`：`relay_total_tokens` vs `driver_budget_total_tokens`）。

- 6/6 run 的 `tokens_unknown_calls=0`，上述 relay usage 均有回报，**不是** unknown 估算。
- 该 7,997 差异的根因（缓存 / 重试 / 迟到计费等）**本次未验证，不作猜测**。
- 故最终收益以原始中继 reported usage 为准（即上表 8.84% / 3.16%）；**不**采用 driver 快照口径的
  12.29% 作为最终收益。

## 6. 停止证据

51/51 turn 正向：`proxy.stop()` 返回 `True`、`is_running_after=false`、`auth_proxy_stopped`
check=`passed`、`agent.__aexit__/ensure_closed` 返回 `True`、逐 turn 前后 localharness PID 集合
核对（无残留，PID 探测按 `/proc/<pid>/exe` basename 匹配真实二进制，避免误匹配命令行文本）、
代理端口停止后不可连接。`stop_confirmed` 产品字段在正常完成路径仍为 `null`（产品只在
cancel/timeout 设置），本报告不据此假写 `true`，而以实验侧正向观测为准。

## 7. 费用（旧新分开；未验证不猜）

| 批次 | 逻辑 turn | 真实 HTTP | reported tokens | 墙钟 | 备注 |
|---|---|---|---|---|---|
| 首轮 formal（审计口径） | 51 | 158 | 837,630 | 约 405 s（事件跨度 06:41:07Z–06:47:52Z） | B 计划全无效，对比不成立 |
| 首轮 calibration（审计） | 7（6+1） | 20 | 93,658 | 38.879 s | 7/6 硬上限违规（只读首轮 `CALIBRATION_SUMMARY.json`；首轮 raw 原样保留） |
| 纠正 calibration | 2 | 6 | 26,628 | 12.17 s | 独立 fixture；离线复核通过 |
| 纠正 formal | 51 | 154 | 845,223 | 372 s | 有效 |
| **纠正合计** | 53 | **160** | **871,851** | ~384 s | 在 232 HTTP / 1,360,000 tokens 合计界内 |

首轮校准的 HTTP/token 并非 unknown：只读首轮
`probes/agensh-orchestration-sdk/runs/calibration/CALIBRATION_SUMMARY.json` 可得 7 turn / 20 HTTP /
93,658 tokens / 38.879 s（main 校准 6 turn、19 HTTP、91,224 tokens、37.129 s，加 no-skills 复验
1 turn、1 HTTP、2,434 tokens、1.75 s）。其中 7/6 记为**硬上限违规，不改称 soft**。首轮 raw 文件
（`CALIBRATION_SUMMARY.json`、`CALIBRATION_RAW.json` 等）保持原样，未修改。pi 开发用量不计入。

## 8. 限制

- 每类 n=1，仅信号；不做统计非劣检验，不推广到大工程、模糊需求或长会话。
- 每 turn `max_model_calls=6`（校准冻结沿用）导致部分 turn `budget_exhausted`；B 的 t3 因此
  低于 C。这是受控但会影响结论的 agent-loop 现象，已如实计入。
- `temperature` 未由 harness 发送（两组一致，如实记录，未私自优化）。
- 本实验不是独立版本 QA、不是 UI 完整产品端到端；只比较“独立编排模型”这一单变量。

## 9. 结论

在有效、无损、可审计的前提下：两组都能真实运行 SDK 工具循环并完成文件写入与验收；权限前置
阻断有效。实际度量方向是**移除独立 planner（C 相对 B）**的收益：在本次 n=1 信号下中位 relay
tokens 改善 8.84%、中位耗时改善 3.16%，均 < 15%，**未达门**——这不是“独立 planner 没有收益”的
反向表述，而是“移除它只带来不足 15% 的收益”。t3 的代码验收 B(5/9) 低于 C(9/9)，源于 B 该轮有
turn 触及每 turn `max_model_calls=6` 而 `budget_exhausted`。

按 run 级代码验收，B 为 **2/3**、C 为 **3/3**（`all_passed_samples`）。这只是**代码验收**结果，
且是在**部分 turn 预算耗尽**（正式 51 turn 中 44 succeeded、7 个 `budget_exhausted`/`failed`）的前提下
得到的，**并非所有 SDK turn 都成功**。故本报告**不**把“生产可删除独立编排”作为结论；同时也不主张
编排必然更优（样本极小）。结论仍为**“无编排可运行，收益未达门，不支持仅凭成本删除独立编排”**。

## 10. 证据索引

- `evidence/AUDIT.source.md`：首轮只读审计（失败证据，来源哈希见 `SOURCE_COPY.sha256`）。
- `evidence/phaseA/`：0 模型离线返修；`offline_replay.json`（6110/1196/7690 字符恢复 + 新 schema 拒绝）、`selftest_offline.stdout.txt`（全过）、`COMMANDS.txt`。
- `evidence/phaseB/`：校准 raw stdout、`CALIBRATION_RECHECK.json`（19 项全过）。
- `evidence/phaseD/analysis.json`：逐 run/类全部指标（无 runner 重算）；`formal.stdout.txt`。
- `runs/formal/*/turns/*.json`：每 turn 无损 `finish_payload`、`captured_calls`、`stop_evidence`、`hook_decisions`、`relay_calls`。
- `runs/formal/*/sessions/*.db`：SDK 原生 session DB（原始证据）。
- `evidence/FREEZE_MANIFEST.txt`：正式前冻结（epoch `1792048031`）。
- `evidence/EVIDENCE.sha256`：逐文件哈希清单（文档更正后重算）；初次清单保留为 `evidence/EVIDENCE.initial.sha256`。
- `evidence/phaseE/DOC_CORRECTION.md` / `.json`：本次文档更正记录（改前 REPORT 副本、前后哈希、三处更正与不改 raw/schema/阈值声明）。
- `evidence/phaseE/USAGE_RECONCILIATION.json`：relay reported usage 与 driver 快照的纯离线算术核对。
- `COPY_VERIFICATION.final.json`：文档更正后最终树哈希证明（初次 `COPY_VERIFICATION.json` 只覆盖更正前树）。
