---
title: "LightGravity Bot L0 首版源包 — 第三方软件 NOTICE"
doc_type: notice
category: engineering
task: "LG-024"
contract: "1.10.0"
sdk: "google-antigravity==0.1.22"
updated: "2026-10-16"
---

# 第三方软件 NOTICE（L0 首版源包）

> 本文件汇总 **L0 源包**实际引用到的依赖的许可与来源版本，供接收方按锁文件重建时保留署名。
> **本 L0 包不随附第三方包体 / SDK / weights**（不重分发）；Python 依赖版本已由 `uv.lock` 固定，
> 前端依赖由 `frontend/package-lock.json` 固定。
> **本包不含本项目自身许可证**：项目暂无 `LICENSE`/`NOTICE`，**未授予公开再分发**（见 §4）。
> 全部版本为实际安装（`importlib.metadata`）实测；随附许可证文件路径亦实测。

## 1. Python 运行时依赖（`uv export --no-dev`，51 项）

| 包 | 版本 | 许可 |
|---|---|---|
| absl-py | 2.5.1 | Apache-2.0 |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| attrs | 26.1.0 | MIT |
| certifi | 2026.7.22 | **MPL-2.0**（文件级弱 copyleft） |
| cffi | 2.1.1 | MIT-0 |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| distro | 1.9.0 | Apache-2.0 |
| fastapi | 0.115.14 | MIT |
| **google-antigravity** | **0.1.22** | **Apache-2.0**（首版唯一执行后端，固定版本） |
| google-auth | 2.62.0 | Apache-2.0 |
| google-genai | 2.30.1 | Apache-2.0 |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpcore2 | 2.13.1 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| httpx2 | 2.13.1 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| mcp | 2.3.0 | MIT |
| mcp-types | 2.3.0 | MIT |
| opentelemetry-api | 1.45.1 | Apache-2.0 |
| protobuf | 7.36.2 | BSD-3-Clause |
| pyasn1 | 0.6.4 | BSD-2-Clause |
| pyasn1-modules | 0.4.2 | BSD |
| pycparser | 3.11 | BSD-3-Clause |
| pydantic | 2.14.1 | MIT |
| pydantic-core | 2.50.1 | MIT |
| pyjwt | 2.15.1 | MIT |
| pypdfium2 | 5.14.0 | BSD-3-Clause + Apache-2.0 + **捆绑 CC-BY-4.0**（见 §2） |
| python-multipart | 0.0.32 | Apache-2.0 |
| referencing | 0.37.0 | MIT |
| requests | 2.34.2 | Apache-2.0 |
| rpds-py | 2026.9.1 | MIT |
| ruamel-yaml | 0.18.17 | MIT |
| ruamel-yaml-clib | 0.2.15 | MIT |
| sniffio | 1.3.1 | MIT OR Apache-2.0 |
| sse-starlette | 3.0.3 | BSD-3-Clause |
| starlette | 0.46.2 | BSD-3-Clause |
| tenacity | 9.1.4 | Apache-2.0 |
| truststore | 0.10.5 | MIT |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| urllib3 | 2.8.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| websockets | 16.1.1 | BSD-3-Clause |

- 运行时包含平台条件项（如 `pywin32` Windows-only、`httpx2-jsfetch` emscripten-only）由锁文件按平台解析，不构成本包固定内容。
- **无 GPL / AGPL / LGPL**。弱 copyleft 仅 `certifi`（MPL-2.0，文件级）；**未修改**其源文件时只需保留许可证与来源。
- 生产依赖闭包命令：`uv export --no-dev --no-emit-project --format requirements-txt`（本包不含包体）。

## 2. pypdfium2 5.14.0 捆绑许可（LG-035 引入，仅 PDF 路径惰性导入）

- 元数据许可证：`BSD-3-Clause, Apache-2.0, dependency licenses`；随附
  `licenses/LICENSES/{BSD-3-Clause,Apache-2.0,CC-BY-4.0}.txt` 及 `licenses/data/linux_x64/BUILD_LICENSES/*`
  （abseil / fast_float / freetype / icu / lcms / libjpeg_turbo / libopenjpeg / libpng / pdfium / zlib 等）。
- **CC-BY-4.0 为署名类许可（非 copyleft）**：分发含其数据 / 构建件时须保留署名。
- 自足 wheel，**不依赖系统 poppler**；非 PDF 路径无需该包。

## 3. 前端依赖（`frontend/package-lock.json`，lockfileVersion 3，224 条目）

- 从锁文件 `packages[*].license` 字段统计：**MIT 204 / ISC 8 / Apache-2.0 5 / BSD-2-Clause 2 /
  BSD-3-Clause 2 / MIT-0 1 / CC-BY-4.0 1**（`caniuse-lite`，浏览器数据）。**无 GPL/AGPL**。
- 前端依赖**不随 L0 源码分发**；仅重建 `frontend/dist` 时参与。L0 包若含预构建 `dist`，
  则 `dist` 中已编译代码的署名要求以构建时依赖为准（见 manifest 含 / 排记录）。

## 4. 本项目自身许可（缺口，不代用户授予）

- 仓库根、`backend/`、`frontend/` 中**未发现** `LICENSE` / `COPYING` / `NOTICE`。
- **未取得**用户对外公开的许可证选择 ⇒ **本包不授予公开再分发**；**公开许可证由用户决定**（本次不发布）。

## 5. 参考仓库（仅开发参考，非产品运行依赖，不重分发）

| 仓库 | HEAD（实测） | 许可 |
|---|---|---|
| Olav OS | `5aa2adf8c49e04dbc623192b197051e607127062` | MIT |
| Olav Tasks | `ab252888bd9e6dc9185a71bcf02b241484e0d4f6` | MIT |
| Olav | `439d3da8a54a9548f6a394fb0265293b5f31acb4` | **Business Source License 1.1（非宽松，非 OSI 开源）** |

- **Olav = BSL-1.1**：仅作方法参考，**不得搬运受限实现**；复用任何文件前逐文件核对许可。

## 6. 上游来源版本

- 后端依赖：按 `uv.lock` 从公开 PyPI 解析；SDK 固定 `google-antigravity==0.1.22`（Apache-2.0）。
- 前端依赖：按 `frontend/package-lock.json` 从公开 npm registry 解析。
- **模式与 Python/前端包体、SDK、weights 均不重分发**；接收方自行从公开来源重建并保留署名。
