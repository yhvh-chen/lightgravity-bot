# LG-038 证据目录

Chat 资料接入与 Files 归档检索统一体验（待版本 QA LG-040）的实施证据。

| 文件 | 内容 |
|---|---|
| [INTEGRATION.md](INTEGRATION.md) | 无需改动的共享装配、旧 Files 兼容、`tags` 受保护接入提案 |
| [STATUS.md](STATUS.md) | 实施状态、真实/fixture 边界、诚实缺口 |
| [REPORT.md](REPORT.md) | 交付报告、变更文件、验证命令与结果 |
| [evidence/lg038-browser-results.json](evidence/lg038-browser-results.json) | 真实 Firefox BiDi 9/9 检查结果（1440/1024/390） |
| [evidence/lg038-search-hit.json](evidence/lg038-search-hit.json) | 真实 `GET /search` 命中（含 version+hash） |
| [evidence/lg038-sources-list.json](evidence/lg038-sources-list.json) | 真实 `GET /sources`（upload 已索引 / link not_indexed） |
| [browser_fixture_server.py](browser_fixture_server.py) | 真实 app + fixture 源 + 静态 dist 的测试服务器 |
| [lg038-materials-check.mjs](lg038-materials-check.mjs) | 真实 HTTP + Firefox BiDi 浏览器检查 |

## 复现

```bash
# 后端 + 前端
uv run pytest -q
uv run mypy
cd frontend && npx tsc --noEmit && npx vitest run && npm run build

# 真实浏览器 fixture（真实 uvicorn + 真实 Firefox）
uv run python probes/lg038/browser_fixture_server.py \
  --data-dir /tmp/lg038-fixture --dist-dir frontend/dist --port 8791 &
FIREFOX_BIN=/snap/bin/firefox node probes/lg038/lg038-materials-check.mjs \
  --url http://127.0.0.1:8791/ --out /tmp/lg038-browser \
  --profile-dir "$HOME/snap/firefox/current"
```

真实边界：fixture 源的机读正文由 scripted `MachineDraft` 生成，用于验证“有机读正文才可检索”；
未调用真实 OCR/vector/ASR/模型。产品模型调用 0。
