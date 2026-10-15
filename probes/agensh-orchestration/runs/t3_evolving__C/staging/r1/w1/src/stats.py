"""Statistics helpers."""


def mean(nums):
    """Return the arithmetic mean of a non-empty sequence of numbers."""
    if not nums:
        raise ValueError("mean() requires a non-empty sequence")
    return sum(nums) / len(nums)


def median(nums):
    """Return the median of a non-empty sequence of numbers."""
    if not nums:
        raise ValueError("median() requires a non-empty sequence")

    ordered = sorted(nums)
    middle = len(ordered) // 2

    if len(ordered) % 2 == 1:
        return ordered[middle]

    return (ordered[middle - 1] + ordered[middle]) / 2
