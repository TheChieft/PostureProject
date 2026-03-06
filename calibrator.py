"""
calibrator.py
-------------
Drives the 10-second calibration phase.

Responsibilities:
- Collect PostureResult objects for CALIBRATION_SECONDS
- Compute the mean smoothed score as the baseline
- Provide a progress ratio [0.0 – 1.0] for UI progress display
"""

from __future__ import annotations
import time
import logging
from typing import Callable

from posture import PostureResult

logger = logging.getLogger(__name__)

CALIBRATION_SECONDS = 10.0
MIN_SAMPLES = 5   # Need at least this many valid frames to compute baseline


class Calibrator:
    """
    Collects posture score samples during the calibration window and
    returns a baseline score when the window expires.

    Usage:
        cal = Calibrator()
        cal.start()
        while not cal.is_done:
            result = scorer.compute(landmarks)
            if result:
                cal.add_sample(result)
        baseline = cal.baseline  # available when is_done
    """

    def __init__(self, duration: float = CALIBRATION_SECONDS,
                 on_complete: Callable[[float], None] | None = None):
        self.duration = duration
        self.on_complete = on_complete

        self._start_time: float | None = None
        self._samples: list[float] = []
        self._baseline: float | None = None
        self._done = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Begin the calibration window."""
        self._start_time = time.monotonic()
        self._samples = []
        self._baseline = None
        self._done = False
        logger.info("Calibration started (%.0fs window).", self.duration)

    def add_sample(self, result: PostureResult):
        """Feed a valid PostureResult into the accumulator."""
        if self._done or self._start_time is None:
            return
        if not result.visibility_ok:
            return

        self._samples.append(result.smoothed_score)
        elapsed = time.monotonic() - self._start_time

        if elapsed >= self.duration:
            self._finish()

    def reset(self):
        """Restart calibration from scratch."""
        self._done = False
        self._baseline = None
        self._samples = []
        self._start_time = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_started(self) -> bool:
        return self._start_time is not None

    @property
    def is_done(self) -> bool:
        return self._done

    @property
    def progress(self) -> float:
        """Fraction of calibration elapsed: 0.0 → 1.0."""
        if self._start_time is None:
            return 0.0
        if self._done:
            return 1.0
        elapsed = time.monotonic() - self._start_time
        return min(elapsed / self.duration, 1.0)

    @property
    def baseline(self) -> float | None:
        """The computed baseline, or None until calibration finishes."""
        return self._baseline

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _finish(self):
        if len(self._samples) < MIN_SAMPLES:
            logger.warning(
                "Calibration finished with too few samples (%d < %d). "
                "Using default baseline 0.1.",
                len(self._samples), MIN_SAMPLES
            )
            self._baseline = 0.1
        else:
            import statistics
            self._baseline = statistics.mean(self._samples)
            logger.info(
                "Calibration done. %d samples, baseline=%.4f",
                len(self._samples), self._baseline
            )

        self._done = True
        if self.on_complete:
            self.on_complete(self._baseline)
