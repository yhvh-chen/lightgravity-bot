import math
from src import stats


def expect_valueerror(fn, *a):
    try:
        fn(*a)
    except ValueError:
        return True
    return False


# mean / median preserved
assert stats.mean([1, 2, 3]) == 2
assert stats.mean([2, 4]) == 3
assert stats.median([3, 1, 2]) == 2
assert stats.median([4, 1, 3, 2]) == 2.5
assert expect_valueerror(stats.mean, [])
assert expect_valueerror(stats.median, [])

# mode
assert stats.mode([1, 1, 2]) == 1
assert stats.mode([3, 3, 1, 1, 2]) == 1  # tie -> smallest
assert stats.mode([5]) == 5
assert stats.mode([2, 1, 2, 1]) == 1  # tie -> smallest
assert expect_valueerror(stats.mode, [])

# stdev (population)
assert stats.stdev([2, 4, 4, 4, 5, 5, 7, 9]) == 2.0
assert stats.stdev([1]) == 0.0
assert math.isclose(stats.stdev([1, 3]), 1.0)
assert expect_valueerror(stats.stdev, [])

# iterables / generators
assert stats.mean(iter([1, 2, 3])) == 2
assert stats.mode(x for x in [1, 1, 2]) == 1
assert stats.stdev(x for x in [2, 4, 4, 4, 5, 5, 7, 9]) == 2.0

print("ALL OK")
