---
title: "agensh SDK 纠正版编排对比实验 — README"
doc_type: readme
experiment_id: agensh-sdk-corrected-20261015
---

# agensh SDK 纠正版编排对比实验

## 这是什么

对首轮 `probes/agensh-orchestration-sdk` 的**测量返修与有界重跑**。单变量：
**B 组在 run 开始时运行 1 次独立 planner SDK turn；C 组没有**；其余（真实 SDK agent loop、
工具权限、程序化 claim、同轮消息、独立 staging、程序整合、验收、两轮）两组完全相同。
本实验不是独立版本 QA，也不是 UI 完整产品端到端。

## 结果

- 有效性前置全部成立（3/3 B 计划有效且真实注入；无损 structured 输出；每 turn 停止正向；
  0 `length` 截断；单一真实输出上限；YAML 合法）。
- 权限门成立：15 次写入/越界尝试在**执行前**被钩子拒绝，0 实际越界。
- 收益未达门：C 相对 B 中位 tokens 改善 8.84%、中位耗时改善 3.16%（均 <15%）。
- 结论：**无编排可运行，收益未达门，不支持仅凭成本删除独立编排**。详见 `REPORT.md`。

## 目录

```
driver/                 实验 driver（仅本目录）
  hooks.py              真实 wire 键 + 租约 + fail-closed 路径钩子
  host.py               产品 AntigravityExecutor 包装；无损 finish；正向停止证据
  relay.py              计量中继；单一输出上限统一
  sessiondb.py          原生 session DB 无损提取（离线）
  experiment.py         正式 B/C driver
  calibrate.py          有界校准（2 turn / 12 HTTP / 60k / 180s）
  sotyaml.py            安全 YAML + 重复键拒绝
  selftest_offline.py   0 模型离线自测（canary/session DB/schema/预算/停止）
  audit_offline.py      首轮 planner 离线回放 + 新 schema 拒绝证明
  calibration_recheck.py 校准 acceptance 离线复核
  analyze_corrected.py  逐 run/类指标重算
  freeze_manifest.py    冻结清单生成
fixtures/               三类任务 initial/reference/acceptance
runs/                   原始结果（formal 6 run + calibration）
evidence/               审计、离线返修、校准、分析、冻结清单、哈希
PROTOCOL.md             正式前冻结协议（epoch 1792048031）
CALIBRATION.md          校准记录
REPORT.md               结果报告
PROGRESS.md             真实 UTC 时间线
```

## 复现

```bash
PY=/home/yhvh/code/lightgravity-bot/.venv/bin/python   # google-antigravity==0.1.22, 不装依赖
cd probes/agensh-orchestration-sdk-corrected
$PY driver/selftest_offline.py          # 0 模型，离线自测
$PY driver/audit_offline.py             # 0 模型，首轮 session DB 回放（源目录只读）
# 真实运行（需环境内 DeepSeek 凭证；驱动会读入内存并从 env 清除）：
$PY driver/calibrate.py                 # ≤2 turn / 12 HTTP / 60k / 180s
$PY driver/calibration_recheck.py       # 离线复核，0 模型
$PY driver/experiment.py --mode formal --single   # 6 run，≤220 HTTP / 1.3M / 900s
$PY driver/analyze_corrected.py         # 离线重算指标
```

## 安全与合规

- 源目录 `/home/yhvh/code/lightgravity-bot/probes/agensh-orchestration-sdk/` 及其 worktree
  只读，未修改；首轮结果未覆盖。
- 未修改产品源码；`PROJECT.md` 与既有 r2 改动未触碰。
- 未 commit / merge / push / deploy。
- 凭证只从环境读入内存并清除；不读 `.env`、不打印真实密钥。
- 所有文件写入隔离在每 worker staging；程序只整合授权租约 diff。
