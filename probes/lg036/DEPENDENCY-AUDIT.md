---
title: "LG-036 技术依赖核实（只读调查副本，不变证据）"
doc_type: evidence
category: engineering
updated: "2026-10-16"
scope: "只读调查副本；原文 /home/yhvh/lg036-dependency-audit-20261016.md，未被修改"
note: "本文件是只读技术调查的逐字副本，作为 PM 依赖校正的不变证据；依赖调整由主代理 PM 决定（checkpoints/2026-10-15/pm-decision-lg036-20261016.txt）。"
---

---
title: "LG-036 技术依赖核实（词法索引与来源核验）"
doc_type: audit
category: engineering
updated: "2026-10-16"
scope: "只读调查；不修改任务/代码/仓库，不调用模型服务"
---

# LG-036 技术依赖核实

调查者：pi 技术依赖核实执行者（DeepSeek env，无嵌套派工）。主代理 PM 决定依赖是否调整。

## 0. 结论（先给）

**可以独立实施，最小真实 depends_on = LG-033（已 done）+ LG-034（已 done，待版本 QA LG-040）。** LG-035（in-progress）不是 LG-036 的技术前置：LG-036 需要的是 `source` 记录 + 原件 + 内容哈希 + 权限/版本文件接口，这些由 **LG-033 契约 + LG-034 实现**已经交付并被真实测试覆盖；LG-035 的 OCR 质量门只影响"图片/PDF 派生正文这一条语料来源"，不影响词法索引的骨架、来源核验（hash/版本/权限）、失效与重建逻辑。

实现路径建议：以 **已在文件中落地的 source SoT + 已注册的 `/content`/`/download`/`/actions` 端点 + 新增 `/search`** 为接口面；对"暂无派生正文"的来源诚实地 `not_indexed` / 无可索引正文，不伪造正文、不把 OCR 质量门当作词法索引的前置。**但必须明确：LG-036 不因此宣称图片/PDF 检索质量已达标**——那是 LG-035 OCR 质量门与 LG-040 集中 QA 的范围。因此不降低 LG-040 硬门。

需要说明的一处缺口：**`GET /api/v1/search`（§4.3，LG-036）当前尚未注册**（`grep search backend/lightgravity/api/sources.py backend/lightgravity/api/app.py` 无命中，exit=1）。这正是 LG-036 自己要实现的端点，不是被阻塞项。其余 LG-036 会用到的读接口已实现。

## 1. 核实依据

### 1.1 任务与状态（只读）
- LG-036 `backlog/tasks/LG-036.md`：`status: todo`，`depends_on: ["LG-034","LG-035"]`；范围明确"先实现无需向量也能工作的资料查找与回源"；验收条件为派生索引（文件/元数据/正式内容）、命中回源核对存在/权限/版本/哈希、旧命中失效、删缓存可重建、损坏/处理中状态如实显示、不启动独立数据库。
  - 注：任务正文自述"LG-034、LG-035 为**接口或集成交付**依赖"——依赖性质是接口/集成，不是 OCR 质量验收。
- LG-033 `status: done`（契约冻结，契约 1.6.0）。
- LG-034 `status: done`（标注"待版本 QA（LG-040）"；集成装配已完成并经真实默认 app 路由验证）。
- LG-035 `status: in-progress`（OCR 质量门阻塞：真实中文页/表格真值缺、端点不可达；不 done）。
- LG-040 `status: todo`，`depends_on: ["LG-035","LG-036","LG-037","LG-038","LG-022"]`，是集中 QA 门，不由 LG-036 单独绕过。

### 1.2 已交付且可消费的接口（文件 SoT + 端点）
代码事实源：`backend/lightgravity/sources/**`（LG-034 + LG-035 落地，基点 `61fad69` / `faf7230` / `d7e4391`）。

- **来源记录结构**：`backend/lightgravity/sources/models.py` `class SourceRecord`（`content_hash`、`source_version`、`scope`、`origin`、`content_digest`、`etag`），字段与 docs/08 §6.6 冻结 schema 一致。
- **内容哈希（密码学）**：`backend/lightgravity/sources/store.py::persist_original` 返回 `hashlib.sha256(data).hexdigest()`；`intake.py::compute_content_hash` 计算原件内容哈希，`source_version` 仅在内容哈希变化时 +1（`update_source`/`SOURCE_VERSION_CHANGED`）。→ LG-036 回源核验所需的"存在/哈希/版本"可由文件与记录得到，与 OCR 无关。
- **stat 令牌 vs 内容哈希**：`store.py::persist_original` + `service.py::download_view` 同时给出 `stat_revision=f"{size}-{mtime_ns}"` 与 `content_hash`。docs/08 §6.6/§4.3 明确两者**严格区分**——LG-036 回源必须用 `content_hash`，不能把 stat 令牌当密码学哈希（契约已有明确语义）。
- **权限/范围**：`service.py::authorize_scope`、`_source_view`（暴露 `scope`、`content_hash`、`source_version`、`derivatives`、`formal`、`index`，且**不回显绝对路径**）；`store.py::resolve_inbox_path` 拒绝 `..`/绝对路径/逃逸符号链接。docs/08 §6.6 冻结"权限与归属只能在文件 SoT，检索只返回已授权候选且读取时回源核对"。
- **索引槽位（已冻结、待填写）**：source 记录含 `index: {lexical: not_indexed, lexical_hash: null, vector: disabled, vector_model: null}`（docs/08 §6.6），LG-036 直接写 `lexical`/`lexical_hash` 字段即可，无需新增 schema 语义。
- **正文语料来源**：`content.py::ContentStore` 提供 `read_formal()` / `read_machine_markdown(source_version)` / `read_pages()`；`service.py::content_view(kind=auto|formal|machine)` 已可读。`service.py::edit_formal` / `sources/{id}/formal` 端点已实现。→ LG-036 索引语料 = 正式版本优先、机器派生次之；两者都可从文件读，**读取接口不依赖 OCR 质量门**。
- **已有端点（app.py:230 已注册 `build_sources_router()`）**：`/sources`（POST/GET）、`/sources/{id}`、`/sources/{id}/receipt`、`/sources/{id}/content`、`/sources/{id}/download`、`/sources/{id}/actions`、`/sources/{id}/formal`、`/intake/jobs/{id}`、`/intake/jobs/{id}/actions`、`/inbox/messages`（见 `backend/lightgravity/api/sources.py`）。
- **未注册（LG-036 自己的交付物）**：`GET /api/v1/search`——代码中不存在，docs/08 §4.3 标为"冻结接口（未实现，向量可选）"，归属 LG-036。

### 1.3 已交付测试（真实运行，LG-034 记录）
`backlog/tasks/LG-034.md` 验证记录：`tests/sources/**` 21 项真实 HTTP+文件集成测试；`tests/api tests/contracts tests/store` 134 passed；装配后 `uv run pytest -q` 545 passed, 1 skipped；`mypy` 109 files clean。覆盖：原件先落盘、`request_id` 幂等/异 payload `source_conflict`、作用域内去重跨 Task 不并权限、内容 hash 变化才升源版本、取消需确认停止、中断不自动重放、重启 `recovery_required`、torn JSONL 修复、路径/符号链接逃逸 403、受控收件区不强建 Task、外部 frontmatter 不获得执行权限、**缓存可从文件重建**。
- 现存测试文件：`tests/sources/test_sources_api.py`、`test_intake_jobs.py`、`test_durability.py`、`tests/sources/ocr/**`（17 passed，见 LG-035 记录）。这些是 LG-036 可直接复用的 fixture/契约基础。

### 1.4 LG-035 阻塞的精确范围
`backlog/tasks/LG-035.md`：OCR 真实端点 `192.168.8.12:11434` `No route to host`（curl 000 / ping 100% 丢包），真实中文页/表格真值不可得，因此**不 done**。其代码面（`processing.py::ProcessingEngine`）只处理 `image/png|jpeg|webp|gif|bmp` 与 PDF（`can_process`），对不支持的媒体 `_finish_unprocessable` 诚实返回、不造正文。
→ 阻塞项是"图片/PDF → 高质量中文正文"的质量验收与授权端点，**不是** source/版本/哈希/权限接口，也不是词法索引骨架。

## 2. 是否可解耦（技术判定）

**可以解耦**，理由：
1. LG-036 验收条件逐条对应的是 **source SoT + 内容哈希 + 版本 + 权限 + 可重建缓存**，全部由 LG-033/LG-034 交付，且已有真实测试。
2. 词法索引对"语料"的最低要求是"可读的正式/派生正文"；`content_view`/`read_formal`/`read_machine_markdown` 已提供该通道，**索引逻辑不依赖 OCR 质量**——只依赖"有正文就索引、无正文就诚实 not_indexed"。
3. 真实边界建议（不降低 LG-040 硬门）：
   - **文本类来源**（上传的 `.md`/`.txt` 等）可作为 LG-036 的真实索引/回源/失效/重建 fixture：走完整接收→索引→查询→回源核对 hash/版本/权限→改内容使旧命中 `source_stale`→删缓存重建。
   - **图片/PDF 来源**：在 LG-035 质量门通过前，派生正文缺失/不可信时，LG-036 必须诚实标 `not_indexed`（或无正文），**不得**用低质 OCR 输出当检索证据，也不得用合成样本冒充质量通过。
4. LG-040 仍覆盖浏览器真实上传、OCR、检索回源、索引重建、并发/幂等、跨 Task 权限、损坏索引、词法降级——LG-036 独立实施不会削弱 LG-040 的集中质量门；反而为 LG-040 提供可复现的检索/回源/重建证据面。

## 3. 若接口不稳/尚缺的返回语义（如实）

- **`/search` 端点自身未实现**：这是 LG-036 的交付内容，不构成阻塞，但意味着"检索返回结构（命中字段、`source_stale`/`index_unavailable` 错误语义、游标/分页）"需按 docs/08 §4.3 + §6.6 冻结语义实现，不得自行扩展。
- **`index.lexical` 的写入与重建语义**：docs/08 §6.6 已冻结 `lexical: not_indexed|...`、`lexical_hash`、`source.indexed`/`source.invalidated` 事件。LG-034 记录明确这些事件"随 LG-035～038 实现"——即 `source.indexed`/`source.invalidated`/`source.deleted` 事件**当前尚未实现**，LG-036 落地时需一并实现，属 LG-036 范围，不属 LG-035 前置。
- **LG-035 的 `derivatives` 记录**：`processing.py::_record_derivatives` 已写入 `{kind, path, source_version, content_hash, model_version}`（与 §6.6 一致），但**仅在 OCR 成功路径产生**。质量门未过时该列表多为空 → 这正是建议对图片/PDF 来源诚实 `not_indexed` 的原因。
- **docs/08 §4.3 状态行更新**：契约表把 `/content`、`/download`、`/actions` 标为"冻结接口（未实现）"，但代码显示这些已由 LG-035 实现（`service.py::content_view/download_view/source_actions`，路由已注册）。这是**文档状态滞后**（LG-035 "集成 owner 待办"亦自述该行应更新），不影响解耦判断；建议由 docs08 单一 owner 在 LG-036 落地时随 §4.3 一并更正为"已实现（待版本 QA LG-040）"。

## 4. 最小真实依赖与真实边界（供 PM 判断）

- 最小真实 `depends_on`：**LG-033（done）+ LG-034（done）**。可选加"引用 LG-035 已交付接口 commit `faf7230`"，因 `/content`/`/download`/`/actions` 的 source 侧实现来自该 commit；但这属接口引用，不是质量前置。
- 建议 scope：实现 `/search`（词法优先、授权过滤、回源核对 hash/版本/权限）、可重建索引缓存、`index.lexical`/`lexical_hash` 写入、`source.indexed`/`source.invalidated` 事件、旧命中失效（`source_stale`）、删缓存重建；对无/不可信正文的来源诚实 `not_indexed`。
- 建议 fixture/真实边界：文本类来源端到端（真实 HTTP+文件）；图片/PDF 在 LG-035 质量门通过前不参与检索质量主张。
- **不会降低 LG-040 质量门的理由**：LG-040 已显式依赖 LG-035、LG-036，独立验收浏览器真实上传、OCR、检索回源、索引重建、并发/幂等/权限/降级；LG-036 独立实施只补齐检索骨架，OCR/检索**质量**结论仍由 LG-035 质量门与 LG-040 集中 QA 判定。

## 5. 未做与边界
- 未修改任何任务/代码/文档/仓库；未运行模型服务；未 push/deploy。
- 未重跑全量测试；引用的测试数字来自 LG-034/LG-035 已记录的真实运行证据。
- 命令证据：`grep -n "search" backend/lightgravity/api/sources.py backend/lightgravity/api/app.py` → 无命中（exit=1）；`app.py` 第 230 行已注册 `build_sources_router()`。
- 依赖调整由主代理 PM 判断；本文件仅为技术事实。

## 证据路径
- `backlog/tasks/LG-033.md`、`LG-034.md`、`LG-035.md`、`LG-036.md`、`LG-038.md`、`LG-040.md`
- `docs/06-roadmap.md` §6、§6.3；`docs/08-interface-contract.md` §4.3、§6.6、§13（1.6.0）；`docs/09-source-intake-and-retrieval.md` §7、§9
- `backend/lightgravity/sources/{models,store,intake,content,processing,service}.py`、`backend/lightgravity/api/sources.py`、`backend/lightgravity/api/app.py:230`
- `tests/sources/{test_sources_api,test_intake_jobs,test_durability}.py`、`tests/sources/ocr/**`
- git：`61fad69`（LG-034 装配）、`faf7230`（LG-035 OCR，in-progress）、`d7e4391`（LG-035 cohort B）
