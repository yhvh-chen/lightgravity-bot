# LG-031 PROOF2-CLOSE 独立审计证据

由 `qa/lg031-close-audit` 独立 QA owner 在**只读**产品/旧 probes 上产生；产品真实生成 **0**；
绝对机器路径已替换为 `<WORKTREE>`/`<AUDIT>`；无 secret。

| 文件 | 内容 | 来源 |
|---|---|---|
| `negctl-independent.json` | 独立复跑**原** `negative_controls.py` 的 4 项对照（N1/N2/N3/N4），全拒 | 实际 harness，新输出 |
| `independent-negctl.json` | 本审计**自有** 3 项对照（X1 finished≠succeeded 拒；X2 无 SQLite 拒；X3 requirements 不符 unavailable） | `qa/lg031-proof2-close/independent_negctl.py` |
| `qarepro-close.json` | 在**新拷贝**上独立复跑 close harness 的实质终态（与 committed evidence 一致；`ledger_unchanged=true`、`new_model_generation=0`） | 实际 `close_proof2.py`，新拷贝/新输出 |

## 复现命令（需私有 fixtures，取自 `lg031-proof2-close` worktree；不进 repo）

```bash
VENV=/home/yhvh/code/lightgravity-bot/.venv/bin/python
WT=/home/yhvh/code/lightgravity-bot-worktrees/lg031-proof2-close
SNAP=$WT/probes/lg031/PROOF2-CLOSE/fixtures/formal-src-snapshot
RAW=$WT/probes/lg031/PROOF2-CLOSE/fixtures/raw-evidence-formal-real2.raw.json

# 原负向对照
$VENV $WT/probes/lg031/PROOF2-CLOSE/harness/negative_controls.py \
    --snapshot "$SNAP" --raw "$RAW" --out /tmp/negctl.json

# 本审计自有负向对照
$VENV $WT/qa/lg031-proof2-close/independent_negctl.py \
    --snapshot "$SNAP" --raw "$RAW" --out /tmp/indep.json

# 新拷贝复跑 close（不触碰原件）
cp -r "$SNAP" "$WT/probes/lg031/PROOF2-CLOSE/fixtures/qa-repro-copy"
$VENV $WT/probes/lg031/PROOF2-CLOSE/harness/close_proof2.py \
    --snapshot "$WT/probes/lg031/PROOF2-CLOSE/fixtures/qa-repro-copy" \
    --originals $WT/probes/lg031/REAL-PROOF2 \
    --out /tmp/qarepro.json
```

> 复跑 close 需快照与 `raw-evidence-formal-real2.raw.json` 为**同级**（harness 从 `snapshot.parent` 读取 raw）。
> 复跑仅使用本地已捕获事件/SQLite，不触发任何模型调用。
