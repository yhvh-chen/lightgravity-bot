# probes/source-intake — 资料接入与检索方向证据入口

本目录是 **文档与证据** 归档，不是产品实现、测试或运行依赖。它为本轮
“资料接入与检索”方向落盘（新设计 [../../docs/09-source-intake-and-retrieval.md](../../docs/09-source-intake-and-retrieval.md)）
提供只读证据入口。

- **这是什么：** 两个既有隔离探针的原始报告、修正记录、指标 JSON、原始 OCR 响应、
  ASR 失败结果、必要合成 fixtures 与真实提取 Markdown 的**逐字节副本**，以及
  源→归档 sha256 清单 [evidence/MANIFEST.json](evidence/MANIFEST.json)。
- **这不是什么：** 不是产品 schema/API、不是已实现能力、不是前端/后端依赖、不是产品
  Python 3.12 venv 或 Antigravity adapter 接入证据。
- **未做的事：** 未改产品代码/依赖，未新增 API/enum，未升级 `CONTRACT_VERSION`，
  未跑任何新模型请求，未新增 backlog 任务或改任务状态，未提交或发布。
  `/tmp` 原始探针目录原样保留，本目录只读取复制。

## 1. 归档清单与源→目标

逐条源路径、目标路径、字节数与 sha256 见 [evidence/MANIFEST.json](evidence/MANIFEST.json)
（`verification.all_byte_identical=true`、`entry_count=28`、`total_archived_bytes=952781`、
`under_3mb=true`）。`/tmp` 源文件字节与归档一致，未改写。

| 来源目录（只读） | 归档目录 | 关键内容 |
|---|---|---|
| `/tmp/lightgravity-eg2-endpoint-20261015/` | [`evidence/eg2-endpoint-20261015/`](evidence/eg2-endpoint-20261015/) | `REPORT.md`、`PROGRESS.md`、`DOC_CORRECTION.md`、`results_text.json`、`results_mm.json`、`results_followup.json` |
| `/tmp/lightgravity-media-text-index-20261015/` | [`evidence/media-text-index-20261015/`](evidence/media-text-index-20261015/) | `REPORT.md`、`PROGRESS.md`、`ocr_metrics.json`、`index_tests.json`、`embed_summary.json`、`http_log.jsonl`、`asr_results.json`、`fixtures_manifest.json`、原始 OCR 响应/提取文本、`docs/*.md`、`fixtures/*`、`ground_truth/*` |

归档按原目录结构镜像到 `evidence/<源目录名>/<相对路径>`；脚本、`__pycache__` 与权重未归档。

## 2. 证据事实（与原始报告一致）

### 2.1 EG2 端点探针（证据 A）

- 目标 `http://192.168.8.12:11434` 是 **llama.cpp `llama-server` router `b11641-843e7dcc1`**，
  不是 Ollama（`/api/version`、`/api/tags` → 404）。
- `embeddinggemma-2-Q8_0` 文本嵌入返回 **768 维**、有限、L2=1.0，与元数据 `n_embd=512` 不一致，
  报告以实测 768 为准。
- 图片/音频/视频字节被真实消费；**不同有效媒体内容改变向量**（第二张图 cos 0.888551、
  第二段音 cos 0.978952，见 `evidence/eg2-endpoint-20261015/results_followup.json` 与原始
  `REPORT.md`）。这是**输入消费**证据，不是识别/语义质量结论。
- `n_params=271002648` 最可能是**文本骨干**，另有单独 `mmproj`；别名 `embeddinggemma-300m`
  不构成“旧模型改名”的证据；checkpoint 出处**未做 hash 验证**，身份仍 `unknown`。
- 转写：该 embedding 模型在 `/v1/audio/transcriptions` 报
  `the current context does not support logits computation`，**只有一个模型在这条路由上失败**。

### 2.2 媒体成文/索引探针（证据 B）

- `qwen3.8-27b` OCR 两张干净合成中文图（截图 + 无文字层单页扫描 PDF 渲染页）：
  NFKC 去空白后 76/87 字符，**CER 0**、编号/日期/金额/发票号/价税合计字段精确命中。
  首请求含 router 自动加载 **162.247 s**，第二请求 **21.799 s**。
- 目标服务 HTTP **7** 次，其中推理 POST **5** 次（上限 10）；未读 `.env`、未打印凭证。
- 中文音频（espeak-ng 合成，22050 Hz 单声道，**11.875 s**）：
  `/v1/audio/transcriptions` → **501**、chat `input_audio` → **500**。
  **`gemma4-mtp` 未测**，无 reader/ASR 接线证据；**不能断言整台服务器不具备 ASR**。
- 产物：2 份成功 MD + 1 份失败记录（失败记录不内嵌 ground truth，避免被当成提取结果）。
- 词法索引：精确词命中、负对照 0 命中；删除缓存重建后 postings/docs/查询一致、源 hash 不变；
  沙箱副本改源文件后过期命中被拒（`stale_hash=true`）。
- 向量缓存：单次 batch5，`embeddinggemma-2-Q8_0`，768 维；语义排序**余量仅 0.048**，
  报告明确它**不是**检索质量结论。

### 2.3 范围澄清（原始报告未改写）

原始报告保留原字节。为避免把有限论断读成全局结论，证据入口明确：

> **已测 Qwen 的中文截图/扫描页 OCR 成功；已测 Qwen 的 ASR 路由（`/v1/audio/transcriptions`
> 501、chat `input_audio` 500）拒绝；已测 embedding 模型转写失败；`gemma4-mtp` 等其它生成模型与
> reader 接线未测。** 两轮探针都未证明整台服务无转写能力（**不能断言整台服务均无 ASR**）、
> 未证明生产级 OCR/语义质量，也未证明多模态识别质量。

## 3. 局限

- 样本为**合成、无隐私**小样本；CER 0 不能外推生产质量；语义余量小。
- 原型运行在**系统 Python 3.14 + 临时脚本**，不是产品 `Python 3.12` 依赖验收，
  也不是 Antigravity adapter/后端接入；探针未与产品代码互相 import。
- 单页栅格 PDF；多页/混合版式/表格/低质量影印未测；Office 未测。
- LAN 端点只作为**一次性只读探针目标**记录，**不是运行默认或产品依赖**；新设计不依赖该地址。
- 归档为证据，不构成产品 schema/API；上传/摄取/检索接口在实现前须冻结并按
  [docs/08 §13](../../docs/08-interface-contract.md) 变更控制升版。

## 4. 本轮文档范围

- 新增设计：[docs/09-source-intake-and-retrieval.md](../../docs/09-source-intake-and-retrieval.md)
  （方向已确认、待实现；API/schema 未冻结）。
- 入口与契约同步：`README.md`、`docs/01`、`docs/02`、`docs/04`、`docs/05`、`docs/08`、`agent.md`。
- 检查记录：[DOC_CHECKS.md](DOC_CHECKS.md)。
- 不改 `design.md` 视觉 tokens，不改 `CONTRACT_VERSION`，不新增 API/枚举/事件/状态，
  不改现有端点语义，不改 backlog 任务与状态，不写 `PROJECT.md`。

## 5. 复核归档

```bash
python3 - <<'PY'
import hashlib, json
m = json.load(open("probes/source-intake/evidence/MANIFEST.json"))
assert m["verification"]["all_byte_identical"] and m["verification"]["under_3mb"]
for e in m["entries"]:
    h = hashlib.sha256(open(e["target"], "rb").read()).hexdigest()
    assert h == e["sha256"], e["target"]
print("manifest ok:", m["verification"]["entry_count"], "entries,", m["verification"]["total_archived_bytes"], "bytes")
PY
```
