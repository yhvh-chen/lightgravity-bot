---
title: "LG-031 phase4 — SALVAGE-REPORT（同次运行证据恢复：硬条件 4 真实原文已复原，无新模型调用）"
doc_type: report
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg031-r3"
branch: "fix/lg031-r3"
base: "8073830"
---

# LG-031 phase4 — SALVAGE-REPORT

- Owner：`agent:pi-lg031-r3`（pi + env DeepSeek；主代理只 PM；**无嵌套派工/推送/部署/发布**）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg031-r3`（branch `fix/lg031-r3`）。
- 起点：HEAD `8073830`，**clean**（仅 2 个未跟踪文件：本包恢复脚本与恢复 JSON）。
- 本包任务：**同一次已完成真实运行的只读证据恢复与契约判定**，**不重跑真实 fixture、不新增模型调用**。
- 事实源优先级：**原始产品证据（surviving SDK session DB + 原 stdout） > 恢复 JSON（机器生成） >
  文档叙述**。恢复 JSON 中任何**仅从 prompt 文本重建**的字段标 `derived` 并分级。

## 0. 一句话结论

phase4 的**硬条件 4「受控带 hash 同伴交接」的真实原文**在**同一次**运行（`run_01M5079F4W8V37RHRTN7W6WWV6`）
中**真实存在且可复原**：目标 `verify` 节点收到的**产品构建**请求 prompt 内含版本化交接
`subtask_01M5079F7MS9XM6AJRDJD4D7HM@1a6053…a64d:…`，且 diff 证据引用带独立
`@sha256:820a554a…` 并**离线重算匹配**。**已按 docs08 冻结契约判定：该交接满足硬条件 4**，
此前 REPORT 的「必须重跑 ≈10 转发」结论被本恢复**取代**。真实调用**新增 0**，全局累计仍 **34/40**。

## 1. 前 owner 停止与技术状态核实（不改旧）

- **前 owner 停止**：前 spwchdnn 在 `maxround 65` 停止，进程 `exit 143`（被终止）。**现在无残留进程**
  （`ps` 仅内核线程；无 pi/worker/python 探针存活）——无未知副作用在跑，无需 kill。
- **HEAD / dirty**：HEAD `8073830`（phase4 诚实 partial 提交），工作区**仅** `salvage_handoff_evidence.py`
  与 `evidence/salvaged_handoff_evidence.json` 两个未跟踪文件；未 reset/clean/覆盖任何旧记录。
- **旧资源未触碰**：旧 24 请求账本、`probes/lg031/{R1,R2,phase3}`、旧 dirty/worktree、主 worktree
  uvicorn(:8123)、022 worktree 全部原样保留。
- **本包范围**：仅 `probes/lg031/phase4/**` 与 LG-031 记录；**产品代码不改**。

## 2. 恢复路径与原数据保全（read-only）

前 owner 已定位：真实运行的 `data/`/`workspace`/`store`/`worktrees` 在 `tempfile.TemporaryDirectory`
内，随探针退出**被删**；但**同次运行**的 google-antigravity **SDK session 存储**写入 `$TMPDIR/antigravity_*`
并**存活**。本包核实其**仍在**并只读提取：

| 原件 | 路径 | 状态 | 只读校验 |
|---|---|---|---|
| deliver worker session | `/tmp/antigravity_285smjk4/58500ca6….db` | **存活** | `sha256=385d861d…249a`（与恢复 JSON 一致） |
| verify worker session | `/tmp/antigravity_82urbszj/aae0af78….db` | **存活** | `sha256=3214d2dc…7628`（一致） |
| reviewer session | `/tmp/antigravity_7qlg37q5/3f9db899….db` | **存活** | `sha256=18a3dd55…3135`（一致） |
| 原运行 stdout | `/tmp/phase4_run_stdout.txt` | **存活** | `sha256=0f428ce5…bd99`，4656 B（一致） |
| 持久生成账本 | `probes/lg031/phase4/ledger/generation/` | 存活 | `count=10, limit=16, remaining=6` |

- 提取方式：`sqlite3 connect file:…?mode=ro`，**只读**；**未写回原 store、未补写字段、未编造收据**。
- 恢复脚本 `salvage_handoff_evidence.py` 重跑**确定性一致**（同一 JSON）；原始证据字节**未改**。
- **unknown 费用**：worker/reviewer usage 仍 `unknown`（不当 0）；本恢复**不产生**任何新转发。
- **TemporaryDirectory 缺口已记录**（见 §5），未重跑旧已发生写入。

## 3. 读到的原件与契约判定（docs08 冻结口径）

### 3.1 docs08 冻结契约（判定依据，不改契约）

- §6.3 Subtask：`upstream_artifact_refs`（加性）；**「依赖放行必须传递上游产物引用与版本/哈希」**；
  `fence` 单调递增，**产物交接**须校验 `fence == 当前 fence`（否则 `stale_lease`）。
- §6.3 `evidence_refs` 解析：executor 产物导入 `<data_dir>/tasks/<task_id>/artifacts/<run_id>/` 并记为
  canonical `evidence:<run_id>/<name>@sha256:<hex>`；workspace 产物为**相对授权 workspace 根**路径，
  **不要求**其自身带 `@sha256:`（§6.3 明确区分两类命名空间）。
- §8 `ExecuteRequest`/`ExecutorResult`：`upstream_artifact_refs` 由协调器构造并传入 worker。
- **判定原则（按用户要求，不自加门）**：**不**要求「每个单文件都须独立 hash」；但**也**不能仅凭
  「deliver 先于 verify」就推断受控交接。必须看到**产品构建的版本化/带 hash 上游引用**。

### 3.2 真实交接原文（verify 节点产品 prompt，`derived` 自 session 文本，分级=原日志级）

verify worker session（`/tmp/antigravity_82urbszj/…db`）的**首步产品请求 prompt**含：

```
Upstream artifacts:
- subtask_01M5079F7MS9XM6AJRDJD4D7HM@1a60539e58a045065adb2c46c1b957b2fd50dc1679eaf2baaf5efe074eeaf64d:out/deliver.txt
- subtask_01M5079F7MS9XM6AJRDJD4D7HM@1a60539e58a045065adb2c46c1b957b2fd50dc1679eaf2baaf5efe074eeaf64d:evidence:run_01M5079F4W8V37RHRTN7W6WWV6/subtask_01M5079F7MS9XM6AJRDJD4D7HM-lg006-diff.patch@sha256:820a554a18070c0c19ea9a79d8230727a183b6b6c7288f3077a4480f9c907714
独立验证：Create the file out/deliver.txt with exactly the single line: delivered
```

- 形态 = 冻结 `<subtask>@<content_hash>:<artifact>`（**源节点 + 版本/content_hash + 目标产物**）。
- **源节点** `subtask_01M5079F7MS9XM6AJRDJD4D7HM` 与 **目标节点** `subtask_01M5079F7MJ6AFWJ8NF1HH7ZB6`
  均为同 run 真实节点。
- diff 证据引用带**独立内容摘要** `@sha256:820a554a…`，**离线重算匹配**（69B excerpt，见 §4）。
- `out/deliver.txt` 为 **workspace 相对产物**，**按 §6.3 不带** `@sha256:` 是**契约正确**，非缺口；
  其内容由 diff patch（`+delivered` at `out/deliver.txt`）与 subtask content_hash 覆盖。

### 3.3 源/目标/版本与授权（真实产品证据）

| 事实 | 真实值 | 来源 |
|---|---|---|
| 源节点 capability/objective/write | `implementation` / "Create the file out/deliver.txt…delivered" / `true` | deliver session 发现投影 |
| 源节点授权 | `reason=granted, fence=1, node_ref=…D7HM, request_id=claim_196f…` | deliver session 工具响应 |
| 目标节点 capability/objective/write | `verification` / "独立验证：…delivered" / `false` | verify session 发现投影 |
| 目标节点授权 | `reason=granted, fence=1, node_ref=…7ZB6, request_id=claim_a593…` | verify session 工具响应 |
| 目标 workspace | `/tmp/tmp839xikyn/workspaces/candidate-ws`（候选隔离 worktree） | verify session tool_call |
| 版本/content_hash | `1a6053…a64d`（承接于版本化交接 ref） | verify prompt Upstream 块 |

- **fence 校验**：源/目标授权均 `fence=1`（程序原子授权，脱敏；`grant_receipt_has_token=false`）。
- **无全局 token**：`sandbox_set_has_secret=false`；receipt 无 bearer。

### 3.4 reviewer 与候选（真实，独立 hash）

- reviewer session（`…7qlg37q5`）产品 prompt 的证据头为 2 条：
  `out/deliver.txt` 与 `evidence:run_…/…-lg006-diff.patch@sha256:820a554a…`。
- reviewer 判决：`outcome=passed`、`validated_outcome=passed`、`model_calls=1`、
  `usage={"unknown":["usage"]}`；`findings=[]`。
- 候选（`candidate_ref=run_01M5079F4W8V37RHRTN7W6WWV6`）**完整可复源**（diff + workspace 文件）。

## 4. 离线 hash 核对（read-only，无模型）

- diff patch 引用 `@sha256:820a554a18070c0c19ea9a79d8230727a183b6b6c7288f3077a4480f9c907714`。
- 从 reviewer prompt 重取 patch 正文（69B）并重算 `sha256` = **820a554a…0714**，**match=true**。
- `out/deliver.txt` 正文 excerpt = `delivered\n`（与 objective 一致；真实内容，非占位）。
- 三个 session DB 的 `sha256` 与恢复 JSON 记录**逐一相符**（§2 表），证明恢复未篡改原始字节。

## 5. 缺口与残余（诚实，不伪造）

1. **同 run 的 `data/`/`store`/`worktrees` 已被 `TemporaryDirectory` 删除**——这是**取证保全缺口**：
   探针用临时目录，未持久化运行目录。**本包不重跑已发生的写入**。
2. **content_hash `1a6053…a64d` 的原始字节**（`SUBTASK.md` @passed 版本）**已随临时目录删除**：
   该值作为**已记录事实**可复原，但**无法**从原始字节离线重算 —— 这是**已记录事实 vs 可重算**的
   分级差异，**非伪造**（§6.3 要求交接带版本/哈希，ref 已带；权威源字节缺失属保全缺口）。
3. **未捕获的真实原文已由本恢复补全**：此前 `handoff_refs: []` 是**提取脚本 bug**
   （扫 `subtasks/*.md` 而非 `subtasks/<id>/SUBTASK.md`），**不代表产品未交接**；本次从**产品 prompt**
   复原了真实交接字符串。
4. 恢复 JSON 中 `handoffs_received_total`、`hash_verification`、`sessions[].*` 为**机器提取**
   （原日志级）；`note`/`residual_gaps` 为**叙述**。任何**从 prompt 文本重建**的字段已在本报告标
   `derived`；原始 DB 字节保留。

## 6. 未来修复（已做/未做，不重跑旧写入）

- 已修：恢复脚本只读、确定性、产出 sanitized 最小 JSON，**不写原 store、不补字段、不编造收据**。
- **未来 probe 须持久目录**（本项目旁持久路径优先；**关闭 auto-clean**），后续**手工清理不得由本包执行**。
  该项为对**未来**探针的要求；**不重跑** phase4 已发生的真实写入。
- 只读离线 fixture 测试沿用既有 `tests/collaboration/test_lg031_r4_real_planner_closure.py`
  （断言 `<subtask>@<64hex>:out/deliver.txt`，零模型），本包未新增模型调用。

## 7. 预算与边界

- 真实模型调用：**本包 0**；全局已知工程累计 **24 + 10 = 34 / 40**（不重放，不归零）。
- 未 push/deploy/发布；未改产品/`sources`/`vectors`/`frontend`；未碰 022 worktree、主目录集成者、
  core 独立 QA 的 0 请求补证；旧 dirty/worktree/8123 不动。
- 默认关闭/旧确定性回退、身份程序注入、无全局 token、`recovery_required` 不重放、停止后才回收权限
  均保留。**用例未经本包降低任何复核/机器门/停止/验收门。**

## 8. 结论与 LG-031 状态

- **硬条件 4 真实原文：已复原并满足冻结契约**（版本化交接 + 独立 diff `@sha256` 离线匹配 +
  fence=1 源/目标授权 + 完整候选 reviewer `passed`）。
- **LG-031 自身真实硬条件全部齐**：1 ✅（2 真实 SDK worker，隔离 worktree）、2 ✅（4 条自主 claim，
  产品 router）、3 ✅（fence=1、脱敏）、4 ✅（**本恢复闭合**）、5 ✅（真实独立 ModelReviewer
  机器门 `passed`）、6 ✅、7 ✅（持久账本 10/16，usage unknown 不当 0）。
- 唯一残余：**同 run 的 `content_hash` 原始字节**随临时目录删除（已记录事实不可离线重算，非伪造）；
  这是**保全缺口**，**不构成**硬条件 4 未达成——ref 的版本/hash 已真实承载。
- **因此按主代理授权可据真实单次运行证据将 LG-031 更新为 `done`（待 LG-032 独立集中 QA 复验）**，
  **不因未来 QA 制造循环**。见 `SALVAGE-STATUS.md`。
