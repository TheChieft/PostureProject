# PostureProject

Webcam-based slouch posture detector for Windows.
Displays an always-on-top coloured bar on the left edge of the screen.

---

## How it works

1. **Calibration (10 s)** — Sit in a good posture while the blue bar fills up.
   A baseline score is captured from your landmarks.
2. **Monitoring** — The bar switches colour based on your posture state:

| Colour             | Meaning                    |
| ------------------ | -------------------------- |
| 🟢 Green (narrow)   | Good posture               |
| 🟡 Yellow (medium)  | Slouching > 15 s — fix it  |
| 🔴 Red (full width) | Slouching > 30 s — act now |

Returning to good posture for 3 seconds resets the bar to green.

---

## Requirements

- Windows 11 (x64 Python, tested on ARM Snapdragon X)
- Python 3.11 x64
- A webcam visible at index 0

---

## Installation

```bash
# 1. Clone / copy the project
cd PostureProject

# 2. Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate        # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

> **Tkinter** ships with the official CPython Windows installer.
> If it is missing, reinstall Python and tick "tcl/tk and IDLE" in the installer.

---

## Running

```bash
python main.py
```

Optional flags:

| Flag         | Description                         |
| ------------ | ----------------------------------- |
| `--camera N` | Use camera index N (default: 0)     |
| `--debug`    | Show score/FPS mini-text on the bar |

Example:

```bash
python main.py --camera 1 --debug
```

---

## Project structure

```
PostureProject/
├── main.py          # Entry point — integrates all modules
├── camera.py        # Webcam capture (640x360, ~10 FPS)
├── pose.py          # MediaPipe Pose wrapper
├── posture.py       # Posture score computation + EMA
├── state_machine.py # GREEN / YELLOW / RED state transitions
├── calibrator.py    # 10-second calibration phase
├── logger.py        # CSV log writer (logs/ directory)
├── ui_overlay.py    # Tkinter always-on-top overlay bar
├── requirements.txt
└── README.md
```

---

## Posture score formula

```
HF  = (mid_ear_x − mid_shoulder_x) / shoulder_width
         Head-forward displacement, normalised by shoulder width

angle = neck vector angle from vertical (degrees)

S   = 0.5 × |HF| + 0.5 × (angle / 90)

Smoothed_S(t) = 0.3 × S(t) + 0.7 × Smoothed_S(t−1)   [EMA]
```

### Thresholds vs baseline

| State  | Condition                                   |
| ------ | ------------------------------------------- |
| Yellow | `smoothed_S > baseline × 1.15` for > 15 s   |
| Red    | `smoothed_S > baseline × 1.30` for > 30 s   |
| Green  | Score back below yellow threshold for > 3 s |

---

## Logs

CSV files are written to the `logs/` directory:

```
logs/posture_20260217_093012.csv
```

Columns: `timestamp, score, state, fps, hf, neck_angle`

A new file is created every 50 000 rows to keep individual files small.

---

## Performance targets

| Metric        | Target         |
| ------------- | -------------- |
| FPS           | ≥ 8            |
| CPU           | < 35 %         |
| False reds    | < 2 / hour     |
| Recovery time | < 10 s average |

Achieved via:
- 640×360 capture resolution
- MediaPipe `model_complexity=0` (Lite)
- EMA smoothing reduces jitter
- CSV logged at 2 Hz (not every frame)

---

## Stopping

Press **Ctrl-C** in the terminal, or close the overlay bar window.
All logs are flushed before exit.

---

## Troubleshooting

| Problem                | Fix                                                                                 |
| ---------------------- | ----------------------------------------------------------------------------------- |
| `Cannot open camera 0` | Check another app isn't using the webcam, or try `--camera 1`                       |
| Mediapipe import error | Ensure Python is x64: `python -c "import platform; print(platform.architecture())"` |
| Bar not always-on-top  | Some fullscreen apps override `topmost`; minimise them                              |
| Very high CPU          | Lower FPS in `camera.py` → `TARGET_FPS = 8`                                         |
