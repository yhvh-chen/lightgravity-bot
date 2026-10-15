---
title: "LG-024 阶段 A 许可与来源清单（首版交付）"
doc_type: inventory
category: engineering
task: "LG-024"
contract: "1.10.0"
updated: "2026-10-16"
---

# 许可与来源清单（阶段 A，草案）

> 真实读取自当前开发机**已安装元数据与各包随附的 LICENSE 文件**，以及本地参考仓库现存文件；
> **不安装新包、不跑远程脚本、不下载 weights**。命令与退出码见 `artifacts/STAGE-A-REPORT.md`。
> **本清单不构成参赛/对外发布资格结论，也不替用户授予公开许可证**；公开发布与云端资格另行处理。
> **依赖 / SDK / weights 不重分发**：本清单只作来源追溯，打包草案默认**不含**第三方包体（见 §5 / `DISTRIBUTION-MANIFEST-DRAFT.md`）。

## 1. 本项目直接依赖（`pyproject.toml`，运行 + dev + 构建）

| 包 | 声明范围 | 实测版本 | 许可（随附 LICENSE 实证） |
|---|---|---|---|
| fastapi | `>=0.115,<0.116` | 0.115.14 | MIT |
| uvicorn | `>=0.30,<1` | 0.54.0 | BSD-3-Clause |
| pydantic | `>=2.7,<3` | 2.14.1 | MIT |
| ruamel.yaml | `>=0.18,<0.19` | 0.18.17 | MIT |
| google-antigravity | `==0.1.22` | 0.1.22 | **Apache-2.0**（固定唯一真实执行路径依赖） |
| pypdfium2 | `>=5,<6` | 5.14.0 | BSD-3-Clause + Apache-2.0 + **捆绑 CC-BY-4.0** 及多项宽松 bundled deps（见 §4） |
| pytest（dev） | `>=8,<9` | 8.4.2 | MIT |
| pytest-asyncio（dev） | `>=0.23,<1` | 0.26.0 | Apache-2.0 |
| httpx（dev） | `>=0.27,<1` | 0.28.1 | BSD-3-Clause |
| mypy（dev） | `>=1.11,<2` | 1.20.2 | Apache-2.0（含 typeshed 子许可） |
| hatchling（构建） | build-system | （未装元数据） | MIT（构建期） |

## 2. 全部 60 个已解析 Python 依赖（含传递依赖）逐包许可

> 命令：`uv run python` 遍历 `importlib.metadata.distributions()`，对每包定位随附
> `LICENSE*`/`COPYING*` 文件并分类。**全部 60 包都有实体许可证文件**，无缺失。
> 分类后**无 GPL / AGPL / LGPL**；弱 copyleft 仅 MPL-2.0；另有双许可与数据类许可见脚注。

| 许可 | 包 |
|---|---|
| MIT | annotated-types, anyio, attrs, cffi, charset-normalizer, fastapi, h11, iniconfig, jsonschema, jsonschema-specifications, librt, mcp, mcp-types, mypy_extensions, pluggy, pydantic, pydantic_core, PyJWT, pytest, referencing, rpds-py, ruamel.yaml, ruamel.yaml.clib, truststore, typing-inspection, urllib3 |
| Apache-2.0 | absl-py, distro, google-antigravity, google-auth, google-genai, mypy, opentelemetry-api, pytest-asyncio, python-multipart, requests, tenacity |
| BSD-3-Clause（含 BSD 系） | click, httpcore, httpcore2, httpx, httpx2, idna, protobuf, pyasn1, pyasn1_modules, pycparser, Pygments, sse-starlette, starlette, uvicorn, websockets, cryptography* |
| **MPL-2.0（弱 copyleft，文件级）** | **certifi, pathspec** |
| 双许可 | cryptography（`Apache-2.0 OR BSD-3-Clause`）、packaging（`Apache-2.0 OR BSD-2-Clause`）、sniffio（`MIT OR Apache-2.0`） |
| 其他 | typing_extensions（PSF-2.0）、pypdfium2（BSD-3-Clause, Apache-2.0, **dependency licenses**，见 §4） |
| 本项目自身 | **lightgravity-bot 0.1.0 — 无 LICENSE 文件（缺口，见 §5）** |

\* cryptography 的随附 LICENSE 主文件为 Apache/BSD 双许可（`LICENSE.APACHE` + `LICENSE.BSD`）。

- **MPL-2.0 说明**：`certifi`、`pathspec` 为 Mozilla Public License 2.0，属**文件级**弱 copyleft；
  未修改其源文件时，仅需保留许可证与来源，不传染本项目源码。若最终分发含其包体，须随附 MPL-2.0 文本。
- **结论**：Python 依赖许可清晰，**无强 copyleft 传染项**；固定 SDK 为 Apache-2.0。

## 3. 前端依赖（`frontend/package.json` + `frontend/package-lock.json`，lockfileVersion 3）

> 直接从锁文件 `packages[*].license` 字段统计，**224 个条目全部带 license 字段，无缺失**。

| 许可 | 条目数 |
|---|---|
| MIT | 204 |
| ISC | 8 |
| Apache-2.0 | 5 |
| BSD-2-Clause | 2 |
| BSD-3-Clause | 2 |
| MIT-0 | 1 |
| **CC-BY-4.0** | 1（`caniuse-lite` 数据包） |

- **无 GPL/AGPL**。非 MIT 明细：`aria-query`/`baseline-browser-mapping`/`expect-type`/`typescript`/`xml-name-validator`（Apache-2.0）、
  `lru-cache`/`electron-to-chromium`/`picocolors`/`saxes`/`semver`/`siginfo`（ISC）、`entities`/`webidl-conversions`（BSD-2-Clause）、
  `source-map-js`/`tough-cookie`（BSD-3-Clause）、`@csstools/color-helpers`（MIT-0）、`caniuse-lite`（CC-BY-4.0，浏览器数据）。
- 前端依赖**不随源码分发**，仅在构建 `frontend/dist` 时参与；若最终分发含 `dist`，须随附相应许可证（见 §6）。

## 4. pypdfium2 5.14.0 捆绑许可（LG-035 引入）

- 元数据 `License: BSD-3-Clause, Apache-2.0, dependency licenses`；随附 `licenses/LICENSES/{BSD-3-Clause,Apache-2.0,CC-BY-4.0}.txt`
  与 `licenses/data/linux_x64/BUILD_LICENSES/*`（abseil/agg23/fast_float/freetype/icu/lcms/libjpeg_turbo/libopenjpeg/libpng/llvm-libc/pdfium/pdfium-binaries/simdutf/zlib）。
- **注意 CC-BY-4.0**：属署名类许可（非 copyleft），分发含其数据/构建件时须保留署名。
- 自带自足 wheel，**不依赖系统 poppler**；仅 PDF 路径惰性导入。
- 详细 provenance 亦见 `probes/lg035/QUALITY-PLAN.md`。

## 5. 本项目自身许可证（**缺口，不自行授予**）

- 仓库根、`backend/`、`frontend/` 中**未发现** `LICENSE` / `COPYING` / `NOTICE` 文件（`find` 仅命中本清单自身）。
- **未取得**用户对外公开的许可证选择；**本阶段不替用户授予公开许可证、不新增 LICENSE 文件**。
- **私人本地 review** 与**公开发布**分开：私人本地评审无需公开许可结论；**对外发布前须由用户明确选定许可证**并由 Stage B
  落地。此项为 Stage B 的**显式待决**。

## 6. 本地参考仓库（仅开发参考，**非产品运行依赖、不重分发**）

| 仓库 | 本地路径 | HEAD commit（实测） | 许可（LICENSE 首行实证） |
|---|---|---|---|
| Olav OS | `/home/yhvh/code/olav-os` | `5aa2adf8c49e04dbc623192b197051e607127062` | **MIT** |
| Olav Tasks | `/home/yhvh/code/olav-tasks` | `ab252888bd9e6dc9185a71bcf02b241484e0d4f6` | **MIT** |
| Olav | `/home/yhvh/code/Olav` | `439d3da8a54a9548f6a394fb0265293b5f31acb4` | **Business Source License 1.1（非宽松，非 OSI 开源）** |

- **Olav 为 BSL-1.1**：**仅作经验/方法参考**，**不得**直接搬入受限实现；复用任何文件前逐文件检查许可（agent.md §9）。
- Olav OS / Olav Tasks 为 MIT，可参考/移植其模式；仍按文件逐项追踪依赖与署名。
- 三仓库**不是产品运行必需路径**（agent.md §2/§9）；本阶段**未修改**参考仓库。LG-029/031 实现记录均已声明"只读语义、未复制代码"。
- 角色/技能候选来源（agency-agents 等在线参考）**本阶段未下载/未核许可**，如需移植须在 Stage B 单独追溯（见 §7）。

## 7. 未取得许可原文 / 未决项（如实记录）

| 项 | 状态 |
|---|---|
| 本项目自身公开许可证 | **未选定、未取得**（用户决定；Stage B 阻塞项） |
| agency-agents 等在线角色内容 | **未下载/未核许可**（本阶段不需；如移植须单独追溯来源 commit + 许可） |
| LG-035 真实 OCR 样本来源 | 记录为 `tesseract-ocr/test`（Apache-2.0，经 GitHub license API 核验，见其 STATUS）；本清单不重复主张 |
| LG-039 中文 ASR 样本 | Wikimedia Commons `Chinese language-1.ogg`（CC BY-SA 3.0，见其 STATUS）；**仅作验证，不随源码分发** |
| 第三方包体/LICENSE 文本随附 | **打包草案默认不含第三方包体**（不重分发）；若改为含，须成批随附上述许可证文本并重列 |

## 8. 分发范围（摘要，详见 `DISTRIBUTION-MANIFEST-DRAFT.md`）

- **可入**：本项目自有源码（`backend/`、`frontend/src/`、`tests/`）、工程/文档、`pyproject.toml`+`uv.lock`、
  `frontend/package.json`+`package-lock.json`、契约内文本。
- **禁入**：`.env`/凭证/secret store、SDK session DB（含旧 `probes/**/*.db`）、`bot-data/`、个人资料、probes 原始日志/raw 上游、
  `.venv`/`node_modules`/构建缓存、本地绝对路径。
- **不重分发**：Python/前端第三方包体、SDK、weights（由锁文件+公开来源重建）。
