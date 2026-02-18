"""
state_machine.py
----------------
Tracks posture state transitions based on the smoothed score,
a baseline, and time thresholds.

States
------
GREEN  : score ≤ baseline_yellow_threshold   (good posture)
YELLOW : score > yellow for > 15 s           (warning)
RED    : score > red for > 30 s              (alert)

Hysteresis: To return from YELLOW/RED → GREEN the score must
drop back below the Green threshold for at least 3 seconds.
"""

from __future__ import annotations
import time
import logging
from enum import Enum, auto

logger = logging.getLogger(__name__)

# Time thresholds (seconds)
YELLOW_TIME_THRESHOLD = 15.0
RED_TIME_THRESHOLD = 30.0
RECOVERY_TIME = 3.0   # Must be good for this long to reset to GREEN


class PostureState(Enum):
    GREEN = auto()
    YELLOW = auto()
    RED = auto()


class StateMachine:
    """
    Monitors score vs. baseline and emits state transitions.
    All threshold logic is here; UI and logger just consume the state.
    """

    # Relative thresholds above baseline
    YELLOW_DELTA = 0.15   # baseline + 15 %
    RED_DELTA = 0.30      # baseline + 30 %

    def __init__(self):
        self._baseline: float | None = None
        self._yellow_threshold: float | None = None
        self._red_threshold: float | None = None

        self.state = PostureState.GREEN
        self._bad_start: float | None = None      # When score first went "bad"
        self._good_start: float | None = None     # When score first came back "good"

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_baseline(self, baseline: float):
        """
        Set baseline from calibration output and compute thresholds.
        """
        self._baseline = baseline
        self._yellow_threshold = baseline * (1.0 + self.YELLOW_DELTA)
        self._red_threshold = baseline * (1.0 + self.RED_DELTA)
        self.state = PostureState.GREEN
        self._bad_start = None
        self._good_start = None
        logger.info(
            "Baseline=%.4f  Yellow>=%.4f  Red>=%.4f",
            baseline, self._yellow_threshold, self._red_threshold,
        )

    @property
    def is_calibrated(self) -> bool:
        return self._baseline is not None

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, score: float) -> PostureState:
        """
        Feed a new smoothed score and return the current state.
        Must be called after set_baseline().
        """
        if not self.is_calibrated:
            return PostureState.GREEN

        now = time.monotonic()
        is_bad = score >= self._yellow_threshold  # type: ignore[operator]

        if is_bad:
            self._good_start = None
            if self._bad_start is None:
                self._bad_start = now
            bad_duration = now - self._bad_start

            if score >= self._red_threshold and bad_duration >= RED_TIME_THRESHOLD:   # type: ignore[operator]
                new_state = PostureState.RED
            elif bad_duration >= YELLOW_TIME_THRESHOLD:
                new_state = PostureState.YELLOW
            else:
                new_state = self.state  # Keep current while accumulating time
        else:
            # Score is good — apply hysteresis
            self._bad_start = None
            if self.state == PostureState.GREEN:
                self._good_start = None
                new_state = PostureState.GREEN
            else:
                if self._good_start is None:
                    self._good_start = now
                good_duration = now - self._good_start
                if good_duration >= RECOVERY_TIME:
                    new_state = PostureState.GREEN
                    self._good_start = None
                    logger.info("State → GREEN (recovered)")
                else:
                    new_state = self.state  # Hold previous while recovering

        if new_state != self.state:
            logger.info("State: %s → %s  (score=%.4f)",
                        self.state.name, new_state.name, score)
            self.state = new_state

        return self.state
