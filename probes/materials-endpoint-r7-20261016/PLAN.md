---
title: "LG-037 R7 端点协议/冷加载诊断 PLAN（冻结于任何 POST 之前）"
doc_type: plan
category: engineering
updated: "2026-10-16"
---

# PLAN — materials-endpoint-r7-20261016（frozen BEFORE any POST）

## 0. 目的、范围与冻结声明

本包是 **LG-037 端点调查/执行 owner** 的 **诊断 + 真实观察** 阶段。

**问题**：端点 `http://192.168.8.12:11434` `/health` 返回 **200**，但 R6
`materials-vector-observe-r6-20261016` 的两次 embedding POST 均在 **~30 s** 超时
（`index_unavailable`），而 **R4/R5 的同类请求在同一端点上成功且延迟仅 0.05–0.12 s**。
需要**基于既有原始证据**诊断：实际协议/路由/模型/冷加载差异；比较实际 URL/body/model/
task 编码/content-type、代理变量 vs 实际 httpclient 设置、timeout/冷加载标志。

**本包不做**：不假定健康 200 = 推理容量；不新增生产代码（除非证明缺陷）；不做质量调优；
不重写 R5 gate；不在同批冻结查询上调阈值；不回顾性编造 R6 未捕获的异常类型；
不做二次模型切换；不做 OCR/ASR/音频/图片输入。

### 0.1 冻结

本 PLAN 必须在**任何真实 POST 之前**作为**独立 commit** 冻结（见 §8）。

## 1. owner / 隔离

- owner 目录：`probes/materials-endpoint-r7-20261016/**`（本文件所在目录，唯一可写区）。
- worktree：`/home/yhvh/code/lightgravity-bot-worktrees/materials-endpoint-r7-20261016`
  branch `investigate/materials-endpoint-r7-20261016`，基点 `main@2d76c83`（已验证 clean）。
- **无产品/backlog/docs/tests/前端/README 改动**；并行 owners
  `materials-fixtures-r7`、`materials-layout-r7` 使用各自目录，**不做产品 LAN/模型调用**；
  本包是**唯一端点请求方**。
- 无 push / deploy / publish / reset / clean / 服务重启 / 模型安装 / 供应商切换；
  不改远端服务或配置；无后台任务。

## 2. 已证事实（来自既有原始证据，只读，无新网络）

以下为**本 PLAN 冻结前**从仓库既有证据中读出的事实，用于设定诊断假设；全部可复核：

| # | 事实 | 证据来源 |
|---|---|---|
| F1 | R4/R5 与 R6 使用**同一** `OpenAICompatEmbeddingBackend` 类与**同一** URL `http://192.168.8.12:11434/v1/embeddings`、**同一** model `embeddinggemma-2-Q8_0` | 三份 harness 源码 |
| F2 | R4/R5 body 形状 `{"model","encoding_format":"float","input":[<text>]}`（text 为裸字符串数组元素）；content-type `application/json`；无 `Authorization`（未配 token） | `embedder.py` `embed()` + 三份 harness |
| F3 | R4/R5 用 `default_timeout_seconds=90.0, cold_timeout_seconds=90.0`；text 走 **cold** 分支（`item.part_type=="text"` → cold timeout） | R4/R5 harness §构造 |
| F4 | R6 用 `default_timeout_seconds=30.0, cold_timeout_seconds=30.0`，并额外 `socket.setdefaulttimeout(3.0)` | R6 `observe_harness.py` |
| F5 | R6 health GET **200** `{"status":"ok"}` 0.004 s；两次 query POST 各 **~30.04 s / 30.03 s** 后 `index_unavailable`，**无原始响应体**（超时） | R6 `STATUS.md` / `observation.json` |
| F6 | R4 查询 text 延迟 0.064/0.060/0.070/0.065 s；R5 查询 text 延迟 0.05–0.06 s；文档 text 0.035–0.125 s | R4/R5 `crossmodal_results.json` `post_log` |
| F7 | R4/R5 docs 向量缓存 header `cache_version=1, dim=768, model=embeddinggemma-2-Q8_0`，10 条（6 text + 2 image + 2 audio），**无 query 向量** | R5 `private/.../vectors.jsonl` |
| F8 | 无任何 `*proxy*` 环境变量；harness 与 embedder 均**无 ProxyHandler/getproxies** 代码；git 无 `http.proxy` | 进程 env / 源码 / git config |
| F9 | 端点身份为 llama.cpp `llama-server` router 模式 `b11641-843e7dcc1`（非 Ollama），多模态 `input[].content[]`；`GET /health` 200、`GET /v1/models` 200 | `probes/source-intake/evidence/eg2-endpoint-20261015/REPORT.md` |
| F10 | 端点在 R4/R5 报告时 `embeddinggemma-2-Q8_0` 为 `loaded`；router `models_autoload=true`，`max_instances=2` | 同上 eg2 REPORT |

### 2.1 由 F1–F6 得到的**可检验**主假设（不是结论）

- **H1（协议/body 无差异）**：R7 若复用**完全相同**的产品 protocol body（同 P3 类路径），
  则请求字节级与 R4/R5 一致 → 协议/路由/task 编码/content-type 不是差异源。
- **H2（超时预算差异）**：R6 与 R4/R5 在同一端点上的唯一**确定性**差异是
  **text cold timeout 30 s vs 90 s**（F3 vs F4）。若端点在 R6 时因**冷加载**（模型被
  unload 后 reload）需要 >30 s，则 R6 的 30 s 超时**必然**失败，而 R4/R5 的 90 s 成功。
- **H3（端点状态变化）**：R6 距 R5 约 34.8 min（ts R5 1792105794 vs R6 1792107880），
  期间端点可能由 warm 转冷或被其他客户端占用；健康 200 **不等于** embeddings 容量。
- **H4（代理无关）**：无代理变量/代码（F8）→ 代理设置不是差异源。

### 2.2 非目标 / 不判定

- 不判定检索质量；不据观测分数关闭跨模态质量；不重算 R5 历史 margin（query 向量历史未保留，F7）。
- **不回顾性编造** R6 首次失败的异常类型（R6 首跑未落盘异常类型）；R7 用**新**观测的
  真实错误类记录。
- 不把端点可达当检索质量通过；不把 health 200 当推理容量。

## 3. 冻结查询（2 条文本，text ≤ 1 KiB）

| id | 文本 | 类型 | 目标 |
|---|---|---|---|
| `Q_IMG_ZH` | `老子 道德經 註解 學說` | positive_crossmodal_image | `M_IMG_ZH` |
| `Q_NEG_ZH` | `量子色動力學 膠子 強相互作用` | negative_control | `[]` |

- 二者为 R5 冻结语料**原字文本**，**不新增/不改写/不调参**。
- top-k：产品 `limit=5` 原生命中；**full 10** 排序用于分数/rank/margin。

## 4. 真实产品路径（记录对象）

在**未修改的产品路径**上运行：

```
RecordingEmbeddingBackend（包装真实 OpenAICompatEmbeddingBackend，仅记录）
  → 真实 HTTP POST /v1/embeddings（唯一真实后端；与 R4/R5 相同 protocol body）
  → 真实 VectorSearchService.search(VectorSearchRequest(query=..., limit=5, include_global=True))
  → 真实 VectorIndex.search（产品余弦，加载只读复用的 R5 文档向量）
```

- **reuse 早期成功 protocol**：R7 **不**修改请求 body，直接使用产品 `embed()` 产生的
  body（与 R4/R5 相同，F2）。**不做 adaptative protocol 猜测，不做额外尝试。**
- 端点**仅** `http://192.168.8.12:11434`，模型**仅** `embeddinggemma-2-Q8_0`，无 auth。
- **timeout 对齐早期成功请求**：`default_timeout_seconds=90.0, cold_timeout_seconds=90.0`
  （即 R4/R5 实际成功协议）；`connect=3s`。**不用 30 s**（R6 差异，H2 的检验条件）。
- `socket.setdefaulttimeout` 设为 3.0 仅作 connect 兜底（同 R6 设计意图），
  但**不**覆盖每次请求的 90 s read timeout。

### 4.1 记录型 wrapper 要求（离线先验证）

1. **全路径记录**：成功与**所有异常路径**均 append 记录（修复 R6 首跑只记成功的缺陷）。
2. **硬上限**：第 3 次 POST 调用**在 HTTP 之前**抛错（`POST_CAP=2`）。
3. **转发前预留**：`evidence/post_reservations.jsonl` append+fsync **先于** HTTP。
4. **成功时**记录：actual query vector（768 完整）、vector sha256、dim、finite/nonzero/L2、
   `prompt_tokens`/usage、raw response body。
5. **失败时**记录：异常类名、message、latency、wire request（无密钥）。
6. **outerVerifiedHit vs candidateVectorIndex 分离**：产品 `VerifiedHit.to_dict()` **无**
   `score`（R6 已证）；R7 分别落盘 (a) 产品原生命中、(b) `VectorIndex.search()`
   完整候选 `score`、(c) 独立重算余弦。**不重复 R6 的 score=null 误读。**

## 5. 网络预算与计数（硬约束）

- **新增阶段端点只读 GET ≤ 3**：仅 `GET /health` 与 `GET /v1/models`（`/api/version` 可选），
  目标**仅** `http://192.168.8.12:11434`，`connect=3s / total=8s`。
- **embedding POST 恰好 2**（`Q_IMG_ZH`、`Q_NEG_ZH` 各 1 次）。
- `concurrency=1`（严格串行）；`retry=0`；**总 timeout 90 s / connect 3 s**。
- text-only，`text ≤ 1 KiB/query`；`audio=0 image=0 docembedding=0 OCR=0 ASR=0 worker=0`。
- **同一实际模型** `embeddinggemma-2-Q8_0`；无第二个模型/无换供应商/无模型安装。
- **首次真实请求 90 s 无响应 → 立即停止后续 POST，第二条标 `NOT_EXECUTED`；不盲重试。**
- 失败预算后**不再 GET**；**不**做未授权 LAN 扫描；**不**探测其他主机/端口。
- 官方 llama.cpp 文档**仅在确需时**查阅，≤3 GET，有界输出，记录 provenance
  （本 PLAN §2 已由 eg2 REPORT 覆盖协议形态，预期**不需要**新文档 GET）。

## 6. 离线有意义检查（FIRST，无网络）

在任何 POST 之前，离线验证 harness：

1. **全路径记录**：注入**替身**后端（确定性、无网络），令其抛异常，断言失败路径也写入记录。
2. **硬上限前置**：断言第 3 次 `reserve()` 在 HTTP 前抛 `HardCapError`，替身后端仅 2 次。
3. **query 向量落盘**：替身后端下断言 query 向量/sha256/dim/`prompt_tokens` 写入证据结构。
4. **两层 score 分离**：断言产品 `VerifiedHit.to_dict()` 无 `score`，候选 dict 有 `score`；
   并断言 fallback/candidate vector index 路径被分别记录。
5. **维度/finite**：复用 R5 文档向量 10 条 / 768 维 / finite / 非零；header 一致。

自检**不**发网络调用；自检通过后才执行真实边界 GET 与 2 POST。

## 7. 真实执行顺序（一次性）

1. 只读复制 R5 `vectors.jsonl` → 本包 `private/r5-vectors/`；核对 header 与逐条 `fragment_hash`、
   sha256 字节一致。
2. 离线自检（§6）。
3. 构建记录型 backend（包真实 backend，`max calls=2`，`connect=3s`，`timeout=90s`）。
4. 有界只读 GET：`/health`（必选 1），`/v1/models`（可选 ≤2）；写 `http/` 原始响应。
5. `Q_IMG_ZH`、`Q_NEG_ZH` 各 **1 次**真实 query（串行，转发前预留）。
6. full-10 排序、目标 rank/margins、native hits、usage；**独立重算**并与产品顺序比较。
7. 若两条均成功且版本可用：raw top-10 候选分数用于诊断中文图片竞争。
8. 写 `evidence/observation.json`、`http/**`、`evidence/post_reservations.jsonl`、`STATUS.md`、`REPORT.md`。

## 8. 判定与不判定

- **判定记录**：实际 GET/POST 使用与结果、exact protocol（R7 vs 早期）、latency、error class、
  端点响应；若成功则实际排名/rank/margin。
- **不判定**：检索质量是否通过；不关闭跨模态质量；不解锁 LG-040/041。
- 负向 top-k 若为 NN（预期）→ 记**预期行为**，**非 ACL 失败**。
- 若两条 POST 均成功且拿到 raw 分数 → 诊断中文图片竞争（仅报告事实，不改阈值）。
- 若端点不可用 → 给出**当前**请求 wire + latency + error class 的**确切**原因；
  **不写“一切健康”**。

## 9. 预算（执行侧）

- 壁钟 ≤ 420 s；≤ 65 rounds；≤ 115000 non-cache tokens；`retry=0`；无后台任务。
- 成本：LAN unknown；pi/DeepSeek unknown **非 0**。

## 10. 交付

- 本 PLAN（POST 前独立 commit）、`STATUS.md`、`REPORT.md`、`evidence/**`、`http/**`。
- HEAD/branch、实际 GET/POST 使用与结果、exact protocol vs prior、cause confidence、
  若有实际排名则 rank、remaining action。

## 11. 后续提议（仅在已证范围）

- 若 R7 证明 90 s cold timeout 成功而 30 s 失败，则为**端点冷加载 >30 s** 的因果事实，
  可作为“R7 式新观测”输入；**不在本轮**改产品默认 timeout，**不改阈值**。
