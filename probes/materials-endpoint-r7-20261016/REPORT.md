---
title: "LG-037 R7 端点协议/冷加载诊断 REPORT（诊断 + 真实观察）"
doc_type: report
category: engineering
updated: "2026-10-16"
---

# REPORT — materials-endpoint-r7-20261016

## 0. 摘要（因果事实优先）

**问题**：端点 `http://192.168.8.12:11434` `/health` 返回 **200**，但 R6
（`materials-vector-observe-r6-20261016`）的两次 embedding POST 均在 **~30 s** 超时
（`index_unavailable`）；而 R4/R5 的同类查询请求在**同一端点**上成功且延迟仅
**0.05–0.12 s**。

**诊断结论（有据）**：

1. **协议/路由/模型/task 编码/content-type/代理在 R4/R5/R6/R7 完全一致**（§2）。
   代理不是差异源（无 `*_proxy` 变量、无 ProxyHandler 代码、git 无 `http.proxy`）。
2. **R6 与 R4/R5 的唯一确定性差异是 text/cold timeout：30 s vs 90 s**。
   R6 的请求体形状与 R4/R5 **字节级一致**（同 `OpenAICompatEmbeddingBackend`）。
3. 本包 R7 用 **R4/R5 的 90 s 预算**运行**同一请求**：**两条均成功**，
   embed latency **0.0614 s / 0.0220 s**，768 维、L2≈1.0、`prompt_tokens=12`。
   ⇒ 端点 **R7 时点 warm 且快**；R6 的 30 s 超时**不是**“正常工况需要 >30 s”。
4. **原因**：R6 时点的端点**瞬时状态**（`--parallel 4` 槽位可能的排队 / 短时忙或首次冷加载偶发）
   导致 30 s 内无响应；到 R7 时已恢复。**置信度：中高**（协议一致 + 同一请求 90 s 内秒回；
   但 R6 时点无 raw 响应体、异常类型也未落盘，故不对 R6 具体瞬时状态作唯一断言）。
5. **health 200 不等于 embeddings 容量**：R6 的 health 200 与 embeddings 超时并存，
   本包也证明 health 与 embeddings 是不同就绪维度。

**本包同时取得首次完整、可复算的真实排名**（§4，new observation，非 R5 重算）：
`Q_IMG_ZH` 目标 `M_IMG_ZH` **rank 7/10**，`margin_to_prev=0.00037`（与 D6 几乎并列）。

## 1. 交付物与原始证据

| 路径（owner 目录内） | 内容 |
|---|---|
| `PLAN.md` | 冻结计划（commit `47f1a05`，**任何端点调用之前**） |
| `STATUS.md` | 状态 |
| `REPORT.md` | 本报告 |
| `evidence/offline_checks.py` / `.json` | 离线有意义检查（无网络，`all_pass=true`） |
| `evidence/r7_harness.py` | 记录型 harness（真实产品路径） |
| `evidence/protocol_comparison.json` | 协议逐维对比 R7 vs R4/R5/R6 |
| `evidence/observation.json` | 真实运行观测（2 POST 成功） |
| `evidence/post_reservations.jsonl` | 转发**前**预留账本（2 条） |
| `http/health.raw.json` | 只读 GET health 原始响应 |
| `http/v1_models.raw.json` | 只读 GET /v1/models 原始响应 |
| `http/queries/Q_IMG_ZH/embeddings.raw.json` | 真实 embeddings 原始响应（768 维 + usage） |
| `http/queries/Q_NEG_ZH/embeddings.raw.json` | 真实 embeddings 原始响应 |
| `http/queries/*/observation.raw.json` | 单查询原始观测 |
| `private/r5-vectors/vectors.jsonl`（未提交） | 只读复用 R5 文档向量 |

## 2. 协议对比（exact，来自既有证据 + 本包观测）

| 维度 | R4 | R5 | R6 | R7 | 是否相同 |
|---|---|---|---|---|---|
| URL | `http://192.168.8.12:11434` | 同 | 同 | 同 | ✅ |
| route | `POST /v1/embeddings` | 同 | 同 | 同 | ✅ |
| model | `embeddinggemma-2-Q8_0` | 同 | 同 | 同 | ✅ |
| body 形状 | `{model, encoding_format:"float", input:[<text>]}` | 同 | 同 | 同 | ✅（R7 重建字节相等） |
| content-type | `application/json` | 同 | 同 | 同 | ✅ |
| auth | 无 token | 无 | 无 | 无 | ✅ |
| task 编码 | 裸 query 文本，单元素，无 prefix/instruction | 同 | 同 | 同 | ✅ |
| http client | 产品 `OpenAICompatEmbeddingBackend`（urllib，无 ProxyHandler） | 同 | 同 | 同 | ✅ |
| 代理变量/代码 | 无 | 无 | 无 | 无 | ✅（非差异源） |
| **text/cold timeout** | **90 s** | **90 s** | **30 s** | **90 s** | ❌ **唯一差异** |

R7 记录的请求体（`observation.json` → `embedding_record.request.request_body`）：

```json
{"model": "embeddinggemma-2-Q8_0", "encoding_format": "float", "input": ["老子 道德經 註解 學說"]}
```

用同一产品类重建的 body 与之 **`EQUAL: True`**（字节 107），证明 R7 与 R4/R5 请求形态一致。

## 3. 真实运行（有界，一次）

| 项 | 值 |
|---|---|
| `GET /health` | **200** `{"status":"ok"}` 0.0038 s（GET 1/3） |
| `GET /v1/models` | **200**；`embeddinggemma-2-Q8_0` **loaded**（GET 2/3） |
| POST `Q_IMG_ZH` | **ok**，embed **0.0614 s**，768 维，L2≈1.0，`prompt_tokens=12` |
| POST `Q_NEG_ZH` | **ok**，embed **0.0220 s**，768 维，L2≈1.0，`prompt_tokens=12` |
| counters | `post_used=2/2`、`post_attempted=2`、`get_used=2/3`、`retries=0`、`media_inputs=0`、`audio_seconds=0` |

- 预留**先于**转发（`post_reservations.jsonl`）；硬上限在 HTTP 之前强制；串行；无重试。
- 端点模型 launch args（`/v1/models` 原始响应）：`--embeddings --pooling mean --sleep-idle-seconds -1
  --parallel 4 --ctx-size 8192 --mmproj /models/mmproj-embeddinggemma-2-Q8_0.gguf --n-gpu-layers 999`。
  `--sleep-idle-seconds -1` = **禁用空闲自动卸载** ⇒ R7 时点模型非因空闲卸载而冷。

## 4. 真实排名（new observation，完整 10 候选，可复算）

### 4.1 `Q_IMG_ZH`（目标 `M_IMG_ZH`）

| rank | label | kind | score |
|---|---|---|---|
| 1 | D1 | text | 0.82494126 |
| 2 | D2 | text | 0.80834318 |
| 3 | D3 | text | 0.78335876 |
| 4 | D5 | text | 0.73889149 |
| 5 | T_NORTHWIND | text | 0.72656572 |
| 6 | D6 | text | 0.72603952 |
| **7** | **M_IMG_ZH** | **image** | **0.72566724** |
| 8 | M_AUD_DIQIU | audio | 0.67628604 |
| 9 | M_AUD_ZH | audio | 0.67496494 |
| 10 | M_IMG_EN | image | 0.59384798 |

- 目标 **rank 7/10**；`margin_to_prev=0.00037228`（与 D6 几乎并列差）、
  `margin_to_top=0.09927402`（离 top-1 D1 较远）、`margin_to_next=0.0493812`。
- **中文图片竞争诊断**：目标图被 **5 条中文文本 distractors**（D1/D2/D3/D5/T_NORTHWIND，Laozi/成語类）
  与 D6 压在下方；目标图与文本簇余弦偏高（R6 诊断已证文档侧 0.7665–0.7856），
  且目标图仅以 **0.00037** 险胜 D6。这是真实观测事实，**不**据此改阈值/加媒体 boost/重写 gate。

### 4.2 `Q_NEG_ZH`（negative control）

- full 10：D2 0.71099 > D6 0.71077 > D5 0.70673 > D1 0.69837 > T_NORTHWIND 0.68976 >
  D3 0.68027 > M_AUD_DIQIU 0.66427 > M_AUD_ZH 0.61649 > M_IMG_ZH 0.58265 > M_IMG_EN 0.56557。
- 产品 top-5 = D2,D6,D5,D1,T_NORTHWIND。**纯 top-k NN（无阈值/弃答）→ 预期行为，非 ACL/契约失败。**

### 4.3 两层 score 与独立重算

- 产品外层 `VerifiedHit.to_dict()` 字段
  `['basis','content_hash','locators','reason','scope','snippet','source_id','source_version','stale','title','verified']`
  —— **无 `score`、无 `similarity`**（R6 `score=null` 的根因）。
- 候选层 `VectorIndex.search()` 含 `score`；本包两通道**分别**落盘，**不重复** R6 误读。
- **独立重算（query 向量 + 复用 R5 文档向量逐条余弦）顺序与产品顺序完全一致**
  （两查询 `independent_order_matches_product=true`）。

## 5. 端点诊断：exact protocol vs prior / cause / confidence

- **exact protocol vs prior**：§2 表；除 **timeout budget** 外**全部一致**。
- **cause**：R6 的 30 s 超时来自 **R6 时点的端点瞬时无响应**，**非**协议差异、
  **非**代理、**非**“正常工况需要 >30 s”（R7 同一请求 0.02–0.06 s 成功）。
  最可能形式：`--parallel 4` 槽位被占导致排队 >30 s，或短时首次冷加载偶发；
  但 R6 未落盘 raw 响应/异常类型，故**不对具体瞬时状态作唯一断言**。
- **confidence**：**中高**。
  - 支持：协议逐维一致 + 同一请求 90 s 内秒回 + 端点模型 loaded 且未空闲卸载。
  - 限制：R6 原始失败响应体与异常类型缺失；无法排他地证明“排队 vs 冷加载 vs 其他”。

## 6. 明确 UNKNOWN / 不证明

- R6 时点端点的**确切**瞬时状态（排队/冷加载/其他）：**UNKNOWN**。
- R6 首次失败异常的**精确类型**：**未捕获**；本包**不**回顾性编造。
- R5 历史 query 向量/margin：**不可重建**；本包**不**做回顾性精确复算。
- 端点在 R4/R5/R6/R7 之外的**持续可用性/容量**：**未测**，**不**声明。
- **不存在**被证明的产品代码缺陷；R6 失败归因于端点瞬时状态，非产品缺陷。
- **不**据本包排名关闭跨模态质量；**不**在同批查询上调阈值。

## 7. 对 LG-037 的含义（无新质量结论之外的越界）

- 取得**首次完整、可复算**的真实 10 候选分数与排名（R7 new observation）。
- 旧 **R5 冻结图片硬门 FAIL 不变**（`Q_IMG_ZH` 目标仍不在 top-5，rank 7）；
  旧负向 top-k NN 无弃答为**预期**、非 ACL/契约失败。
- **不加新阈值/媒体过滤**；**不在冻结 R5 查询上调阈值**；**不重写 R5 gate**。
- **不解锁 LG-040/041**；产品真实 worker 调用 0。

## 8. 边界与计数

- 无产品/backlog/docs/tests/前端改动；仅 `probes/materials-endpoint-r7-20261016/**`。
- 只读 GET **2/3**；embedding POST **2/2**；retry **0**；串行；media/OCR/ASR/worker **0**；
  无模型安装/换供应商/服务重启；未改远端服务或配置。
- 未 push/deploy/publish/reset/clean；无后台任务。
- 成本：LAN unknown；pi/DeepSeek unknown **非 0**。

## 9. 剩余动作 / 最小后续建议（仅在已证范围）

- 若需区分“排队 vs 冷加载”，**新开**一轮并在 R6 同式 30 s 预算下记录**完整异常类与 raw 响应**
  （R7 harness 已具备全路径记录能力）；**不在本轮**重放 R6、不改产品默认 timeout。
- 端点为**可配置测试端点**，不硬编码产品依赖；本包不据此改动产品配置。
