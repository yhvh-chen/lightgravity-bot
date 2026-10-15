from src.stats import mean, median

assert mean([1, 2, 3]) == 2
assert mean([2]) == 2
assert mean([1, 2]) == 1.5
assert median([1, 2, 3]) == 2
assert median([3, 1, 2]) == 2
assert median([1, 2, 3, 4]) == 2.5
assert median([5]) == 5
assert median((4, 1, 3, 2)) == 2.5

for fn in (mean, median):
    try:
        fn([])
    except ValueError:
        pass
    else:
        raise AssertionError(f"{fn.__name__}([]) did not raise ValueError")

print("ok")
