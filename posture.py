"""
posture.py
----------
Computes the composite Posture Score S from PostureLandmarks.

Score formula
-------------
S = w1 * HF + w2 * neck_angle_deg

Where:
  HF           = (mid_ear_x - mid_shoulder_x) / shoulder_width
                 Positive → head forward of shoulders (bad)
  neck_angle   = angle between the neck vector (shoulder→ear midpoint)
                 and the vertical axis, in degrees.
                 Positive → head tilted forward (bad)

EMA smoothing:
  smoothed_S(t) = alpha * S(t) + (1 - alpha) * smoothed_S(t-1)
"""

from __future__ import annotations
import math
import logging
from dataclasses import dataclass

from pose import PostureLandmarks

logger = logging.getLogger(__name__)

# Default weights
W1 = 0.5   # Head-forward contribution
W2 = 0.5   # Neck-angle contribution
EMA_ALPHA = 0.3


@dataclass
class PostureResult:
    raw_score: float        # Unsmoothed composite score
    smoothed_score: float   # EMA-smoothed score
    hf: float               # Head-forward displacement (normalised)
    neck_angle_deg: float   # Degrees from vertical
    visibility_ok: bool


class PostureScorer:
    """
    Stateful scorer that maintains an EMA-smoothed posture score.
    """

    def __init__(self,
                 w1: float = W1,
                 w2: float = W2,
                 ema_alpha: float = EMA_ALPHA):
        self.w1 = w1
        self.w2 = w2
        self.ema_alpha = ema_alpha
        self._smoothed: float | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(self, landmarks: PostureLandmarks) -> PostureResult | None:
        """
        Compute posture metrics from landmarks.
        Returns None if landmarks have poor visibility.
        """
        if not landmarks.visibility_ok:
            return None

        hf = self._head_forward(landmarks)
        angle = self._neck_angle(landmarks)
        raw = self.w1 * abs(hf) + self.w2 * (angle / 90.0)

        # EMA
        if self._smoothed is None:
            self._smoothed = raw
        else:
            self._smoothed = (self.ema_alpha * raw
                              + (1.0 - self.ema_alpha) * self._smoothed)

        return PostureResult(
            raw_score=raw,
            smoothed_score=self._smoothed,
            hf=hf,
            neck_angle_deg=angle,
            visibility_ok=True,
        )

    def reset(self):
        """Reset EMA state (call after calibration resets)."""
        self._smoothed = None

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _head_forward(lm: PostureLandmarks) -> float:
        """
        HF = (mid_ear_x - mid_shoulder_x) / shoulder_width
        Normalised coordinates → shoulder_width prevents scale issues.
        """
        mid_ear_x = (lm.left_ear[0] + lm.right_ear[0]) / 2.0
        mid_shoulder_x = (lm.left_shoulder[0] + lm.right_shoulder[0]) / 2.0
        shoulder_width = abs(lm.left_shoulder[0] - lm.right_shoulder[0])

        if shoulder_width < 1e-6:
            return 0.0

        return (mid_ear_x - mid_shoulder_x) / shoulder_width

    @staticmethod
    def _neck_angle(lm: PostureLandmarks) -> float:
        """
        Angle between the neck vector (mid_shoulder → mid_ear)
        and the upward vertical, in degrees.

        Note: In normalised MediaPipe coords y increases downward,
        so we negate y to point "up" for the angle calculation.
        """
        mid_ear_x = (lm.left_ear[0] + lm.right_ear[0]) / 2.0
        mid_ear_y = (lm.left_ear[1] + lm.right_ear[1]) / 2.0
        mid_shoulder_x = (lm.left_shoulder[0] + lm.right_shoulder[0]) / 2.0
        mid_shoulder_y = (lm.left_shoulder[1] + lm.right_shoulder[1]) / 2.0

        # Vector from shoulder midpoint to ear midpoint
        dx = mid_ear_x - mid_shoulder_x
        dy = -(mid_ear_y - mid_shoulder_y)   # flip y so up = positive

        neck_len = math.hypot(dx, dy)
        if neck_len < 1e-6:
            return 0.0

        # Vertical unit vector pointing up: (0, 1)
        # cos(theta) = dot(neck_vec, vertical) / neck_len
        cos_theta = dy / neck_len
        cos_theta = max(-1.0, min(1.0, cos_theta))  # clamp for safety
        angle_rad = math.acos(cos_theta)
        return math.degrees(angle_rad)
