# DOC_CHECKS — 本轮文档/证据检查记录

范围：资料接入方向文档落盘（新增 `docs/09-source-intake-and-retrieval.md`、入口文档同步、
`probes/source-intake/evidence/` 证据归档）。只执行一次性命令；**未跑镜像测试、未跑后端/前端
pytest/vitest/build、未跑真实推理**。结果均为本次本机实际输出。

## 1. 归档 sha256 与大小

命令（读取 `MANIFEST.json` 并逐条重算目标 sha256）：

```bash
.venv/bin/python - <<'PY'
import hashlib, json
m = json.load(open("probes/source-intake/evidence/MANIFEST.json"))
assert m["verification"]["all_byte_identical"] and m["verification"]["under_3mb"]
for e in m["entries"]:
    assert hashlib.sha256(open(e["target"], "rb").read()).hexdigest() == e["sha256"], e["target"]
print("manifest ok:", m["verification"]["entry_count"], "entries,",
      m["verification"]["total_archived_bytes"], "bytes")
PY
```

结果：**PASS**。`entry_count=28`、`total_archived_bytes=952781`（≤3 MiB）、
`all_byte_identical=true`、`under_3mb=true`；每一条目目标 sha256 与 manifest 一致，
源 `/tmp` 文件字节未改写。

## 2. Markdown 相对链接与锚点

命令：一次性 Python 扫描 `README.md`、`agent.md`、`PROGRESS.md`、`docs/01,02,04,05,08,09`、
`probes/source-intake/README.md`、`probes/source-intake/DOC_CHECKS.md` 的 `[..](..)` 相对链接，解析相对路径存在性。

结果：**PASS**。检查 11 个文件、125 条相对链接均解析到存在的文件；本轮新增/修改的链接
**不含 `#fragment` 锚点**（锚点检查为空集，无失败项）。

## 3. frontmatter 合法性

命令：`.venv/bin/python` 用 ruamel.yaml 解析各文档 `---` frontmatter。

结果：**PASS**。`README.md`、`agent.md`、`PROGRESS.md`、`docs/01/02/04/05/08/09` 的 frontmatter 均可解析为
mapping；`docs/02`、`docs/05` 的 `updated` 由 `2026-10-14` 同步为 `2026-10-15`。
`probes/source-intake/README.md` 与本文件沿用 probe 目录无 frontmatter 约定。

## 4. 入口与 SoT/Task 边界一致性

| 检查 | 结果 |
|---|---|
| `docs/09` 声明“未实现、API/schema 未冻结” | **PASS** |
| `README.md`、`agent.md`、`docs/01/02/04/05/08` 均链接 `docs/09` | **PASS** |
| Chat 为唯一常规资料接入入口、Files 不新增一级入口 | **PASS**（docs/05 §3.1、docs/09 §2） |
| 上传处理不自动创建交付 Task/Run/团队、不绕过交付门 | **PASS**（docs/04 §2、docs/09 §4） |
| 原件/派生/缓存/人工校订分层与回源；上传 frontmatter 不受信 | **PASS**（docs/02、docs/09 §5） |
| Chat 回执只在摄取/文件层面示意，不加入现有 Task phase | **PASS**（docs/09 §6） |
| 邮箱连接器与模型 Connection 分离、不暗加冻结 schema | **PASS**（docs/09 §2） |

## 5. 未新增 API/枚举、契约版本未变

| 检查 | 命令 | 结果 |
|---|---|---|
| `CONTRACT_VERSION` 未变 | `grep CONTRACT_VERSION backend/lightgravity/contracts/constants.py` | `1.5.0` |
| `contracts/` 无本轮改动 | `git diff --stat -- backend/lightgravity/contracts` | 空 |
| `docs/08` 仅加说明段，无端点/枚举改动 | `git diff -- docs/08-interface-contract.md` | 仅 §1 一段说明 |
| `docs/09` 未定义新端点/枚举，仅描述“未冻结”方向 | 人工核对 | 无新端点/枚举定义 |

## 6. 空白/差异检查

```bash
git diff --check
```

结果：**PASS**，退出码 0，无空白错误。新增未跟踪文件另用
`git diff --no-index --check /dev/null <file>` 检查，未发现空白错误（退出码 1 表示存在差异本身）。

## 7. 诚实限制

- 本轮**没有**运行后端/前端测试、构建、mypy、Playwright 或任何真实模型请求。
- `docs/09` 的阶段/回执/作业状态是**设计示意**，不是已实现枚举；实现前须按 `docs/08` §13 冻结并升版。
- 证据归档只证明两个探针在**当时本机/合成样本**下的结果，不代表生产质量、整台服务能力或产品接入。
- 现有 Files 上传 API/UI 为历史实现，交互收拢**未开始**；本轮未改其代码或语义。
- `PROJECT.md` 未由本轮文档写者修改。

## 8. 收尾细化复核（2026-10-15，本次）

范围：仅对已落盘资料设计做最小文案收尾，澄清三处边界，不新增实现。改动文件：
`docs/09-source-intake-and-retrieval.md`（§4 授权边界、§8 去重作用域、§10 范围澄清）、
`docs/04-bot-behavior.md`（§2）、`probes/source-intake/README.md`（§2.3），并同步
`agent.md` §3 同一句边界。未改代码/任务/原始证据/manifest/`PROJECT.md`/`CONTRACT_VERSION`，
未运行模型/联网/安装/pytest/mypy/build。

### 8.1 本次细化内容

| 项 | 位置 | 结果 |
|---|---|---|
| 1 摄取授权边界 | `docs/04` §2、`docs/09` §4、`agent.md` §3 | 统一为：资料接入授权范围内程序可写原件/资料记录/提取件/索引、不要求工程交付 Run；工程源码修改、Task 运行控制状态修改等仍遵现有 Task/Run 权限与验收，摄取不扩大授权，有界工具问答仍只读，不把每次上传变成重复确认 |
| 2 去重作用域 | `docs/09` §8 | 区分同一来源/同一授权范围的重复提交，与相同字节来自不同来源/不同 Task/Project（后者保留独立来源记录/作用域/权限/引用，即使未来共享 blob 也不自动合并授权、抹来源或扩大可见范围）；幂等绑定稳定接入请求 ID，源 hash 变化生成新源版本并重建派生，同请求 ID 不同 payload 按冲突处理 |
| 3 音频实测范围 | `docs/09` §10、`probes/source-intake/README.md` §2.3 | 改为：已测 Qwen 中文截图/扫描页 OCR 成功；已测 Qwen 的 ASR 501 与 chat `input_audio` 500 拒绝；已测 embedding 模型转写失败；`gemma4-mtp`/其它生成模型与 reader 未测；不能断言整台服务均无 ASR |

### 8.2 归档 sha256 与大小（复核）

命令同 §1。结果：**PASS**。`entry_count=28`、`total_archived_bytes=952781`、
`all_byte_identical=true`、`under_3mb=true`；逐条重算目标 sha256 与 `MANIFEST.json` 一致，
**归档 28 项 sha 未变**，源 `/tmp` 文件未改写。

### 8.3 Markdown 相对链接与锚点（复核）

命令同 §2。结果：**PASS**。检查 11 个文件、125 条相对链接均解析到存在的文件；
无 `#fragment` 锚点。

### 8.4 frontmatter 合法性（复核）

命令同 §3。结果：**PASS**。`README.md`、`agent.md`、`PROGRESS.md`、
`docs/01/02/04/05/08/09` 的 frontmatter 均可解析为 mapping；
`probes/source-intake/README.md` 与本文件沿用 probe 目录无 frontmatter 约定。

### 8.5 空白/差异检查（复核）

```bash
git diff --check
```

结果：**PASS**，退出码 0，无空白错误。三个本轮改动的未跟踪文件
（`docs/09-source-intake-and-retrieval.md`、`probes/source-intake/README.md`、
`probes/source-intake/DOC_CHECKS.md`）另用 `git diff --no-index --check /dev/null <file>` 检查，
未发现空白错误。

### 8.6 本次限制

- 仅文案收尾与边界澄清，**未新增/修改代码、任务、原始证据、`MANIFEST.json`、`PROJECT.md`**，
  `CONTRACT_VERSION` 保持 `1.5.0`。
- 未运行后端/前端测试、mypy、构建、Playwright 或任何真实模型请求。
- 具体摄取处理状态与目录仍**待接口冻结**，本次不定义字段。
