# LG-037 集成接线（供唯一集成 owner 串行处理）

本包交付可选向量路径，但**不修改** `backend/lightgravity/api/app.py`（共享文件，owner 规则）
以及任何共享 search 组合/配置/挂载。以下接线由唯一集成 owner 串行执行。

## 1. 本包已存在（已验证，且不改任何共享文件）

- `backend/lightgravity/sources/vectors/**` — `VectorIndex`（可删除重建的 stdlib JSONL 缓存）、
  `VectorSearchService`（建/重建/失效/检索）、`embedder.py`（唯一向量服务客户端）。
- `backend/lightgravity/api/vector.py` — `build_vector_router()`（**新增**路由模块）。
- 测试 `tests/sources/vectors/**`（39 项）在**真实** `create_app` + 真实 `SourceStore` + 真实 HTTP 上运行。

## 2. 最小挂载（集成 owner，`api/app.py`）

1. 在既有 router import 旁加：

   ```python
   from .vector import build_vector_router
   ```

2. 与既有冻结 router 一起挂载：

   ```python
   app.include_router(build_vector_router(), prefix=API_PREFIX)
   ```

无需新依赖、无需新环境变量；`api/app.py` 之外不改任何 owner 文件。

## 3. 挂载后产生的端点（docs/08 §4.3/§6.6，加性可选）

| 方法 + 路径 | 说明 |
|---|---|
| `GET /api/v1/vector/status` | 诚实状态：`enabled`、`backend.model`、`cache{exists,readable,documents,model,dim,cache_version}`、不可用原因。**不调用远端服务**。 |
| `GET /api/v1/vector/search?q=&task_ref=&project_ref=&inbox_ref=&include_global=&limit=&rebuild_if_missing=` | 向量检索 + 回源核对；后端/缓存不可用 → `index_status=index_unavailable`、`lexical_fallback=true`、`hits=[]`；**GET 只读，不写**。 |
| `POST /api/v1/vector/rebuild` | 从文件 SoT **删除并重建**向量缓存；`?source_id=` 可选。 |

响应体为**加性、非权威投影**；权限/版本始终回源核对。

## 4. 配置（env，**不硬编码 LAN**）

```
# LIGHTGRAVITY_VECTOR_BASE_URL=   # 例：授权测试端点
# LIGHTGRAVITY_VECTOR_MODEL=
# LIGHTGRAVITY_VECTOR_TOKEN=       # 仅进程 env，不落仓库/提示词
# LIGHTGRAVITY_VECTOR_TIMEOUT_SECONDS=60
# LIGHTGRAVITY_VECTOR_COLD_TIMEOUT_SECONDS=150
```

未配置 → 向量路径**诚实 disabled**，词法检索与原件查看照常可用。**不把 LAN 地址当运行默认**。

## 5. 与词法 search 的组合语义（供集成 owner 决策）

- 词法是**默认可用**路径（LG-036 `GET /search`）；向量是**可选增强**。
- 建议组合：先词法；若客户端显式请求向量且 `vector/status.enabled`，可并行取向量并合并候选——
  **但每个候选必须分别回源核对**（两路已共享同一 `authorize_and_verify` 规则）。
- **本包不自行实现共享 search 组合**（属共享接线）；若需在 `GET /search` 内联向量，由唯一集成 owner 串行完成，
  并保持「向量不可用 → 词法/原件仍可用」不变量。
- **不得**让向量缓存承载权限/归属；不得因此改动 `source.index` 语义（`vector`/`vector_model` 已在 docs/08 §6.6 冻结）。

## 6. 版本/schema 提案

- **无新端点语义自扩、无新错误码、无新枚举**：复用已冻结的 `source.index.vector`/`vector_model`、
  `index_unavailable` 与 `source.indexed`/`source.invalidated`。故**本包不提出 docs/08 升版**。
- 如集成 owner 认为 `GET /search` 需内联向量，请先登记 docs/08（§4.3/§13）再加性实现。

## 7. 诚实边界

- 端点目前**不可达**，真实检索质量**未验证**；本包机制测试用**替身向量**，不代表品质。
- LG-035 OCR 质量门仍阻塞；`embedding ≠ OCR/ASR`。LG-040 不解锁。
