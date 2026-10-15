---
title: "batch-20261016 第三批集成报告（LG-017 R1 / LG-030 / LG-035 / LG-021 QA）"
doc_type: report
category: engineering
updated: "2026-10-16"
---

# 第三批集成报告（唯一集成 owner）

唯一集成 owner（pi，现有 env DeepSeek）。本报告记录**只读核对 + 安全合并 + 共享装配 + 最小兼容修复**的
实际结果，不做产品真模型验收（归 LG-021/022/032/040）。主代理只 PM、不推送/部署/发布、无嵌套派工。

## 0. 基点与保护

- 集成前 main HEAD：`c138537`（与主代理预期一致，已核实）。集成分支：`integrate/batch3`。
- 全部旧实验分支、`/tmp` worktree、项目旁 worktree、原始 probes 与 dirty 原样保留；
  未 reset/clean、未重复 pick、未整树覆盖、未推送/部署/发布。
- 逐一 `--no-ff` merge，无冲突：`fix/lg017-r1` → `dev/lg030` → `dev/lg035` → `qa/lg021`。

## 1. 各包实际 HEAD / status 核对（合并前）

| 任务 | 分支 | HEAD | status（合并前） | 证据 |
|---|---|---|---|---|
| LG-017 R1 | `fix/lg017-r1` | `8fbdedb` | clean | `probes/lg017/{REFIX-R1,STATUS}.md`、`review_real_probe.{py,json}` |
| LG-030 | `dev/lg030` | `f029152` | clean | `probes/lg030/{STATUS,REPORT,INTEGRATION}.md`、`http_protocol_check.{py,out}` |
| LG-035 | `dev/lg035` | `d7e4391`（含 `faf7230`） | clean | `probes/lg035/{STATUS,REPORT,INTEGRATION,QUALITY-PLAN*}.md`、`reports/**` |
| LG-021 QA | `qa/lg021` | `43dc3f1` | clean（收尾 pi 已退出并提交） | `probes/lg021/REPORT.md`、`evidence/**`、`scripts/**` |

- 派工最新事实：017-r1 真实 review 1 次 passed、usage unknown；035 cohort B 因 `192.168.8.12:11434`
  两次 `No route to host` 未 POST，累计 4/10；LG-021 收尾 pi（`bounded-lfsw8w5a`）在集成开始前仍在运行，
  **本 owner 先收其它三个已结束分支，末尾确认其退出且 commit clean 后方合并**（见 §7）。

## 2. 共享装配与依赖（唯一 owner 串行）

- **后端无跨分支文件重叠**：017-r1 改 `settings/**`、`verify/**`、`coordinator/service.py`、`api/bootstrap.py`；
  030 改 `collaboration/**`、`api/collaboration.py`；035 改 `sources/**`、`api/sources.py`。合并后无冲突。
- **依赖**：035 新增 `pypdfium2>=5,<6`（`pyproject.toml` + `uv.lock`）；`uv sync --frozen` 成功。
  许可 BSD-3-Clause + Apache-2.0，自包含 wheel，无系统 poppler，懒加载，未引入 Pillow。
- **默认 app 装配**：`create_app()` 实枚举含 `/api/v1/sources/{id}/{content,download,actions,formal}`、
  `/api/v1/intake/jobs/*`、`/api/v1/inbox/messages`、`/api/v1/runs/{id}/collab_requests`（均默认关闭）。
  `/content`/`/download` 仅经 `resolve_path` 读文件，**不调用 OCR、不执行外部正文**（`api/sources.py` 无网络调用）。

## 3. 最小兼容修复（集成 owner）

### 3.1 LG-017 reviewer 默认连接的产品可操作性（前端）

- **缺口**：`default_reviewer_connection_ref` 此前只在受保护 API 存在，Settings 界面无法设置 →
  首版用户无法从“无 reviewer → 配置 → 独立复核”闭环；且 LG-021 独立 QA 候选 `61fad69` 内**尚无该 UI**，
  其判定明确列为未覆盖项。
- **修复（既有 LG-017 首版兼容工作，不建新任务/平台）**：复用现有连接实体/组件/秘密管理，加**最小 typed
  reviewer 默认选择**：
  - `frontend/src/api/settings.ts`：`GlobalSettingsView.default_reviewer_connection_ref`、
    `defaults.reviewer`、`SettingsUpdateInput.default_reviewer_connection_ref`。
  - `frontend/src/views/settings/DefaultsEditor.tsx`：第三个角色选择器 + resolution 行 + 显式提示
    “留空即无 review，**不静默回退 worker 连接**”。
  - `frontend/tests/settings.test.tsx`：新增显式设置/清空 reviewer 默认的断言。
- 语义显式、受 pin/预算（reviewer 走独立默认连接与凭证，模型调用经既有预算与 `validate_findings`）。
  **未用静默程序门/默认假 pass 绕开 reviewer 配置**。
- 独立复验：LG-021 需对该新增设置路径与敏感状态做**增量复验**，不继承旧候选截图冒充已验
  （清单见 `backlog/tasks/LG-021.md`）。

### 3.2 LG-030 程序认证边界（默认拒绝）

- **缺口**：`POST /runs/{id}/collab_requests` 身份此前取自请求体 `from_member_ref`，与契约
  “worker 侧调用须经受控执行身份，不接受浏览器直接指定任意 owner”不符。
- **修复（最小接口 + 默认拒绝）**：新增执行身份接缝 `ApiContext.worker_identity`
  （`(Request) -> str | None`，默认 `None`）；`PeerService.request(..., authenticated_member_ref=...)`
  要求程序认证身份等于 body 身份，否则 `unauthenticated`/`identity_mismatch` 拒绝且**不落盘、不耗预算**。
  **body 自报身份永不作为认证**。
- **不制造依赖死循环**：真实 worker 身份注入 + Graph 接线归 **LG-031**；030 交付的是**安全的协议边界**
 （默认关闭 + 默认拒绝），不再因“待 031 运行时接线”永久 in-progress。
- 复现（默认 app，真实 HTTP）：`uv run python probes/lg030/http_protocol_check.py` →
  `DENY rejected unauthenticated` / `POST 200 requested True` / `REPLAY True` /
  `BUDGET rejected budget_exhausted` / `GET 200 ['c1','c2']`。

## 4. 契约（docs/08 与入口）

- 契约保持 **`1.7.0`**（第三批**未新增**字段/端点/错误码/枚举；030 执行身份边界为**集成澄清**，
  035 复用既有冻结端点与事件）。
- `docs/08 §4.3`：LG-030 两行 → `已实现（默认关闭；待版本 QA LG-032）`；LG-035 `content/download/actions`
  行 → `已实现（LG-035；待版本 QA LG-040）`；新增“执行身份边界”说明段。
- `docs/08 §5.1`：LG-035 另已实际产生 `source.attributed`（成功/部分提取）与 `intake.failed`（失败）。
- `docs/06` §6.1：加第三批集成更新块；§6.3 契约澄清。
- `README.md`/`PROJECT.md`/`agent.md`：017-r1 已同步 1.7.0；第三批无需再改版本描述。

## 5. 整合候选检查（真实退出码）

| 检查 | 命令 | 结果 | 退出码 |
|---|---|---|---|
| 后端类型 | `uv run mypy` | Success, **124 source files** | 0 |
| 后端测试 | `uv run pytest -q` | **647 passed, 1 skipped** | 0 |
| 定向（协作/身份） | `uv run pytest tests/collaboration -q` | **57 passed** | 0 |
| 协议链复现 | `uv run python probes/lg030/http_protocol_check.py` | 5 行断言符合 | 0 |
| 前端类型 | `npx tsc --noEmit` | 0 errors | 0 |
| 前端测试 | `npx vitest run` | 12 files, **83 passed** | 0 |
| 前端构建 | `npx vite build` | built | 0 |

- **产品真实模型调用 0**（本轮集成；017 的 1 次真实 DeepSeek 复核沿用其原始证据，未重放）。
- 前端复跑原因：本批**确实**修改了前端（reviewer 默认选择接线），故重跑 tsc/test/build 而非沿用 021/019 旧基点。
- 已知测试工具隔离怪癖（**非本批引入，不阻断**）：`tests/startup/*` 使用 `from conftest import make_settings`；
  若在**同一 pytest 会话**里把 `tests/api` 与 `tests/startup` 一起收集，会因 `tests/api/conftest.py` 同名而收集失败。
  已在 `c138537`（集成前）同样存在；**全量 `uv run pytest -q` 正常（647 passed）**，单目录亦正常，仅 ad-hoc 子集顺序触发。
- `git diff --check` 报告的尾随空白仅在 **LG-035 gold 真值文件** `probes/lg035/fixtures/8071_093.3B.txt`（真实转写真值，
  字节保真，不改动）。

## 6. 任务状态结论（诚实）

- **LG-030**：**`done`**（待版本 QA LG-032）。协议在受保护 HTTP + 真实 `FileStore` 上满足验收；
  程序认证接缝已就位且默认拒绝；真实身份注入/Graph 接线归 LG-031，不再是 030 阻塞项。
- **LG-017**：**保持 `in-progress`**。R1 已补齐真实受控 `ModelReviewer` + 诚实 `unavailable` 默认 +
  阻止 accept；本轮又补最小 Settings reviewer 默认选择。但按任务硬条件须 **LG-022（及 LG-021 增量）**
  独立集中 QA 复验，本包不自评完整版本 pass。
- **LG-035**：**保持 `in-progress`**。产品 Python 3.12 真实 OCR（真实清晰页/多页 PDF，预注册阈值通过）、
  机器/人工分层、重处理不覆盖、部分失败诚实均已实现；但**真实中文/表格人工真值质量门阻塞**
  （已授权端点两次不可达 + 无许可明确样本），**不以合成页面当真实品质**，不得凭 API 通过置 done。
- **LG-021**：**保持 `in-progress`**。独立 QA（候选 `61fad69`）真实浏览器主要路径 31/31 通过、
  可见文字对比度达标；但存在证据精度缺口（1440 截图实为 1366×682）、键盘焦点证据强度有限、
  4 个对比度类未测、产品 SDK 真实执行未覆盖、**LG-017 reviewer UI 未覆盖（候选内不存在）**。
  **未判 pass**；判定与最小复验清单写入任务与 `probes/lg021/REPORT.md`。
- **LG-041**：保持 `todo`（`needs decision`）。

## 7. LG-021 收尾进程核对

- 集成开始时 `qa/lg021` worktree 有未跟踪 `probes/lg021/`，对应收尾 pi（`bounded-lfsw8w5a`）仍在运行。
- 本 owner **未触碰其 index/工作区**；先完成其它三个分支的收拢与共享装配。
- 收尾期间再次核对：该进程已退出，`qa/lg021` HEAD `43dc3f1`、**worktree clean**，方 `--no-ff` 合并其判定与证据。

## 8. 未完成 / 剩余质量门

- 首版集中 QA：LG-021（in-progress，最小增量复验）、LG-022（含 LG-017 独立复核真实门）。
- 去中心化：LG-031（真实身份注入/Graph 接线）、LG-032（集中 QA）。
- 资料与 Embedding：LG-036（词法索引，依赖 035）、LG-037/038、LG-040（集中 QA）。
- LG-035 真实中文/表格人工真值质量门；已授权 OCR 候选端点不可达（外部阻塞，主代理已向用户发异步可选样本路径/服务恢复问题，尚无回复）。
- LG-029/030 的 settings 写入开关、coordinator `LeaseManager`、执行身份注入仍未装配（归 LG-031）。
- 完整 checkpoint skip 仍未实现。
- 产品真实模型路径未在本候选中运行（0 调用）。

## 9. 就绪任务与 claim

- 集成后 backlog 专用根校验：**41 项、无诊断**；`tasks ready` **无就绪任务**。
- LG-022 依赖 LG-017/021（均 in-progress）、LG-031 依赖 LG-030（done）但 LG-029/030/031 线尚未就绪、
  LG-036 依赖 LG-035（in-progress）——**均不满足真 done 前置，未 claim、未建 worktree**，
  不以“创建 claim commit”伪造就绪（详见 PROGRESS）。
