import sys

sys.path.insert(0, "src")
import stats  # noqa: E402

assert stats.mean([1, 2, 3]) == 2
assert stats.mean([2, 4]) == 3
assert stats.mean([5]) == 5
assert stats.mean([1, 2]) == 1.5
assert stats.mean((1, 2, 3)) == 2  # accepts tuples

for fn in (stats.mean, stats.median):
    try:
        fn([])
    except ValueError:
        pass
    else:
        raise AssertionError(f"{fn.__name__} did not raise on empty")

assert stats.median([3, 1, 2]) == 2
assert stats.median([1]) == 1
assert stats.median([5, 1, 3, 2, 4]) == 3

assert stats.median([1, 2, 3, 4]) == 2.5
assert stats.median([4, 3, 2, 1]) == 2.5
assert stats.median([4, 2]) == 3

data = [3, 1, 2]
stats.median(data)
assert data == [3, 1, 2], data

print("ALL OK")
