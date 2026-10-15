# LG-038 — Chat/Files 资料统一体验：集成与受保护接入提案

状态：实施完成（待版本 QA LG-040）。本文件记录本轮**唯一新增前端接线模块**、
**无需改动的共享文件**，以及一项**交唯一 owner 决定的最小受保护接入提案**。
不扩大冻结 schema，不改 OCR/lexical/vectors 核心、coordinator/verify/adapter/store/settings、
`api/app.py` 与共享 docs/contracts。

## 1. 无需改动的共享装配（事实核对）

- `backend/lightgravity/api/app.py` 在 batch5 已挂载
  `build_sources_router()`（LG-034）与 `build_search_router()`（LG-036）。
  本轮**未修改** `api/app.py`。
- 因此 Chat/Files 统一体验所需的全部端点（`POST/GET /sources`、`.../receipt`、
  `.../content`、`.../download`、`.../actions`、`.../formal`、`POST /inbox/messages`、
  `GET /search`）在默认 `create_app()` 上已可达；真实 HTTP 证据见
  `tests/sources/test_lg038_materials_flow.py`（4 passed，真实 app + FileStore，0 模型调用）。

## 2. 本轮新增（owner 范围）

- `frontend/src/api/sources.ts`：sources/search 线协议与 `createSourcesApi()`。
  仅新增的前端 API helper 独立模块；不改 `api/app.py`，不新增端点语义。
- `frontend/src/views/chat/useChatMaterials.ts`：每文件生命周期（upload/drag/link）。
- `frontend/src/views/chat/ChatMaterialIntake.tsx`：Chat 唯一常规接入口的 UI。
- `frontend/src/views/chat/ChatSourceSearch.tsx`：带来源/版本/hash 的检索引用与打开。
- `frontend/src/views/files/FilesMaterialsPanel.tsx`：Files 读取同一 sources 状态，
  预览/校订/重处理/下载；`FilesView` 以最小面接入 `surface` 切换与 `source:<id>` 深链。
- `frontend/src/components/icons.tsx`：加性新增 `link` 图标（无其它改动）。
- `tests/sources/test_lg038_materials_flow.py`、`frontend/tests/lg038-materials.test.tsx`。

## 3. 旧 Files 上传兼容

- `POST /files/upload`、`GET /files/download`、`GET /files`、`GET /files/content`
  **语义不变、未被删除**；工作区浏览/授权下载/历史保留在 `Workspace files` surface。
- 为避免第二条常规摄取流程，`Workspace files` 的上传区**明确引导**使用 Chat
  作为唯一常规接入口，同时保留旧端点用于授权下载与历史；**不静默丢弃旧 API、不假处理**。
- 未把旧 `POST /files/upload` 自动转成 sources 摄取（那会制造并行流水线），
  也未删除它（那会破坏授权下载/历史）。

## 4. 受保护接入提案（交唯一 owner，不擅自扩冻结 schema）

`backend/lightgravity/sources/service.py::source_actions` 当前仅支持
`reprocess/cancel/revoke/delete`；`docs/08 §4.3` 与 §6.6 亦如此冻结。
本任务要求 Files 支持「归档 / 标签 / 链接语义」的**整理**，其中：

- **归档**：已有 `revoke`（`status→archived` + 命中失效）。语义上等同「归档」，
  但命名是 `revoke`，UI 未暴露。**提案（最小）**：不新增端点/状态，
  仅在 UI 以“Archive (revoke)”呈现并对已归档项显示 `archived`；不改后端。
- **标签**：**当前 schema 无 `tags` 字段**（`docs/08 §6.6` 未冻结）。
  在没有 docs08 owner 加性升版前，**本包不新增前端 tag 写入，也不伪造标签**。
  **提案**：若需要，由唯一 docs08 owner 按 §13 加性 MINOR 冻结
  `source.tags: []`（可选、非秘密、未知字段保留语义不变），再由本包或后续任务接线。
  在此之前，Files Materials 如实不提供标签编辑。
- **链接语义**：`origin.kind="link"`、`external_ref`、`fetched=false` **已冻结且已实现**
  （`SourceOriginRequest`），本包已接入并诚实显示 `link_only`，无需扩展。
  未抓取链接不显示为已成文，且**不做后台自动抓外站**（保持 `fetched=false`）。

> 结论：本包**不修改** `api/sources.py` 与 `docs/08`；上述标签字段提案交由唯一 owner
> 决定是否加性升版。若 owner 决定不加，则“标签”保持未实现，UI 不宣称支持。

## 5. 真实 / fixture 边界

- 后端 4 项 E2E 用**真实默认 app + 真实 FileStore + 真实 HTTP**；机器派生文本用
  scripted `MachineDraft` 模拟一次**成功提取**（不调用 OCR/模型），用于验证“有机读正文才可检索”。
- 前端 13 项用注入的 `SourcesApi` double，断言的是**UI 诚实语义**（link_only、失败不清原件、
  冲突不覆盖、服务不可达如实显示），非后端实现。
- **未做**：真实 OCR/vector/ASR 调用（产品模型调用 0）；真实浏览器对真实后端的多分辨率冒烟
  （见 STATUS 的限制）。
