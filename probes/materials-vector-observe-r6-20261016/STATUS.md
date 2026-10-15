---
title: "LG-037 R6 证据可观测性 STATUS"
doc_type: status
category: engineering
updated: "2026-10-16"
---

# STATUS — materials-vector-observe-r6-20261016

## 阶段

- **phase = OBSERVATION**（证据可观测性），**非**质量调优、**非**重写 R5 gate。
- PLAN 已于**任何 POST 之前**冻结为独立 commit `e1680da`（基点 `main@7c27f18`，已验证 clean）。
- 离线有意义检查（无网络）**已通过**：`evidence/offline_checks.json` `all_pass=true`。

## 离线检查结论（FIRST，无网络）

1. **nullable/misnamed score（proven）**：产品 `VerifiedHit.to_dict()` 字段为
   `basis, content_hash, locators, reason, scope, snippet, source_id, source_version,
   stale, title, verified` —— **不含 `score` 也不含 `similarity`**；
   产品 `VectorIndex.search()` 候选 dict **含 `score`**。→ harness **双通道**记录。
2. **dimensions/finite（proven）**：复用 R5 文档向量 **10 条 / 768 维 / 全 finite / 全非零**；
   header `model=embeddinggemma-2-Q8_0, dim=768, cache_version=1` 一致。
3. **hard call limit（proven）**：记录型 guard 在第 3 次调用前抛错，替身后端仅发 2 次。
4. **actual query vector persisted（proven）**：替身后端下 query 向量（768）/sha256/`prompt_tokens` 落盘。

## 真实运行结果（2 POST，恰好一次，无重试）

- **health GET（1/1）**：HTTP **200**，`{"status":"ok"}`，latency 0.004s。
- **POST 1 `Q_IMG_ZH`**：**blocked** —— `index_unavailable`，latency **30.04s**（撞 30s 读超时）。
- **POST 2 `Q_NEG_ZH`**：**blocked** —— `index_unavailable`，latency **30.03s**（撞 30s 读超时）。
- 计数：`post_used=2/2`、`post_attempted=2`、`retries=0`、`health_get=1/1`、
  `media_inputs=0`、`audio_seconds=0`。**预算无剩余，不重试、不加调用**。
- 记录：`evidence/post_reservations.jsonl`（转发前预留 2 条）、`http/health.raw.json`、
  `evidence/observation.json`、`http/queries/*/observation.raw.json`。
- **端点判定**：健康可达，但 `/v1/embeddings` 在 30s 内无响应（两次一致）。
  **记录为 block**；**不**把端点可达当检索质量通过；**不推断**这是产品缺陷。

## 可观测性管线演示（离线，弱路径，明确披露）

真实 query embed 不可用（超时），故以**明确披露的弱路径**验证**可观测性机制**：
`evidence/pipeline_demo.py` 在**真实产品代码路径**（真实 `SourceStore` + 真实
`VectorSearchService.search` + 真实 `authorize_and_verify` + 真实 `VectorIndex.search`
产品余弦，复用 R5 文档向量）上，用**确定性替身 query 向量**（**非**真实 embedding）跑通：

- query 向量/sha256/dim(768) 落盘；完整 **10** 条 ranking 分数；产品原生命中
  （字段集确认**无** `score`/`similarity`）；**独立重算与产品顺序完全一致**（`order_match=true`）。
- `Q_NEG_ZH` 负向返回 top-5 **纯 NN**（预期，**非 ACL 失败**）。
- **不**把该替身排序读作质量结论；`pipeline_demo.json` 明标 `weaker_path=true`、
  `real_query_embed=false`、`not_a_quality_observation=true`。

## 复用 R5 证据（只读）

- 只读复制 `vectors.jsonl` → 本包 `private/r5-vectors/`，**sha256 `8e8e6afc…` 与源一致**。
- 10 条文档向量按 `fragment_hash`/cached text 映射到 R5 标签，**未重新嵌入文档**。
- 媒体原件复用 R5 fixtures 只读，**无下载、无合成、无再嵌入**。

## 边界声明

- **保持旧 R5 质量 FAIL 结论不变**；**不因观测分数声称质量通过**；**不解锁 LG-040/LG-041**。
- 新实时 query 向量**无法**重建 R5 历史未知 query 向量，**不做回顾性精确 margin 复算**。
