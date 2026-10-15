"""Statistics helpers."""

import math


def mean(nums):
    data = list(nums)
    if not data:
        raise ValueError("mean() arg is an empty sequence")
    return sum(data) / len(data)


def median(nums):
    data = sorted(nums)
    if not data:
        raise ValueError("median() arg is an empty sequence")
    n = len(data)
    mid = n // 2
    if n % 2 == 1:
        return data[mid]
    return (data[mid - 1] + data[mid]) / 2


def mode(nums):
    data = list(nums)
    if not data:
        raise ValueError("mode() arg is an empty sequence")
    counts = {}
    for value in data:
        counts[value] = counts.get(value, 0) + 1
    best = max(counts.values())
    return min(value for value, count in counts.items() if count == best)


def stdev(nums):
    data = list(nums)
    if not data:
        raise ValueError("stdev() arg is an empty sequence")
    n = len(data)
    avg = sum(data) / n
    variance = sum((value - avg) ** 2 for value in data) / n
    return math.sqrt(variance)
