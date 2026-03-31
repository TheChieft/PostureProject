"""
main.py
-------
Entry point for the PostureProject application.

Architecture
------------
main thread   → UI (tkinter — launcher, dashboard, mini-widget)
worker thread → Camera + MediaPipe + scoring + logging

Flow
----
1. Launcher window lets user pick mode (focus / posture-only) and parameters.
2. on_start() creates all windows and launches the worker thread.
3. Worker opens camera, runs calibration, then enters the monitoring loop.
4. When monitoring ends the worker calls on_done() which brings the launcher back.
5. Ctrl-C or window close triggers graceful shutdown.
"""

from __future__ import annotations
import argparse
import logging
import threading
import time

from camera import Camera
from calibrator import Calibrator
from dashboard import DashboardWindow
from focus_session import FocusSession, Phase
from launcher import LauncherWindow
from logger import PostureLogger
from mini_widget import MiniWidget, CAM_W, CAM_H
from pose import PoseDetector
from posture import PostureScorer
from state_machine import StateMachine, PostureState

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
_camera_event = threading.Event()   # set = camera preview requested


def worker_loop(dashboard: DashboardWindow,
                mini_widget: MiniWidget,
                focus_session: FocusSession,
                camera_index: int,
                debug: bool,
                preview: bool = False,
                on_done=None,
                camera_event: threading.Event | None = None):
    """
    Runs in a background thread.
    Owns Camera, PoseDetector, PostureScorer, Calibrator, StateMachine,
    and PostureLogger.
    """
    cam = Camera(index=camera_index)
    if not cam.open():
        _log.error("Cannot open camera %d. Exiting.", camera_index)
        _stop_event.set()
        if on_done:
            on_done()
        return

    import base64 as _b64
    import cv2 as _cv2
    import psutil
    import winsound

    with cam, PoseDetector() as detector, PostureLogger() as csv_logger:

        scorer = PostureScorer()
        machine = StateMachine()
        calibrator = Calibrator()

        if preview:
            _cv2.namedWindow("PostureProject - Preview", _cv2.WINDOW_NORMAL)
            _cv2.resizeWindow("PostureProject - Preview", 640, 360)

        # ── Pre-calibration countdown (3 s) ──────────────────────────
        # Open camera panel so the user can see themselves and sit properly.
        mini_widget.start_calibration_countdown()
        _cdown_start = time.monotonic()
        while time.monotonic() - _cdown_start < 3.0 and not _stop_event.is_set():
            _remaining = int(3.0 - (time.monotonic() - _cdown_start)) + 1
            mini_widget.update_calibration_countdown(_remaining)
            frame_c, _ = cam.read_frame()
            if frame_c is not None and camera_event and camera_event.is_set():
                _thumb = _cv2.resize(frame_c, (CAM_W, CAM_H))
                _rgb   = _cv2.cvtColor(_thumb, _cv2.COLOR_BGR2RGB)
                _ok, _buf = _cv2.imencode(".png", _rgb, [_cv2.IMWRITE_PNG_COMPRESSION, 1])
                if _ok:
                    mini_widget.set_camera_frame(_b64.b64encode(_buf.tobytes()).decode())
            time.sleep(0.05)

        mini_widget.update_calibration_countdown(0)   # countdown done, starting
        calibrator.start()
        _log.info("Calibration phase started. Hold good posture for 10 s.")

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
                if _beep_stop is not None:
                    _beep_stop.set()
                    _beep_stop = None
                _bad_since = None
                scorer.reset()
                machine = StateMachine()
                _prev_state = None
                # 3-second countdown before capturing new baseline
                mini_widget.start_calibration_countdown()
                _rc_start = time.monotonic()
                while time.monotonic() - _rc_start < 3.0 and not _stop_event.is_set():
                    _rem = int(3.0 - (time.monotonic() - _rc_start)) + 1
                    mini_widget.update_calibration_countdown(_rem)
                    _f, _ = cam.read_frame()
                    if _f is not None and camera_event and camera_event.is_set():
                        _t = _cv2.resize(_f, (CAM_W, CAM_H))
                        _r = _cv2.cvtColor(_t, _cv2.COLOR_BGR2RGB)
                        _ok2, _b2 = _cv2.imencode(".png", _r, [_cv2.IMWRITE_PNG_COMPRESSION, 1])
                        if _ok2:
                            mini_widget.set_camera_frame(_b64.b64encode(_b2.tobytes()).decode())
                    time.sleep(0.05)
                mini_widget.update_calibration_countdown(0)
                calibrator = Calibrator()
                calibrator.start()
                _log.info("Recalibration started.")

            frame, ts = cam.read_frame()
            if frame is None:
                time.sleep(0.005)
                continue

            landmarks = detector.process(frame)

            # ---- Camera preview in mini widget ----
            cam_open = camera_event is not None and camera_event.is_set()
            if cam_open:
                # Encode as PNG (RGB) — Tkinter PhotoImage supports PNG natively
                thumb = _cv2.resize(frame, (CAM_W, CAM_H))
                rgb   = _cv2.cvtColor(thumb, _cv2.COLOR_BGR2RGB)
                ok, buf = _cv2.imencode(".png", rgb, [_cv2.IMWRITE_PNG_COMPRESSION, 1])
                if ok:
                    mini_widget.set_camera_frame(_b64.b64encode(buf.tobytes()).decode())

            # ---- Preview window (--preview flag) ----
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
                    mini_widget.update_away()
                continue

            _no_landmark_since = None  # Person is visible again
            result = scorer.compute(landmarks)
            if result is None:
                continue

            # ---- Calibration phase ----
            if not calibrator.is_done:
                calibrator.add_sample(result)
                mini_widget.update_calibration_progress(calibrator.progress)
                if calibrator.is_done:
                    baseline = calibrator.baseline
                    machine.set_baseline(baseline)
                    scorer.reset()  # Clear EMA so post-cal tracking is fresh
                    dashboard.session_started()
                    mini_widget.calibration_complete()
                    _log.info("Calibration complete → baseline=%.4f", baseline)
                continue

            # ---- Normal monitoring phase ----
            state = machine.update(result.smoothed_score)
            fps = cam.actual_fps

            mini_widget.update_posture(state)

            if state != _prev_state:
                dashboard.add_event(state)
                _prev_state = state

            # ---- Focus session tick (phase auto-transition) ----
            focus_session.tick()

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
    mini_widget.close()

    if on_done:
        on_done()


def main():
    parser = argparse.ArgumentParser(
        description="PostureProject — webcam-based posture monitor"
    )
    parser.add_argument(
        "--camera", type=int, default=0,
        help="OpenCV camera index (default: 0)"
    )
    parser.add_argument(
        "--preview", action="store_true",
        help="Show camera feed window with landmark dots (press Q to quit)"
    )
    args = parser.parse_args()

    launcher = LauncherWindow()

    def _on_start(mode: str, work_secs: int, break_secs: int) -> None:
        _stop_event.clear()
        _recalibrate_event.clear()
        _pause_event.clear()
        _camera_event.clear()

        def _on_phase_change(phase: Phase) -> None:
            try:
                import winsound as _ws
                import threading as _t
                if phase == Phase.BREAK:
                    def _b():
                        _ws.Beep(880, 200)
                        _ws.Beep(1100, 300)
                    _t.Thread(target=_b, daemon=True).start()
                elif phase == Phase.WORK:
                    def _b():
                        _ws.Beep(800, 150)
                        _ws.Beep(800, 150)
                    _t.Thread(target=_b, daemon=True).start()
            except Exception:
                pass

        focus_session = FocusSession(on_phase_change=_on_phase_change)

        def _on_pause(paused: bool) -> None:
            dashboard.set_paused(paused)
            if paused:
                _pause_event.set()
            else:
                _pause_event.clear()

        # Dashboard: data manager only — UI is embedded in mini_widget
        dashboard = DashboardWindow(
            on_recalibrate=lambda: (_recalibrate_event.set(), _pause_event.clear()),
            on_pause=_on_pause,
            on_stop=lambda: _stop_event.set(),
        )

        def _on_camera_toggle() -> None:
            if mini_widget._cam_open:
                _camera_event.set()
            else:
                _camera_event.clear()

        def _on_recalibrate() -> None:
            _recalibrate_event.set()
            _pause_event.clear()

        def _on_stop() -> None:
            _stop_event.set()

        mini_widget = MiniWidget(
            focus_session=focus_session,
            dashboard=dashboard,
            on_camera_toggle=_on_camera_toggle,
            on_recalibrate=_on_recalibrate,
            on_pause=_on_pause,
            on_stop=_on_stop,
        )

        # Show mini widget immediately; dashboard deferred until 📊 clicked
        mini_widget.start(launcher.root)

        # Auto-start focus session if mode == "focus"
        if mode == "focus":
            focus_session.start(work_secs, break_secs)

        def _on_done() -> None:
            # Called from worker thread — schedule on main thread
            launcher.root.after(0, launcher.show)

        worker = threading.Thread(
            target=worker_loop,
            args=(dashboard, mini_widget, focus_session,
                  args.camera, False, args.preview),
            kwargs={"on_done": _on_done, "camera_event": _camera_event},
            daemon=True,
            name="PostureWorker",
        )
        worker.start()
        _log.info("Worker thread launched.")

    try:
        launcher.start(on_start=_on_start)
    except KeyboardInterrupt:
        _log.info("Interrupted by user.")
    finally:
        _stop_event.set()
        _log.info("Application exited cleanly.")


if __name__ == "__main__":
    main()
