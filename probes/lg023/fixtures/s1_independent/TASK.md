# S1 independent — 独立两文件修复

## 目标

实现 `src/slugs.py` 的 `slugify(title)` 与 `src/ranges.py` 的 `clamp(value, lo, hi)`、`in_range(value, lo, hi)`。
两个文件相互独立，无依赖。

## 语义（验收一致）

- `slugify(title: str) -> str`：转为小写；把**连续**的非字母数字字符替换为**单个** `-`；去掉首尾 `-`。
- `clamp(value, lo, hi)`：低于 `lo` 返回 `lo`，高于 `hi` 返回 `hi`，否则返回 `value`。
- `in_range(value, lo, hi) -> bool`：`lo <= value <= hi` 时为 `True`，否则 `False`。

## 交付要求

- 在工程根目录下修改 `src/slugs.py` 与 `src/ranges.py`。
- 仅修改这两个文件；不要改动测试或其他文件。
- 完成后确保代码可被 `import src.slugs` / `import src.ranges` 正常导入。
