"""Statistics helpers."""


def mean(nums):
    """Return the arithmetic mean of ``nums``.

    Raises ValueError for an empty sequence.
    """
    values = list(nums)
    if not values:
        raise ValueError("mean() requires at least one value")
    return sum(values) / len(values)


def median(nums):
    """Return the median of ``nums``.

    Raises ValueError for an empty sequence. For an odd number of values the
    sorted middle value is returned; for an even number the mean of the two
    middle values is returned.
    """
    values = sorted(nums)
    if not values:
        raise ValueError("median() requires at least one value")
    n = len(values)
    mid = n // 2
    if n % 2 == 1:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2
