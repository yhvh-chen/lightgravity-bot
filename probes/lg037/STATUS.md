---
title: "LG-037 可选多模态向量索引 — 进度"
doc_type: probe-record
category: quality
status: in-progress
updated: "2026-10-15"
owner: agent:pi-lg037
base: dda78f2
---

# LG-037 STATUS

## 结论（截至本记录）

- **实现完成，机制/降级以替身向量验证通过；真实检索质量未验证（服务不可达），任务保持 `in-progress`，LG-040 不解锁。**
- 不声称图片/PDF 检索质量通过；LG-035 真实中文/表格 OCR 质量门仍阻塞，本包不夸大。

## 依赖与基线核实（真实完成）

- 基点 `dda78f2`（claim commit，`dev/lg037`，与 LG-038 同基点）。
- **LG-033 `done`**：docs/08 由 1.5.0 → 1.6.0 加性冻结 `source`/`intake_job`、`sources`/`intake`/`search`/`inbox`、
  `source.*`/`intake.*` 事件、`source_conflict`/`source_stale`/`index_unavailable`；已核实。
- **LG-036 `done`**（第五批集成 owner 解除装配阻塞）：`GET /api/v1/search` 在真实默认 app 返回 200，
  词法缓存/回源核对/授权过滤已实装；`pytest` 693 passed、mypy 130 files clean（其集成记录）。已核实。
- LG-035 仍 `in-progress`（真实 OCR 质量门阻塞，端点不可达+无许可样本）；LG-039 `done`（ASR 负结论）。

## 服务可达性（真实，只读，单次，不重试）

- 授权候选 `http://192.168.8.12:11434`：
  `curl -sS --connect-timeout 5 .../health` → HTTP `000`，
  `curl: (7) Failed to connect to 192.168.8.12 port 11434 after 3069 ms: Could not connect to server`，exit 7。
  证据 `reports/endpoint_reachability.txt`。**与 LG-035 最近两次 `No route to host` 一致**。
- 因此**不产出任何新的真实质量指标**（Recall@k/排序/负误命中）；预注册计划见 `PLAN.md`（调用前冻结）。
- 未连续探测、未擅自换服务、未安装模型、未下载权重。**服务只读请求 1（≤3）、embedding POST 0（≤8）。**

## 已执行（真实命令与结果）

- 新增代码（owner 范围）：`backend/lightgravity/sources/vectors/**`（`embedder.py`/`index.py`/`service.py`/`__init__.py`）、
  `backend/lightgravity/api/vector.py`（**新增**路由模块，未改 `api/app.py`）。
- 新增测试：`tests/sources/vectors/**`（39 项：38 passed + 1 真实质量探针按授权跳过）。
- **局部检查**：`uv run mypy` → **135 files clean**；
  `uv run pytest tests/sources tests/api tests/contracts -q` → **171 passed, 1 skipped**；
  全量 `uv run pytest -q` → **728 passed, 5 skipped**（stash 对照基线 **690 passed, 4 skipped**，
  差额 `+38 passed +1 skipped` 即本包 39 项，无回归）。
- 未改 lexical 核心、`api/app.py`、现有 sources/API/client/前端、coordinator/settings/store/contracts、共享 docs。
  未推送/部署/发布。

## 真实 / 替身 / 未测（诚实区分）

| 类别 | 状态 |
|---|---|
| 机制真实（真实 `FileStore`+`create_app`+HTTP） | **已验证**：索引失效、权限作用域只收窄、维度/模型/hash/缓存版本记录、模型切换重建不混、删 cache 重建复现、失败诚实降级、媒体直嵌 |
| 向量输出 | **替身**（`FakeEmbeddingBackend`，确定性、无网络）；**非真实质量**，不作品质结论 |
| 协议代码路径 | 按 source-intake 探针的真实 llama.cpp 形状实现（文本 `input` 字符串；多模态 `input[].content[]` 的 `image_url`/`input_audio`），**但本包未对真实服务验证该形状**（不可达） |
| 真实检索质量（Recall@k/排序/负误命中/词法对照） | **未测**（端点不可达）；不输出新指标 |
| 图片/PDF/音频语义识别质量 | **未测**；embedding ≠ OCR/ASR，未从向量推断文字 |
| 中文 ASR | 不重复验证（LG-039 已负结论）；真实音频仅作媒体→向量输入 |

## 预算实耗

- 服务只读 1 / ≤3；embedding POST **0** / ≤8；零自动重试；并发 0（未发 POST）。
- 媒体输入 0 MiB / ≤10 MiB；真实音频 0s / ≤30s。
- 产品 worker / ASR / OCR 调用 **0**；新服务/下载模型 **0**。
- cost/tokens：**unknown**（未收到服务 usage；开发模型轮次与 token 无精确计数）。

## 待办 / 阻塞

- 真实质量需：端点恢复可达且模型可调用（或另行授权的 OpenAI-compatible embedding 端点）。
  届时按 `PLAN.md` 预注册指标运行 `tests/sources/vectors/test_real_quality.py`（`LG037_RUN_REAL_VECTOR=1`）。
- 集成接线（共享 search 组合/挂载）写入 `INTEGRATION.md`，由唯一集成 owner 串行处理；未自行改 `api/app.py`。
- LG-040 不解锁；未验收不置 done。
