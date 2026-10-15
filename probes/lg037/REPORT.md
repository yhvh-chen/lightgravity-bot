# LG-037 REPORT — 可选多模态向量索引

- owner：`agent:pi-lg037`；基点：`dda78f2`（`dev/lg037`）
- 结论：**实现完成；机制/降级以替身向量验证通过；真实检索质量未验证（授权端点不可达）**。
  任务保持 `in-progress`，**LG-040 不解锁**，不声称图片/PDF 检索质量通过。

## 1. 交付内容

| 文件 | 作用 |
|---|---|
| `backend/lightgravity/sources/vectors/embedder.py` | 唯一向量服务客户端；文本走 OpenAI-compatible `input` 字符串；媒体走**已测** llama.cpp `input[].content[]`（`image_url`/`input_audio`）；可配置、有界、无自动重试、无凭证落盘 |
| `backend/lightgravity/sources/vectors/index.py` | 可删除重建的向量缓存（stdlib JSONL，无独立向量库服务）；记录 **model/dim/fragment_hash/cache_version**；模型切换拒绝混用 |
| `backend/lightgravity/sources/vectors/service.py` | 建/重建/失效/检索门面；媒体**直接建向量**不伪造成文字；写入 `source.index.vector`/`vector_model`；授权候选→回源核对；不可用诚实降级 |
| `backend/lightgravity/sources/vectors/__init__.py` | 包导出 |
| `backend/lightgravity/api/vector.py` | **新增**只读/显式 API 路由：`GET /vector/status`、`GET /vector/search`、`POST /vector/rebuild`（由集成 owner 挂载） |
| `tests/sources/vectors/**` | 39 项：缓存机制、服务机制、embedder 线形、HTTP 路由、真实质量探针（授权跳过） |

**未改**：lexical 核心、`api/app.py`、现有 sources/API/client/前端（038 owner）、coordinator/settings/store/contracts、共享 docs。

## 2. 协议（引用真实 probe，不臆造）

来源 [probes/source-intake/evidence/eg2-endpoint-20261015/REPORT.md](../../probes/source-intake/evidence/eg2-endpoint-20261015/REPORT.md)：

- 服务身份 **llama.cpp `llama-server` router `b11641-843e7dcc1`**，OpenAI-compatible，**非 Ollama**。
- 实测文本 embedding **768 维、有限、L2=1.0**（元数据 `n_embd=512` 与实测冲突 → 用实测 768）。
- 多模态 shape：`input: [{"content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}]}]`；
  真实探测证明「媒体字节与不同媒体内容影响向量」（content-contrast），**语义/识别质量未验证**。
- 本包**不把通用 OpenAI 字符串 embedding 当已测多模态能力**：媒体只按上述 `content` 数组，且仅在可达时发送。

## 3. 质量查询集与真值（预注册，`PLAN.md` 调用前冻结）

- 指标：Recall@1/3/5、MRR、top-1 正确率、负向误命中数，**并与纯词法基线对照**。
- 样本：自造中文小文本；复用 source-intake 合成图 fixture（许可/hash 已记录）；
  真实音频沿用 LG-039 已核 **CC BY-SA 3.0** 中文人声（`Chinese language-1.ogg`，sha256 已记录）——
  **仅作媒体→向量输入，不作转写/ASR 结论**；合成音**不得**作语义质量结论。
- **本次未运行**（端点不可达），因此**不输出任何新质量指标**。

## 4. 验证证据（真实命令）

- `uv run mypy` → **135 source files clean**。
- `uv run pytest tests/sources tests/api tests/contracts -q` → **171 passed, 1 skipped**。
- `uv run pytest -q` → **728 passed, 5 skipped**；stash 对照基线 **690 passed, 4 skipped** →
  差额 `+38 passed +1 skipped` = 本包 39 项，**无回归**。
- 机制覆盖（真实 `FileStore` + 真实 `create_app` + 真实 HTTP，替身向量）：索引失效、作用域只收窄、
  版本变化 → `source_stale`、撤销 → `source_revoked`、模型切换重建不混、删 cache 重建复现、
  维度不匹配不比较、后端失败 → `failed` + 诚实 `index_unavailable`、媒体（图/音）直嵌且 `text==""`、
  **缓存无权限状态**（不含 `task_ref`/作用域值）。

## 5. 真实 / 替身 / 未测

- **真实**：缓存/服务/HTTP 机制在真实文件 SoT 与真实 app 上运行；端点可达性单次真实探测。
- **替身**：向量来自 `FakeEmbeddingBackend`（确定性、无网络）——**只证机制，不证品质**。
- **未测**：真实检索质量（Recall@k/排序/负误命中/词法增益）；真实多模态线形对真服务；
  图片/PDF/音频语义识别质量；中文 ASR（LG-039 已负结论，不重复）。
- **不夸大**：LG-035 真实中文/表格 OCR 质量门仍阻塞；本包未据向量推断 OCR/ASR 文字。

## 6. 预算与计数

- 服务只读 **1** / ≤3；embedding POST **0** / ≤8；零自动重试；并发 0。
- 媒体输入 0 MiB / ≤10 MiB；真实音频 0s / ≤30s。
- 产品 worker/ASR/OCR 调用 **0**；新服务/下载模型 **0**。cost/tokens **unknown**。

## 7. 局限与后续

- 端点不可达即本案的**外部阻塞**；不连续探测、不换服务。恢复后按 `PLAN.md` 运行真实质量探针。
- 检索质量**未经真实服务验证**，因此**不得**作为 LG-040 解锁依据，也不得宣称多模态检索质量通过。
- 向量缓存为**可删除重建派生**；权限/归属/版本始终回源核对，缓存不承载独有业务事实。
