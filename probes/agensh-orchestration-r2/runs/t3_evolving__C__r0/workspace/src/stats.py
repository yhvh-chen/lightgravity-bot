"""Statistics helpers."""

import math


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
    counts = {}
    for value in nums:
        counts[value] = counts.get(value, 0) + 1
    best = None
    best_count = -1
    for value, count in counts.items():
        if count > best_count or (count == best_count and value < best):
            best = value
            best_count = count
    return best


def stdev(nums):
    if not nums:
        raise ValueError("stdev() arg is an empty sequence")
    n = len(nums)
    avg = sum(nums) / n
    variance = sum((value - avg) ** 2 for value in nums) / n
    return math.sqrt(variance)
