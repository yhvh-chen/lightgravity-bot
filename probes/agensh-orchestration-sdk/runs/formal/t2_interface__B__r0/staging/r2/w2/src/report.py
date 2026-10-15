"""Report rendering (initial stub — depends on geometry)."""
from .geometry import area, perimeter


def describe(shape):
    """Render a one-line human-readable description of *shape*.

    Delegates all shape math to :mod:`src.geometry` (``area`` / ``perimeter``),
    so any unsupported ``kind`` raises the ``ValueError`` defined there.
    """
    return (
        f"{shape['kind']}: "
        f"area={area(shape):.2f} perimeter={perimeter(shape):.2f}"
    )
