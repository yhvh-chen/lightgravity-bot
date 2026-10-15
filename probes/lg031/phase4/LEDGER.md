---
title: "LG-031 phase4 — LEDGER（真实生成转发持久账本，唯一权威）"
doc_type: ledger
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg031-r3"
---

# LG-031 phase4 — LEDGER

本文件是 phase4 **真实 DeepSeek 生成转发**的唯一权威记录。持久机器账本位于
`probes/lg031/phase4/ledger/generation/`（契约 1.10 `PersistentGenerationLedger`，
转发前持久预留、跨进程/重启、损坏不当 0）。两者冲突时以**机器账本**为准并立即更正本文件。

## 预算基线与硬限

| 项 | 值 |
|---|---|
| 旧累计（前三阶段，不归零） | **24**（原包 1 + R1 3 + R2 6 + phase3 14） |
| 本 phase4 批准新增上限 | **16** |
| 全局已知工程累计上限 | **40** |
| SDK/API retry | 0 |
| 单请求输出上限 | ≤12000 tokens |
| 单 HTTP 超时 | ≤120s |
| 并发 | ≤2 |

## 旧成本（保留，不重放）

- 原包：1 真实 reviewer；usage `unknown`。`probes/lg031/review_real_probe.json`。
- R1：2 worker + 1 reviewer = 3；worker A `total_tokens=6880`、B `6923`、reviewer unknown。
  `probes/lg031/r1_worker_claim_probe.json`。
- R2：共享计数 `count=6/limit=6`（worker A 4 + worker B 发现 1 + reviewer 1）；
  worker A `20587`、B `3361`、reviewer unknown。`probes/lg031/r2_worker_claim_probe.json`。
- phase3：**14/14 用尽**（运行 1/2/3 = 4/5/5）；worker/reviewer usage 全部 unknown。
  机器账本 `count=14, limit=14, remaining=0, corrupt=false, persistent=true`。
  `probes/lg031/phase3/ledger/generation/`、`probes/lg031/phase3/evidence/`。

## 本 phase4 实际转发记录

| # | 时间(UTC) | 角色/stage | 模型 | 结果 | usage | 备注 |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | 尚无真实转发（离线阶段） |

- 机器账本初值：`count=0, limit=16, remaining=16`（待真实阶段首次预留前建立）。
- 所有 usage 未知记 `unknown`（不当 0）。

## 未知项

- 本 phase4 尚未产生真实转发，故无 usage 记录。
- 部分 SDK 路径的 usage 若不可得，明确 `unknown` 而非估算。
