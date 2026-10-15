---
title: "LG-023 实验方法审计与 harness 返修 PLAN"
doc_type: experiment-protocol
category: engineering
status: frozen-before-offline-repair
audit_id: lg023-method-audit-20261016
experiment_id: lg023-single-vs-team-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg023-method
branch: fix/lg023-method
base_commit: fa9401d
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
model: deepseek-v4-flash
updated: "2026-10-16"
owner: "agent:pi-lg023-method-audit"
---

# LG-023 实验方法审计与 harness 返修 PLAN

> 本文件在**任何新真实 DeepSeek 请求之前**写定。本包**真实产品/DeepSeek 生成 0**：
> 只做取证、方法审计、harness 修复与**离线**验证。**不跑旧/新真实 fixture**，**不消耗剩余 3**，
> **不新建 ledger 规避旧 phase 48**，**不合入 main**，**不解锁 LG-024/032**，**不改产品代码**（只读）。

## 0. 一句话目标

前 owner `dev/lg023@fa9401d` 的 cohort **不能称为“冻结正式对照完成”**：采样中违反冻结协议
（改 worker 提示/工具集、反复调 S1/A、破坏 4-attempt 界限）。本包：

1. **保全/恢复**旧原件（fortune），明确缺口，不推断补造控制状态；
2. **定位并修复 harness**（而非产品）中的 stop-gate 与计量/协议守卫缺陷；
3. 冻结一份**可在未来新 cohort 使用**的 harness，并**离线**证明其接真实 proxy/executor 事实；
4. 明确旧 45/48 全部作为 **protocol-deviation 失败成本保留**，不洗白、不归零。

## 1. 背景事实（审计起点，详见 REPORT）

- 前 cohort：S1×A 在**最终 harness** 下机器门 6/6 + 独立 reviewer passed，但**版本验收门**
  `verify_and_prepare` 返回 `unconfirmed`（`cleanup='pending'`，1 session 未确认关闭）。
- 该结果 `runs/s1_independent__A/**` 被**后续 S1/A 重试覆盖**（不可变历史丢失）；旧 `_accept`
  崩溃/字段 bug 与后续覆盖都在同一个 attempt-id 输出路径上发生。
- 两 arm 的 `initial_head` commit hash 不同（`48419c5`/`791de14` for S1；`243dd74`/`a1c207e` for S2），
  但**由相同 fixture 目录 `cp` 后 `git commit` 产生**——必须**逐字节核 tree**是否同一版本（审计项）。
- global ledger 总数 45 可核（`generation.jsonl` 45 行），但**逐 attempt count 不可信**：
  attempt guard 是**手工 monkey-patch helper**，离线 proof 只测 `PersistentGenerationLedger` 与
  未被真实 proxy 调用的 guard。

## 2. 审计范围（本包 owner 可写）

- `probes/lg023/METHOD-AUDIT/**`（本 PLAN/STATUS/REPORT + 离线证据 + 未来协议草稿 + 局部离线测试）。
- harness 的**必要修正**（仅限评估脚本；产品 `backend/**` **只读**）。
- 对 `probes/lg023/{PLAN,STATUS,REPORT}.md` **只追加**“已被审计取代”与准确偏差，**不删除原文/账本/证据**。
- LG-023 记录（追加审计指针；不改状态为 done）。

**禁止**：产品/共享 `PROJECT/docs08` 等；跑任何真实 DeepSeek 生成；`reset/clean/rm` 旧数据；
新建 ledger 规避旧 48；把混淆样本标 done。

## 3. 审计项（必须给出事实结论）

| # | 项 | 判定方式 |
|---|---|---|
| A1 | 冻结后采样中改了 worker 提示/工具集 | 比对 `4a8ac0d..fa9401d` 的 `run_attempt.py` diff + dispatch log |
| A2 | 反复调 S1/A，超过 4-attempt 界限 | 从 dispatch log 提取所有 `run_attempt.py --sample` 调用并计数 |
| A3 | 旧 S1/A/evidence 路径被覆盖 | 比对 ledger pid 时间线与 `runs/` mtime；恢复幸存原件 |
| A4 | 45/48 global 总数可核，逐 attempt count=0 不可信 | 重算 `generation.jsonl`；核对 attempt guard 是否真实接线 |
| A5 | 两 arm 起始 commit hash 不同是否 tree 同一版本 | 重建 initial 目录 → `git rev-parse HEAD^{tree}` 比较 |
| A6 | 旧 REPORT“全部失败原件保留/最终拍定协议”核实 | 逐 attempt 原件 + dispatch log 对照 |
| A7 | stopgate 为什么真实完成仍 unconfirmed | **离线**用 fake executor + 真 `GraphDispatcher` + 真 `StoreResourceStopper` 复现 |
| A8 | 计量是否在**真实 proxy 转发前**强制 | **离线**用本地 fake upstream 走真实 `LocalAuthProxy`，证明 `reserve()` 被调用 |
| A9 | 旧 runtime 是否被 `TemporaryDirectory` 删除 | 检查 `/tmp/tmp*` 与 `/tmp/antigravity_*` 幸存 |

## 4. 交付物

- `METHOD-AUDIT/{PLAN,STATUS,REPORT}.md`（先事实，后缺陷，再修复）。
- `METHOD-AUDIT/evidence/**`（只读审计原件索引、树比较、ledger 重算、离线复现结果）。
- `METHOD-AUDIT/harness/**`（未来 cohort 的修正 harness 草稿 + 离线自检；不覆盖旧 harness）。
- 私有持久幸存原件：`/home/yhvh/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/lg023-survivors/**`
  （`700`/`600`，含 `MANIFEST.sha256` 与 `cmp` 验证；**不入 repo/prompt/输出 body/secret**）。

## 5. 硬界（本包）

- wall ≤ 1200s；模型轮 ≤ 220；非缓存 token ≤ 300k；idle ≤ 240s；开发 retry 0。
- **探针单次 ≤ 60s**；禁止 100s timeout 反复试错。
- **真实 DeepSeek 生成 0**；offline 只允许：fixtures/账本/**真实 proxy + 本地 fake upstream**/
  **真 SDK 资源生命周期**。**不得用 fake executor 过门冒充实验成功**。
- 若发现真产品缺陷：**报告最小 repro 交 PM，不自修自验**。

## 6. 下一 phase（需 PM 先预注册；本包不执行）

未来真正的对照 cohort 需 PM **先**明确 budget 与样本 PLAN（总上限、每 attempt 上限、attempt 总数、
门与样本），并接受：旧 45 为 protocol-deviation 失败成本、两 arm 需同提示/工具/预算/起始 tree。
本包只交一份**可复现的 harness 与离线证明**，不代替 PM 预注册。
