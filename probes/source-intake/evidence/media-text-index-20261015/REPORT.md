# REPORT — 多来源成文/索引小闭环（隔离原型验证）

- Executor: pi technical-test executor（有界、隔离原型）
- Date (UTC): 2026-10-15，真实探针窗口 11:05:32Z – 11:10:44Z（约 5 分 12 秒，含首轮模型加载 162 s）
- Writable dir: `/tmp/lightgravity-media-text-index-20261015/`（唯一可写目录；未改产品/worktree/PROJECT/backlog/旧探针）
- Target: 仅 `http://192.168.8.12:11434`（llama.cpp router `b11641-843e7dcc1`，非 Ollama）
- 约束遵守：未下载/新增权重、未改服务配置或默认值、未显式卸载其它模型、未重启、未读 `.env`、未打印凭证、
  未装新依赖、未运行远程脚本、未调用其它代理；样本全为合成/无隐私；子进程以 `env -u DEEPSEEK_API_KEY` 运行。
- 前置证据只读参考：`/tmp/lightgravity-eg2-endpoint-20261015/{REPORT.md,DOC_CORRECTION.md}`。

## 0. 结论一句话

**图像截图与“扫描型 PDF”这一支真正打通：原始媒体 → 真实 OCR 文字 → Markdown(frontmatter) → 可重建词法索引（含来源/行/页定位、重建校验、过期 hash 拒绝）。**
**音频转写一支为真实服务能力缺口（FAIL，未被隐藏）**：服务未安装 ASR/音频 mmproj 模型，`/v1/audio/transcriptions` 与 chat `input_audio` 都明确拒绝。
因此“原始媒体→真实提取文字→Markdown→可重建索引”整体为**部分打通**：文本类媒体完成，音频未完成。

| 环节 | 判定 | 依据 |
|---|---|---|
| A 输入材料（中文截图 + 栅格扫描 PDF + 普通话 TTS） | **PASS** | Pillow + 已装 Noto Sans CJK；`pdftotext` 仅输出 1 字节 ⇒ PDF 无文字层；espeak-ng `cmn` 本地合成 11.875 s |
| B 图像 OCR（截图） | **PASS（小样本）** | `qwen3.8-27b`，CER 0.0，编号/日期/金额全字段精确命中 |
| B 扫描 PDF OCR（栅格页） | **PASS（小样本）** | `qwen3.8-27b`，CER 0.0，发票号/开票日期/价税合计全字段精确命中 |
| C 音频转写 | **FAIL（服务缺口）** | `/v1/audio/transcriptions`→501；chat `input_audio`→500；无 ASR 后端 |
| D Markdown + 词法索引 | **PASS** | 3 份 MD（2 成功 + 1 失败记录），倒排索引关键词命中回指文件/行/页 |
| D 向量缓存（可选，≤2 POST） | **PASS（sanity）** | 1 次批量 embedding，768 维、L2=1.0；语义/精确/负对照排序方向正确 |
| E 可重建性 + 过期 hash 拒绝 | **PASS** | 删缓存重建后 postings/查询一致、源 hash 未变；沙箱改动源文件后命中被拒 |

## 1. 真实样本与 ground truth（合成、无隐私）

| 产物 | 说明 | sha256 |
|---|---|---|
| `ground_truth/doc_image.txt` | 冻结原文（76 字），137… | `8083d2d62c35eae76848…`（完整见文件） |
| `ground_truth/doc_pdf.txt` | 冻结原文（87 字） | `2de470de427fc738cc28…` |
| `ground_truth/audio.txt` | 冻结转写原文（普通话） | `bad89082c30755c65da3…` |
| `fixtures/screenshot.png` | 中文收款通知截图（Pillow 渲染） | `74025921f66ef88a4105020848e6941cd6886512e7b44a69da29603d3194308d` |
| `fixtures/scanned.pdf` | **栅格扫描型 PDF**（图像嵌入，无文字层；`pdftotext`=1 字节） | `bd2045bdd892d436c32bd518a34607d745799fd1b4e8c2c1f95519b675b903b5` |
| `fixtures/scanned_page-1.png` | `pdftoppm -r 150` 渲染页（OCR 输入） | `04c3c4aa7019c6b94112d246b14d9f3c7f3483b7a93b86006ffe3bdba4838afd` |
| `fixtures/audio.wav` | 普通话，22050 Hz 单声道，**11.875 s**，espeak-ng `cmn` 合成（**非真人**） | `580761a61c33ffa68cb5d33bb684cc9a9af1b592dd4070bc4e2d7e91e628d343` |
| `fixtures_manifest.json` | 上述 hash/来源汇总 | — |

- 原文含可机械比对字段：编号、日期、金额、发票号码、（音频）编号/日期/金额。
- 跨材料检索词：`服务`（两文档都有）。
- 负对照：`紫水晶矩阵`（不存在），另保留 `紫水晶项目` 作为词元重叠反例说明。

## 2. 模型与接口 schema（实测）

- Router `/props`：`role=router`, `max_instances=2`, `models_autoload=true`, `build_info=b11641-843e7dcc1`。
- `/v1/models`（实时）：`bge-reranker-v2-m3-Q8_0`(text)、`embeddinggemma-2-Q8_0`(text/image/audio/video)、
  `gemma4-mtp`(text/image, unloaded)、`qwen3.8-27b`(text/image, unloaded)。
- OCR 使用已装 `qwen3.8-27b`，`POST /v1/chat/completions`，typed content
  `{"type":"image_url","image_url":{"url":"data:image/png;base64,…"}}`（schema 依据已存
  `llamacpp_server_README_b11641.md` §chat/completions 与 `llamacpp_multimodal_b11641.md`；未新拉文档）。
- 请求参数：`max_tokens=1024`, `temperature=0`, `stream=false`, `chat_template_kwargs.enable_thinking=false`。
- **提示词只要求“识别可见文字/不推断补全/保留行与标点”，从未把 ground truth 文本放入 prompt。**
- 触发 router 自动加载 `qwen3.8-27b`（首次 162.25 s，≤180 s 硬界，未超时）；未加载/卸载其它模型做改动。

## 3. OCR 可核指标（`ocr_metrics.json`）

Unicode 归一化（NFKC + 去空白）后编辑距离：

| 材料 | gt 字符 | 提取字符 | 编辑距离 | CER | 字符准确率 | 全字段精确命中 |
|---|---|---|---|---|---|---|
| doc_image（截图） | 76 | 76 | 0 | **0.0** | **1.0** | 编号 `LG-2026-1015-007`、日期 `2026年10月15日`、金额 `8,765.42` 全部 ✓ |
| doc_pdf（扫描页） | 87 | 87 | 0 | **0.0** | **1.0** | 发票号码 `25337000000098765432`、开票日期 `2026年10月14日`、价税合计 `1,234.56` 全部 ✓ |

- `finish_reason=stop`；usage：doc_image prompt 562 / completion 65 / total 627；doc_pdf 562/83/645。
- 提取耗时：doc_image 162.25 s（含首轮加载）、doc_pdf 21.80 s。
- 原始响应完整保留：`ocr_doc_image_raw_response.json`、`ocr_doc_pdf_raw_response.json`；
  提取文本：`ocr_*_extracted.txt`。
- **注意：这是干净合成小样本的 sanity 结果，不能据此宣称生产级中文 OCR 质量。**

## 4. 音频转写（FAIL — 明确缺口，`asr_results.json`）

- 输入：`fixtures/audio.wav`（普通话 espeak-ng 合成 11.875 s）。未把预期转写放进 prompt。
- `POST /v1/audio/transcriptions`（multipart，`model=qwen3.8-27b`）→ **HTTP 501**
  `{"code":501,"message":"The current model does not support audio input.","type":"not_supported_error"}`
- `POST /v1/chat/completions`（`input_audio` part）→ **HTTP 500**
  `"audio input is not supported - hint: if this is unexpected, you may need to provide the mmproj"`
- 判断：**该服务当前没有可用的 ASR 后端 / 音频 mmproj**。已装生成模型 `qwen3.8-27b`（已测）与 `gemma4-mtp`
  （未测，metadata 亦为 text+image）均未声明音频；唯一声明 audio 的是 embedding 模型
  `embeddinggemma-2-Q8_0`，前序探针已证其在该路由报 “does not support logits computation”。
- **中文转写未测出结果（无后端）**；未伪造转写、未下载/部署 Whisper 或 reader。`docs/audio.md` 为
  **失败记录**，正文明确“未提取”，且**故意不内嵌 ground truth**以免被误当提取结果。

## 5. Markdown / 索引 / 检索（`docs/`, `index.json`, `index_tests.json`）

- 记录（合法 YAML frontmatter，`record_type: probe_source_record`，明示“非产品 schema、非产品新 schema”）：
  `docs/doc_image.md`（success）、`docs/doc_pdf.md`（success）、`docs/audio.md`（failed）。
  字段含 `id / source_ref / source_sha256 / media_type / extractor_model / extractor_method /
  extraction_status / generated_at_utc / locator(page/time) / http_status / usage / ground_truth_ref`。
  正文为**真实提取文本**（非 ground truth 替代）。
- 索引：`index.json`（`lg-probe-inverted-v1`），本地 JSON 倒排（CJK 单字+双字、ASCII 词），
  候选 token 并集 + 归一化子串校验；**状态/权限仍读文件，索引只是缓存**。
- 检索示例（命中回指 md 行 + 源文件 + 页/时间 locator）：

| 查询 | 命中 | 回指 |
|---|---|---|
| `服务`（跨材料） | `doc-image-001` 行 7；`doc-pdf-001` 行 7 | `fixtures/screenshot.png` / `fixtures/scanned_page-1.png` page 1 |
| `LG-2026-1015-007` | `doc-image-001` 行 4 | 截图 |
| `8,765.42` | `doc-image-001` 行 6 | 截图 |
| `25337000000098765432` | `doc-pdf-001` 行 4 | 扫描页 page 1 |
| `紫水晶矩阵`（负对照） | 0 | — |
| `紫水晶项目`（词元重叠反例） | 0 | — |

- 诚实记录：首轮**仅 token 并集**时 `紫水晶项目` 因共用 token `项目` 误命中 1 条；加入归一化子串校验后为 0。

## 6. 向量缓存（可选步骤，已真实执行）

- `POST /v1/embeddings`，1 次批量 5 输入，`model=embeddinggemma-2-Q8_0`，768 维、finite、L2=1.0，0.076 s。
- 缓存 `embeddings.npy`（完整向量）+ `embeddings.json`（每项仅前 8 维，避免打印完整向量）。
- 余弦（`embed_summary.json`）：

| 比较 | cos | 方向 |
|---|---|---|
| 语义查询“多久之内必须给出回应” vs doc_image / doc_pdf | 0.657 / 0.609 | 命中 doc_image（含“三个工作日内确认”）✓，**但余量小** |
| 精确编号 vs doc_pdf / doc_image | 0.725 / 0.678 | 命中 doc_pdf ✓ |
| 负对照 vs doc_image / doc_pdf | 0.568 / 0.578 | 最低 ✓ |

- 说明：语义余量小（0.048），仅 sanity，不构成检索质量结论。

## 7. 可重建性与过期 hash 拒绝（`index_tests.json`）

- 仅删除临时缓存 `index.json` 并重建：`postings_and_docs_identical=true`、
  `all_source_hashes_unchanged=true`、`query_results_identical=true`（原件/MD 未删）。
- 过期 hash：在 `stale_test/` **临时副本**（原件未动）中改动复制的 `screenshot.png` 后，
  `doc-image-001` 命中 `accepted=false, stale_hash=true`（拒绝原因：recorded source_sha256 ≠ 当前 hash）；
  `doc-pdf-001` 仍 `accepted=true`。**真实执行，非仅设计。**

## 8. HTTP / 预算计数（`http_log.jsonl`, `budget_counters.json`）

- 目标服务 HTTP 合计 **7**（上限 24），推断生成/OCR/ASR/embedding POST 合计 **5**（上限 10）。
- 明细：

| # | 请求 | 状态 | 耗时 |
|---|---|---|---|
| 1 | GET /v1/models | 200 | 0.010 s |
| 2 | GET /props | 200 | 0.001 s |
| 3 | POST /v1/chat/completions（OCR 截图，含首载） | 200 | 162.247 s |
| 4 | POST /v1/chat/completions（OCR 扫描页） | 200 | 21.799 s |
| 5 | POST /v1/audio/transcriptions | 501 | 0.020 s |
| 6 | POST /v1/chat/completions（input_audio） | 500 | 0.023 s |
| 7 | POST /v1/embeddings（batch5） | 200 | 0.076 s |

- 失败仅第 5/6 条（音频，预期负向）；无重试、无换模型重试；无请求触及 5 s 连接 / 45 s 常规读取上限；
  首载 162.247 s < 180 s 硬界。总真实探针约 5 分 12 秒 < 12 分钟。
- 未读取 `.env`，未打印凭证、完整向量或 base64（`embed_raw_response.json` 含向量但仅本地存档、不打印到报告）。

## 9. 未达到 / 最小补齐工作

1. **音频转写（未达）**：需服务端安装音频能力的 ASR/omni 模型（或为生成模型提供音频 mmproj）后，
   以 multipart + 已知转写重测；不得由本探针下载/部署。
2. **OCR/检索质量（未验收）**：仅 2 份干净合成样本，CER=0 **不能**外推生产质量；需真实/多样中文样本与
   标注集，并有独立基线。
3. **语义检索（弱证据）**：语义查询余量小；需更大样本评估。
4. **PDF 覆盖**：本轮为单页栅格 PDF；多页/混合版式、表格、低质量影印未测。
5. **未接产品**：frontmatter 明示为 probe 记录，非产品 schema；未做字段/层级人工校订，未进入产品管线。

## 10. 产物索引（本目录，`/tmp/lightgravity-media-text-index-20261015/`）

`PROGRESS.md`、`REPORT.md`、`fixtures_manifest.json`、`ground_truth/{doc_image,doc_pdf,audio}.txt`、
`fixtures/{screenshot.png,scanned.pdf,scanned_page-1.png,audio.wav}`、`docs/{doc_image,doc_pdf,audio}.md`、
`index.json`、`index_tests.json`、`embeddings.npy`、`embeddings.json`、`embed_summary.json`、
`ocr_metrics.json`、`ocr_*_raw_response.json`、`ocr_*_extracted.txt`、`ocr_*_summary.json`、
`asr_results.json`、`http_log.jsonl`、`budget_counters.json`、`live_v1_models.json`、`live_props.json`、
生成/测试脚本 `make_fixtures.py`、`svc_client.py`、`run_discovery.py`、`run_ocr.py`、`metrics.py`、
`build_docs.py`、`index_lib.py`、`run_index_tests.py`、`run_asr.py`、`run_embed.py`，以及 `stale_test/`（沙箱副本）。

**状态：隔离原型验证完成；未改产品、未提交、未发布、未安装新功能。**
