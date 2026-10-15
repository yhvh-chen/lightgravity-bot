---
control_writer: driver
experiment_schema: agensh-orchestration-sdk/v1 (experiment-only)
fixture_initial_hash: 9a704d7cd0f772c96c93e318233fed90171d33c342c84082c1d20fe4a86faacf
group: C
run_id: t1_independent__C__r0
task: t1_independent
---

# TASK

## 用户目标（本轮）
实现 src/slugs.py 和 src/ranges.py 中的函数（不要修改其他文件）：
- slugify(title): 把 title 转小写；把每一段连续的非字母数字字符（a-z、0-9 之外）替换成单个 "-"；去掉结果首尾的 "-"。
- clamp(value, lo, hi): value < lo 时返回 lo；value > hi 时返回 hi；否则返回 value。
- in_range(value, lo, hi): 当 lo <= value <= hi 时返回 True，否则返回 False。
