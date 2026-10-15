---
control_writer: driver
experiment_schema: agensh-orchestration-sdk/v1 (experiment-only)
fixture_initial_hash: 1862b291f11ccd793e10fe833d4c6204a22be195c616d5e4b1433b72c45ad31c
group: B
run_id: t2_interface__B__r0
task: t2_interface
---

# TASK

## 用户目标（本轮）
实现 src/geometry.py 和 src/report.py，二者必须遵守同一个 shape 接口（不要修改其他文件）：
- shape 是 dict：kind 为 "rect" 时含 width、height；kind 为 "circle" 时含 radius。
- geometry.area(shape): rect 返回 width*height；circle 返回 math.pi*radius**2；未知 kind 抛 ValueError。
- geometry.perimeter(shape): rect 返回 2*(width+height)；circle 返回 2*math.pi*radius；未知 kind 抛 ValueError。
- report.describe(shape): 使用 geometry 的 area/perimeter，返回 f"{shape['kind']}: area={area(shape):.2f} perimeter={perimeter(shape):.2f}"。
