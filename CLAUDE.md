# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

- Development is done in **WSL (Ubuntu-24.04)**; execution is on **Windows** (Conda, Python 3.11 x64, Snapdragon X ARM).
- The `.conda/` and `.venv/` directories are local environments — ignore them.
- Source files live at the repo root (no subdirectory nesting).

## Running the application

The program must run with **Windows Python** (Conda) because it needs the Windows webcam and Tkinter display.

### First-time setup (PowerShell)

```powershell
cd \\wsl.localhost\Ubuntu-24.04\home\thechieft\projects\PostureProject

# Install dependencies
pip install -r requirements.txt

# Download the MediaPipe pose model (~5 MB, stored locally, not committed to git)
python download_model.py
```

### Running

```powershell
cd \\wsl.localhost\Ubuntu-24.04\home\thechieft\projects\PostureProject
python main.py
python main.py --camera 1 --debug
```

### mediapipe Notes

- On Windows ARM (Snapdragon X), only `mediapipe>=0.10.30` is available via pip.
- These versions dropped the legacy `mp.solutions` API — `pose.py` uses the Tasks API (`mp.tasks.vision.PoseLandmarker`) instead.
- `requirements.txt` pins `mediapipe==0.10.30`.
- The Tasks API requires a `.task` model file — download it with `download_model.py`. The file is excluded from git (`.gitignore`).

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
