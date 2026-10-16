# LG-050 本地合入与构建 — 收口报告（close/report）

> PM 收口补记：本报告记录合入与构建执行完成时的事实。其后 README 已补完整团队建号、启动与多机访问步骤，LG-050 已依据独立 QA 记为 done；用户最终验收仍待定。产品代码未再改动，既有 QA 限制保留。

- 角色：LG-050 本地合入与构建执行者（非 PM）
- 结果：**本地合入成功 + 主目录生产构建成功**
- 产品候选：`feat/team-integration-20261016` @ `2d83263`
- QA 证据：`qa/team-chat-20261016` @ `19882bd`（独立 QA = PASS_WITH_LIMITATIONS，`/tmp/lg-team-qa-REPORT.md`）
- 合入 commit（merge --no-ff）：**`4b0dd207a99220f8a7e23699cefa5061c8523cf6`**
- 边界：未发布、未 push、未重启 8123、未调真实模型、未读 `.env`、未触碰任何现有 data/账号配置、未另做产品改动/新样本测试。

## 1. 合入前基线核对（符合预期）

| 项 | 观测 | 结论 |
|---|---|---|
| main HEAD | `0ecfec8c22351bbc9764a1f7dbbb069d8a3a0a76` | 与指派一致 |
| main 工作区 dirty | 仅 ` M PROGRESS.md`（+13 行，用户内容） | 一致 |
| PROGRESS.md sha256（合并前） | `c95eb3b3969c40d6eb269edeefba1ffba10d2ea956c39ed55883f854e13bad36` | 已记录 |
| merge-base(main, 2d83263) | `0ecfec8`（即 main HEAD） | 产品分支从 main 领先 7 个 commit |
| 主目录常量 CONTRACT_VERSION（合并前） | `1.12.0` | 待合入后核对 |

## 2. 候选 vs QA 证据差异核对

`git diff --name-status 2d83263 19882bd` → 仅 10 个新增文件，全部在 `probes/team-chat-20261016/qa/`：

```
A probes/team-chat-20261016/qa/QA-REPORT.md
A probes/team-chat-20261016/qa/qa-browser-results.json
A probes/team-chat-20261016/qa/qa-browser-transcript.txt
A probes/team-chat-20261016/qa/qa-cli-start.txt
A probes/team-chat-20261016/qa/qa-http-results.json
A probes/team-chat-20261016/qa/qa_browser_e2e.mjs
A probes/team-chat-20261016/qa/qa_browser_server.py
A probes/team-chat-20261016/qa/qa_cli_start.sh
A probes/team-chat-20261016/qa/qa_http.py
A probes/team-chat-20261016/qa/run_browser_e2e.sh
```

- 非 QA 路径差异数量：**0**
- 产品子树在两 commit 间完全一致（backend/frontend/docs 无 diff）
- `19882bd` 是 `2d83263` 的直接子 commit（单父）
- 结论：`2d83263..19882bd` 仅新增 QA 证据，**产品树相同**，符合指派。

## 3. 合入结果

执行：

```
git merge --no-ff 19882bd
→ Merge made by the 'ort' strategy. 73 files changed, 5847 insertions(+), 95 deletions(-)
```

- merge commit：`4b0dd207a99220f8a7e23699cefa5061c8523cf6`
- 父：`0ecfec8` (main) + `19882bd` (QA)
- **无冲突**（`2d83263` 未触碰 `PROGRESS.md`，故用户文件无冲突风险）
- 未执行 stash / reset / clean；`PROGRESS.md` 全程保留

### 产品候选树对照（合入后 main vs 候选 2d83263）

| 路径 | main(HEAD) tree | 候选 2d83263 tree | |
|---|---|---|---|
| backend | `90558cc05803e347253ffc179e9f92caf09de22a` | 同左 | SAME |
| frontend | `09b53dc9c5dbd305581c8277710de611a7959703` | 同左 | SAME |
| docs | `c41d96967659d8d1a894ca7fa7be1bb61f7aadff` | 同左 | SAME |
| tests | `b96882220286bf52725b4a1dad4a4fff3f64f6ac` | 同左 | SAME |

`.env.example` / `README.md` / `PROJECT.md` 亦与候选一致。合入后主目录 `CONTRACT_VERSION = "1.13.0"`（`backend/lightgravity/contracts/constants.py:121`），与 QA/候选记录一致。

QA 证据已在 main：`probes/team-chat-20261016/qa/`（10 文件）。

## 4. 主目录生产构建（frontend/dist 实际重建）

`frontend/dist` 为 gitignore（旧 dist 为 10-16 19:37 的旧产物），必须重建为登录页版本。

```
npm --prefix frontend run build
> tsc --noEmit && vite build
vite v5.4.21 building for production...
✓ 107 modules transformed.
dist/index.html                   0.40 kB │ gzip:  0.27 kB
dist/assets/index-FK02_4JN.css   38.93 kB │ gzip:  5.77 kB
dist/assets/index-eVTue_U2.js   298.56 kB │ gzip: 88.05 kB
✓ built in 1.10s   (EXIT=0)
```

- 主目录实际 `frontend/dist` 已重建（时间戳 10-16 22:27），`index.html` 引用新 hash `index-eVTue_U2.js`。
- 构建产物含团队登录门相关标记（`team`/`password`），与 QA 侧 107 modules 一致。
- 未提交 dist（gitignore），未另做产品改动。

## 5. 收口后核对

| 检查 | 结果 |
|---|---|
| PROGRESS.md sha256（合并/构建后） | `c95eb3b3969c40d6eb269edeefba1ffba10d2ea956c39ed55883f854e13bad36` — **未变** |
| git status（porcelain） | ` M PROGRESS.md`（仅此一项；无 untracked） |
| 8123 | 运行中 pid 3320745/3320750，启动于 Oct 15 00:07（uptime ~1d22h）— **未重启、未触碰** |
| 新增服务残留 | 无（本次仅执行 build，无长驻进程；`vite`/构建进程已退出） |
| push | 未 push（`origin/main=c04c10c` 不变；main ahead 378） |

## 6. 限制 / 遗留（均非本次任务范围，如实报告）

1. **README 团队模式运行步骤未补**：QA 已登记为文档缺口，按指派由 root 随后直接补（本任务明确不修改任务/PM 文档）。
2. **8123 未重启**（授权要求）：常驻进程仍是旧进程，磁盘上新 `frontend/dist` 不会由该进程即时生效；root 后续重启后才会服务新登录页。
3. **未重跑全量测试**：按指派不重复已通过的全量测试；未跑新样本。
4. QA PASS_WITH_LIMITATIONS 的 non-blocking 项（README、cross-origin 错误码不统一、后台暂停轮询、`bot` 大小写、限流内存态、未接真实模型/SDK、浏览器同进程双 context）继续保留，不影响本次技术收口。
5. 本报告不更新 LG-050 状态、不涉及发布/部署。
