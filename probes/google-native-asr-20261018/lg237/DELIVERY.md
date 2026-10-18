---
title: "LG-237 Google 原生 ASR 前端交付"
doc_type: report
category: engineering
updated: "2026-10-18"
---

# LG-237 Google 原生 ASR 前端交付

状态：**完成前端实现与局部检查；未做真实后端/浏览器集成，未部署/推送**。后端仍由 LG-236 并行实现，真实装配与浏览器验收留给 LG-238/LG-239。旧 Reader 质量 **FAILED** 历史保留，未提出 Google 质量 PASS 或线上可用声明。

## 1. 分支与提交

- worktree：`/home/yhvh/code/lightgravity-bot-worktrees/google-native-asr-ui-20261018`
- 分支：`dev/google-native-asr-ui-20261018`
- 起点：`39ab93963006a796222cfa358b0b12604a6c0494`（LG-235 冻结/探针提交；tree `8be97d7...`）
- 交付提交：`f17b0d1bb4319e07393a5a21f9a08983ba8d9ee4`
- 交付 tree：`5ee015b0e4ca06598198ae4723dd23466f13e77f`
- 提交后 worktree 干净；仅提交本任务拥有的 `frontend/src/**` 与 `frontend/tests/**`，未改后端、app/bootstrap/health/constants、docs 版本、README/PROJECT、任务状态、根 PM dirty 或线上服务。

## 2. 实现范围

### 2.1 类型与原有 client

- `frontend/src/api/englishAsr.ts`
  - 加性加入 `provider: eg2-reader | google-native` 与 `runtime: inprocess | google-native` 判别。
  - `EnglishAsrSettingsView` 加性接受 `provider`、`model`、`base_url`、`credential_configured`；旧 1.20 无 `provider` 块按 `eg2-reader` 处理。
  - `EnglishAsrLimits.max_audio_seconds` 允许 `null`，并加性接受只读 `max_request_bytes`。
  - `EnglishAsrUpdateInput` 加性支持 Google `provider`/`runtime`/`model`/`base_url`/write-only `credential_ref`/`credential_value`；旧 legacy 字段仍可用。
  - 配置 reason 展示加性支持 `credential_missing`、`model_unavailable`。
  - 未新增读取/探测端点；继续只使用既有 `GET /settings` 与 `PUT /settings/english_asr`。

- `frontend/src/api/googleAsr.ts` 保持 LG-235 冻结导出名/语义不变；本任务只使用其默认值与边界常量。

### 2.2 Settings 表单

- `frontend/src/views/settings/EnglishAsrPanel.tsx`
  - 表单内明确显示 Provider，可在 **Google native audio** 与 **EG2 + Reader (legacy)** 间选择。
  - Google 模式只显示：Model（默认 `gemini-3.8-flash`）、Base URL（默认 `https://generativelanguage.googleapis.com/v1beta`）、write-only API key、timeout 与 audio-byte 限制。
  - Google 模式不要求/不写 `model_dir`、`reader_dir`、`device`、`threads`，不发送数字 `max_audio_seconds`；不展示 Reader/30 秒限制文案。
  - API key 使用 `type=password`；保存成功、关闭、Provider 切换及卸载时清空；失败保留输入供修正。没有 localStorage/sessionStorage/URL/日志写入。
  - PUT 使用嵌套 `english_asr.revision` 作为 `expected_revision`；空白 key 省略（保留已存 secret）；首次 Google enable 无已存 key 时前端先报普通校验错误、不发送 PUT。
  - 保存文案明确“configured / capability not verified”，不声称 Google key/model/网络已核实，不触发推理。
  - 迟到 save/reload 响应通过表单版本令牌隔离；表单已切换 Provider 时不把旧响应写回当前 secret/draft。
  - Legacy 表单保留原路径/hash/revision 语义；未重写旧 Reader 逻辑。

- `frontend/src/views/settings/SettingsView.tsx`
  - Settings 摘要按 Provider 展示：Google 显示 Model、Base URL、API key 存储状态（不验证）、audio/request/timeout/concurrency；不显示 Reader/Encoder pin。
  - Legacy 摘要仍显示原 Encoder/Reader pin 与 30 秒限制。
  - 保存通知区分 Provider，继续说明保存不运行转写。

### 2.3 Chat receipt / Files 展示

- `frontend/src/views/chat/ChatMaterialIntake.tsx`
  - Google machine provenance 显示为 “machine Google transcript · Google native …”，不再使用 in-process 表述。
  - `asr_stop_unconfirmed` 改为通用 “transcript provider may still be running”，同时适用于 Google/legacy。
  - 加性映射 Google 错误理由：auth、rate limit、model unavailable、provider unavailable、invalid request、refused、empty response、response invalid；不把失败显示为成功。
  - 原有 `asr_unavailable` 文案保持旧测试兼容。

- `frontend/src/views/files/FilesMaterialsPanel.tsx`
  - Google transcript 显示 “Machine Google transcript”/“Google native”。
  - provenance 加性展示 Provider、Model、Endpoint、Prompt version、Latency；Google 不伪造 Encoder/Reader pin。
  - 仍只读既有 machine content 端点；formal-first、correction、history、audio preview 语义不变。

- `frontend/src/api/types.ts`
  - `SourceTextMachineProvenance` 加性接受 Google provenance 字段；旧字段仍可选。

## 3. 实际检查命令与结果

均在 `frontend/` 下执行；临时从根 `frontend/node_modules` 链接依赖，检查后已删除链接，未提交。

| 命令 | 结果 |
|---|---|---|
| `npm run typecheck` | **exit 0** |
| `npx vitest run tests/lg237-google-asr-ui.test.tsx tests/lg161-english-asr-settings.test.tsx tests/lg161-english-asr-receipts.test.tsx tests/lg142-files-receipt.test.tsx tests/lg142-material-intake.test.tsx tests/chat.test.tsx tests/settings.test.tsx` | **7 files / 56 tests passed** |
| `npm run build` | **exit 0**；vite 128 modules，`dist/assets/index-DDU0pU3S.js` 453.46 kB，CSS 68.30 kB |
| `git diff --check`（提交前） | **通过**，无空白错误 |

新增 `frontend/tests/lg237-google-asr-ui.test.tsx` 覆盖：

- Google 表单字段、默认值、无 model/Reader 目录、无 30 秒/Reader 限制文案；
- 保存 payload：嵌套 revision、provider/runtime/model/base、write-only key、无 legacy 字段、成功后 key 清空且不进入 storage/URL；
- 空白 key 保留已存 secret（不发送 credential）；
- 首次 enable 无 key 时阻止 PUT；
- 表单切换 Provider 后迟到 save 响应不覆盖当前 draft/secret；
- team member 不读取管理员 settings、不显示表单；
- Google receipt/provenance 与失败理由；
- Files Google transcript 展示且无 Reader/Encoder pin。

测试输出中的 `act(...)` warning 来自既有 `lg142-material-intake`/`ChatBody` 测试路径，不是本次新增失败；相关测试通过。未运行完整前端套件、真实后端、浏览器或 E2E。

## 4. 未运行 / 限制

- **没有**真实 Google、产品、ASR、TTS、embedding 调用；没有使用真实 Google key。测试全部使用注入 fake client 与既有形状 fixture，不能当作真实端到端证据。
- 后端 LG-236 仍在并行实现；本 UI 按冻结 §23 类型编写，尚未与真实 `GET /settings.english_asr` / `PUT` 响应联调。真实字段缺失/差异由 LG-238 串行集成时处理。
- 无浏览器截图或 Playwright 验收；桌面/窄屏视觉、真实权限、上传回执与迟到网络行为留给 LG-239。
- 未改 README/PROJECT/docs 契约版本；源码 `CONTRACT_VERSION` 未升 `1.22.0`。
- 未部署、推送、release、创建 Cloud 资源，未触碰 8123/5173/18123、192.168.8.12、账号/数据/索引。
- 旧 Reader 独立质量门 FAILED、§21 限制、LG-235 H2 `thought`/WER/实体差异全部保留；Google 本任务不声明质量或生产可用。
- UI 只发送 write-only `credential_value`；`credential_ref` 类型保留但当前不暴露技术字段。无 secret 删除/回显/重新验证入口，符合冻结契约。
- 测试环境未安装新依赖、SDK、模型或 Torch；未新增前端依赖。

## 5. 给 LG-238 的接口要求

1. **保持 1.22 视图字段**：Google `GET settings.english_asr` 必须返回 `provider:"google-native"`、`runtime:"google-native"`、`model`、`base_url`、`credential_configured`，并保留 `revision`/`content_hash`/`enabled`/`configured`/`available`/`reason`/`language`/`timestamps_supported`/`limits`。旧块可省略 `provider`（UI 按 `eg2-reader` 处理）。
2. **保持 PUT 语义**：接受本 UI 的 Google payload（`expected_revision` 取嵌套 `english_asr.revision`；`provider`/`runtime`/`model`/`base_url`/可选 `credential_value`；无 legacy 目录/线程/数字 `max_audio_seconds`）。成功响应需包含完整 `english_asr` 视图，尤其 `provider` 与新的 `revision`，供表单继续保存。
3. **不要改变冻结导出**：`frontend/src/api/googleAsr.ts` 的导出名/默认常量语义不变；`EnglishAsrApi.update` 继续接受本任务扩展后的输入类型。
4. **真实装配后**再按 §23.11/§23.12 升 `CONTRACT_VERSION=1.22.0` 并同步 health/docs/README/PROJECT；本任务不拥有这些文件。
5. **错误体保持通用脱敏**：不要把 key、API URL query、音频 base64、底层协议细节返回前端；UI 只展示 `reason`/通用消息。
6. **保持既有边界**：不新增前端直连供应商 API、不上传新端点、不新增导航/面板；Google 失败不得自动 fallback 到 Reader。
7. **联调重点**：provider 缺失兼容、首次 enable/blank key 保留 secret、revision 冲突、Google 与 legacy 切换后的迟到响应、receipt `machine.provider/engine/runtime` 形状、Files/ Chat 的 Google 标题与错误理由。

## 6. 根目录状态

- 根 `/home/yhvh/code/lightgravity-bot` 的既有 PM dirty 文件、`main@cd0e8c8`、服务与数据未改；本报告是唯一新增的根 `probes/` 交付文件。
- 源实现仅存在于上述 worktree 分支提交；根目录未复制源码。
- 真实命令/退出码/提交/tree/限制均按上文记录；未把 fake fixture 写成真实 Google 成功。
