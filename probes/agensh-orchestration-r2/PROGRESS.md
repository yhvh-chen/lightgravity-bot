# PROGRESS（只读管理检查用）

## 2026-10-15T05:5xZ — 完成

- 阶段：正式运行与离线重算完成，成果已就绪，待有界整合回主工作区。
- 冻结：`frozen_at_utc=2026-10-15T05:53:15Z`，预运行 manifest `a9fba8f0…a9311`（26 文件）。
- 正式运行：首请求 `2026-10-15T05:53:56Z`，最后事件 `2026-10-15T05:57:11Z`（约 195s）。
  18 run 全部执行（B/C 各 9，每类各 3）。
- 预算实测：HTTP 153/162，正常调用 153/153，重试 0/9，`total_tokens=179851`/600000，
  usage 缺失 0，无 fatal，无 abort，无 driver 残留进程。
- 结果：B 8/9 全通过（60/63 条目）；C 9/9（63/63）。t3：B 2/3、C 3/3。
  中位 token B 11114 vs C 9081（+18.3%），中位耗时 B 11.911s vs C 9.865s（+17.2%）。
  两组冲突/越权/无效/解析失败/截断/SoT 问题均为 0。
- 截断/reasoning：`thinking.type=disabled` 生效，153 次 `finish_reason=stop`，0 reasoning，0 length。
- 预注册判定：**独立编排可移除候选 = 是（仅候选，非自动淘汰）**。
  重要限制：B 唯一失败源于“t3 单文件任务 + 规划把同一文件分给两人”与程序一写者规则的交互；n=3 无统计功效。
- 偏差：`driver/analyze_results.py` 在全部模型调用后有纯离线修正（`REPEATS` 类型），冻结判定规则文本不变；
  详见 PROTOCOL §13。
- 阻塞：无。下一步：复制 `probes/agensh-orchestration-r2/` 回主工作区（排除 `runs_mock/`、`__pycache__`）。
