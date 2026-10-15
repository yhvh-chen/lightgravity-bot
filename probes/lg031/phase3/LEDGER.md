---
title: "LG-031 phase3 — LEDGER（真实生成转发持久账本，唯一权威）"
doc_type: ledger
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg031-r3"
---

# LG-031 phase3 — LEDGER

本文件是本 phase3 **真实 DeepSeek 生成转发**的唯一权威记录。持久机器账本位于
`probes/lg031/phase3/ledger/generation/`（契约 1.10 `PersistentGenerationLedger`，
转发前持久预留、跨进程/重启、损坏不当 0）。两者冲突时以**机器账本**为准并立即更正本文件。

## 预算基线与硬限

| 项 | 值 |
|---|---|
| 旧累计（前两阶段，不归零） | **10**（原包 1 reviewer + R1 3 + R2 6） |
| 本 phase3 批准新增上限 | **14** |
| 全局已知上限 | **≤24** |
| SDK/API retry | 0 |
| 单请求输出上限 | ≤12000 tokens |
| 单 HTTP 超时 | ≤120s |
| 并发 | ≤2 |

## 旧成本（保留，不重放）

- 原包：1 真实 reviewer 调用；usage `unknown`（`{"unknown":["usage"]}`，不当 0）。
  `probes/lg031/review_real_probe.py` → `review_real_probe.json`。
- R1：2 真实 worker（各自 autonomous discovery→claim 领取不同节点后撞 proxy 429）+ 1 真实 reviewer。
  usage：worker A `total_tokens=6880`、worker B `6923`、reviewer `unknown`。
  `probes/lg031/r1_worker_claim_probe.json`。
- R2：单次运行共享计数 `count=6/limit=6`（worker A 4 + worker B 发现 1 + reviewer 1）。
  usage：worker A `total_tokens=20587`、worker B `3361`、reviewer `unknown`。
  `probes/lg031/r2_worker_claim_probe.json`。

## 本 phase3 实际转发记录

| # | 时间(UTC) | 角色/stage | 模型 | 结果 | usage | 备注 |
|---|---|---|---|---|---|---|
| — | — | — | — | 尚未开始 | — | 真实转发前此处保持空 |

（每次真实转发后由本包 owner 更新；机器账本 `count` 必须与上表行数一致。）

## 未知项

- 旧 reviewer usage、phase3 reviewer usage（若未知）一律记 `unknown`，**不当 0**。
- 部分 SDK 路径的 usage 若不可得，明确 `unknown` 而非估算。
