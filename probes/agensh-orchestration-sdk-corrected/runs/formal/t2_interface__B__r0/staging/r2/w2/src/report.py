"""Report rendering (initial stub — depends on geometry)."""
from .geometry import area, perimeter


def describe(shape):
    """Render a human-readable description of ``shape``.

    Uses :func:`geometry.area` and :func:`geometry.perimeter` so the numeric
    contract stays owned by the geometry module; an unknown ``kind`` raises
    ``ValueError`` which propagates unchanged.
    """
    return (
        f"{shape['kind']}: area={area(shape):.2f} "
        f"perimeter={perimeter(shape):.2f}"
    )
