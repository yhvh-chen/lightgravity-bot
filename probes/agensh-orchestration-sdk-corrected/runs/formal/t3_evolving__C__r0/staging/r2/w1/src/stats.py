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


def mode(nums):
    """Return the most frequently occurring value in ``nums``.

    Raises ValueError for an empty sequence. When several values tie for the
    highest frequency, the smallest of those values is returned.
    """
    values = list(nums)
    if not values:
        raise ValueError("mode() requires at least one value")
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    best_count = max(counts.values())
    return min(value for value, count in counts.items() if count == best_count)


def stdev(nums):
    """Return the population standard deviation of ``nums``.

    The variance is computed as the mean of the squared deviations from the
    arithmetic mean (i.e. divided by ``n``, not ``n - 1``); the result is its
    square root. Raises ValueError for an empty sequence.
    """
    values = list(nums)
    if not values:
        raise ValueError("stdev() requires at least one value")
    n = len(values)
    avg = sum(values) / n
    variance = sum((value - avg) ** 2 for value in values) / n
    # sqrt(variance) can land a hair below the exact answer when variance is a
    # perfect square (e.g. 2.25 -> 1.4999999999999998), so snap those cases.
    root = variance ** 0.5
    rounded = round(root)
    if rounded >= 0 and rounded * rounded == variance:
        return float(rounded)
    return root
