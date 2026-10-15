# 收尾/集成说明（agensh-orchestration）

> 本目录由**收尾/集成执行者**从实验 worktree 复制并做文档表达修正。它**不是**独立 QA，**不是**版本验收，
> 也不替代原实验报告。原始实验 worktree 保留未动。

## 来源与边界

- 源 worktree：`/tmp/lightgravity-worktrees/agensh-ablation-20261015`，分支 `experiment/agensh-ablation-20261015`，base `9987d4f`。
- 目标：`/home/yhvh/code/lightgravity-bot/probes/agensh-orchestration/`（复制前不存在）。
- 复制排除：`__pycache__/`、`*.pyc`、`runs_mock/`（离线 mock 全流程产物，可由
  `python3 driver/run_pilot.py --mock --runs-dir runs_mock` 离线重建；其摘要与判定已保存在 `evidence/offline/run_log.txt`）。
- 未新增任何真模型请求；未提交、未合并、未 push、未 deploy；未改产品代码、backlog、根依赖、PROJECT。

## 复制保真

- 复制文件 **242** 个，复制后逐文件 sha256 与源**全部一致**（清单见 `copy_manifest_source.sha256` /
  `copy_manifest_main_predocedit.sha256`，结论见 `copy_verification.txt`）。
- 文档修正后再次核对：除 `REPORT.md` / `README.md` / `PROTOCOL.md` 外，其余 **239/239** 文件仍与源逐字节一致。

## 文档表达修正（仅表达，不改结果/测试/预注册规则）

- `REPORT.md`：
  - 明确 C 只含「两轮同步编辑提案」，缺同轮开工前协商与程序化原子认领往返，**不是完整 Agensh 自组织**；
    整文件冲突规则对不同内容一律拒绝，故 C 失败**不能证明**独立编排模型不可替代；下一轮应比较
    「无编排 + 程序化原子认领 / 同伴协商」。
  - 明确 A 组 3 次截断使「B 优于 A」与截断混淆，**不能直接当作重新规划有害的因果证据**。
  - 删除未受控的因果句「更长上下文诱发了更长的 reasoning」，改为观测 + 显式假设（未受控验证）。
  - 修正复现命令 `python3 driver/offline_checks.sh` → `bash driver/offline_checks.sh`；核实证据索引并如实更正。
- `README.md`：加入解释边界；说明 `runs_mock/` 未复制但可离线重建。
- `PROTOCOL.md`：§11 修订历史的时间 `05:2xZ` 明确为**占位符、精确冻结时刻未记录**，不补写时间；
  保留历史说明（草稿 6/8 → 冻结前 5/9），并静态核对当前协议与验收条目**无偏差**。§2–§10 预注册规则未改。

## 离线复核结果（无网络、无模型调用）

- `evidence/finalize/offline_recheck.py` → `offline_recheck.txt`：**全部 PASS**。
  - 原始 usage 重算：raw 调用 **45**、`total_tokens=106949`、重试 **0**、usage 缺失 0、截断 **6**
    （A 3 / B 0 / C 3）、reasoning 24966 / completion 55199。
  - 分组：A **2/3**（17/21，tokens 48907）、B **3/3**（21/21，tokens 34589）、C **1/3**（6/21，tokens 23453）。
  - 9/9 样本 SoT 一致、summary↔run 文件链接齐全、Markdown 本地链接可解析。
  - `runs/`、`evidence/`、`fixtures/` 敏感信息扫描无命中；raw 请求字段限于 allowlist（无认证头/密钥）。
  - 验收条目静态计数与协议一致：t1=6、t2=6、t3 stage1=5 / stage2=9。
- `evidence/finalize/analysis_recompute.txt`：用原 driver `analyze_results.py` 从 raw 重算，
  与已存 `evidence/pilot/analysis.json` **sha256 完全相同**（`a31b21e3…1dcb`）。
- `evidence/pilot/run_stdout.log` 存在（1954 bytes），已核实其内容与 raw/results 一致；未伪造 stdout。

## 观察到的并发改动（非本执行者）

- 收尾期间主工作区 `PROJECT.md` 出现一处未提交改动（mtime 16:32:19，追加编排消融决策日志）。
  该改动**不是本执行者所为**，本执行者未触碰 `PROJECT.md`。纳入记录以免误归因。

## 剩余限制

- 无独立 QA、无版本验收；本目录只是收尾/集成复核。
- 协议冻结的精确时刻永久缺失；首个正式请求时刻由 `pilot_start_epoch` 推出。
- 样本极小（每格 n=1）、存在输出截断混淆，结论只作下一轮候选，不推广。
- `runs_mock/` 未随目录复制；如需重放离线 mock，请按 README 重建命令运行（无需联网）。
- 未提交/未合并/未 push/未 deploy；`probes/agensh-orchestration/` 在 git 中为未跟踪目录。
