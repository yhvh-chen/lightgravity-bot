# DOC_CORRECTION — agensh SDK 纠正版报告文档更正（纯离线）

doc_type: doc_correction
experiment_id: agensh-sdk-corrected-20261015
corrected_at_utc: "2026-10-15T07:20:00Z"
scope: "REPORT.md 表达更正 + 追加证据/manifest；0 模型样本、0 重跑、0 产品代码/driver/fixture/raw 修改"

本文件记录对 `REPORT.md` 的**文档级更正**。更正只改文档表达与相应 hash 记录，不新增任何
SDK/模型样本，不读取凭证，不打印 env，不递归派工，不 commit/push/merge/deploy，不修改
`PROJECT.md`。归属仅为 `probes/agensh-orchestration-sdk-corrected/`（REPORT + 追加证据/manifest）。
首轮 `probes/agensh-orchestration-sdk/`、r2、fixtures、`runs/` 原始 raw、`driver/` 产品代码、schema、
阈值全部**未修改**。

## 1. 改前副本与哈希

| 项 | 值 |
|---|---|
| 改前 REPORT 副本 | `evidence/phaseE/REPORT.pre_doc_correction.md` |
| 改前 REPORT sha256 | `30e081c042ed31076351a16634e65b014548924f18b578a1400030607482dec0` |
| 改后 REPORT sha256 | `d369f0f9771fbe2db91405b86a9d01f1e041cf900da76cb760a599d415626bb1` |
| 初次 manifest（保留） | `evidence/EVIDENCE.initial.sha256`（= 原 `evidence/EVIDENCE.sha256`，sha256 `ee424532e90fe76977bd612ab8016d2efe388e0b2017a21457ff9618c7985872`） |
| 最终 manifest | `evidence/EVIDENCE.sha256`（本次文档更正后重算） |
| 最终复制证明 | `COPY_VERIFICATION.final.json`（新增；不改初次 `COPY_VERIFICATION.json`） |

> **不假称**：初次 `COPY_VERIFICATION.json` 只覆盖**文档更正前**的 470 文件树，**不**覆盖本次
> 文档更正后的最终树。最终树的覆盖以 `COPY_VERIFICATION.final.json` + 重算的 `EVIDENCE.sha256`
> 为准；初次 manifest 以 `EVIDENCE.initial.sha256` 原样保留以便对照。

## 2. 三处更正

### 更正 1：第 9 节收益方向

原文把度量的方向写成“独立 planner 编排……**没有带来 ≥15% 的 token 或时间收益**”。实际度量是
**移除独立 planner（C 相对 B）**的收益，而非“planner 无收益”。更正为：C 相对 B 的中位 relay
tokens 改善 8.84%、中位耗时改善 3.16%，均 < 15%，未达门。

同时澄清：**B 2/3、C 3/3 是 run 级代码验收**（`all_passed_samples`），且是在**部分 turn 预算
耗尽**（正式 51 turn 中 44 succeeded、7 个 `budget_exhausted`/`failed`）的前提下得到，
**不是所有 SDK turn 都成功**。因此不得把“生产可删除独立编排”作为结论。

### 更正 2：新增 usage 核对（纯离线算术）

在 `runs/formal/t2_interface__C__r0/turns/r1-edit-w2.json` 中，该 turn 6 个
`relay_calls[].usage.total_tokens` = 5,085 / 5,919 / 6,734 / 7,063 / **7,997** / 8,344，求和
**41,142**；同 turn SDK `usage.total_tokens` = **33,145**，差 **7,997**。总量上新总中继
**845,223** 与 driver 快照 **837,226** 的差同为 **7,997**。详见
`evidence/phaseE/USAGE_RECONCILIATION.json`。

- 以原始中继 **reported usage** 为准；usage 有回报、`tokens_unknown_calls=0`，**不是** unknown 估算。
- 差异根因**本次未验证**，不猜缓存/重试/迟到计费。
- **不**再以 driver 快照口径的 **12.29%** 作为最终收益。

### 更正 3：首轮 calibration HTTP/token（只读首轮 summary）

原文称首轮 calibration 的 HTTP/token 为“未知”。只读
`probes/agensh-orchestration-sdk/runs/calibration/CALIBRATION_SUMMARY.json` 可得已知值：
**7 turn / 20 HTTP / 93,658 tokens / 38.879 s**（main 6 turn、19 HTTP、91,224 tokens、37.129 s，
加 no-skills 复验 1 turn、1 HTTP、2,434 tokens、1.75 s）。其中 **7/6 记为硬上限违规，不改称 soft**。
首轮 raw 文件（`CALIBRATION_SUMMARY.json`、`CALIBRATION_RAW.json` 等）**原样保留**。

## 3. 未改动声明

- 未新增模型样本；未重跑测试/校准/正式；未改 `driver/`、`fixtures/`、`runs/`、session DB、任何 raw。
- 未改 schema、阈值、协议冻结 (`PROTOCOL.md`)、`CALIBRATION.md`、`PROGRESS.md`、`README.md`、`PROJECT.md`。
- 未触碰首轮 `agensh-orchestration-sdk/`、`agensh-orchestration-r2/`、r2 产物。
- 只同步本次文档（`REPORT.md`）与新证据回本实验主目录；源 worktree 同名目录可同步文档。

## 4. 校核

- usage 和与差：41,142 − 33,145 = 7,997；845,223 − 837,226 = 7,997（离线算术，已复算）。
- 链接检查：`REPORT.md` 内引用路径均指向本目录既有文件（`evidence/phaseD/analysis.json`、
  `runs/formal/t2_interface__C__r0/turns/r1-edit-w2.json`、`evidence/EVIDENCE.sha256`），
  首轮 calibration 引用路径指向只读源目录。
