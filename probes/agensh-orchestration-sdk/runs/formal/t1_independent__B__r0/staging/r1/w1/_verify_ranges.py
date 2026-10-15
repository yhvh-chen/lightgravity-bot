from src.ranges import clamp, in_range

# clamp spec: <lo -> lo, >hi -> hi, else value
assert clamp(-5, 0, 10) == 0
assert clamp(0, 0, 10) == 0
assert clamp(5, 0, 10) == 5
assert clamp(10, 0, 10) == 10
assert clamp(99, 0, 10) == 10
# floats and negative ranges
assert clamp(-1.5, -1.0, 1.0) == -1.0
assert clamp(1.5, -1.0, 1.0) == 1.0
assert clamp(2, -3, -2) == -2
# inverted / degenerate range: spec is literal, lo check wins
assert clamp(5, 10, 0) == 10

# in_range spec: lo <= value <= hi inclusive
assert in_range(0, 0, 10) is True
assert in_range(10, 0, 10) is True
assert in_range(5, 0, 10) is True
assert in_range(-1, 0, 10) is False
assert in_range(11, 0, 10) is False
assert in_range(2, 2, 2) is True
assert in_range(-2, -3, -2) is True

# bool return type
assert isinstance(in_range(5, 0, 10), bool)

# no NotImplementedError remains
import inspect
assert "NotImplementedError" not in inspect.getsource(clamp)
assert "NotImplementedError" not in inspect.getsource(in_range)

print("all range checks passed")
