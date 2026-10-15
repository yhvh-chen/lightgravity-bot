"""Report rendering (initial stub — depends on geometry)."""
from .geometry import area, perimeter


def describe(shape):
    """Render a human-readable summary line for a shape dict.

    Delegates all shape-specific logic to ``geometry`` so this module stays a
    pure consumer of the shared area/perimeter interface. Unknown kinds raise
    ValueError via geometry.
    """
    return (
        f"{shape['kind']}: area={area(shape):.2f} "
        f"perimeter={perimeter(shape):.2f}"
    )
