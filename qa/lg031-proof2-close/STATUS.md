---
title: "LG-031 PROOF2-CLOSE 独立审计 STATUS（qa/lg031-close-audit）"
doc_type: status
category: engineering
owner: "LG031 close-audit 独立 QA owner（非 031 源作者/真实 proof/close 作者）"
branch: "qa/lg031-close-audit"
audit_target: "fix/lg031-proof2-close@54e7695"
updated: "2026-10-16"
product_real_generation: 0
verdict: PASS-WITH-ADDENDA
---

# LG-031 PROOF2-CLOSE 独立审计 STATUS

## 判定

| 项 | 判定 |
|---|---|
| 54e7695 是否合法消费同一真实候选完成/真实 review/停止事实并经产品服务收口 | **是（PASS）** |
| 是否有证据伪造 | **无** |
| 是否有非授权门绕过 | **无** |
| 是否有 live ModelReviewer fallback | **无** |
| 是否 fabricate completion | **无** |
| 门 7「绑定 accept」是否在合法产品服务路径达成 | **是**（本审计独立复跑复现） |
| 可用性 | **PASS，附 A1/A2/A3 补遗** |

**结论：PASS-WITH-ADDENDA。** LG-031 可在**仅补遗、不改历史/不重开**的前提下由本 QA owner
mark `done` 待 **LG-032 完整版本 QA**；053 实质结论「受监督缓存真实结果收口、非自动 restart/checkpointskip、
原 Task checks 空但外部 truth 有效、所有未测」成立。

## 补遗项（须在 031/PM 整合文档与（如适用）close 报告澄清）

- **A1（中）**：原真实 review DTO `unsubstantiated=["F1"]`，close 落 `[]`（产品 `validate_findings` 重算语义）；
  REPORT §2「复用 DTO 全部一致」**不准确**。outcome/accept 不受影响。**属记录失真，须补遗。**
- **A2（中）**：REPORT/STATUS 的收口后工作副本 4 hash（`TASK.md 2eda2bef…`/`RUN.md 558a66c1…`/task events `df1af19b…`/
  run events `1d110973…`）**全盘不存在、不可复现**；fixture 在 evidence 落盘后被再次写入。**以 committed
  `evidence/close-proof2.json` 为准**，prose 锚须更正或标注作废。不影响 committed evidence 与实质终态。
- **A3（低，已充分披露）**：reviewer 停止事实为 harness 派生（process-exit + turn 正常返回），非产品记录 teardown；
  写入形状复刻 `_record_reviewer_stop` 且如实标 `basis=harness-derived:…`；负向对照 N3 拒存活进程。**接受，标为 authority 最弱环。**
- **A4（低，文档 errata）**：「旧 phase 剩 6」指 phase4（cap16 用10），非 REAL-PROOF2（cap48 用28 余20）；
  易误读为 oldremaining6。**补遗澄清即可，不改旧原报告。**

## 本审计独立验证（真实命令/输出）

- 独立复跑负向对照（实际 harness，新输出）：
  `python probes/lg031/PROOF2-CLOSE/harness/negative_controls.py --snapshot <snapshot> --raw <raw> --out qa/.../negctl-independent.json`
  → `ALL_NEGATIVE_CONTROLS_REFUSED: True`（N1 未知 run、N2 未知 session、N3 存活进程、N4 binding 不符 全拒）。
- 本审计自有负向对照（`independent_negctl.py`，实际 harness 模块，无 live fallback）：
  X1 `execution_finished` 非 succeeded → 拒（5/6）；X2 无 SQLite → 拒（0/6）；X3 requirements_revision 不符 → `unavailable`。
  → `INDEPENDENT_CONTROLS_ALL_REFUSED: True`。
- 新拷贝独立复跑 close：实质终态 `run: executing→verifying→awaiting_acceptance→completed`、
  `task: →awaiting_acceptance→completed`、`step_d confirmed=true`、`step_e confirmed/completed`、
  **`ledger_unchanged=true`、`new_model_generation=0`**（与 committed evidence 一致）。
- 原件：REAL-PROOF2 7 项 sha256 逐一对齐冻结值（`PLAN 37c339da…` 等），账本 28 条/hash `e9a1ef78…` 不变，
  `lg031-real-proof2` worktree clean。
- close commit 仅动 `probes/lg031/PROOF2-CLOSE/**`，**无产品/文档/测试改动**。

## 边界 / 不宣

- 产品真实生成 **0**；未重跑真实 SDK/POST；未新调模型。
- **不宣**全产品 pass；**不宣**产品自动机器门执行通过（原 Task `authorized=[]`）；**不宣**自动 restart/checkpointskip。
- 产品自动机器门 + 版本级 + 032 阶段 B 成本对照**仍待 032 同门**，本审计不预判。
- 本包不合 main；无 push/deploy/publish/upload；未动 8123/其他进程；未动 main@91550a9 PM dirty。

## 文件

- `qa/lg031-proof2-close/REPORT.md`
- `qa/lg031-proof2-close/STATUS.md`
- `qa/lg031-proof2-close/independent_negctl.py`
- `qa/lg031-proof2-close/evidence/{negctl-independent,independent-negctl,qarepro-close}.json`
