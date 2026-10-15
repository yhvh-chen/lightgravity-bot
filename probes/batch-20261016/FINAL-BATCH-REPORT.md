---
title: "2026-10-16 批次最终报告（LG-032 评估范围关闭 + 本轮全部交付收拢）"
doc_type: report
category: engineering
status: "FINAL (local only) — LG-032 evaluation-scope done per independent close audit PASS; 035/037 in-progress; 040/041 todo; no push/deploy/publish"
updated: "2026-10-16"
---

# 2026-10-16 批次最终报告

本报告由**唯一 main 最终整合 / PM 文档 owner** 撰写。所有执行仍经 pi + 现有 DeepSeek；主代理只 PM，**无 nested 代理**；
**未 push / deploy / publish**；无外部消息。所有结论带本地证据链接，标注准确 branch/head、验证范围与剩余外部条件。

## 1. 整合事实（可核）

| 项 | 值 |
|---|---|
| 开工 main | `5df1956`（clean） |
| 前置保全 | 无 PM dirty（main 已 clean） |
| 合入 1（ff-only） | `prep/lg035-real-truth@9ad8315` ← main 为直接祖先 ⇒ main `= 9ad8315` |
| 合入 2（--no-ff） | `qa/lg032-close-audit@4d175113`（含 `fix/lg032-cohort3-entry@271fefb`）→ merge `d0c0c4e` |
| 最终 main（产品树） | `d0c0c4e`；`HEAD:backend/lightgravity = 55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f` |
| 产品路径 diff `5df1956→d0c0c4e` | **空**（backend/frontend/src/tests/docs/pyproject/uv.lock/Makefile） |
| 契约 / SDK / 默认 | `1.11.0` / `google-antigravity==0.1.22` / 协作候选 default **off** |
| 任务 CLI（backlog 专用根） | `validate` 41 tasks/0 diagnostics；`digest` **2 todo / 2 in-progress / 37 done**，complete=true；`ready=[]` |

**为什么本包不重跑产品全套测试**：产品 tree 与 main 逐字节相同，源机制已由独立 **R1 / BOUNDARY-R1 / SERIAL-R1**
证据、`329 affected tests + mypy` 与独立 `SERIAL-R1` 覆盖；本集成只新增 `harness / probes / docs / 任务元数据`。
故仅核产品 hash same。**不称 "whole product pass"**，**不把真 SDK + fake 门叫 real provider**。

## 2. LG-032 最终依据与计量（评估范围 done）

**判定依据**：独立只读封账审计 `qa/lg032-close-audit@4d175113`
（`probes/lg032/CLOSE-AUDIT/CLOSE-REPORT.md`，对 `fix/lg032-cohort3-entry@271fefb`）判 **PASS**——
证据绑定/模式/计量由原始结果/SoT/物理 JSONL/源哈希独立复现，**无重要缺陷**；PM 据此将 LG-032 置 `done`（**仅评估范围**）。

**有效 cohort3（4/4，各唯一次，无重跑/repair/retry/STOP）**：

| # | attempt | delivered | first-pass | machine | mode | restored off | review | unsub | repair |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `s1_units__A` | ✅ | ✅ | 5/5 | off | ✅ | passed | 0 | 0 |
| 2 | `s1_units__B` | ✅ | ✅ | 5/5 | on | ✅ | passed | 0 | 0 |
| 3 | `s2_pipeline__A` | ✅ | ✅ | 7/7 | **off**（接 B 后仍 off） | ✅ | passed | 0 | 0 |
| 4 | `s2_pipeline__B` | ✅ | ✅ | 7/7 | on | ✅ | passed | 0 | 0 |

- **mode-isolation**：A refs 无 selector / `lease_granted=0`；B refs 有 selector / `lease_granted=3, revoked=3`；
  `s2_pipeline__A`（A3）接在 B 后仍**无 selector**。
- **唯一物理 ledger**：`0→20→40→57→84`（`generation.count.json={"count":84}`）；reqs `20+20+17+27=84 ≤ 192`，各 ≤48。
- **accept**：绑定同 candidate plan/requirements，**幂等 confirmed**、**wrong target 409 `illegal_transition`**；
  `check_records=[{evidence-present,passed,4 refs}]`；per-node hash truth。
- **异步真实独立 ModelReviewer**：`reviewer_kind=model`、`outcome=passed`、`unsubstantiated=0`；权威 teardown
  `done/agent_closed/proxy_stopped/confirmed`。
- **SDK 原件**：18 个 `*.db`（600）含真实 trajectory；源哈希与冻结一致（entry/overlay/driver/config/tree）。

**旧失败协议成本（永久单列，不洗白/不归零/不混入有效 AB）**：
- cohort1 nominal 4 delivered 但 **87 模式污染 AB invalid**（s2A 实际 pool）；
- cohort2 **19 输出 dir assembly STOP**；
- 合计 **106**；**032 本轮真实已知 = 106 + 84 = 190**；新已知上限 **298**（=106+192）未超。
- 有效 **A 合 37 / B 合 47**（多 10 requests **≠** 全 token 钱节省）；elapsed `105.38/59.21/96.83/115.49`，
  **不拿失败 median 作收益**。

**成本口径**：product SDK token/实际账单 **unknown**（不当 0）；开发 pi 可得 metadata（私有
`~/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/LG032-SHARED-PI-COST-AUDIT.md`，snapshot `21:24:34Z`）
LG032 可靠映射 26 logs / 1574 turns / input 1,678,454 + output 517,978 / cacheRead 124,136,832；
边界/共享 unassigned 单列不硬分 arm；`toolpriceestimate 9.728773` **非 provider 账单、币种不推断**；
晚于 snapshot/本最终 dispatch 不包含，**不能称最终全成本**。脱敏摘要见
[`FINAL-CHECKPOINT/LG032-COST-APPENDIX.md`](FINAL-CHECKPOINT/LG032-COST-APPENDIX.md)。
旧 **031 86 / 023 65 / core unknown / 全部 pi QA 修复失败开销**分列，不双算。

**done 边界（不扩大）**：**非全产品 pass**；**2 tiny code case 无统计承诺**；全 cost unknown/收益不支持默认启用；
**default off / 回退保留**；OS sandbox / auto-resume / checkpoint skip / OCR / embedding / ASR 质量**未覆盖**；
**不扩 LG-031 原 done 机制范围**。

## 3. LG-035 真实真值预备（in-progress，未质量通过）

`prep/lg035-real-truth@9ad8315`（前 `77596f4`）：`probes/lg035/TRUTH-PREP/**` 完整备料 +
LG-035 补遗（status in-progress）。

- 两份**严格配对**真实中文样本：Z1 公共领域书页扫描（`File:10-13老解老.pdf` p10）+ Wikisource 人工
  `ProofreadPage` **level 3**；Z2 `方言調查表格` 表格型 PDF（NLC416）**18 页纯扫描、无 text layer**，
  p2 与人工 GT **同 file/同页**严格配对。
- Z2 binary `sha1 fe5572520076aee2f3a252277e0fa648588a02bc`、**392,964 B**，private **700/600/ignored**；
  **repo 仅合法 manifest/GT/评分协议**，binary 不入 repo。
- **真实 OCR/embedding/ASR 0 新调用**，**quality NOT measured**；授权端点 `192.168.8.12:11434` 不可达；
  **mixed born-digital + scan 类仍缺**。**不能标 035 done 或解锁 040/041**。
- **GET 预算事件如实**：旧检索 **13/12 超 1**（保留）；另明确授权 **1 GET** 补 Z2 → **累计 14**；**不抹预算事件**。
- **XFUND NC 不需用户选择作阻塞依赖**：PD 已有替代路径且 XFUND 未用。

## 4. 资料服务与 ASR 外部条件

- 候选资料服务 `192.168.8.12:11434` **仍不可达**：私有 latest 复核
  `~/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/MATERIALS-RECHECK2-HEALTH.md`
  （`21:13:33Z`）：`GET /health` HTTP 000/curl 7、`GET /v1/models` HTTP 000/curl 28 连接超时，**无 TCP**，
  **0 POST**；协议 **llama.cpp / OpenAI-compatible（非 Ollama）**。**本包不再探测、不自换 endpoint/model**；
  仅脱敏归档 latest 结论 + 路径。
- **资料真中文二样本预备 ≠ quality pass**；**035 混合类样本 + OCR 真实质量、037 真实 vectors quality/召回、
  040 集中 QA 依赖、041 ASR 质量** 均未达、未完成。
- **不因 XFUND NC / 普通实现选择要求用户确认**；继续需要**原候选服务恢复或授权可达同协议 endpoint**。

## 5. 交付清单（本轮新增/更新，均在 main `d0c0c4e`）

- `probes/lg032/**`：METHOD-FINAL / FINAL-COHORT / COHORT2-QA / COHORT3 / MODE-ISOLATION / **CLOSE-AUDIT**
  （`CLOSE-REPORT.md`、`REPORT-v1.md`、`STATUS.md`、`metadata.json`）。
- `probes/lg035/TRUTH-PREP/**`：REPORT / PLAN-STATUS / Z2-BINARY-CLOSE / manifest / protocol / truth(GT) / private(.gitignore)。
- `.gitignore`：新增 `probes/lg032/FINAL-COHORT/fixtures/*/seed.git/`（可再生成 seed 对象库不入库）。
- `backlog/tasks/LG-032.md`：frontmatter `done`（保留全部历史重开/失败/成本/assignee）+ 封账收口记录；
  `backlog/tasks/LG-035.md`：TRUTH-PREP 补遗（additive）。
- 本报告 + [`FINAL-CHECKPOINT/RESUME.md`](FINAL-CHECKPOINT/RESUME.md) +
  [`FINAL-CHECKPOINT/LG032-COST-APPENDIX.md`](FINAL-CHECKPOINT/LG032-COST-APPENDIX.md) +
  `FINAL-CHECKPOINT/{validate.txt,digest.json,ready.json}`。
- 文档同步：`PROGRESS.md`、`BACKLOG.md`、`docs/06 §6` 当前排期状态、`README` 最新入口状态（历史保留）。

## 6. 覆盖范围与限制（诚实，不宣全产品 pass）

- 结论仅指 LG-032 任务本身：「固定条件比较 + 独立机制 QA + 发现缺陷返修复验 + 默认 off 负结果记录」是否可 done。
- **不能被 4 个 tiny code case 覆盖**：完整 checkpoint skip、自动 resume（未实现）、OS security sandbox
  （非 Git worktree）、资料 OCR/embedding 真实质量、中文 ASR 门。
- provider token / 实际账单 / 后续 dispatch 为 **unknown**；shared pi 成本为**工具自报估计**（非账单）。
- **历史缺口如实索引**：METHOD-AUDIT（023 方法）/ PRESERVATION-INCIDENT（TMD/覆盖/预检 dry 删除/旧 store 缺口）
  报告均保留；**不谎称 100% 原件从无缺口**，也不以重建冒充原件。
- 旧 **106** 与旧 **13/12** 预算事件在本报告**不隐去**。

## 7. 参考

- [LG-032 封账报告](../../lg032/CLOSE-AUDIT/CLOSE-REPORT.md)
- [LG-032 cohort3 正式报告](../../lg032/COHORT3/COHORT3-FORMAL-REPORT.md)
- [LG-035 TRUTH-PREP 报告](../../lg035/TRUTH-PREP/REPORT.md) 与 [Z2 补遗](../../lg035/TRUTH-PREP/Z2-BINARY-CLOSE.md)
- [LG-031/032 依赖与集成历史](LG031-BOUNDARY-INTEGRATION.md)
- [RESUME](FINAL-CHECKPOINT/RESUME.md) ｜ [032 成本附录](FINAL-CHECKPOINT/LG032-COST-APPENDIX.md)
- [滚动排期](../../../docs/06-roadmap.md) ｜ [任务入口](../../../BACKLOG.md) ｜ [开发规则](../../../agent.md)
