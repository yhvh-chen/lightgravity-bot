# LG-050 独立集中版本 QA 报告（共享团队聊天与简单认证）

- QA 执行者：LG-050 独立集中版本 QA 执行者（独立于全部实施者；不返修产品代码、不派工）。
- QA 候选：`feat/team-integration-20261016` @ `2d83263`。
- QA worktree：`/tmp/lg-team-qa-20261016`，分支 `qa/team-chat-20261016`。
- 结论：**PASS_WITH_LIMITATIONS**（全部 LG-050 里程碑验收项通过；无阻断产品缺陷；限制为非阻断文档/语义/环境项，见 §5）。
- 未读取 `.env` 或真实秘密；未调用真实模型；未触碰常驻 `8123` 或任何既有 dataRoot；仅用临时 dataRoot/端口；QA 结束已停止自开服务（`8123` 仍 200，无残留 QA 进程）。

## 1. 证据清单（本目录）

| 文件 | 内容 |
|---|---|
| `qa_http.py` | 独立真实 HTTP 认证/团队聊天矩阵（自起 uvicorn + 临时 dataRoot + 两个独立 cookie jar）。58/58 check 通过。 |
| `qa-http-results.json` | 上述矩阵逐项 machine-readable 结果。 |
| `qa_cli_start.sh` / `qa-cli-start.txt` | 文档化 CLI 建号（`user add`/`list`）+ `lightgravity start` 团队模式单进程启动 + loopback/Host 边界 + 停止；真实输出。 |
| `qa_browser_server.py` | QA 用服务端：候选后端 + 候选 `frontend/dist`（生产构建）同源。 |
| `qa_browser_e2e.mjs` / `run_browser_e2e.sh` | 真实 Firefox 原生 WebDriver BiDi 端到端：两个独立浏览器 user context 登录、A 发普通消息、B 不刷新 3s 轮询看到署名、@bot、退出。 |
| `qa-browser-results.json` / `qa-browser-transcript.txt` | 浏览器 E2E 结果与完整过程记录（含候选服务端启动事实）。 |

本 QA 不修改 `backend/`、`frontend/`、`docs/`、契约或任务状态。

## 2. 方法与边界

- **真实 HTTP**：`qa_http.py` 用真实 socket（`http.client`）对真实 uvicorn 进程发请求，两个账号各自持有独立 cookie jar；没有用 FastAPI TestClient。
- **零模型计数**：QA 侧包裹候选 app 自身的 coordinator（构建在 broadcasting store 上，SSE 事件仍真实故不破坏事件链），用计数 stub 替换 classifier/responder，并用 `UnavailableExecutor` 默认执行器；不接任何模型/SDK。
- **真实浏览器**：用本机 snap Firefox 158 的原生 BiDi（见 `probes/browser-diagnostics` 的可用路径结论），避开了本机 headless Chrome 顶层 `Page.navigate` 到 `http://` 的已知挂起；两个 Firefox user context（容器）验证 cookie 隔离。
- **LAN/SSH 边界**：仅验证默认 loopback 与 Host/Origin 守卫，未做任何 LAN 部署，未放宽允许列表。

## 3. 验收矩阵结果（全部 PASS）

| 验收项 | 证据 | 结果 |
|---|---|---|
| 两账号各自登录、共享群聊、真实作者 | HTTP T01/T04；浏览器 alice/bob 登录 + bob 看到 alice 消息作者 `alice` | PASS |
| 匿名任务/历史/文件下载/资料/搜索/事件均 401 | HTTP T02（`/tasks`、`/conversations/global/messages`、`/files/download`、`/files/content`、`/sources`、`/search`、`/events/stream`、`/settings`、`/resources`） | PASS |
| 旧 `X-LG-Token` 不能绕过 | HTTP T03（匿名带 token 仍 401；member 带 token 仍 403） | PASS |
| member 不能写 settings/resources/credential | HTTP T11（GET/PATCH `/settings`、PUT credential、PATCH `/resources` 全 403；无 secret 文件落盘） | PASS |
| Task `resource_proposal` 间接路径 403 不落写 | HTTP T12（403；消息未持久化；目标资源 404） | PASS |
| forged author 拒绝 | HTTP T05（global 与 task 消息带 `author` 均 422 `extra_forbidden`；未落盘） | PASS |
| 普通消息零 responder/classifier/model | HTTP T06（计数 stub：classifier=0、responder=0；无 Task） | PASS |
| @bot 恰一次触发 | HTTP T07（classifier=1、responder=1、kind=direct）；浏览器 @bot 仅新增 1 条 assistant | PASS |
| 重复 message_id 并发不双回复 | HTTP T08（6 并发同 `message_id`：classifier=1、responder=1、仅 1 行） | PASS |
| 并发普通消息序号不丢 | HTTP T09（24 并发全部落盘、seq 唯一且严格递增） | PASS |
| 游标补齐 | HTTP T10（`after` cursor 仅返回更新消息） | PASS |
| 登出失效 | HTTP T15a-c；浏览器 alice 退出后回到登录门且 bob 会话独立 | PASS |
| 过期失效（含已开 SSE） | HTTP T15d-f（活动 SSE 在会话过期后被撕掉；旧 cookie 401） | PASS |
| 账号哈希文件不能经 Files 读取 | HTTP T13（故意把 workspace 根设成含 `team/` 的 data 根；`/files/content`、`/files/download`、`/files` 列表均被 `path_outside_workspace`/403 拒绝；文件确含 hash+salt） | PASS |
| crossorigin 写拒绝 | HTTP T14（凭证写 Origin=evil → 拒绝；登录 Origin=evil → 403；loopback 登录仍 200）；CLI smoke Host=evil → 400、Origin=evil → 403 | PASS |
| single mode 基本路径不回归 | HTTP T16（`/auth/me`=single authenticated；`/tasks`、`/version` 200） | PASS |
| README/文档命令可建 admin/member 并启动 | CLI smoke：`user add`（getpass stdin）建 alice/bob、`user list` 只列用户名/角色/时间、`start` 团队模式起来、`stop` 释放端口 | PASS |
| 真实浏览器路径 | 浏览器 E2E：2 个独立 user context 登录 → A 发普通消息 → B 3s 轮询（未刷新）看到作者 `alice` → @bot assistant 回复 → alice 退出、bob 会话独立；`ok:true` | PASS |

## 4. 真实证据摘录

- 前端生产构建（QA worktree）：`npm run build` → 107 modules transformed，`dist/index.html` + JS/CSS 产出（构建非功能验收，此处仅证明候选可构建且浏览器加载真实产物）。
- 浏览器 E2E 结果：`qa-browser-results.json` → `ok:true`，`browser=firefox/158.0`，全部子检查 true。
- HTTP 矩阵：`qa-http-results.json` → `checks=58 failed=0`。
- CLI/启动：`qa-cli-start.txt` → 匿名 `/auth/me`=`{"mode":"team","authenticated":false}`；页面 `__LG_RUNTIME_TOKEN__=""`；登录 200；admin `/tasks` 200；匿名 `/tasks` 401；Host=evil 400；Origin=evil 403；stop 成功、端口拒绝连接。

## 5. Non-blocking 观察 / 限制（不洗成通过，也不阻断技术收口）

1. **README 未记录团队模式用法**：README 只有单用户安装/启动；建 admin/member 与 `LIGHTGRAVITY_TEAM_MODE=1` 的命令目前只在 `.env.example` 注释与集成报告里。命令本身实测可用（见 §3），属文档缺口，非产品缺陷。
2. **cross-origin 凭证写返回 401 `unauthorized`（消息 “credential endpoints only accept loopback browser origins”）**，而 cross-origin 登录返回 403 `forbidden`。两者都拒绝且不落写；401/403 的不一致是轻微错误语义不统一，建议后续对齐 `forbidden`，不影响本次验收。
3. **隐藏标签页暂停轮询（by design）**：`useChat` 在 `document.hidden` 时跳过轮询；前台 B 的 3s 轮询验收通过，后台标签页需重新可见后才补齐。属有意行为，记录以免被误读为丢消息。
4. **assistant 持久化作者渲染为小写 `bot`**（author `username:"bot"`），旧/乐观回退为 `Bot`，纯文案大小写差异。
5. **会话在进程内存中**：重启即失效需重登；登录限流为进程内窗口（多进程部署需共享存储）——已在集成报告登记。
6. **本 QA 未调用真实模型/SDK**：零模型结论由计数 stub 证明；`@bot` 走候选内置确定性 responder。因此本报告不声称真实 SDK/模型链路完成（该项不在 LG-050「不需要真实模型」验收内）。
7. **浏览器为同一 Firefox 进程的两个 user context（容器）**，不是两个独立 OS 浏览器进程；cookie/会话隔离已由行为验证（alice 退出不影响 bob）。Chrome 顶层 HTTP 导航在本机挂起，故按既有诊断改用 Firefox BiDi。

## 6. 技术收口建议

- 允许**技术收口**：候选 `feat/team-integration-20261016@2d83263` 的 LG-050 里程碑验收项在独立 QA 下全部通过，无要求返修的阻断缺陷。
- 用户最终验收、合并 `main`、发布与部署均为另行动作，本次不执行。
- 建议（非阻断）后续小任务补 README 团队模式用法并统一 cross-origin 拒绝错误码。
