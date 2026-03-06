# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

- Python 3.11 x64, Windows 11 (Snapdragon X ARM). The `.conda/` and `.venv/` directories are local environments — ignore them.
- The actual source lives in `PostureProject/` (the inner directory).

## Running the application

```bash
cd PostureProject
pip install -r requirements.txt
python main.py
python main.py --camera 1 --debug   # alternate camera + debug overlay
```

## Architecture

Two-thread design:
- **Main thread** — runs the Tkinter `OverlayWindow` (required by tkinter's single-thread constraint)
- **Worker thread** — owns all camera/ML/scoring/logging objects; communicates to UI via method calls on the shared `OverlayWindow` instance

### Module responsibilities

| Module | Role |
|---|---|
| `camera.py` | OpenCV webcam capture at 640×360, ~10 FPS |
| `pose.py` | MediaPipe Pose wrapper; produces `PostureLandmarks` |
| `posture.py` | Computes `PostureResult` from landmarks (HF + neck angle), maintains EMA smoothing |
| `calibrator.py` | 10-second baseline capture; outputs mean smoothed score as baseline |
| `state_machine.py` | GREEN/YELLOW/RED transitions based on score vs. baseline + time thresholds |
| `logger.py` | CSV writer to `logs/` at ~2 Hz; rotates at 50,000 rows |
| `ui_overlay.py` | Always-on-top left-edge colour bar; shows calibration progress then posture state |
| `main.py` | Entry point; wires all modules, launches worker thread |

### Data flow

```
Camera → PoseDetector → PostureScorer → Calibrator (phase 1)
                                      → StateMachine → OverlayWindow (phase 2)
                                                     → PostureLogger
```

### Key data types

- `PostureLandmarks` (pose.py) — normalised x/y coords for ears and shoulders
- `PostureResult` (posture.py) — raw score, EMA-smoothed score, hf, neck_angle_deg
- `PostureState` (state_machine.py) — GREEN / YELLOW / RED enum

### Score formula

```
HF = (mid_ear_x - mid_shoulder_x) / shoulder_width
S  = 0.5 * |HF| + 0.5 * (neck_angle_deg / 90)
smoothed_S = 0.3 * S + 0.7 * smoothed_S_prev   # EMA, alpha=0.3
```

State thresholds (relative to calibration baseline):
- YELLOW: score > baseline × 1.15 for > 15 s
- RED: score > baseline × 1.30 for > 30 s
- GREEN recovery: score below yellow threshold for > 3 s

After calibration completes, `PostureScorer.reset()` is called to clear the EMA so monitoring starts fresh.

## Logs

Written to `PostureProject/logs/posture_<datetime>.csv`. Columns: `timestamp, score, state, fps, hf, neck_angle`. New file created every 50,000 rows.
