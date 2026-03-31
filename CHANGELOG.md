# Changelog

All notable changes are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.1.0] — 2026-03-30

### Added
- **Mini widget** — floating horizontal status bar (always on top, draggable)
  - Posture color strip, session phase label, countdown timer, progress bar
  - Inline camera preview panel (📷 toggle)
  - Inline session dashboard panel (📊 toggle) with 10-minute timeline and stats
- **Focus sessions** — Pomodoro-style work/break timer with 4 presets
- **Session dashboard** — timeline, time per state, % breakdown
- **Calibration countdown** — 3-second "sit up straight" prompt before baseline capture; camera opens automatically so the user can verify detection
- **Absence detection** — enters neutral state after 3 s without a detected person; alerts pause automatically
- **Taskbar presence** — app always visible in the Windows taskbar (Win32 `WS_EX_APPWINDOW`)
- **Always-on-top reliability** — reinforced via `SetWindowPos(HWND_TOPMOST)` every 1.5 s
- **App icon** — loaded into taskbar entry via `WM_SETICON` (no more Python icon)
- **Stop confirmation** — ■ button asks before ending a session
- **Privacy footer** — launcher states all processing is 100% local

### Changed
- Replaced the left-edge sidebar overlay with the mini widget
- Windows 11 dark neutral colour scheme (`#1e1e1e`, `#2a2a2a`, `#0078D4`)
- Font updated to **Segoe UI Variable** throughout the launcher
- Camera preview now encoded as PNG (fixes black panel bug)
- Dashboard no longer opens as a separate window — it's an inline collapsible panel
- `launcher.hide()` uses `iconify()` instead of `withdraw()` — keeps launcher in taskbar

### Fixed
- Dashboard "×" button was closing the entire session without confirmation
- Pause segments disappearing from timeline after resuming
- Session timer kept counting while paused
- Windows opening at random screen positions
- Camera preview panel showing a black rectangle (wrong image encoding)

---

## [1.0.0] — 2026-01-15

### Added
- Initial release
- Real-time posture detection via MediaPipe Pose (Tasks API)
- 10-second personalised baseline calibration
- GREEN / YELLOW / RED state machine with configurable thresholds
- Audible alert (continuous beep) after 8 s of sustained bad posture
- Left-edge always-on-top colour bar overlay
- CSV session logging to `logs/` (~2 Hz, rotates at 50 000 rows)
- PyInstaller packaging (`--onedir --windowed`)
- `--preview` flag for live landmark overlay window
