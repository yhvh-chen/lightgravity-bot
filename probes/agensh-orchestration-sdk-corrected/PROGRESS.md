---
title: "agensh SDK 纠正版 — 进度"
doc_type: progress
experiment_id: agensh-sdk-corrected-20261015
status: complete
updated_at_utc: "2026-10-15T07:15:00Z"
---

# 进度（全部时间来自真实 UTC 时钟）

| 阶段 | UTC 时刻 | 说明 |
|---|---|---|
| 分支/worktree 创建 | 2026-10-15T06:58:02Z | `experiment/agensh-sdk-corrected-20261015` @ `9987d4f`；新目录 `probes/agensh-orchestration-sdk-corrected/`（此前不存在） |
| Phase A 离线返修 | 2026-10-15T06:58Z–07:04Z | 0 模型；`selftest_offline` 全过；`audit_offline` 从源 session DB 恢复 6110/1196/7690 字符 |
| Phase B 校准 | 2026-10-15T07:05Z–07:06Z | 2 turn / 6 HTTP / 26,628 tokens / 12.17 s；离线复核全过 |
| 协议冻结 | 2026-10-15T07:07:11Z | epoch `1792048031`；manifest `evidence/FREEZE_MANIFEST.txt` |
| Phase D 正式 | 2026-10-15T07:07:30Z–07:13:42Z | 6 run；154 HTTP / 845,223 relay tokens / 372 s |
| 分析/报告 | 2026-10-15T07:14Z–07:15Z | 离线重算，无新增模型样本 |

## 预算使用

| 阶段 | 逻辑 turn | 真实 HTTP | reported tokens | 墙钟 |
|---|---|---|---|---|
| 校准 | 2 | 6 | 26,628 | 12.17 s |
| 正式 | 51（48 worker + 3 planner） | 154 | 845,223 | 372 s |
| 合计 | 53 | 160 | 871,851 | ~384 s |

正式硬界：51 turn / 220 HTTP / 1,300,000 tokens / 900 s；合计硬界：232 HTTP / 1,360,000 tokens。
均在界内。pi 开发用量不计入上表。

## 状态

- 有效性前置：全部满足（3/3 B plan 有效且注入；无损 structured 输出；0 `length` 截断；
  每 turn 停止正向；标准 YAML 合法；真实参数单一输出上限）。
- 正式完成后未新增任何模型样本。
- 首轮（`agensh-sdk-20261015`）与纠正版费用在 `REPORT.md` 中分开列示；未知不猜。
