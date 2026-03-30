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
from dashboard import DashboardWindow
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
# Shared events between worker / UI / dashboard
# ------------------------------------------------------------------
_stop_event = threading.Event()
_recalibrate_event = threading.Event()
_pause_event = threading.Event()


def worker_loop(overlay: OverlayWindow,
                dashboard: DashboardWindow,
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

    import cv2 as _cv2
    import psutil
    import winsound

    with cam, PoseDetector() as detector, PostureLogger() as csv_logger:

        scorer = PostureScorer()
        machine = StateMachine()
        calibrator = Calibrator()

        # Start calibration immediately
        calibrator.start()
        overlay.update_calibration(0.0, 0)
        _log.info("Calibration phase started. Hold good posture for 10 s.")

        if preview:
            _cv2.namedWindow("PostureProject - Preview", _cv2.WINDOW_NORMAL)
            _cv2.resizeWindow("PostureProject - Preview", 640, 360)

        log_interval = 0.5        # Seconds between CSV rows (≈ 2 Hz)
        last_log_time = 0.0
        _prev_state: PostureState | None = None

        # Bad posture beep tracking (YELLOW or RED sustained)
        _bad_since: float | None = None
        _beep_stop: threading.Event | None = None

        # Absence tracking: no landmarks detected for sustained period
        _no_landmark_since: float | None = None

        def _start_beep_loop(stop_event: threading.Event):
            """Beeps repeatedly until stop_event is set."""
            while not stop_event.is_set():
                winsound.Beep(880, 500)
                stop_event.wait(0.6)  # 0.6 s gap between beeps

        # Resource stats (updated every second to avoid overhead)
        _cpu_pct = 0.0
        _ram_pct = 0.0
        _last_stats_time = 0.0
        psutil.cpu_percent()  # first call always returns 0.0; prime the counter

        while not _stop_event.is_set():

            # ---- Pause ----
            if _pause_event.is_set():
                time.sleep(0.1)
                continue

            # ---- Recalibrate ----
            if _recalibrate_event.is_set():
                _recalibrate_event.clear()
                calibrator = Calibrator()
                calibrator.start()
                scorer.reset()
                machine = StateMachine()
                _prev_state = None
                if _beep_stop is not None:
                    _beep_stop.set()
                    _beep_stop = None
                _bad_since = None
                overlay.update_calibration(0.0, 0)
                _log.info("Recalibration started.")

            frame, ts = cam.read_frame()
            if frame is None:
                time.sleep(0.005)
                continue

            landmarks = detector.process(frame)

            # ---- Preview window ----
            if preview:
                display = frame.copy()
                h_px, w_px = display.shape[:2]

                if landmarks is not None:
                    for pt in [landmarks.left_ear, landmarks.right_ear,
                               landmarks.left_shoulder, landmarks.right_shoulder]:
                        cx, cy = int(pt[0] * w_px), int(pt[1] * h_px)
                        _cv2.circle(display, (cx, cy), 5, (0, 255, 0), -1)

                # Update resource stats once per second
                now_s = time.monotonic()
                if now_s - _last_stats_time >= 1.0:
                    _cpu_pct = psutil.cpu_percent()
                    _ram_pct = psutil.virtual_memory().percent
                    _last_stats_time = now_s

                fps_now = cam.actual_fps
                phase = "CAL" if not calibrator.is_done else machine.state.name

                # State label — top left
                _cv2.putText(display, phase, (10, 30),
                             _cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)

                # Stats — bottom left
                stats_lines = [
                    f"FPS: {fps_now:.1f}",
                    f"CPU: {_cpu_pct:.0f}%",
                    f"RAM: {_ram_pct:.0f}%",
                ]
                for i, line in enumerate(stats_lines):
                    y = h_px - 12 - (len(stats_lines) - 1 - i) * 22
                    _cv2.putText(display, line, (10, y),
                                 _cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

                _cv2.imshow("PostureProject - Preview", display)
                if _cv2.waitKey(1) & 0xFF == ord('q'):
                    _stop_event.set()
                    break

            if landmarks is None:
                # Track absence: after 3 s with no person, go to away state
                if _no_landmark_since is None:
                    _no_landmark_since = time.monotonic()
                elif time.monotonic() - _no_landmark_since >= 3.0:
                    if _beep_stop is not None:
                        _beep_stop.set()
                        _beep_stop = None
                    _bad_since = None
                    overlay.update_away()
                continue

            _no_landmark_since = None  # Person is visible again
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
                    dashboard.session_started()
                    _log.info("Calibration complete → baseline=%.4f", baseline)
                continue

            # ---- Normal monitoring phase ----
            state = machine.update(result.smoothed_score)
            fps = cam.actual_fps

            overlay.update_posture(state, result.smoothed_score, fps)

            if state != _prev_state:
                dashboard.add_event(state)
                _prev_state = state

            # ---- Beep: continuous after 8 s in YELLOW or RED ----
            now = time.monotonic()
            if state in (PostureState.YELLOW, PostureState.RED):
                if _bad_since is None:
                    _bad_since = now
                elif _beep_stop is None and (now - _bad_since) >= 8.0:
                    _beep_stop = threading.Event()
                    threading.Thread(
                        target=_start_beep_loop,
                        args=(_beep_stop,),
                        daemon=True,
                    ).start()
                    _log.warning("Alert: sustained bad posture > 8 s (%s)", state.name)
            else:
                if _beep_stop is not None:
                    _beep_stop.set()
                    _beep_stop = None
                _bad_since = None

            # CSV logging at reduced rate to keep I/O light
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

    def _on_pause(paused: bool) -> None:
        if paused:
            _pause_event.set()
        else:
            _pause_event.clear()

    dashboard = DashboardWindow(
        on_recalibrate=lambda: (_recalibrate_event.set(), _pause_event.clear()),
        on_pause=_on_pause,
        on_stop=lambda: (_stop_event.set(), overlay.close()),
    )

    worker = threading.Thread(
        target=worker_loop,
        args=(overlay, dashboard, args.camera, args.debug, args.preview),
        daemon=True,
        name="PostureWorker",
    )
    worker.start()
    _log.info("Worker thread launched.")

    try:
        # Blocks on the main thread — required for tkinter
        overlay.start(on_ready=dashboard.start)
    except KeyboardInterrupt:
        _log.info("Interrupted by user.")
    finally:
        _stop_event.set()
        worker.join(timeout=5.0)
        _log.info("Application exited cleanly.")


if __name__ == "__main__":
    main()
