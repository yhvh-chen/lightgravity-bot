import sys
sys.path.insert(0, ".")

from src.ranges import clamp, in_range

assert clamp(5, 0, 10) == 5
assert clamp(-1, 0, 10) == 0
assert clamp(11, 0, 10) == 10
assert clamp(0, 0, 10) == 0
assert clamp(10, 0, 10) == 10
assert clamp(2.5, 0.0, 1.0) == 1.0
assert clamp(-3, -5, -1) == -3
assert clamp("b", "a", "c") == "b"

assert in_range(5, 0, 10) is True
assert in_range(0, 0, 10) is True
assert in_range(10, 0, 10) is True
assert in_range(-1, 0, 10) is False
assert in_range(11, 0, 10) is False
assert in_range(0, 0, 0) is True
assert type(in_range(5, 0, 10)) is bool

# returns the original object when in range (no coercion)
obj = object()
assert clamp(obj, obj, obj) is obj

print("all ranges assertions passed")
