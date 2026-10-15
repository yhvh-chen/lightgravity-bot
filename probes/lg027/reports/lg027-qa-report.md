# LG-027 — Settings / Credential Lifecycle 专项版本 QA 报告

- 任务：LG-027《验收模型设置与凭证生命周期》（首版验收专项，非实现）
- Worktree：`/tmp/lightgravity-worktrees/lg027`（branch `qa/lg027`）
- 基点 commit：`b8251b5c63dbccac0a15d3c513a4cbc70ea1f9aa`（HEAD 未变，未提交）
- 执行者：agent:pi-lg027（未参与实现）
- 环境：Chrome 151.0.7922.71 / Node v22.23.2 / CPython 3.12.13 / uv 0.12.1
- 结论：**pass**（有明确的环境限制，见 §6；未冒充 013 Chat / 016 恢复功能验收）

---

## 1. 环境恢复记录（不是重新开工）

上一进程因 `/tmp` 配额耗尽导致派工日志 writer 退出（EDQUOT），并非功能验收失败。
本次继续在同一 worktree、同一 HEAD 上进行，未 reset / 未覆盖 / 未删除已有证据：

- 清理已完成的其它任务 gitignored 依赖释放空间；本 worktree 的 `.venv`/`node_modules`、
  全部 dirty 源改动与证据完整保留。
- 检查了全部既有文件完整性：Python/JS/Bash 语法与 JSON 解析均通过，文件结尾完整，
  **未发现配额中断留下的残缺文件**；不完整文件不会被当作通过。
- 旧证据保留为 `*.prerecovery.json`，新证据为同名 JSON（内容一致或为新的真实运行）。

## 2. 候选基点与范围

- 验收对象是**设置入口与凭证链路完整后的集中 QA**：Docs 07/08 当前版本 +
  依赖 LG-015 / LG-020 / LG-026 的已实现接口。
- **不冒充** LG-013 Chat 功能验收，也不冒充 LG-016 恢复功能验收；相关能力未在本报告
  宣称通过。
- 前端全量首版 QA 仍归 LG-021 / LG-022。

## 3. 实际执行与证据

### 3.1 真实 CLI 服务器 + 真实 HTTP：设置→分层测试→默认→新 Task

`probes/lg027/scripts/lg027_settings_path.py`（真实 `python -m lightgravity start`
uvicorn loopback，真实 HTTP，非 in-process ASGI）。

**离线模式 `LG027_NETWORK=off`**（`evidence/lg027-settings-path-off.json`，无网络/无模型调用）：

- 缺认证启动：`tasks/settings/health` 均 200；`execution_ready=false`，
  原因 `no default worker connection configured`。
- 敏感写入无 token → **401 unauthorized**（默认拒绝）。
- 建连接 201、写凭证 200（`source=secret_store`，响应不回显凭证）。
- 分层测试：`config_parse=passed`、`credential=passed`、`capability=declared`、
  `runtime_network=skipped`、`tool_probe=skipped`、`structured_output=skipped`，
  `overall=not_run` —— **网络未通过不被当作全部能力通过**。
- 设默认后 `execution_ready=true`，`default_worker_connection_ref=deepseek-lg027`。
- 新 Task 到达真实 executor（Member 招募并 pin），因上游不可达快速失败（`task_phase=failed`），
  证明**入口**而非模型成功。
- 凭证泄漏扫描：`persisted_secret_leaks=[]`、`server_log_leaks=false`。

**真实网络模式 `LG027_NETWORK=on`**（`evidence/lg027-settings-path-on.json`，
本次恢复新执行 1 次，`LG027_WAIT_SECONDS=90`，外层 `timeout 150` 硬停）：

- 分层测试 `overall=verified`：`runtime_network=passed`；
  `tool_probe=skipped`、`structured_output=skipped`（**与网络通过明确区分**）。
- 设默认后新 Task 真实执行：**两个 Subtask 均 `state=passed`、`acceptance=passed`**；
  `task_phase=awaiting_acceptance`、Run `state=awaiting_acceptance`。
- Member / Run 均 pin 到配置连接与凭证版本。
- 泄漏扫描：`persisted_secret_leaks=[]`、`server_log_leaks=false`；证据 JSON 内无密钥。

### 3.2 错误分支 / 边界（本地、无真实网络）

`tests/e2e/settings/test_lg027_error_branches.py`（9 例全过）：真实
`FileStore/FileSecretStore/ConnectionService/ConnectionTester`，上游为受控本地 HTTP：

- 错误 key → 上游 401 → `runtime_network=failed`；
- 不存在 model → 上游 404 → `failed`；
- 慢上游 → 超时失败且**有界**（不无限重试）；
- revision 冲突（更新 / 设测试）→ 真实 `RevisionConflict`；
- 凭证轮换 → 前一测试结果 `is_stale=True`；
- 禁用被引用的默认连接 → 需同调用清引用；原子清引用后 allowed；
- 部分写入失败 → 凭证回滚，无孤立秘密。

### 3.3 活跃 Member 不热换 / 新招募用新配置

`tests/e2e/settings/test_lg027_default_pin.py`：真实 `build_runtime` + 真实 HTTP。

- 切换全局默认后，活跃 Member 与既有 Run 的 `connection_pin` 保持旧连接；
- 新 Task/Run 解析并使用新默认；本地不可达上游，**无模型调用**。

### 3.4 真实浏览器渲染（系统 Chrome + CDP，`file://`）

`probes/lg027/scripts/lg027_browser_file.mjs`（runner：`run_browser_file.sh`），
驱动**真实生产构建** `frontend/dist`（inlined）——11/11 通过
（`evidence/browser-file/lg027-browser-file-results.json` + 2 张真实截图）：

- 真实 bundle 渲染 app shell；齿轮打开 Settings（Models & Providers）；
- URL 保留真实 Task scope（`task_lg027_fixture`）；
- 无后端时**公开显示加载错误**（`Failed to fetch`），不伪造连接数据；
- 密钥串不在 localStorage/sessionStorage/URL；
- 1440px 与 390px 均无横向溢出；窄屏经顶部抽屉打开 rail 后 Settings 正常渲染。

截图：`evidence/browser-file/01-settings-view-1440.png`、`02-settings-390.png`。

### 3.5 前端组件层（jsdom，补充非浏览器证据）

`frontend/tests/settings.test.tsx` + `settings-auth.test.ts`：14/14 通过，覆盖
写-only 密钥字段清空、保存后不回显、密钥不入 session/localStorage、移除凭证引用删除秘密存储。

## 4. 通过项小结（对应验收条件）

| 验收条件 | 结果 | 证据 |
|---|---|---|
| 缺认证启动→Settings→分层测试→设默认→新 Task 真实执行 | pass | §3.1 on/off |
| 网络成功 ≠ 全部能力通过（tool/structured skipped） | pass | §3.1 on |
| 错误 key / 不存在 model / 超时取消 / revision 冲突 / 凭证轮换 stale / 禁用被引用连接 | pass | §3.2 |
| 秘密不入浏览器存储/聊天/任务 Markdown/日志/响应/导出 | pass | §3.1/3.4/3.5 扫描 |
| 部分写入故障不留孤立秘密/坏引用 | pass | §3.2 |
| 活跃 Member 默认切换不热换；新招募用新配置 | pass | §3.3 |
| 返回 Task 与窄屏表单有实际证据 | pass（渲染层） | §3.4 |

## 5. Checks / Calls / 泄漏 / 进程

- Checks：pytest e2e 9/9、vitest 14/14、`file://` 浏览器 11/11、off-mode 与 on-mode
  真实路径各 1 次全链路。
- 真实上游调用：本次恢复**新执行 1 次真实 DeepSeek 运行**（产品默认单交付 Run、2 个
  Subtask，两 Subtask 通过验收）。**产品未对外暴露精确调用计数**（凭证代理按设计不记录调用，
  且 CLI 无可设 `model_calls_cap` 的入口），故**不伪称精确总量**：
  旧计数无法完整核实，按规则覆盖为**未知/旧上限 5**，本次恢复新增**硬上限 4**，
  最坏累计上限 9；实际观测只用了 1 次运行、受 `timeout 150` + `LG027_WAIT_SECONDS=90` 硬停。
- 泄漏：off/on/证据 JSON/server.log 均无密钥；证据 JSON 无 `sk-` 形串；未读取 `.env`，
  未输出/截图密钥；真实 key 仅来自进程环境进入受控 secret store 与内存。
- 进程：本包 lightgravity server / 探针 Chrome / node 均已退出（仅残留系统 crashpad handler
  与本人 pi-worker）。

## 6. 真实限制与未覆盖（如实记录，不作 pass）

1. **沙箱内 Chrome 无法做 HTTP(S) 导航与页面内 fetch**（已精确复现）。
   - 复现：`Page.navigate` 到 `http://127.0.0.1:<port>/` 永不返回；`Runtime.evaluate`
     的 `fetch('http://127.0.0.1:<port>/api/v1/health')` 立即 `Failed to fetch`；
     而同一 Chrome `Page.navigate` 到 `file://` 正常渲染。
   - Chrome verbose 日志显示 `127.0.0.1` 请求只到
     `NetworkDelegate::NotifyBeforeURLRequest`，**从未到达服务端**（server.log 无该请求）。
   - 已试 `--no-proxy-server`、`--host-resolver-rules`、`--disable-web-security`、
     `NetworkServiceSandbox`/`NetworkServiceInProcess`、`--single-process`、
     局域网 IP（192.168.8.50）与外部站点 —— 均同样超时。
   - 因此**无法在真实浏览器 + 真实后端**上跑完整 Settings CRUD/分层测试/设默认流程；
     该部分由真实 CLI + 真实 HTTP（§3.1）覆盖，浏览器部分只声称渲染证据（§3.4）。
     **未用 mock 浏览器冒充真实后端联调。**
2. 另注：`file://` 下 `document.cookie` getter 会阻塞渲染线程，探针已避免读取；
   cookie 不持久化由 HTTP 探针与 jsdom 测试覆盖。
3. 本报告不覆盖：LG-013 Chat、LG-016 恢复、前端全量首版 QA（归 LG-021/022）。

## 7. 建议

- §6.1 的 Chrome HTTP 阻断是环境级问题，影响一切真实浏览器+本地后端联调；
  建议由 root 在环境层解决或在首版 QA 说明中统一记录，届时可重跑
  `run_browser.sh`（HTTP 版探针已就绪并修复了 createTarget 不导航、IndexedDB/cookie 阻塞等问题）。
- 产品侧未发现需返修的缺陷；本包不修改产品代码。

## 8. 证据清单

```
probes/lg027/evidence/
  lg027-settings-path-off.json              离线全链路（本次重跑，确定性一致）
  lg027-settings-path-off.prerecovery.json  恢复前保留
  lg027-settings-path-on.json               真实 DeepSeek 全链路（本次新跑，双 Subtask 通过）
  lg027-settings-path-on.prerecovery.json   恢复前保留
  browser-file/lg027-browser-file-results.json
  browser-file/01-settings-view-1440.png
  browser-file/02-settings-390.png
probes/lg027/scripts/
  lg027_settings_path.py       真实 CLI+HTTP 全链路
  lg027_browser_file.mjs       file:// 真实渲染探针
  run_browser_file.sh          渲染探针 runner
  lg027_browser.mjs            HTTP 版全流程探针（当前环境受限，保留）
  run_browser.sh               HTTP 版 runner（保留）
tests/e2e/settings/
  test_lg027_error_branches.py 9 例
  test_lg027_default_pin.py    pin/热换
```
