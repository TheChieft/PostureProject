"""
camera.py
---------
Manages webcam capture at low resolution and controlled FPS.
Target: 640x360, 8-12 FPS, no frame storage.
"""

import cv2
import time
import logging

logger = logging.getLogger(__name__)

TARGET_WIDTH = 640
TARGET_HEIGHT = 360
TARGET_FPS = 10


class Camera:
    """
    Wraps OpenCV VideoCapture with controlled resolution and frame rate.
    Frames are never written to disk.
    """

    def __init__(self, index: int = 0, width: int = TARGET_WIDTH,
                 height: int = TARGET_HEIGHT, fps: int = TARGET_FPS):
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps

        self._cap: cv2.VideoCapture | None = None
        self._frame_interval = 1.0 / fps
        self._last_frame_time = 0.0
        self._actual_fps = 0.0
        self._frame_count = 0
        self._fps_timer = time.time()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> bool:
        """Open the capture device and apply resolution settings."""
        self._cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            # Fallback: try without backend hint
            self._cap = cv2.VideoCapture(self.index)

        if not self._cap.isOpened():
            logger.error("Cannot open camera index %d", self.index)
            return False

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)
        # Reduce internal buffer to minimise latency
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info("Camera opened: %dx%d (requested %dx%d)",
                    actual_w, actual_h, self.width, self.height)
        return True

    def close(self):
        """Release the capture device."""
        if self._cap and self._cap.isOpened():
            self._cap.release()
            logger.info("Camera released.")
        self._cap = None

    # ------------------------------------------------------------------
    # Frame access
    # ------------------------------------------------------------------

    def read_frame(self):
        """
        Return (frame, timestamp) respecting the target FPS interval.
        Returns (None, None) if the interval has not elapsed or capture fails.
        """
        now = time.monotonic()
        elapsed = now - self._last_frame_time
        if elapsed < self._frame_interval:
            return None, None

        if self._cap is None or not self._cap.isOpened():
            return None, None

        ret, frame = self._cap.read()
        if not ret or frame is None:
            logger.warning("Failed to read frame from camera.")
            return None, None

        self._last_frame_time = now
        self._update_fps()
        return frame, now

    def _update_fps(self):
        self._frame_count += 1
        elapsed = time.monotonic() - self._fps_timer
        if elapsed >= 1.0:
            self._actual_fps = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_timer = time.monotonic()

    @property
    def actual_fps(self) -> float:
        return round(self._actual_fps, 1)

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()
