"""
main.py
-------
Entry point for the PostureProject application.

Architecture
------------
main thread   → UI (tkinter overlay) — required by tkinter
worker thread → Camera + MediaPipe + scoring + logging

Flow
----
1. Worker opens camera and pose detector.
2. Calibration phase (10 s): collect baseline score → set on StateMachine.
3. Normal loop: read frame → detect landmarks → score → state → log.
4. Overlay is updated via shared state object (thread-safe writes).
5. Ctrl-C or window close triggers graceful shutdown.
"""

from __future__ import annotations
import argparse
import logging
import sys
import threading
import time

from camera import Camera
from calibrator import Calibrator
from logger import PostureLogger
from pose import PoseDetector
from posture import PostureScorer
from state_machine import StateMachine, PostureState
from ui_overlay import OverlayWindow

# ------------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
_log = logging.getLogger("main")

# ------------------------------------------------------------------
# Shared state between worker and UI thread
# ------------------------------------------------------------------
_stop_event = threading.Event()


def worker_loop(overlay: OverlayWindow,
                camera_index: int,
                debug: bool,
                preview: bool = False):
    """
    Runs in a background thread.
    Owns Camera, PoseDetector, PostureScorer, Calibrator, StateMachine,
    and PostureLogger.
    """
    cam = Camera(index=camera_index)
    if not cam.open():
        _log.error("Cannot open camera %d. Exiting.", camera_index)
        _stop_event.set()
        overlay.close()
        return

    import cv2 as _cv2  # local import to keep top-level imports clean

    with cam, PoseDetector() as detector, PostureLogger() as csv_logger:

        scorer = PostureScorer()
        machine = StateMachine()
        calibrator = Calibrator()

        # Start calibration immediately
        calibrator.start()
        overlay.update_calibration(0.0, 0)
        _log.info("Calibration phase started. Hold good posture for 10 s.")

        log_interval = 0.5        # Seconds between CSV rows (≈ 2 Hz)
        last_log_time = 0.0

        while not _stop_event.is_set():
            frame, ts = cam.read_frame()
            if frame is None:
                time.sleep(0.005)
                continue

            landmarks = detector.process(frame)

            # ---- Preview window ----
            if preview:
                display = frame.copy()
                if landmarks is not None:
                    h_px, w_px = display.shape[:2]
                    for pt in [landmarks.left_ear, landmarks.right_ear,
                               landmarks.left_shoulder, landmarks.right_shoulder]:
                        cx, cy = int(pt[0] * w_px), int(pt[1] * h_px)
                        _cv2.circle(display, (cx, cy), 5, (0, 255, 0), -1)
                phase = "CAL" if not calibrator.is_done else machine.state.name
                _cv2.putText(display, phase, (10, 28),
                             _cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
                _cv2.imshow("PostureProject - Preview", display)
                if _cv2.waitKey(1) & 0xFF == ord('q'):
                    _stop_event.set()
                    break

            if landmarks is None:
                continue

            result = scorer.compute(landmarks)
            if result is None:
                continue

            # ---- Calibration phase ----
            if not calibrator.is_done:
                calibrator.add_sample(result)
                overlay.update_calibration(
                    calibrator.progress,
                    calibrator.sample_count
                )
                if calibrator.is_done:
                    baseline = calibrator.baseline
                    machine.set_baseline(baseline)
                    scorer.reset()  # Clear EMA so post-cal tracking is fresh
                    _log.info("Calibration complete → baseline=%.4f", baseline)
                continue

            # ---- Normal monitoring phase ----
            state = machine.update(result.smoothed_score)
            fps = cam.actual_fps

            overlay.update_posture(state, result.smoothed_score, fps)

            # CSV logging at reduced rate to keep I/O light
            now = time.monotonic()
            if now - last_log_time >= log_interval:
                csv_logger.log(
                    score=result.smoothed_score,
                    state=state,
                    fps=fps,
                    hf=result.hf,
                    neck_angle_deg=result.neck_angle_deg,
                )
                last_log_time = now

    if preview:
        import cv2 as _cv2
        _cv2.destroyAllWindows()
    _log.info("Worker thread finished.")
    overlay.close()


def main():
    parser = argparse.ArgumentParser(
        description="PostureProject — webcam-based posture monitor"
    )
    parser.add_argument(
        "--camera", type=int, default=0,
        help="OpenCV camera index (default: 0)"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Show score/FPS overlay on the bar (development mode)"
    )
    parser.add_argument(
        "--preview", action="store_true",
        help="Show camera feed window with landmark dots (press Q to quit)"
    )
    parser.add_argument(
        "--bar-x", type=int, default=0,
        help="X pixel offset for the overlay bar (use to place on a second monitor)"
    )
    args = parser.parse_args()

    overlay = OverlayWindow(debug=args.debug, x_offset=args.bar_x)

    worker = threading.Thread(
        target=worker_loop,
        args=(overlay, args.camera, args.debug, args.preview),
        daemon=True,
        name="PostureWorker",
    )
    worker.start()
    _log.info("Worker thread launched.")

    try:
        # Blocks on the main thread — required for tkinter
        overlay.start()
    except KeyboardInterrupt:
        _log.info("Interrupted by user.")
    finally:
        _stop_event.set()
        worker.join(timeout=5.0)
        _log.info("Application exited cleanly.")


if __name__ == "__main__":
    main()
