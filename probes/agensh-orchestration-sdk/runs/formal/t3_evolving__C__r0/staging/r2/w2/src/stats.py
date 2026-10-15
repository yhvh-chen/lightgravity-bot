"""Statistics helpers.

Contract:
- ``mean(nums)``: arithmetic mean; raises ``ValueError`` on empty input.
- ``median(nums)``: middle value of the sorted data (average of the two
  middle values for even-length input); raises ``ValueError`` on empty input.
"""

__all__ = ["mean", "median"]


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
