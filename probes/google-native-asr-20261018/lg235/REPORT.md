---
title: "LG-235 Google 原生音频原型与接口冻结报告"
doc_type: report
category: engineering
updated: "2026-10-18"
---

# LG-235 报告：Google 原生音频原型 + 1.22 契约冻结

状态：**完成接口冻结与受限真实原型；产品后端/UI 未实现，未部署**。旧 Reader 质量 **FAILED** 保持；本次 Google 结果单独报告，不构成生产质量或用户验收。

## 1. 分支与提交

- 工作树：`/home/yhvh/code/lightgravity-bot-worktrees/google-native-asr-contract-20261018`
- 分支：`prep/google-native-asr-20261018`
- 基点：Tasks 核心 `8d869fff6223b50a02085444ed9b87a7bd8c5003`（契约 1.21.0，独立 QA 已通过其范围）
- 精确机械合入（无冲突）：
  - LG-229 原提交 `dad742d7745267947246bd937e620d8dcdb049b3` → 本地 `8d3473e`
  - LG-230 原提交 `cd0e8c82d60b98abf6168bd4a9131e3fb3981415` → 本地 `539e622`
- 契约/共享类型提交：`8feff91478d08f861404c4aa6ce81d306bf6bfd1`（tree `2de0a8fd9c819ce3514857460fef413ba7dc8e02`）
- 本报告所在的交付提交是该提交的子提交（branch HEAD）；最终 HEAD/tree 在交付回复中列出。`git status --short` 在交付时为干净。
- 与 `main@cd0e8c8` 的差异仍完整包含 Tasks 1.21 的 57 文件增量；LG-229/230 未覆盖 Tasks 代码。未引入冻结远端 ASR `33b73b3`，未改根目录 PM dirty 文件、任务状态、账号或索引。

## 2. 官方来源（访问日期 2026-10-18）

- <https://ai.google.dev/gemini-api/docs/audio>：native audio；`POST https://generativelanguage.googleapis.com/v1beta/interactions`；inline `input[].data` base64 + `mime_type`；**20 MB total request**（含 prompt/全部文件）；`gemini-3.8-flash` 示例。
- <https://ai.google.dev/gemini-api/docs/generate-content/audio>：legacy `generateContent` native audio；本路径不采用。
- <https://ai.google.dev/gemini-api/docs/transcribe>：专用 `gemini-3.5-transcribe`；**未调用、未假定启用**。

## 3. 凭证与请求安全

- 仅使用 pi 进程继承的 `LG_GOOGLE_ASR_API_KEY`（运行前由受控环境映射，未打印/未落文件）。子进程用 `env -u DEEPSEEK_API_KEY -u OPENAI_API_KEY` 剥离开发凭证。
- key 只放在 `x-goog-api-key` 请求头；未进入 URL/query、文件、日志、报告、提交或响应记录。探针脚本只从环境读取，并在任何错误体输出前替换 key。
- 未写入根 `.env`、Settings、root source、`content/` 或任何产品配置。真实 Google 凭证不存仓库。

## 4. 原型方法与调用数

- 复用**既有** H1/H2 Piper 英文 WAV（`lg163` QA holdout），未生成新 TTS、未使用私有产品音频：
  - H1 `probes/english-asr-20261018/lg163/artifacts/tts/qa-h1-harbor.piper-ljspeech-high.16k.wav`，333,332 B，SHA-256 `e186594f70db78b4cbd9bb926beb72421bd5dfe3f7d2da4f1bba0a498663c740`
  - H2 `.../qa-h2-clinic.piper-ljspeech-high.16k.wav`，312,526 B，SHA-256 `b590b0ccb2df0cdf29012d79840ab7077c644190533d70d3cc0eecddde6702e6`
- 模型：`gemini-3.8-flash`；固定 prompt：`Transcribe the speech in this audio verbatim. Return only the plain transcription text, with no commentary, labels, or formatting.`（无人名/地名/数字/答案提示）。
- 调用：1 次 `GET /v1beta/models/gemini-3.8-flash` 元数据 + **H1 一次 POST + H2 一次 POST**；共两次推理，无第三次、无重试、无模型轮换、无 Files API、无 SDK。
- 首次 H1 POST 实际 HTTP 200，但第一版探针解析器只找 `output_text`，未读 `steps`，被误记为协议失败。**没有重发 H1**；保存的 H1 200 响应被重新解析，随后 H2 仅请求一次。首版记录保留在 `raw/attempt1-harness-parse-failure.json`。这是 harness 解析错误，不是 Google 协议失败。

## 5. 真实结果

| 项 | H1 | H2 |
|---|---|---|
| HTTP | 200 | 200 |
| 延迟 | 6.078 s | 7.221 s |
| 音频输入 tokens | 261 | 245 |
| text input tokens | 26 | 26 |
| total input | 287 | 271 |
| output tokens | 33 | 34 |
| thought tokens | 0 | 87 |
| total tokens | 320 | 392 |
| cache/tool tokens | 0 / 0 | 0 / 0 |

原始正文（未清洗；H2 的字面 `thought` 保留）：

- **H1**: `On April 9th 2027 the North Harbor market opens at 6:45 and the ferry to Cedar Island carries 38 passengers.`
- **H2**: `thought` 换行后 `Dr. Lina Ortiz will visit the Eastside clinic on November 12th to review 29 patient files and collect 17 samples before noon.`

模型元数据 `GET` 200：`models/gemini-3.8-flash`，displayName `Gemini 3.8 Flash`，`supportedGenerationMethods` = `generateContent`、`countTokens`、`createCachedContent`、`batchGenerateContent`（未列 `interactions`，但实际 `interactions` 200；作为观察记录，不据此改协议）。

完整原始响应/usage/状态：`raw/h1-response.json`、`raw/h2-response.json`、`raw/probe-report.json`、`raw/probe-summary.json`。

## 6. 质量比较（既有 normalizer，未改规则）

使用 `probes/english-asr-20261018/harness/normalize_wer.py` 原实现（同一规则套 reference/hypothesis；旧标签不改写）：

| 片段 | Google WER | 关键事实 | 缺失（normalizer 逐字） |
|---|---:|---:|---|
| H1 | **0.04000** | 5 / 6 | `April ninth`（输出为 `April 9th`；数字本身识别正确，现有 normalizer 不展开序数 `9th`） |
| H2 | **0.17391** | 3 / 5 | `Lena Ortiz`（输出 `Lina Ortiz`）、`November twelfth`（输出 `November 12th`；现有 normalizer 不展开序数 `12th`） |

H2 的 WER 还包含字面 `thought` 作为 1 次 insertion；若仅作观察、去掉该前缀则为 0.13043，但**交付的主判定仍用未清洗 raw 文本的 0.17391**，不把清洗后的值当正式结果。H2 保留了 `Eastside Clinic`、`twenty nine`、`seventeen`。

历史 Reader 对照（同一 H1/H2、同一 normalizer；旧 FAILED 保留）：

| 片段 | Reader WER | Reader 关键事实 | Reader 缺失 |
|---|---:|---:|---|
| H1 | 0.08000 | 5 / 6 | `Cedar Island` |
| H2 | 0.21739 | 3 / 5 | `Lena Ortiz`、`Eastside Clinic` |

结论：本次 Google 原型在 H1 找回 `Cedar Island`、在 H2 找回 `Eastside Clinic`，但 H2 仍有 `Lena`→`Lina` 与表面数字格式差异；**不是质量门 PASS**。旧 Reader 的 FAILED 判定、原始输出和限制不改写；Google 只代表这两条合成英文短样本的实测范围。TTS 输入是名义真值而非人工转写，不声称真人/口音/噪声/中文/多语/长音频/生产质量；时间戳与说话人未验证。

## 7. 契约冻结摘要

完整规范见 [`CONTRACT.md`](CONTRACT.md) 与 `docs/08 §23`；关键冻结项：

- provider：`eg2-reader`（旧块默认）↔ `google-native`；旧 `runtime=inprocess`/路径字段保持。
- 默认：`gemini-3.8-flash`；base `https://generativelanguage.googleapis.com/v1beta`；endpoint `/v1beta/interactions`；auth header `x-goog-api-key`。
- inline 20,000,000 total request bytes；raw audio default 10,000,000 / max 14,000,000；timeout 180（30..600）；concurrency 1；无 30 秒 Reader 伪限制。
- write-only `credential_ref`/`credential_value` 存既有 `FileSecretStore`；产品**不读环境 key**；GET 只返回 `credential_configured`。
- `configured`≠verified；`available` 只表示可尝试；单文件成功只由 receipt/正文证明。
- 错误：401/403 `asr_auth_failed`、429 `asr_rate_limited`、404/model `asr_model_unavailable`、5xx `asr_provider_unavailable`、400/413 `asr_invalid_request`、200 空/拒绝/结构错分别 `asr_empty_response`/`asr_refused`/`asr_response_invalid`；发送后超时/取消 `asr_stop_unconfirmed` + `recovery_required`；无自动重试/fallback/模型轮换。
- 响应只读 `steps[type=model_output].content[type=text].text`；忽略 thought；machine provenance 记录 model/endpoint/prompt_version/audio_sha/request_bytes/latency/usage，不伪造 encoder/reader/timestamps。
- 每 job 一次 ASR 尝试保留；产品不设新总用量上限；usage 缺失记 null 非 0。

共享代码：

- `backend/lightgravity/asr/provider_contract.py`：provider 常量、默认值、固定 prompt、错误 reasons、`select_provider()`；无网络/模型/凭证读取。
- `frontend/src/api/googleAsr.ts`：Google view/input 类型与默认值；types only，无网络客户端。
- `tests/asr/test_google_provider_contract.py`：旧块映射、Google 映射、非法组合、冻结默认值。

## 8. 检查与证据

在 worktree 运行，未跑全量/浏览器（按范围）：

- `uv run pytest -q tests/asr/test_google_provider_contract.py tests/asr tests/contracts/test_contracts.py tests/adapter/test_proxy.py tests/sources/vectors/test_embedder.py` → **32 passed**。
- `npm run typecheck`（临时链接根 `frontend/node_modules`，检查后移除，未提交）→ **通过**。
- `npx vitest run tests/lg161-english-asr-settings.test.tsx` → **7 passed**。
- `uv run python` 仅 import `provider_contract`：`torch_imported False`、`numpy_imported False`、`transformers_imported False`；Google 契约模块不做模型加载。
- `git diff --check` → 通过。
- 未跑完整后端套件、浏览器/E2E、真实产品上传或部署；这些留给 236/238/239，不能把本报告当版本 QA。

证据文件：

- `raw/probe_google_native.py`（可复现探针；默认复用已保存 H1 响应，只有缺失时才请求；请勿重跑造成新推理）
- `raw/probe-report.json`、`raw/probe-summary.json`、`raw/quality-holdout-google.json`
- `raw/h1-response.json`、`raw/h2-response.json`、`raw/h1-transcript.txt`、`raw/h2-transcript.txt`
- `raw/attempt1-harness-parse-failure.json`（首版解析错误，保留）
- `raw/SHA256SUMS`

## 9. 用量、费用与限制

- Google usage 已记录：H1 320 tokens、H2 392 tokens（明细见 §5）。**费用、配额余额、账户计划未知；未计为 0**。
- 两次样本请求是 LG-235 的受控测试计划，**不是**产品调用次数上限/预算；产品仍保留 LG-230 的无限用量与计数/用量/超时/并发。
- 未验证：专用 `gemini-3.5-transcribe`、长音频、Files API、人类/口音/噪声/中文/多语质量、时间戳/说话人、生产配额/并发、API 错误率。模型元数据未列 `interactions` 但实测可用；该差异保留，不推断其他模型/端点。
- 未部署、未推送、未 release、未创建 Cloud 资源、未改 8123/5173/18123、未调用 `192.168.8.12`、未改根服务/账号/数据/索引/PM dirty/任务状态。

## 10. 根目录状态（compact）

- 根 `/home/yhvh/code/lightgravity-bot` 的既有 dirty 文件、`main@cd0e8c8`、8123/5173/18123 服务与数据未改；未在根运行测试/服务。
- 所有新代码/契约/证据仅在本 worktree 分支提交。根 `docs/08` 的 PM dirty/1.20 部署事实未被覆盖；本分支 docs/08 保留 §18～§22 并新增 §23。
- 交付后 worktree 无未提交改动；最终 HEAD/tree 由交付回复的 `git rev-parse HEAD`/`HEAD^{tree}` 给出。
