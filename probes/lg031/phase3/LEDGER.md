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
| 1 | 2026-10-16T~03:27Z | produce worker (turn 1) | deepseek-v4-flash | 429/预算 | `unknown`（SDK worker usage 未暴露） | Run1：produce worker 第 1 轮 |
| 2 | 同上 | produce worker (turn 2) | deepseek-v4-flash | ok | `unknown` | Run1：自主调用 claim 工具 |
| 3 | 同上 | produce worker (turn 3) | deepseek-v4-flash | ok | `unknown` | Run1：`max_model_calls=3` 用尽前最后一轮 |
| 4 | 同上 | reviewer | deepseek-v4-flash | `unavailable`（无候选证据） | `{"unknown":["usage"]}`（不当 0） | Run1 reviewer 单轮 |
| 5 | 2026-10-16T~03:29Z | produce worker | deepseek-v4-flash | ok（自主 discover+claim） | `unknown` | Run2：`discover_and_request_claim()` |
| 6 | 同上 | produce worker | deepseek-v4-flash | ok（claim granted） | `unknown` | Run2：`discover_and_request_claim(node_ref=...)` |
| 7 | 同上 | produce worker | deepseek-v4-flash | ok | `unknown` | Run2：写文件轮 |
| 8 | 同上 | produce worker | deepseek-v4-flash | 429（per-worker proxy cap=4 用尽） | `unknown` | Run2：produce worker 第 4 次后 429 |
| 9 | 同上 | reviewer | deepseek-v4-flash | `unavailable`（无候选证据） | `{"unknown":["usage"]}` | Run2 reviewer 单轮 |
| 10 | 2026-10-16T~03:30Z | produce worker | deepseek-v4-flash | ok（自主 discover/claim） | `unknown` | Run3：cap 提升至 6，worker 多次工具调用 |
| 11 | 同上 | produce worker | deepseek-v4-flash | ok | `unknown` | Run3 |
| 12 | 同上 | produce worker | deepseek-v4-flash | ok | `unknown` | Run3 |
| 13 | 同上 | produce worker | deepseek-v4-flash | ok | `unknown` | Run3 |
| 14 | 同上 | produce worker + reviewer（嵌套 429） | deepseek-v4-flash | `unavailable`（429） | `{"unknown":["usage"]}` | Run3 最后一次预留；全局 14/14 用尽 |

- **机器账本最终 `count=14, limit=14, remaining=0, corrupt=false, persistent=true`。**
- 三次运行分别消耗 4 / 5 / 5 = **14**；`generation.jsonl` 共 14 条 `reserved` 条目（pid 1934241:4、1936962:5、1940208:5）。
- 所有 reviewer `usage` **unknown**（不当 0）；worker usage 由 SDK 事件未暴露为 token 明细，记 **unknown**。
- 证据：`probes/lg031/phase3/evidence/run{1,2,3}_*` + `probes/lg031/phase3/ledger/generation/generation.jsonl`。

### 真实硬条件达成情况（本 phase3）

| # | 条件 | 结果 |
|---|---|---|
| 1 | ≥2 真实 SDK worker，各自独立 worktree | ⚠️ 仅 produce worker 真跑；integrate 未达（预算耗尽） |
| 2 | worker 自主 discovery→申请原子授权 claim | ✅ Run2/Run3 真实 worker **自主**调用 `discover_and_request_claim()`→`discover_and_request_claim(node_ref)`；经**产品** `GraphDispatcher._claim_for_worker` 路由 |
| 3 | 程序验证并原子授权 + lease/fencing | ✅ 程序 granted/fence=1、receipt 脱敏（离线产品路径测试证实）；真链中 claim 工具调用事件已捕获 |
| 4 | 受控带 hash 同伴交接 | ❌ 未达（integrate worker 未跑完，无交接） |
| 5 | 完整候选独立 ModelReviewer + 机器门 passed | ❌ 未达（候选不完整；reviewer 真实跑但诚实 `unavailable`） |
| 6 | 默认关闭/回退、身份程序注入、worker 无全局 token | ✅ |

**结论：partial。** 真实请求硬上限 14/14 用尽；硬条件 2/3/6 真实成立，1 部分、4/5 未闭合。

## 未知项

- 旧 reviewer usage、phase3 worker/reviewer usage 一律记 `unknown`，**不当 0**。
- 部分 SDK 路径的 usage 若不可得，明确 `unknown` 而非估算。
