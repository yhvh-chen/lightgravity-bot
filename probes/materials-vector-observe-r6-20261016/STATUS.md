---
title: "LG-037 R6 证据可观测性 STATUS"
doc_type: status
category: engineering
updated: "2026-10-16"
---

# STATUS — materials-vector-observe-r6-20261016

## 阶段

- **phase = OBSERVATION**（证据可观测性），**非**质量调优、**非**重写 R5 gate。
- PLAN 已于**任何 POST 之前**冻结为独立 commit `e1680da`（基点 `main@7c27f18`）。
- 离线有意义检查（无网络）**已通过**：`evidence/offline_checks.json` `all_pass=true`。

## 离线检查结论（FIRST，无网络）

1. **nullable/misnamed score（proven）**：产品 `VerifiedHit.to_dict()` 字段为
   `basis, content_hash, locators, reason, scope, snippet, source_id, source_version,
   stale, title, verified` —— **不含 `score` 也不含 `similarity`**。
   产品 `VectorIndex.search()` 候选 dict **含 `score`**。→ harness 必须**双通道**记录。
2. **dimensions/finite（proven）**：复用 R5 文档向量 **10 条 / 768 维 / 全 finite / 全非零**；
   header `model=embeddinggemma-2-Q8_0, dim=768, cache_version=1` 一致。
3. **hard call limit（proven）**：记录型 guard 在第 3 次调用前抛错，替身后端仅发出 **2** 次
   → 上限在 HTTP **之前**强制。
4. **actual query vector persisted（proven）**：替身后端（无网络）下 query 向量（768）、
   sha256、`prompt_tokens` 被写入证据结构。

## 网络/预算

- 真实 POST：**0/2**（尚未执行）；health GET：0/1；retry 0；concurrency 1。
- 端点 `http://192.168.8.12:11434`，模型 `embeddinggemma-2-Q8_0`（唯一）。
- 端点/缓存可用性：待真实执行时确认；不可用则记录 block、不重试。

## 复用 R5 证据（只读）

- 已只读复制 `materials-vector-r5-20261016/.../vectors.jsonl` → 本包 `private/r5-vectors/`，
  **sha256 `8e8e6afc…` 与源一致**（字节相同）。
- 10 条文档向量已按 `fragment_hash` / cached text 映射到 R5 标签
  （D1,D2,D3,D5,D6,T_NORTHWIND,M_IMG_ZH,M_IMG_EN,M_AUD_ZH,M_AUD_DIQIU），**未重新嵌入文档**。

## 尚未完成

- 真实 2 POST（`Q_IMG_ZH`、`Q_NEG_ZH`）、full-10 排序、目标 rank/margins、独立重算。
- `REPORT.md` 收尾。

## 边界声明

- **保持旧 R5 质量 FAIL 结论不变**；**不因观测分数声称质量通过**；**不解锁 LG-040/LG-041**。
- 新实时 query 向量**无法**重建 R5 历史未知 query 向量，**不做回顾性精确 margin 复算**。
