---
title: "agensh SDK 编排实验 — 复现与证据索引"
doc_type: readme
experiment_id: agensh-sdk-20261015
---

# README

在**真实 Antigravity SDK**（`google-antigravity==0.1.22`）内，用产品
`AntigravityExecutor` + `LocalAuthProxy` + `LocalOpenAIAgentConfig` 驱动真实 agent loop
与文件工具，对比 **B（仅 1 次初始规划）** 与 **C（无独立编排模型）**；claim/消息/文件 SoT/
验收由程序强制，两组共有。

## 结果

见 `REPORT.md`（结果先行）。一句话：6/6 run 通过，但**候选门未满足**，且 **B 臂无效**
（planner 输出全部程序判无效，worker 未收到计划），因此**不**主张取消独立编排。

## 复用 vs 实验自建

| 组件 | 来源 |
|---|---|
| SDK 真实执行 / 代理 / 配置 / 编译 | **产品代码**：`backend/lightgravity/adapter/{executor,proxy,sdk_config,compiler,registry,credentials}.py`（冻结哈希见 `evidence/FREEZE_MANIFEST.txt`） |
| 真实 SDK/harness | `google-antigravity==0.1.22`，`localharness` sha256 `65a96a2a…5ecd3` |
| fixture + 验收 | 复用 r2（复制并记录哈希：`evidence/copied_fixtures.sha256`） |
| 计量中继 / 路径钩子 / 租约 SoT / 整合 / 校准 / 分析 | **本实验目录**（`driver/`） |

## 目录

- `INVESTIGATION.md` / `ENVIRONMENT.md`：上一回合技术调查与环境（保留）。
- `CALIBRATION.md`：校准（独立预算、偏差、样本数选择依据）。
- `PROTOCOL.md`：正式前冻结协议（输入/提示/参数/预算/判定/中继规则）。
- `REPORT.md`：正式结果、候选门判定、失败与边界。
- `PROGRESS.md`：真实时间进度。
- `driver/`：`host.py`（产品 adapter + schema + 钩子）、`relay.py`（中继）、
  `experiment.py`（B/C 编排）、`calibrate.py`、`analyze.py`、`recover_planner.py`、
  `audit_r2_yaml.py`、`sotyaml.py`、`hooks.py`、`selftest_offline.py`。
- `fixtures/`：复用的 3 类 fixture + acceptance + reference。
- `runs/calibration*/`、`runs/formal/`：原始证据（turn JSON、relay 记录、staging diff、
  events.jsonl、SoT、session DB、analysis.json）。
- `evidence/`：冻结清单、r2 YAML 审计、planner 恢复、fixture/formal YAML 审计、日志。

## 复现

```bash
PY=/home/yhvh/code/lightgravity-bot/.venv/bin/python
cd <此目录>
$PY driver/selftest_offline.py          # 0 真实模型：安全 YAML / 中继 / 钩子 / canned SDK
$PY driver/audit_r2_yaml.py /path/to/probes/agensh-orchestration-r2 --out evidence/r2_yaml_audit.json
# 真实（需 DEEPSEEK_API_KEY 在进程环境；会被读入内存后立即移除）
$PY driver/calibrate.py --runs-dir runs/calibration
$PY driver/experiment.py --mode formal --single --runs-dir runs/formal
$PY driver/recover_planner.py
$PY driver/analyze.py
```

## 诚实边界

实验 host + 产品 adapter + 官方 SDK/harness；**非** UI、**非**完整产品运行时端到端、
**非**沙箱逃逸保证。仅 openai-compat/DeepSeek。未覆盖大工程/模糊需求/长会话/跨 turn resume。
