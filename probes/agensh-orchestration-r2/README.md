# probes/agensh-orchestration-r2

编排角色对比实验（第二轮），实验分支 `experiment/agensh-r2-20261015`，
worktree `/tmp/lightgravity-worktrees/agensh-r2-20261015`，base commit `9987d4f`。

**这是什么：** 在固定确定性调度、文件 SoT、程序化原子认领/同伴协商、权限、预算与验收之后，
比较 B（仅开头一次独立规划）与 C（无编排模型）是否带来可观测差异。3 类任务 × 2 组 × 3 次独立重复 = 18 run。
**这不是什么：** 不是产品端到端，也不是真实 SDK 工具循环。模型只返回 JSON，
由实验 driver 做认领/租约/校验/整合/验收。详见 [PROTOCOL.md](PROTOCOL.md) 与 [REPORT.md](REPORT.md)。

**冻结：** 协议在任何真实请求前冻结，冻结时刻 `2026-10-15T05:53:15Z`，
受控输入/提示/参数/验收快照 manifest 哈希见 `PROTOCOL.md` 文首与
`evidence/offline/freeze_manifest.sha256`。

## 目录

| 路径 | 说明 |
|---|---|
| `PROTOCOL.md` | 运行前冻结的协议：条件、固定参数、单 run 流程、认领/租约规则、预算、指标、预注册判定 |
| `REPORT.md` | 中文结果报告（先结果后限制） |
| `driver/run_experiment.py` | 主 driver：B/C 调度、claim 原子授予、租约、整合、SoT、验收、恢复 |
| `driver/llm_client.py` | 标准库 DeepSeek SSE 客户端：`thinking.type=disabled`、finish_reason、usage、脱敏 |
| `driver/analyze_results.py` | 从 raw usage 重算分组/按类/按 repeat 指标与判定规则 |
| `driver/validate_fixtures.py` | 离线：初始必败、参考必过 |
| `driver/protocol_selftest.py` | 离线：互斥认领、顺序消息可见、越权/basehash/语法拒绝、状态版本、恢复不重复请求、无 secret env |
| `driver/offline_llm_selftest.py` | 离线：SSE 正常/缺 usage/保活卡死/HTTP500/HTTP400/reasoning/finish_reason/thinking 载荷 |
| `driver/freeze_snapshot.py` | 生成冻结快照（config/prompt/manifest） |
| `driver/offline_checks.sh` | 一键跑全部离线检查（写 `evidence/offline/`） |
| `fixtures/<task>/initial` | 模型可见初始代码 |
| `fixtures/<task>/acceptance.py` | 客观验收（**不进入模型上下文**） |
| `fixtures/<task>/reference*` | 参考正确解（**不进入模型上下文**） |
| `runs/` | 正式运行产物（SoT、subtasks、events、raw、calls、results、summary） |
| `evidence/offline/` | 离线验证输出、fixture 源哈希、冻结快照 |
| `evidence/formal/` | 正式运行的分析 JSON 与一致性/脱敏核对 |
| `evidence/finalize/` | 收尾离线复核与复制核对 |

## 复现

```bash
cd probes/agensh-orchestration-r2
bash driver/offline_checks.sh                              # 离线，无网络
python3 driver/validate_fixtures.py                        # 初始必败 / 参考必过
python3 driver/protocol_selftest.py                        # 认领/消息/租约/恢复
python3 driver/offline_llm_selftest.py                     # 本地 SSE 边界

# 正式运行（需进程环境已注入 DEEPSEEK_API_KEY；不读取 .env，不写密钥）
python3 driver/run_experiment.py                           # 写 runs/；--resume 可续跑且不重复请求
python3 driver/analyze_results.py                          # 从 raw usage 重算
```

driver 只使用 Python 标准库；真实端点 `https://api.deepseek.com/v1/chat/completions`，
模型 `deepseek-v4-flash`，`max_tokens=8192`，`temperature=0.0`，`thinking.type=disabled`。

## 说明

- 正式运行硬界：正常调用 ≤153，基础设施重试 ≤9，HTTP ≤162，`total_tokens` ≤600000，
  墙钟 ≤1500s；连续 3 次基础设施失败停止。
- 若服务不接受 thinking 配置或仍出现 reasoning，保存原错并停止，不偷偷改参数或切模型。
- 费用无价格来源时记 `unknown`。
- 本目录不提交、不合并、不 push、不 deploy。
