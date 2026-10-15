"""Statistics helpers (implemented)."""


def mean(nums):
    """Return the arithmetic mean of *nums*.

    Raises ValueError when *nums* is empty. Works with any sized
    iterable of numbers (list or tuple), without modifying it.
    """
    if len(nums) == 0:
        raise ValueError("mean() arg is an empty sequence")
    return sum(nums) / len(nums)


def median(nums):
    """Return the median of *nums*.

    Raises ValueError when *nums* is empty. For an odd-length input the
    middle element of the sorted values is returned; for an even-length
    input the arithmetic mean of the two middle elements is returned.
    The input is never modified (a sorted copy is used).
    """
    if len(nums) == 0:
        raise ValueError("median() arg is an empty sequence")
    ordered = sorted(nums)
    n = len(ordered)
    middle = n // 2
    if n % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2
