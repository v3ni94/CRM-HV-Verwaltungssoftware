"""MH Verwaltungsplattform (mhvp): API, worker and domain logic."""

import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _read_version() -> str:
    """Single source: the ``VERSION`` file of the repository (GAI-111, CLAUDE.md section 10).

    Lookup: ``MHVP_VERSION_FILE``, the repository root of a source checkout, ``/app/VERSION``
    (image). Fallback: package metadata, then ``0.0.0``. The versions in ``pyproject.toml`` and
    ``package.json`` are no source (``scripts/bump_version.py`` keeps them in line).
    """
    candidates = [os.environ.get("MHVP_VERSION_FILE", "")]
    here = Path(__file__).resolve()
    candidates += [str(p / "VERSION") for p in here.parents[:5]] + ["/app/VERSION"]
    for name in candidates:
        if not name:
            continue
        try:
            text = Path(name).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text and text[0].isdigit():
            return text
    try:
        return version("mhvp")
    except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
        return "0.0.0"


__version__ = _read_version()
