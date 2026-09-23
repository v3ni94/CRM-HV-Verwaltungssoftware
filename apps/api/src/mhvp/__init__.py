"""MH Verwaltungsplattform (mhvp): API, worker and domain logic."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mhvp")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
    __version__ = "0.0.0"
