---
title: "LG-032 独立只读封账审计（CLOSE-AUDIT）— 封账报告"
doc_type: audit
category: engineering
status: "CLOSE PASS — evidence-binding/mode/metering independently reproduced from raw results/SoT/physical JSONL/source hashes; no important defect; 032 evaluation scope may be done (PM decides); NOT full-product pass; real provider 0"
experiment_id: lg032-close-audit-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-close-audit
branch: qa/lg032-close-audit
base_commit: "271fefb448a77fcd0f419acba7d26e024d3aa658"
product_tree_object: "55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f"
updated: "2026-10-16"
owner: "agent:pi-lg032-close-audit（独立封账审计 owner；非产品/driver/entry/正式执行者；只读；真实 provider 0）"
---

# LG-032 独立只读封账审计 — 封账报告

## 0. 封账判定

- **判定：PASS**（对本包可核范围）。
- 任务 032 声称的 cohort3 事实**独立只读核对全部复现**，未发现**证据绑定 / 模式 / 计量**的重要缺陷。
- **建议 032「评估范围」可 done**（固定条件比较 + 独立机制 QA + 发现缺陷返修复验 + 默认 off 负结果记录本身成立）；
  **终判由 PM 决定**；本包**不写任务状态、不自判 done**。
- **不等于全产品 pass**；见 §6 覆盖/限制。
- **本包真实 provider 0**；未运行任何 SDK / 测试 / POST / runner；不嵌套；不 main merge / push / deploy / publish。

## 1. 事实清单（原始核对结论）

| # | 待核事实 | 独立实测 | 判定 |
|---|---|---|---|
| 1 | 有效 cohort3 = 固定 4 attempts 各一次全 delivered | s1_units__A→s1_units__B→s2_pipeline__A→s2_pipeline__B 各 1 次、4/4 `sample_delivered=true`、events/ledger/ts 顺序一致 | ✅ |
| 2 | generation 请求 20+20+17+27 = 84 | 逐 attempt `attempt_generation_requests` 实测同值；合计 84 ≤ 192 | ✅ |
| 3 | 唯一物理 ledger 0→20→40→57→84 | 单路径 `lg032-cohort3-data`；`generation_final.count` 20/40/57/84；count.json `{"count":84}` | ✅ |
| 4 | actual mode off/on/off/on + restored off | dispatcher 三开关四齐 congruent；第 3 attempt（s2A 接在 B 后）实测 off；`restored_off=true` x4；最终 SETTINGS=false | ✅ |
| 5 | A 无 selector；B 有 selector/lease3；A3(s2A after B) refs 无 selector | A 运行 lease_granted=0；B 运行=3/revoked=3；s2A session_refs=3 且无 lease | ✅ |
| 6 | Machine 5/5、5/5、7/7、7/7 | machine_gate passed/total 实测同值，exit 0 | ✅ |
| 7 | 授权 evidence-present check passed + per-node hash truth | `check_records=[{evidence-present,passed,4 refs}]` 四齐；`truths_before_accept=true`；`accept_response` 绑 `candidate_plan_hash` | ✅ |
| 8 | accept same candidate plan/requirements 绑定 + 幂等 + wrong target 拒 | 4 唯一 plan_hash；idempotent=confirmed；wrong target=409 illegal_transition | ✅ |
| 9 | async 真实独立 ModelReviewer passed / 0 unsubstantiated + 权威 teardown confirmed | `reviewer_kind=model`、`outcome=passed`、`unsubstantiated=0`、`model_calls=1` x4；`connection_id=deepseek-v4-flash` cred=true；`reviewer_cleanup` done/agent_closed/proxy_stopped/confirmed x4 | ✅ |
| 10 | 资源 stop 全部实际 | `member ready→released`(run scheduling finished)+`member.released`；cleanup reviewer confirmed | ✅ |
| 11 | SDK/API 原件持久可核 | native-sessions 18 `*.db`(600) 含真实 SDK trajectory 表；gen_metadata 合计 80 行（内容未打印）；artifacts diff patch 落盘；private-logs 副本 sha==formal | ✅ |
| 12 | 冻结 source 不变 | 产品 tree 55e4de56…、entry e8340f90…、driver 503a807f…、overlay df565291…、config a04a8f30… 全部 == 冻结；COHORT3 分支仅新增 2 个报告文件 | ✅ |
| 13 | 四 attempt same plan/seed/profile/budget 仅 mode 变量 | seed_head s1=`53458ac7…`/s2=`6fa0fd00…` == pin；`initial_head==seed_head`；caps 192/48 不变；mode 为唯一自变量 | ✅ |

## 2. 成本口径（分列，不洗失败成本）

- 旧 032 cohort1 模式 invalid **87** + cohort2 输出 dir STOP **19** = **106 失败成本不可洗**；
  与有效 **84** 分列 ⇒ **032 本轮真实合计 190**。
- cohort3 上限 **192 / attempt 48 / 已知总上限 298** **未超**。
- 有效 **A 合 37**（20+17）/ **B 合 47**（20+27）；请求数差 10 **不是完整 token/钱**。
- elapsed 逐样本取自 raw：105.38 / 59.21 / 96.83 / 115.49；**不用失败 median 推节省**。
- **SDK tokens / 实际钱 = unknown**（`usage={"unknown":["usage"]}`，不记 0）。
- 开发 pi 可得 metadata 私有 `LG032-SHARED-PI-COST-AUDIT.md`（snapshot `2026-10-15T21:24:34Z`，**工具自报估计非账单**）：
  LG032 归类 26 logs / input 1,678,454 + output 517,978 / cacheRead 124,136,832；shared/unassigned 另列
  （51 UNASSIGNED logs / 1,353 calls）；使用文件缺失 42 记 unknown；**后续 dispatch 不含不能称最终**。
  **不把 request 数/时间当成本节省，不 default on。**
- 旧 031 86 / 023 65 / core **unknown** 另列，**不混 cohort**。

## 3. 证据路径（只读，引用）

- 物理 ledger：`/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-data/generation/{generation.count.json,generation.jsonl}`
- formal outputs：`/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-formal/{runs/<attempt>/{result.json,.formal_attempt_started},evidence/<attempt>.json}`
- SDK 原件：`/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-data/native-sessions/**/*.db`、`artifacts/**`、`attempts/**`
- 私有副本/STATUS：`/home/yhvh/code/lightgravity-bot-worktrees/lg032-cohort3-private-logs-20261015T212653Z/`
- 旧账本：`lg032-method-final-data/generation/*`(87)、`lg032-cohort2-data/generation/*`(19)
- 报告：`probes/lg032/COHORT3/{COHORT3-FORMAL-REPORT.md,ENTRY-INDEPENDENT-AUDIT-R1.md,COHORT3-FORMAL-FREEZE-R1.md}`、
  `probes/lg032/COHORT2-QA/{COHORT2-FORMAL-REPORT.md,REPORT-SERIAL-R1.md}`、本 `CLOSE-AUDIT/`
- shared cost metadata：`/home/yhvh/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/LG032-SHARED-PI-COST-AUDIT.md`

## 4. 关键 hash（脱敏，未含 secret）

- 产品 tree `55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f`
- entry `e8340f9035c06568bcd311c89f2f227f3e0b5504d0303505862c67e27aa590e2`
- overlay `df5652919e54830f7af5af8fa8c26a0f2cb527d3ddca2c1811259054acc788bf`
- driver `503a807fe987b65236222b734127b21aff70455e3070403fe98fe9f62b286208`
- config `a04a8f309a72626c5b039039198feab03f143966e6634bf1fe5228ff0834a117`
- ledger count `fef0bd52e61e58a2f6200194bf7af5219a5d8c1f9ffd2dcbd7335fb81d92e68f`；jsonl `a266e2fd8fa80cbc828746b14d5b7aaaf0923d90c97331b42665295971aa3f72`
- result.json：`b54d3c01…a4d00` / `09c237d9…bc309` / `0bf3c823…e6f7f6` / `fe0bf73e…97620d`
- 旧 cohort1 `609946be…a01e68`(count) `beba08e0…871abd`(jsonl)；cohort2 `be90a0f9…658585`(count) `15a4bb00…595fbb`(jsonl)

## 5. 门覆盖（可引用只读范围）

- 核心 022/R1、032 stageA→返修 R1、BOUNDARY-R1、SERIAL-R1 均独立源质量证据；**本包 0 不重跑全套**。
- SERIAL-R1 证据支持「旧 cohort1 s2A=6 refs B-like 污染已修」（本审计实测 s2A refs=3 无 lease）。
- 旧 cohort STOP/invalid 补遗：cohort2 remaining 由 144 更正为 **173**(192−19)，原历史报告字节保留。

## 6. 覆盖范围与限制（不宣全产品 pass）

- 结论仅指 032 任务本身：「固定条件比较、独立机制 QA、发现缺陷返修复验、默认 off 负结果记录」是否可 done。
- **不能被这 4 个 tiny code case 覆盖**：full checkpoint skip、自动 resume（未实现）、OS security sandbox
  （非 Git worktree）、资料 OCR/embedding 真实质量、中文 ASR 门；**未来外部 quality block 不造循环**。
- SDK token / 实际账单 / 后续 dispatch 为 **unknown**；shared pi 成本为估计非账单。

## 7. unknown

- SDK per-attempt token、实际费用、计费账单 = unknown（不记 0）。
- shared pi QA 成本为工具自报估计；unassigned/边界未做 hard arm split。
- 资料服务（21:13Z 复查不可达）相关未涉。

## 8. 风险与后续

- 风险：4 tiny case 样本量小，机制门通过不代表全产品负载/质量；生产默认须保持 off 或按开关/回退策略，不因本轮默认 on。
- 后续：PM 决定 032 是否 done；若需扩展质量门（OCR/ASR/resume/sandbox）另立包，不借本审计循环。
- 本包仅新增 `probes/lg032/CLOSE-AUDIT/**`；未改任务状态 / 产品 / driver / 旧报告字节。

## 9. 修订历史

- 2026-10-16（真实 provider 0）：独立只读封账；身份/ledger/mode/review/accept/stop/cost 全部 raw 复现一致；
  封账 **PASS**；032 交 PM 判 done。
