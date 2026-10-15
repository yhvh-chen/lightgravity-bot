"""Statistics helpers."""


def mean(nums):
    """Return the arithmetic mean of a non-empty sequence of numbers."""
    if len(nums) == 0:
        raise ValueError("mean() requires a non-empty sequence")
    return sum(nums) / len(nums)


def median(nums):
    """Return the median of a non-empty sequence of numbers."""
    if len(nums) == 0:
        raise ValueError("median() requires a non-empty sequence")

    ordered = sorted(nums)
    n = len(ordered)
    midpoint = n // 2

    if n % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2
