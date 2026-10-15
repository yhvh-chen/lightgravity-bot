import math, sys
sys.path.insert(0, "src")
from geometry import area, perimeter

assert area({"kind": "rect", "width": 3, "height": 4}) == 12
assert perimeter({"kind": "rect", "width": 3, "height": 4}) == 14
assert math.isclose(area({"kind": "circle", "radius": 2}), math.pi * 4)
assert math.isclose(perimeter({"kind": "circle", "radius": 2}), 4 * math.pi)
for f in (area, perimeter):
    try:
        f({"kind": "hex"})
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
print("geometry OK")
