---
title: "LG-037 R7 端点诊断/观察 STATUS"
doc_type: status
category: engineering
updated: "2026-10-16"
---

# STATUS — materials-endpoint-r7-20261016

## 阶段

- **phase = ENDPOINT_DIAGNOSIS_AND_OBSERVATION**（协议/冷加载诊断 + 真实观察），
  **非**质量调优、**非**重写 R5 gate。
- PLAN 已于**任何端点调用之前**冻结为独立 commit `47f1a05`（基点 `main@2d76c83`，已验证 clean）。
- 离线有意义检查（无网络）**已通过**：`evidence/offline_checks.json` `all_pass=true`。

## 离线检查结论（FIRST，无网络）

1. **全路径记录（proven）**：包装器对成功与**失败**路径均记录；替身后端抛错时
   `response=null`、`error_class=RuntimeError`、latency 落盘。修复 R6 首跑“只记成功”缺陷。
2. **硬上限前置（proven）**：第 3 次 `reserve()` 在 HTTP **之前**抛 `HardCapError`；
   替身后端仅被调用 **2** 次。
3. **query 向量落盘（proven）**：替身后端下 768 维向量/sha256/dim/`prompt_tokens` 落盘。
4. **两层 score 分离（proven）**：产品 `VerifiedHit.to_dict()` 字段**无** `score`；
   `VectorIndex.search()` 候选 dict **有** `score`。→ 分开记录。
5. **R5 复用向量（proven）**：10 条 / 768 维 / finite / 非零；header
   `model=embeddinggemma-2-Q8_0, dim=768, cache_version=1` 一致。

## 真实运行结果（有界）

- **只读 GET 2/3**：`GET /health` → **200** `{"status":"ok"}` 0.0038 s；
  `GET /v1/models` → **200**，`embeddinggemma-2-Q8_0` **loaded**（`--sleep-idle-seconds -1`，
  `--parallel 4`，`--mmproj ...`）。
- **embedding POST 2/2**（串行、retry 0、timeout 90 s / connect 3 s、text-only）：
  - `Q_IMG_ZH` → **ok**，embed latency **0.0614 s**，768 维，L2≈1.0，`prompt_tokens=12`。
  - `Q_NEG_ZH` → **ok**，embed latency **0.0220 s**，768 维，L2≈1.0，`prompt_tokens=12`。
- 计数：`post_used=2/2`、`post_attempted=2`、`get_used=2/3`、`retries=0`、
  `media_inputs=0`、`audio_seconds=0`。
- 预留先于转发：`evidence/post_reservations.jsonl`（2 条，转发前）。
- 原始请求/响应落盘：`http/v1_models.raw.json`、`http/health.raw.json`、
  `http/queries/*/embeddings.raw.json`（含完整 768 维与 usage）、`http/queries/*/observation.raw.json`。

## 真实排名（new observation，非 R5 重算）

`Q_IMG_ZH`（目标 `M_IMG_ZH`，positive_ text→image）：

| rank | label | kind | score |
|---|---|---|---|
| 1 | D1 | text | 0.82494 |
| 2 | D2 | text | 0.80834 |
| 3 | D3 | text | 0.78336 |
| 4 | D5 | text | 0.73889 |
| 5 | T_NORTHWIND | text | 0.72657 |
| 6 | D6 | text | 0.72604 |
| **7** | **M_IMG_ZH** | **image** | **0.72567** |
| 8 | M_AUD_DIQIU | audio | 0.67629 |
| 9 | M_AUD_ZH | audio | 0.67496 |
| 10 | M_IMG_EN | image | 0.59385 |

- 目标 **rank 7/10**，`margin_to_prev=0.00037`（与 D6 几乎持平）、`margin_to_top=0.09927`。
- `Q_NEG_ZH`：top-5 = D2,D6,D5,D1,T_NORTHWIND（纯 NN，**预期**，非 ACL 失败）。
- **独立重算顺序与产品顺序完全一致**（两查询 `order_match=true`）。
- 产品外层 `VerifiedHit` **无** `score`；候选层有 `score`（两通道分别落盘）。

## 端点诊断结论（based on facts, not guesses）

- 协议 URL/route/model/task 编码/content-type/auth/http client **R4/R5/R6/R7 完全一致**。
- 代理变量/代码**均无**（非差异源）。
- **R6 与 R4/R5 的唯一确定性差异是 text/cold timeout：30 s vs 90 s**。
- R7 用 **90 s**（R4/R5 协议）时，**同一请求在 0.022–0.061 s 成功**；
  端点 R7 时 **warm 且快**。
- ⇒ R6 的 30 s 超时**不是**“端点正常工况需要 >30 s”；更符合 **R6 时点的端点瞬时状态**
  （busy/queued/stuck，`--parallel 4` 槽位可能的排队；或短时冷加载首次触发），
  到 R7 时已恢复。**health 200 不等于 embeddings 容量**。
- **未**回顾性编造 R6 未捕获的异常类型；上述为**因果事实 + 明确置信度**，非断言。

## 边界声明

- **保持旧 R5 质量 FAIL 不变**；本包**不**声称检索质量通过；**不解锁 LG-040/041**。
- 新 query 向量**不能**重建 R5 历史 query 向量；**不做**回顾性精确 margin 复算。
- 未改产品/backlog/docs/tests/前端；仅 `probes/materials-endpoint-r7-20261016/**`。
- 未 push/deploy/publish/reset/clean；无后台任务；无产品 LAN 以外的外部调用。
