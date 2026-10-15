from src.slugs import slugify

cases = [
    ("Hello, World!", "hello-world"),
    ("  Foo   Bar  ", "foo-bar"),
    ("Already-Slugged", "already-slugged"),
    ("A__B", "a-b"),
    ("!!!", ""),
    ("", ""),
    ("CamelCase123", "camelcase123"),
    ("Foo...bar", "foo-bar"),
    ("--foo--", "foo"),
    ("a1b2c3", "a1b2c3"),
    ("Hello, World!  ", "hello-world"),
]

for src, want in cases:
    got = slugify(src)
    assert got == want, f"slugify({src!r}) = {got!r}, want {want!r}"
print("all slugify checks passed")
