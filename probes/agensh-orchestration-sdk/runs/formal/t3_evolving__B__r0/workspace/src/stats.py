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


def mode(nums):
    """Return the most frequently occurring value in ``nums``.

    Raises ``ValueError`` if ``nums`` is empty. If several values share
    the highest count the smallest of them is returned.
    """
    nums = list(nums)
    if not nums:
        raise ValueError("mode() requires at least one value")
    counts = {}
    for value in nums:
        counts[value] = counts.get(value, 0) + 1
    best_count = max(counts.values())
    return min(value for value, count in counts.items() if count == best_count)


def stdev(nums):
    """Return the population standard deviation of ``nums``.

    Raises ``ValueError`` if ``nums`` is empty. The variance is the mean
    of the squared deviations from the arithmetic mean (i.e. divided by
    ``n``), and the standard deviation is its square root.
    """
    nums = list(nums)
    if not nums:
        raise ValueError("stdev() requires at least one value")
    n = len(nums)
    mu = sum(nums) / n
    variance = sum((x - mu) ** 2 for x in nums) / n
    return variance ** 0.5
