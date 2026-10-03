"""Load tolerant runtime limits for tests (regression guard that survives parallel load).

Every runtime limit keeps its purpose (a slowdown regression must still fail), but the
absolute seconds are scaled by the load factor of the machine measured in the same process:
a fixed CPU reference workload is timed once and compared with its time on an idle machine.
The factor is never below 1 (a fast machine does not tighten the limit) and capped at
MAX_FACTOR so that a real regression is still caught. MHVP_PERF_FACTOR overrides it.
"""

from __future__ import annotations

import hashlib
import os
import time

REFERENCE_IDLE_SECONDS = 0.05  # reference workload on an idle machine (generous rounding)
MAX_FACTOR = 8.0
_factor: float | None = None


def _reference_seconds() -> float:
    best = float("inf")
    for _ in range(3):  # best of three: a short load peak does not inflate the factor
        started = time.perf_counter()
        digest = b"mhvp"
        for _ in range(60_000):
            digest = hashlib.sha256(digest).digest()
        best = min(best, time.perf_counter() - started)
    return best


def load_factor() -> float:
    """Slowdown of this process versus an idle machine, between 1.0 and MAX_FACTOR."""
    global _factor
    if _factor is None:
        override = os.environ.get("MHVP_PERF_FACTOR")
        if override:
            _factor = max(1.0, float(override))
        else:
            _factor = min(MAX_FACTOR, max(1.0, _reference_seconds() / REFERENCE_IDLE_SECONDS))
    return _factor


def scaled_limit(seconds: float) -> float:
    """Absolute limit in seconds, scaled by the current load factor (measure before the run)."""
    return seconds * load_factor()
