---
title: "LG-037 R6 材料向量诊断 STATUS（非重放恢复）"
doc_type: status
category: engineering
updated: "2026-10-15"
---

# STATUS — materials-vector-diagnosis-r6-20261016

## 任务性质

- 这是对被中断的 R6 只读诊断的**收尾恢复**，不是重跑。
- 上一执行者包装器在 REPORT/commit 之前，于 `token_budget_exceeded` 触发后 **180 秒** 处
  `exit 143`（预算终止）。**不能**声称上一进程正常退出，也**不能**声称原始证据完整。
- 遵循本项目第 6 节“未知副作用的中断不能自动重放”：本任务**不重放**模型/网络调用。
  本轮为**显式非重放恢复**，只归档与总结既有产物。

## 副作用与并发核查

- 无模型/网络调用（本轮）；`http/*.raw.json` 与 `evidence/*` 均为上一轮留下的静态快照。
- 已核查进程列表：不存在仍在本 owned 目录写入的残留进程。列表中的
  `materials-ocr-layout-r6-20261016`（PID 2838424）属于**并行 OCR owner**，未触碰；
  其 `pi` 子进程（PID 2838427）亦未触碰。主仓/main 未触碰。
- 当前仅有的 git 改动：本 worktree 分支 `investigate/materials-vector-diagnosis-r6-20261016`，
  HEAD 基线 `7c27f18`，唯一未跟踪路径为本 owned probes 目录。

## 产物完整性（诚实口径）

| 文件 | 状态 |
|---|---|
| `evidence/offline_geometry.py` | 完整，已产出结果 |
| `evidence/offline_geometry_results.json` | 完整（12978 B） |
| `evidence/ranking_boundary.py` | 完整，已产出结果 |
| `evidence/ranking_boundary_results.json` | 完整（425 B） |
| `evidence/full_ranking_q_img_zh.py` | **不可执行草稿**：第 63 行语法错误（未闭合字符串 + 误用 `.__add__`） |
| `evidence/full_ranking_q_img_zh.json` | **缺失**（脚本从未成功运行） |
| `http/health.raw.json` | 完整（`{"status":"ok"}`） |
| `http/models.raw.json` | 完整（模型清单，未打印任何秘密） |

## 结论口径

- 原始 query 向量与原始 `prompt_tokens` **未被保留**（R4/R5 harness 的 `score` 字段为
  `null`），因此**无法**离线重算 query→doc 分数；本轮**不编造**边距或截断位置。
- 既有快照足以证明**查询文本一致**、**语料差异**与**标签审计**层面的实际事实，
  不足以给出被拒候选的真实分数与排名边距。
- R5 的质量 FAIL 结论不变：本轮不做任何 relabel / regate / 默认阈值变更。

## 下一步建议

- 若需定量归因排名翻转，**最小前置修复**是先补齐**证据可观测性**：让 harness 持久化
  query 向量与原始 embeddings 响应（含 `prompt_tokens`），再抽样；在此之前继续抽样只会
  重复产生不可复算的证据。
- 未证明存在代码缺陷，故本轮**不提议**任何产品代码改动。
