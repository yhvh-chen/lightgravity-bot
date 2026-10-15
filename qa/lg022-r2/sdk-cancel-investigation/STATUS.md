# SDK 取消语义调查 — STATUS

- Owner：独立 SDK 取消语义调查/QA owner。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-r2`（`qa/lg022-r2`），开工 HEAD `0a88ab8`（clean）。
- 产品只读；真实 DeepSeek 请求 0；无嵌套派工/推送/部署。

## 进度

- [x] 读 AGENTS/agent、LG-022 原验收、docs06 版本门、docs/08 停止契约、前 REPORT/SUPPLEMENT/STATUS、
      前 `review_cancel_sdk_proof.py` 及其实际产物（不重放历史全量大报告）。
- [x] 冻结 PLAN（本目录 `PLAN.md`）。
- [x] 只读 SDK 0.1.22 源码：确认公开取消入口 `Conversation.cancel()`/`Connection.cancel()` 与
      `is_idle`/`wait_for_idle()`；`Connection.cancel()` 只发 `halt_request`、不等待 idle。
- [x] 只读产品接线：定位 `run_review_turn` / `_await_with_stop` 的 stop 轮询范围（疑似 H2 缺陷）。
- [x] 最小本地 fake SSE 上游（`fake_upstream.py`，有效 SSE + 分阶段 release + 硬 hold 超时）
      + 最小真 SDK cancel 顺序验证（P1）：`sdk_min_cancel_probe{,2,3}.py` + `evidence/sdk-min-cancel{2,3}.json`。
- [x] 接产品真实 ReviewLifecycle 复现（P2/P3）：`product_stop_probe.py`、`product_stop_lingering.py`、
      `decisive_product_vs_sdk_cancel.py` + `evidence/{product-stop,product-stop-lingering,decisive-product-vs-sdk-cancel}.json`。
- [x] 定位确切产品缺陷 + 最小 repro + 修复方向；写 REPORT。
- [x] 资源清理核实：无本包残留 loopback/子进程/端口；8123 未触。
- [x] 精确 commit（仅 `qa/lg022-r2/sdk-cancel-investigation/**`）。

## 已成立结论（增量，先保存）

- **S1（源码契约）**：SDK 0.1.22 公开取消入口 = `Conversation.cancel()`（转发 `Connection.cancel()`）；
  `cancel()` 是**请求**（置 `_client_cancelled` 并发 `halt_request`），**不是**同步确认；
  真实停止确认须观察 `is_idle`（`STATE_FULLY_IDLE`/`STATE_CANCELLED` 后置位）或 `agent.__aexit__`/`disconnect()` 返回。
- **S2（产品接线，疑似缺陷 H2）**：`run_review_turn` 中 stop 轮询仅覆盖 `agent.chat()` 返回（即 `send`），
  **不覆盖 `async for chunk in response.chunks` 流式迭代**；产品路径**无任何** `Conversation.cancel()` 调用。
  故流式阶段 stop 请求不会触达 SDK 取消 → turn 不停 → 产品诚实返回 `unconfirmed`。
  这与前包 `real_sdk_teardown_fact={}`、`upstream_saw_client_gone=false` 一致。
- **S3（P1 证成，真 SDK cancel 契约存在且可用）**：最小真 SDK 探针（真 `Agent`+真 `LocalAuthProxy`+本地
  fake SSE 上游，0 真实模型调用）证明：
  - **控制组（不 cancel）**：流保持开启、6s 内 `is_idle` 仍为 `false`；
  - **cancel 组**：`await conversation.cancel()` 后 0.05s 内 SDK 自身流生成器抛
    `AntigravityCancelledError: "The request was cancelled by the client."`，`is_idle==true`，
    `agent.__aexit__` 正常返回。
  - 证据：`evidence/sdk-min-cancel3.json`（`cancel_order_proven=true`）。
  ⇒ 前包“5s 内未停止”**不是 SDK 不支持 cancel**，而是产品 stop 路径未调用 SDK cancel（见 S2）。
- **S4（P2/P3 证成，产品接线缺陷确认）**：`evidence/decisive-product-vs-sdk-cancel.json`、
  `evidence/product-stop-lingering.json`（均 `real_model_calls: 0`，真 SDK + 真产品 `ModelReviewer`/
  `run_review_turn`/`ReviewLifecycle`/`ControlService` + 本地 fake SSE 上游）：
  - **A（当前产品停止路径）**：流式进行中 `ControlService.stop(cancel)` → 等待满 5s，返回
    `state=unconfirmed`/`confirmed=false`/`phase=cancelling`；`resource_stop_report_at_stop={}`；
    `lifecycle_still_reviewing=true`；`upstream_saw_client_gone=false`；`run.state=verifying`、refs 保留。
    stop 后 **6s 仍 `reviewing=true`、future 未完成、无 teardown 事实**（turn 未停、未被取消）。
  - **B（修复方向，探针内不改产品源码）**：在流式迭代中**并发轮询 stop event** 并调用 SDK 文档取消入口
    `conversation.cancel()`+`wait_for_idle()` → turn **0.013s 停止**，`is_idle=true`，
    `resource_stop_report.confirmed=true`。
  ⇒ 产品 reviewer 停止路径无效；根因见 `REPORT.md`（§根因）。

## 真实调用计数

| 阶段 | 真实产品/DeepSeek 生成请求 | 说明 |
|---|---|---|
| 本包 | **0** | 仅本地 fake 上游 + 真 SDK/真产品生命周期进程 |

- 旧 unknown/历史计数不在本包混算；本包不改任何历史账本。

## 独立裁定（简述；详见 REPORT §7）

- SDK 取消契约**可用且已证实**（`Conversation.cancel()`+`wait_for_idle()`）。
- 产品 reviewer 停止路径**未接入 SDK 取消入口**：流式阶段不轮询 stop、无 `conversation.cancel()` 调用。
- 属**重要缺陷，必须修复**，阻断 LG-022 最终 `done`；在现有 SDK 范围内可局部修复。
- QA **不自修**；修复后需新独立 QA 复验。
