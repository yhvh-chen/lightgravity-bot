---
title: "LG-031 AUDIT-CLOSE — PM 本地整合记录（审计 PASS-with-addenda 收口，非全产品 pass）"
doc_type: report
category: engineering
owner: "PM 本地整合 owner（唯一 PM；pi 现有 DeepSeek；无嵌套代理；不 push/deploy/publish）"
branch: "main"
base_candidate: "qa/lg031-close-audit@741bebb（含 fix/lg031-proof2-close@54e7695 与 dev/lg031-real-proof2@e167724）"
main_anchor_before: "91550a9（root PM 两份 dirty：PROGRESS.md + probes/batch-20261016/RUNTIME-CANDIDATE-INTEGRATION.md）"
main_anchor_commit: "7b88bb1（精确保全并提交上述两份已存在 PM 改动）"
merge_commit: "9835a28（--no-ff 合并 qa/lg031-close-audit）"
contract: "1.11.0"
sdk: "google-antigravity==0.1.22"
product_real_generation: 0
updated: "2026-10-16"
---

# LG-031 AUDIT-CLOSE — PM 本地整合记录

## 0. 一句话结论

独立审计 `qa/lg031-close-audit@741bebb`（对 `fix/lg031-proof2-close@54e7695`，含 `dev/lg031-real-proof2@e167724`）
判 **PASS-with-addenda**（**非** clean / **非** full-product-pass）。据此在 **不重开、不改历史字节** 前提下
**mark LG-031 `done`**，并**正式准备 LG-032（阶段 B 成本对照）依赖**。本包**产品真实生成 0**、未重新技术调查、
未跑全套测试、未执行 032 采样；纯 docs/evidence 本地整合。

## 1. 执行序列（精确、可核）

1. **开工核 Git/worktree/HEAD clean**：`main@91550a9`，`git status --porcelain` 仅两项预期 root-PM dirty：
   `PROGRESS.md`、`probes/batch-20261016/RUNTIME-CANDIDATE-INTEGRATION.md`（均为直接 CLI digest 校正，+12 行）。
   `qa/lg031-close-audit@741bebb`、`fix/lg031-proof2-close@54e7695`、`dev/lg031-real-proof2@e167724` 均在；
   审计与作者已退出（03x 源/close/audit owner 无并发写）。
2. **main 先留锚**：`git add` 上述两份 dirty（**逐字节保全，不丢弃/重写/reset**）→ 提交 **`7b88bb1`**，
   tree clean。此提交只含已存在的 root PM 改动，无产品/代码变更。
3. **核 ancestor / 安全 merge**：`merge-base main qa/lg031-close-audit = b819dd3`（**已在 main 历史内**）；
   audit 分支相对 `b819dd3` 仅追加 REAL-PROOF2/PROOF2-CLOSE 证据与审计文件，**未动** `PROGRESS.md`/
   `RUNTIME-CANDIDATE-INTEGRATION.md`（merge 无冲突）。**不重复 pick**：`741bebb`/`54e7695`/`e167724` 等
   经 merge 一次带入。
4. **safe merge**：`git merge --no-ff qa/lg031-close-audit` → **`9835a28`**；无冲突、无覆盖。产品树
   （`backend/ frontend/ docs/ tests/ contracts/ backlog/` 等）相对 `7b88bb1` **零字节变化**（merge 只加 probe/QA 文件）。
   合并后 `qa/lg031-proof2-close/*` 与 `probes/lg031/{PROOF2-CLOSE,REAL-PROOF2}/*` 关键文件 hash 与源分支**逐一相同**。
5. **归档**：`qa/lg031-close-audit`、`fix/lg031-proof2-close`、`dev/lg031-real-proof2`、`dev/lg031-real-proof`、
   `fix/lg031-{r1,r2,r3,pool}` 及全部旧 proof/失败/raw/worktree **保留不动**。

## 2. 判定与依据（如实，不加修饰）

| 项 | 值 |
|---|---|
| 审计判定 | **PASS-with-addenda**（非 clean、非 full-product-pass） |
| 031 `done` 依据 | 真双 worker / 隔离 / hash handoff + **真实独立 review**（`model`/`validated_outcome=passed`）+ **0 模型产品 service 收口**（`verify_and_prepare`→`_open_acceptance`→绑定 `decide(accept)`）+ **独立 audit** |
| 收口性质 | 对**同一持久候选**（Run `run_01M50GARZGSWF8KVJM2PVRZWWC`/Task `task_01M50GARZ7FDBC1YR46TCFMM18`）以既有产品服务在 **0 模型生成**下走合法状态迁移至 `completed` |
| 证据伪造 / 非授权门绕过 / live fallback / fabricate completion | **均无**（审计独立复算 + 独立负向对照全拒；`ledger_unchanged=true`、`new_model_generation=0`） |

### 2.1 补遗（历史 report 绝不改字节；此处仅记录，供 031 record / 032 引用）

- **A1（中）**：原真实 review DTO `unsubstantiated=["F1"]`，close 落 `[]`——产品 `validate_findings` 对 `findings=[]`
  **重算** 为空。故 **并非所有 DTO 字段原样透传**；REPORT §2「复用 DTO … 全部一致」不准确。`outcome=passed`/accept
  绑定不受影响。**属记录失真**，本补遗如实记，不改原 close REPORT。
- **A2（中）**：旧 REPORT/STATUS 的 4 个「收口后工作副本」hash 锚（`TASK.md 2eda2bef…`/`RUN.md 558a66c1…`/
  task events `df1af19b…`/run events `1d110973…`）**全盘不存在、不可复现**（fixture 在 evidence 落盘后被再次写入）。
  **以 committed evidence 锚及审计独立副本哈希为准**（`evidence/close-proof2.json` sha256 `8859e0a8…`，
  审计在新拷贝独立复跑得相同实质终态）。prose 锚不作权威。
- **A3（低，已充分披露且 audit 接受）**：reviewer 停止事实为 **harness 派生**（process-exit + turn 正常返回，
  `basis=harness-derived:…`），非产品记录的 teardown——**authority 最弱环**，已披露；**不代表自动恢复**能力。
  严格口径下 reviewer 停止可记「unknown held」，此裁量点**交 032**。
- **A4（低，文档 errata）**：`cap48/used28/剩余20` 属 REAL-PROOF2；旧「剩余 6」属 **phase4**（cap16/用10），
  两者**不同预算**，易误读，**补遗澄清，不改旧原报告**。

### 2.2 未宣 / 归 032（不得借此绕过 032）

- **原 Task `checks` 空** ⇒ `checks.authorized=[]` ⇒ **不称「机器检查执行通过」**；真实文件外部 truth
  （alpha/beta hash + no-cross）已验证且 hash 匹配，但那是**独立只读复算**，非产品自动机器门。
- **新鲜正常产品入口 + 授权机器检查 / 异步 review / 真实 stopgate / 绑定 accept / 正式成本样本** 仍归 **LG-032**。

## 3. 状态与边界

- **LG-031：`done`**（保留全部历史重开/失败/成本记录；task record 引用本补遗与 `qa/lg031-close-audit`）。
- **LG-032：`in-progress`**，反锁依赖现已**正式可满足**（031 done）；**尚未正式采样**。
- 产品 code/contract **不变**：契约 **1.11.0**、SDK **0.1.22**、default 自主池 **off**；既有 token/连接 pin/
  授权/evidence/stop/replay 边界不变。
- **成本**：旧真实工程 **86**（34+24+28）；**本包产品 0**；**032 未正式采样**，预算固定 **4×48 / 总 192**，
  **本包不执行**。**不把计划当结果**；provider token/费用 unknown 不当 0。
- 未 push/deploy/publish/upload；无外部消息；未动 `qa/lg032-final-cohort`（并行 032 owner 的独立 worktree）。

## 4. main 候选 / 分支 / 证据 / 下一步

- **main 候选**：`9835a28`（= `7b88bb1` + `qa/lg031-close-audit` 安全 merge）。
- **分支锚**：`qa/lg031-close-audit@741bebb`、`fix/lg031-proof2-close@54e7695`、`dev/lg031-real-proof2@e167724`、
  `dev/lg031-real-proof@b819dd3`（均保留）。
- **证据**：`probes/lg031/REAL-PROOF2/**`、`probes/lg031/PROOF2-CLOSE/**`、`qa/lg031-proof2-close/**`。
- **下一步（032）**：独立 owner 冻结固定样本/次数/费用上限与成功门，先离线验证 harness（同一 actual
  `settings.data_dir` 物理 ledger 全 stage 共用、跨重启不归零、损坏不当 0、转发前预留、usage unknown 记 unknown），
  再以 **4×48 / 总 192** 上限执行；未完成样本不计已交付成本；只有质量不退化且结果支持收益才建议默认启用。

## 5. 任务 CLI 实际输出（仅 backlog 根；2026-10-15T20:01Z 复核）

```
validate /home/yhvh/code/lightgravity-bot/backlog --json
  {"ok":true,"tasks":41,"truncated":false,"diagnostics":[]}

digest /home/yhvh/code/lightgravity-bot/backlog --json
  {"complete":true,"diagnostics":[],"counts":{"todo":2,"in-progress":3,"done":36},
   "in_progress":[LG-032,LG-035,LG-037],"ready":[],"critical_path":{"length":2,"ids":["LG-035","LG-040"]}}

ready /home/yhvh/code/lightgravity-bot/backlog --json
  {"tasks":[],"complete":true,"diagnostics":[]}
```

**与预期一致（以实际输出为准）**：**36 done / 3 in-progress（032/035/037）/ 2 todo（040/041）**，
validate 0 diagnostics，digest complete=true，ready=[]。若与预期不同则查 frontmatter（本次一致）。
