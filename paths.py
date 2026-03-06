"""
paths.py
--------
Resolves runtime file paths for both development and PyInstaller frozen modes.

When running as a PyInstaller bundle:
  - Bundled read-only assets (model file) live in sys._MEIPASS
  - Writable user data (logs) live next to the .exe (sys.executable parent)

When running as a normal Python script:
  - Both point to the directory containing this file
"""

from __future__ import annotations
import sys
from pathlib import Path


def _bundle_dir() -> Path:
    """Read-only assets directory (bundled files like the .task model)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)          # type: ignore[attr-defined]
    return Path(__file__).parent


def _data_dir() -> Path:
    """Writable user-data directory (logs, config). Next to .exe when frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def model_path() -> Path:
    """Path to pose_landmarker_lite.task."""
    return _bundle_dir() / "pose_landmarker_lite.task"


def logs_dir() -> Path:
    """Path to the logs/ directory (created on demand by PostureLogger)."""
    return _data_dir() / "logs"
