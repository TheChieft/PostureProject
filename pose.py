"""
pose.py
-------
Thin wrapper around MediaPipe Pose.
Extracts only the landmarks needed for posture scoring:
  - left_ear, right_ear, left_shoulder, right_shoulder

Returns a typed dataclass for downstream consumers.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass

import cv2
import mediapipe as mp
import numpy as np

logger = logging.getLogger(__name__)

# MediaPipe landmark indices we care about
_LM = mp.solutions.pose.PoseLandmark
LEFT_EAR_IDX = _LM.LEFT_EAR.value
RIGHT_EAR_IDX = _LM.RIGHT_EAR.value
LEFT_SHOULDER_IDX = _LM.LEFT_SHOULDER.value
RIGHT_SHOULDER_IDX = _LM.RIGHT_SHOULDER.value


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
    Wraps MediaPipe Pose for single-frame landmark extraction.
    Designed for low-resolution inputs (640x360) without GPU.
    """

    # Minimum visibility score for a landmark to be considered reliable
    VISIBILITY_THRESHOLD = 0.5

    def __init__(self,
                 min_detection_confidence: float = 0.6,
                 min_tracking_confidence: float = 0.5):
        self._mp_pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=0,          # Lite model — lowest CPU cost
            smooth_landmarks=True,
            enable_segmentation=False,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        logger.info("PoseDetector initialised (model_complexity=0).")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, frame: np.ndarray) -> PostureLandmarks | None:
        """
        Run pose detection on a BGR frame.

        Returns a PostureLandmarks instance, or None if MediaPipe fails
        to detect a pose at all.
        """
        # MediaPipe expects RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self._mp_pose.process(rgb)

        if not results.pose_landmarks:
            return None

        lms = results.pose_landmarks.landmark

        def xy(idx: int) -> tuple[float, float]:
            lm = lms[idx]
            return (float(lm.x), float(lm.y))

        def vis(idx: int) -> float:
            return float(lms[idx].visibility)

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
        self._mp_pose.close()
        logger.info("PoseDetector closed.")

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
