"""Statistics helpers for computing simple summary measures."""


def mean(nums):
    """Return the arithmetic mean of ``nums``.

    Raises ``ValueError`` if ``nums`` is empty.
    """
    if not nums:
        raise ValueError("mean() arg is an empty sequence")
    return sum(nums) / len(nums)


def median(nums):
    """Return the median of ``nums``.

    For an odd-length sequence this is the middle value of the sorted
    sequence; for an even-length sequence it is the average of the two
    middle values.  Raises ``ValueError`` if ``nums`` is empty.
    """
    if not nums:
        raise ValueError("median() arg is an empty sequence")
    ordered = sorted(nums)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2
