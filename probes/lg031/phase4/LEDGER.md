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
| 本 phase4 批准新增上限 | **16**（实际用 **10**，剩 6） |
| 全局已知工程累计上限 | **40**（实际累计 **34**） |
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

一次真实产品闭环 attempt（run `run_01M5079F4W8V37RHRTN7W6WWV6`，task
`task_01M5079F4WRHPVMVHGM1NS7FK9`），共 **10** 次真实转发（pid 1968580）。

| # | 时间(UTC) | 角色/stage | 模型 | 结果 | usage | 备注 |
|---|---|---|---|---|---|---|
| 1–6 | 2026-10-16T~03:46Z | deliver worker（自主 discover/claim/create_file 等工具轮） | deepseek-v4-flash | ok | `unknown` | 6 条 `adapter.tool_call`；`discover_and_request_claim` 被真实调用 |
| 7–9 | 同上 | verify worker（自主 discover/claim + 只读检查轮） | deepseek-v4-flash | ok | `unknown` | 依赖满足后调度；claim 经产品 router |
| 10 | 同上 | 独立 reviewer | deepseek-v4-flash | **passed**（机器门 `validated_outcome=passed`） | `{"unknown":["usage"]}` | `reviewer_kind=model`，`model_calls=1` |

- 机器账本最终：`count=10, limit=16, remaining=6, corrupt=false, persistent=true`；
  `generation.jsonl` 共 10 条 `reserved`。
- 全部 worker/reviewer usage 记 `unknown`（不当 0）。
- dispatcher `succeeded`；候选完整（reviewer 证据含 `out/deliver.txt` + diff patch
  `@sha256:820a554a…`）。
- **未捕获**：真实 `handoff_refs`（探针提取 bug，见 REPORT §4）；**未重跑**（16 上限内已用 10，
  一次完整 attempt ≈10 超出剩余 6）。

## 未知项

- 本 phase4 worker usage（SDK 未把 token 明细作为事件暴露）与 reviewer usage 均记 `unknown`，
  **不当 0**。
- 真实 handoff 字符串**已由同次运行证据恢复复原**（探针提取 bug 已确诊；产品侧交接真实发生）：
  从存活 SDK session DB 只读提取到 verify 节点产品 prompt 的 `Upstream artifacts:` 块，含
  `subtask_…@1a6053…:out/deliver.txt` 与 `@sha256:820a554a…`（离线重算 match=true）。
  见 `SALVAGE-REPORT.md`、`evidence/salvaged_handoff_evidence.json`；**新增真实调用 0**。
