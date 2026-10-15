"""Reference final solution for T3 (not visible to the model)."""
import math


def mean(nums):
    if not nums:
        raise ValueError("mean of empty sequence")
    return sum(nums) / len(nums)


def median(nums):
    if not nums:
        raise ValueError("median of empty sequence")
    ordered = sorted(nums)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def mode(nums):
    if not nums:
        raise ValueError("mode of empty sequence")
    counts = {}
    for value in nums:
        counts[value] = counts.get(value, 0) + 1
    best = max(counts.values())
    return min(value for value, count in counts.items() if count == best)


def stdev(nums):
    if not nums:
        raise ValueError("stdev of empty sequence")
    mu = mean(nums)
    variance = sum((x - mu) ** 2 for x in nums) / len(nums)
    return math.sqrt(variance)
