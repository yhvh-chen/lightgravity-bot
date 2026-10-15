# S2 interface — 带依赖交接

## 目标

实现 `src/geometry.py` 的 `area(shape)`、`perimeter(shape)`，以及 `src/report.py` 的 `describe(shape)`。
`report.py` 依赖 `geometry.py`（`from .geometry import area, perimeter`），构成跨模块依赖链。

## 接口（显式写定）

- `shape` 为 dict，`kind` ∈ {`rect`, `circle`}。
- `rect` 使用 `width, height`；`circle` 使用 `radius`。
- 未知 `kind` 抛 `ValueError`。
- `area`/`perimeter` 对 circle 使用 `math.pi`。
- `describe(shape)` 返回 `f"{shape['kind']}: area={area(shape):.2f} perimeter={perimeter(shape):.2f}"`。

## 交付要求

- 在工程根目录下修改 `src/geometry.py` 与 `src/report.py`。
- 仅修改这两个文件；不要改动测试或其他文件。
- 完成后确保 `import src.geometry` / `import src.report` 正常，且 `report.describe` 对 rect/circle 正确。
