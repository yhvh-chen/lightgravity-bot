---
title: "LG-023 cohort-3 方法修复/正式评估 REPORT"
doc_type: report
category: engineering
experiment_id: lg023-cohort3-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg023-cohort2
branch: eval/lg023-cohort3
product_base_commit: e0a8cec
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
model: deepseek-v4-flash
updated: "2026-10-16"
owner: "agent:pi-lg023-cohort3"
---

# LG-023 cohort-3 方法修复/正式评估 REPORT

> **状态：IN-PROGRESS（修复/硬门阶段）。真实 DeepSeek 生成 0。**
> 本包先修 cohort-2 发现的 harness 计量缺陷 D1（driver 侧），经**离线硬门**验证通过并冻结 hash 后，
> 才在预注册的 4 attempts 下发真实 DeepSeek 请求。**硬门未绿前不发任何实时请求。**

## 0. 起点与保留（不重置）

- 起点：`eval/lg023-cohort2@1d6d45c`（clean）；本包在其 worktree 内新建 `eval/lg023-cohort3`。
- cohort-2 分支、worktree 目录、`runs/`、`evidence/`、attempt ledger、旧 45(dev/lg023)、
  METHOD-AUDIT、全部旧原件：**保留、未 reset/clean/覆盖**。
- 产品/共享 docs 与其它包进程（8123/F1/F2）：**只读、不触碰**。

## 1. D1（唯一已知问题）——精确定位（harness，非产品）

- **现象**：cohort-2 attempt 1 的持久 ledger 落在
  `lg023-cohort2-data/attempts/s1_independent__A/data/generation/`，**非**冻结要求的单一 phase
  `lg023-cohort2-data/generation/`。phase 级 ledger 目录**不存在**。
- **根因**：driver 每个 attempt 设 `settings.data_dir = <attempt>/data`；产品
  `backend/lightgravity/api/bootstrap.py:build_runtime` 无条件调用
  `configure_generation_ledger(settings.data_dir)`，于是 `_GLOBAL_GENERATION_COUNTER` 的 ledger 根
  = 该 attempt 的 `data_dir`，**覆盖**了 driver 事先设的 `LIGHTGRAVITY_GENERATION_LEDGER_DIR`。
- **不归因**：这**不是**「核心产品 persistent ledger 缺陷」——产品 `configure_generation_ledger` +
  `PersistentGenerationLedger` 行为正确（METHOD-AUDIT P/ledger_proof、`qa/lg022-stream` 主链均单账本）。
  这是 **cohort-2 driver 把 `data_dir` 随 attempt 换** 造成的接线错误。
- **最小 repro**（已由 cohort-2 记录）：`LIGHTGRAVITY_GENERATION_LEDGER_DIR=<phase> ... build_runtime(Settings(data_dir=<attempt>))`
  ⇒ counter ledger 根 = `<attempt>/generation`，非 `<phase>/generation`。
- **禁止的错修**：在 `build_runtime` 前再设同一 env、或 `build_runtime` 后重 pin counter——都不采用。
  正确修法 = **让全串行 attempt/服务共用同一真实 phase `settings.data_dir`**，使产品的
  `configure_generation_ledger(settings.data_dir)` **自然续读同一账本**。

## 2. 修复方向（本包采用，产品源只读）

1. driver 对**全部串行 attempt**用**同一** `settings.data_dir = <phase-data-root>`（`PHASE_DATA_DIR`）。
2. 每 attempt 的**隔离**改在 `workspaces/<attempt-id>/`、`secrets/<attempt-id>/`、候选工作区、
   Task/Run/Subtask 的 attempt 命名空间——**不**把 `settings.data_dir` 随 attempt 换。
3. 服务可复用单一进程或顺序重启**同一** `data_dir`；样本/arm 隔离用不同持久 workspace refs/fixtures，
   **不清**上个 Task/Run 来「隔离」，不重写旧 Root/ledger。
4. **不**改产品源；**不**用 CounterHelper 测试当实际服务验证。
5. dry 与 formal **同一代码路径**，只换受控上游/基目录；dry **不跳过** bootstrap。

## 3. 硬门（离线，真实 DeepSeek 0；必须先于任何正式请求全绿）

- **G1** 真 `build_runtime`/`create_app` 启动链，**≥2 次顺序 runtime 启动**（同一 phase `data_dir`）。
- **G2** 真 `LocalAuthProxy` + **本地 fake 上游**：worker 与 reviewer 的**实际转发**都落**单 phase 物理路径**
  （`PHASE_DATA_DIR/generation/generation.jsonl`），且**跨启动累加**。
- **G3** 同 cap 的**总超限**与**attempt 超限**都在**转发前拒绝**（429，ledger 不增）。
- **G4** ledger **损坏 fail-closed**（绝不当 0）。
- **G5** runtime 诊断 `GET /diagnostics/generation` 报告的 ledger **路径 / persistent / realcounter 对象 /
  物理 JSONL** 与**冻结路径一致**——在 **FIRST FORMAL REQUEST 之前**核对。
- **G6** dry-run 与 formal 同一装配路径（只换上游/基目录），dry 亦走 bootstrap。
- SDK 真本地 fake 允许；DeepSeek **0** 直到门全绿；secret 仅 controlled env，不输出。

## 4. 预注册（PM，首请求前；本包不实施正式采样直到硬门+hash 冻结）

- **2 样本 S1/S2 × A 单实施写节点 / B 两依赖写节点 × 各 1 次 = 恰 4 attempts，每个正式 run 仅 1 次。**
- **新总 48** 实际 DeepSeek 生成，**每 attempt 总 12**，全 role/stage/失败/review **共用一个持久账本**。
- 旧 49（45+4）**不入新账本**但仍单列完整失败/方法成本；已知 eval 整体上限 **97**。
- 双方同稳定 e0 产品树、SDK 0.1.22/`deepseek-v4-flash`、自主开关 off/旧程序调度、toolcap 32、
  每 worker 模型 ≤12 但 attempt 合计 12、output 16000、HTTP 120、retry 0、并发 ≤2。
- 固定同初始 commit+tree、prompt 模板、工具集、资源参数、隐藏测试真值和机器+独立 review+真实 stopgate+
  绑定 accept 门。单 worker 标签不含共同 reviewer。
- 冻结合法 plan **只比较实施节点数**，**非**自动规划能力/新去中心化比较。

## 5. 成本（准确，未知不当 0）

| 阶段 | 真实生成 | 说明 |
|---|---|---|
| 旧 LG-023 cohort 1 | **45/48** | protocol-deviation 失败成本；逐 attempt 归因不可信 |
| cohort-2 | **4** | attempt 1 worker3+reviewer1；D1 停止；单列 |
| 旧 LG-022 | unknown+6+8+5/10 | 单列 |
| 旧 LG-031 | 34/40 | 单列 |
| **本 cohort-3** | **0（至硬门通过前）** | 离线 fake 上游不计真实生成 |

- 已知 eval 真实生成实际上限 **45+4+48 = 97**。
- usage/费用：provider 未回传可核总额 ⇒ `unknown`，**不当 0**；**不据失败样本中位数推收益**。
- 开发/controller 侧成本（修 driver/硬门/harness）**单列/shared**，不当 runtime 收益。

## 6. 局限（明确）

- 样本小、单模型、强制冻结合法 plan：不声称统计显著性；不推广。
- 结论**仅**限两小型代码样本、强制程序计划；**不测** UI/恢复/取消/长会话/真实工程规模。
- 未覆盖浏览器/恢复/取消。
- 未宣整产品 pass；最终 done 由主代理按授权决定。

## 7. 产物索引（进行中）

- 本包：`probes/lg023/cohort3/{PLAN,STATUS,REPORT}.md`、`harness/`、`evidence/`、`runs/`。
- 保留的对照：`probes/lg023/cohort2/**`、`probes/lg023/METHOD-AUDIT/**`、`probes/lg023/**`（旧）。

**不推送 / 不部署 / 不发布。LG-023 保持 `in-progress`。**
