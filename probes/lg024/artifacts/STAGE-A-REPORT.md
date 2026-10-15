---
title: "LG-024 阶段 A 报告（交付准备；不写共享 docs）"
doc_type: report
category: engineering
task: "LG-024"
owner: "agent:pi-lg024"
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
head: "309e839"
updated: "2026-10-16"
---

# LG-024 阶段 A 报告

> **性质**：首版交付准备的**独立可审阅**产物。**只写 `probes/lg024/**` 与忽略的构建/私有烟测产物**；
> 共享 docs（README、docs/06、PROJECT、agent、docs/08）由 `integrate/lg031-runtime` owner 独占，**未释放前不写**。
> **本阶段产品真实模型生成 0**；**未推送/部署/发布/上传**；**LG-024 不 done**（验收需 Stage B）。
> 所有 runtime/草案原件持久保留；旧 worktree/dirty 未 reset/clean/覆盖/重复 pick；敏感仅私有 700/600。

## 1. 源锚点（核实际）

| 项 | 值 |
|---|---|
| worktree | `/home/yhvh/code/lightgravity-bot-worktrees/lg024`，branch `dev/lg024` |
| HEAD（本报告） | `309e839309c54dfdef92047b9ab4fa44d2ae5d30` |
| 固定首版稳定产品树 | `e0a8cec` —— 与 HEAD 产品路径 `git diff` **空（逐字节相同）** |
| 契约 / SDK | `1.10.0` / `google-antigravity==0.1.22`（实测 0.1.22） |
| Python | CPython 3.12.13（`.venv` 由 `uv run` 新建，gitignored） |
| 锁文件 sha256 | `pyproject.toml` `b16a9132…`；`uv.lock` `53146a1b…`；`frontend/package-lock.json` `92a6a323…` |
| 主工作区 uvicorn | `:8123` PID `3320750`（旧常驻）**未触碰** |
| `integrate/lg031-runtime` | `c4d4e87` + 4 产品源已改 + 未跟踪 `probes/lg031/RUNTIME-AUTH-INTEGRATION/` ⇒ **共享 docs 未释放** |

## 2. 已验 / 未验范围（源码可解析 / 机制实现 / 真实验收分开）

### 2.1 固定首版稳定树 `e0a8cec` 的已验范围（不得向上引申）

| 门 | 范围 | 状态 |
|---|---|---|
| LG-010 原型大版本 QA | 契约 1.3.1 core **最小后端闭环** | **pass/done**（门内） |
| LG-027 设置/凭证 | 设置/凭证 **CLI+HTTP + browser 渲染** | **pass**（门内） |
| LG-021 前端状态/响应式 | 前端状态/响应式（含 `qa/lg021-r1` 26/26） | **done**（门内） |
| LG-022 首版端到端+故障 | 真 SDK+本地 fake SSE 流式停止 PASS、真 DeepSeek 主链一例 PASS | **done**（**仅门内**） |

- 产品内部自检（非产品验收）：第五/七/八批集成 `mypy` 137 files clean、`pytest` 775→794 passed / 2 skipped 等，均为**开发期机制证据**，**不等于真实验收**。
- **LG-022 门内未测**（诚实）：真实 DeepSeek 上游 cancel/pause-during-review；重启后 `verifying`/`repairing → recovery_required`；跨 Run 真实 reject/repair；light/浏览器全矩阵。

### 2.2 未验 / 质量不齐 / 未开（不夸大完整产品能力）

| 项 | 事实 |
|---|---|
| LG-029 领取/租约 | 机制已实现并集成，但 **F2 缺陷返修中**（`fix/lg029-auth` WIP *unverified*）：claim/lease HTTP 端点曾接受请求体 `owner` 未接程序认证身份（违反 LG-028 §2.4）。**未验** |
| LG-031 去中心化整合 | **真实运行硬条件未闭合**（无真实 SDK 两 worker 发现/领取/交接/隔离执行/候选 review），仅真 Git + 进程内 fake executor。**未验** |
| LG-032 去中心化版本 QA | 阶段 A partial，**阶段 B 暂停**；F1 部分符合、F2 重要缺陷。**未整合验收** |
| LG-035 图片/PDF OCR | 机器/人工分层已实现；真实清晰页/多页 PDF 通过（预注册阈值），但**真实中文/表格人工真值质量门阻塞**（端点不可达+无许可样本）。**质量不齐** |
| LG-037 可选向量 | 机制/降级以替身向量通过；**真实检索质量未验证**（服务 `192.168.8.12:11434` 不可达）。**质量不齐** |
| LG-039 中文 ASR | **负结论**：已测服务 4 模型无一同时具备音频输入且支持文本生成；真实人声推理 5 次全失败。 |
| LG-040 资料/Embedding 版本 QA | **未开（todo）** |
| LG-041 中文转写接入 | **质量锁未解锁（todo）**，阻塞于 LG-039 质量门 |
| 完整 checkpoint skip 调度 | **未实现**（既有边界）：过期后未知副作用只进 `recovery_required`，不自动重放 |

### 2.3 LG-023 两组对照证据（不洗成收益）

- **cohort-3（正式）**：4/4 attempts 全部真实交付；请求 **A/B = 3/5/3/5 总 16**（单持久 phase 账本）；A 总 elapsed 25.17s、B 33.43s。
  **组队 arm 在完成率上无增益、成本更高 ⇒ 不支持这两样本的组队收益**。样本小、单模型、强制计划、usage/cost `unknown`。
- **usage/费用 unknown**：provider 未回传可核 token/费用；**不当 0**，也不与 shared 开发-QA 成本混算。
- **旧 45 + 4 单列保留，不隐去**：cohort-1 ledger **45**（协议违规）+ cohort-2 **4**（harness D1 停止成本）；
  **总实际 eval 请求 = 45 + 4 + 16 = 65**（旧部分 SoT 字节已丢失，仅已恢复部分私有保全）。
- `probes/lg023/ledger/generation.count.json` = `{"count":45}`（旧 phase）；cohort-3 16 落其 phase data 账本。

## 3. 产物索引（全部 `probes/lg024/**`）

| 产物 | 路径 | 说明 |
|---|---|---|
| 计划 | `probes/lg024/PLAN.md` | 阶段 A/B 划分与边界 |
| 本阶段状态 | `probes/lg024/STATUS.md` | 开工核对 + 阶段 A 结论文摘 |
| 许可与来源 | `probes/lg024/LICENSE-INVENTORY.md` | 60 Python 包 + 224 前端包 + 参考仓库 + 缺口 |
| 启动/安装入口草案 | `probes/lg024/STARTUP-SMOKE-DRAFT.md` | Make/CLI 入口 + 已跑烟测小节 |
| 分发清单草案 | `probes/lg024/DISTRIBUTION-MANIFEST-DRAFT.md` | L0/L1/L2、include/exclude、锚点 |
| 本地打包脚本 | `probes/lg024/pack-local.sh` | draft source-staging + MANIFEST.sha256 |
| 分发排除校验 | `probes/lg024/verify-dist-exclusion.sh` | 静态禁入项/绝对路径校验 |
| 私有烟测 | `probes/lg024/smoke/`（700/600） | 脚本 + 结果（运行数据 gitignored） |
| 本报告 | `probes/lg024/artifacts/STAGE-A-REPORT.md` | — |

## 4. 准确命令与退出码（真实）

| # | 命令 | 结果 | 退出码 |
|---|---|---|---|
| 1 | `git status --short` | 空（clean） | 0 |
| 2 | `git diff e0a8cec HEAD -- backend/ frontend/ src/ tests/ pyproject.toml uv.lock` | 空 | 0 |
| 3 | `uv run python` 遍历 60 dist：随附 LICENSE 定位+分类 | 60/60 有实体许可证文件；无 GPL/AGPL；MPL-2.0×2 | 0 |
| 4 | `frontend/package-lock.json` 224 条目 license 字段统计 | 全有 license；非 MIT 明细见清单 §3 | 0 |
| 5 | `bash probes/lg024/pack-local.sh /tmp/lg024-dist-test HEAD` | 448 文件 L0 归档 + manifest + 锚点 | **0** |
| 6 | `bash probes/lg024/verify-dist-exclusion.sh <tarball>` | OK（448 文件，无禁入项）；17 条 doc/evidence `/home/yhvh/` **WARN**（非产品码） | **0** |
| 7 | 脏产品树 → `pack-local.sh` | `refuse: product tree is dirty` | **3**（预期，已恢复文件） |
| 8 | `bash probes/lg024/smoke/run-smoke.sh`（port 18432） | health 200 / version 200 / index 200 / protected 401 / stop 0 / 端口释放 / 无残留 | **0** |

- 命令 5/6/8 的原始输出与私有记录见 `smoke/smoke-record.log`（600）。命令 5/6 输出目录 `/tmp/lg024-dist-test`（临时，不入 repo）。
- **残留清理声明（真实）**：为核实“旧 SDK 会话 DB 不入分发”，曾以 `sqlite3 mode=ro` 只读打开一个旧 `probes/agensh-orchestration-sdk-corrected/**/*.db`，
  SQLite 连同产生了两个 `-shm`/`-wal` 边车文件（未跟踪）。原 `.db` 未被修改（mtime 仍为 checkout 时间）；
  本包已删除**自己产生的**两个边车文件以恢复原状（非 reset/clean 他人成果）。后续不再打开这些 DB。**未抽取/未持久化任何 prompt/headers/密钥**。

## 5. 烟测详情（Stage A，产品真实模型 0）

- **隔离**：专用端口 `18432`、专用 data `probes/lg024/smoke/_data`、`--no-executor`；**不碰 :8123、不复用主 worktree dataRoot**。
- **health**：`{"status":"ok","contract_version":"1.10.0","schema_version":"lightgravity.bot/v1","capabilities":{...,"sdk_adapter":false}}`。
- **受保护接口**：无 token `POST /api/v1/settings/connections` → **401 unauthorized**（`LocalAccessPolicy` 默认拒绝）；
  `_secrets/` 空、未生成凭证、未打印任何 token 值（仅 `token_source:"generated"`）。
- **静态 UI**：`GET /` → 200（CLI 默认壳；`frontend/dist` 不存在，**未因分发需要而 build 前端**）。
- **停止**：`lightgravity stop` exit 0 → 端口 `18432` 释放、无 `lightgravity start` 残留；主 `:8123` PID 不变。
- **依赖安装**：使用**已锁版本**（`uv.lock`）；`.venv` 由 `uv run` 就地创建。**包未提供离线自含安装**：依赖/SDK 需从公开来源按锁文件重建，**不把 dev 环境"可运行"写成离线自含安装**。

## 6. 许可缺口与分发边界（详见清单/草案）

- **本项目自身无 LICENSE/NOTICE**（缺口）。**未选定公开许可证** ⇒ **不替用户授予**；对外发布前须用户明确选择，Stage B 落地。
- **弱 copyleft 提醒**：Python `certifi`/`pathspec`（MPL-2.0，文件级）、`pypdfium2` 捆绑 CC-BY-4.0；
  前端 `caniuse-lite`（CC-BY-4.0 数据）。**无 GPL/AGPL/LGPL**。
- **参考仓库 Olav = BSL-1.1（非宽松）**：仅方法参考，**不外搬受限实现**；Olav OS / Olav Tasks = MIT。
- **禁入最终分发**：`.env`/凭证/secret store、SDK DB（旧 `probes/**/*.db` 111 个）、`bot-data/`、个人资料、
  probes 原始日志/raw 上游、`.venv`/`node_modules`/`dist`、本地绝对路径。
- **私人本地 review 与公开发布分开**：本阶段**不要求用户确认发布**，也不做任何上传/部署/推送。

## 7. 未测 / 限制（不写"全部通过"）

- 真实 `lightgravity init` 写连接凭证、`status --deep` 就绪报告、浏览器六入口渲染、真实模型闭环 **未在 Stage A 跑**（部分烟测不冒充）。
- 未重跑全量后端 pytest / 未跑完整前端矩阵（**UI 未改**，本阶段无需）。
- 未安装无关 license 工具、未跑远程脚本、未下载 weights。
- 打包脚本产出为 **draft**：`main` 与 `integrate/lg031-runtime` 并行演进，**不宣称最新 main 可发布**。

## 8. Stage B 具体接续（待 `integrate/lg031-runtime` owner 释放）

1. **释放判据**：该 owner 停止写共享 `api/{app,bootstrap}.py`、docs/08、README、PROJECT、agent、docs/06，且产品源整合候选稳定。
2. **绑定准确候选**：以届时真实 `main` 产品树/契约/SDK 为准重出 `pack-local.sh` 锚点（**不预设**）。
3. **串行落地共享文档**：README 入口（安装/启动/任务/资源/恢复）、docs/06 排期状态、必要 PROJECT·agent·docs/08 一致性。
4. **许可证决策**：请用户选定项目公开许可证并落 LICENSE（本阶段**未**代行）。
5. **端到端补验**：真实 `init`+`status --deep`＋浏览器六入口＋（授权/预算内）真实模型闭环；记录退出码/版本/限制。
6. **完成 LG-024 验收条件后由主代理决定 mark done**（本阶段**不 done**）。

## 9. 状态

- **LG-024 `in-progress`（阶段 A 完成，不 done）**；LG-029/031/032/035/037 `in-progress`；LG-040/041 `todo`；
  LG-021/022/023/030/034/036/038 `done`（各门内/待版本 QA 范围保留）。
- 契约 `1.10.0`、SDK `0.1.22`、自主模式默认 off 不变。**本阶段产品真实模型生成 0**，未推送/部署/发布/上传。
- **精确本地 commit**：见 `dev/lg024` HEAD（本报告提交后）。
