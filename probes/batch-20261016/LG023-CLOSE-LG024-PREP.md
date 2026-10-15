---
title: "LG-023 证据/PM 收拢 + LG-024 准备交接（cohort-3 收口，独立 PM 复核补注）"
doc_type: handoff
category: engineering
task: "LG-023 / LG-024"
owner: "agent:pi-lg024-prep"
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
model: deepseek-v4-flash
updated: "2026-10-16"
---

# LG-023 证据/PM 收拢 + LG-024 准备交接

> 本文件由主代理 PM（只做项目管理，**无嵌套派工 / 无推送 / 无部署 / 无发布**；主代理不写产品代码、不看代码作审查）
> 在 **LG-023 独立 PM 复核** 后落盘。用途：①用**独立只读复核**核定 cohort-3 比较目标是否满足并据此 mark LG-023 done（**仅本评估门内，不是整产品 pass**）；
> ②**补注修正措辞与已知缺口**（不覆盖任何旧原件字节）；③交接 LG-024 阶段 A（probes/本地产物/许可/启动烟测草案）与阶段 B（待 runtime owner 释放后串行落地共享文档）。
> **本包产品真实生成 0**：零调用、只读已持久 SDK DB 与原件中可取得的 gen metadata；未运行产品代码/测试、未重跑模型、未执行新探针。

## 1. 开工核对（真实，只读）

- 主工作区 `main@834b262` **clean**；`eval/lg023-cohort3@7e0b702` **clean**；`integrate/lg031-runtime@c4d4e87`
  有**产品源 dirty**（`backend/**`、`tests/collaboration/test_lg031_pool_selection.py` + 未跟踪 `probes/lg031/RUNTIME-AUTH-INTEGRATION/`），
  **本包未触碰其 branch/文件/index**；该 owner 独占产品源与共享 docs（docs/08、README、PROJECT、agent、docs/06）。
- 现场进程：主工作区 uvicorn(:8123) 为**旧常驻服务**，非本 worktree/本包，**未 kill、未接线、未复用 dataRoot**。
- backlog 专用根（`<repo>/backlog`）：`validate` → **ok=true, 41 tasks, 0 diagnostics**；`digest` → **complete=true**，
  counts **32 done / 6 in-progress / 3 todo**；`ready` → **空**（LG-024 因 LG-023 仍 in-progress 而未就绪）。
  > 注：对整个仓库根运行 `validate` 会命中旧实验 `probes/agensh-orchestration-r2/runs/**` 内**已跟踪**的 subtask 样例重复 frontmatter 键
  > （commit `b2bd5eb` 既存，非本包/非 backlog 任务），故诊断非 0；**backlog 任务根**为 0 诊断。此差异如实记录、不在本包修旧实验文件。

## 2. LG-023 独立只读复核（不只看 summary 标题）

复核对象：`eval/lg023-cohort3` 唯一物理证据（已 ff 合入 main）。**全部经零模型只读核验**：

| 核对项 | 方法 | 结果 |
|---|---|---|
| 分支关系 | `git merge-base --is-ancestor` | cohort3 为 main 后代，**ff 合入**，无冲突、无重复 pick |
| 产品树锚 | `git diff e0a8cec HEAD -- backend/ frontend/ src/ tests/ pyproject.toml uv.lock` | **空** ⇒ 产品树逐字节同 `e0a8cec`，**未重跑全量 pytest** |
| cohort3 变更范围 | `git diff --name-only 834b262 7e0b702` | 仅 `backlog/` 与 `probes/`，**未改产品/共享 docs** |
| protocol hash | 按 `protocol_manifest.py` 逻辑**独立重算** frozen_protocol_hash | **`c8f83417…` MATCH** |
| harness 字节 | 逐文件 sha256 vs manifest.harness_sha256（7 文件） | **全部 MATCH** |
| fixtures 字节 | rglob 逐文件 sha256 vs manifest.fixtures_sha256（24 文件） | **全部 MATCH** |
| 单一 ledger | `find` 全 phase data 下 `generation.jsonl` | **唯一一条** `<…>-data/generation/generation.jsonl` |
| ledger 行数/计数 | `wc -l` + `generation.count.json` | **16 行**，count=16，`corrupt=false`，`persistent=true` |
| 逐 attempt 累计 | 4 份 `result.json.generation_final` | **0→3→8→11→16** 单调累加，**转发前预留** |
| 每 attempt 机器门 | `result.json.machine_gate.checks` | **6/6**，且为**不同具名检查**（非仅标题） |
| 独立 reviewer | `result.json.review` | 4/4 `outcome=passed`，`findings=0`，独立 session |
| 停止门 | `result.json.reviewer_cleanup` | 4/4 `confirmed=true`、`agent_closed=true`、`proxy_stopped=true`、`problems=[]` |
| accept 绑定 | `result.json.accept_response` | 4/4 `state=confirmed`、`phase=completed`、`candidate_plan_hash` 各自绑定 |
| session refs | `result.json.session_refs` | A=1 / B=2 / A=1 / B=2，与计划写节点数**一致** |
| elapsed | `result.json.elapsed_seconds` | 11.95 / 15.92 / 13.22 / 17.51 s |

**四 attempt 的原始字段与 REPORT/aggregate 摘要一致**，未见事后改动或覆盖；attempt 输出目录含一次性 `.formal_attempt_started` guard。

## 3. LG-023 比较目标是否满足（核定结论）

- 设计：**2 样本 × 2 arm × 1 repeat = 4 attempts**，**每个正式 run 一次**；两 arm 共用相同 fixture/初始树/需求文本/
  机器门/独立 reviewer/版本验收门/模型/预算/工具集/worker 提示/权限/SDK/契约；**唯一自变量 = 计划写节点数**（A=1、B=2 依赖）。
- 初始 commit / 树 / 工具资源 / 门：**由 protocol hash 与逐文件 sha256 绑定并已独立复核**（§2）。
- 四例均 **6/6 机器门 + 独立 review passed + 真实停止门 confirmed + 绑定 accept**；数据（A: 6 请求/25.17s；B: 10 请求/33.43s）**不支持这两样本的组队收益**。
- **据此，LG-023 在本评估门内可 mark `done`**（不是整产品 pass；不删除产品编排/评审能力；样本小/单模型/强制计划局限保留见 §4）。

## 4. 措辞修正与已知缺口（**在不动旧原件字节的前提下补注**）

> 以下为 PM 补注，**不修改** cohort3 REPORT/STATUS/PLAN/evidence 与 cohort1/2、METHOD-AUDIT 的任何原文；
> 旧协议违规 (cohort-1 45) 与 cohort-2 停止成本 (4) **全部保留**。

1. **「cost higher/lower」仅指已测代理量**：cohort-3 REPORT/STATUS 中 “A 总真实生成 6、B 总 10”“总 elapsed 25.17s vs 33.43s”
   是**已测请求数 / elapsed** 代理量；**完整 token / 费用 / shared 开发-QA 成本未知**。
   **不得**引申为完整生命周期成本或货币节省。契约 §6 的「全交付生命周期成本」在本 cohort 中**未取得**。
2. **USAGE/费用 unknown 的来源**：`result.json.usage/cost = "unknown"`（provider 未回传可核 usage）。
   本包**只读**已持久 6 个 SDK session DB（`native-sessions/**/*.db`，含 `gen_metadata` 表）核对：
   该表为 protobuf 二进制，**仅含 system prompt / step 结构 / model_enum 等**，**无可核的 provider token/费用字段**；
   与结果 `unknown` **互相印证**。故按实际 SDK/提供者字段来源：**provider 真实 usage 不可得**，**不把 SDK 估计或缺失字段冒充 provider 计费 tokens**。
   - **不逐 attempt 追加 metrics**：无可靠来源，逐 attempt 配对不可靠 ⇒ **保持 unknown**（不扫无关用户/tmp 全部 session、不重跑模型补 token）。
   - **安全**：只以只读 `sqlite3 mode=ro` 打开，**未抽取、未持久化**任何 prompt/headers/密钥/raw body；敏感原件不入 repo。
3. **旧 45 协议违规 + 4 停止成本保留、总数 65**：旧 cohort-1（`dev/lg023`, ledger **45 行**）+ cohort-2（**4**，harness D1 停止）
   **另行单列、不清零、不并入** cohort-3 的 16。**总实际 eval 请求 = 45 + 4 + 16 = 65**（不是 48，也不是 97；97 是含 48 上限的**上限值**）。
   **不得用新 16 覆盖旧 49**；**不得当作所有旧失败原件都齐**——旧部分运行 SoT 已丢失（METHOD-AUDIT 明示部分字节丢失，仅已恢复部分私有保全）。
4. **停止门归因**：cohort-2 REPORT 记录 `cleanup='pending'` 为历史旧型未接 confirmer 的事实；METHOD-AUDIT 已证**旧停止门不是产品 bug**。
   本 cohort-3 4/4 `reviewer_cleanup.confirmed=true`。**原报告措辞按上述保留并在本补注修正读者理解**，不改原文。
5. **workspace 隔离两 arm 一致关闭**、**自主模式默认 off**、**旧程序调度路径** 为明确冻结实验设置；不代表产品隔离/自主能力。
6. **本包不因无法取得费用阻止合法评估 done**：LG-023 门（固定输入/版本/资源/验收门、可取得成本、缺失标 unknown）已满足。

## 5. LG-024 排期（阶段 A 立即可做，阶段 B 待 runtime owner 释放）

- **依赖**：LG-024 `depends_on: [LG-022, LG-023]`。LG-022 门内 done、LG-023 本次 done ⇒ **LG-024 可在 backlog 根 ready 后原子 claim**。
- **阶段 A（本包创建 worktree 后可开始；不写共享 docs）**：
  - 整理 **probes / 本地产物 / 许可 / 启动烟测草案**：许可清单（`pyproject.toml` 依赖 + 参考来源 commit/许可）、
    本地分发与演示素材草案、安装/启动/任务/资源/恢复入口草稿（**放在 LG-024 owner 的 probes/本地产物，不写 README/docs/PROJECT/agent/docs06**）。
  - **不提前 done**：LG-024 验收条件要求 README/设计/规则与实际行为一致，需共享 docs owner 释放后串行落地。
- **阶段 B（等待）**：`integrate/lg031-runtime` owner 释放（产品源与 docs/08、README、PROJECT、agent、docs/06）后，
  **串行**落地 README 等共享文档，并**绑定准确候选**（以届时 main 实际产品树/契约/版本为准，不预设）。
- **worktree**：创建**全新持久** `/home/yhvh/code/lightgravity-bot-worktrees/lg024`（branch `dev/lg024`），
  基于**最终 main / claim commit**；路径若存在**先核不覆盖**。

## 6. 状态如实（本包结束时）

- **LG-023 `in-progress → done`（仅评估门内）**；**LG-024 `todo → in-progress`（claim 后，阶段 A）**；
  **LG-029/031/032 `in-progress`**（重要返修/QA，不因本包改变）；**LG-035/037 `in-progress`**；**LG-040/041 `todo` 不解锁**；
  **LG-022 `done`（门内）**、**LG-031 `done`（待 032 独立集中 QA）** 保留。
- **契约 `1.10.0`、SDK `google-antigravity==0.1.22`、自主模式默认 off 不变**。**本包产品真实生成 0**，未推送/部署/发布。
- **全部旧实验、worktree、原始 probes、旧 dirty 保留**，未 reset/clean/覆盖/重复 pick。
