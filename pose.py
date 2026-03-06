"""
pose.py
-------
Thin wrapper around MediaPipe Tasks Pose Landmarker.
Extracts only the landmarks needed for posture scoring:
  - left_ear, right_ear, left_shoulder, right_shoulder

Uses the Tasks API (mediapipe >= 0.10.30).
Requires pose_landmarker_lite.task in the same directory.
Run download_model.py once to fetch the model file.
"""

from __future__ import annotations
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

logger = logging.getLogger(__name__)

# BlazePose landmark indices — same topology as legacy mp.solutions API
LEFT_EAR_IDX       = 7
RIGHT_EAR_IDX      = 8
LEFT_SHOULDER_IDX  = 11
RIGHT_SHOULDER_IDX = 12

MODEL_PATH = Path(__file__).parent / "pose_landmarker_lite.task"


@dataclass
class PostureLandmarks:
    """Normalised (0-1) 2-D coordinates of the four key landmarks."""
    left_ear: tuple[float, float]
    right_ear: tuple[float, float]
    left_shoulder: tuple[float, float]
    right_shoulder: tuple[float, float]
    visibility_ok: bool  # True when all four landmarks are sufficiently visible


class PoseDetector:
    """
    Wraps MediaPipe Tasks Pose Landmarker for single-frame landmark extraction.
    Designed for low-resolution inputs (640x360) without GPU.
    """

    VISIBILITY_THRESHOLD = 0.5

    def __init__(self,
                 min_detection_confidence: float = 0.6,
                 min_tracking_confidence: float = 0.5):
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Pose model not found at {MODEL_PATH}\n"
                "Run:  python download_model.py"
            )

        base_options = mp_python.BaseOptions(model_asset_path=str(MODEL_PATH))
        options = mp_vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.VIDEO,
            min_pose_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
            output_segmentation_masks=False,
        )
        self._landmarker = mp_vision.PoseLandmarker.create_from_options(options)
        self._start_ms = int(time.monotonic() * 1000)
        logger.info("PoseDetector initialised (Tasks API, lite model).")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, frame: np.ndarray) -> PostureLandmarks | None:
        """
        Run pose detection on a BGR frame.
        Returns PostureLandmarks or None if no pose detected.
        """
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        ts_ms = int(time.monotonic() * 1000) - self._start_ms

        result = self._landmarker.detect_for_video(mp_image, ts_ms)

        if not result.pose_landmarks:
            return None

        lms = result.pose_landmarks[0]  # first detected person

        def xy(idx: int) -> tuple[float, float]:
            lm = lms[idx]
            return (float(lm.x), float(lm.y))

        def vis(idx: int) -> float:
            lm = lms[idx]
            v = getattr(lm, "visibility", None)
            if v is None:
                v = getattr(lm, "presence", 1.0)
            return float(v) if v is not None else 1.0

        indices = [LEFT_EAR_IDX, RIGHT_EAR_IDX,
                   LEFT_SHOULDER_IDX, RIGHT_SHOULDER_IDX]
        visibility_ok = all(vis(i) >= self.VISIBILITY_THRESHOLD
                            for i in indices)

        return PostureLandmarks(
            left_ear=xy(LEFT_EAR_IDX),
            right_ear=xy(RIGHT_EAR_IDX),
            left_shoulder=xy(LEFT_SHOULDER_IDX),
            right_shoulder=xy(RIGHT_SHOULDER_IDX),
            visibility_ok=visibility_ok,
        )

    def close(self):
        """Release MediaPipe resources."""
        self._landmarker.close()
        logger.info("PoseDetector closed.")

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
