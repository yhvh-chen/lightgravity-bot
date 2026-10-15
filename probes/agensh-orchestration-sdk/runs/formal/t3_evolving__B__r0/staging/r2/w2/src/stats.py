"""Statistics helpers."""


def mean(nums):
    """Return the arithmetic mean of ``nums``.

    Raises ``ValueError`` if ``nums`` is empty.
    """
    nums = list(nums)
    if not nums:
        raise ValueError("mean() requires at least one value")
    return sum(nums) / len(nums)


def median(nums):
    """Return the median of ``nums``.

    Raises ``ValueError`` if ``nums`` is empty. For an odd number of
    values the middle one of the sorted sequence is returned; for an
    even number the average of the two middle values is returned.
    """
    nums = sorted(nums)
    if not nums:
        raise ValueError("median() requires at least one value")
    n = len(nums)
    mid = n // 2
    if n % 2 == 1:
        return nums[mid]
    return (nums[mid - 1] + nums[mid]) / 2
