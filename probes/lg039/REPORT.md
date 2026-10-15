---
title: "LG-039 中文语音转写后端与质量验证报告"
doc_type: report
category: quality
status: complete
updated: "2026-10-16"
---

# LG-039 — 中文语音转写后端与质量验证报告

## 0. 结论（先行）

**负结论：已授权的唯一候选服务不存在任何可用的中文 ASR 路径。**
在该服务的全部 4 个模型上，用**真实人类中文/中英混合语音**实测所有已知音频入口，
**没有任何一条路径返回转写文字**——全部为 501「不支持音频」、500「不支持 audio input」、
500「embedding 无 logits」或 500「模型加载失败」。

- **LG-041 不解锁**：质量门未达标（实际上无从计算质量，因为系统零输出），不得启用中文转写。
- 该负结论**只针对该服务当前已安装模型**，不泛化为「llama.cpp/所有服务都没有 ASR」。
  达成 ASR 需要一个**声明并支持音频→文本的生成模型 + 匹配的音频 mmproj**（当前服务上没有）。
- 未伪造任何转写；embedding 向量、英语 reader 作者指标、合成音频均**未**被当作中文转写证据。

## 1. 范围、授权与预算（预注册）

- 候选服务：`http://192.168.8.12:11434`（**唯一授权测试端点**）。协议核实为
  **llama.cpp `llama-server` router**，build_info `b11641-843e7dcc1`，`role=router`，
  `models_autoload=true`。**非 Ollama**；未切换任何其它或收费供应商。
- 可写范围：`probes/lg039/**`、`backlog/tasks/LG-039.md`。未改共享 docs/代码/其它 worktree，
  未 push/deploy/publish，未建产品接入，未置 LG-041 状态。
- 预算与实耗：
  - 产品服务**只读** `health`/`models`/`props` = **3 次**（上限 4）。
  - 推理 POST = **5 次**（上限 6，含失败，零自动重试）：gemma4-mtp 转写、qwen3.8-27b 转写、
    qwen3.8-27b chat input_audio、embeddinggemma-2 转写、bge-reranker 转写。
  - 单次 HTTP timeout ≤90s（最长一次 70.4s，gemma4-mtp 加载失败）；并发 1；总量音频 ≤90s。
  - 公开下载：`Chinese language-1.ogg` **1,509,884 字节（约 1.44 MiB）**，单文件 ≤8MiB、
    合计 ≤15MiB，HTTP timeout 30s，未运行下载脚本、未引入项目依赖。

## 2. 真实人声来源、许可与真值

- **来源**：Wikimedia Commons 文件 `File:Chinese language-1.ogg`
  （`https://upload.wikimedia.org/wikipedia/commons/f/fb/Chinese_language-1.ogg`）。
  经 Commons API `extmetadata` 核实的许可：**CC BY-SA 3.0**（LicenseUrl
  `http://creativecommons.org/licenses/by-sa/3.0/`），作者 `Audioman at English Wikipedia`，
  原始上传 2006-04-08。内容是英语维基百科 "Chinese language" 条目开场白的**真人朗读**
  （含中英混合发音），属**公开、明确许可**的真实人类语音，非个人私密文件。
- **固定来源与 hash**（下载后本地计算）：
  - `real_voice_chinese_language-1.ogg`（原件，143.58s）sha256
    `1a8df6fbd1cff0ce6c192932cb6d1d5a8e20e551ba915896685544abb0528e9f`
  - 截取前 60s、16kHz 单声道 PCM 送入请求的副本 sha256
    `40138aca20df96285f971fc520dd1caedbbb980bd387595891dc141f8f97933c`
    （用本机 `ffmpeg` 转换，仅作测试输入，≤8MiB）。
- **真值（ground truth）状态**：该文件是英语维基条目朗读，**未取得逐句时间对齐的官方中文
  转写真值**。因服务对所有音频路径**零输出**，CER/关键信息命中**无法且无必要**计算；
  缺失真值不影响本报告的负结论（负结论是「无输出」而非「输出质量差」）。
- **覆盖缺口（如实记录）**：口音、噪声、长音频（>90s）、时间戳、纯中文长句的**质量维度
  完全没有被测**——不是通过，而是**无法开始**，因为服务不产出任何转写。合成音频
  （`probes/source-intake/.../fixtures/audio.wav`，espeak-ng）仅用于复现既有 501 证据，
  **未**用于质量结论。

## 3. 实测矩阵（原始证据见 evidence/）

所有请求均带上述真实人声输入；原始响应逐字存档于 `evidence/raw_*.json`。

| # | 模型 | 入口 | HTTP | 耗时 | 原始响应要点 |
|---|---|---|---|---|---|
| 1 | `gemma4-mtp` | `POST /v1/audio/transcriptions` | **500** | 70.42s | `model name=gemma4-mtp failed to load` |
| 2 | `qwen3.8-27b` | `POST /v1/audio/transcriptions` | **501** | 10.97s | `The current model does not support audio input.` |
| 3 | `qwen3.8-27b` | `POST /v1/chat/completions` + `input_audio` | **500** | 0.11s | `audio input is not supported - hint: ... provide the mmproj` |
| 4 | `embeddinggemma-2-Q8_0` | `POST /v1/audio/transcriptions` | **500** | 0.09s | `the current context does not support logits computation. skipping` |
| 5 | `bge-reranker-v2-m3-Q8_0` | `POST /v1/audio/transcriptions` | **501** | 2.16s | `The current model does not support audio input.` |

- **失败率：5/5 = 100%**。成功转写：**0**。
- 可用输出：无。时间戳：无。CER：不适用（无输出、无真值）。
- `gemma4-mtp` 是任务点名需核查的模型：其声明模态为 **text/image**（mmproj 为图像，
  `gemma-4-26B-A4B-it-qat-q4_0-...-mmproj`），**不含 audio**；且本次**加载失败**
  （70s 后 500），未产生任何输出。**未自动重试、未换模型无限试**。

## 4. 服务能力事实（只读核实）

`GET /v1/models`（llama.cpp router 返回）：

| 模型 | 输入模态 | 生成能力 | 状态 |
|---|---|---|---|
| `qwen3.8-27b` | text, image, video | 是 | loaded |
| `bge-reranker-v2-m3-Q8_0` | text | 否（reranker） | unloaded |
| `embeddinggemma-2-Q8_0` | text, image, audio, video | **否**（`--embeddings`，无 logits） | loaded |
| `gemma4-mtp` | text, image | 是 | unloaded（本次加载失败） |

**关键判据**：全服务**没有一个模型同时满足「接受音频输入」且「具备文本生成能力」**。
唯一声明 audio 的 `embeddinggemma-2` 是 embeddings-only，其 audio 模态产出的是**向量**，
**不是文字**——按任务要求，**向量不得当作转写**。
这与既有证据（[probes/source-intake](../source-intake/README.md)：已测 Qwen 的 ASR 路由拒绝、
已测 embedding 转写失败、gemma4-mtp 未测）一致，并**补上了 gemma4-mtp 的实测缺口**。

## 5. 基础设施/资源可知范围

- 远端为 llama.cpp router，`max_instances=2`、`models_autoload=true`；模型路径在远端
  `/models/...`（不可见本机）。**远端 GPU/CPU/内存具体规格不可知**。
- `gemma4-mtp` 指向一个约 31B 的 GGUF（`gemma-4-31B-it-qat-UD-Q4_K_XL.gguf`），
  70s 加载失败，**失败根因未由服务显式给出**（可能是 OOM 或权重不可用），**不猜测**。
- 未知项：远端硬件上限、并发语义、模型卸载策略；已知项：build `b11641-843e7dcc1`。

## 6. 与任务验收条件的对照

| 验收条件 | 结果 |
|---|---|
| 先确定可用后端、许可证、模型来源和资源预算 | 已确定：llama.cpp router；无可用 ASR 后端；模型来源/模态已核实；预算见 §1 |
| Qwen/embedding 失败不泛化为所有模型 | 已遵守：**逐个模型**实测（含点名未测的 `gemma4-mtp`），未泛化；结论限定本服务 |
| 预先固定有授权人声样本、中文真值与判据 | 人声+许可+hash 已固定（§2）；因服务零输出，真值/CER 不适用；判据预注册见 STATUS |
| 覆盖口音/噪声/长音频/时间戳/中英混合 | **未覆盖**（服务不产出，无法开始）；如实记录，**不声称达标** |
| 报告 CER、关键信息、耗时、失败率 | CER 不适用；耗时与失败率 100% 见 §3；无输出 |
| 英语 reader 作者指标不作中文证据；向量不当转写 | 已遵守，未引用英语指标，未把 embedding 向量当文字 |
| 达标给接入建议；不达标保留失败记录与原件，明确阻塞 | 不达标；失败原件与原始响应已存 `evidence/`；LG-041 阻塞条件见 §7 |

## 7. LG-041 阻塞条件（明确）

LG-041 **不解锁**，需先满足以下任一实质条件后才可能重验：

1. 在该（或另一经授权）服务上安装一个**同时支持音频输入与文本输出**的生成模型 + 匹配的
   音频 mmproj，使 `POST /v1/audio/transcriptions` 或 chat `input_audio` 能返回文字；
2. 或引入独立、已授权的 ASR 服务/模型，并满足本任务同样的真实人声、真值、覆盖与判据要求。

在此之前，产品侧应保持：中文音频**保留原件**、明确记为**失败/不支持**状态，
**不生成空的成功正文**（见 [docs/09 §6 失败诚实](../../docs/09-source-intake-and-retrieval.md)、
[docs/08 §4.3 `source`/`intake_job`](../../docs/08-interface-contract.md)）。

## 8. 未知成本与限制

- 开发模型轮/墙钟受任务预算约束（本包 12 分钟墙钟、≤35 轮、≤100k token 软上限）。
- 产品推理请求已按 §1 计数；**远端单次加载/推理的算力与费用未知**（本机无法计量远端 GPU）。
- 未做：逐项独立 QA、产品全量测试、其它供应商、长音频/噪声/口音专项、时间戳验证。
- 本报告为**探针证据**，不是产品 schema/API/依赖，也不是 LG-040 集中验收。

## 9. 原始证据清单

| 文件 | 内容 |
|---|---|
| `evidence/raw_tx_gemma4-mtp.json` | gemma4-mtp 转写 500 加载失败 |
| `evidence/raw_tx_qwen3.8-27b.json` | qwen3.8-27b 转写 501 不支持音频 |
| `evidence/raw_chat_input_audio_qwen3.8-27b.json` | qwen chat input_audio 500 不支持 |
| `evidence/raw_tx_embeddinggemma-2.json` | embedding 转写 500 无 logits |
| `evidence/raw_tx_bge-reranker.json` | bge-reranker 转写 501 不支持音频 |
| `evidence/real_voice_chinese_language-1.ogg` | 真实人声原件（CC BY-SA 3.0，sha256 见 §2） |

## 10. 参考

- [LG-039 任务](../../backlog/tasks/LG-039.md)、[LG-041 任务](../../backlog/tasks/LG-041.md)
- [滚动排期 §6](../../docs/06-roadmap.md#6-去中心化与-embedding-扩展排期2026-10-15)
- [接口契约](../../docs/08-interface-contract.md)、[资料接入设计](../../docs/09-source-intake-and-retrieval.md)
- [既有 source-intake 证据](../source-intake/README.md)、[执行规则](../../agent.md)
