---
title: "r1-review-lifecycle.json 版本说明（原始 vs QA 刷新）"
doc_type: note
category: engineering
updated: "2026-10-16"
---

# `r1-review-lifecycle.json` 版本说明

R1 返修 owner 的确定性探针输出 `probes/lg022/evidence/r1-review-lifecycle.json` 在 R1 独立 QA 处
被**本地重跑刷新**（仅计时数值变化，机制结论不变）。R2 返修按 PM 指令保全两个版本，不丢原始记录：

| 版本 | 路径 | SHA-256 | 说明 |
|---|---|---|---|
| **R1 原提交 `d07a4a6` 原始字节（权威）** | `probes/lg022/evidence/r1-review-lifecycle.json` | `9853bca4dc67b6b2134ab287f0bdfdedb078e68b2810eb1a4cdde066bcedcc1d` | R1 owner 产出的原始证据，R2 已恢复为原字节 |
| **QA 刷新版（保留，非权威）** | `probes/lg022/reverify-r1/evidence/r1-review-lifecycle-refreshed.json` | `feb2d1e49be0c056a4c966c5fbf189f9486d538b26204c25a19400386eae7eaa` | QA owner 本地重跑版本，仅 `d1_running_loop.elapsed` 0.0022→0.0023、`d2_served_during_review.loop_served_latency` 0.5302→0.5286 |

两个版本均有可核路径与 sha；QA `reverify-r1/REPORT.md` §9 的“原样保留并注明”已由本说明落实为
可复核的两文件并存，无需改写历史报告。
