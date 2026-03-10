# PostureProject

Real-time posture monitor for Windows. Uses your webcam and MediaPipe to track
head position and neck angle, then displays an always-on-top colour bar on the
left edge of your screen — green when your posture is good, yellow when you've
been slouching for a while, red when it's gone on too long.

No cloud, no account, no background services. Runs entirely on your machine.

---

## Quick start — Download the .exe

1. Go to [**Releases**](../../releases) and download `PostureProject.zip`
2. Extract the folder anywhere on your PC
3. Run `PostureProject.exe` (double-click or from PowerShell):

```powershell
.\PostureProject.exe
```

**Requirements:** Windows 10 or 11, a webcam. No Python needed.

---

## How it works

### Step 1 — Calibration (~10 seconds)

A **blue bar** rises from the bottom of the screen. Sit in your best posture and
hold it while the bar fills up. This captures your personal baseline score.

### Step 2 — Monitoring

After calibration the bar changes colour based on how long you've been slouching:

| Bar | Width | Meaning |
|---|---|---|
| 🟢 Green | Narrow | Good posture |
| 🟡 Yellow | Medium | Slouching for > 5 s — straighten up |
| 🔴 Red | Full width | Slouching for > 7 s — act now |

After **8 seconds** in Yellow or Red a beep plays on repeat until you sit up
straight. Returning to good posture for **2 seconds** resets the bar to green.

### Step 3 — Dashboard

A second window opens automatically alongside the bar:

- **Session timer** — elapsed time since calibration finished
- **Colour timeline** — last 10 minutes of posture history
- **Stats table** — time and percentage spent in each state

Buttons:

| Button | Action |
|---|---|
| Recalibrate | Restart the 10-second baseline capture |
| Pause | Freeze monitoring (grey segment appears in timeline) |
| Stop | Close the application |

---

## Command-line options

```powershell
PostureProject.exe [options]
```

| Option | Default | Description |
|---|---|---|
| `--camera N` | `0` | OpenCV camera index (try `1`, `2`… if the wrong camera opens) |
| `--preview` | off | Show live webcam feed with pose landmark dots (press Q to close) |
| `--debug` | off | Draw score and FPS as tiny text on the colour bar |
| `--bar-x N` | `0` | Horizontal pixel offset for the bar — use to place it on a second monitor |

Examples:

```powershell
# Use a secondary webcam
.\PostureProject.exe --camera 1

# Place the bar on the right side of a dual-monitor setup
.\PostureProject.exe --bar-x 1920

# Show the webcam preview while running
.\PostureProject.exe --preview
```

---

## Logs

Session data is written to a `logs\` folder next to the executable:

```
PostureProject\
└── logs\
    └── posture_20260309_093012.csv
```

Columns: `timestamp, score, state, fps, hf, neck_angle`

A new file is created every 50,000 rows to keep file sizes manageable.

---

## Building from source

For developers who want to modify the code or rebuild the executable.

### Requirements

- Windows 10 or 11 (x64 or ARM64 / Snapdragon X)
- [Python 3.11](https://www.python.org/downloads/release/python-3119/) from
  python.org — **not** the Windows Store version
- PowerShell (built into Windows)

> If you are developing from WSL, **do not use a virtual environment** when
> running over a UNC path (`\\wsl.localhost\...`) — activation scripts fail.
> Install directly into the system Python instead.

### Setup

```powershell
# 1. Clone the repository
git clone https://github.com/TheChieft/PostureProject.git
cd PostureProject

# 2. Install Python dependencies
py -3.11 -m pip install --only-binary :all: -r requirements.txt

# 3. Download the MediaPipe pose model (~5 MB, not included in the repo)
py -3.11 download_model.py
```

### Running from source

```powershell
py -3.11 main.py
py -3.11 main.py --preview --debug
```

### Building the .exe

```powershell
.\build.ps1
```

Output: `dist\PostureProject\PostureProject.exe`

The entire `dist\PostureProject\` folder is self-contained. Copy it to any
Windows machine — no Python installation needed.

---

## Project structure

```
PostureProject/
├── main.py              # Entry point — wires all modules, launches worker thread
├── camera.py            # OpenCV webcam capture (640×360, ~10 FPS)
├── pose.py              # MediaPipe PoseLandmarker wrapper (Tasks API)
├── posture.py           # Posture score computation + EMA smoothing
├── state_machine.py     # GREEN / YELLOW / RED state transitions
├── calibrator.py        # 10-second baseline calibration
├── logger.py            # CSV writer (logs/ directory)
├── ui_overlay.py        # Always-on-top colour bar (Tkinter)
├── dashboard.py         # Session dashboard window
├── paths.py             # Path resolution for dev vs frozen .exe
├── download_model.py    # Downloads pose_landmarker_lite.task from Google
├── build.ps1            # PowerShell build script (wraps PyInstaller)
├── PostureProject.spec  # PyInstaller configuration
└── requirements.txt
```

---

## How the score is calculated

```
HF    = (mid_ear_x − mid_shoulder_x) / shoulder_width   # head-forward offset
angle = neck vector angle from vertical (degrees)

S(t)          = 0.5 × |HF| + 0.5 × (angle / 90)
smoothed_S(t) = 0.3 × S(t) + 0.7 × smoothed_S(t−1)     # EMA, α = 0.3
```

State thresholds are relative to the personal baseline captured during calibration:

| Transition | Condition |
|---|---|
| GREEN → YELLOW | `smoothed_S > baseline × 1.15` sustained for > 5 s |
| YELLOW → RED | `smoothed_S > baseline × 1.30` sustained for > 7 s |
| RED / YELLOW → GREEN | Score below yellow threshold for > 2 s |
| Beep starts | Still in YELLOW or RED after 8 s |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Cannot open camera 0" | Another app may be using the webcam. Try `--camera 1`. |
| No pose detected | Make sure your face and both shoulders are visible. Good lighting helps. |
| Bar not always-on-top | Some fullscreen apps override topmost windows — minimise them. |
| High CPU | Lower `TARGET_FPS` in `camera.py` (default ~10). |
| No beep sound | `winsound` requires audio output. Check Windows volume and speakers/headphones. |
| Mediapipe import error | Confirm Python is **not** the Windows Store version: `py -3.11 -c "import sys; print(sys.executable)"` |

---

## License

[PolyForm Noncommercial 1.0.0](LICENSE) — free for personal, educational, and
non-commercial use. Commercial use requires a separate agreement with the author.
