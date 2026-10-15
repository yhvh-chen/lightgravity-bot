"""Statistics helpers."""


def mean(nums):
    """Return the arithmetic mean of nums.

    Raises ValueError if nums is empty.
    """
    values = list(nums)
    if not values:
        raise ValueError("mean() arg is an empty sequence")
    return sum(values) / len(values)


def median(nums):
    """Return the median of nums.

    Raises ValueError if nums is empty. Does not mutate the input.
    """
    values = list(nums)
    if not values:
        raise ValueError("median() arg is an empty sequence")
    values.sort()
    mid = len(values) // 2
    if len(values) % 2 == 1:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2
