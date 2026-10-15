"""Statistics helpers."""

import math


def mean(nums):
    """Return the arithmetic mean of nums.

    Raises ValueError if nums is empty.
    """
    values = list(nums)
    if not values:
        raise ValueError("mean() arg is an empty sequence")
    return sum(values) / len(values)


def median(nums):
    """Return the median of nums.

    Raises ValueError if nums is empty. Does not mutate the input.
    """
    values = list(nums)
    if not values:
        raise ValueError("median() arg is an empty sequence")
    values.sort()
    mid = len(values) // 2
    if len(values) % 2 == 1:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def mode(nums):
    """Return the most frequent value in nums.

    Raises ValueError if nums is empty. Ties are broken by returning the
    smallest of the most frequent values.
    """
    values = list(nums)
    if not values:
        raise ValueError("mode() arg is an empty sequence")
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    highest = max(counts.values())
    return min(value for value, count in counts.items() if count == highest)


def stdev(nums):
    """Return the population standard deviation of nums.

    Raises ValueError if nums is empty. The variance is computed by
    dividing by n (population variance).
    """
    values = list(nums)
    if not values:
        raise ValueError("stdev() arg is an empty sequence")
    avg = sum(values) / len(values)
    variance = sum((value - avg) ** 2 for value in values) / len(values)
    return math.sqrt(variance)
