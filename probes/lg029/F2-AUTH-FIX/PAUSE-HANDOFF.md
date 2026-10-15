# LG-029 F2 返修 — 暂停保全交接（PAUSE-HANDOFF）

> 状态：**暂停未验（paused-unverified）**。本文件只做保全交接，不是通过/失败结论，不声称 QA / LG-032 通过，不标 `029 done`，产品真实生成请求 **0**。
> worktree：`lightgravity-bot-worktrees/lg029-auth-fix`｜分支 `fix/lg029-auth`｜基点 / HEAD `834b262`（保全前 clean）
> 暂停者：LG029 F2 暂停保全 owner（pi, DeepSeek，仅 PM 协调，无嵌套代理/发布）
> 原 F2 owner：`agent:pi-lg029-auth`（bounded `bounded-rjdj5e5n`），被主代理精确 SIGINT（pid 2090653）中断于 ~250s / exit 143。
> 暂停原因：**资源 owner 协调**——实际改动触及与 F1 runtime owner 交叉的 grant/bootstrap 共享模块（见 §3），须串行；**不是**已通过/失败。

---

## 1. 暂停时精确树状态（无重放、无回滚、无 reset/clean）

`git status --porcelain --untracked-files=all`（保全前）：

```
 M backend/lightgravity/api/app.py
 M backend/lightgravity/api/bootstrap.py
 M backend/lightgravity/api/collaboration.py
 M backend/lightgravity/api/context.py
 M tests/collaboration/test_api_collaboration.py
?? probes/lg029/F2-AUTH-FIX/PLAN.md
?? probes/lg029/F2-AUTH-FIX/STATUS.md
?? probes/lg029/F2-AUTH-FIX/repro_http_auth.py
?? probes/lg029/F2-AUTH-FIX/evidence/http-auth-repro.json
```

- 仅上述 5 个 tracked 文件 dirty + 4 个 F2 自有 untracked 探针文件。无其它未跟踪残留；`probes/lg029/` 其余文件（INTEGRATION/REPORT/STATUS）**未改**。
- 无 `.env`/秘密文件被修改或纳入；`.gitignore` 已忽略 `.env*`/`secrets/`/`bot-data/` 等，本次保全未复制任何秘密。

### sha256（暂停快照）

```
6dd0378f2ca30fbbf47186adb16f81a09e348951b74f254551e6dbff6ff4b09a  backend/lightgravity/api/app.py
2d5a0c1e2176cb37c9eeb87cd927a077f33adfd12a90feea230d50c0304dc58b  backend/lightgravity/api/bootstrap.py
5d081923a628ae3449517438d825ba065d71117359578fc0e23a4d06824c6734  backend/lightgravity/api/collaboration.py
617bb7ec1f797dd7ddf0065a3fa8b873103faacd3279f989e4cedae96cd506b1  backend/lightgravity/api/context.py
056054d80458f43237ebf8613ea88157cef46153b3e28a7065bf7505bcf4a79f  tests/collaboration/test_api_collaboration.py
```

（探针 4 文件的 sha256 见 §6 私有备份 `sha256-dirty-and-probe.txt`。）

---

## 2. 哪些源文件实际仍改动 / 哪些已恢复

| 文件 | 归属 | 实际状态 |
|---|---|---|
| `backend/lightgravity/api/collaboration.py` | **F2 核心**（本包） | 仍改动（+227/-36 附近）：四端点 default-deny + 程序 grant 身份/scope/fence；新增 `resolve_request_grant()`（放在本文件，而**非** PLAN 设想的 `execution_grant.py`） |
| `tests/collaboration/test_api_collaboration.py` | F2 持有 | 仍改动（+309）：改用 grant registry/header 注入，新增未认证/伪造/跨 run/跨 scope/fence/关闸用例 |
| `backend/lightgravity/api/app.py` | **F1 共享 bootstrap/runtime**（越界） | 仍改动：`create_app` 加 `worker_grant` kwarg 并透传 |
| `backend/lightgravity/api/context.py` | **F1 共享 bootstrap/runtime**（越界） | 仍改动：`ApiContext` 加 `worker_grant` + `WorkerGrantResolver` |
| `backend/lightgravity/api/bootstrap.py` | **F1 共享 bootstrap/runtime**（越界） | 仍改动：`build_runtime` 把 `resolve_request_grant` 接入 `worker_grant` |
| `backend/lightgravity/collaboration/execution_grant.py` | **F1 engine（本包不得改）** | **未改**（PLAN step4 曾计划在此加 `resolve_worker_grant`，实际未落地——正是越界回流 API 的点） |

**无文件被回滚/覆盖**；原 tree 全部留原地。

### 越界判定（事实，不预判结论）

PLAN 明确「只改我持有的文件」，并声称为 `execution_grant.py` 加 `resolve_worker_grant`。实际 tree：
- `execution_grant.py` **未动**；
- 新解析器 `resolve_request_grant` 落在 `api/collaboration.py`（F2 文件，可接受）；
- 但 `worker_grant` 接缝被**同时写进** `api/app.py`、`api/context.py`、`api/bootstrap.py` —— 这三个是 F1 runtime/bootstrap 共享模块，`ApiContext.worker_identity` 先例即由 LG-031/F1 拥有。此即「实际修改触及 F1 runtime owner 交叉的 grant/bootstrap 共享模块」，须串行。

---

## 3. 测试真实执行 / 未执行（不重放）

- 发现 `.pytest_cache/v/cache/nodeids`（mtime 2026-10-16 04:54）含 `test_api_collaboration.py` 20 个用例 id，其中有 F2 新增用例名（`test_discoverable_requires_program_grant`、`test_claim_without_grant_default_denies_and_writes_nothing`、`test_renew_cannot_steal_peer_lease` 等）。→ **至少发生过一次 collection**（04:54 前）。
- `.pytest_cache/v/cache/lastfailed` = `{}`（空）。
- **但** F2 测试文件在 04:55:18 又被修改（晚于 04:54 的 cache），最终内容包含 `_mint(..., lease_owner=...)`。
- **签名残留（关键）**：`tests/collaboration/test_api_collaboration.py:120,135` 调用 `registry.mint(..., lease_owner=...)`，而当前冻结源 `backend/lightgravity/collaboration/execution_grant.py::ExecutionGrantRegistry.mint()` **没有 `lease_owner` 形参**（签名止于 `kind`）。同时 stale bytecode `execution_grant.cpython-312.pyc`（mtime 04:53）字符串中含 `lease_owner` / `effective_lease_owner`。→ 曾存在一个带 `lease_owner`/`effective_lease_owner` 的 `execution_grant` 版本被导入，但**当前源不含**。故新测试**不可能对当前冻结源全绿**。
- 因此：**F2 新增/修改测试未被本暂停包重跑，最终结论未知（unknown）**。未运行 `pytest`、未跑 SDK、未跑真实模型或 HTTP 复现。`repro_http_auth.py` 的 evidence JSON 是原 owner 中断前留下的产物，**未复跑、未验证**。

### unknown / 未测

- `resolve_request_grant` + `worker_grant` 接线在真实 `build_runtime` 下是否可 import/无环（`bootstrap.py` 顶部 import `.collaboration.resolve_request_grant`，而 `api/collaboration.py` 模块级 import `..collaboration` engine；需确认无循环导入）——**未验证**。
- 新测试与 `mint(lease_owner=...)` 的签名缺口：未修、未回退。
- F1 的 `dev/lg029@ddab113` 相对 `main` **删除**了 `execution_grant.py`（F1 线尚未含该文件）；F2 依赖的 `default_registry()`/`ExecutionGrantRegistry` 在 `main@834b262` 存在、在 F1 线不存在 → 串行整合时归 F1 定接口。
- mypy cache 有 3.12 目录但**未确认**本次是否针对改动模块运行；不作为证据。

---

## 4. 交给后续唯一串行整合者的依赖 / 剩余

**依赖（必须由 F1 engine/bootstrap owner 提供或确认，本包不接线）：**

1. `execution_grant` 接口：是否需要 `mint(lease_owner=...)` 与 `ExecutionGrant.effective_lease_owner`（测试已引用，当前源缺失）。
2. `ApiContext` / `create_app` / `build_runtime` 的 `worker_grant` 接缝归属：若 F1 决定在 engine 侧提供 `resolve_worker_grant`，应把 `resolve_request_grant` 从 `api/collaboration.py` 移回/对齐，本包的 `app/context/bootstrap` 改动需 F1 串行合并。
3. 契约行为变化（四端点身份由 body→program-grant、`owner` 变可选、未认证返回 `claim_refused/unauthenticated`）需 docs08 owner F1 串行登记（本包按 PLAN 未改 docs）。

**F2 剩余（未完成，勿视为已完成）：**

- PLAN step4（grant 级解析）、step5（context/bootstrap 接线）、step6（collaboration 四端点）代码已落但**未验**；step7（测试）与源存在签名缺口；step8（pytest+mypy）、step9（HTTP 复现）、step10（REPORT+commit）**未完成**。
- 暂停原因与接口需求即本节 1–2；整合者须先与 F1 串行确认 `worker_grant` 接缝与 `lease_owner` 接口，再重跑局部测试。

**明确不在本包内：** 不做 bootstrap 接线修复、不改 F1 engine/`execution_grant.py`、不碰 8123 / F1 worktree / eval / 他包、不 reset/clean、不重放未知副作用、不跑新 pytest/SDK。

---

## 5. 分支 HEAD 未变确认（保全过程）

- 本包 `fix/lg029-auth` HEAD：`834b262`（仅后续 WIP commit 会前进，base 未变）。
- root `main`：`834b262` — **未改**。
- F1 `dev/lg029`（worktree lg029）：`ddab113` — **未改**。
- eval `eval/lg023-cohort2`：`834b262` — **未改**。
- 8123 listener（uvicorn pid 3320750）与 F1/eval 会话进程**未触碰**。

---

## 6. 私有持久备份路径

`/home/yhvh/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/lg029-f2-paused/`

- `tracked-diff.patch` — 5 个 tracked 文件的完整 diff（无秘密）
- `status-porcelain.txt` — 全仓 untracked-all 状态快照
- `sha256-dirty-and-probe.txt` — 5 tracked + 4 探针文件 sha256
- `untracked/F2-AUTH-FIX/` — F2 自有探针目录完整副本（PLAN/STATUS/repro/evidence）
- `HEADS-at-pause.txt` — 本包/root/F1/eval HEAD 快照

不复制 `.env`、`secrets/`、`bot-data/` 或任何密钥。
