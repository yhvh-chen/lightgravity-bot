---
run_id: t3_evolving__C__r1
task: t3_evolving
group: C
fixture_initial_hash: 4af564b8e01944032d559891c7bc77953375d08338809eb9ab2b35762235f046
experiment_schema: agensh-orchestration-r2/v0 (experiment-only)
control_writer: driver
---

# TASK

## 用户目标（本轮）
实现 src/stats.py（不要修改其他文件）：
- mean(nums): 空列表抛 ValueError，否则返回算术平均。
- median(nums): 空列表抛 ValueError；奇数长度返回排序后的中间值；偶数长度返回中间两个数的平均。

用户在本轮开始前新增的明确要求（所有组同样适用）：
- 新增 mode(nums): 返回出现次数最多的值；若平局返回最小的那个值；空列表抛 ValueError。
- 新增 stdev(nums): 返回总体标准差（即 sqrt(方差)，方差按除以 n 计算）；空列表抛 ValueError。
- 必须保持 mean/median 对空列表抛 ValueError 的既有行为。
