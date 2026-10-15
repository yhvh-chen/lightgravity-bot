# LG-021 独立 QA 判定与复验清单

- 任务：LG-021「完成前端状态与响应式验收」
- 候选：`61fad69c96b9837ca3680e024b9a0a34371ddb3a`（`Integrate batch2 …`）
- 分支：`qa/lg021`（HEAD == 候选，见下方「HEAD 核验」）
- 判定：**已有主要路径通过；LG-021 保持 `in-progress`**，待整合新 reviewer UI 后做精确 1440 与必要增量复验。不是 false pass，也不是整体 fail。
- 覆盖范围：仅本候选 `61fad69`。LG-017 新增的 reviewer 设置 UI **未覆盖**（本候选内该 UI 尚不存在，见「未测/阻断」），需后续增量复验。
- 证据根目录：`probes/lg021/evidence/`
- 生成时间：2026-10-16（前序真正独立 QA 进程 `bounded-lfsw8w5a` 于 35 轮上限退出 143，已完成判定但未及落盘；本收尾包仅将既有独立 QA 结果落盘，未新增产品调查/产品调用）。

## 1. 本包方法与边界（为什么不是"再跑一次完整 QA"）

本包**不重跑完整浏览器 QA**、不重建工具框架、不继续泛化对比度 helper。只做三件事：

1. 核对既有真实 HTTP 浏览器 QA 的各次 JSON/截图与候选；
2. 对唯一确证的证据缺口（对比度采样 7/24）做**至多一次**小范围关键文字 computed style 实取 + 外部数值核算；
3. 形成可执行判定与最小复验清单，如实标失败/未测/阻断，本地提交。

产品模型 0 次调用；产品 SDK（Antigravity）在本包**未真实执行**（QA 以 `--no-executor` 启动真实产品服务；截图/交互均为真实 fixture 数据，非产品 SDK 真实运行）。截图已按此标注。

## 2. HEAD 核验

```
$ git rev-parse HEAD
61fad69c96b9837ca3680e024b9a0a34371ddb3a
$ git branch --show-current
qa/lg021
$ git status --short
?? probes/lg021/          # 仅本 QA 证据目录未跟踪
```

候选与 HEAD 一致，工作区无产品代码改动（遵循「不改产品代码」）。

## 3. 既有真实 QA 证据（保留，未重跑）

- 真实运行：`probes/lg021/scripts/run_browser_qa.sh` 启动真实产品单进程服务（`python -m lightgravity start … --no-executor`，真实 `frontend/dist` + `/api/v1`），种子来自 `seed_lg021_fixtures.py`，真实 Firefox 156.0.1 经原生 BiDi 驱动。
- 最近一次完整运行：`/tmp/lg021-qa.A181YA`（日志已归档 `evidence/raw-runs/lg021-qa-final2.log`），**31/31 check 全 PASS，`ok:true`**。
- 结果 JSON：`evidence/browser-qa-results.json`；API 线证据：`evidence/api-tasks.json`、`evidence/api-notifications.json`；种子：`evidence/seed.json`；服务端尾部：`evidence/server-tail.log`。
- 10 张截图：`evidence/01…10-*.png`（真实运行/fixture，产品 SDK 未真实执行）。

### 3.1 逐项实际结果（1440/1024/390、五入口+Settings、草稿/TaskScope、长内容/折叠、空错断线不可用历史、键盘焦点/对比度）

| 验收项 | 状态 | 证据 |
|---|---|---|
| 五入口 Chat/Board/Files/Team/Resources + 底部 Settings 存在 | PASS | `browser-qa-results.json` `fiveWorkEntriesAndSettings`、`settingsAtRailBottom` |
| 五入口渲染真实视图（非 placeholder） | PASS | `allFiveEntriesRenderRealViews` |
| 无横向溢出 1440 | PASS（见 §5 截图宽度保留意见） | `noHorizontalOverflow1440` |
| 无横向溢出 1024 | PASS | `noHorizontalOverflow_1024`（sw=cw=1024） |
| 无横向溢出 390 | PASS | `noHorizontalOverflow_390`（sw=cw=390） |
| Board 读取真实 phase 且区分（failed 等，非一律 running） | PASS | `boardReadsRealPhases`、`boardDistinguishesPhases` |
| 打开任务保持 Task 范围 | PASS | `openTaskPreservesScope` |
| Files 列工作区条目 | PASS | `filesListsWorkspaceEntries` |
| Team 渲染 Available/Recruited | PASS | `teamRendersAvailableRecruited` |
| Resources 渲染分类 | PASS | `resourcesRendersCategories` |
| Settings 类型化分区、无原始 YAML blob | PASS | `settingsTypedSections`、`settingsNoRawYamlBlob` |
| 通知徽标来自后端 / 目标指向 task+run / 读后持久 | PASS | `notificationBadgeFromBackend`、`notificationTargetsTaskRun`、`notificationReadPersists` |
| TaskScope 跨视图切换保持 | PASS | `taskScopeSurvivesViewSwitch` |
| 草稿跨视图切换保持 | PASS | `chatDraftSurvivesViewSwitch` |
| 面板折叠 | PASS | `panelsCollapse` |
| 历史过滤区分归档 | PASS | `historyFilterSeparatesArchived` |
| 空态不伪造任务 | PASS | `emptyPhaseHasNoFabricatedTasks` |
| 断线显示诚实状态（Reconnecting(closed)） | PASS | `disconnectedShowsHonestStatus`（截图 `09-disconnected-1440.png`） |
| API 被拦时 Board 显示错误态 + 可恢复 | PASS | `boardShowsErrorStateWhenApiBlocked`、`recoversAfterError`（截图 `10-error-state-1440.png`） |
| Settings 秘密字段不回显 / 无敏感 token 泄漏 | PASS | `settingsSecretFieldNotEchoed`、`noSensitiveTokenInBrowserState` |
| 键盘焦点：rail 项可聚焦且有可访问名、Tab 推进且有解析出的焦点环 | PASS（有保留意见，见 §5） | `railItemsFocusableWithName`、`railKeyboardFocusAdvancesWithResolvedRing` |
| Esc 关闭 popover | PASS | `popoverClosesOnEscape` |
| 长内容展示（超长标题任务） | PASS（截图） | `evidence/04-task-long-1440.png` |
| 对比度 | 原运行 7/24 采样 PASS；本包补测后可见文字 PASS（见 §4） | `browser-qa-results.json` + `evidence/contrast-supplement.json` |

### 3.2 两次预算停止（如实计入成本，不重放）

原 QA 为**两轮/多次预算停止**（如 `bounded-at_ibaww`、`bounded-at_ayz8d92t`、`bounded-at_lfsw8w5a` 等），均因轮数上限 `stop143` 退出，副作用未知（sideEffects unknown）。**不能称首轮通过**：所有原始尝试与其成本都须计入该验收门下的全交付生命周期。未知副作用**不自动重放、不清理外部进程**（仅核对现有文件与签名进程：发现既有根服务 `8123` 等，均未触碰）。这些失败/限额尝试日志保留于 `evidence/raw-runs/`（`lg021-run.log`、`lg021-qa-run.log`、`lg021-qa-run2.log`、`lg021-qa-final.log`、`lg021-qa-final2.log`）。

## 4. 对比度：唯一补充取证（本包新增，最多一次，<=60s）

- 缺口：原完整运行 `textContrastMeetsAA` 只采样 7/24 候选类，且检查阈值仅要求 `ratios.length >= 4`，覆盖不足以支撑"全部关键文字达标"。
- 补测脚本（真实服务 + 真实 Firefox，只取对比度，不重跑其他 QA）：`scripts/diag_contrast.mjs`，驱动 `scripts/…` 无；由临时 driver 复用 `seed_lg021_fixtures.py` 起真实服务后导航 board/settings/chat。
- 补测结果：`evidence/contrast-supplement.json`。原 helper 已实现透明背景向祖先 `source-over` 合成（无"采样 0 = pass"缺陷）；补测沿用同一算法，覆盖原遗漏的可见文字类。
- 结果：所有**可见文字**类最低 **4.76**（`#64748b` on `#ffffff`），满足 WCAG AA（≥4.5）。
  - board：`.lg-card__meta` 4.76、`.lg-section__title` 4.76、`.lg-context-item__meta` 4.76、`.lg-composer__hint` 4.76，其余 7.24–17.85。
  - settings：`.lg-field__label` 17.85、`.lg-detail-header__title` 17.06、`.lg-detail-header__meta` 7.24 等。
  - chat：`.lg-context-item__label` 17.85，其余 ≥4.76。
- 外部独立核算（token 对白/`#f8fafc`）：`#0f172a` 17.85/17.06、`#475569` 7.58/7.24、`#64748b` 4.76/4.55、`#2563eb` 5.17/4.94、`#15803d` 5.02/4.79、`#b45309` 5.02/4.80、`#b91c1c` 6.47/6.18 —— 均 ≥4.5。
- 唯一 <4.5 实测：`.lg-select:disabled`（`#64748b` on `#f1f5f9` = **4.34**）。**WCAG 1.4.3 明确豁免 disabled/inactive 控件**，故记为低优先观察（非阻断、非产品缺陷返修项）。已在证据 JSON 内显式标注 `note: disabled-control (WCAG 1.4.3 exempt)`。

## 5. 失败 / 未测 / 阻断（如实记录，不强行通过）

### 5.1 证据保留意见（非功能失败，但影响"1440"声称）

- 截图 `01-shell-1440.png`…`05-settings-form-1440.png` 实际像素为 **1366×682**，并非 1440 宽；`08/09/10-*-1440.png` 才是真实 **1440×900**。
- 原因：脚本 `setViewport(1440,900)` 后接 `.catch(()=>{})`，早段 `browsingContext.setViewport` 静默失败（Firefox 默认无头视口 1366×682），后段（line 317 之后）成功。
- 影响：`noHorizontalOverflow1440` 与 01–05 的"1440"视觉证据**未在精确 1440 视口下确证**（1366 更窄，不构成更强反例，但标签与断言不精确）。**建议复验项**：在确证 1440×900 视口下重取 01–05 截图与溢出断言。

### 5.2 键盘焦点（证据强度有限）

- `railKeyboardFocusAdvancesWithResolvedRing` 通过，但其 `note` 自述 `focus-visible not BiDi-observable here; ring checked via rule+token`，即焦点环取自 CSS 规则/token 解析而非真实 `:focus-visible` 匹配观察。真实键盘焦点可见性证据强度有限，记为**部分未测**。

### 5.3 对比度未覆盖类（未测）

以下类在各次访问中不可见（需打开通知 popover / 渲染消息 / 选中任务详情列 / 非空列计数），其对比度**未测**：

- `.lg-notification__meta`、`.lg-popover__status`（需打开通知弹层）
- `.lg-message__meta`（需有消息）
- `.lg-detail-header__meta`、`.lg-board__count`（需选中/非空列）

按其 token（`.lg-notification__meta`/`.lg-message__meta`/`.lg-popover__status` 用 `--lg-color-text-subtle` on panel = 4.76；`.lg-detail-header__meta` 用 muted = 7.24）外部核算应达标，但**未经真实渲染取样，记为未测**。

### 5.4 产品 SDK 真实执行：未覆盖（设计如此）

本 QA 以 `--no-executor` 运行，**产品 Antigravity SDK worker 未真实执行**。五入口/Board/Team 等展示真实 API 数据与真实 phase，但"SDK worker 真实跑一次任务"不在本 QA 范围，属阻断性未测（需另有真实 SDK 集成证据）。

### 5.5 LG-017 reviewer 设置 UI：未覆盖

候选 `61fad69` 的 Settings 仅含 "Models & Providers"（Connections），**不存在 reviewer 专属设置 UI**（`SettingsView.tsx` 无 reviewer 分区；docs 无此 UI 契约）。故该项非"漏测"，而是**本候选内尚不存在**；如后续新增，需增量复验。

## 6. 最小复验清单（可执行）

1. **1440 精确视口**：在确证 `setViewport(1440,900)` 生效后重取 01–05 截图并重跑 `noHorizontalOverflow1440`（当前为 1366×682）。
2. **键盘焦点**：在能观察 `:focus-visible` 的环境（非当前 BiDi 限制）实测 rail 项焦点环可见性。
3. **剩余对比度类**：打开通知弹层与含消息会话，对 `.lg-notification__meta`、`.lg-popover__status`、`.lg-message__meta`、`.lg-detail-header__meta`、`.lg-board__count` 取真实 computed style。
4. **LG-017 reviewer UI**：若后续候选新增该设置 UI，按 design.md 补类型化表单/秘密不回显/状态区分验收。
5. **真实 SDK 闭环**：在本 QA 之外，单独提供 `--no-executor` 关闭时 SDK worker 真实执行一次任务并停止的证据（当前阻断性未测）。

## 7. 结论

- 已有真实 HTTP 浏览器 QA 的**31 项检查在该次真实运行中全部通过**，本包补测后**可见文字对比度全部达 AA**（disabled 控件 4.34 属 WCAG 豁免，非阻断）。
- 但存在**证据精度缺口**（1440 截图实为 1366×682）、**键盘焦点可见性证据强度有限**、**部分对比度类未测**、**产品 SDK 真实执行未覆盖**、**LG-017 reviewer UI 未覆盖（本候选不存在）**。
- **判定（收尾确认）：已有主要路径通过；LG-021 仍为 `in-progress`，待整合新 reviewer UI 后的精确 1440 与必要增量复验。** 这既不是 false pass，也不把它升级为全任务通过。
- 具体增量复验（**基于已有 31 条检查，不重跑全套**）：
  1. 精确 1440 / 1024 / 390 视口下的五入口 + Settings 关键布局；
  2. 真实 reviewer 默认选择保护的 UI 验收；
  3. 相关可见 meta 类的对比度与键盘焦点。
- 未以"再最后跑一次"掩盖缺口；未把"没有报告"当作新的调查项目——给定事实未知项按未测原样记录。
- 本判定仅覆盖候选 `61fad69`（`qa/lg021` HEAD，除 `probes/lg021/` untracked 外无改动）。

## 8. 证据文件索引（本包新增/归档）

- `probes/lg021/REPORT.md`（本文件）
- `probes/lg021/evidence/contrast-supplement.json`（本包唯一补充取证）
- `probes/lg021/scripts/diag_contrast.mjs`（小范围对比度探针，非完整 QA）
- `probes/lg021/evidence/raw-runs/*.log`（归档既有运行日志，含两次预算停止）
- 既有：`evidence/browser-qa-results.json`、`evidence/01…10-*.png`、`evidence/api-*.json`、`evidence/seed.json`、`evidence/server-tail.log`
