# LG-022 独立复验 R2 — 补查收尾 SUPPLEMENT

> 本文件是 **`REPORT.md` 的准确 scope 修正与补遗**，不覆盖、不改写原报告与历史账本。
> Owner：本轮补查收尾独立 QA（`qa/lg022-r2` worktree，branch `qa/lg022-r2`）。
> 产品代码**只读**，未做任何产品修复；无嵌套派工/发布；`qa/lg022-r2/**` 以外未改。
> 本包**真实产品/模型调用 0**，未重跑 DeepSeek 主链，未再运行 SDK cancel 新试验。

## S0. 本包边界与状态快照（先保存）

- **本包起点**：worktree HEAD `a41f399`（前包 R2 报告提交）；本包唯一未跟踪文件为前包留下的
  `qa/lg022-r2/harness/review_cancel_sdk_proof.py`（22378 B，mtime 2026-10-16 03:35:41）。
- **前包（`bounded-uuv5ekyo`）实测**：wall 限 600s，**wall143** 被外部终止；其 dispatch log
  `/home/yhvh/.cache/lightgravity-bot/dispatch-logs/lightgravity-pi-bounded-uuv5ekyo.log` 保留。
  前包已 **真实执行**：
  - 写出并运行 `harness/review_cancel_sdk_proof.py`，产出 `/tmp/lg022-cancel-sdk.json`（保留原位）；
  - 为调试该脚本，写了多个 `/tmp/exp_cancel*.py` 临时探针（非产品、非本包交付）。
- **副作用范围（unknown → 已尽力核实）**：
  - 前包**未**向 DeepSeek 发起真实生成请求（`/tmp/lg022-cancel-sdk.json` 自记 `real_model_calls: 0`，
    上游为 loopback 伪上游；`/tmp/lg022-r2-real/data/generation/generation.jsonl` 只有主链 7 条、
    mtime 03:25，早于前包 03:35–03:43 活动，**未被前包追加**）。
  - 前包临时进程（`exp_cancel*.py`）已不在进程表；本包复核无本包签名的残留监听端口/子进程。
  - 前包对产品 data/workspace 的写入：**unknown / 未证实**（其调试走纯本地伪上游 + 临时探针）；
    本包**不自动重放**其任何未知动作。
- **本包已执行**：仅只读核查（git/进程/证据文件）+ 写 `SUPPLEMENT.md`/`STATUS.md`；
  **无任何真实 DeepSeek 生成请求**。

## S1. 真实 SDK cancel/stop 补证：**仍未证实（unconfirmed）**

- 前包 `review_cancel_sdk_proof.py` 的实际输出 `/tmp/lg022-cancel-sdk.json`（**保留，未改**）：
  - `provider: provider-substitute`（真 `google-antigravity==0.1.22` `Agent` + 真 `LocalAuthProxy`，
    模型侧为 loopback 伪 OpenAI-compatible 上游，**非 DeepSeek**）；`real_model_calls: 0`。
  - `cancel_real_sdk.pre`：`stream_opened=true`、`reviewing=true`、`session_refs` 非空（2 条真实形态 ref）。
  - `control`：`state=unconfirmed`、`confirmed=false`、`phase=cancelling`、
    `reason="reviewer did not stop within 5.0s; unknown side effects, slot retained"`。
  - `review_result: {timeout: true}`；`real_sdk_teardown_fact: {}`（**空**）；
    `upstream_saw_client_gone: false`；`confirmed_after_real_sdk_stop: false`。
  - `verdict.C1_cancel_confirmed_after_real_sdk_stop = false`；`C3_pause...= false`；
    `all_pass = false`。
  - 唯一成立项：`C2_unconfirmed_keeps_run_and_refs = true`（未确认时 run/phase/`session_refs` 保留、
    槽不释放）——这与既有 `evidence/stopgate-proof.json` 的 held 机制一致，属**产品机制**证据。

### S1.1 挂起落在哪一层（按已有证据，不夸大）

| 层 | 是否有证据 | 说明 |
|---|---|---|
| **QA harness（本补证脚本）** | **是** | 该脚本**从未跑成**：真 SDK reviewer 在伪上游流式下**5s 内未停止**，`real_sdk_teardown_fact` 为空、`upstream_saw_client_gone=false`。这是**脚本尚未取得真实停证据**，非产品结论。 |
| **真实 SDK 行为** | **unknown（未证实）** | 现有证据**不能**判定 SDK `Agent.chat` 取消后是否/何时真正 teardown；`session_refs` 仅是注入的 real-shape 字符串，`upstream_saw_client_gone=false` 说明伪上游未观察到连接断开。真 SDK cancel 语义 **未证实**。 |
| **产品生命周期** | **未受本补证影响** | 产品 `ControlService.stop` 在 reviewer 未确认停时**正确**返回 `unconfirmed` 并**保留槽/refs**（C2 通过，与 `stopgate-proof.json` R2B/R2C 一致）。**未见产品 fail**。 |

**结论**：该挂起**属于 QA harness 未跑成 + 真实 SDK 行为未知**，**不能**冒充「产品 fail」，
也**不能**冒充「SDK cancel 成功」。真实 DeepSeek 路径下 reviewer 活跃时 cancel/pause 的
「停止确认前不终止/不释放、SDK/proxy 退出后才确认」——**仍未证实**。

### S1.2 前包为何 wall143（定位，不重放）

前包 dispatch log 末尾显示其在反复调试「`agent.chat()` 取消后 Task 是否结束」，
多次以 `timeout 100 .venv/bin/python /tmp/exp_cancel*.py` 运行，每次**占满 100s**、
输出仅 `resolved` / 未停止。**这是 QA 调试循环挂死**，而非产品行为；本包**不再重放**。

## S2. 主链 7 + light 1 是否共用同一 phase 账本：**否 → 未统一**

按**原始两份证据 + 实际落盘账本**核实（未改任何历史账本/证据）：

| 链路 | data_dir（账本路径） | limit | count | 证据（原始） |
|---|---|---|---|---|
| 真主链（worker+reviewer→awaiting→accept） | `/tmp/lg022-r2-real/data/generation/` | **10** | **7** | `evidence/real-chain.json` `final_generation={count:7,limit:10}`；`generation.jsonl` 7 条、`generation.count.json={"count":7}` |
| 真 light Q&A | `/tmp/lg022-r2-lightqa/data/generation/` | **3** | **1** | `evidence/light-qa.json` `generation={count:1,limit:3}`；其 `generation.jsonl` 1 条 |

- **两条链路使用不同 data_dir → 不同的持久账本文件，且 `limit` 不同（10 vs 3）**。
  证据：`harness/real_chain_r2.py` 默认 `LG022_GEN_LIMIT=10`；`harness/light_qa_probe.py` 默认
  `LG022_GEN_LIMIT=3`，而 `REPORT.md` §9 记录的运行命令 `light_qa_probe.py` **未带** `LG022_GEN_LIMIT=10`。
- 因此报告中的 **“8/10” 是把两个独立 phase（7/10 与 1/3）事后相加的数字**，
  **不是**同一次统一硬总额执行。**历史全 stage 统一硬总额（如 10）并未执行**。
- **可准确核实的已知真实量**：主链 **7**（上限 10，独立）+ light **1**（上限 3，独立）= **已知实际 8**；
  但该 8 **不受任何统一硬限约束**。旧 QA 首轮仍 **unknown**，R1 **6/10 单列**，均未洗数。

### S2.1 这是 QA 流程缺口，**不是**产品 persistent ledger 缺陷

- 产品持久账本的语义（转发前原子预留/跨进程重启不归零/并发不超/损坏 fail-closed）已由
  `evidence/ledger-proof.json`、`evidence/service-ledger-*.json` 独立证明**通过**，
  与上述「两次运行各建各的 data_dir」无关。**不得**把此 QA 流程缺口写成产品账本 bug。
- 未重写旧账本、未补造 reserve、未宣称历史受统一硬限。

### S2.2 后续 024/023（及同类 QA 脚本）统一 phase ledger 的配置要求

1. **单次 run 只允许一个 `data_dir`**：主链与所有 light/辅助探针必须传**同一个** `data_dir`
   （对应同一 `<data_dir>/generation/` 持久账本）。
2. **统一 `LG022_GEN_LIMIT`**：所有 harness 默认值与**显式运行命令**必须一致（例如统一 10），
   并在运行前把该值写入证据；禁止依赖各脚本**不同**的默认值。
3. **ledger 复用而非新建**：辅助探针**不得**另起 `data_dir`/另设 `limit`；须 `reserve()` 到同一账本，
   使 `remaining` 跨 stage 单调递减可核。
4. **计数只认账本**：报告中的 phase 实数取**该统一账本** `count`，不得把多个独立账本 count 相加充当单一硬限内用量。
5. **保留旧脚本/证据**：仅可新增修正版脚本或明确 diff 说明，不得篡改历史证据 hash。

**本包已提供（仅配置/协调，未执行、无模型调用）**：
`qa/lg022-r2/harness/unified_phase_ledger_config.py` —— 固化原始 harness SHA-256、单一
`LG022_GEN_LIMIT` 默认值(10)，并提供 `validate_run_config(data_dirs, limits)`：
对历史双路径配置会返回两条违规（`2 dirs` + `limits [3,10]`），对未来统一配置返回 `[]`。
**未执行任何真实运行**；旧脚本字节未改（hash 见该文件与下文）。

原始 harness 冻结 SHA-256（本包提交时）：
```
fc95283c…07357  deterministic_probe_r2.py
5b7d5400…78853  ledger_proof.py
e73e9e9d…f8a72  light_qa_probe.py
98da253c…8ce89  real_chain_r2.py
ce4a6ba9…587a7  review_cancel_sdk_proof.py
af4cbbf5…b593a  service_ledger_proof.py
7c326b68…9ae95  stopgate_proof.py
```

## S3. REPORT “PASS（成功门全满足）”的准确 scope 修正

原 `REPORT.md` §5 判定「成功门全满足」。按 PM 补查要求，改为**分列**（不降门、不改门）：

### 已通过（有真实/离线证据）
- **真实主链**：真 DeepSeek worker → 真独立 `ModelReviewer` → `awaiting_acceptance` → 绑定人工 accept
  （duplicate 幂等 / stale 拒绝）；`session_refs` 保留、无伪 `cleanup=done`、真 reviewer teardown 事实
  （`evidence/real-chain.json`）。
- **停止/完成门（机制）**：reviewer 未确认停时 held、槽不释放、refs 保留
  （`evidence/stopgate-proof.json` R2A–R2E；本补证 C2 再证）。
- **生成计数器（产品机制）**：持久账本语义独立通过（`ledger-proof.json`、`service-ledger-*.json`）。
- **D2/D3 确定性/真链**：restart 不重放、跨 Run 预算、成功 Run 无 `fail_reason`（`deterministic-probe-r2.json`、`real-chain.json`）。
- **全量 pytest**：772 passed / 5 skipped（原报告 §4，未重跑）。

### 仍未满足 / 未证实（不改门，仅如实分列）
- **真实 SDK cancel/stop 补证**：**未证实**（§S1）。原 REPORT §4 的 cancel-during-review 证据是
  **`deterministic-double`**（asyncio Event 驱动的替身 reviewer），**无真实 SDK session**；
  前包试图用真 SDK 补证**未跑成**（`/tmp/lg022-cancel-sdk.json` `all_pass=false`）。
  故「真 SDK 下 cancel 确认仅在真实 teardown 后」**仍无证据**。
- **历史实验统一硬总额流程缺口**：主链 7 与 light 1 **未共用同一路径/同一硬限**（§S2）；
  已知实际 8 可核实，但**不受统一硬限**。属 QA 流程缺口（非产品缺陷）。

### 哪些检查仍用 deterministic-double / 替身（诚实标注）
| 检查 | 证据类型 | 说明 |
|---|---|---|
| cancel-during-review（原 REPORT §4） | **`deterministic-double`** | asyncio Event 替身 reviewer，**无真实 SDK session**；不构成真 SDK cancel 证据 |
| restart 不重放 / 跨 Run 预算 | **`deterministic-double` + 真 coordinator/RecoveryScanner 装配** | 注入死 worker probe 的受控替身 |
| 持久账本语义 | **offline（真子进程/真 proxy + 本地伪上游）** | 非 DeepSeek，但用真 SDK/真进程 |
| 本补证 `review_cancel_sdk_proof.py` | **provider-substitute（真 SDK Agent + 伪上游）** | **未跑成**；产出 `all_pass=false`；**不代表产品 fail** |

## S4. 这是否阻断 LG-022 最终 `done`（独立判断，不擅自降门）

**依据来源（原文）**：
- `docs/06-roadmap.md` §2：D 阶段含“暂停取消、重启检查、返修、并行整合”；E 阶段含“浏览器与 Bot 故障场景通过”；
  §2.1 明列 **LG-022 首版集中 QA＝端到端与故障，完整首版验收门，汇总 LG-027/LG-021 证据**。
- `PROJECT.md`（LG-016/006 行为约定）：**“`cancel` 只有观察到 SDK 会话 idle 才返回 `confirmed=true`，
  未确认不写终止状态”**。这是被验收的产品**行为语义**。

**独立判断**：
- 该语义的**产品机制**已在两处通过：① `evidence/stopgate-proof.json` R2A–R2E（未确认 → held、不释放、不删 refs；
  确认后才 `awaiting_acceptance`）；② 真主链 `evidence/real-chain.json` 记录**真实** reviewer teardown 事实
  （`reviewer_cleanup.confirmed=true`）。本补证 C2 再证「未确认保留」。
- **仍缺**：真实 SDK session 活跃时的 cancel/pause **直接**演示“确认顺序”（§S1）——原 §4 只有 deterministic-double，
  前包 provider-substitute 补证未跑成。
- **裁定**：产品行为机制**已满足且未见缺陷**；但**真实 SDK cancel/stop 的直接端到端证据缺失**。
  若 LG-022“端到端与故障”验收把该直接证据设为**必要**，则该项**尚未满足**，构成对 022 最终 `done` 的
  **证据完整性阻断**（应先补齐或由 PM 明确接受限制）；若判定机制证据（离线 stop-gate + 真主链 reviewer teardown）
  已充要，则可**保留限制**（列为“未测/替代方法”），而非门内条件。
- 第二项（§S2 统一账本，仅影响统计口径）属 QA 流程缺口，**不构成** 022 最终 done 的阻断。
- **不降门**：门保持 PLAN.md §4 原文；本条仅如实分列“已满足/未满足”，交 PM/用户裁定。

## S5. 剩余步骤（准确、可执行）

1. **真实 SDK cancel 补证**（可选/按 PM 决定）：在不消耗 DeepSeek 的前提下，用真 `Agent` + 伪上游，
   让 reviewer turn **能真正 teardown**（前包卡在伪上游 hold 使 SDK 5s 内不停）；确认顺序
   `unconfirmed → SDK 真停 → confirmed+cancelled`，或明确记录 SDK 层未知。
2. **统一 ledger 运行**（024/023 或后续 QA）：按 §S2.2 单一 `data_dir` + 统一 `LG022_GEN_LIMIT`，
   出统一 `count`；如需真跑，须另有明确预算授权（本包 0 真调用）。
3. **报告 scope 已按 §S3 修正**；`STATUS.md` 同步。
4. 交 PM/用户：022 最终 `done` 与否 + 是否接受保留限制。

## S6. 提交与资源

- 本包新增/修改：`qa/lg022-r2/SUPPLEMENT.md`、`qa/lg022-r2/STATUS.md`，收纳前包遗留的
  `qa/lg022-r2/harness/review_cancel_sdk_proof.py`（QA 脚本，无秘密），以及新增未执行配置助手
  `qa/lg022-r2/harness/unified_phase_ledger_config.py`（仅配置/协调，无模型调用、无秘密）。
- 未改产品代码、未改历史证据/账本、未动 `docs/`、未动 `lg031`。
- 残留资源：本包无新增进程/端口；root `8123`（pid 3320750）未触碰；旧 worktree/dirty/证据保留。
- 凭证/密钥/grant/请求头/请求体**未**进入本报告或任何文件。
