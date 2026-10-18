---
title: "LG-235 Google 原生音频转写接口冻结（1.22.0 候选）"
doc_type: contract
category: engineering
updated: "2026-10-18"
---

# LG-235 Google 原生音频转写接口冻结

状态：**接口/原型完成，未实现产品后端/UI，未部署**。规范正文是 [docs/08 §23](../../../docs/08-interface-contract.md)；本文件给 LG-236/237/238 的并行契约摘要与冻结字段。源码 `CONTRACT_VERSION` 仍为 `1.21.0`；LG-238 在公共 backend runtime 实现并装配后才升 `1.22.0`。

## 1. 范围与不变量

- 用官方 Gemini **原生** audio REST（`POST https://generativelanguage.googleapis.com/v1beta/interactions`）做英文小文件转写；**不是** OpenAI 兼容 chat/transcriptions 代理。
- 替代本轮 demo 的 EG2/Reader 远端帧桥接，但**不删除、不改判**旧 Reader 质量 FAILED；旧 provider 与字段保持。
- Google 模式不得 import `torch`/`numpy`/`transformers`/Reader，不调用本机编码器、模型容器、`192.168.8.12`、Files API 或云资源；不要求 Google SDK（标准 HTTP/httpx 足够）。
- 不新增实时麦克风、说话人/词级时间戳、通用 ASR 平台、自动模型轮换或静默 fallback。
- 产品调用次数不设新上限；保留计数/usage/latency、超时、取消、并发容量与每 job 一次 ASR 尝试。

## 2. provider 判别与旧配置

存储 `settings/ENGLISH_ASR.md` 的 `english_asr` 块加性新增 `provider`：

| 存储块 | 解析 |
|---|---|
| 无 `provider`（1.20 旧块） | `provider="eg2-reader"`, `runtime="inprocess"`，旧字段原义 |
| `provider="eg2-reader"` | 同上；`runtime` 只能 `inprocess` |
| `provider="google-native"` | `runtime="google-native"`（可省略，不得为其他值） |
| 未知/不匹配 | `422 validation_failed`，不猜测/回退 |

旧 `model_dir`/`reader_dir`/`device`/`threads`/`max_audio_seconds=1..30` 保留给 legacy；Google 模式不得要求或写这些字段。切换 provider 不自动重处理旧资料，旧 machine 正文/receipt 保持自己的 provenance。

冻结常量/无行为 helper：`backend/lightgravity/asr/provider_contract.py`。前端类型：`frontend/src/api/googleAsr.ts`。236 只可加性扩展，不改义；237 使用已冻结的导出名/语义。

## 3. 设置视图（GET）

`GET /settings.english_asr` 保留 §21.3 全部字段，加性新增：

```json
{
  "provider": "google-native",
  "runtime": "google-native",
  "model": "gemini-3.8-flash",
  "base_url": "https://generativelanguage.googleapis.com/v1beta",
  "credential_configured": true,
  "models": {},
  "limits": {
    "max_audio_seconds": null,
    "max_audio_bytes": 10000000,
    "max_request_bytes": 20000000,
    "timeout_seconds": 180,
    "max_concurrency": 1
  }
}
```

- 旧块视图补 `provider:"eg2-reader"`、`model:null`、`base_url:null`、`credential_configured:false`；旧字段/legacy limits 不变。
- 不返回 `credential_ref`/`credential_value`/API key/请求头/正文/音频/本地路径。`models` 为空：托管模型不伪造 revision/SHA/license。
- `language:"en"` 是配置的英文主线，不是语言识别结论；`timestamps_supported:false`。
- Google 视图 reasons 加性：`credential_missing`、`model_unavailable`；旧 reasons 保持。

## 4. 受保护写入（PUT）

`PUT /settings/english_asr` 继续使用既有管理员/受保护写、Host/Origin、`expected_revision`（取 `english_asr.revision`，不是全局 revision）。

Google payload：

```json
{
  "expected_revision": 3,
  "enabled": true,
  "provider": "google-native",
  "runtime": "google-native",
  "model": "gemini-3.8-flash",
  "base_url": "https://generativelanguage.googleapis.com/v1beta",
  "credential_ref": "<write-only ref>",
  "credential_value": "<write-only secret>",
  "timeout_seconds": 180,
  "max_audio_bytes": 10000000
}
```

- `model` 默认 `gemini-3.8-flash`，安全 id 模式 `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`。可显式改用其他原生模型；不得自动探测/切换。`gemini-3.5-transcribe` 仅为官方专用模型，LG-235 未调用、未假定启用。
- `base_url` 默认 `https://generativelanguage.googleapis.com/v1beta`；仅接受 https、无 userinfo/query/fragment、host 精确 `generativelanguage.googleapis.com`、port 缺省或 443、path `/v1beta`（可带尾 `/`）。拒绝 `/v1beta/openai`、http、其他 host/代理。
- `credential_ref`/`credential_value` 为 write-only，写入既有受控 `FileSecretStore`；省略表示保留；首次 enable 必须有可解析秘密或同时提供新值。显式 `null`/空串 -> 422；无删除/回显。
- **产品不得读取 `LG_GOOGLE_ASR_API_KEY` 或任何环境变量作为 Google 产品凭证**；该变量仅 LG-235 探针使用。DeepSeek/OpenAI 开发凭证不得成为产品 Google 凭证。
- Google 模式 `model_dir`/`reader_dir`/`device`/`threads` 不得出现；`max_audio_seconds` 省略或 `null`（数字 -> 422）。`max_audio_bytes` 默认 10,000,000，范围 1..14,000,000；`timeout_seconds` 默认 180，范围 30..600；`max_request_bytes=20,000,000` 只读；`max_concurrency=1` 为本地容量。
- 保存只做校验，**不请求网络、不验证 key、不加载模型、不推理、不改资料/不自动重处理**。保存成功不等于 Google 可用。

## 5. 可用性语义

- Google `configured=true`：model/base_url 有效且秘密存储有可解析凭证。
- Google `available=true`：enabled + configured + 无配置错误。表示**可以尝试**，不表示 key/model/网络已验证；只有 source receipt 成功与正文证明单文件成功。
- `credential_configured=true` 只表示秘密存在，不代表有效。UI 文案应写 “native Google transcription configured; capability not verified”，不得写 verified/connected。
- `capabilities.english_asr` 继续是处理可用性（attemptable），不新增 Google health 字段。Google 模式不要求 torch/numpy/Reader import。
- legacy `configured`/`available`/`reason` 语义不变。

## 6. 原生请求/响应

```json
{
  "model": "gemini-3.8-flash",
  "input": [
    {"type": "text", "text": "<fixed prompt>"},
    {"type": "audio", "data": "<base64>", "mime_type": "audio/wav"}
  ]
}
```

- 端点 `<base_url>/interactions`；认证仅 `x-goog-api-key` 请求头。禁止 key 进入 query/URL/日志/错误/事件/receipt/前端/提交。
- 固定 prompt（`prompt_version=google-native-transcribe-v1`）：`Transcribe the speech in this audio verbatim. Return only the plain transcription text, with no commentary, labels, or formatting.` 不含答案/人名/地名/数字/词表提示；不能按样本改 prompt。
- 仅支持明确音频 MIME（WAV/MP3/AIFF/AAC/OGG/FLAC/WebM 等）；未知 MIME 发送前失败。
- 双重预检：原始 `<= max_audio_bytes`；序列化 JSON body（含 base64、prompt、JSON 开销）`<= 20,000,000` 字节。超限不发送、不产生 provider usage。base64 约 4/3 膨胀。
- 不使用 Files API/远端文件生命周期；本路径仅 inline。
- 响应只读最终 `steps[type="model_output"].content[type="text"].text`，忽略 `thought` step/signature；按内容顺序换行连接并 trim。模型 commentary/label 原样作为**不可信 machine 正文**，不静默删行/改写。
- 200 但 `status!="completed"`、无 model_output/text、结构非法 -> 失败；不重试、不换模型/供应商、不 fallback 到 GenerateContent/OpenAI/专用 ASR/本地 Reader。
- `usage` 记录 total/input/output/thought 等非秘密计数；缺失为 `null`，不得当 0。`latency_ms` 记录真实耗时。

## 7. 错误、超时与未知停止

| 条件 | status / reason | stop_confirmed | 重试 |
|---|---|---|---|
| 未启用 | unavailable / `asr_disabled` | true（未发） | 否 |
| 无凭证/秘密不可解析/配置无效 | unavailable / `asr_unavailable`（视图 `credential_missing`/`invalid_config`） | true（未发） | 否 |
| 预检 MIME/大小/请求体超限 | failed / `asr_invalid_request` 或 `audio_too_long` | true（未发） | 否 |
| 401/403 | unavailable / `asr_auth_failed` | true（已响应） | 否 |
| 404/模型不可用 | failed / `asr_model_unavailable` | true | 否 |
| 429 | failed / `asr_rate_limited` | true（已响应） | 否 |
| 400/413/422 | failed / `asr_invalid_request` | true | 否 |
| 5xx | failed / `asr_provider_unavailable` | true（已响应） | 否 |
| DNS/TLS/连接建立失败（未发 body） | failed / `asr_provider_unavailable` | true | 否 |
| 发送后超时/取消/断连 | extracting / `asr_stop_unconfirmed`；job `recovery_required` | **false** | 否 |
| 200 显式拒绝/安全阻断 | failed / `asr_refused` | true | 否 |
| 200 空正文 | failed / `asr_empty_response` | true | 否 |
| 200 结构非法/非 completed | failed / `asr_response_invalid` | true | 否 |

- 发送后超时/取消不证明远端已停止：不写终态/部分正文，不自动/手工重放，迟到响应丢弃，直到真实停止确认。
- 每个 intake job 仍最多一次 ASR 尝试；失败也是尝试并计数。`reprocess` 是新的显式 attempt，不是自动重试。
- 401/429/模型不可用/协议失败必须如实报告并停止；不自动重试/换模型/换供应商。旧 Reader 不是 Google 失败的自动 fallback。

## 8. 来源/回执/索引

沿用 §20/§21 的摄取、持久化、索引、权限、正式校订生命周期。`machine` 加性形状：

```json
{
  "engine": "google-native",
  "provider": "google",
  "model": "gemini-3.8-flash",
  "runtime": "google-native",
  "endpoint_host": "generativelanguage.googleapis.com",
  "endpoint_path": "/v1beta/interactions",
  "prompt_version": "google-native-transcribe-v1",
  "model_version": "google-native:gemini-3.8-flash",
  "content_variant": "machine",
  "generated_at": "2026-10-18T00:00:00Z",
  "audio_sha256": "sha256-hex",
  "mime_type": "audio/wav",
  "audio_bytes": 333332,
  "request_bytes": 444500,
  "latency_ms": 6078,
  "usage": {"total_tokens": 320, "total_input_tokens": 287, "total_output_tokens": 33}
}
```

- Google 没有 `encoder`/`reader`；不得伪造。`timestamps:null`；`detected_language` 不声明，`language:"en"` 仅英文主线配置。
- machine 正文为不可信派生，不覆盖 formal；`model_version` 参与派生键；配置/model/prompt 变化不追溯改写旧正文。
- 词法/可选文本 embedding/Files/Chat/检索/选材/撤销/归档/删除/Team-Personal 隔离复用既有实现；失败不产生正文/索引，但不阻断原件/词法/直接音频向量。

## 9. 计数、用量与无限边界

- 不新增 Google 专用调用次数上限；保留计数/usage/latency/超时/取消/并发。
- `max_asr_calls=1`/job 是既有每作业一次尝试语义，不是产品总上限；LG-230 的无限用量政策保留。
- 真正发送 HTTP 前计数；预检失败不发送、无 provider usage；响应 usage 非秘密记录，缺失为 `null` 非 0。
- LG-235 的两次样本请求不是产品预算/上限/长期承诺；不重复测试调用。

## 10. 文件归属（并行）

| owner | 文件/范围 | 边界 |
|---|---|---|
| **LG-235（已冻结）** | `docs/08` §23、`backend/lightgravity/asr/provider_contract.py`、`frontend/src/api/googleAsr.ts`、`probes/.../lg235/**` | 只冻结常量/类型/契约/原型 |
| **LG-236 后端** | `backend/lightgravity/asr/**`（config/service/router/settings_store + Google client/runtime；provider_contract 只可加性扩展）、`backend/lightgravity/sources/worker.py`、`backend/lightgravity/settings/service.py`、`tests/asr/**`、`tests/sources/**` 相关测试 | 实现 §3～§8；不改 app/bootstrap/health/constants/docs 版本/README/PROJECT（238 owner）；不改前端 |
| **LG-237 UI** | `frontend/src/**`（Settings 表单、`api/englishAsr.ts`、`api/googleAsr.ts` 加性使用、Files/Chat 回执、样式、前端测试） | provider-aware 表单、write-only 凭据、上传/回执/失败/历史；不改后端/app/bootstrap/docs 版本；不改冻结导出名/语义 |
| **LG-238 集成** | `api/app.py`、`api/bootstrap.py`、`api/health.py`、`contracts/constants.py`、`docs/08` 版本/状态、README/PROJECT、`tests/integration/**`、e2e 装配 | 串行装配；公共 runtime 实现后升 `1.22.0`；不改 236/237 内部语义 |

- 236/237 独立 worktree 并行，共享文件冲突由 238 串行解决。236 不修改前端，237 不修改后端/app。
- 保持公开 seam：`build_english_asr_service`、`build_english_asr_router`、`english_asr_capability`、`EnglishAsrService.transcribe(data, *, filename, cancel_check) -> AsrOutcome`；238 无需改 provider 分派即可装配。Google 细节放 `machine`/内部 client，不新增前端直连供应商 API。
- 237 读路径只用既有 `GET /settings` 的 `english_asr` 视图；写路径 `PUT /settings/english_asr`，`expected_revision` 取 `english_asr.revision`。

## 11. 版本与完成判定

- 本节是 **1.22.0 冻结候选**；LG-235 完成 ≠ 生产/用户验收。
- LG-238 只有在 236+237 串行装配、公共 runtime 真实实现、局部/类型/构建/契约检查完成后，才升 `CONTRACT_VERSION` 与 `/health.contract_version` 为 `1.22.0`，并同步 README/PROJECT/状态。
- 旧 Reader FAILED、§21 限制、LG-235 H2 字面 `thought`/WER/实体差异全部保留；Google 新路径单独报告。

## 12. 官方来源

访问日期 **2026-10-18**：

- <https://ai.google.dev/gemini-api/docs/audio>（native `/v1beta/interactions`，inline audio，20 MB 总请求上限，`gemini-3.8-flash`）
- <https://ai.google.dev/gemini-api/docs/generate-content/audio>（legacy GenerateContent 原生音频；本路径不采用）
- <https://ai.google.dev/gemini-api/docs/transcribe>（专用 `gemini-3.5-transcribe`；未调用、未假定启用）
