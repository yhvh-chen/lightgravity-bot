"""Statistics helpers."""

import math
from collections import Counter


def mean(nums):
    if not nums:
        raise ValueError("mean() arg is an empty sequence")
    return sum(nums) / len(nums)


def median(nums):
    if not nums:
        raise ValueError("median() arg is an empty sequence")
    ordered = sorted(nums)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def mode(nums):
    if not nums:
        raise ValueError("mode() arg is an empty sequence")
    counts = Counter(nums)
    top = max(counts.values())
    return min(value for value, count in counts.items() if count == top)


def stdev(nums):
    if not nums:
        raise ValueError("stdev() arg is an empty sequence")
    n = len(nums)
    avg = sum(nums) / n
    variance = sum((x - avg) ** 2 for x in nums) / n
    return math.sqrt(variance)
