"""
logger.py
---------
Writes posture metrics to a rotating CSV log file.
No frames or images are stored — text data only.

CSV columns:
  timestamp   : ISO-8601 datetime string
  score       : EMA-smoothed posture score
  state       : GREEN / YELLOW / RED
  fps         : actual camera FPS at sample time
  hf          : head-forward displacement
  neck_angle  : neck angle in degrees
"""

from __future__ import annotations
import csv
import logging
import os
from datetime import datetime
from pathlib import Path

from state_machine import PostureState

logger = logging.getLogger(__name__)

LOG_DIR = Path("logs")
MAX_ROWS_PER_FILE = 50_000   # Rotate after ~50 k rows (~8 h at 2 Hz)

_FIELDNAMES = [
    "timestamp", "score", "state", "fps", "hf", "neck_angle"
]


class PostureLogger:
    """
    Appends one row per sample to a date-stamped CSV file.
    Automatically rotates when MAX_ROWS_PER_FILE is reached.
    """

    def __init__(self, log_dir: Path = LOG_DIR):
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._file = None
        self._writer = None
        self._row_count = 0
        self._current_path: Path | None = None
        self._open_file()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(self,
            score: float,
            state: PostureState,
            fps: float,
            hf: float,
            neck_angle_deg: float):
        """Write one CSV row."""
        if self._writer is None:
            return

        row = {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "score": round(score, 5),
            "state": state.name,
            "fps": round(fps, 1),
            "hf": round(hf, 5),
            "neck_angle": round(neck_angle_deg, 2),
        }
        self._writer.writerow(row)
        self._row_count += 1

        # Flush every 10 rows to avoid data loss without hammering disk
        if self._row_count % 10 == 0:
            self._file.flush()

        if self._row_count >= MAX_ROWS_PER_FILE:
            self._rotate()

    def close(self):
        """Flush and close the current log file."""
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = None
            self._writer = None
            logger.info("PostureLogger closed: %s", self._current_path)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _open_file(self):
        """Open a new dated CSV file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._current_path = self._log_dir / f"posture_{timestamp}.csv"
        self._file = self._current_path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=_FIELDNAMES)
        self._writer.writeheader()
        self._row_count = 0
        logger.info("PostureLogger writing to: %s", self._current_path)

    def _rotate(self):
        """Close the current file and open a fresh one."""
        logger.info("Rotating log file after %d rows.", self._row_count)
        self.close()
        self._open_file()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
