---
title: "LG-032 成本附录（脱敏口径摘要）"
doc_type: report
category: engineering
status: "sanitized summary — tool-reported estimate, NOT provider billing; not final all-cost"
updated: "2026-10-16"
---

# LG-032 成本附录（脱敏口径摘要）

本附录只归档**脱敏口径摘要**，便于复核 032 成本边界。**不包含**原 prompt、raw 大 metadata、凭证、日志正文或任何 secret；
原 metadata 仅保留在开发机私有路径，不 repo。

## 1. product SDK（产品执行）

- **token / 实际账单 = `unknown`**（不当 0）。cohort3 4 attempt 的 SDK result 内 `model_usage`/`usage` 记为
  `{"unknown": ["usage"]}`，SDK 不回报 per-attempt token。
- 已知**真实 generation 请求数**：有效 cohort3 = **84**（20+20+17+27，≤192）；旧 cohort1 87 + cohort2 19 = **106** 单列；
  本轮 032 真实已知合计 **190**（`=106+84`），新已知上限 **298**（`=106+192`）未超。

## 2. 开发 pi / shared pi（工具自报估计，非账单）

- 私有来源：`~/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/LG032-SHARED-PI-COST-AUDIT.md`
  （+ 同目录 `LG032-metadata.csv` / `LG032-metadata.json`），**snapshot as-of `2026-10-15T21:24:34Z`**。
- **LG032 可靠映射**：26 logs / **1574** unique model turns /
  noncache input **1,678,454** + output **517,978** / cacheRead **124,136,832**。
- **边界 / 共享 unassigned 单列**，**不硬分 arm**（不把 whole-project dispatcher 快照全部归 LG032）。
- `toolpriceestimate = 9.728773` 为**工具自报估计、非 provider 账单**；**币种不推断**。
- 晚于 snapshot 的 dispatch 与**本最终 dispatch 不包含**在 snapshot 内 ⇒ **不能称最终全成本**。

## 3. 分列不双算

- 旧 **LG-031 工程 86**（34+24+28）、旧 **LG-023 65**（45+4+16）、core QA **unknown**、以及**全部 pi QA / 修复失败开销**
  均**分列**，**不双算**进有效 cohort 成本。
- 有效 A 合 37 / B 合 47（多 10 requests）**≠** token/钱节省；elapsed 按 REPORT 105.38/59.21/96.83/115.49；
  **不拿失败 median 作收益**，**收益不支持默认启用**。

## 4. 结论

成本口径**不支持**因本轮数据默认启用自主协作路径；**default 自主池仍 off、回退保留**。
详细证据：`probes/lg032/CLOSE-AUDIT/CLOSE-REPORT.md` §2、`probes/lg032/COHORT3/COHORT3-FORMAL-REPORT.md` §6。
