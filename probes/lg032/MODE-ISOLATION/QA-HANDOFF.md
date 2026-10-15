---
title: "LG-032 MODE-ISOLATION → 独立串行方法 QA 交接"
doc_type: handoff
category: engineering
status: "READY-FOR-INDEPENDENT-SERIAL-METHOD-QA; real provider 0; 032 NOT done"
experiment_id: lg032-mode-isolation-20261016
worktree: /home/yhvh/code/lightgravity-bot-worktrees/lg032-mode-isolation
branch: fix/lg032-mode-isolation
base_commit: "379c089"
head_commit: "f08a12f"
updated: "2026-10-16"
owner: "agent:pi-lg032-mode-isolation（返修 owner；不得自宣 formalReady）"
---

# LG-032 MODE-ISOLATION QA 交接

> 本包只改**独立 QA harness**（`probes/lg032/**`），**产品源只读未改**。请**独立于实施者**的 serial 方法 QA 复核下列门。

## 1. 交付物

| 项 | 路径 |
|---|---|
| 协议失败认定 + 返修报告 | `probes/lg032/MODE-ISOLATION/REPORT-MODE-FIX.md` |
| 状态 | `probes/lg032/MODE-ISOLATION/STATUS.md` |
| harness 修复（改） | `probes/lg032/FINAL-COHORT/harness/run_attempt.py` |
| fairness 自测（改，新不变量） | `probes/lg032/FINAL-COHORT/harness/fairness_selftest.py` |
| cohort2 overlay（新） | `probes/lg032/MODE-ISOLATION/mode_config.py` |
| 0-real 串行 bootstrap 探针（新） | `probes/lg032/MODE-ISOLATION/serial_mode_probe.py` |
| 0-real 真 SDK A-after-B 探针（新） | `probes/lg032/MODE-ISOLATION/serial_sdk_fake.py` |
| 证据 | `probes/lg032/MODE-ISOLATION/evidence/**` |

## 2. 待独立复核的验收条件

1. **每 attempt 显式装配**：A=`decentralized_claim_enabled=False`、B=`True`，经产品受控\n   `ConnectionService.update_settings`，且发生在 `build_runtime` **之前**（读 `run_attempt.py` 调用顺序）。\n2. **build 后断言实际 active mode**：`_assert_active_mode` 读真实 dispatcher\n   `_autonomous_claim`/`_autonomous_pool`/`_decentralized_enabled()` + 三开关；不匹配 `SystemExit`。\n   **非 env 字符串断言**。\n3. **不 A 继承 B**：串行 `A→B→A→B` 同 `settings.data_dir` 下每步 congruent；legacy 对照复现原污染。\n4. **phase 结束恢复 off**：`_safe_restore_mode` 写回 `False`，记录 `restored_off`；产品默认 off 不变。\n5. **只改 harness**：`git diff 379c089 HEAD -- backend` 为空；`HEAD:backend/lightgravity` == `55e4de56`。\n6. **0 real provider**：探针只用 loopback fake + dummy credential；证据 `real_provider_generation=0`。\n7. **新 cohort2 root**：`mode_config.PHASE_DATA_DIR` == `lg032-cohort2-data`；本包未创建它。\n8. **无禁用手段**：无宽 root、无 `monkeypatch` stop、无手写 Run 结果、无 `rm`/`rmtree`/`reset`/`clean`。\n9. **旧产物保留**：旧 87 / Run / SDK / raw / ledger 未改字节；未后补跑旧 formal。\n\n## 3. 关键证据\n\n- `evidence/serial-mode-20261015T205829Z.json`（fix 4/4 congruent + legacy A-after-B pool=True）。\n- `evidence/sdk-serial-mode-20261015T205924Z.json`（真 SDK：B=6refs+selection+pool on；\n  A-after-B=3refs, 无 selection, pool off；同 ledger 16→23）。\n- `evidence/single-A-dry-fixed-20261016.json`（单 A 14/14 PASS）。\n- `evidence/fairness-selftest-20261016.txt`（PASS）。\n\n## 4. 本包明确不做\n\n- 不授权新 formal、不发真实请求、不宣 `formalReady`、不 mark 032 done、不 main merge/push/deploy/publish。\n- 不裁定最终 A/B 成本结论（由 PM 依据独立 QA 与未来 cohort2 收口）。\n