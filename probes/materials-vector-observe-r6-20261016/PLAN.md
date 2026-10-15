---
title: "LG-037 R6 证据可观测性 harness PLAN（冻结于任何 POST 之前）"
doc_type: plan
category: engineering
updated: "2026-10-16"
---

# PLAN — materials-vector-observe-r6-20261016

## 0. 目的与边界（先读）

R6 诊断 [REPORT](../materials-vector-diagnosis-r6-20261016/probes/materials-vector-diagnosis-r6-20261016/REPORT.md) §4/§6 证明：
R4/R5 harness 未保留 query 向量与原始 embeddings 响应（含 `prompt_tokens`），
且落盘 `crossmodal_results.json` 的 `vector_hits` **score 字段为 `null`**，导致 query→doc
原始余弦**不可复算**。诊断 §6 给出的**唯一最小前置动作**是实现**证据可观测性**。

本包**只做证据可观测性**：实现一个有界、可复用的 harness，记录**真实产品**
请求/响应（无 auth）、query 字节/哈希/向量、文档向量哈希/model/dim/片段指纹、
**完整排序分数**、产品原生命中、usage/`prompt_tokens`。

### 0.1 明确不做（NOT scope）

- **不是**质量调优；**不重写 R5 gate**；**不在同一批冻结查询上校准阈值**。
- **不重跑 R5 语料 embedding**（`docembedding0`）；**不重新嵌入任何文档**。
- **不伪造**端到端；不改动旧 fixtures/缓存；不改产品/测试/backlog/docs 代码。
- 不下载模型、不换供应商、不做媒体 boost、不做 OCR/ASR/音频/图片输入。
- 不 push / deploy / publish / reset / clean；无后台任务。

### 0.2 增量价值与诚实披露

- R5 的**文档向量**保留在其 worktree 私有缓存（`private/vector-data/sources-index/vectors/vectors.jsonl`，
  header `cache_version=1, dim=768, model=embeddinggemma-2-Q8_0`）。本包**只读复制**该文件到
  **本包私有 scratch**，核对 header/逐条 `fragment_hash` 后复用这些向量，**不重新嵌入文档**。
- **新实时 query 向量无法重建 R5 历史未知 query 向量**：R5 未落盘其 query 向量，故本包**不声称**
  对 R5 排名翻转做**回顾性精确 margin 复算**。本包只报告**新观测**：用**同一冻结查询文本**、
  用**真实 query embed + 真实产品余弦索引 + R5 复用文档向量**计算的新分数与排名。
- **保持旧 R5 结论 FAIL 不变**；**不因观测到分数而声称质量通过**；**不解锁 LG-040/LG-041**。

## 1. owner / 隔离

- owner 目录：`probes/materials-vector-observe-r6-20261016/**`（本文件所在目录）。
- worktree：`/home/yhvh/code/lightgravity-bot-worktrees/materials-vector-observe-r6-20261016`
  branch `test/materials-vector-observe-r6-20261016`，基点 `main@7c27f18`（已验证 clean）。
- **无产品/backlog/docs/tests 编辑**；并行 OCR owner 隔离；inference0（无第二个推理后端）。

## 2. 真实产品路径（记录对象）

harness 在**未修改的产品路径**上运行：

```
记录型 EmbeddingBackend（包装真实 OpenAICompatEmbeddingBackend）
  → 真实 HTTP POST /v1/embeddings（唯一真实后端）
  → VectorSearchService.search(VectorSearchRequest(...))（真实产品 search）
  → 真实 VectorIndex.search（产品余弦，加载 R5 复用文档向量）
```

- **recording wrapper** 只**记录**，不改变请求/响应字节；真实 HTTP 仍由产品 backend 发出。
- 真实 `VectorSearchService.search`：产品授权/回源核对路径（`authorize_and_verify`）。
- 端点：**仅** `http://192.168.8.12:11434`，模型**仅** `embeddinggemma-2-Q8_0`。
- 无 auth（该端点无 token；`Authorization` 仅在配置存在时发送，本包不配置 token）。

### 2.1 产品命中字段核对（窄检查）

- `VectorIndex.search()` 产出候选 dict 含 `score`（产品余弦）。
- `authorize_and_verify()` **重建** `VerifiedHit`，其中 `score=0.0`（硬编码），
  且 `VerifiedHit.to_dict()` **不含** `score` 字段 → 产品 API 命中外层**无 score**。
- 因此本包**分别**记录：
  1. **native product hits**（`VectorSearchService.search()` 返回的 `hits[]`，即产品原生字段），
  2. **pre-authorization ranked candidates**（`VectorIndex.search()` 的完整 `score` 与排序），
  3. **independent recompute**（用 query 向量 + 复用文档向量自行重算余弦并比较产品顺序）。
- **窄检查**：不修改产品代码；仅在 harness 内**读取**这两层并写入证据。

## 3. 冻结查询（2 条文本，text ≤ 1 KiB）

| id | 文本 | 类型 | 来源 |
|---|---|---|---|
| `Q_IMG_ZH` | `老子 道德經 註解 學說` | positive_crossmodal_image（目标 `M_IMG_ZH`） | R5 冻结 corpus 原文（逐字一致） |
| `Q_NEG_ZH` | `量子色動力學 膠子 強相互作用` | negative_control（relevant=[]） | R5 冻结 corpus 旧负向 |

- `Q_IMG_ZH` 文本**必须逐字**等于 `老子 道德經 註解 學說`。
- 负向为 R5 corpus 旧负向 `Q_NEG_ZH`；**期望 top-k 为纯 NN（非 ACL 失败）**。
- 二者均为**已有**冻结查询，**不新增/不调参**。
- top-k：**full 10 ranking**（全部复用文档向量数）用于分数/排序/margin；产品 `limit=5` 用于原生命中对照。

## 4. 观测字段（每次 query POST 落盘）

- **request**：method/endpoint/path（**不含** base host 以外敏感项；无 token）、`model`、
  `input` 结构摘要（text 输入为字面文本；媒体为空）、`encoding_format`、query **字节**（utf-8
  length）与 **sha256**、query 文本。
- **response**：HTTP status、`usage`（原样，含 `prompt_tokens`）、vector **dim**、
  finite/nonzero/L2 检查、vector **sha256**、**完整** query 向量（768 维）。
- **documents**：每个复用文档条目的 `source_id`、`kind`、`basis`、`model`、`dim`、
  `fragment_hash`、`cache_version`、`source_version`、`content_hash`、向量 sha256（不落整向量；
  文档向量已在 R5 缓存，仅记录其哈希以证复用）。
- **ranking（full 10）**：按 `score` 降序的 `(source_id, doc_label, kind, fragment_hash, score)`；
  目标 `M_IMG_ZH` 的 **rank** 与到相邻项的 **margin**（top-1 边距、目标与前一/后一名边距）。
- **native product hits**：`VectorSearchService.search()` 的 `hits[]`（`source_id/title/kind/
  basis/verified/snippet/...`）与 `stale`/`skipped`/`index_status`/`vector_model`/`dim`。
- **reservation**：转发**前**向 `evidence/post_reservations.jsonl` 追加预留（append+fsync）；
  **硬上限在 HTTP 之前强制**。

## 5. 预算与计数（硬约束）

- 授权 **2 POST TOTAL**（两条 query，各 1 次，**无文档嵌入**）。
- **可选** ≤1 次 **health GET**，8s 超时（不计入 POST）。
- `retry=0`；`concurrency=1`（严格串行）；`timeout=30s` / `connect=3s`；text ≤ 1 KiB/query。
- `audio=0 image=0 docembedding=0 OCR=0 ASR=0 worker=0`。
- 若缓存/端点不可用：**记录 block**，**不重试、不加调用**。
- 无新测试套件（证据-only）；不跑 full suite。

## 6. 离线有意义检查（FIRST，无网络）

在任何 POST 之前，对 harness 运行**离线自检**（`evidence/offline_checks.py`，无网络）：

1. **nullable/misnamed score**：断言产品 `VerifiedHit.to_dict()` **不含** `score`
   （记录实际字段集），且 `VectorIndex.search()` 候选**含** `score`；证明 harness 双通道记录必要。
2. **dimensions/finite**：复用文档向量全部 768 维、finite、非零；header `model/dim/cache_version` 一致。
3. **hard call limit**：注入计数后端，断言超过 `POST_CAP=2` 时 `reserve()` 抛错，且第 3 次
   **不发出** HTTP。
4. **actual query vector persisted**：用**替身** embedding 后端（确定性、无网络）跑通 query 路径，
   断言 query 向量/哈希/`prompt_tokens` 被写入证据结构（证明可观测性管线）。

自检**不**发网络调用；只有自检通过后才执行真实 POST。

## 7. 真实执行顺序（一次性）

1. 只读复制 R5 `vectors.jsonl` 到本包 `private/r5-vectors/`；核对 header 与逐条 `fragment_hash`。
2. 构建记录型 backend（包装真实 backend，`max calls=2`，`connect=3s`，`timeout=30s`）。
3. 构建真实 `VectorSearchService`，加载复用文档向量（**不**调用 `index_source`/`rebuild`）。
4. （可选）1× health GET。
5. 对 `Q_IMG_ZH`、`Q_NEG_ZH` 各执行 **1 次**真实 query（串行，转发前预留）。
6. full-10 排序、目标 rank/margins、native hits、usage；**独立重算**并与产品顺序比较。
7. 写 `evidence/observation.json`、`http/` 原始响应、`evidence/post_reservations.jsonl`、`STATUS.md`、`REPORT.md`。

## 8. 判定与不判定

- **判定记录**：query 向量是否落盘、分数是否完整、产品原生字段、独立重算是否与产品顺序一致。
- **不判定**：检索质量是否通过；不据观测分数关闭跨模态质量；不重算 R5 历史 margin。
- 负向 top-k **若** 为 NN（预期）→ 记为**预期行为**，**非 ACL 失败**。

## 9. 预算（执行侧）

- 壁钟 ≤360s、≤70 rounds、≤110000 noncache tokens；`retry=0`；无后台任务。
- 成本：LAN unknown；pi/DeepSeek unknown 非 0。

## 10. 状态与交付

- 本 PLAN 在**任何 POST 之前**作为**独立 commit** 冻结。
- 交付：本 PLAN、`STATUS.md`、`REPORT.md`、`evidence/**`、`http/**`（均在本 owner 目录）。
