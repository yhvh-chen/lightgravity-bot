"""Statistics helpers (initial stub — not implemented)."""


def mean(nums):
    nums = list(nums)
    if not nums:
        raise ValueError("mean() arg is an empty sequence")
    return sum(nums) / len(nums)


def median(nums):
    raise NotImplementedError
