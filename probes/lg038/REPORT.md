# LG-038 — 交付报告

## 目标回顾

Chat 作为唯一常规资料接入口（上传/拖拽/粘贴链接记录），Files 负责整理归档/
预览追溯/校订重处理下载，同一来源文件 SoT；上传不自动建交付 Task/Run/团队。
服务不可达/未配 OCR/vector 时诚实显状态。旧 Files 上传保留兼容。检索引用带来源/
版本/hash 可打开并回源校验。明确交付需求才走既有 Task/Run，不把资料对话强组队。

## 基点与依赖（真实核对）

- 基点：`dev/lg038` @ `dda78f2`（claim `agent:pi-lg038`），clean。
- 依赖真实满足：LG-013/014/034/036 均 `done`；`api/app.py` 已挂载 sources + search
  （batch5），**本包未改 `api/app.py`**。

## 变更文件（owner 范围）

新增：
- `frontend/src/api/sources.ts` — sources/search 前端 API helper 独立模块。
- `frontend/src/views/chat/useChatMaterials.ts` — 每文件生命周期 hook。
- `frontend/src/views/chat/ChatMaterialIntake.tsx` — Chat 接入口 UI。
- `frontend/src/views/chat/ChatSourceSearch.tsx` — 检索引用/打开。
- `frontend/src/views/files/FilesMaterialsPanel.tsx` — Files 同源 Materials 面。
- `tests/sources/test_lg038_materials_flow.py` — 真实 HTTP E2E（4）。
- `frontend/tests/lg038-materials.test.tsx` — 前端语义测试（13）。
- `probes/lg038/**` — INTEGRATION/STATUS/REPORT/README、浏览器检查与证据、
  fixture server、INTEGRATION 提案。

最小修改：
- `frontend/src/views/chat/ChatBody.tsx` — 挂载材料接入口与检索（1 处）。
- `frontend/src/views/files/FilesView.tsx` — 加 `surface` 切换与 `source:<id>` 深链。
- `frontend/src/components/icons.tsx` — 加性新增 `link` 图标。
- `frontend/src/views/{chat,files}/*.css` — 复用 tokens 的新组件样式。

未改：OCR/lexical/vectors 核心、coordinator/verify/adapter/store/settings、
`api/app.py`、`api/sources.py`、共享 docs/contracts、`CONTRACT_VERSION`（保持 1.7.0）。

## 验证命令与结果

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `uv run pytest -q` | 697 passed, 1 skipped |
| 后端类型 | `uv run mypy` | 130 files clean |
| 新增 E2E | `uv run pytest tests/sources/test_lg038_materials_flow.py -q` | 4 passed |
| 前端类型 | `npx tsc --noEmit` | 0 错误 |
| 前端测试 | `npx vitest run` | 96 passed（含新增 13） |
| 前端构建 | `npm run build` | 成功 |
| 真实浏览器 fixture | `node probes/lg038/lg038-materials-check.mjs ...` | 9/9 |

浏览器检查覆盖：Chat 材料入口存在 + 明示不建交付 Task、链接/搜索输入、
检索命中带 v/hash、打开 Files 同源 Materials、1440/1024/390 无横向溢出。

## 关键设计决定

- 组织“两条常规摄取流程”：Files 上传保留端点/历史，但 UI 引导旧上传至 Chat；
  不把旧上传自动转 sources，也不删除旧 API。
- 链接仅记录：`fetched=false`，未抓取不显示成文，不做后台自动抓外站。
- 标签不擅自实现：`tags` 未冻结，写最小受保护提案交唯一 owner（`INTEGRATION.md §4`）。
- 归档复用既有 `revoke`（`archived` + 命中失效），不新增端点。
- 本包不依赖 LG-037：向量服务不可用时词法/原件仍可用（真实证据中 `vector=disabled`）。

## 限制与未验证

见 `STATUS.md`“未做 / 诚实缺口”：真实 OCR/vector/ASR 质量未验证（LG-035 质量门阻塞、
LG-037 未实现）；标签未实现；浏览器为必要局部冒烟；390 折叠导航不含 Settings 文本。
独立资料版 QA 归 LG-040。
