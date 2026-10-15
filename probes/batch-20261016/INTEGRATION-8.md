---
title: "第八批串行集成报告（LG-022 stream 停止接线 + LG-031 r3 闭环）"
doc_type: report
category: engineering
updated: "2026-10-16"
owner: "agent:pi-integration-8"
---

# INTEGRATION-8 — 第八批串行集成（唯一集成 owner）

唯一串行集成 owner（pi + env DeepSeek；主代理只 PM；**无嵌套派工/推送/部署/发布**）。所有源 owner 已退出后才执行。
先读 AGENTS/agent/PROJECT/PROGRESS/BACKLOG/docs06/08、LG-022/031、stream 修复 REPORT、独立调查、phase4/SALVAGE-REPORT，
再核对 Git 分支/worktree/dirty/merge 关系。**全部旧分支/worktree/dirty/原始失败与成本记录保留**，未 reset/clean/重复 pick、未复制 `.env`。

## 0. 结论

- `fix/lg022-stream` 最终 HEAD `7d0510d`（源 owner 已**精确暂存 8 项**本包文件，REPORT 完整落地，**补做唯一收尾 commit**）；
  `fix/lg031-r3` 最终 HEAD `2f04654`（clean，SALVAGE-REPORT 真实恢复硬条件 4 ⇒ LG-031 done 待 032）。
- 二者安全合入 `integrate/batch7` → **`975afc2`**；root PM dirty 先**独立精确提交**（`cef379a`）保全。
- `main` 已**本地快进收拢**至 `975afc2`（不是只停在 integrate 分支）。**未推送**。
- 契约 **保持 `1.10.0`**（两包均无接口/字段/端点/枚举/迁移变化，不机械升版）。产品 SDK `google-antigravity==0.1.22` 不变。
- 本包产品真实模型/外部服务调用 **0**；UI 未改，未重跑整套前端。

## 1. 集成前事实核对（全部真实）

| 位置 | 分支 | HEAD | 状态 |
|---|---|---|---|
| root | `integrate/batch7` | `85adc82` + 主代理 PM dirty `PROGRESS.md` | dirty 必须精确保留 |
| root | `main` | `29ffbb6` | 尚未收拢 |
| worktree `lg022-stream-fix` | `fix/lg022-stream` | `1dd5c67` + **8 项已精确暂存** | 未 commit（本次补做） |
| worktree `lg031-r3` | `fix/lg031-r3` | `2f04654` | clean |

- **签名进程核实**：`ps` 仅见本集成 owner 的 bounded pi 包装进程（命令行与本任务一致：`--wall-seconds 1200 --model-idle-seconds 240 --max-rounds 210 --max-noncache-tokens 280000 --max-auto-retries 0`）；**无源 owner 残留**（stream 实施 owner bounded-`_bxj_bqi` 已于 wall900/exit143 退出，031 r3 owner 前 spwchdnn maxround65/exit143 退出）。
- **022-stream 精确暂存集合核实**：8 项 = `verify/review.py`(M) + `STREAM-STOP-FIX/{PLAN,REPORT,STATUS}.md` + `{continuous_fake_upstream,stream_stop_probe}.py` + `evidence/stream-stop-fix.json` + `tests/verify/test_lg022_stream_stop.py`；无 untracked、无越界文件。REPORT 完整（真 SDK+fakeSSE stop 0.132s confirmed、10 局部 unit、85/134/285 相关回归、mypy 9 通过、产品 DeepSeek 0）。**未重跑任何已通过探针**（不因 wall900 退出把已通过检查当未执行，也不无核假设 commit 存在）。

## 2. root PM dirty 独立保全（精准提交）

- 主代理 root worktree 的未提交 `PROGRESS.md`（core R2 补证 + LG-031 phase4 检查点，+11 行）先**只读复制**私有保全：
  `/home/yhvh/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/PM-PROGRESS-dirty-preserved-85adc82.md`，
  `sha256=73e4fe9e51d16fcc77bc936ef9cd86065c717b8aa22b7662850db5189a43bf94`（与工作树一致）。
- 随后在 `integrate/batch7` **精确提交**为 `cef379a`（仅 `PROGRESS.md`，不 `add -A`，不碰旧 dirty `fix/lg031-r1`）。

## 3. 合入 fix/lg022-stream（局部 verify/review.py SDK 流式 cancel 接线 + 全部 QA 证据）

- 唯一收尾 commit：`7d0510d`（8 文件，1284+/49-；**仅**源 owner 已暂存集合，无新增/遗漏）。
- 产品修复（仅 `backend/lightgravity/verify/review.py`，185+/49-）：把复核运行中 `pause`/`cancel` 的 stop 接到 **SDK 0.1.22 公开取消入口**——
  ① 真正的**流式读取阶段**用「不取消的 pull task + 有界重查」承载 stop（既不关闭共享 cursor、又不丢/不重 chunk）；
  ② stop 命中调 `Conversation.cancel()` + 有界 `wait_for_idle()`，**仅 SDK 确认 idle 才为真**（不假装停止）；
  ③ enter/chat/stream/stop/teardown 收敛到**同一协程/loop**，消除 `__aexit__` 在已关闭 loop 上的偶发 `RuntimeError`。
- 不变量保留：`ReviewStopped` 语义、**未确认不伪 done**、`session_refs` 从不删除、`cleanup` 不伪 `done`、`resource_stop_report.confirmed` 未改。
- 源头合并关系：`1dd5c67` 已把独立 QA `qa/lg022-r2@cea87ab` **仅证据** merge 进 022 分支（clean）。
- **合入方式**：`git merge --no-ff fix/lg022-stream` → `eecbf05`（**无冲突**；其基点 `85adc82` 是 batch7 祖先）。带入 QA 证据（qa/lg022-r2 full harness/evidence）。
- **LG-022 保持 `in-progress`**：旧 `qa/lg022-r2` 的 PASS 标题只覆盖**此前**的持久账本+停止门主链，**不覆盖本次新流式修复的真实上游复验**；最新 `cea87ab` 独立调查已确认**重要缺陷是 stream 阶段没有 cancel/deadlock（叫流式 stop 未接线，不是单纯限制）**。**必须由新独立 QA（`qa/lg022-stream`）复验新流式修复后方可判定**，不被旧 a41 PASS 标题误导。

## 4. 合入 fix/lg031-r3（bootstrap G1/目标投影 G2/预算 proxy 对齐/真实两 worker 链与同次数据恢复）

- 源 HEAD `2f04654`（base `0144eb7`，**非** batch7 祖先 → 存在文档冲突，见下）。
- 产品变更（加性最小）：
  - `adapter/executor.py`：per-session loopback proxy 上限对齐 coordinator 冻结的 `request.budget.max_model_calls`（`min(max_proxy_calls, remaining, request_model_calls)`；未设 budget 时不变），消除「proxy 先 429 掩盖 SDK 真实 `MAX_MODEL_CALLS_EXCEEDED`」缺陷；
  - `api/bootstrap.py`：G1——读取 `decentralized_claim_enabled` 开关，开启才接 `GraphDispatcher(autonomous_claim=True)` + 进程内 `ExecutionGrantRegistry`；关闭/缺省保持旧确定性 `plan_source=rules`、无工具、无 grant；
  - `collaboration/execution_grant.py`：G2——受限 claim 工具发现投影**加性补充**程序拥有的 `objective`/`write`（内部 SDK 工具投影，非 HTTP 契约字段）。
- 证据/探针：`probes/lg031/{phase3,phase4}/**`（离线硬门全绿、真实 RuleBasedPlanner 产品闭环、SALVAGE-REPORT 从存活 SDK session DB **只读**复原硬条件 4 真实原文，原字节未动）。测试：`tests/adapter/test_lg031_r3_generation_ceiling_alignment.py`、`tests/collaboration/test_lg031_r3_product_path_closure.py`、`tests/collaboration/test_lg031_r4_real_planner_closure.py`、`tests/startup/test_lg031_r3_bootstrap_autonomous.py`。
- docs08：仅**加性实现说明**「产品路径自主 claim 接线（1.10.0，无版本/字段/端点变化）」。
- **冲突处理（唯一 owner）**：`PROGRESS.md` 内容冲突——r3 分支的检查点覆盖了 root 的新状态；本包**同时保留双方**：root batch7 最新状态（INTEGRATION-7 + PM 检查点 `cef379a` 内容）**与** r3 的 phase3/phase4/SALVAGE 检查点。其余文件自动合并、无冲突。
- `.gitignore` 扩展覆盖 phase4 的瞬时账本锁，并从提交中移除 0 字节 `generation-budget.lock`（运行时产物，非证据；phase3 已同样处理）。
- **LG-031 置 `done`（待 LG-032 独立集中 QA）**：SALVAGE-REPORT 按 docs08 §6.3 冻结口径判定硬条件 1–7 在**真实单次运行证据**上全部成立（硬条件 4 的版本化/带 hash 交接真实原文已复原、diff `@sha256:820a554a…` 离线重算 match）。**不制造待 032 循环**、未降低任何门、未伪造证据。残余 `content_hash` 原始字节随临时目录删除为**已记录事实/保全缺口**，如实披露。

### 4.1 幸存 SDK DB/stdout 无秘密保全（只读，已由独立只读包完成）

- 3 个 google-antigravity SDK session DB + 原运行 stdout 已由**独立只读保全 pi** 复制到**私有持久**目录：
  `/home/yhvh/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/lg031-phase4-survivors/20261016T040115+1100/`（目录 `700`、文件 `600`）。
- 本包**独立复核**：4 个 `sha256` 与 `MANIFEST.sha256` 及 `salvaged_handoff_evidence.json` 记录**逐一相符**，且与 `/tmp` **原件 `cmp` 字节相等**；原件 `/tmp` **未移动/未删除**。
- **未重新复制/删除/运行模型**；**不入 repo 秘密原件**；`SUBTASK.md` 原始字节丢失的限制如实保留。

## 5. 集成检查（真实退出码，绑定 `975afc2`）

| 命令 | 退出码 | 结果 |
|---|---|---|
| `.venv/bin/python -m mypy` | **0** | **Success: no issues found in 137 source files** |
| `.venv/bin/python -m pytest -q -p no:randomly` | **0** | **794 passed, 2 skipped**（82.49s） |
| `tasks validate <backlog>` | 0 | **ok=true, 41 tasks, 0 diagnostics** |
| `tasks digest <backlog>` | 0 | **complete=true → 33 done / 3 in-progress / 5 todo** |

- **UI 未改** → 未重跑完整前端。**本包产品真实模型/外部服务调用 0**；API 重试 0。
- 2 个 skip 为条件门 gated 真实检查（沿用既有），非失败。

## 6. 状态如实（不自判核心/去中心化/材料全门 pass）

- **LG-022 `in-progress`**：新流式修复待**独立 QA `qa/lg022-stream`**（新持久 worktree），不被旧 a41 PASS 标题覆盖。
- **LG-031 `done`（待 LG-032 独立集中 QA 复验版本级行为）**：不因未来 QA 制造循环。
- **LG-023/032 `todo` 未 claim**（023/032 依赖 LG-022 尚未 done，**不 claim**，保留后续步骤）。
- **LG-035/037 `in-progress`**（真实质量/端点不可达，不假 done）；**LG-040 不解锁**；**LG-041 质量门阻塞不解锁**。
- **自主模式默认 off**；不重新引入模型编排；去中心化仅在开关开启时启用（缺省确定性路径）。
- 保留：1.10 持久账本为唯一生成限额事实源、全部停止确认、非空 session 历史、token/pin/证据授权/验收幂等/反重放；1.9 资料 archive/search/vector/UI 语义。

## 7. 成本账本（全部旧失败/成本保留，不重置/不洗白）

- **LG-022**：首轮 QA 真实总数 **unknown**；R1 **6/10**；`qa/lg022-r2` 真实主链 **8**（主链 7 + 直答 1，**两阶段使用不同账本**，未执行统一总额硬限——**不是**产品持久账本缺陷）。两轮失败记录保留（`probes/lg022/REPORT.md`、`probes/lg022/reverify-r1/REPORT.md`）。
- **LG-031**：旧 24（原 1 + R1 3 + R2 6 + phase3 14）+ phase4 **10** = **累计 34/40**（全局已知工程累计，不重放、不归零）；usage `unknown` 不当 0。
- **本包真实模型调用 0**（产品真实请求 0）。

## 8. 新独立 QA worktree（供独立复验，本包不执行 QA/不调用模型）

- 经 `git worktree add -b qa/lg022-stream /home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-stream main` 基于**最终 main 候选 `975afc2`** 创建；**不覆盖任何旧路径**（旧 `lg022-qa-r2` 等全部保留）。
- QA 最小清单（交独立 QA owner）：
  1. 真实（或受控真 SDK）主链中复核运行中 `pause`/`cancel` 在 `stop_timeout` 内真实停止 reviewer 并 `confirmed`，`session_refs` 保留、无残留 reviewer。
  2. `verifying` 下 pause 两步落位；cancel 直接 `cancelled`；未确认保持 `cancelling`/`pausing` 且不释放槽。
  3. 自动复核路径 `run.reviewer_cleanup.status=done` 仅在真实 teardown 事实存在时写入；失败保持 `pending`/unconfirmed。
  4. 无 stop 的正常成功 review 仍完整 drain 且 teardown confirmed（无回归）。
  5. 契约仍 `1.10.0`，无新增端点/字段/枚举。

## 9. 分支与候选（最终）

| 用途 | 分支 | HEAD | 说明 |
|---|---|---|---|
| main（本地收拢） | `main` | `975afc2` | 已快进收拢，**未推送** |
| 集成候选 | `integrate/batch7` | `975afc2` | 与 main 同点 |
| 022 流式修复 | `fix/lg022-stream` | `7d0510d` | 唯一收尾 commit |
| 031 r3 | `fix/lg031-r3` | `2f04654` | clean |
| **新独立 QA** | `qa/lg022-stream` | `975afc2` | worktree `lg022-qa-stream` |
| QA 证据源（旧） | `qa/lg022-r2` | `cea87ab` | 仅证据，保留 |

- 未 push/deploy/发布；旧 dirty `fix/lg031-r1` 未碰；主 worktree uvicorn(:8123) 未 kill/复用 dataRoot。
