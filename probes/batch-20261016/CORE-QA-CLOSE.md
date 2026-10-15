---
title: "核心首版 QA 收口报告（LG-022 独立流式停止复验收拢 + 023 排期）"
doc_type: report
category: engineering
updated: "2026-10-16"
owner: "agent:pi-lg023"
---

# CORE-QA-CLOSE — 核心首版 QA 收口（唯一串行验收证据整合/排期 owner）

唯一串行验收证据整合/排期 owner（pi + env DeepSeek；**主代理只 PM**；**无嵌套派工/推送/部署/发布**）。
本包**产品生成 0**：不执行评估、不新增探针、不重跑模型或测试。所有源 owner 已退出后才执行本包。

## 0. 结论一句话

`qa/lg022-stream` 独立 QA 已退出、结论为**门内 PASS 且无未修重要缺陷**；据此将 **LG-022 置 `done`**
（仅「首版端到端 + 本次流式停止缺陷独立真实复验」门内范围，**不宣称整产品 pass**），并把该 QA 证据
（14 文件纯 QA）**安全 `--ff-only` 合入 `main`**（产品树逐字节不变）。随后 `validate`/`digest` 确认
backlog 完整、无诊断且 LG-023 `ready`，再 **CLI 原子 claim LG-023 --as agent:pi-lg023**，基于最终 main/claim commit
创建**全新持久 worktree**。**LG-032 暂不 claim**（原任务 ready ≠ 立刻占有；待 023 评估后与 024 并行排期）。

## 1. 开工事实核对（全部真实）

| 位置 | 分支 | HEAD | 状态 |
|---|---|---|---|
| root | `main` | `e0a8cec` | clean（开工时） |
| worktree `lg022-qa-stream` | `qa/lg022-stream` | **`49c95f5`** | clean，**仅 14 个 QA 文件**（纯 `qa/lg022-stream/**`，产品/ docs 零改动） |
| worktree `lg031-r3` | `fix/lg031-r3` | `2f04654` | 已由 INTEGRATION-8 合入 main（`975afc2`） |
| 主 worktree | root | 有既存 uvicorn(:8123) | **非本包、未 kill/未复用 dataRoot** |

- **签名进程核实**：`ps` 仅见本收口 owner 的 bounded pi 包装进程；**无 022-stream QA owner 残留**，无 stream 修复者/集成者/031 实施者残留。
- **旧 worktree/dirty 全部保留**：`lg031-r1` dirty=8、`/tmp/*experiment*` dirty（15/17/1）等**均未触碰**；未 reset/clean/覆盖/重复 pick；未复制 `.env`。
- **合并关系**：`git merge-base --is-ancestor main qa/lg022-stream` 为真 ⇒ main 是 QA 分支直系祖先，`--ff-only` 安全（无冲突、无重放、产品树不变）。

## 2. 独立 QA 退出与结论（不接受早于 QA 退出）

- **owner 状态**：`agent:pi-lg022-stream-qa` 已退出；worktree `lg022-qa-stream` clean @ `49c95f5`。
- **硬门/主链证据复核（只读，不重跑）**：`evidence/stream-stop-hard-gate.json` `hard_gate_pass=true`；
  `evidence/main-chain-verdict.json` `ok=true`（`real_generation_count=5`, `phase_limit=10`, `candidate_head=e0a8cec`）。
- **结论**：真 SDK 0.1.22 + 真产品装配 + 有效本地 fake SSE 下，流式阶段 pause/cancel 均触达 SDK 公开取消入口、
  仅在真实 teardown 后 confirm（0.21s/0.22s）、未确认保持 held；真实 DeepSeek 主链一例到绑定 accept。
  **无未修重要缺陷**（若有 fail 只 checkpoint、不 claim 023——本包**未发现 fail**）。

## 3. merge（仅 QA 证据，产品树不变）

- 命令：`git merge --ff-only qa/lg022-stream` → **`main@49c95f5`**（`e0a8cec..49c95f5`，14 文件新增、2437+ 行）。
- **产品树证明**：`git diff --name-only e0a8cec main -- backend/ frontend/ src/ tests/ docs/ pyproject.toml` **为空** ⇒
  **产品树与已验候选逐字节相同**，故**不重跑全量 pytest**（无新代码，按既有完整门 + 本次缺陷修复独立证据判定）。
- 契约 **保持 `1.10.0`**；SDK `google-antigravity==0.1.22` 不变。**未推送/部署/发布**。

## 4. 准确门范围与成本（完整保留，不被旧错误 PASS 标题覆盖）

### 4.1 门范围（准确）

- **通过**：真 SDK + 真产品装配 + 本地有效 fake SSE 的**流式 pause/cancel 真实停止**；真实 DeepSeek 主链一例（5/10）到 accept；
  持久 generation ledger（唯一路径/limit=10）；pytest 791 pass/5 skip、mypy 137 clean。
- **未测（保留，不夸大）**：**真实 DeepSeek 上游下 cancel/pause-during-review 未跑**（stop 缺陷在产品↔SDK 调用序，与上游无关；
  已用真 SDK + 本地 SSE 证明取消路径，**不冒充 DeepSeek 故障**）；重启后 `verifying`/`repairing → recovery_required` 与跨 Run 真实 reject/repair
  未在本 phase 重跑；light 问答/浏览器矩阵按材料差异引用既有 021/027 证据。
- **provider-substitute**：流式硬门上游为**本地 fake SSE**（明确非 DeepSeek）；主链为真实 DeepSeek。
- **全部失败成本保留**：见 §4.2。

### 4.2 成本账本（旧 022 unknown + 6 + 8 与新 phase 分别记录）

| 阶段 | 真实生成请求 | 账本说明 |
|---|---|---|
| LG-022 首轮 QA（`8e81089`） | **unknown** | 含 429 rerun；单列保留，不当 0 |
| R1 复验（`6228474`） | **6** | 单列保留 |
| R2（`cea87ab`） | **8** = 主链 7 + light 1 | **两账本未统一、未执行统一总额硬限**（非产品持久账本缺陷）；单列保留 |
| **本 phase（`qa/lg022-stream`）** | **5/10**（唯一持久 ledger：真 worker + 真 reviewer） | 门内通过；0 额外 light/浏览器/QA 返修 |
| **本收口包（`CORE-QA-CLOSE`）** | **0** | 产品生成 0，不执行评估/新探针 |

- 旧轮成本**不归零、不洗白**；不以旧错误 PASS 标题（仅覆盖持久账本+停止门主链）覆盖本次流式修复的真实复验。

### 4.3 031 已知工程账本

- **LG-031 已知工程累计 34/40**（旧 24 = 原 1 + R1 3 + R2 6 + phase3 14；+ phase4 10），单列保留、不重放、不归零。
- **原运行 SoT 部分字节丢失**（phase4 探针 `TemporaryDirectory` 删除的 `data/store/worktrees`）；**SDK 原件（3 个 session DB + 原 stdout）
  已持久备份**于 `~/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/lg031-phase4-survivors/20261016T040115+1100/`（`700`/`600`），
  硬条件 4 的版本化/带 hash 交接原文由此**只读哈希恢复**；**恢复限制如实保留**（未写回原 store、未补字段、未编造收据）。
- 本包不改 031 状态（保持 `done`，待 LG-032 独立集中 QA）。

## 5. 状态如实（035/037/040/041 门不动）

- **LG-022 → `done`**（门内范围，见 §0/§4.1）。
- **LG-031 保持 `done`**（待 LG-032）。
- **LG-023 → 原子 claim 后 `in-progress`**（见 §6，本包不执行评估）。
- **LG-032 保持 `todo`、暂不 claim**（原 ready ≠ 立刻占有；待 023 评估后与 024 并行排期）。
- **LG-035 / LG-037 保持 `in-progress`**（真实质量门/端点不可达，不假 done）；
  **LG-036/038 保持 `done` 待 040**；**LG-040 `todo` 不解锁**；**LG-041 `todo` quality gate 阻塞不解锁**。
- 自主模式默认 off；不重新引入模型编排；去中心化仅开关开启时启用。

## 6. LG-023 排期（claim + worktree；本包不执行评估）

- **CLI 原子 claim**：`tasks claim LG-023 --as agent:pi-lg023`（backlog 目录），**不直接绕 claim**。
- **新持久 worktree**：`/home/yhvh/code/lightgravity-bot-worktrees/lg023`（branch `dev/lg023`），
  **基于最终 main/claim commit** 创建；**若路径已存在先核不覆盖**。旧 worktree 全部保留。

### 6.1 LG-023 预算（采样前最终修订；此即执行依据）

> 本节为**采样前**最终修订，**非**看实验结果后改额；样本与成功门仍**固定为两任务 × 两 arm × 一次**。

- **真实 DeepSeek 生成：4 attempts / 总 48 / 每 attempt 12**。
- **全 stage 同 phase 持久 ledger**（worker/reviewer/所有 stage 共用同一 `phase data_dir`/路径，**不分账**）。
- **output ≤ 16000 tokens/请求**；**HTTP timeout 120s**；**retry 0**；**并发 ≤ 2**。
- **旧 16/24/6 只是未执行草稿，作废**（不构成已用额度、不影响样本/门）。
- **按已见真实双 worker 链约 10 calls**，为**双方**（两 arm）设置**同样足够 cap**，避免一方因预算不足被误判失败。
- 本包不执行评估、不发真实请求。

### 6.2 LG-032/024 后续排期（暂不动）

- **LG-032 暂不 claim**；待 023 评估完成后与 **LG-024** 并行排期（032 版本级集中 QA 依赖 031/022 已 done）。
- 不在本包替 032 预注册样本/预算/成功标准。

## 7. 校验与提交

- `tasks validate`（backlog 目录）：**ok=true, 41 tasks, 0 diagnostics**（见 PROGRESS 收口节实际退出码）。
- `tasks digest`：**complete=true**；LG-023 `ready=true` 后原子 claim。
- 本包结束顺序：**先写持久 REPORT（本文件 + PROGRESS 收口节）→ 精确提交**（不 `add -A`）→
  确认 **main clean / 023 worktree 路径 / HEAD / 文件计数 / ready 状态**。
- **未推送/部署/发布**。契约 `1.10.0`、SDK `0.1.22` 不变。本包产品生成 0。
