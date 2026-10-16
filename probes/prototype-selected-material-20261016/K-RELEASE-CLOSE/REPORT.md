# REPORT — K-RELEASE-CLOSE：selected-material 原型 PM/docs 集成闭环

- 日期：2026-10-16
- 角色：root PM（**仅项目管理文档与 probe**；**零产品代码改动、零网络、零模型/浏览器调用、零测试、零依赖变更、无 push/deploy、不触 `8123`**）
- 任务：**LG-049《验证选定资料交付完整生命周期》闭环 + LG-047 里程碑独立 QA 闭环**（parent 关系：LG-049 `parent: LG-047`）；`assignee` 历史保留
- 结论：**两个任务据实际完整证据置 `done`**（LG-049 PASS_WITH_LIMITATIONS；LG-047 命名里程碑据此闭环）；`LG-041` 保持 `todo`/阻塞不变；CLI 实测 **49 tasks / 0 diagnostics / 48 done / 0 in-progress / 1 todo / ready=[]**

> 本报告只记录**本轮 PM 实际执行的动作与实测事实**。不宣告用户最终验收、不宣告部署/发布、不宣告累积成本已知。全部历史失败/成本记录保留。

---

## 1. 前置复核（关闭前实际核对，非仅报告转述）

关闭前，root PM 依据**跨分支原始事实**核对 N-R3-LIFECYCLE（LG-049，owner `agent:pi-proto-lifecycle-qa`，独立于全部产品实施者）：

| 前置要求 | 实际核对来源 | 结果 |
|---|---|---|
| 独立 QA 实际 PASS_WITH_LIMITATIONS | `probes/.../N-R3-LIFECYCLE/REPORT-N-R3-LIFECYCLE-20261016.md` | ✅ PASS_WITH_LIMITATIONS |
| 真实 SDK 文件产物 6 事实 | `evidence/sdk_lifecycle.json` `facts_all_present=true`、`facts_found` 6/6；工作区 `orion-summary.md` | ✅ 6/6 全对 |
| `verify` SDK 节点真实执行 | `events/task_*/events.jsonl`：`subtask B running→verifying→passed`；`node_states.verify=passed` | ✅（R2 曾 429 处本轮通过） |
| 真实 ModelReviewer | 事件 `error.recorded mode=review reviewer_kind=model model_calls=1 outcome=passed` | ✅ 模型复核者 |
| worker/reviewer stop CONFIRMED | `RUN.md` `cleanup.status: done`、`reviewer_cleanup.{status:done,confirmed:true,agent_closed:true,proxy_stopped:true}`；事件 `member.released` | ✅ accept 前 |
| API accept → done | 事件 `task.phase_changed verifying→awaiting_acceptance`（stop 后）→ `completed`；`TASK.md status:done/phase:completed/acceptance.status:accepted`；accept HTTP 200 `confirmed=true` | ✅ |
| 账本 cap16 未扩展 | 产品 `generation.count.json={"count":8}`；campaign `count.json={"count":8}`、`manifest.json cap=16` | ✅ 8/16 |

**复核中注意到的诚实细节（不改结论，记录以备审阅）**：`evidence/sdk_lifecycle.json` 的 `stop_facts` 快照在**采集时点**读到 `worker_cleanup_status: "pending"`、`worker_stop_confirmed: null`、`reviewer_is_model: false`；这是该快照在 accept 前瞬时字段读取的时序产物。**权威事实**以 `RUN.md`（worker `cleanup.status=done`、reviewer `confirmed=true`）与 `events.jsonl`（`member.released` + `cleanup.updated scope=reviewer confirmed=true` + `error.recorded reviewer_kind=model`）为准，两者均支持报告结论。报告在 §4.3 已自行披露 `history.jsonl` 首次追加的 node 标签顺序已由 `reconciliation_correction` 更正，未掩盖。

---

## 2. 本次执行的唯一工作：`--no-ff` 串行合并（probes/docs only）

- **源**：`qa/proto-material-lifecycle-r3-20261016` @ **`dc1a1b222a6ed06e478a541771161d1e76ff30b1`**（N-R3-LIFECYCLE probe/scripts/ledger）。
- **合并**：`git merge --no-ff qa/proto-material-lifecycle-r3-20261016` → 合并提交 **`76f10c7c155c6d132b6a8c91b4fc40ed87684bc2`**（父 `096d796a26098f103091d171da1111848604945e` + `dc1a1b222a6ed06e478a541771161d1e76ff30b1`）。
- **冲突处理（PM 文档变更，非代码）**：源分支相对 `main` 的唯一非 probe 差异是 `backlog/tasks/LG-049.md`（源分支缺少 `main@096d796` 追加的 R3 验证记录）。合并**保留 `main` 的 LG-049 验证记录**，仅引入 `probes/prototype-selected-material-20261016/N-R3-LIFECYCLE/**`。**无代码冲突、无测试弱化。**
- **产品树冻结校验（合并后实测）**：`backend`/`frontend`/`tests`/`examples` 树哈希与 `0188ca2` **逐字节一致**（§3）。

---

## 3. 最终 `main` / 产品哈希 / 源 heads（精确记录）

### 3.1 最终 `main`
- 合并后 HEAD：**`76f10c7c155c6d132b6a8c91b4fc40ed87684bc2`**（另有本轮 PM/docs 提交，见 §7 最终 HEAD）。
- 工作树：clean。

### 3.2 产品树哈希（`main` == `0188ca2` == 冻结 QA 产品）
| tree | hash |
|---|---|
| `backend` | `8b4256a412cccd010dcbbfd9966f9530413c4172` |
| `frontend` | `07618bb29bed372f47422b584070101196ce86bc` |
| `tests` | `9a37448e61af6023d0306c59067864c9ae8b31cc` |
| `examples` | `63ee05cd045a4233f28205c182d798d114f2f910` |

`main`、QA R3 分支（`dc1a1b2`）、冻结候选 `0188ca2` 四树逐字节相同 ⇒ **J（分类器修复）之后产品代码未再变**。

### 3.3 源 QA 分支 heads（显式记录，全部保留未改）
| 分支 | head | 内容 |
|---|---|---|
| `qa/proto-material-20261016` | `57809d4` | R1 FAIL |
| `qa/proto-material-r2-20261016` | `a9ba494` | R2 FAIL/INCOMPLETE（已并入 main `256cd78`） |
| `qa/proto-material-route-r2-20261016` | `11b5848` | L routing PASS（已并入 main `d8d8b4e`） |
| `qa/proto-material-lifecycle-r3-20261016` | `dc1a1b2` | N-R3-LIFECYCLE PASS_WITH_LIMITATIONS（**本轮并入 main `76f10c7`**） |

历史 `fix/proto-material-classifier-r2-20261016` @ `2352c52`（J）不变；I-R2 `a9ba494` 的 FAIL 记录保留未改。

---

## 4. 真实检查（本轮 closer 自身不发起产品测试/模型/网络）

- **本轮 closer 自身调用**：产品前向请求 **0**、模型调用 **0**、浏览器 **0**、网络 **0**、新测试 **0**、依赖变更 **0**。
- **复用（非重跑）**：N-R3-LIFECYCLE 的真实 SDK 生命周期证据（8/16 前向：deliver 2 + verify 5 + reviewer 1）；I-R2 真实 UI 证据（上传→原生提取→选材→真实 DeepSeek 回答→Sources→reload→宽度 390/1024/1440，过渡 overshoot 0，绑定前端树 `07618bb2…` 与冻结一致）；L routing PASS（绑定 backend `8b4256a4…`，与冻结完全相同）；H 的 mypy（139 files clean）与 pytest（930 passed / 2 skipped）。
- **本轮实际运行的只读命令**：`git merge/diff/rev-parse/ls-tree`、`node olav-tasks/dist/cli.js tasks validate/digest/ready backlog`、读取 raw/evidence/RUN.md/events 与文档。无产品运行。
- **前端**：本轮**未构建前端**（仅 PM/docs），未跑浏览器；UI 事实以 I 的真实证据 + 相同前端树哈希绑定，不新增声明。

---

## 5. 实际调用计数 / 账本（不猜测、不宣称全生命周期精确成本）

- **R3 `N-R3-LIFECYCLE`**：产品持久账本 `generation.count.json={"count":8}`；独立 campaign `count.json={"count":8}`、`manifest.json` cap **16**、`history_lines=8`、`remaining=8`。**cap 未扩展**。
- **R2**：actual **8**（cap 8，已耗尽，不可重跑），单列保留。
- **R1**：已知 **1** 次真实请求 + **账目缺口**（原 12 次 campaign 全程未核实），单列保留。
- **本轮 closer**：新增 **0**。
- **成本**：产品 `usage:{unknown:["usage"]}` ⇒ token/cost **unknown，非 0**。**不宣称全生命周期总调用上界或精确成本已知。**

---

## 6. 限制与未宣称项（保留，不洗白）

1. **累积成本 unknown 非 0**；不据此推断收益或上界。
2. **浏览器 UI 证据为复用**（前端未构建；前端树 `07618bb2…` 与冻结一致），本 campaign 本体为 API 级生命周期。
3. **未重跑全量测试**（产品代码零改动，遵“不为纯复用重跑全量”）。
4. **`/artifacts/content?evidence_ref=orion-summary.md` 裸名返回 400** 属端点契约（要求 `evidence:run/name@sha256:hex`），deliverable 经授权工作区 + diff refs 判定，非产品缺陷。
5. **R3 只证明本次 cap16 下 R2 的 429 未复现**（实测 8/16），**不**推断所有预算情形。
6. **用户 QA fixture accept ≠ 用户最终验收**：本轮为技术性 QA；用户最终验收仍待定，未部署/未发布。

---

## 7. 本轮 PM/docs 提交与最终 HEAD

- 合并提交：**`76f10c7c155c6d132b6a8c91b4fc40ed87684bc2`**。
- PM/docs 提交：添加本报告的 PM/docs 提交（`git log -1 --format=%H -- probes/prototype-selected-material-20261016/K-RELEASE-CLOSE/REPORT.md` 可查其真实哈希；该提交即本轮 PM/docs 变更，包含 LG-047/049 置 done + PROJECT/PROGRESS/BACKLOG/docs06/docs10/docs11 当前快照更新）。
- **最终 `main` HEAD**：本报告所在的 PM/docs 提交（`git rev-parse main`），`main` 工作树 clean、无未提交改动。
- 无 reset/stash/clean；全部其它分支/worktree/raw ledger 保留。

### 7.1 本轮修改的 PM/docs 文件
- `backlog/tasks/LG-047.md`：`status: done`（+闭环验证记录；历史记录保留）。
- `backlog/tasks/LG-049.md`：`status: done`（+root PM 闭环复核记录）。
- `PROJECT.md`：更新**当前快照**为 49 任务（旧 41 任务历史快照明确标注为历史，删除误导性“当前”表述）；保留历史失败/成本记录。
- `PROGRESS.md`、`BACKLOG.md`、`docs/06-roadmap.md`：当前里程碑/任务计数更新为 49/48 done/1 todo/0 in-progress。
- `docs/10`、`docs/11`：更新为**已实测原型**事实（R3 生命周期实际通过 + 保留限制）。
- `probes/prototype-selected-material-20261016/K-RELEASE-CLOSE/REPORT.md`（本报告）。

---

## 8. 自身进程停止声明

- 本轮 closer 为 Claude Code 会话内 root PM，**未启动任何长期产品进程/worker/QA 进程**，无残留进程需停止。
- 不触 `8123`；不 push/deploy；不杀 inflight；不改任何活动 worktree/campaign/ledger。

---

## 9. 结论

- **LG-049 置 `done`**（PASS_WITH_LIMITATIONS，实际完整生命周期证据支撑）。
- **LG-047 命名里程碑独立 QA 置 `done`**（据 N-R3-LIFECYCLE 实际证据闭环；历史 R1/R2 FAIL 保留）。
- **LG-041 保持 `todo`**（质量门阻塞），`LG-048` 保持 `done`。
- CLI 实测：`validate` **49 tasks / 0 diagnostics**；`digest` **48 done / 0 in-progress / 1 todo**；`ready=[]`。
- 产品树 `main` == `0188ca2`；用户最终验收、部署、发布仍待定。
