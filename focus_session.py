"""
focus_session.py
----------------
Work / break session timer (Pomodoro-style).

Thread-safe. Contains no UI code.
Call tick() periodically to fire automatic phase transitions.
"""
from __future__ import annotations
import threading
import time
from enum import Enum
from typing import Callable


class Phase(Enum):
    IDLE  = "idle"
    WORK  = "work"
    BREAK = "break"


# (display_label, work_seconds, break_seconds)
PRESETS: list[tuple[str, int, int]] = [
    ("30 min / 2.5 min",  30 * 60,   150),   # 150 s = 2.5 min
    ("45 min / 5 min",    45 * 60,   5 * 60),
    ("90 min / 10 min",   90 * 60,  10 * 60),
    ("3 h  / 20 min",    180 * 60,  20 * 60),
]


class FocusSession:
    """
    Work / break session timer.  All methods are thread-safe.

    on_phase_change is invoked (outside the internal lock) whenever
    the active phase changes.  It receives the new Phase value.
    """

    def __init__(self, on_phase_change: Callable[[Phase], None] | None = None):
        self._cb = on_phase_change
        self._lock = threading.Lock()

        self._phase = Phase.IDLE
        self._work_secs  = 25 * 60
        self._break_secs =  5 * 60

        self._phase_start: float | None = None        # monotonic, None when paused
        self._elapsed_before_pause: float = 0.0       # accumulated elapsed in current phase

    # ── Control ───────────────────────────────────────────────────────

    def start(self, work_secs: int, break_secs: int) -> None:
        """Begin a new session (always starts in WORK phase)."""
        with self._lock:
            self._work_secs  = work_secs
            self._break_secs = break_secs
            self._phase      = Phase.WORK
            self._phase_start = time.monotonic()
            self._elapsed_before_pause = 0.0
        self._fire(Phase.WORK)

    def stop(self) -> None:
        """End the session and return to IDLE."""
        with self._lock:
            self._phase       = Phase.IDLE
            self._phase_start = None
            self._elapsed_before_pause = 0.0
        self._fire(Phase.IDLE)

    def pause(self) -> None:
        """Freeze the timer without ending the session."""
        with self._lock:
            if self._phase == Phase.IDLE or self._phase_start is None:
                return
            self._elapsed_before_pause += time.monotonic() - self._phase_start
            self._phase_start = None

    def resume(self) -> None:
        """Unfreeze the timer."""
        with self._lock:
            if self._phase == Phase.IDLE or self._phase_start is not None:
                return
            self._phase_start = time.monotonic()

    def skip(self) -> None:
        """Jump immediately to the next phase (WORK→BREAK or BREAK→WORK)."""
        nxt = None
        with self._lock:
            if self._phase == Phase.IDLE:
                return
            nxt = Phase.BREAK if self._phase == Phase.WORK else Phase.WORK
            self._phase      = nxt
            self._phase_start = time.monotonic()
            self._elapsed_before_pause = 0.0
        self._fire(nxt)

    def tick(self) -> None:
        """
        Check whether the current phase has expired and advance if so.
        Call from any thread (e.g. the worker loop) at ~1 Hz.
        """
        nxt = None
        with self._lock:
            if self._phase == Phase.IDLE or self._phase_start is None:
                return   # also handles paused state
            elapsed = self._elapsed_before_pause + (time.monotonic() - self._phase_start)
            dur = self._work_secs if self._phase == Phase.WORK else self._break_secs
            if elapsed >= dur:
                nxt = Phase.BREAK if self._phase == Phase.WORK else Phase.WORK
                self._phase      = nxt
                self._phase_start = time.monotonic()
                self._elapsed_before_pause = 0.0
        if nxt is not None:
            self._fire(nxt)

    # ── Read-only properties ──────────────────────────────────────────

    @property
    def phase(self) -> Phase:
        with self._lock:
            return self._phase

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._phase != Phase.IDLE and self._phase_start is None

    @property
    def remaining_secs(self) -> float:
        with self._lock:
            if self._phase == Phase.IDLE:
                return 0.0
            dur = self._work_secs if self._phase == Phase.WORK else self._break_secs
            if self._phase_start is None:   # paused
                return max(0.0, dur - self._elapsed_before_pause)
            elapsed = self._elapsed_before_pause + (time.monotonic() - self._phase_start)
            return max(0.0, dur - elapsed)

    @property
    def progress(self) -> float:
        """Fraction of current phase elapsed: 0.0 → 1.0."""
        with self._lock:
            if self._phase == Phase.IDLE:
                return 0.0
            dur = self._work_secs if self._phase == Phase.WORK else self._break_secs
            if self._phase_start is None:   # paused
                return min(1.0, self._elapsed_before_pause / dur) if dur > 0 else 0.0
            elapsed = self._elapsed_before_pause + (time.monotonic() - self._phase_start)
            return min(1.0, elapsed / dur) if dur > 0 else 0.0

    def _fire(self, phase: Phase) -> None:
        if self._cb:
            self._cb(phase)
