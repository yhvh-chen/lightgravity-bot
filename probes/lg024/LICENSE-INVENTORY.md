---
title: "LG-024 阶段 A 许可与来源清单（首版交付）"
doc_type: inventory
category: engineering
task: "LG-024"
updated: "2026-10-16"
---

# 许可与来源清单（阶段 A）

> 真实读取自当前开发机已安装元数据与参考仓库，**不安装新包**。供首版交付/分发可审阅。
> 许可判定不构成参赛/对外发布资格结论；对外动作另行处理。

## 1. 本项目运行/开发依赖（`pyproject.toml`）

| 包 | 固定范围 | 实测版本 | 许可（metadata） |
|---|---|---|---|
| fastapi | `>=0.115,<0.116` | 0.115.14 | MIT |
| uvicorn | `>=0.30,<1` | 0.54.0 | BSD-3-Clause |
| pydantic | `>=2.7,<3` | 2.14.1 | MIT |
| ruamel.yaml | `>=0.18,<0.19` | 0.18.17 | MIT |
| google-antigravity | `==0.1.22` | 0.1.22 | Apache-2.0 |
| pypdfium2 | `>=5,<6` | 5.14.0 | BSD-3-Clause + Apache-2.0 + bundled permissive deps（见 `probes/lg035/QUALITY-PLAN.md`） |
| pytest（dev） | `>=8,<9` | 8.4.2 | MIT |
| pytest-asyncio（dev） | `>=0.23,<1` | 0.26.0 | Apache-2.0 |
| httpx（dev） | `>=0.27,<1` | 0.28.1 | BSD-3-Clause |
| mypy（dev） | `>=1.11,<2` | 1.20.2 | MIT |
| hatchling（构建） | build-system | （未安装元数据） | MIT（构建期） |

- 全部为 **MIT / BSD-3-Clause / Apache-2.0** 类宽松许可；**未见 GPL/AGPL**。
- `google-antigravity==0.1.22` 是**固定唯一真实执行路径**依赖（docs/08 §8），Apache-2.0。

## 2. 本地参考仓库（仅开发参考，**非运行依赖**）

| 仓库 | 本地路径 | HEAD commit | 许可 |
|---|---|---|---|
| Olav OS | `/home/yhvh/code/olav-os` | `5aa2adf8c49e04dbc623192b197051e607127062` | **MIT** |
| Olav Tasks | `/home/yhvh/code/olav-tasks` | `ab252888bd9e6dc9185a71bcf02b241484e0d4f6` | **MIT** |
| Olav | `/home/yhvh/code/Olav` | `439d3da8a54a9548f6a394fb0265293b5f31acb4` | **Business Source License 1.1（非宽松）** |

- **Olav 为 BSL-1.1**：仅作**经验/方法参考**，**不得**直接搬入受限实现；复用任何文件前逐文件检查许可（agent.md §9）。
- Olav OS / Olav Tasks 为 MIT，可参考/移植其模式；仍按文件追踪依赖与署名。
- **参考仓库不是产品运行必需路径**（agent.md §2/§9）。

## 3. 结论

- 首版运行依赖许可清晰、无 copyleft 传染项；SDK 为固定 Apache-2.0 版本。
- 参考仓库中 **Olav 为 BSL-1.1**，须在交付文档中**明确不外搬其受限实现**；MIT 参考可正常署名。
- 本清单为**阶段 A 草案**，阶段 B 落地 README 时按其一致性要求同步。
