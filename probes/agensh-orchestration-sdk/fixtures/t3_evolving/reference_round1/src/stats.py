"""Reference round-1-only solution for T3 (not visible; passes stage 1, fails stage 2)."""


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
