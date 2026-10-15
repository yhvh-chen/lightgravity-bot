# LG-022 流式停止缺陷包 — 独立复验 PLAN（新重拆，非 stream 修复者/集成者/031 实施者）

- Owner：`agent:pi-lg022-stream-qa`（新独立 pi 上下文；经 env DeepSeek；**无嵌套派工/推送/部署/发布**）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-stream`（branch `qa/lg022-stream`）。
- 持久 QA 目录（**非** TemporaryDirectory，保 SoT/证据）：`qa/lg022-stream/**`；
  runtime fixture/账本持久目录：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-stream-data/`。
- 核准确整合候选 HEAD：`e0a8cec`（= `main` = `integrate/batch7` 后代；batch8 记录 commit）。
  产品树 == `975afc2`（INTEGRATION-8 集成点）== `7d0510c` 流式修复点所在链。
- LG-022 claim：保持 `in-progress`（本包不擅自改状态；门内真实通过后由主代理按授权标注）。
- SDK：`google-antigravity==0.1.22`（安装版固定；未升级/切换供应商）。契约 `1.10.0`。

## 0. 本包是什么

前两轮（`qa/lg022` 首轮 fail、`qa/lg022-r1` FAIL、`qa/lg022-r2` scope 修正未闭环）**原样保留**，
本包是**重拆的「SDK 流式停止缺陷包」独立复验**：上轮 R2 独立调查证实「复核运行中 pause/cancel 未接到
SDK 取消入口」是**产品生命周期接线缺陷（D2 家族）**；`fix/lg022-stream` 声称已把 stop 接到 SDK 公开取消入口
（`Conversation.cancel()` + 有界 `wait_for_idle()`，流式阶段承载 stop）。本包**独立复验该修复**，
**不能原样无界重跑旧失败**，**不自修产品**（发现缺陷最小 repro 交 PM）。

## 1. 第一离线硬门（**先于任何 DeepSeek 请求**）

真实 SDK 0.1.22 `Agent`/`Conversation` + **真实产品** `ModelReviewer`/`ReviewLifecycle`/`ControlService` 装配 +
**有效本地 fake SSE**，验证：

1. 流式阶段 `pause` 与 `cancel` **都触达 SDK 公开 cancel**；
2. 观察 **真实 `Conversation.is_idle`**（`wait_for_idle` 返回）；
3. **真实 Agent 与 loopback proxy 退出后才 confirm**；
4. confirm 之前**不能终止/放槽**；
5. 关闭失败/unknown 保持 **held**（`unconfirmed` + 槽保留 + `session_refs`/历史保留）；
6. `session` 对象真实（真 `Conversation`/`Agent`），**不用 Event 假 reviewer 冒充真实 SDK 取消**；
   只 seed 测试 Run 时明确 refs 是 fixture，而真实对象是真。
7. 正常成功流/timeout/部分 chunk **不被轮询破坏**（不丢/不重）。
8. 独立固定**有界进程**（`timeout` 包裹），**不 100 秒超时循环**。

## 2. 持久 generation ledger 门（离线）

真实预算 = **persistent ledger 全 stages 同一路径**、跨重启不归零、损坏 fail-closed、031 上限对齐但**不扩大程序授权预算**。

## 3. 第二主链一例（真实 DeepSeek，唯一真模型路径）

真实 Settings worker/reviewer → 真实 Task/SDK 写产物 → 真实异步独立 review → 真实停止证明 →
`awaiting_acceptance` → 绑定 requirements/candidate/planhash accept；duplicate/stale/control/token/pin 回归。

## 4. 预算（冻结，不得事后分裂账本）

- 真实 DeepSeek 生成总上限 **10**（**唯一一条**受控持久 `data_dir`/generation ledger；**唯一一个主链 fixture，不重复，不另跑 light**）。
- 所有 worker/reviewer/失败/QA 返修复验/SDK retry **共用同一 ledger**（path 与 limit 先冻结并核传给所有 stage）。
- **禁止**再分两个 ledger 后写 8/10 统一限额。
- output ≤14000；HTTP 120s；并发 ≤2；retry 0。
- 旧轮真实计数**单列保留、不归零、不洗**：首轮 unknown / R1 6 / R2 实际 8（未统一 hardtotal）。
- 新 failure 预算不足 → **保留不完整，不得偷偷再建 data_dir**。
- wall 1200s；round ≤220；noncache ≤280k；idle 240s；开发 retry 0。

## 5. 范围 / owner 白名单

- 本包新增：`qa/lg022-stream/**`（PLAN/STATUS/REPORT、harness、evidence）。
- **产品只读**；不改产品代码（发现缺陷最小 repro 交 PM）；不碰 8123/其它任务/其它 owner。
- 精确清自有签名进程，凭证只受控 env，不输出 / 不写 prompt / 不写 raw 请求。
- 原文件/worktree/日志全保留；证据持久，不 TemporaryDirectory 自动删除关键 SoT。

## 6. 裁定规则

- 按**真实门**裁定 022；主代理已授权依**独立真实通过证据**标 022 `done`（无需问用户普通实施确认），
  **但只能门内范围，不能全产品 pass**。
- 旧错误 PASS 标题在最新状态引用说明「已被 SDK 调查阻断后修复」，**不洗历史**。
- 报告先持久后精确 commit：准确 candidate/head、真实与替身、命令退出、模型次数、unknown 费用、所有未测。

## 7. 未授权 / 明确不做

- 不跑 032/040 版本门；031 模式默认 off，本门不是 032/040。
- 不重复额外 provider 调用或完整浏览器矩阵；已有 lightQ&A/浏览器 021/027 旧证据按材料差异引用。
- 不宣称此前未跑的真实 `reject/repair` 等已跑（按现有证据 + 局部回归引用）。
