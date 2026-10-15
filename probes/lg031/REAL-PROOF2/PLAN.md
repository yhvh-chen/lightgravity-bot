---
title: "LG-031 真实工程 proof2 — PLAN（PM 预注册，真实 DeepSeek 冻结验证，第二隔离副本）"
doc_type: plan
category: engineering
owner: "LG031 REAL-PROOF2 owner（pi 现有 DeepSeek；主代理仅 PM；无嵌套派工/推送/部署/发布）"
branch: "dev/lg031-real-proof2"
base: "dev/lg031-real-proof@b819dd3"
source_anchor: "qa/lg032-runtime-r1@26ea945 + main@3797964"
contract: "1.11.0"
sdk: "google-antigravity==0.1.22"
model: "deepseek-v4-flash"
updated: "2026-10-16"
status: "FROZEN-BEFORE-FIRST-REAL-REQUEST"
---

# LG-031 真实工程 proof2 — PLAN

> 本 PLAN 在**任何真实 DeepSeek 生成之前**冻结：fixture / prompt / 工具 / caps / 计划模板 / 初始 commit /
> machine truth / 物理 ledger 路径 / 隔离边界。位置：`probes/lg031/REAL-PROOF2/`。
>
> **本包性质**：这是**另一个明确授权的全新隔离测试副本**（全新 Task/Run/Subtask/ledger/worktree），
> **不是**对旧 failed Run 的恢复/修改，**不自动重放**旧 alpha/beta。旧工程 34 与上次 24（实际 58）**全部保留**，
> 旧 phase 剩余额度**不再消费**。本包只增加**一次**正式 Task 运行与**一个**新的持久物理账本，硬上限 **48**。

## 0. 目标（一句话）

在**真实 DeepSeek provider** 下，用**一次**正式 fixture 运行证明 LG-031 真实工程门：真实至少两个逻辑 worker 在
**程序冻结的多候选实现池**中由模型**通过真实 SDK 工具**自主选择节点（含合法非首项）、程序原子授权并绑定所选节点的
**真实隔离工作区**执行；真实 `verification` 节点**读取两个已通过节点的版本化/hash 上游交接原文**并经真实机器门；
最后真实独立 `ModelReviewer` + 真实 stopgate + 绑定 accept。**沿用同一冻结 3 节点 fixture/计划/requirements/提示模板/
工具/caps/initialcommit/同门**，唯一预算差异 = phase 总生成硬上限 24→**48**。

## 1. 冻结 fixture（首请求前固定，与旧 proof 逐字节同构）

### 1.1 输入 Git fixture（固定初始 commit）

- 全新持久目录 `fixtures/formal/`（**非** TemporaryDirectory，永不自动清除）。
- 一个**空功能仓库** `<formalRoot>/workspaces/task-ws`，其固定初始 commit **只读 clone 自旧 proof 的固定 initial commit**
  `6cf81ea38456b7a0c3c2536b48985d7af3a55f11`（旧 Repo **不改**、不删除、不 reset）：
  - tree 仅 `README.md` blob `3556390bb66a01f7711464a03bf1eb98e5e8ef36`（sha256
    `edd49b5e67e78e5def5894f58c75d1d7f4374c0d86325d3c7f51cc751a64ebf9`），内容精确为 `lg031 real-proof fixture\n`；
  - **无** `out/` 目录、无产物文件；
  - 若只读 clone 不可用则按同一内容重新 `git init` 生成初始 commit，并要求 `git rev-parse HEAD` 与上面一致
    （blob/tree/commit 确定⇒commit hash 一致）；初始 commit hash 在证据中记录。
- `out/` 由模型在执行会话中真实创建（不预建）。

### 1.2 machine truth（独立机器门真值，与旧 proof 相同）

| 节点 | 期望文件 | 期望精确内容 |
|---|---|---|
| `alpha` | `out/alpha.txt` | `alpha`（去尾空白后 == `alpha`） |
| `beta` | `out/beta.txt` | `beta`（去尾空白后 == `beta`） |
| `verify` | 无写入（`write=false`） | 只读记录上游 hash |

- 额外断言：`alpha`/`beta` 产物**各在自己的隔离 worktree**、**不串**；`verify` 无写；`verify` 有 `>=2` 条版本化/hash 上游交接。

### 1.3 冻结计划模板（3 节点，程序校验）— 与旧 proof 逐字节相同

| key | capability | write | depends_on | objective（冻结原文） |
|---|---|---|---|---|
| `alpha` | `implementation` | true | — | `Create out/alpha.txt containing exactly the word alpha.` |
| `beta` | `implementation` | true | — | `Create out/beta.txt containing exactly the word beta.` |
| `verify` | `verification` | false | `alpha`, `beta` | `Read the two upstream artifacts (out/alpha.txt and out/beta.txt) and report their exact contents and upstream hashes.` |

- 两同 capability ready 写节点（alpha/beta）在 Run 起点同时 ready，同属 `implementation` Member 授权池（池大小 2）。
- `verify`（第二 Member，`verification`）依赖 alpha 与 beta，只读。
- `max_parallel` 保持产品默认 **1**；显式开启 `decentralized_claim_enabled=true`。
- 用**真实 `PlanValidator`** 校验、**真实 `GraphDispatcher` + `AntigravityExecutor` + `CollaborationService`** 执行；
  只把「产生 3 节点形状」的 planner 明确替换为程序冻结 `PlanProposal`，**不注入任何假控制状态**。
- 真实模型**自由选择合法候选**，**不**程序预绑定/代选；若真实选首项也照录，不为好看改 prompt。

## 2. 角色与授权（首请求前固定，与旧 proof 相同）

| 角色 | capability | 工具（只读/写边界） | Member |
|---|---|---|---|
| implementation | `implementation` | `view-file` + `create-file`（写 `out/`） | 1 个 Member，授权池 = {alpha, beta} |
| verification | `verification` | `view-file` + `run-command`（只读） | 第 2 个 Member |

- 选择期无写工具：phase-1 选择会话 `allowed_tools=()`，仅附受限 `discover_and_request_claim`。
- 执行期真实绑定：phase-2 由程序按所选 node 构建隔离 git worktree + objective + 上游 hash + 该 node 成员权限。
- 选择提示（冻结原文，与旧 proof 相同）：多候选时优先取实际列表**非首项**以检验合法自由选择。
- 提示模板/工具集/权限与旧 proof `probe_formal_real.py` §`_build_resources`/`FROZEN_SUBTASKS` **逐字同源**。

## 3. 预算/计量（首请求前固定，唯一差异：phase 总上限 48）

- **新增真实 DeepSeek 生成总上限 48**（旧 24 上限 + verify 只读节点所需额外预算）；**仅一次正式 fixture 运行，不重复**。
- 单一**持久实际 `settings.data_dir` / generation ledger**：`<formalRoot>/data/generation/generation.jsonl`；
  全部 selector / execution / 只读验证 / reviewer / 失败 / 返修复验 / 任何 SDK retry 都扣；同一 phase 跨会话/Run **不归零**；
  **转发前持久预留**；损坏**绝不当 0**。
- `HTTP 120s`、`API/SDK retry 0`、并发 `<=2`、每请求 `output <= 12000`。
- 旧 LG031 工程已知 **34（10+14+10）不归零**；上次 proof **24 不归零**；实际旧总数 **58**；旧 phase 剩 6 **不再消费**。
- 新已知整体工程上限 **106**（=58 + 本包 48）；本包**不是** 032 收益 cohort，**不预设省 token**。
- 合法模型失败如实计成本；**harness/计量/重要 source 错误 => STOP 整个 proof**，不边改边重跑、不另建 ledger、不加额救场。

## 4. 观测/原件保全（仅**事前启用既有**保存功能，不改产品行为/不注入上下文）

- 优先通过**既有公开** `profile/context.save_dir`（`SessionProfile.save_dir` / `DispatchContext.save_dir`）把 SDK **原生会话存储**
  放到**私有持久 Root** `<formalRoot>/data/sdk-sessions/`；若 SDK 实际不生成 DB/存储文件，**如实记录「无 SDK DB」**，
  保存全部真正产生的原始事件/输入模板 hash/SoT/输出，**不伪造 SQLite**，**不因数据库不存在而自扩产品**。
- 旧报告「无 SDK DB，`save_dir` 没设」**准确保留**；与旧 proof 的差异记为 **observability**（不注入模型上下文/不改变权限/预算）。
- 所有新 Task/Run/Subtask/SDK 资料/worktree/原始 diff → 持久 `700/600`、输出 create-only。
- SDK 默认 `/tmp` 已知原件**可复制到私有 Root 并存 hash/cmp，但不删除**；**不扫描他人/tmp 用户 DB**。
- 无 `.env`/headers/grant secret 入 repo/提示词/报告；vendor key 只经受控进程 env；不打印 prompt/headers/凭证/敏感 body。

## 5. 0 真实生成预检（先于任何真实模型；复用旧 harness **但新持久位置**）

- 复用真实 SDK 0.1.22 + **本地受控 loopback fake 上游**（provider-substitute；dummy 凭证），走**实际 `build_runtime`/SDK
  + `GraphDispatcher`/`AntigravityExecutor` 生产装配路径**；**独立新持久** `fixtures/precheck2/`（不覆盖旧 fixtures）。
- 通过**实际 `build_runtime`/`create_app` + 真实 `Settings.from_env`**装配三节点与 startup：
  确认 **`configure_generation_ledger(settings.data_dir)`** 生效，**startup 后物理 ledger 路径** == 期望；
  **不可仅 env override 后又被 bootstrap 覆盖**；**所有 roles（worker/verifier/reviewer）指同一个 actual `settings.data_dir`**；
  **不只测 unused helper**。
- `fakeRoot`（`fixtures/precheck2/`）与 `formalRoot`（`fixtures/formal/`）**分开**，不混计数。
- 确认：default `max_parallel=1` 下两个 ready 候选**确可见**且可选**非首项**；正确目标隔离工作区；完整选择/执行 session 历史；
  实际 Verifier stop 门；HTTP 默认拒绝/claim scope/lease owner 保持；**每 stage 开始/结束 ledger count 记录**（默认串行；
  worker+reviewer 计数一致）。
- 全 0 本地 fake 预检输出与源码/hash 固定后**才**调用 DeepSeek。
- 若预检发现**真正 runtime 缺陷**：只最小 repro 报告 PM，本包**不自修行为**，不继续真调用。

## 6. 正式运行（一次）

1. 冻结并记录 code hash / prompt 模板 hash / tool / caps / 计划模板 / 初始 commit / machine truth / ledger 路径。
2. 启动真实 runtime（真实 DeepSeek 配置，`base_url` 指向受控 loopback 认证代理 → DeepSeek 上游）。
3. 驱动单一新 Task/Run：程序校验并冻结计划 → 真实双 worker 自主多候选选择 → 原子授权 → 隔离执行 → verify 交接 →
   机器门 → 真实独立 ModelReviewer → 真实 stopgate → 绑定 accept。
4. 六个选择+执行 session 与 `reviewer_cleanup` 都在 Run/Verifier 真实 stop 门；未停 held、不伪 done、不删 refs。
5. 越 TaskRun/capability/写 scope 不授；fence 与 lease owner 一致；expiry 不重放；不同 node 产物/manifest/交接归正确隔离 workspace。
6. 所有真实 `session_refs`（预期 >= 6）与 `reviewer_cleanup` 参与资源门；正常全停才 `awaiting_acceptance`；
   未交付 diff / refs 历史保留。

## 7. 持久保全

- 所有原始 Task/Run/Subtask/SDK/工件/worktrees/未交付 diff 持久保存于 `fixtures/formal/`（项目旁 proof-data），
  **禁止 TemporaryDirectory 清除 / 输出覆盖**；私有 `700/600` + hash/cmp。`fixtures/*` 的 `rmtree` 重建**不得**用于正式/预检根。
- 仓库仅脱敏摘要/manifest/evidence；**不打印 prompt/headers/令牌/密钥**；**不复制 `.env`**。
- 精准清**自有**进程，不动 8123 / 其它服务。

## 8. 交付

- `probes/lg031/REAL-PROOF2/{PLAN,STATUS,REPORT}.md` + `evidence/**` + `forensics/**` + `precheck2/**` + `fixtures/**`（create-only）。
- 结束时：probes/lg031/REAL-PROOF2/** 先落盘，再精准本地 commit；**不合入 main**；**不 push/deploy/publish/upload**。

## 9. 预算/边界

- wall 1800s / maxround 300 / noncache 420k / idle 240s / 开发 retry 0；单探针 <= 60/90s；formal 整个 fixture 有界 <= 600s 短轮询。
- 普通选择自主推进，不向用户请求重复实施确认。
- 只有 proof 真实同门全齐才 031 `done` 待 032 独立成本 QA；partial 明确缺口；局部 candidate 通过**不**假 done；
  无未来 QA 循环；源新版本行为不变**不**重复全量 pytest/UI 矩阵，仅 harness 必要局部检查与 hash/元数据一致性。

## 10. 与旧 proof 的差异清单（仅列差异，其余同源）

| 项 | 旧 proof | 本 proof2 | 理由 |
|---|---|---|---|
| 生成硬上限 | 24 | **48** | verify 只读节点额外预算（旧 24 在 verify 执行 429 耗尽） |
| 正式运行次数 | 1 | **1** | 不重复 |
| 物理 ledger | `REAL-PROOF/fixtures/formal/...` | `REAL-PROOF2/fixtures/formal/...`（新增） | 全新隔离副本；旧不消费 |
| SDK `save_dir` | 未设（无 DB） | 事前经既有公开 `context.save_dir` 启用；若仍无 DB 如实记录 | observability，不注入上下文/不改权限 |
| fixture 初始 commit | 本包 `_init_git_fixture` 生成 | **只读 clone 旧固定 initial commit** | 保持逐字节同构、不改旧 Repo |
| 其余（计划/fixture/提示/工具/caps/门/初始内容） | — | **逐字节同源** | 同门 |

## 11. 已知旧事实（本包不重放、不修改）

- 旧 24 归因（只读 forensics，`forensics/attribute_old_24.py`）：selection 12（alpha-slot 5 / beta-slot 3 / verify-slot 4）+
  execute 12（alpha 6 / beta 1 / verify 5）；`verify` 执行第 6 次请求在**转发前**被 429 拒绝。
- 根因 = **共享 cap 24 耗尽**（per-session cap 12 **未**触发；`max_session=6`）。
- 旧结论 PARTIAL，**非 runtime 缺陷**（`reserve-before-forward` 与 `corrupt=false` 行为正确）。
