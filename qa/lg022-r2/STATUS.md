# LG-022 独立复验 R2 — STATUS

- Owner：独立新 pi 上下文（`agent:pi-lg022-r2` 复验角色；非 R2 返修者、非集成者、非 017/018/019/021/027 实施者）。
- Worktree：`/home/yhvh/code/lightgravity-bot-worktrees/lg022-qa-r2`（branch `qa/lg022-r2`）。
- 开工 HEAD：`0144eb7`（产品树 == 最终整合 HEAD `85adc82`）。
- 预算：真转发硬上限 **10**（本 phase）；输出 ≤18000；HTTP 120s；并发 ≤2；重试 0。

## 进度

- [x] 读 AGENTS/agent/PROJECT/PROGRESS/BACKLOG/docs06版本门/docs08(1.10.0)/LG022+017+016+027、最初 QA、reverify-r1/REPORT、REFIX-R2/REPORT、INTEGRATION-7、实际代码。
- [x] 核实际最终整合 HEAD：`85adc82`（产品树 == `0144eb7`）；claim 保持 `in-progress`。
- [x] 冻结 PLAN（`PLAN.md`）。
- [x] 离线独立证明持久 generation ledger（`evidence/ledger-proof.json`、`service-ledger-*.json`）：全 6+4 项 pass。
- [x] 离线 stop-gate 释放证明（`evidence/stopgate-proof.json`）：R2A–R2E 全 pass。
- [x] 真实链 settings→task→SDK 产物→异步 reviewer→停止证明→awaiting→accept（`evidence/real-chain.json`）。
- [x] 真 light Q&A（`evidence/light-qa.json`）。
- [x] D2/D3 确定性探针（`evidence/deterministic-probe-r2.json`）：restart 不重放 / 跨 Run 预算 / cancel-during-review 真停止。
- [x] 全量 pytest（本 worktree）：772 passed, 5 skipped；契约 1.10.0 一致。
- [x] REPORT + 精确本地 commit。

## 真实调用计数（防洗数）

| 阶段 | 真实生成请求 | 状态 |
|---|---|---|
| 旧 QA 首轮（`8e81089`） | **unknown**（含 429 rerun；单列保留） | 不洗 0 |
| R1 复验（`6228474`） | **6/10**（单列保留） | 已知 |
| 本 R2 phase | **8 = 主链 7（独立账本 limit10）+ light 1（独立账本 limit3）**；非同一硬限 | 见补查收尾（§S2） |

- 未宣称本任务累计 ≤20；旧 unknown 单列；未借改代码/重放未知写入。
- **修正**：原“8/10”是两独立 phase 事后相加，**非统一硬限内用量**（主链与 light 用不同 data_dir/limit）。

## 补查收尾（本包，2026-10-16）

> 详见 `SUPPLEMENT.md`（`REPORT.md` 的准确 scope 修正，不覆盖原报告）。本包**真实产品/模型调用 0**。

- **前包 `bounded-uuv5ekyo`**：wall 限 600s，**wall143** 被终止；dispatch log 保留。其真实执行为
  运行 `review_cancel_sdk_proof.py` 并调试 async（多次 100s 挂），产物 `/tmp/lg022-cancel-sdk.json` 保留。
  副作用：**无真实 DeepSeek 调用**（主链账本 mtime 03:25 早于前包活动，未被追加）；其 async 调试是否写入
  产品 data/workspace 为 **unknown**，本包**不重放**。
- **真实 SDK cancel/stop 补证：仍未证实**。前包脚本 `all_pass=false`（`confirmed_after_real_sdk_stop=false`,
  `real_sdk_teardown_fact={}`, `upstream_saw_client_gone=false`）。挂起属 **QA harness 未跑成 + SDK 行为 unknown**，
  **非产品 fail**，也**非** SDK cancel 成功。原 REPORT §4 的 cancel-during-review 仍是 **deterministic-double**（无真实 SDK session）。
- **主链 7 + light 1 未共用同一账本**：主链 `/tmp/lg022-r2-real`（limit **10**, count 7），
  light `/tmp/lg022-r2-lightqa`（limit **3**, count 1）。**未统一硬总额**；已知实际 **8** 可核实但不受统一硬限。
  属 QA 流程缺口，**非**产品 persistent ledger 缺陷（后者已独立证明通过）。

## 结论（scope 修正）

- **已通过**：真实主链（真 worker+reviewer→awaiting→绑定 accept）、停止/完成门产品机制、
  生成计数器产品机制、D2/D3 确定性/真链、全量 pytest。
- **仍未满足/未证实**：① 真实 SDK cancel/stop 补证；② 历史实验统一硬总额流程缺口。
- **是否阻断 022 最终 `done`**：产品机制未见缺陷；但若验收要求真实 SDK cancel 的直接证据，则该项尚未满足，
  构成**证据完整性阻断**，需补齐或由 PM 明确接受限制。**本包不擅自降门**，门保持原样。
- 按 agent.md，QA 只提供独立复验结论，最终 `done` 由主代理/用户决定；本包不自改 LG-022 状态。
