---
title: "LG-031 REAL-PROOF2 — REPORT（真实 DeepSeek，单次正式运行，隔离第二副本）"
doc_type: report
category: engineering
owner: "LG031 REAL-PROOF2 owner（pi 现有 DeepSeek；主代理仅 PM；无嵌套派工/推送/部署/发布）"
branch: "dev/lg031-real-proof2"
base: "dev/lg031-real-proof@b819dd3"
source_anchor: "qa/lg032-runtime-r1@26ea945 + main@3797964"
contract: "1.11.0"
sdk: "google-antigravity==0.1.22"
model: "deepseek-v4-flash"
updated: "2026-10-16"
---

# LG-031 REAL-PROOF2 — REPORT

## 0. 一句话结论

在**真实 DeepSeek** provider 下执行**唯一一次**正式 fixture：真实双逻辑 worker 经产品 `GraphDispatcher` 候选池两阶段
生命周期，真实模型通过 SDK 工具 `discover_and_request_claim` 领取节点，各自写出精确产物 `out/alpha.txt`=`alpha`、
`out/beta.txt`=`beta`（各自隔离 worktree、无串），`verify` 节点**真实接收两个已通过节点的版本化/hash 上游交接**（4 条 ref），
真实独立 `ModelReviewer` **真实运行并通过**（`reviewer_kind=model`，`validated_outcome=passed`），真实 stop 门
`confirmed=true`（6/6 停止、proxy 停止）。**但** 正式 harness **未**驱动产品 `verify_and_prepare`/accept 绑定路径
（inherited harness 只手动写 `phase=verifying` + 运行 review），因此 **gate 7「绑定 accept」未达**。
按预注册「仅一次、不重复、不归零」与「harness/装配错误 ⇒ STOP 整个 proof」，本包记录为 **PARTIAL**：
门 1–6 PASS，门 7 因 **harness 装配缺口（非 runtime 缺陷）** 未达。LG-031 保持 **in-progress**。

## 1. 预注册事实（首请求前冻结）

| 项 | 值 |
|---|---|
| HEAD | `ed770a3`（预注册）/ harness `fce51ced…`；产品树相对 R1 已验 `afcae82` 仅 `contracts/constants.py` + 契约测试的**版本 metadata** 变化 |
| 源锚 | `qa/lg032-runtime-r1@26ea945`（R1 独立 813/5 等四门 PASS）+ `main@3797964` |
| SDK | `google-antigravity==0.1.22`（`installed_sdk_version()` 实证） |
| 实际模型 | `deepseek-v4-flash` @ `https://api.deepseek.com/v1`（env 凭证，不打印/不落盘） |
| PLAN hash | `37c339da8d2749555594e62061eefa369baed5f63341a99cde589d3c9d6926d3` |
| **protocol hash** | `155e1cc0896207848b44080ac51c2a05679bc54ed8d9a96bc620e406641bc025` |
| formal harness hash | `fce51ced98b7a9df8d2dd36a56cf9867ade1dfc145392ed970655299423b1db0` |
| validated plan hash | `37e5c771a7e1c9c41543180e71b79e08de79205fa687cfcca3385a00137b8e8e`（与旧 proof 正式一致） |
| ledger 路径 | `probes/lg031/REAL-PROOF2/fixtures/formal/data/generation/generation.jsonl`（持久） |
| caps | 真实生成 **48**；HTTP 120s；retry 0；并发 <=2；output <=12000 |
| 初始 commit | `6cf81ea38456b7a0c3c2536b48985d7af3a55f11`（**只读 clone** 自旧固定 commit，旧 Repo 未改） |
| SDK save_dir | `.../fixtures/formal/workspaces/.lg-sdk-sessions`（既有公开 `context.save_dir`；旧 proof 未设） |

## 2. 真实运行数据（`evidence/formal-real2.redacted.json`；私有原始 `fixtures/raw-evidence/formal-real2.raw.json`）

- Run `run_01M50GARZGSWF8KVJM2PVRZWWC`，Task `task_01M50GARZ7FDBC1YR46TCFMM18`。
- 真实生成请求：**28 / 48**。其中 worker dispatch 阶段 27（harness 在 `result.update` 时快照得
  `ledger_snapshot{count:27,limit:48,remaining:21}`），随后真实独立 `ModelReviewer` 追加 **1** 次真实调用；
  持久物理账本 `generation.jsonl` 最终 **28** 条 `reserved`（`count.json=28`），`persistent=true`、`corrupt=false`、
  `limit=48`、`remaining=20`。**以机器账本为准**。
- 真实 SDK 会话：**6**（3 选择 + 3 执行：alpha/beta/verify），全部进入真实 Run `session_refs`（`sessions_in_run_refs=true`）。
- 真实工具调用 **35** 次（含 `discover_and_request_claim`×6、`edit_file`/`view_file`、受限 `request_peer`×3）。
- `adapter.error` **0** 条（无 429 / 无异常）。
- 真实 stop 门：`confirmed=true`，`sessions_stopped=6/6`，`proxy_stopped=true`。
- elapsed：**91.267s**（< 600s 有界）。
- **未**触达 `awaiting_acceptance`（见 §4）。

## 3. 逐门结果

| 真实门 | 结果 | 证据 |
|---|---|---|
| ① 真实至少 2 逻辑 worker | **PASS** | 2 实现节点 `passed`，同 `implementation` Member 两次 claim（各 `fence=1`） |
| ② 候选池 >=2 且可选非首项 | **PASS（能力）** | 预检证池 `[alpha,beta]` 可见、非首项可选；正式真实模型自由领取（未程序预绑定/代选） |
| ③ 所选 node 真实隔离执行 + 精确产物 | **PASS** | alpha/beta 各在自己的 `.lg-worktrees/<run>/<key>` worktree；`alpha_exact/beta_exact=true`、`no_cross_contamination=true` |
| ④ verify 接收版本化/hash 上游交接 | **PASS** | `verify.upstream_artifact_refs` 4 条（alpha+beta，各含 artifact ref + `@sha256:` diff 证据） |
| ⑤ 真实独立 ModelReviewer | **PASS** | `reviewer_kind=model`、`outcome=passed`、`validated_outcome=passed`、`model_calls=1`；真实 DeepSeek |
| ⑥ 真实 stopgate | **PASS** | `confirmed=true`、6/6 stopped、`proxy_stopped=true` |
| ⑦ 绑定 accept | **未达（harness 装配缺口，非 runtime 缺陷）** | harness 未驱动产品 `verify_and_prepare`/accept；run 仍 `executing`，task `verifying`，`acceptance.status=pending` |

**机器门（独立于 reviewer）**：`alpha_exact=true, beta_exact=true, no_cross_contamination=true, verify_no_write=true,
verify_has_two_handoffs=true, all_nodes_passed=true` ⇒ **`pass=true`**。

## 4. 门 7 缺口性质（STOP 条件，如实记录）

- **现象**：正式 harness `probe_formal_real2.py`（继承旧 `probe_formal_real.py`）在 `dispatcher.dispatch` 完成后，
  仅由 `writer.write_task(phase="verifying", acceptance=…)` **手动**写 task 阶段，并调用 `_review_sync`（真实 reviewer）。
  它**从未**调用产品 `VerificationService.verify_and_prepare`（真实机器检查 + 真实 stop 门 + `_open_acceptance` 候选绑定），
  也**未**绑定 human accept。
- **结果**：task `phase=verifying`、`acceptance.status=pending`（含 `evidence_refs` 但**无** `candidate_ref`/`candidate_plan_hash`/`check_records`）；
  run 仍 `state=executing`、`cleanup.status=pending`。**未**进入 `awaiting_acceptance`。
- **最小 repro（0 额外真实生成）**：对**同一持久候选**离线调用产品
  `VerificationService(...).verify_and_prepare(task_id)`（真实 `StoreResourceStopper`）→ 返回
  `state=unconfirmed, confirmed=False`，`problems=["run … is still in active state 'executing'",
  "6 session(s) not confirmed closed (cleanup='pending')"]`。该调用**未**改变 task/run 状态
  （task revision 4、run revision 17 不变；仅追加一条 `data/coordinator/requests.jsonl` 幂等条目）。
- **性质**：这是 **harness/装配缺口**——产品具备完整 accept 绑定路径（`verify_and_prepare` → `_open_acceptance`），
  harness 未接；**不是** runtime 缺陷。产品的 `verify_and_prepare` 对未停止 Run 返回 `unconfirmed` 是**正确**的保守行为。
- **处置**：按预注册「harness/装配/计量/重要代码错误 ⇒ STOP 整个 proof，不改后重跑」，本包**停止**，
  **不**就地修补 harness 后重跑，**不**新账本、**不**加额。single formal run 已消费 27/48，如实记录。

## 5. 真实自由选择

- 正式真实模型**自由领取**节点（`discover_and_request_claim`×6），**未**程序预绑定/代选。
- 预检已证池 `[alpha,beta]` 两候选可见且非首项可选（fake 脚本化）；正式由真实模型自主决定。

## 6. observability 差异（如实记录，不注入上下文/不改权限）

- 旧 proof「**无 SDK DB**，`save_dir` 没设」事实**准确保留**。
- 本包事前经**既有公开** `context.save_dir` 把 SDK 原生会话存储放到私有 Root
  `.../fixtures/formal/workspaces/.lg-sdk-sessions`；SDK **真实生成 6 个 SQLite trajectory DB**
  （`file` 实证 SQLite 3.x；含 `trajectory_meta`/`steps` 等表）。**真实产生、未伪造**。
- 该差异仅为 observability：不注入模型上下文、不改变权限/预算/门。

## 7. 持久原件（私有，create-only，700/600）

- 全部产品 SoT：`fixtures/formal/data/{tasks,runs,subtasks,members,events,artifacts,generation,settings,locks,coordinator}/**`。
- 真实 worktree 与未交付 diff：`fixtures/formal/workspaces/.lg-worktrees/<run>/{alpha,beta,verify}/**`。
- SDK 原生会话 DB：`fixtures/formal/workspaces/.lg-sdk-sessions/*.db`（6 个）。
- 私有原始证据：`fixtures/raw-evidence/formal-real2.raw.json`（306KB，600，含 model text；**不提交**）。
- 脱敏 evidence（提交）：`evidence/formal-real2.redacted.json`（model text/prompt/tool-args 已剥离；无 headers/凭证）。
- 旧 worktrees/dirty/日志/文件**全部保留**；未读无关/tmp 用户数据；未复制 `.env`；未触碰 8123/其它服务。

## 8. 计费/计量

- 本包真实生成 **28**（唯一正式运行：27 worker dispatch + 1 reviewer）；预检/dry-run 均为本地 fake 上游（**0 真实**），fakeRoot/formalRoot 分离。
- known token：SDK 事件未暴露 token 明细，如实记 **unknown**（不当 0）。reviewer usage `{"unknown":["usage"]}`。
- 旧 LG031 工程 **34（10+14+10）不归零**；上次 proof **24 不归零**；旧实际总数 **58**；旧 phase 剩 6 **不再消费**。
- 本包 +28 ⇒ 新已知整体工程实际约 **86**；预注册上限 **106**（=58+48），本包未超（remaining 20）。
- 非 032 成本对照，不预设省 token。

## 9. 状态与后续（交 PM）

- **LG-031 保持 `in-progress`**：门 1–6 真实 PASS，门 7（绑定 accept）因 **harness 装配缺口**未达（非 runtime 缺陷）。
- **最小后续（PM 决策，不在本包自修）**：在 harness 中于 `dispatch` 后接入产品真实
  `Verifier.stopgate`（`StoreResourceStopper(session_confirmer=executor)`）+ `verify_and_prepare`（run→verifying→awaiting_acceptance
  候选绑定）+ human `accept`；此路径为**确定性、0 模型生成**，可作为**单独**授权的收口步骤；本包**不**擅自动手。
- **LG-032** 保持 `in-progress`（阶段 B 暂停，依赖 031 真实门）。
- 本包**不合入 main**；HEAD/契约/protocolhash/真实次数见 STATUS；**无 push/deploy/publish/upload**。
