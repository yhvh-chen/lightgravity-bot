"""Throwaway harness: verify report.describe() against a reference geometry.

Not part of the deliverable; safe to delete.
"""
import math
import sys

sys.path.insert(0, "/tmp/lightgravity-worktrees/agensh-sdk-20261015/probes/agensh-orchestration-sdk/runs/formal/t2_interface__B__r0/staging/r1/w2")

# Stand in a reference geometry implementation so report.py can be exercised
# even if w1's geometry.py has not landed yet.
from src import geometry as real_geometry
from src import report


def area(shape):
    if shape["kind"] == "rect":
        return shape["width"] * shape["height"]
    if shape["kind"] == "circle":
        return math.pi * shape["radius"] ** 2
    raise ValueError(f"unknown kind: {shape['kind']!r}")


def perimeter(shape):
    if shape["kind"] == "rect":
        return 2 * (shape["width"] + shape["height"])
    if shape["kind"] == "circle":
        return 2 * math.pi * shape["radius"]
    raise ValueError(f"unknown kind: {shape['kind']!r}")


# Point report.py's imported names at the reference impl for the test run.
report.area = area
report.perimeter = perimeter

rect = {"kind": "rect", "width": 3, "height": 4}
circle = {"kind": "circle", "radius": 1}

got_rect = report.describe(rect)
got_circle = report.describe(circle)

assert got_rect == "rect: area=12.00 perimeter=14.00", got_rect
assert got_circle == "circle: area=3.14 perimeter=6.28", got_circle

try:
    report.describe({"kind": "hexagon"})
except ValueError as exc:
    print("ValueError propagated:", exc)
else:
    raise AssertionError("expected ValueError for unknown kind")

print("rect   ->", got_rect)
print("circle ->", got_circle)

# If w1's real geometry.py has landed, check the real integration too.
try:
    real = report.describe(rect)
    print("real geometry.py ->", real)
except NotImplementedError:
    print("real geometry.py -> still a stub (w1 not landed)")

print("OK")
