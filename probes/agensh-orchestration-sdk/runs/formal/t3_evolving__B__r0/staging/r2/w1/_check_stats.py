import math

from src.stats import mean, median, mode, stdev

# empty -> ValueError for all four
for fn in (mean, median, mode, stdev):
    try:
        fn([])
    except ValueError:
        pass
    else:
        raise AssertionError(f"{fn.__name__}([]) did not raise ValueError")

assert mean([1, 2, 3]) == 2
assert mean([1, 2]) == 1.5
assert median([3, 1, 2]) == 2
assert median([4, 1, 3, 2]) == 2.5
assert median([1]) == 1

# mode: most frequent
assert mode([1, 2, 2, 3]) == 2
# mode tie -> smallest
assert mode([1, 2, 1, 2]) == 1
assert mode([5, 5, 4, 4, 4, 5]) == 4  # 5 appears 3x? no: 5->3, 4->3 -> smallest 4
assert mode([3]) == 3
assert mode([-1, -1, 2, 2]) == -1

# stdev: population (divide by n)
assert stdev([2, 4, 4, 4, 5, 5, 7, 9]) == 2.0
assert stdev([1]) == 0.0
assert stdev([1, 3]) == 1.0
assert math.isclose(stdev([1, 2, 3]), math.sqrt(2 / 3))

# generators/iterables accepted
assert mean(iter([1, 2, 3])) == 2
assert mode(iter([1, 1, 2])) == 1
assert stdev(iter([1, 1])) == 0.0
assert median(iter([1, 2, 3, 4])) == 2.5

print("all checks passed")
