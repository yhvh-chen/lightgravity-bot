# LG-020 启动/分发实测证据

- 日期：2026-10-14（UTC）
- worktree：`/tmp/lightgravity-worktrees/lg020`，agent `pi-lg020`
- 基线 commit：`25312d1`
- 环境：Python 3.12.13、uv 0.12.1；临时目录 `/tmp`；**未调用真实模型**

## 1. 局部检查

```bash
uv run mypy          # Success: no issues found in 81 source files
uv run pytest -q     # 331 passed, 1 warning in 28.92s（含 tests/startup 27 项）
uv run pytest tests/startup -q   # 27 passed
```

`tests/startup/` 覆盖：token 生成/注入/不落盘、Host+Origin 守卫、SPA 托管与
`no-store`、默认拒绝敏感写、缺凭证/缺 executor 的就绪报告、幂等 init、真实子进程
start→status→stop。

## 2. 一体服务真实启动（temp data/workspace/secret + 合成 dist，非 Vite 双源）

```bash
uv run lightgravity start --data-dir /tmp/lg020-evidence/data \
  --workspace-root /tmp/lg020-evidence/ws --secret-store /tmp/lg020-evidence/secrets \
  --frontend-dist /tmp/lg020-evidence/dist --host 127.0.0.1 --port <free>
```

实际观察（节选）：

- 启动输出 `executor_wired: true`、`frontend_served: true`，执行报告
  `execution_ready: false`，`reasons: ["no enabled agent resource ...",
  "no default worker connection configured"]`（缺配置如实不可用，未崩溃）。
- `GET /api/v1/health` → 200，`capabilities.sdk_adapter: true`、`settings: true`。
- `GET /api/v1/settings` → 200（无 token 可读）。
- `PATCH /api/v1/settings`（无 token）→ **401**（默认拒绝，不可绕过）。
- `GET /` → HTML 含 `__LG_RUNTIME_TOKEN__`，`Cache-Control: no-store`；`GET /assets/app.js`
  → 200 `text/javascript`（同源一体托管）。
- pid 记录 `<data>/runtime/lightgravity.json` 不含秘密。
- `uv run lightgravity stop` → `{"stopped": true, "forced": false,
  "message": "process ... stopped after SIGTERM"}`，pid 记录被移除，端口关闭。

## 3. 显式最小 init（幂等 + revision 保持）

```bash
uv run lightgravity init --data-dir /tmp/lg020-init/data \
  --workspace-root /tmp/lg020-init/ws --secret-store /tmp/lg020-init/secrets \
  --connection-id lg-demo --credential-ref lg-demo-key --agent-id developer \
  --set-worker-default
```

- 首次：创建 `connection:lg-demo`、3 个 tool、2 个 skill、`agent:developer`，并设置
  worker 默认连接；Connection 文件只写 `credential_ref`。
- 第二次：全部 `skipped`，`defaults: {}`，各资源 revision 不变。
- 之后写入 secret store（`sk-manual-evidence-not-real`，仅用于本地就绪验证）再
  `status --deep`：`execution_ready: true`、`credential_configured: true`、
  `agent_refs: ["developer"]`、`reasons: []`。即“模型/凭证配好后恢复执行入口”。

## 4. 后台启动/停止与残留清理

```bash
uv run lightgravity start --daemon ... && uv run lightgravity status ...
uv run lightgravity stop --data-dir /tmp/lg020-daemon/data
```

- 后台启动返回 pid，`status` 显示 `running: true` 且 `health.status: ok`。
- `stop` 后 pid 记录移除、端口关闭，`pgrep`/`ps` 未发现残留服务进程
  （daemon 走 `setsid`，stop 对进程组发信号；前台进程不是组长时只杀单 pid，
  避免误伤 shell/ci）。

## 5. 首启认证握手

- 服务进程内随机 token，仅在内存；`index.html` 响应注入
  `window.__LG_RUNTIME_TOKEN__`（已有前端 `auth.ts` 读取），不写 URL/日志/持久
  storage。
- 前端 Settings 客户端 `createSettingsApi` 默认 `getRuntimeToken`，调用时读取该
  全局，自动带 `X-LG-Token`；未构建 dist 时提供最小引导页做同样握手。

## 6. 未实测 / 限制

- 未执行 `npm ci`/`npm run build`（无 `node_modules`），静态托管用合成 dist 验证；
  真实 `frontend/dist` 需先 `make frontend-build`。
- 未调用 DeepSeek（按要求至多 1 次且非必要，本次不需要）。
- 默认连接注入 compiler/新 Task 用默认等跨模块行为见 runtime README「已知缺口」，
  属共享文件，需要整合接线，本次未实现。
