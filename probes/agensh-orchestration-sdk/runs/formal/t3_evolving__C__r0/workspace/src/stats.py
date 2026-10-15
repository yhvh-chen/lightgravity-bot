"""Statistics helpers.

Contract:
- ``mean(nums)``: arithmetic mean; raises ``ValueError`` on empty input.
- ``median(nums)``: middle value of the sorted data (average of the two
  middle values for even-length input); raises ``ValueError`` on empty input.
- ``mode(nums)``: most frequent value, ties broken by choosing the smallest
  such value; raises ``ValueError`` on empty input.
- ``stdev(nums)``: population standard deviation (``sqrt`` of the variance
  computed by dividing by ``n``); raises ``ValueError`` on empty input.
"""

import math

__all__ = ["mean", "median", "mode", "stdev"]


def mean(nums):
    """Return the arithmetic mean of ``nums``.

    Raises ValueError when ``nums`` is empty.
    """
    values = list(nums)
    if not values:
        raise ValueError("mean() requires a non-empty sequence")
    return sum(values) / len(values)


def median(nums):
    """Return the median of ``nums``.

    Raises ValueError when ``nums`` is empty. Odd-length input returns the
    middle element of the sorted data; even-length input returns the average
    of the two middle elements.
    """
    values = list(nums)
    if not values:
        raise ValueError("median() requires a non-empty sequence")
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def mode(nums):
    """Return the most frequent value in ``nums``.

    Ties are broken by returning the smallest of the tied values. Raises
    ValueError when ``nums`` is empty.
    """
    values = list(nums)
    if not values:
        raise ValueError("mode() requires a non-empty sequence")
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    # max count wins; ties resolved towards the smallest value.
    return min(counts, key=lambda value: (-counts[value], value))


def stdev(nums):
    """Return the population standard deviation of ``nums``.

    The variance is computed by dividing the sum of squared deviations by
    ``n`` (population variance), and the standard deviation is its square
    root. Raises ValueError when ``nums`` is empty.
    """
    values = list(nums)
    if not values:
        raise ValueError("stdev() requires a non-empty sequence")
    n = len(values)
    avg = sum(values) / n
    variance = sum((value - avg) ** 2 for value in values) / n
    return math.sqrt(variance)
