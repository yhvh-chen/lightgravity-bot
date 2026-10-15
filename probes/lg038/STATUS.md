# LG-038 — 实施状态

状态：**实施完成，待版本 QA LG-040**。本包不自评版本通过。

## 已完成（真实证据）

- Chat 唯一常规接入口：上传/拖拽（`ChatMaterialIntake` → `POST /sources`）、
  粘贴链接记录（`origin.kind=link`, `fetched=false`）。
- 全局上传进受控收件区、**不建交付 Task/Run/团队**：`POST /sources` 与
  `POST /inbox/messages` 均返回 `created/task_created=false`；E2E 断言任务数不变。
- 每文件状态（received/processing/成功/部分/失败）由 source/receipt 回读；
  断线重连与手动 refresh 读同一状态。
- 链接 `link_only`：真实证据中 link source `lexical=not_indexed`、无 content（404），
  未抓取不显示成文，无后台自动抓外站。
- 原件先落盘、失败不清原件：失败派生不产生可检索正文；`/download?kind=original` 仍可取。
- Files 读取同一 sources 状态，支持预览/校订/重处理/下载；编辑有 `expected_revision`
  冲突；重处理不覆盖人工正式版；Markdown/HTML 只安全预览。
- 检索命中带 `source_id`/`source_version`/`content_hash`，可打开；撤销/归档后旧命中失效。
- 旧 `POST /files/upload`/`GET /files/download` 语义不变、未删除，Workspace surface 保留；
  UI 明确引导旧上传走 Chat，不制造第二摄取流程。

## 验证（真实运行）

- 后端：`uv run pytest -q` → **697 passed, 1 skipped**；`uv run mypy` → **130 files clean**。
- 新增 E2E `tests/sources/test_lg038_materials_flow.py` → **4 passed**（真实默认 app + FileStore + HTTP）。
- 前端：`tsc --noEmit` 0；`vitest run` → **96 passed**（新增 13）；`vite build` 成功。
- 真实浏览器 fixture：`probes/lg038/lg038-materials-check.mjs` 在
  真实 uvicorn（`browser_fixture_server.py`）+ 真实 Firefox 156 上 → **9/9**，
  覆盖 1440/1024/390；结果 `probes/lg038/evidence/lg038-browser-results.json`。
- 真实 HTTP 证据：`evidence/lg038-search-hit.json`、`evidence/lg038-sources-list.json`。

## 真实 / fixture 边界

- 后端 E2E 用真实 app/FileStore/HTTP；**机读正文用 scripted `MachineDraft` 模拟一次成功提取**，
  未调用真实 OCR/模型。
- 浏览器 fixture 的“真实”指真实服务 + 真实浏览器 + 真实 HTTP；数据是 fixture 源，非真实用户资料。
- **产品模型 / 外部 OCR / vector / ASR 调用：0**。

## 未做 / 诚实缺口（不夸大）

- **真实 OCR/vector/ASR 质量未验证**：LG-035 的真实中文/表格质量门仍阻塞（端点不可达 +
  无许可样本），LG-037 未实现；本包不依赖 037，向量后端故障时词法/原件仍可用。
- **标签（tags）未实现**：`docs/08 §6.6` 无 `tags` 字段；本包未擅自扩冻结 schema，
  仅提交最小受保护接入提案（`INTEGRATION.md §4`），交唯一 owner 决定。
- **归档**以既有 `revoke` 承载（`status→archived` + 命中失效）；UI 未新增“archive”端点。
- 浏览器 fixture 只做**必要局部冒烟**（材料入口/检索/打开/三档宽度无横向溢出），
  未重复完整 LG-021 矩阵（五入口/底部 Settings/单活跃 Chat/草稿与 TaskScope 保持的完整回归
  由既有测试与 LG-021/022 覆盖）。
- 390px 下 `Settings` 文本在导航折叠态不可见（走抽屉），为既有壳层响应式行为，非本包回归。
- Token/成本：本包无模型调用，成本影响 unknown（不按零计）。

## 未接线 / 后续

- 若 owner 批准 `tags` 加性字段，Files Materials 的标签编辑需另派接线；
  在此之前 UI 不提供标签，也不伪造。
- 独立资料版 QA 归 **LG-040**。
