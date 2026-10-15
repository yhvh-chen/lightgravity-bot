# LG-022 流式停止缺陷包 — 独立复验 STATUS

- Owner：`agent:pi-lg022-stream-qa`（新独立上下文；非 stream 修复者/集成者/031 实施者；产品只读）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-stream`（branch `qa/lg022-stream`）。
- 核准确 HEAD：`e0a8cec`（= `main` = batch8 记录 commit；产品树 == `975afc2` 集成点）。
- 持久 QA 目录：`qa/lg022-stream/**`；runtime/ledger 持久目录：`lg022-qa-stream-data/`（非临时）。
- 预算：真实 DeepSeek 生成 **总上限 10**（唯一持久 ledger 路径，全 stage 共用）；output ≤14000；HTTP 120s；并发 ≤2；retry 0；
  wall 1200s；round ≤220；noncache ≤280k；idle 240s；开发 retry 0。

## 进度

- [x] 核 HEAD/claim、AGENTS/agent、docs06 集中门、docs08（§8.1/§9，契约 1.10.0）、LG-022 原文、
      既有 022 QA（`qa/lg022`）/R1/R2/补遗、SDK 调查包、STREAM-STOP-FIX、INTEGRATION-8。
- [x] 冻结 PLAN（`PLAN.md`）+ 冻结唯一 ledger 路径/limit（`harness/unified_phase_ledger_config.py`）。
- [x] 第一离线硬门：真 SDK + 真产品装配 + 有效本地 fake SSE，流式 pause/cancel 都触达 SDK cancel/idle/真实退出后才 confirm
      （`evidence/stream-stop-hard-gate.json`，`hard_gate_pass=true`；S1 cancel 0.21s、S2 pause 0.22s、S3 unknown-held、S4 normal drain）。
- [x] 持久 generation ledger 离线门（`evidence/ledger-proof.json`，L1–L5 全 pass）。
- [x] 第二主链一例（真实 DeepSeek 5/10，唯一 fixture）：`evidence/main-chain.json` + `main-chain-verdict.json`（全 pass）。
- [x] 全量 pytest（791 passed, 5 skipped）+ mypy（137 files clean）+ STREAM-STOP-FIX 探针交叉核。
- [x] REPORT + 精确本地 commit。

## 真实调用计数（防洗数，不归零）

| 阶段 | 真实生成请求 | 状态 |
|---|---|---|
| 首轮 QA（`8e81089`） | **unknown**（含 429 rerun） | 单列保留 |
| R1 复验（`6228474`） | **6** | 单列保留 |
| R2（`cea87ab`） | **8**（主链 7 + light 1，两账本未统一） | 单列保留 |
| 本 phase | **5/10**（唯一持久 ledger；主链 worker+reviewer） | 门内通过 |

- 本 phase 0 额外 light 调用、0 浏览器矩阵、0 QA 返修重跑；离线硬门/账本门 0 真实模型调用。
