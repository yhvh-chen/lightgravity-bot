"""Statistics helpers."""

import math


def mean(nums):
    nums = list(nums)
    if not nums:
        raise ValueError("mean() arg is an empty sequence")
    return sum(nums) / len(nums)


def median(nums):
    raise NotImplementedError


def mode(nums):
    nums = list(nums)
    if not nums:
        raise ValueError("mode() arg is an empty sequence")
    counts = {}
    for n in nums:
        counts[n] = counts.get(n, 0) + 1
    best = max(counts.values())
    return min(n for n, c in counts.items() if c == best)


def stdev(nums):
    nums = list(nums)
    if not nums:
        raise ValueError("stdev() arg is an empty sequence")
    m = sum(nums) / len(nums)
    var = sum((x - m) ** 2 for x in nums) / len(nums)
    return math.sqrt(var)
