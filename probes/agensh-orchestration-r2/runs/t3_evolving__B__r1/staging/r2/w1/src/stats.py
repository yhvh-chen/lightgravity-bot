"""Statistics helpers (initial stub — not implemented)."""


def mean(nums):
    raise NotImplementedError


def median(nums):
    data = sorted(nums)
    if not data:
        raise ValueError("median() arg is an empty sequence")
    n = len(data)
    mid = n // 2
    if n % 2 == 1:
        return data[mid]
    return (data[mid - 1] + data[mid]) / 2
