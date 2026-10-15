---
title: "LG-033 契约准备探针记录（只读，未推理）"
doc_type: probe-record
category: architecture
status: preparation-record
updated: "2026-10-16"
---

# probes/lg033 — LG-033 契约准备探针记录

本文件记录 LG-033 契约准备包（准备稿，非冻结）的**基点、只读检索命令、证据来源、限制与成本未知项**。
它**不是**产品实现、schema/API、测试或运行依赖；本包**产品真实模型调用 0**，**无新网络实验**。

## 1. 范围与授权

- 本包仅可写：`docs/contracts/LG-033-preparation.md` 与 `probes/lg033/PREPARATION.md`。
- 未改：docs/08、README、PROJECT、agent.md、`CONTRACT_VERSION`、backlog 任务状态、任何产品代码/依赖。
- 未跑：后端/前端测试、构建、产品真实模型调用、新的网络探针。
- 禁止修改其它 worktree（`lg028-contract`、`ui-controls`、`main` 等）——本包未触碰。

## 2. 基点（命令与结果）

| 项 | 值 | 命令/来源 |
|---|---|---|
| 分支 | `dev/lg033-contract` | `git status --short --branch` |
| 本包前基点 | `a34c915`（上一版 50 行准备稿） | `git log --oneline -3` |
| 契约版本 | `1.5.0` | `backend/lightgravity/contracts/constants.py`；docs/08 §13 |
| LG-033 任务 | `status: in-progress`，`assignee: agent:pi-lg033` | `backlog/tasks/LG-033.md`；`tasks digest` |
| LG-033 claim 提交 | `b2bd5eb`（checkpoint 含 claim） | `git log --oneline -- backlog/tasks/LG-033.md` |

`tasks digest .` 输出：`41 tasks: 19 todo, 5 in progress, 17 done.`，并报 **12 条 diagnostics**，
全部位于 `probes/agensh-orchestration-r2/runs/*/subtasks/*.md`（"Invalid YAML or duplicate frontmatter keys"）。
这些是**既有探针归档的 frontmatter 问题**，与本包及 backlog 任务无关；本包**未修改**这些文件，
也不据此判断任务就绪性。任务 frontmatter 的精确状态以其文件为准。

## 3. 只读检索（已执行，无副作用）

- 读取（完整或节选）：`AGENTS.md`、`agent.md`、`PROJECT.md`、`PROGRESS.md`、`BACKLOG.md`、
  `docs/06-roadmap.md`、`docs/08-interface-contract.md`（§3–§13）、`docs/09-source-intake-and-retrieval.md`。
- 读取任务：`backlog/tasks/LG-033.md` 与 LG-034～LG-041 全部。
- 读取契约定点：`backend/lightgravity/contracts/constants.py`、`backend/lightgravity/store/protocol.py`、
  `store/paths.py`、`store/index.py`、`backend/lightgravity/evidence.py`、`backend/lightgravity/api/files.py`（头部语义）。
- 读取证据入口：`probes/source-intake/README.md`（未重新读取 `evidence/` 原始响应，只引用其摘要与 MANIFEST 元数据）。
- 参考实现定位（按 agent.md §9，先定位再决定；本包**未复用代码**）：
  `/home/yhvh/code/olav-tasks/src/docs-kb.ts`（字面量正则检索 + frontmatter 校验 + 路径包含，MIT）、
  `src/project-files.ts`（原子写 + sha256 + 路径校验，MIT）。
  许可：`/home/yhvh/code/olav-tasks/LICENSE` = MIT（Copyright (c) 2026 olav-os contributors）。
- `docs/contracts/LG-028-preparation.md`（lg028-contract worktree，只读对照命名约定，未修改该 worktree）。

无 dump 整个仓库；未 `cat` 大文件全量；未对 `olav-tasks` 运行构建或安装。

## 4. 复述的探针事实（只读，不作运行默认/质量结论）

来源 `probes/source-intake/**`，详情与 sha256 见 [证据入口](../source-intake/README.md)、
[MANIFEST.json](../source-intake/evidence/MANIFEST.json)、[DOC_CHECKS.md](../source-intake/DOC_CHECKS.md)。

- `192.168.8.12:11434` 是 **llama.cpp `llama-server` router `b11641-843e7dcc1`**（**非 Ollama**）；
  地址与模型是可配置测试端点，**不是运行默认或产品依赖**。
- `embeddinggemma-2-Q8_0` 文本嵌入 **768 维**、有限、L2=1.0；第二图 cos 0.888551、第二音 cos 0.978952
  只是**输入消费**证据，**语义/识别质量未验证**；checkpoint 出处未 hash 验证。
- `qwen3.8-27b` OCR 两张**合成**中文图：NFKC 去空白 76/87 字符、**CER 0**（**合成小样本，非生产质量**）。
- 中文音频（espeak-ng **合成**）：`/v1/audio/transcriptions` → 501、chat `input_audio` → 500；
  该 embedding 模型这条路由转写失败，**不代表整台服务无 ASR**；`gemma4-mtp` 等未测。
- 原型运行在**系统 Python 3.14 + 临时脚本**，**不是**产品 Python 3.12 / Antigravity adapter 接入证据。

## 5. 限制

- 准备稿是**接口草案**，字段名/枚举/端点/事件/错误码均为**候选**；未冻结、未实现、未升版。
- 未做产品真实模型调用、未跑测试/构建、未做新的质量实验；不得据此宣称任何能力已实现。
- 中文 ASR、生产级 OCR、Office、多页/混合版式、真实人声、邮箱/抓取均**未验证**。
- 局部链接/一致性检查的范围见 §6；不代表逐任务 QA 或版本验收。
- `tasks digest` 的 12 条 diagnostics 为既有探针归档问题，未在本包处理。

## 6. 局部检查（已执行）

- 文档相对链接：准备稿引用的 `docs/08`、`docs/09`、`docs/06`、`backlog/tasks/LG-0xx.md`、
  `probes/source-intake/**`、`backend/lightgravity/**`、`docs/contracts/LG-028-preparation.md` 均在仓库内存在（本机核对）。
- 一致性：准备稿口径与 docs/09、docs/06 §6、docs/08 §13、LG-033～041 验收条件逐条对应（§11 清单）。
- 未运行 `pytest`/`mypy`/前端构建（本包无代码改动；局部文档检查不建镜像测试，遵 agent.md §8）。

## 7. 成本与未知项

- 本包**产品真实模型调用 = 0**；未启动产品服务、未部署、未推送。
- pi 开发代理 token/费用**未知**（未在开发侧计量）；不做推算。
- 墙钟耗时未精确记录；无新网络请求，无 API 重试。

## 8. Git

- 本包允许仅对上述两份文档做**本地提交**，**不推送**。
- 提交后 LG-033 仍 `in-progress`，等待单一 docs/08 owner 串行冻结。
