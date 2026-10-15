---
title: "LG-031 真实工程 proof — PLAN（真实 DeepSeek 冻结验证）"
doc_type: plan
category: engineering
owner: "LG031 接口冻结/真实工程 proof owner（pi 现有 DeepSeek；主代理仅 PM；无嵌套派工/推送/部署/发布）"
branch: "dev/lg031-real-proof"
base: "qa/lg032-runtime-r1@26ea945 + merge main@3797964"
contract: "1.11.0"
sdk: "google-antigravity==0.1.22"
model: "deepseek-v4-flash"
updated: "2026-10-16"
---

# LG-031 真实工程 proof — PLAN

> 本 PLAN 在**任何真实 DeepSeek 生成之前**冻结：prompt / tool / caps / 计划模板 / 初始 commit / machine truth / code hash /
> 物理 ledger 路径。位置：`probes/lg031/REAL-PROOF/`。

## 0. 目标（一句话）

在**真实 DeepSeek provider** 下，用**一次**正式 fixture 运行证明 LG-031 真实工程门：真实至少两个逻辑 worker 在**程序冻结的
多候选实现池**中由模型**通过真实 SDK 工具**自主选择**非首项**节点、程序原子授权并绑定所选节点的**真实隔离工作区**执行；
真实 `verification` 节点**读取两个已通过节点的版本化/hash 上游交接原文**并经真实机器门；最后真实独立 `ModelReviewer` +
真实 stopgate + 绑定 accept。**不是** 032 成本对照，不冒称自动规划质量。

## 1. 冻结 fixture（首请求前固定）

### 1.1 输入 Git fixture（固定初始 commit）

- 全新持久目录 `fixtures/formal/`（**非** TemporaryDirectory，永不自动清除）。
- 一个**空功能仓库** `<formalRoot>/task-ws`，初始固定 commit：
  - `README.md` 内容精确为 `lg031 real-proof fixture\n`；
  - **无** `out/` 目录、无产物文件；
  - 初始 commit hash 在 PLAN/证据中记录（`git rev-parse HEAD`）。
- `out/` 由模型在执行会话中真实创建（不预建）。

### 1.2 machine truth（独立机器门真值）

执行完成后，独立机器门（不依赖 reviewer 结论）核对：

| 节点 | 期望文件 | 期望精确内容 |
|---|---|---|
| `alpha` | `out/alpha.txt` | `alpha\n`（去尾空白后 == `alpha`） |
| `beta` | `out/beta.txt` | `beta\n`（去尾空白后 == `beta`） |
| `verify` | 无写入（`write=false`） | 只读记录上游 hash |

- 额外断言：`alpha` 与 `beta` 产物**各在自己的隔离 worktree**、**不串**（alpha 内容不得出现在 beta worktree，反之亦然）。

### 1.3 冻结计划模板（3 节点，程序校验）

计划由**程序冻结**并用真实 `PlanValidator` 校验，随后由真实 `GraphDispatcher` 执行（**不是**默认 `RuleBasedPlanner`，理由见 §1.3.1）：

| key | capability | write | depends_on | objective（冻结原文） |
|---|---|---|---|---|
| `alpha` | `implementation` | true | — | `Create out/alpha.txt containing exactly the word alpha.` |
| `beta` | `implementation` | true | — | `Create out/beta.txt containing exactly the word beta.` |
| `verify` | `verification` | false | `alpha`, `beta` | `Read the two upstream artifacts (out/alpha.txt and out/beta.txt) and report their exact contents and upstream hashes.` |

- **两个同 capability ready 写节点**（alpha/beta）在 Run 起点同时 ready，二者同属 `implementation` Member 授权池（池大小 2）。
- `verify` 依赖 alpha 与 beta 两者，是**第二个 Member**（`verification`），只读（`write=false`）。
- `max_parallel` 保持产品默认 **1**；默认自主模式开关按本 proof 显式开启 `decentralized_claim_enabled=true`（否则无多候选池）。

#### 1.3.1 为何使用程序冻结的 3 节点计划（首请求前写明实际理由，非规避）

- 任务要求「固定最小 3 节点合法计划：alpha/beta 两个同 capability ready 写节点 + verify 只读节点依赖两者」，且明确
  「计划强制拆分仅用于工程能力证明，不冒称自动规划质量」。
- 产品默认 `RuleBasedPlanner` **只生成 1 个 implementation 节点 + 可选 1 个 verification 节点**（deliver+verify），
  无法提供「同一 capability 的两个 ready 写节点」以检验「模型在多候选中选**非首项**」。这是一个**计划形状**限制，不是产品缺陷。
- 因此本 proof 使用**与法定 planner 等价最小 fixture**：计划仍由程序生成、经**真实 `PlanValidator`** 校验、由**真实
  `GraphDispatcher` + 真实 `AntigravityExecutor` + 真实 `CollaborationService`** 执行；仅把「产生 3 节点形状」的 planner 明确替换为
  程序冻结的固定计划（`PlanProposal`），**不注入任何假控制状态**（节点/租约/grant/交接/状态均由产品真实产生）。
- **同等门不做删减**：真实双 worker、非首项选择、隔离绑定、版本化交接、机器门、独立 reviewer、stopgate、绑定 accept **全部保留**，
  不擅自少测非首项或交接。

## 2. 角色与授权（首请求前固定）

| 角色 | capability | 工具（只读/写边界） | Member |
|---|---|---|---|
| implementation | `implementation` | `view-file` + `create-file`（写 `out/`） | 1 个 Member，授权池 = {alpha, beta} |
| verification | `verification` | `view-file` + `run-command`（`cat`/`sha256sum` 只读） | 第 2 个 Member |

- **选择期无写工具**：phase-1 选择会话 `allowed_tools=()`，仅附受限 `discover_and_request_claim`。
- **执行期真实绑定**：phase-2 由程序按**所选 node** 构建隔离 git worktree + objective + 上游 hash + 该 node 成员权限。
- 选择提示（冻结，写入 selection objective）：多候选时优先取实际列表**非首项**以检验合法自由选择；**不程序预绑定、不代模型选、不写死动态 ref 绕 discovery**。

## 3. 预算/计量（首请求前固定）

- **新增真实 DeepSeek 生成总上限 24**；**仅一次正式 fixture 运行，不重复**。
- 单一**持久实际 `settings.data_dir` / generation ledger**（`<formalRoot>/data/generation/generation.jsonl`）；全部 selector /
  execution / 只读验证 / reviewer / 失败 / 返修复验 / 任何 SDK 重试都扣；同一 phase 跨会话/Run **不归零**。
- `HTTP 120s`、`API/SDK retry 0`、并发 `<=2`、每请求 `output <= 12000`。
- 旧 LG031 工程已知 **34（10+14+10）不归零**；新已知整体工程上限 **58**；旧 phase 剩 6 **不再消费**。
- 普通合法模型失败按事实计成本；**harness/计量/重要 source 错误则停止此 proof**，不边改边重跑或新 ledger 归零。

## 4. 0 真实生成预检（先于任何真实模型）

- 复用真实 SDK 0.1.22 + **本地受控 loopback fake 上游**（provider-substitute；dummy 凭证；全 role loopback），
  走生产 `build_runtime`/`GraphDispatcher`/`AntigravityExecutor` 路径；**独立新持久 fixture/counter**。
- 确认：default `max_parallel=1` 下两个 ready 候选**确可见且可选非首项**；正确目标隔离工作区；完整选择/执行 session 历史；
  实际 Verifier stop 门；HTTP 默认拒绝/claim scope/lease owner 保持。
- **真正 startup 后** runtime 账本物理路径与 PLAN 一致（不因 env pin 被 bootstrap 覆盖）；所有 role 包括 reviewer 读同一 **actual** phase `settings.data_dir`。
- `fakeRoot`（`fixtures/precheck/`）与 `formalRoot`（`fixtures/formal/`）**分开**，不混计数。
- 若预检发现**真正 runtime 缺陷**：只最小 repro 报告 PM，本包**不自修行为**，不继续真调用。

## 5. 正式运行（一次）

1. 冻结并记录 code hash / prompt / tool / caps / 计划模板 / 初始 commit / machine truth / ledger 路径。
2. 启动真实 runtime（真实 DeepSeek 配置，`base_url` 指向受控 loopback 认证代理 → DeepSeek 上游）。
3. 驱动单一新 Task/Run，程序校验并冻结计划 → 真实双 worker 自主多候选选择 → 原子授权 → 隔离执行 → verify 交接 → 机器门 →
   真实独立 ModelReviewer → 真实 stopgate → 绑定 accept。
4. 所有选择+执行真实 `session_refs`（预期 >= 6）与 `reviewer_cleanup` 参与资源门；正常全停才 `awaiting_acceptance`；
   未交付 diff / refs 历史保留；**不伪 cleanup done / 不降机器或独立 review 门**。

## 6. 持久保全

- 所有原始 Task/Run/Subtask/SDK/工件/worktrees/未交付 diff 持久保存于 `fixtures/formal/`（项目旁 proof-data），
  **禁止 TemporaryDirectory 清除 / 输出覆盖**；私有 700/600 + hash/cmp。
- 仓库仅脱敏摘要/manifest；**不打印 prompt/headers/令牌/密钥**；**不复制 `.env`**。
- 精准清**自有**进程，不动 8123 / 其它服务。凭证只现有 env 受控使用，不切供应商/模型。

## 7. 交付

- `probes/lg031/REAL-PROOF/{PLAN,STATUS,REPORT}.md` + `evidence/**` + `precheck/**` + `fixtures/**`（create-only）。
- 结束时：probes/lg031/REAL-PROOF/** 先落盘，再精准本地 commit；**不合入 main**；**不 push/deploy/publish/upload**。

## 8. 预算/边界

- wall 1800s / maxround 300 / noncache 420k / idle 240s / 开发 retry 0；单探针 <= 60/90s；formal 整个 fixture 有界 <= 480s 短轮询。
- 只有 proof 真实同门全齐才 031 `done` 待 032 完整成本 QA；partial 明确缺口；不因未来 032 循环等待，也不因局部 candidate 通过假 done。
