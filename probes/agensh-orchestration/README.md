# probes/agensh-orchestration

编排角色消融 pilot（实验分支 `experiment/agensh-ablation-20261015`）。

**这是什么：** 在固定确定性调度、文件 SoT、权限、预算与验收之后，比较三种编排条件
（A 全程编排 / B 仅初始规划 / C 无编排）是否带来可观测增益。
**这不是什么：** 不是产品端到端、也不是真实 SDK 工具循环。模型只返回 JSON 文件编辑，
由实验 driver 做校验/整合/验收。详见 [PROTOCOL.md](PROTOCOL.md) 与 [REPORT.md](REPORT.md)。

**解释边界（收尾修订）：** C 组只是「两轮同步编辑提案、无同轮协商/程序化原子认领、整文件冲突即拒绝」的弱无编排
基线，不是完整 Agensh 自组织；A 组在 6 次截断中占 3 次，因此 B 优于 A 不能直接当作“重新规划有害”的因果证据。
详见 [REPORT.md](REPORT.md) §4–§6。

## 目录

| 路径 | 说明 |
|---|---|
| `PROTOCOL.md` | 运行前冻结的协议：条件、fixture 规范、预算硬界、指标、预注册判定规则 |
| `REPORT.md` | 中文结果报告（先结果后限制） |
| `driver/run_pilot.py` | 主 driver：组调度、有界调用、隔离整合、SoT、验收 |
| `driver/llm_client.py` | 标准库 DeepSeek SSE 客户端：首事件/总超时、usage、脱敏 |
| `driver/analyze_results.py` | 从 `runs/*/raw/*.json` 重算分组指标与判定规则 |
| `driver/validate_fixtures.py` | 离线：初始必失败、参考解必通过 |
| `driver/offline_llm_selftest.py` | 离线：SSE 正常/缺 usage/保活卡死/HTTP500/JSON 提取 |
| `driver/offline_checks.sh` | 一键跑全部离线检查（写 `evidence/offline/`） |
| `fixtures/<task>/initial` | 模型可见初始代码 |
| `fixtures/<task>/acceptance.py` | 客观验收（**不进入模型上下文**） |
| `fixtures/<task>/reference*` | 参考正确解（**不进入模型上下文**） |
| `runs/` | 正式 pilot 产物（SoT、events、raw、results、summary） |
| `evidence/offline/` | 离线验证输出与 fixture 初始 hash |
| `evidence/pilot/` | 正式 pilot 的 stdout 与分析 JSON |
| `evidence/finalize/` | 收尾/集成离线复核（复制 hash 比对、原始 usage 重算、SoT/链接/敏感信息扫描）；非原实验产物 |

> **未随本目录复制的内容（集成取舍）：** `runs_mock/`（离线 mock 全流程产物，约 768K）未复制；它可由
> `python3 driver/run_pilot.py --mock --runs-dir runs_mock` 离线重建，且 `evidence/offline/run_log.txt` 已保存其
> 运行摘要与 mock 预算/判定，足以证明离线流程曾通过。`__pycache__/` 与 `*.pyc` 亦未复制。

## 复现

```bash
cd probes/agensh-orchestration
python3 driver/validate_fixtures.py        # 初始必败 / 参考必过
python3 driver/offline_llm_selftest.py     # 本地 SSE 边界（无网络）
python3 driver/run_pilot.py --mock --runs-dir runs_mock   # 全流程离线（无网络）

# 正式 pilot（需要进程环境已注入 DEEPSEEK_API_KEY；不读取 .env，不写密钥）
python3 driver/run_pilot.py                # 写 runs/
python3 driver/analyze_results.py          # 从 raw usage 重算指标
```

driver 只使用 Python 标准库；真实调用端点 `https://api.deepseek.com/v1/chat/completions`，
模型 `deepseek-v4-flash`。默认 `--resume` 可跳过已完成样本。

## 实验硬界（正式 pilot 实测）

- 正常调用 45/45，HTTP 45/48，重试 0/3，`total_tokens=106949`（<200000），墙钟约 180s（<900s）。
- 每组 worker 调用机会相同（各 12 次）；A/B 的编排调用计入总成本。
- 费用 `unknown`（无可核验价格来源，不猜费率）。
