---
title: "LG-037 R6 材料向量诊断 REPORT（离线几何 / 语料差异 / 标签审计）"
doc_type: report
category: engineering
updated: "2026-10-15"
---

# REPORT — materials-vector-diagnosis-r6-20261016

## 0. 恢复声明与边界（必读）

本 REPORT 是对**被中断**的 R6 只读诊断的**非重放收尾**。上一执行者的包装器在
REPORT/commit 之前，于 `token_budget_exceeded` 触发后 180 秒处 `exit 143`（预算终止）。
因此：

- **不是**正常退出；**不是**完整原始证据。
- 本轮**不重放**任何模型/网络调用，遵循第 6 节“未知副作用的中断不能自动重放”。
- 上一执行者的最终消息明确：**完整原始向量 / 完整分数 / `prompt_tokens` 未保留，无法重算**。
  本 REPORT **不编造**任何分数、边距或截断位置；所有未知均显式标为 UNKNOWN。
- 未触碰 main、并行 OCR owner、产品/测试/backlog/docs 代码。

本轮只归档并总结既有快照能**证明**的内容，不完成所有“期望但未采集”的分析。

## 1. 证据来源与可复算性

- 复用 R4/R5 owner 写出的**只读**文档向量缓存（`vectors.jsonl`）与 `crossmodal_results.json`；
  两者均存在且字段与脚本断言一致（已核对，见 §2）。
- 缓存 header：`cache_version=1`、`dim=768`、`model=embeddinggemma-2-Q8_0`。
- `crossmodal_results.json` 中 `vector_hits` 的 score 字段为 `null`（R4 三元组、R5 四元组），
  **故 query→doc 原始分数未保留，无法离线复算**。反向索引 / 语料 / 输入哈希被保留。

## 2. 已证明的结论（有据）

### 2.1 查询文本跨轮一致（proven）

- `Q_IMG_ZH` 文本在 R4、R5 完全相同：`老子 道德經 註解 學說`。
- 因此 R4→R5 的排名变化**不能**由查询文本变化解释。

### 2.2 语料差异（proven）

- R4 索引文档：`D1,D2,D3,D4,D5,D6,D7,M_AUD_ZH,M_IMG_EN,M_IMG_ZH`。
- R5 索引文档：`D1,D2,D3,D5,D6,M_AUD_DIQIU,M_AUD_ZH,M_IMG_EN,M_IMG_ZH,T_NORTHWIND`。
- R4 独有：`D4,D7`；R5 独有：`T_NORTHWIND,M_AUD_DIQIU`。
- 同标题文本文档（D1/D2/D3/D5/D6）跨轮 `fragment_hash` 不同、向量不逐位相同，
  余弦 0.9959–0.9992 —— 即**同标题文本内容本身发生了改变**，非仅集合增删。
- 媒体文档（`M_IMG_ZH,M_IMG_EN,M_AUD_ZH`）跨轮 `fragment_hash` 相同且**向量逐位相同**
  （cos=1.0）—— 媒体侧编码稳定。

### 2.3 排名结构变化（proven，来自被记录的 ordinal top-5）

- R4 `Q_IMG_ZH` top-5：`D1,D2,D3,D5,M_IMG_ZH`（第 5 名含目标图）。
- R5 `Q_IMG_ZH` top-5：`D1,D2,D3,D5,T_NORTHWIND`（目标图 `M_IMG_ZH` 掉出）。
- 唯一新进候选为 `T_NORTHWIND`（文本），它取代了 R4 中的 `D4`；`D7` 一并消失。
  → 目标图掉出与**语料组成变化**在时间/集合上一致，与图像或模型变化不一致（见 2.2）。

### 2.4 文档侧几何（proven，纯离线）

- R5 中 `M_IMG_ZH` 与 Laozi 文本簇 {D1,D2,D3} 的余弦为 0.7665–0.7856（偏高），
  与新进干扰项 `T_NORTHWIND` 的余弦为 0.6686。
- 即：查询目标图在**文档侧**并不比新文本干扰项更“远”；单看文档几何无法证明
  目标图会因语料变化而必然掉出 —— 排名翻转的决定性量是**未保留的 query→doc 分数**。

## 3. 标签审计（proven，范围受限）

- 标签侧数据（`labels_authorship`）存在于 R4/R5 结果文件中并被沿用；本轮未做
  任何 relabel / regate / 默认阈值变更。
- 由于 query 分数未保留，**无法**据标签给出候选真实排序边距；只能确认标签文件
  跨轮可用且被一致引用。

## 4. 明确 UNKNOWN / 未证明项

- query 向量**未保留** → query→doc 原始余弦**不可复算**。
- 原始 `/v1/embeddings` 响应与 `prompt_tokens`**未保留** → 不报告 token 用量或截断。
- `M_IMG_ZH` 在 R5 全体 10 候选中的**具体名次**：UNKNOWN（只知不在 top-5）。
- R4→R5 排名翻转的**精确分数边距**：UNKNOWN，不做推断。
- 不存在被证明的产品代码缺陷。

## 5. 中途失效的产物（诚实记录）

- `evidence/full_ranking_q_img_zh.py`：**语法错误，从未成功运行**。
  第 63 行未闭合字符串并误用 `.__add__`；`evidence/full_ranking_q_img_zh.json` **未生成**。
  该文件作为“被中断尝试”的原始证据**原样保留**，未在本轮修复或重跑，
  以免把未执行代码伪装成已复算结论。

## 6. 最小修复建议（仅在已证明范围内）

- 未证明代码缺陷，故**不提议任何产品代码改动**。
- 若要定量归因，建议的**唯一**最小前置动作是**实现证据可观测性**：让 R4/R5 一类的
  harness 持久化 query 向量与原始 embeddings 响应（含 `prompt_tokens`）。
  在该可观测性到位**之前**，继续抽样只会重复产出不可复算的证据。

## 7. 限制与状态

- 原 R5 质量 **FAIL** 结论维持不变。
- 本轮为**显式非重放恢复**，不宣称完成版本验收、不宣称原始证据完整。
- 产物位于本 owned 目录：`STATUS.md`、本 `REPORT.md`、`evidence/`、`http/`。
