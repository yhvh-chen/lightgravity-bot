# LG-020 — Runtime 启动与本地分发

本包（`lightgravity.runtime`）与 `lightgravity.api.bootstrap`、`lightgravity.cli`
是 LG-020 新增的**本地启动/分发接线**，不修改冻结的 `api/app.py`、`api/context.py`
以及 `adapter/`、`coordinator/`、`verify/` 既有实现。装配只通过公开的
`create_app(...)` 注入。

## 入口

```bash
# 单命令前台启动（默认 loopback），构建过前端时同进程托管 frontend/dist
uv run lightgravity start

# 指定隔离的 data / workspace / secret 目录
uv run lightgravity start \
  --data-dir ./bot-data --workspace-root ./bot-data/workspaces --secret-store ./secrets

# 后台启动（日志在 <data-dir>/logs/lightgravity.log），status / stop 配套
uv run lightgravity start --daemon
uv run lightgravity status          # 进程 + /api/v1/health
uv run lightgravity status --deep   # 额外输出执行就绪报告
uv run lightgravity stop            # SIGTERM，必要时 SIGKILL，并清理 pid 记录

# 显式、幂等的最小资源初始化（不提供 --connection-id 时不写任何配置）
uv run lightgravity init --connection-id primary --credential-ref worker-key \
  --agent-id developer --set-worker-default
```

`python -m lightgravity ...` 与安装后的 `lightgravity` / `lg` 控制台脚本等价。
`make lg-start / lg-start-daemon / lg-status / lg-stop / lg-init` 是等价封装，
`make serve` 先构建前端再启动。

## 装配内容（复用正式组件，未创建第二套）

- `lightgravity.store.FileStore`：`LIGHTGRAVITY_DATA_DIR` / workspace 隔离；
- `lightgravity.settings`：`FileSecretStore` + `ConnectionService` + `ConnectionTester`
  （Settings 写/测试/默认连接走同一权威文件，秘密只在受控 store/env）；
- `lightgravity.adapter.AntigravityExecutor`：正式 DeepSeek loopback 认证代理，
  凭证解析走 settings 层 `credential_resolver`；缺凭证/缺模型时返回
  `capability_unavailable`/`config_invalid`，不崩溃也不伪造成功；
- `lightgravity.coordinator.GraphDispatcher`：真实 planner/recruiter/scheduler 接入
  executor；默认**不保留** `UnavailableExecutor` 假入口（仅 `--no-executor` 或装配
  异常时降级，并在健康/报告中如实标记）。

## 认证握手与访问边界

- 每个服务进程生成随机 `X-LG-Token`（也可由 `LIGHTGRAVITY_RUNTIME_TOKEN` 注入）；
  只保存在进程内存。
- 静态前端由同进程托管：请求 `index.html`（或 `dist` 缺失时的最小引导页）时把
  token 注入 `window.__LG_RUNTIME_TOKEN__`，响应带 `Cache-Control: no-store`；
  不写 URL、日志、`localStorage`/`IndexedDB`，也不落盘。前端 `auth.ts` 已在调用
  时读取该全局，Settings 写接口自动带 `X-LG-Token`。
- 敏感写（`/api/v1/settings` 的 POST/PUT/PATCH/DELETE）默认拒绝（401
  `unauthorized`），只有携带正确 token 才通过；不存在开放默认值的旁路。
- `HostGuardMiddleware`：默认只接受 loopback / `testserver` / 显式
  `LIGHTGRAVITY_ALLOWED_HOSTS` 的 `Host`；带 `Origin` 时其 host 也必须在允许集合内。

## 就绪语义

`execution_report()`（`status --deep`/启动输出）区分事实，而不是笼统“可用”：

- `executor_wired`：adapter+GraphDispatcher 是否真实装配；
- `agent_refs`：启用的 agent 资源（role catalog 由此派生）；
- `default_worker_connection_ref` 与 `credential_configured`；
- `execution_ready` 只有在四者齐备时才为 true；否则给出具体 `reasons`。

缺认证/runtime 时历史（`GET /tasks`）与 Settings 读取仍可用，执行明确不可用。

## 目录/配置

- 运行时数据：`--data-dir`（默认 `./bot-data`，gitignore），pid 记录在
  `<data-dir>/runtime/lightgravity.json`（不含秘密），后台日志在 `<data-dir>/logs/`。
- 秘密：`--secret-store`（默认 `./secrets`，gitignore）。
- 前端：`--frontend-dist`（默认 `./frontend/dist`），`--no-frontend` 只起 API。
- 其它环境变量示例见根 `.env.example`（不读取/不回显真实 `.env`）。

## 已知缺口 / 需要整合的共享接线

以下不属于 LG-020 文件归属，本次**未实现**，列出以免误认为已齐备：

1. **默认连接自动注入 compiler**：`ConnectionService.resolve_default` /
   `pin_connection` 已存在，但 `adapter/compiler.py` 仍在 agent 缺少
   `connection_ref` 时直接 `connection_missing`，`coordinator` 也尚未把
   `default_worker_connection_ref` 固定到成员。要满足“新 Task 用默认、活跃成员
   保持旧配置”，需在 compiler/GraphDispatcher 侧接线（共享文件，需整合）。
2. **仅通过 Settings 创建连接后仍无 agent**：首版 Settings 只创建/编辑
   connection；`lg init` 才会写最小 agent。若产品希望“配好模型即可执行”，需要
   由整合决定是在 Settings 保存后生成默认 agent，还是保留显式 `lg init`。
3. **`frontend/dist` 未构建**：本包只做托管与 token 注入；仓库当前无
   `node_modules`/`dist`，未在本次执行 `npm ci`。真实前端一体验证需先
   `make frontend-build`。
4. Files/资源视图等大组件是否齐备由各自任务负责，本包不做“假齐备”声明。
5. `store/protocol.py` 的 `Store.create` 增补可选 `body` 参数（与 `FileStore`
   实际签名对齐的加性共享变更），需整合确认。

## 测试

`tests/startup/`：token 不落盘、Host/Origin 守卫、SPA 托管与 token 注入、默认
拒绝敏感写、缺凭证/缺 executor 的就绪报告、幂等 init、真实子进程
start→status→stop 往返。运行：

```bash
uv run pytest tests/startup -q
uv run mypy
```
