"""LightGravity Bot backend package.

Only the engineering skeleton is present at this stage (LG-002). Business
packages (store, adapter, coordinator, verify, settings) are added by their
owning tasks; see docs/08-interface-contract.md §11 for file ownership.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lightgravity-bot")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0+uninstalled"

__all__ = ["__version__"]
