# LG-050 串行集成报告（共享团队聊天与简单认证）

- 执行者：LG-050 串行集成执行者（非 PM，不派工）。
- 集成 worktree：`/tmp/lg-team-integration-20261016`，分支 `feat/team-integration-20261016`，从 `main` `0ecfec8` 创建。
- 合并来源：
  - `feat/team-backend-20261016` @ `1df7310`（含最终测试提交；此前 `5ea956f` 已先合，`1df7310` 再合入）。
  - `feat/team-frontend-20261016` @ `26dc6f4`。
- 两分支均基于 `main` `d873a36`；PM 的 `0ecfec8`（docs08 `1.13.0`、§14、PROJECT/BACKLOG/LG-050）在集成侧保留。
- 全程未读取 `.env`、未调用真实产品模型、未触碰常驻 `127.0.0.1:8123`（pid 3320750）或现有 `bot-data`。

## 1. 公开契约与实现版本统一 `1.13.0`

- `backend/lightgravity/contracts/constants.py`：`CONTRACT_VERSION` 由 `1.12.0` 升为 `1.13.0`，并加 `1.13.0` 注释；`tests/contracts/test_contracts.py` 同步断言。
- `docs/08-interface-contract.md`：§13 新增 `1.13.0` 行；§14 标题由“接口冻结、实施中”改为“实施完成待独立 QA”，补记实际实现偏差（`forbidden`、登录限流 429、logout 幂等、admin-only 范围、SSE 会话存活性、Files 保护、显式三态 auth probe）；§12 清单当前版本改为 `1.13.0`。
- `README.md`：当前版本与 docs 引用由 `1.12.0` 更新为 `1.13.0`，加一句 LG-050 进展；历史大段版本记录保留不改。
- `.env.example`：新增 LG-050 团队模式段（开关、账号文件、TTL、cookie Secure、bot mention，及交互式建号命令）。
- `docs/06-roadmap.md`：§0 LG-050 注记由“当前实施中”改为“实现完成、集成候选待独立 QA”。
- `PROJECT.md`：在既有 LG-050 决策条下追加短进展（候选分支、契约、局部检查、待 QA）。

## 2. 后端局部集成检查（未重复后端全量 pytest）

后端执行者已跑全量 `pytest`（见 [backend-execution-report.md](backend-execution-report.md)：**978 passed / 5 skipped**）与 `mypy`（145 files clean）。集成侧只做有意义的定向复跑：

```bash
cd /tmp/lg-team-integration-20261016
PYTHONPATH=backend /home/yhvh/code/lightgravity-bot/.venv/bin/python -m pytest tests/team tests/contracts -q
# -> 51 passed
```

含新增 `test_files_cannot_read_team_accounts_even_inside_workspace`（`1df7310`）。

## 3. 前端类型 / 测试 / 构建

```bash
cd /tmp/lg-team-integration-20261016/frontend
npm run typecheck     # -> pass
npx vitest run        # -> 16 files / 131 tests passed
npm run build         # -> tsc + vite build pass (107 modules, dist/ emitted)
```

（为运行而临时软链主目录 `frontend/node_modules`，未安装/升级依赖；提交前删除。）

### optimistic auth probe 修复

前端报告的“初始 probe 期间乐观渲染单用户工作台”已修：`AuthProvider` 现为显式三态。

- `checking`：只渲染 Loading，**不挂载工作台也不显示登录表单**。
- `error`（网络/5xx/未知 mode）：渲染可重试错误（`ErrorState` + Retry 重新探测），**不降级为单用户**。
- `ready`：仅 `mode:"single"` 或 legacy `404` 进单用户工作台；`mode:"team"` 未登录进登录门，已登录进工作台。
- 单用户真实功能保留；旧 shell/smoke 测试改为 await 真实门控后的挂载（不牺牲门控换同步显示）。新增 3 个 probe 状态测试。

## 4. 真实后端 + built 前端接口对齐冒烟

专用端口 `8791`、专用数据根 `/tmp/lg-team-int-data`、`--no-executor`、`LIGHTGRAVITY_TEAM_MODE=1`，使用 `frontend/dist`。

真实账号创建（口令经 `getpass`，不进 argv/日志）：

```bash
export PYTHONPATH=backend
PY=/home/yhvh/code/lightgravity-bot/.venv/bin/python
printf '<admin-password>\n<admin-password>\n' | $PY -m lightgravity.cli user add --username alice --role admin --data-dir /tmp/lg-team-int-data
printf '<member-password>\n<member-password>\n' | $PY -m lightgravity.cli user add --username bob  --role member --data-dir /tmp/lg-team-int-data
$PY -m lightgravity.cli user list --data-dir /tmp/lg-team-int-data   # 只列 username/role/created_at
```

`accounts.json` 权限实测 `0700` 目录 / `-rw------- 0600` 文件，无明文/哈希输出。

启动与核对（curl 实测）：

| 请求 | 结果 |
|---|---|
| `GET /api/v1/version` | `contract_version:"1.13.0"` |
| `GET /api/v1/auth/me` 匿名 | `{"mode":"team","authenticated":false,...}` |
| `GET /api/v1/tasks` 匿名 | 401 |
| `GET /api/v1/settings` 匿名 | 401 |
| `GET /`（SPA） | 200；内联 `__LG_RUNTIME_TOKEN__=""` |
| 错误口令登录 | 401 |
| admin 登录 / `/auth/me` / `/tasks` / `/settings` | 200；`{"mode":"team","authenticated":true,"username":"alice","role":"admin"}` |
| member 登录 / `/tasks` | 200 |
| member `/settings` | 403 `forbidden` |
| member `PATCH /resources/...` | 403 |
| 全局消息带客户端 `author` | 422 `validation_failed`（`extra_forbidden`） |
| 全局普通消息（`message_id`+`content`） | 200 `kind:"recorded"`、`reply:null`、`data.creates_task:false` |
| 读取全局消息 | item.message 内 `author:{kind:"user",username:"bob",role:"member"}`；同 `message_id` 重发幂等（不重复落盘） |
| `@bot ...` | 200 `kind:"direct"`（走既有路由，无真实模型调用、无 Task） |
| 匿名带 `X-LG-Token` 访问业务 | 401（token 不构成团队身份） |
| `POST /auth/logout` / 之后带旧 cookie | 204 / 401 |

服务用 `lightgravity stop`（SIGTERM）确认停止，端口释放；常驻 8123 未受影响。

## 5. 远程访问核实（默认 loopback，不偷偷放开 host）

实际机制：`--host` 决定绑定地址（默认 `127.0.0.1`）；`HostGuardMiddleware` 只接受 loopback、`testserver`，以及显式配置的 `--allow-host <host>` / `LIGHTGRAVITY_ALLOWED_HOSTS`（逗号分隔）。因此**其他电脑默认不可访问**；要开放必须同时①绑定可达地址（如 `--host 0.0.0.0`）并②把对方使用的 Host 显式加入允许列表，同源 `Origin` 也须匹配。本集成**未**放宽任何 host 允许列表。

额外限制：`settings/router.py` 的 `_require_loopback_origin` 对凭证/Settings 敏感写**只接受 loopback 浏览器 origin**。所以即使开放了 LAN host，管理员在远端浏览器配置模型/凭证仍会被拒。

推荐共享方式（不改变默认安全边界）：服务端保持 loopback，其他电脑用 SSH 隧道，使浏览器 origin 保持 `127.0.0.1`，凭证端点亦可正常：

```bash
# 在服务器上（默认 loopback 启动团队模式）
LIGHTGRAVITY_TEAM_MODE=1 uv run lightgravity start \
  --data-dir ./bot-data --workspace-root ./bot-data/workspaces \
  --secret-store ./secrets --host 127.0.0.1 --port 8000
# 在每台客户端
ssh -L 8000:127.0.0.1:8000 <server>     # 然后浏览 http://127.0.0.1:8000
```

若确需 LAN 绑定，必须显式同时设置 `--host <可达地址>` 与 `--allow-host <客户端使用的 Host>`；这是有意的双开关，不是默认放开所有 host。

## 6. 已知限制与未验证项

- 会话在服务端进程内存中，重启即失效需重登；登录限流为进程内窗口（多进程部署需共享存储）。
- 团队全局消息同步为约 3s 轮询既有读取接口（非新增 SSE）；页面隐藏暂停，401 回登录门。
- 普通消息零模型/零 Task；`@bot` 才走既有分类路由。`X-LG-Token` 在团队模式不授权。
- 真实浏览器端到端（双窗口互见、断线重连、窄屏）**未执行**，按派工留给独立 QA。
- 未合回 `main`、未发布/部署；**未宣称 QA 通过**。

## 7. 本地启动命令（真实可用）

```bash
# 0) 依赖
uv sync

# 1) 交互式建号（口令走 getpass，不进 argv/日志）
uv run lightgravity user add --username alice --role admin  --data-dir ./bot-data
uv run lightgravity user add --username bob   --role member --data-dir ./bot-data
uv run lightgravity user list --data-dir ./bot-data

# 2) 团队模式启动（默认 loopback）
LIGHTGRAVITY_TEAM_MODE=1 uv run lightgravity start \
  --data-dir ./bot-data --workspace-root ./bot-data/workspaces \
  --secret-store ./secrets --host 127.0.0.1 --port 8000
# 浏览器打开 http://127.0.0.1:8000/ 登录；普通消息共享，@bot 触发助手
```

单用户模式：不设 `LIGHTGRAVITY_TEAM_MODE`，行为与既有版本一致（`/auth/me` 返回 `mode:"single"`）。
