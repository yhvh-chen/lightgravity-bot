---
title: "LG-037 R6 证据可观测性 REPORT"
doc_type: report
category: engineering
updated: "2026-10-16"
---

# REPORT — materials-vector-observe-r6-20261016

## 0. 摘要

本包实现并运行了 **LG-037 证据可观测性 harness**，直接针对 R6 诊断
[REPORT](../materials-vector-diagnosis-r6-20261016/probes/materials-vector-diagnosis-r6-20261016/REPORT.md)
§4/§6 证明的缺口：R4/R5 harness 未保留 query 向量/原始 embeddings 响应
（含 `prompt_tokens`），且落盘 `vector_hits` 的 **score 为 `null`**，导致 query→doc
原始余弦**不可复算**。

- 阶段 **OBSERVATION**（可观测性），**非**质量调优、**非**重写 R5 gate。
- PLAN 在**任何 POST 之前**冻结为独立 commit。
- 离线有意义检查（无网络）**全部通过**：nullable/misnamed score、维度/finite、
  硬调用上限、query 向量落盘。
- **真实 2 POST 恰好执行一次**（无重试）：两条均因 `/v1/embeddings` 在 **30s** 内无响应
  而 **block**（`index_unavailable`）；health GET **200**。预算用尽，不重试。
- 在**真实产品代码路径**上以**明确披露的弱路径**验证可观测性管线：
  完整 10 条分数、产品原生命中、独立重算顺序一致。
- **保持旧 R5 FAIL 不变**；**不据观测分数声称质量通过**；**不解锁 LG-040/LG-041**。

## 1. 交付物与原始证据路径

| 路径 | 内容 | sha256 |
|---|---|---|
| `probes/materials-vector-observe-r6-20261016/PLAN.md` | 冻结计划（POST 前） | — |
| `.../STATUS.md` | 状态 | — |
| `.../REPORT.md` | 本报告 | — |
| `.../evidence/offline_checks.py` / `.json` | 离线有意义检查 | `ca2e047b…` |
| `.../evidence/observe_harness.py` | 真实产品路径 + 记录型 wrapper | — |
| `.../evidence/observation.json` | 真实运行观测（2 POST block） | `25a3fc16…` |
| `.../evidence/post_reservations.jsonl` | 转发**前**预留账本（2 条） | `536c244e…` |
| `.../evidence/pipeline_demo.py` / `pipeline_demo.json` | 弱路径可观测性机制演示 | `46dc9fde…` |
| `.../http/health.raw.json` | 唯一健康 GET 原始响应 | `94598efb…` |
| `.../http/queries/Q_IMG_ZH/observation.raw.json` | 单查询原始观测 | — |
| `.../http/queries/Q_NEG_ZH/observation.raw.json` | 单查询原始观测 | — |
| `private/r5-vectors/vectors.jsonl`（未提交，私有） | 复用的 R5 文档向量 | `8e8e6afc…`（与源字节一致） |

## 2. 离线有意义检查（FIRST，无网络）

`evidence/offline_checks.json` `all_pass=true`：

1. **nullable/misnamed score（proven）**：产品 `VerifiedHit.to_dict()` 字段
   `basis, content_hash, locators, reason, scope, snippet, source_id, source_version,
   stale, title, verified` —— **无 `score`、无 `similarity`**。
   `VectorIndex.search()` 候选 dict **含 `score`**。→ harness **双通道**记录。
   （这是 R5 `score=null` 的直接原因：产品命中层**根本不携带** score。）
2. **dimensions/finite（proven）**：复用 R5 文档向量 10 条 / 768 维 / finite / 非零；
   header `model=embeddinggemma-2-Q8_0, dim=768, cache_version=1` 一致。
3. **hard call limit（proven）**：guard 在第 3 次调用前抛错，替身后端仅发 2 次。
4. **actual query vector persisted（proven）**：替身后端下 query 向量/sha256/`prompt_tokens` 落盘。

## 3. 真实运行（2 POST，恰好一次）

| 项 | 值 |
|---|---|
| health GET | 1/1，HTTP **200**，`{"status":"ok"}`，0.004s |
| POST `Q_IMG_ZH`（`老子 道德經 註解 學說`） | **block**：`index_unavailable`，30.04s |
| POST `Q_NEG_ZH`（`量子色動力學 膠子 強相互作用`） | **block**：`index_unavailable`，30.03s |
| counters | `post_used=2/2`、`post_attempted=2`、`retries=0`、`media_inputs=0`、`audio_seconds=0` |

- **预留先于转发**：`post_reservations.jsonl` 两条在 HTTP 之前 append+fsync。
- **硬上限在 HTTP 之前强制**；无第 3 次调用；无重试；串行。
- **判定为 block**：端点健康可达，但 `/v1/embeddings` 30s 内无响应（两次一致）。
  **不**推断产品缺陷；**不**把端点可达当检索质量通过。
- **harness 诚实缺陷（记录）**：首次真实运行中，记录型 wrapper 仅在成功时 append 记录，
  导致超时异常的精确类型未落盘；已修复（成功/失败均记录），但因**无剩余预算**、
  且**不重放未知副作用**，**未重跑**。latency=30.0s 是 `EmbeddingTimeout` 的强证据但**不被声称为已确证类型**。

## 4. 可观测性管线演示（离线弱路径，明确披露）

真实 query embed 不可用，故 `evidence/pipeline_demo.py` 在**真实产品代码路径**上
（真实 `SourceStore` + 真实 `VectorSearchService.search` + 真实 `authorize_and_verify`
+ 真实 `VectorIndex.search` 产品余弦，**复用 R5 文档向量**，媒体原件只读复用 R5 fixtures）
以**确定性替身 query 向量**（**非**真实 embedding）验证机制：

- **query 向量/sha256/dim(768)** 落盘；**完整 10 条 ranking 分数**；
- **产品原生命中**字段集确认**无 `score`/`similarity`**；
- **独立重算与产品顺序完全一致**（`order_match=true`，两条查询）；
- `Q_NEG_ZH` 负向返回 top-5 **纯 NN**（预期，**非 ACL 失败**）；
- `pipeline_demo.json` 明标 `weaker_path=true`、`real_query_embed=false`、
  `not_a_quality_observation=true`、`docembedding=0`。

**该演示证明**：可观测性 harness 已能持久化 query 向量、完整分数、产品原生命中、
`prompt_tokens` 并独立重算——正是 R5 缺失的能力。**不**读作这些查询的检索质量。

### 4.1 演示观察到的（非质量结论）

- `Q_IMG_ZH`：目标 `M_IMG_ZH` 在替身向量下 **rank 7/10**，score 0.01737，top-1 为 `D3`(0.05812)。
- `Q_NEG_ZH`：top-5 = `M_AUD_ZH, M_AUD_DIQIU, D3, D6, D2`（NN，无弃答）。
- 这些来自**非真实**替身向量，**不得**用于任何质量/阈值判断。

## 5. 复用 R5 证据（只读，未再嵌入）

- `vectors.jsonl` 只读复制，sha256 与源**字节一致**（`8e8e6afc…`）。
- 10 条文档向量按 `fragment_hash`/cached text 映射到 R5 标签：
  `D1,D2,D3,D5,D6,T_NORTHWIND,M_IMG_ZH,M_IMG_EN,M_AUD_ZH,M_AUD_DIQIU`。
- **未调用任何文档嵌入**（`docembedding=0`）；无下载、无合成、无媒体输入。

## 6. 明确 UNKNOWN / 不证明

- 两条真实 query 的 **query 向量、原始响应、`prompt_tokens`**：**未取得**（超时 block）。
- **真实产品排序**：**未取得**（真实 embed 不可用）。
- R5 历史 query 向量**不可重建** → **不做回顾性精确 margin 复算**。
- **不存在**被证明的产品代码缺陷；block 归因于端点 embeddings 响应超时。
- **不**声明确认了 embeddings 路径的真实失败模式（超时 vs 冷加载 vs 其他）。

## 7. 边界与状态

- **保持旧 R5 质量 FAIL 结论不变**；**不因观测分数声称质量通过**；
  **不解锁 LG-040/LG-041**；本包**待版本 QA**。
- 无产品/backlog/docs/tests 代码改动；仅 `probes/materials-vector-observe-r6-20261016/**`。
- 未 push/deploy/publish/reset/clean；无后台任务。
- 成本：LAN unknown；pi/DeepSeek unknown 非 0。

## 8. 最小后续建议（仅在已证明范围）

- 若授权端点 embeddings 可稳定响应 ≤30s，可**新开**一轮（**非本轮**）真实观测，
  复用本 harness：它将落盘 query 向量、完整分数、`prompt_tokens`，从而**首次**让
  R5 式排名可复算。
- **不**在本轮或同批冻结查询上调阈值、不重跑、不重放。
