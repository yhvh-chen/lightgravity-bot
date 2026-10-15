import sys

sys.path.insert(0, "/tmp/lightgravity-worktrees/agensh-sdk-20261015/probes/agensh-orchestration-sdk/runs/formal/t1_independent__C__r0/staging/r1/w1")

from src.slugs import slugify

cases = [
    ("Hello World", "hello-world"),
    ("Hello, World!", "hello-world"),
    ("  Multiple   Spaces  ", "multiple-spaces"),
    ("Already-Slugged", "already-slugged"),
    ("--Edge--", "edge"),
    ("", ""),
    ("...", ""),
    ("a_b_c", "a-b-c"),
    ("CamelCase", "camelcase"),
    ("UPPER lower 123", "upper-lower-123"),
    ("MiXeD\tTabs\nAnd Spaces", "mixed-tabs-and-spaces"),
    ("123", "123"),
    ("a---b", "a-b"),
]
for inp, want in cases:
    got = slugify(inp)
    assert got == want, (inp, got, want)
print("all", len(cases), "cases passed")
