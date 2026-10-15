"""Statistics helpers."""


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
