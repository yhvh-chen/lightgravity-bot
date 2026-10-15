# LG-021 增量复验报告（incremental-r1）

- 任务：LG-021「完成前端状态与响应式验收」
- 本包类型：同一 owner 新上下文的**增量复验**，只补既有门明确缺口；不重跑 31 条首验脚本，不建通用对比度框架。
- 候选（本包验证的集成 HEAD）：`e4cef4a`（`main`，含第三批集成 merge `c667434` 与后续 claim/docs 提交）。
  相关集成提交：reviewer UI 接线 `635489e`（`frontend/src/api/settings.ts`、`views/settings/DefaultsEditor.tsx`、`frontend/tests/settings.test.tsx`）。
- 分支：本 worktree `lg021-r1`（cwd 持久）。本包**不改产品代码**，只写 `probes/lg021/incremental-r1/**` 与 LG-021 任务记录。
- 生成时间：2026-10-16。
- 证据根：`probes/lg021/incremental-r1/`（旧 `probes/lg021/**` 原件全部保留，未删改）。

## 0. 方法、边界与成本诚实

- 真实运行：`run_incremental.sh` 启动**真实产品单进程服务**（`python -m lightgravity start … --no-executor`，真实 `frontend/dist` + `/api/v1`），
  独立临时 data root + workspace，真实 Firefox 156.0.1 经原生 BiDi 驱动，真实 same-origin HTTP。
- 前端：本包**实际执行** `npx vite build`（`frontend/dist` 先前不存在）。构建产物含新增 reviewer UI（`dist/assets/index-*.js` 内含 “Default reviewer connection”）。
- **产品模型调用 0**：无 coordinator 连接被配置，`--no-executor`，coordinator 使用内置确定性 responder；本包所有断言均为 UI/API 真实，非模型真实。
- 未触碰 root `8123` 服务；未清理任何非本包进程。已精确清理本包 6 个 `/tmp/lg021-incr.*` 临时根（确认无进程引用后 `rm -rf`）；
  本包自行启动的 server/firefox 进程组均在脚本 trap 内退出。副作用未知者不重放。
- 单命令 ≤120s；长检查短轮询。

## 1. 视口断言（真实 `window.innerWidth/innerHeight`，非文件名）

每次切换后重试 `browsingContext.setViewport` 直至 `window.innerWidth/innerHeight` 精确匹配，再做断言；截图 PNG 头像素独立复核。

| 视口 | innerW×innerH 实测 | 五入口+底部 Settings | Settings 位于 rail 底部 | 无横溢 (sw≤iw 且 cw==iw) | 截图像素 |
|---|---|---|---|---|---|
| 1440×900 | 1440×900 PASS | PASS | PASS | PASS（sw=cw=1440） | 1440×900 PASS |
| 1024×768 | 1024×768 PASS | PASS | PASS | PASS（sw=cw=1024） | 1024×768 PASS |
| 390×844 | 390×844 PASS | PASS（先开 nav 抽屉） | PASS（抽屉内测量） | PASS（sw=cw=390） | 390×844 PASS |

- 旧 QA 遗留缺口「1440 截图实为 1366×682、`noHorizontalOverflow1440` 标签不精确」在本包**已闭合**：
  五入口 + 底部 Settings 关键布局与无横溢**均在确证 1440×900 视口下**通过，截图 `inc-1440-settings.png` 实测 1440×900。
- 390：窄屏 rail 位于 nav 抽屉；本包先点击真实 “Toggle navigation” 打开抽屉，再断言五入口 + 底部 Settings，并测量 rail 几何（设置项 bottom 距 rail bottom ≤80px）。无横溢。
- 前 31 条已通过项保持既有证据与旧候选绑定，本包只补上述精确视口证据，未重跑。

## 2. 新 Settings 默认 reviewer 选择（LG-017 R1 增量）

真实 HTTP + 真实 UI 操作（非 raw API 冒充 UI），独立 fixture 连接。

| 子项 | 状态 | 证据 |
|---|---|---|
| 通过真实 UI 创建两个真实连接（`openai-compat`），并以 UI `<select>` + “Save defaults” 设置 reviewer 默认 | PASS | `reviewerBackendConnectionsCreated`、`reviewerConfiguredViaUI_realApiReflects` |
| 真实 `GET /api/v1/settings` 反映 `default_reviewer_connection_ref` | PASS | `reviewerConfiguredViaUI_realApiReflects.apiAfterSave` |
| reviewer 与同一连接实体/worker 共用但为**独立角色**（不与 worker ref 混淆） | PASS | `reviewerIsSeparateConnectionEntity` |
| 受保护保存 / `expected_revision` 冲突拒绝 | PASS | `reviewerExpectedRevisionConflictRejected`（stale write → **409**） |
| 缺少 runtime token 拒绝 | PASS | `missingTokenRejectedOnProtectedWrite`（无 `X-LG-Token` → **401**） |
| 无秘密回显 | PASS | `noSecretEchoInSettingsApi`（settings/connections 响应中无 `sk-…`） |
| 刷新持久 | PASS | `reviewerSelectionPersistsAfterReload`（reload 后 select 值仍为 `deepseek-reviewer`） |
| 未配置诚实反馈 | PASS | `reviewerUnconfiguredHonestFeedback`（清空后 API `reviewer=null`，UI 显示 “No reviewer default configured.”） |
| Task/Settings 切换 scope 保持 | PASS | `taskScopeSurvivesSettingsSwitch`（`?task=task_…` 切换前后一致） |

- 语义：reviewer 默认独立于 worker；留空 = 无真实 reviewer（诚实 `unavailable`，不静默回退 worker）。
- **UI/API 真实 ≠ 模型通过**：本包只证明设置路径与敏感状态行为；真实 `ModelReviewer` 复核证据归 LG-017/LG-022，不在本包。

## 3. 已采可见 meta 对比度 + 焦点（有限真实 computed style）

真实渲染取样，透明背景沿祖先 `source-over` 合成；不可见类记 not-applicable，不伪采。外部数值独立核算一致。

| 类 | 场景 | fg / bg | 比值 | 状态 |
|---|---|---|---|---|
| `.lg-notification__meta` | 打开通知 popover（真实） | `#64748b` / `#ffffff` | **4.76** | PASS |
| `.lg-popover__status` | 同 popover | `#64748b` / `#ffffff` | **4.76** | PASS |
| `.lg-message__meta` | Chat 真实发送一条消息（确定性 responder，模型 0） | `#64748b` / `#ffffff` | **4.76** | PASS |
| `.lg-board__count` | Board 列计数（真实非空列） | `#64748b` / `#f8fafc` | **4.55** | PASS |
| `.lg-detail-header__meta` | Settings detail header | `#475569` / `#f8fafc` | **7.24** | PASS |

- 全部 sampled 可见类 ≥4.5（最低 **4.55**）；外部核算：`#64748b`/`#fff`=4.76、`#64748b`/`#f8fafc`=4.55、`#475569`/`#f8fafc`=7.24，与浏览器实取一致。
- 沿用既有对比度结论（min 4.76 / 4.55，`.lg-select:disabled` 4.34 属 WCAG 1.4.3 豁免），**未为每项重建通用框架**。
- **焦点**：真实 Tab 可将焦点推进到 rail 项（`focusRailReachableByRealTab` PASS）。但 `:focus-visible` 在本 headless Firefox + BiDi 键事件下 **不可观测**（聚焦 rail 按钮时 outline 解析为 `none 3px`）。
  按“不可见标未适用而非伪采”，本项记为 **not-applicable 观察**（`results.focus.ringObservable=false`，`focusNote` 明确），**不写 pass、不判产品缺陷**。与旧 QA §5.2 结论一致。

## 4. 通过 / 失败 / 未测（准确）

- **本包新增 26 项检查全部 PASS（26/26，`ok:true`）**，覆盖 §1–§3 的既有缺口闭合。
- **真实缺陷：0**（未发现需返修产品代码的具体缺陷；`.lg-select:disabled` 4.34 为 WCAG 豁免观察，非缺陷）。
- **未测/仍开放（不属本包范围，如实列出）**：
  1. `:focus-visible` 焦点环可见性：当前环境不可观测，维持 not-applicable（非产品缺陷）。
  2. 产品 SDK / `ModelReviewer` 真实执行：本包 `--no-executor`、模型 0；真实模型复核证据归 LG-017/LG-022，不在本包。
  3. 首验 31 条中与本次差异无关的项：保持既有证据与旧候选绑定，本包不重跑、不重判。

## 5. 判定

- 既有缺口（1440 精确视口/无横溢、新 reviewer 设置路径与敏感状态、5 个未采 meta 类对比度）在本包**已按增量、有限、可复核方式补齐并通过**。
- 不因工具限制（focus-visible 不可观测）写 pass；如实标 not-applicable。
- LG-021 是否转 `done` 由主代理/集中 QA 决定；本包证据支持“新增差异已复验、无发现产品缺陷”，但真实模型/首验全量门不在本包。

## 6. 证据文件

- `probes/lg021/incremental-r1/run_incremental.sh` — 真实服务 + Firefox BiDi 驱动（独立 data root、`--no-executor`）。
- `probes/lg021/incremental-r1/incremental_qa.mjs` — 增量检查脚本（复用既有 BiDi helper 模式）。
- `probes/lg021/incremental-r1/evidence/incremental-results.json` — 26 项结构化结果（`ok:true`）。
- `probes/lg021/incremental-r1/evidence/incremental-progress.log` — 逐项 PASS/FAIL 进度。
- `probes/lg021/incremental-r1/evidence/inc-1440-settings.png` / `inc-1024-settings.png` / `inc-390-settings.png` — 实测像素 1440×900 / 1024×768 / 390×844。
- `probes/lg021/incremental-r1/evidence/seed.json`、`server-tail.log` — 真实种子摘要与服务尾部。
- 旧 `probes/lg021/**`（REPORT/evidence/scripts）**全部保留未改**。
