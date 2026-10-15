---
title: "LG-039 中文 ASR 验证 — 进度"
doc_type: probe-record
category: quality
status: complete
updated: "2026-10-16"
---

# LG-039 中文 ASR 验证 STATUS

## 预注册方案（固定后不改阈值）

- 目标：在已授权的唯一候选服务 `http://192.168.8.12:11434`（llama.cpp llama-server router
  `b11641-843e7dcc1`，**非 Ollama**）上，找出**真实可用**的中文 ASR 路径；不支持或不达标给明确负结论。
- 真实人声来源：优先项目内授权材料；本地无可用真实中文人声，麦克风采集设备不可用。
  备选：明确许可的公开来源小规模真实中文语音 + 真值（核实许可、固定 hash 与来源，单文件 ≤8MiB，
  合计 ≤15MiB）。**合成语音不作为质量结论**；embedding 向量、英语作者指标均不得作为中文转写证据。
- 判据（预注册，固定）：
  - 成功 = 得到真实中文文字转写，且与真值可算字符错误率（CER）；关键信息（编号/日期/金额）命中。
  - 质量门（LG-041 解锁条件）= 至少 1 个真实人声样本可产出可读中文转写，CER 可计算，且关键信息命中；
    覆盖口音/噪声/长音频/时间戳/中英混合的要求：**未取得覆盖不得声称质量门达标**。
  - 负结论条件 = 服务无任何模型/路由接受音频输入，或全部返回不支持/失败。
- 预算：服务只读 health/models ≤4 请求（已用 3）；推理 POST ≤6（含失败，零自动重试）；
  总音频 ≤90s；单 HTTP timeout ≤90s；并发 1。公开下载合计 ≤15MiB、单文件 ≤8MiB。
- 未达标时：不改阈值、不假 done、LG-041 不解锁；记录实质阻塞与具体缺材料。

## 已执行（截至记录时）

- 读取 AGENTS/agent/PROJECT/PROGRESS/BACKLOG/docs06/08/09/LG039/041、既有 probes（source-intake、lg033）。
- 服务只读核实（3 请求）：
  - `GET /health` → `{"status":"ok"}`。
  - `GET /v1/models` → 4 个模型：`bge-reranker-v2-m3-Q8_0`(text)、`embeddinggemma-2-Q8_0`
    (text/image/audio/video，embeddings-only，loaded)、`gemma4-mtp`(text/image，unloaded，有 mmproj)、
    `qwen3.8-27b`(text/image/video，loaded，无 audio)。
  - `GET /props` → role=router，build_info `b11641-843e7dcc1`，models_autoload=true。
- **关键事实**：全服务 4 个模型元数据中**无一声明同时具备音频输入且支持文本生成**：
  `embeddinggemma-2` 是 embeddings-only（`--embeddings`，无 logits）；
  `qwen3.8-27b` 无 audio 模态；`gemma4-mtp` mmproj 为 image，模态 text/image。
- 本地真实人声：仓库内唯一音频为合成 espeak-ng `audio.wav`（证据 B）；无 arecord/pulse，
  ALSA 采集设备不可用（`hw:0,0` 打不开），本机无法采集真实人声。

## 已完成

- 真实人声来源：Wikimedia Commons `File:Chinese language-1.ogg`，经 API 核实许可 **CC BY-SA 3.0**，
  真人朗读，1.44 MiB（≤8MiB），固定 sha256；已存 `evidence/`。
- 推理实测 5 次（全失败，零自动重试，并发 1）：
  - `gemma4-mtp` 转写 → 500 `model ... failed to load`（70.4s）；
  - `qwen3.8-27b` 转写 → 501 不支持音频；
  - `qwen3.8-27b` chat `input_audio` → 500 不支持；
  - `embeddinggemma-2` 转写 → 500 无 logits；
  - `bge-reranker` 转写 → 501 不支持音频。
- 结论：**该服务无任何可用中文 ASR 路径**，失败率 5/5=100%，无输出、无时间戳、CER 不适用。
- 最终报告：[REPORT.md](REPORT.md)。**LG-041 不解锁**（质量门无输出，未达标）。

## 成本与未知

- 服务只读 3 次（上限 4）、推理 POST 5 次（上限 6）；公开下载 1.44 MiB（上限 15MiB）。
- 未知：远端硬件规格、gemma4-mtp 加载失败根因（疑似 OOM/权重问题，未由服务显式给出，未猜测）、
  长音频/噪声/口音/时间戳质量维度（服务零输出，无法开始测试）。
