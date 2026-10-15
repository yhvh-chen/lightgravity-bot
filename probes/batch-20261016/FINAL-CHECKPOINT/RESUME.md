---
title: "本轮批次最终检查点与续接（RESUME）"
doc_type: report
category: project
status: "final checkpoint — LG-032 evaluation scope done; 035/037 in-progress; 040/041 todo; no push/deploy/publish"
updated: "2026-10-16"
---

# 本轮批次最终检查点与续接

本文件是 2026-10-16 批量推进的**持久续接检查点**。所有结论带本地证据链接；**保留现存实验、worktree
及幸存原件，历史缺口见 §4**（不谎称 100% 原件从无缺口），**未 push / deploy / publish**；无外部消息；
**无 nested agent**。

## 0. 本轮整合入口（唯一 main 最终整合/PM 文档 owner）

- 开工 `main@5df1956` **clean**；两个待合 owner 均已退出且 clean：
  `qa/lg032-close-audit@4d175113`、`prep/lg035-real-truth@9ad8315`。无残留源 owner 进程。
- 收拢（唯一写动作，串行、无重复 cherry-pick）：
  1. `git merge --ff-only prep/lg035-real-truth` → main advanced to **`9ad8315`**（main 为直接祖先 ⇒ ff-safe）。
  2. `git merge --no-ff qa/lg032-close-audit` → 集成合并锚 **`d0c0c4e`**（仅 merge anchor，非最终 main 头；无冲突；merge-base `0814b80`）。
- **产品树未变**：`git diff 5df1956 HEAD -- backend/ frontend/ src/ tests/ docs/ pyproject.toml uv.lock Makefile`
  **为空**（`d0c0c4e` 同此产品树）；`HEAD:backend/lightgravity` = **`55e4de56b7fe333d81a9bbc7a5e45e19977f9e9f`**（=已验证冻结 tree）。
  最终 main 头**以 `git rev-parse HEAD` 为准**，不硬写自引用新 commit 哈希。
  ⇒ 集成只新增 probe/harness/docs/任务元数据，**不重跑产品全套测试**（源机制已由 R1/BOUNDARY-R1/SERIAL-R1 及
  `329 affected tests + mypy` 独立覆盖）。
- **历史保留**：`--no-ff` 合并保留 main 的 LG-031「BOUNDARY-R1」再开记录与 LG-032「依赖恢复」记录
  （4 处/1 处均仍在）；分支旧版 `LG-031.md`/`LG-032.md` 未覆盖 main。旧 store 缺口、TMD 覆盖、预检 dry 删除事故等
  保留在既有 METHOD-AUDIT / PRESERVATION-INCIDENT 报告，不隐去。

## 1. 当前任务状态（CLI 实读，非预设）

backlog 专用根：`node /home/yhvh/code/olav-tasks/dist/cli.js tasks {validate,digest,ready} backlog`

- `validate` → `OK: 41 tasks, no diagnostics.`
- `digest` → `41 tasks: 2 todo, 2 in progress, 37 done`，`complete=true`。
- `ready` → `[]`，`complete=true`，`diagnostics=0`。
  - `ready=[]` 是因为**现有 in-progress 的可执行部分已完成**、其余为 `external blocked`（候选服务不可达）与
    `quality gate`（LG-041 中文 ASR），**不是未认领的 ready 工作**。
- 状态分布：**2 in-progress = LG-035 / LG-037**；**2 todo = LG-040 / LG-041**；**37 done**（含本轮新 done 的 **LG-032**）。
- 保存的实际 JSON：`FINAL-CHECKPOINT/{validate.txt,digest.json,ready.json}`（脱敏）。

## 2. 唯一 future block 清单（真正外部条件）

1. **LG-035 / LG-037 / LG-040（资料与 Embedding 线）——候选资料服务不可达**。
   - 目标 `http://192.168.8.12:11434` **仍不可达**：latest 私有只读复核
     `~/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/MATERIALS-RECHECK2-HEALTH.md`
     （`updated 2026-10-15T21:13:33Z`）：`GET /health` HTTP **000**/curl 7、`GET /v1/models` HTTP **000**/curl 28
     连接超时；**无 TCP 建立（num_connects=0）**；**0 POST**。协议为 **llama.cpp / OpenAI-compatible（非 Ollama）**。
     **本最终包不再探测、不自换 endpoint/model**。
   - **恢复后**：先 `health`/`models`/能力/有限预算 **freeze** → Chinese/table/PDF OCR 质量门 + embedding 质量门 → **LG-040**。
   - **不因 XFUND NC / 普通实现选择要求用户确认**；继续需要的是**原候选服务恢复或授权可达的同协议 endpoint**。
2. **LG-041（中文转写）——真实 ASR 质量门未过**：LG-039 已 done 但为**可用路径负结论**（已授权服务无可用户音频转写路径），
   `blocked_by` quality gate 保留；**ASR 独立质量达标才实施 041，不阻塞图/PDF 版本**。

## 3. 各线当前真实状态

- **LG-032 `done`（仅「评估范围」）**：见 `probes/lg032/CLOSE-AUDIT/CLOSE-REPORT.md`（PASS）。
  有效 cohort3 `4/4` 各唯一次全真实 delivered/first-pass，actual mode `off/on/off/on + restored off`，
  机器 `5/5,5/5,7/7,7/7`，唯一物理 ledger `0→20→40→57→84`（84≤192），异步真实独立 ModelReviewer passed/0 unsubstantiated。
  旧 cohort1 `87`（模式污染 invalid）+ cohort2 `19`（entry STOP）= **106 永久单列**；032 本轮真实已知 **190=106+84**。
  **default off / 回退保留**；**全 cost unknown、收益不支持默认启用**；**非全产品 pass**。
- **LG-035 `in-progress`**：TRUTH-PREP@9ad8315 已备**两份严格配对真实中文样本**（Z1 公共领域书页扫描 + Wikisource 人工
  ProofreadPage level-3；Z2 `方言調查表格` 表格 PDF 18 页纯扫描无 text layer，`sha1 fe557252…` 392,964 B，private
  700/600/ignored；repo 仅 manifest/GT/评分协议）。**真实 OCR/embedding/ASR 0 新调用，quality NOT measured**；
  mixed born-digital+sccan 类仍缺。**GET 13/12 超 1 如实保留**，另授权 1 GET 补 Z2 → **累计 14**，预算事件不抹。
  **不能标 035 done 或解锁 040/041**。
- **LG-037 `in-progress`**：可选多模态向量机制/回退已验证；**真实 vectors quality/召回未达**（端点不可达）。
- **LG-040 `todo`**：依赖 LG-035/036/037/038/022；**未解锁**。
- **LG-041 `todo`**：中文 ASR 39 负结论质量锁，**不假实施**。
- 已 done 且保留：LG-013/016/027、017/018/019、核心 QA/评估 023/024、028、029、030、031、032，以及 **LG-033/034/036/038**（其中 036/038 待 040 版本 QA）。**LG-035/LG-037 仍 `in-progress`，不在 done 之列**。
- **代码契约 `1.11.0`、SDK `google-antigravity==0.1.22`、自主协作默认 off**；SDK 是产品 runtime、pi 是开发执行，
  **无常驻模型编排 agent**；正式 1.5→后续变更控制链接 history 按实际，**不改 docs/08 formal contract 或源码**。

## 4. 归档与私有保全（不改、不删）

- 旧初始 dirty 已保 `b2bd5eb`；原实验分支 `experiment/*`、全部 worktree、旧 `/tmp` 原件**保留未动**。
- 幸存 LG-031 SDK 原件：`~/.cache/lightgravity-bot/checkpoints/2026-10-16-batch/lg031-phase4-survivors/20261016T040115+1100/`
  （700/600，hash/cmp 一致）。
- **不谎称 100% 原件从无缺口**：历史 TMD/覆盖、预检 dry 删除事故、旧 store 缺口的报告均已保留，
  明确索引 **METHOD-AUDIT** 与 **PRESERVATION-INCIDENT**；不能原件重建造真。
- **LG-024 本地 review package**：`probes/lg024/STAGE-B/dist/lightgravity-bot-L0-e0a8cec-20261015T183958Z.tar.gz`
  sha256 `581f1de603ab8adc6533efa9d4b2ed0506433d17328646b00ab7bbb2761f4de0`，**只锚 `e0`/contract `1.10`**，
  不改原包、**不假称当前 1.11 整包**。**发布准备 done ≠ 发布授权**；**own 公开 LICENSE 未选**，是未来发布事项，
  本轮**不普通确认、不擅选许可**。

## 5. 续接命令（唯一 owner 从 main 出发）

```bash
# 0) 确认 main clean 且任务快照
git -C /home/yhvh/code/lightgravity-bot status --porcelain
node /home/yhvh/code/olav-tasks/dist/cli.js tasks digest backlog

# 1) 外部恢复后（资料线）：先只读 health/models，再 freeze 预算，再 OCR/embedding 质量门
curl -sS -m 5 http://192.168.8.12:11434/health
curl -sS -m 5 http://192.168.8.12:11434/v1/models

# 2) 允许 035/037 真实质量评估通过后，按真实依赖推进 LG-040；ASR 独立质量达标才 041。
#    （具体样本/预算由 PM 另行冻结；不复用 023/032 混淆数据）
```

**交接**：本轮已完成授权的本地整合；`main` clean；唯一 block 是外部候选服务恢复/同协议可达 endpoint 与 ASR 质量门。
无其它未认领 ready 工作。
