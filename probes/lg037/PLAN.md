# LG-037 预注册计划（**调用服务与写代码前冻结**）

- 任务：LG-037 接入 EmbeddingGemma 2 可选多模态向量索引
- 基点：`dda78f2`（claim commit，`dev/lg037`）
- owner：`agent:pi-lg037`
- 冻结时间（UTC）：2026-10-15T14:44Z
- 授权候选服务：`http://192.168.8.12:11434`（**唯一**候选；地址/模型必须可配置，不硬编码为产品运行依赖）

## 0. 事实源与边界（不可弱化）

- 文件（原件 + `SOURCE.md` frontmatter + 正式内容）为唯一 SoT；向量索引是**可删除重建的缓存**，
  不承载独有的权限/归属/正文/控制状态。检索先产**授权候选**，再**回源核对**存在/哈希/版本/权限。
- 向量为**可选派生**；不可用/未配置时必须**词法检索与原件查看照常可用**（LG-036 已有词法路径）。
- 媒体（图片/音频等）**直接建向量**，不伪造成文字；OCR/ASR 是**独立通路**，不得用向量输出冒充文字。
- 记录模型**标识/版本/维度/来源片段 hash/缓存版本**；**模型切换必须整库重建，不混用不兼容向量**。
- **embedding ≠ OCR/ASR**。LG-035 图片/PDF OCR **质量门仍阻塞**；本包**不声称**图片/PDF 检索质量通过。

## 1. 服务协议（引用真实 probe 格式，不臆造）

已测协议来自 [probes/source-intake/evidence/eg2-endpoint-20261015/REPORT.md](../../probes/source-intake/evidence/eg2-endpoint-20261015/REPORT.md)：

- 服务身份：**llama.cpp `llama-server` router `b11641-843e7dcc1`**（OpenAI-compatible），**非 Ollama**
  （`/api/version`、`/api/tags` → 404）。`GET /props` → `{"role":"router","build_info":"b11641-843e7dcc1"}`；
  `GET /health` → `{"status":"ok"}`；`GET /v1/models` → OpenAI 兼容，`owned_by: llamacpp`。
- 目标模型：`embeddinggemma-2-Q8_0`（别名 `embeddinggemma-2` 等），**实测输出 768 维、有限、L2=1.0**
  （元数据 `n_embd=512` 与实测 768 冲突 → **以实测 768 为准**）。
- **文本** embedding：`POST /v1/embeddings`，`input` 为字符串数组或字符串；`encoding_format: "float"`。
- **多模态** embedding：`POST /v1/embeddings`，`input` 为对象数组，每元素 `{"content":[{type, ...}]}`，
  part 可为 `{"type":"text","text":...}`、`{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}`、
  `{"type":"input_audio", ...}`（真实探测所用 image part 形状见 REPORT §3）。
- 已测事实**仅**为「媒体字节与不同媒体内容确实影响向量」（transport/content-contrast），
  **语义/识别质量未验证**；合成样本不能证明质量。

### 1.1 硬约束

- **不把通用 OpenAI 字符串 embedding 假当已测多模态能力**：多模态调用只按上述 `content` 数组形状，
  且仅在端点可达时发送；否则记 blocked。
- 地址/模型/维度来自配置（env），**不硬编码 LAN 为运行依赖**；未配置 → 诚实 disabled/`capability_unavailable`。

## 2. 检索质量查询集与真值（**调用前固定**）

### 2.1 样本与真值来源

- **文本**：合成/自造的中文小文本片段（本包自建，许可本项目自有），与其语义近邻。
- **图片**：复用 [probes/source-intake/evidence/media-text-index-20261015/fixtures/](../../probes/source-intake/evidence/media-text-index-20261015/fixtures/)
  （`screenshot.png`/`scanned_page-1.png`，合成非私有）+ 真值文本；**许可与 hash 已在 LG-035/证据 B 记录**。
- **音频**：**沿用 LG-039 已核授权的真实人声** `Wikimedia Commons File:Chinese language-1.ogg`
  （**CC BY-SA 3.0**，真人朗读，sha256 `1a8df6fbd1cff0ce6c192932cb6d1d5a8e20e551ba915896685544abb0528e9f`，见
  [probes/lg039/evidence/](../../probes/lg039/evidence/)）——**仅作媒体→向量输入**，**不用于转写/ASR 结论**
  （LG-039 已确证该服务无可用中文 ASR；本包不重复、不推断 ASR 质量）。合成 440Hz 音频**不得**作语义质量结论。

### 2.2 预注册质量指标

在**任一服务调用前**固定以下指标与判据（此后不得改阈值/指标）：

- **Recall@k**（k=1,3,5）：对每个 query，其真值目标是否出现在前 k 个**回源核对通过**的命中中；报告均值。
- **排序**：真值目标的名次（MRR）与 top-1 正确率。
- **负向误命中**：预置**不相干负例 query**（语义无关），统计其在 top-k 中的误命中数（越低越好）。
- **词法基线**：同一查询集先在**纯词法**（LG-036 `GET /search`）上跑，报告其 Recall@k/负误命中，
  作为向量增益的对照。**词法基线不可省**。
- **预算**：见 §3。

### 2.3 判据（各自独立，不互相代替）

- **机制/降级判据（不依赖服务）**：向量缓存可删除重建并复现；模型切换触发重建且不混向量；
  维度/模型/hash/缓存版本正确记录；权限/版本/存在性回源核对后失效；服务不可用 → 词法/原件可用。
  以**替身（stub/fake）向量**验证机制正确性 —— 但**明确标注为替身，不作为真实品质指标**。
- **真实质量判据（依赖服务）**：仅当端点可达且真实模型可调用时产出 Recall@k/排序/负误命中；
  同时报告词法基线与向量；**不得仅凭可达/合成向量声称质量通过**。
- **不达标/不可达**：不输出新质量指标；诚实记 blocked，保留可用降级与实现。

## 3. 服务调用预算（硬边界，超即停）

- `health`/`models` 只读请求合计 **≤3**；**失败不自动重试**。
- `POST /v1/embeddings` **≤8**（含失败；**零自动重试**；**并发 1**）。
- 每次 `timeout ≤60s`；首冷加载 `≤150s`。
- 媒体输入合计 **≤10 MiB**；真实音频 **≤30s**。
- 产品 worker / ASR / OCR 调用 **0**；新服务/下载模型 **0**；凭证仅进程 env，不落仓库/提示词。
- 开发预算：≤15 分钟，≤110 开发模型轮，非缓存 tokens ≤180k。

## 4. 交付物

- 代码：`backend/lightgravity/sources/vectors/**`（可选向量索引 + embedder），
  必要的新 api/vector 配置路由模块；**不改** lexical 核心、`api/app.py`、现有 sources/API/client/前端、
  coordinator/settings/store/contracts 与共享 docs。
- 测试：`tests/sources/vectors/**`（真实 FileStore 的失效/权限/维度/模型切换/删 cache 重建/失败降级 + mypy 相关）。
- 探针/报告：`probes/lg037/{STATUS,PLAN,REPORT,INTEGRATION}.md` + `reports/**`。
- 集成接线（共享 search 组合/配置/挂载）写入 `probes/lg037/INTEGRATION.md`，由唯一 owner 串行处理。

## 5. 当前状态（记录时）

- 端点可达性：**不可达**。单次只读探测 `curl --connect-timeout 5 http://192.168.8.12:11434/health`
  → HTTP `000`，`curl: (7) Failed to connect ... after 3069 ms`，exit 7（证据
  `probes/lg037/reports/endpoint_reachability.txt`）。与 LG-035 最近两次 `No route to host` 一致。
  **不连续探测、不擅自换服务或安装模型**。
- 因此：真实质量指标**不产出**；本包以**替身向量**验证机制/降级，如实记真实/替身/未测。
