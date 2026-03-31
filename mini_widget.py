"""
mini_widget.py
--------------
Horizontal floating status bar — the primary runtime UI.

Layout (always-on-top, draggable, ~520 × 61 px):

 ┌─────────────────────────────────────────────────────────────────┐
 │▌  BUENA  •  TRABAJO  24:35    [⏸]  [↺]  [■]    [📷]  [📊]   │
 │   ████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░             │  ← 3 px bar
 └─────────────────────────────────────────────────────────────────┘

[📷] expands/collapses a camera-preview panel below the bar.
[📊] expands/collapses an inline session dashboard (timeline + stats).
[⏸] pauses/resumes, [↺] recalibrates, [■] stops (with confirmation).

During calibration, a 3-second countdown is shown in the timer area
and the camera panel opens automatically so the user can verify
detection.  It closes automatically once calibration completes.
"""
from __future__ import annotations
import threading
import time
import tkinter as tk
from tkinter import messagebox
from typing import TYPE_CHECKING, Callable

from state_machine import PostureState
from focus_session import FocusSession, Phase

if TYPE_CHECKING:
    from dashboard import DashboardWindow

# ── Windows 11 dark theme ─────────────────────────────────────────────
BG      = "#1e1e1e"   # base background
BG2     = "#2a2a2a"   # panel / surface
BG3     = "#363636"   # elevated (buttons, inputs)
FG      = "#e4e4e4"   # primary text
FG_DIM  = "#888888"   # secondary / dimmed
ACCENT  = "#0078D4"   # Windows blue
BORDER  = "#404040"   # subtle separator
AWAY_C  = "#3c3c3c"

POSTURE_COLORS = {
    PostureState.GREEN:  "#16C60C",
    PostureState.YELLOW: "#F7BC00",
    PostureState.RED:    "#E81123",
}
POSTURE_LABELS = {
    PostureState.GREEN:  "BUENA",
    PostureState.YELLOW: "ALERTA",
    PostureState.RED:    "MAL",
}
PHASE_COLORS = {
    Phase.WORK:  ACCENT,
    Phase.BREAK: "#107C10",
}
PHASE_LABELS = {
    Phase.WORK:  "TRABAJO",
    Phase.BREAK: "DESCANSO",
}

STRIP_W   = 4      # left accent strip width
W         = 520    # widget total width
CAM_H     = 180    # camera preview panel height
CAM_W     = 320    # camera preview panel width
FONT      = "Segoe UI Variable"
FONT_MONO = "Consolas"


class MiniWidget:
    """
    Horizontal floating status bar.

    Create it, then call start(root) from the main thread once the Tk
    root exists.  All on_* callbacks are optional.
    """

    def __init__(
        self,
        focus_session:    FocusSession,
        dashboard:        "DashboardWindow",
        on_camera_toggle: Callable[[], None]     | None = None,
        on_recalibrate:   Callable[[], None]     | None = None,
        on_pause:         Callable[[bool], None] | None = None,
        on_stop:          Callable[[], None]     | None = None,
    ) -> None:
        self._session   = focus_session
        self._dashboard = dashboard
        self._on_cam    = on_camera_toggle
        self._on_recal  = on_recalibrate
        self._on_pause_cb = on_pause
        self._on_stop   = on_stop

        # Posture state (written from worker, read on main thread)
        self._posture: PostureState = PostureState.GREEN
        self._away:    bool         = False

        # Calibration state
        self._calibrating:    bool  = True   # True until calibration_complete()
        self._cal_countdown:  int   = 3      # 3→2→1→0 (0 = calibrating)
        self._cal_progress:   float = 0.0

        # Camera panel state
        self._cam_open:  bool = False
        self._cam_lock   = threading.Lock()
        self._cam_frame: str | None = None   # latest PNG as base64 string
        self._cam_photo: tk.PhotoImage | None = None

        # Dashboard panel state
        self._dash_open: bool = False

        # Session pause state
        self._paused = False

        # Tk refs — main bar
        self._win:         tk.Toplevel | None = None
        self._strip:       tk.Frame    | None = None
        self._posture_lbl: tk.Label    | None = None
        self._session_lbl: tk.Label    | None = None
        self._timer_lbl:   tk.Label    | None = None
        self._pause_btn:   tk.Button   | None = None
        self._prog_canvas: tk.Canvas   | None = None
        self._cam_btn:     tk.Button   | None = None
        self._dash_btn:    tk.Button   | None = None

        # Tk refs — panels
        self._cam_panel:  tk.Frame  | None = None
        self._cam_canvas: tk.Canvas | None = None
        self._dash_panel: tk.Frame  | None = None
        self._dash_canvas: tk.Canvas | None = None   # timeline
        self._dash_elapsed: tk.Label | None = None
        self._dash_stat_labels: dict = {}   # (PostureState, 'time'|'pct') → Label

        # Drag
        self._drag_ox = 0
        self._drag_oy = 0

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self, root: tk.Tk) -> None:
        """Build the widget.  Must be called from the main thread."""
        self._win = tk.Toplevel(root)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.attributes("-alpha", 0.97)
        self._win.configure(bg=BG)
        self._win.resizable(False, False)

        self._build_ui()
        self._bind_drag_recursive(self._win)

        self._win.update_idletasks()
        sw = root.winfo_screenwidth()
        self._win.geometry(f"+{sw - W - 20}+20")

        # Windows-specific: reliable always-on-top + taskbar entry
        self._win.after(100, self._setup_windows)

        self._schedule_draw()
        self._schedule_keep_top()

    def close(self) -> None:
        if self._win:
            try:
                self._win.after(0, self._win.destroy)
            except Exception:
                pass
            self._win = None

    # ── Windows integration ───────────────────────────────────────────

    def _setup_windows(self) -> None:
        """Windows-specific: add widget to taskbar and reinforce topmost."""
        if not self._win:
            return
        try:
            import ctypes
            GWL_EXSTYLE      = -20
            WS_EX_APPWINDOW  = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            SW_HIDE = 0
            SW_SHOW = 5

            # winfo_id() returns the HWND of the tkinter child frame on Windows;
            # GetParent gives us the outer Win32 window that owns the taskbar slot.
            hwnd = self._win.winfo_id()
            outer = ctypes.windll.user32.GetParent(hwnd) or hwnd

            # Remove ToolWindow style (hides from taskbar), add AppWindow style
            style = ctypes.windll.user32.GetWindowLongW(outer, GWL_EXSTYLE)
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(outer, GWL_EXSTYLE, style)

            # A hide/show cycle is required for the taskbar change to take effect
            ctypes.windll.user32.ShowWindow(outer, SW_HIDE)
            ctypes.windll.user32.ShowWindow(outer, SW_SHOW)

            # SetWindowPos with HWND_TOPMOST is more reliable than tkinter's -topmost
            HWND_TOPMOST = -1
            SWP_NOMOVE   = 0x0002
            SWP_NOSIZE   = 0x0001
            ctypes.windll.user32.SetWindowPos(
                outer, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE
            )
        except Exception:
            pass   # Non-Windows or permission issue — tkinter fallback is in place

    def _schedule_keep_top(self) -> None:
        """Periodically re-assert always-on-top in case another window took it."""
        if self._win:
            try:
                self._win.lift()
                self._win.attributes("-topmost", True)
            except Exception:
                pass
            self._win.after(1500, self._schedule_keep_top)

    # ── Posture API (called from worker thread) ────────────────────────

    def update_posture(self, state: PostureState) -> None:
        self._posture = state
        self._away    = False

    def update_away(self) -> None:
        self._away = True

    # ── Calibration API (called from worker thread) ───────────────────

    def start_calibration_countdown(self) -> None:
        """Begin the pre-calibration countdown and auto-open the camera."""
        self._calibrating   = True
        self._cal_countdown = 3
        self._cal_progress  = 0.0
        if self._win:
            self._win.after(0, self._auto_open_camera)

    def update_calibration_countdown(self, n: int) -> None:
        """n: seconds remaining (3→2→1); 0 means calibration is now running."""
        self._cal_countdown = n

    def update_calibration_progress(self, progress: float) -> None:
        self._cal_progress = progress

    def calibration_complete(self) -> None:
        """Mark calibration as done; auto-close camera after a brief delay."""
        self._calibrating  = False
        self._cal_progress = 1.0
        if self._win:
            self._win.after(800, self._auto_close_camera)

    # ── Camera API (called from worker thread) ────────────────────────

    def set_camera_frame(self, png_b64: str) -> None:
        """Receive a PNG frame (base64-encoded) from the worker thread."""
        with self._cam_lock:
            self._cam_frame = png_b64

    # ── Internal camera helpers ───────────────────────────────────────

    def _auto_open_camera(self) -> None:
        """Open the camera panel (runs on main thread via after())."""
        if not self._cam_open:
            self._cam_open = True
            if self._cam_btn:
                self._cam_btn.configure(bg=ACCENT, fg="white")
            if self._cam_panel:
                self._cam_panel.pack(fill="x")
            if self._on_cam:
                self._on_cam()

    def _auto_close_camera(self) -> None:
        """Close the camera panel (runs on main thread via after())."""
        if self._cam_open:
            self._cam_open = False
            if self._cam_btn:
                self._cam_btn.configure(bg=BG, fg=FG_DIM)
            if self._cam_panel:
                self._cam_panel.pack_forget()
            if self._on_cam:
                self._on_cam()

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        w = self._win

        # ── Main row ──────────────────────────────────────────────────
        main_row = tk.Frame(w, bg=BG, height=58)
        main_row.pack(fill="x")
        main_row.pack_propagate(False)

        # Left accent strip
        self._strip = tk.Frame(main_row, width=STRIP_W, bg=ACCENT)
        self._strip.pack(side="left", fill="y")
        self._strip.pack_propagate(False)

        # Info section
        info = tk.Frame(main_row, bg=BG)
        info.pack(side="left", fill="y", padx=(10, 0))

        self._posture_lbl = tk.Label(
            info, text="BUENA", bg=BG, fg=POSTURE_COLORS[PostureState.GREEN],
            font=(FONT, 9, "bold"), anchor="w",
        )
        self._posture_lbl.pack(anchor="w", pady=(11, 0))

        self._session_lbl = tk.Label(
            info, text="Calibrando…", bg=BG, fg=FG_DIM,
            font=(FONT, 8), anchor="w",
        )
        self._session_lbl.pack(anchor="w")

        # Timer (large, center)
        self._timer_lbl = tk.Label(
            main_row, text="", bg=BG, fg=FG,
            font=(FONT_MONO, 18, "bold"),
        )
        self._timer_lbl.pack(side="left", padx=(14, 0))

        # Flex spacer
        tk.Frame(main_row, bg=BG).pack(side="left", expand=True, fill="both")

        # Small control buttons
        ctrl = tk.Frame(main_row, bg=BG)
        ctrl.pack(side="left", fill="y", padx=(0, 4))

        ctrl_kw = dict(
            bg=BG, relief="flat", cursor="hand2", bd=0,
            font=(FONT, 12),
            activebackground=BG3, activeforeground=FG,
        )

        self._pause_btn = tk.Button(
            ctrl, text="⏸", fg=FG_DIM, command=self._toggle_pause, **ctrl_kw,
        )
        self._pause_btn.pack(side="left", padx=2)

        tk.Button(
            ctrl, text="↺", fg=FG_DIM, command=self._do_recalibrate, **ctrl_kw,
        ).pack(side="left", padx=2)

        tk.Button(
            ctrl, text="■", fg="#E81123", command=self._do_stop, **ctrl_kw,
        ).pack(side="left", padx=2)

        # Vertical separator
        tk.Frame(main_row, width=1, bg=BORDER).pack(
            side="left", fill="y", pady=10, padx=4
        )

        # Square action buttons
        sq_kw = dict(
            relief="flat", cursor="hand2", bd=0,
            font=("Segoe UI Emoji", 16), width=2,
            activebackground=BG3,
        )

        self._cam_btn = tk.Button(
            main_row, text="📷", bg=BG, fg=FG_DIM,
            command=self._toggle_camera, **sq_kw,
        )
        self._cam_btn.pack(side="left", padx=(4, 2), pady=4)

        self._dash_btn = tk.Button(
            main_row, text="📊", bg=BG, fg=FG_DIM,
            command=self._toggle_dashboard, **sq_kw,
        )
        self._dash_btn.pack(side="left", padx=(2, 8), pady=4)

        # ── Progress bar ──────────────────────────────────────────────
        self._prog_canvas = tk.Canvas(w, height=3, bg=BG, highlightthickness=0)
        self._prog_canvas.pack(fill="x")

        # ── Camera panel (hidden until toggled) ───────────────────────
        self._cam_panel = tk.Frame(w, bg="#111111", height=CAM_H)
        # Not packed initially

        self._cam_canvas = tk.Canvas(
            self._cam_panel, width=CAM_W, height=CAM_H,
            bg="#111111", highlightthickness=0,
        )
        self._cam_canvas.pack(expand=True)

        # ── Dashboard panel (hidden until toggled) ────────────────────
        self._dash_panel = tk.Frame(w, bg=BG2)
        # Not packed initially
        self._build_dash_panel()

    def _build_dash_panel(self) -> None:
        p = self._dash_panel

        # Header: label + elapsed time
        header = tk.Frame(p, bg=BG2)
        header.pack(fill="x", padx=12, pady=(8, 3))

        tk.Label(
            header, text="SESIÓN", bg=BG2, fg=FG_DIM,
            font=(FONT, 7, "bold"),
        ).pack(side="left")

        self._dash_elapsed = tk.Label(
            header, text="—", bg=BG2, fg=FG,
            font=(FONT_MONO, 9),
        )
        self._dash_elapsed.pack(side="right")

        # Timeline canvas
        self._dash_canvas = tk.Canvas(
            p, width=W - 24, height=20, bg="#111111", highlightthickness=0,
        )
        self._dash_canvas.pack(padx=12, pady=(0, 6))

        # Stats: one cell per state side-by-side
        stats_row = tk.Frame(p, bg=BG2)
        stats_row.pack(fill="x", padx=12, pady=(0, 10))

        for state in PostureState:
            color = POSTURE_COLORS[state]
            cell = tk.Frame(stats_row, bg=BG2)
            cell.pack(side="left", expand=True, fill="x")

            tk.Label(
                cell, text=f"● {POSTURE_LABELS[state]}", bg=BG2, fg=color,
                font=(FONT, 8, "bold"),
            ).pack(anchor="w")

            t_lbl = tk.Label(cell, text="—", bg=BG2, fg=FG, font=(FONT_MONO, 10, "bold"))
            t_lbl.pack(anchor="w")

            p_lbl = tk.Label(cell, text="—", bg=BG2, fg=FG_DIM, font=(FONT, 8))
            p_lbl.pack(anchor="w")

            self._dash_stat_labels[(state, "time")] = t_lbl
            self._dash_stat_labels[(state, "pct")]  = p_lbl

        # Bottom border
        tk.Frame(p, height=1, bg=BORDER).pack(fill="x")

    # ── Draw loop ─────────────────────────────────────────────────────

    def _schedule_draw(self) -> None:
        self._draw()
        if self._win:
            self._win.after(250, self._schedule_draw)

    def _draw(self) -> None:
        if self._calibrating:
            self._draw_calibration()
        else:
            self._draw_normal()

        self._draw_progress_bar()

        if self._cam_open:
            self._refresh_camera()

        if self._dash_open:
            self._draw_dashboard()

    # ── Calibration rendering ─────────────────────────────────────────

    def _draw_calibration(self) -> None:
        if self._strip:
            self._strip.configure(bg=ACCENT)

        if self._posture_lbl:
            self._posture_lbl.config(text="CALIBRANDO", fg=ACCENT)

        if self._session_lbl:
            if self._cal_countdown > 0:
                self._session_lbl.config(
                    text="Siéntate recto y mira al frente", fg=FG_DIM
                )
            else:
                pct = int(self._cal_progress * 100)
                self._session_lbl.config(
                    text=f"Capturando línea base…  {pct}%", fg=FG_DIM
                )

        if self._timer_lbl:
            if self._cal_countdown > 0:
                self._timer_lbl.config(text=str(self._cal_countdown), fg=ACCENT)
            else:
                self._timer_lbl.config(text="", fg=FG_DIM)

        if self._pause_btn:
            self._pause_btn.config(text="⏸", fg=FG_DIM)

    # ── Normal rendering ──────────────────────────────────────────────

    def _draw_normal(self) -> None:
        # Strip color
        if self._strip:
            color = AWAY_C if self._away else POSTURE_COLORS.get(self._posture, AWAY_C)
            self._strip.configure(bg=color)

        # Posture label
        if self._posture_lbl:
            if self._away:
                self._posture_lbl.config(text="AUSENTE", fg=FG_DIM)
            else:
                self._posture_lbl.config(
                    text=POSTURE_LABELS.get(self._posture, ""),
                    fg=POSTURE_COLORS.get(self._posture, FG_DIM),
                )

        # Session / timer
        phase = self._session.phase
        if phase == Phase.IDLE:
            if self._session_lbl:
                self._session_lbl.config(text="Sin sesión", fg=FG_DIM)
            if self._timer_lbl:
                self._timer_lbl.config(text="")
        else:
            remaining  = self._session.remaining_secs
            mm, ss     = int(remaining // 60), int(remaining % 60)
            phase_clr  = PHASE_COLORS.get(phase, FG)
            if self._session_lbl:
                self._session_lbl.config(text=PHASE_LABELS.get(phase, ""), fg=phase_clr)
            if self._timer_lbl:
                self._timer_lbl.config(text=f"{mm:02d}:{ss:02d}", fg=phase_clr)

        # Pause button icon
        if self._pause_btn:
            self._pause_btn.config(text="▶" if self._paused else "⏸")

    # ── Progress bar ──────────────────────────────────────────────────

    def _draw_progress_bar(self) -> None:
        c = self._prog_canvas
        if not c:
            return
        c.delete("all")
        cw = c.winfo_width() or W
        c.create_rectangle(0, 0, cw, 3, fill=BG3, outline="")

        if self._calibrating:
            if self._cal_progress > 0 and self._cal_countdown == 0:
                c.create_rectangle(0, 0, int(cw * self._cal_progress), 3,
                                   fill=ACCENT, outline="")
        else:
            phase = self._session.phase
            prog  = self._session.progress
            if prog > 0 and phase != Phase.IDLE:
                bar_color = PHASE_COLORS.get(phase, AWAY_C)
                c.create_rectangle(0, 0, int(cw * prog), 3, fill=bar_color, outline="")

    # ── Dashboard panel rendering ─────────────────────────────────────

    def _draw_dashboard(self) -> None:
        snap    = self._dashboard.get_snapshot()
        events  = snap["events"]
        s_start = snap["session_start"]
        t_pause = snap["total_paused"]
        p_since = snap["paused_since"]
        c_pauses = snap["completed_pauses"]

        now = time.monotonic()

        # Elapsed label
        if self._dash_elapsed:
            if s_start is None:
                self._dash_elapsed.config(text="Calibrando…")
            else:
                cur_pause = (now - p_since) if p_since else 0.0
                elapsed   = max(0.0, now - s_start - t_pause - cur_pause)
                hh = int(elapsed // 3600)
                mm = int((elapsed % 3600) // 60)
                ss = int(elapsed % 60)
                self._dash_elapsed.config(text=f"{hh:02d}:{mm:02d}:{ss:02d}")

        # Timeline
        self._draw_mini_timeline(events, now, c_pauses, p_since)

        # Stats
        if s_start is not None:
            eff_now  = p_since if p_since else now
            cur_p2   = (now - p_since) if p_since else 0.0
            elapsed2 = max(0.0, now - s_start - t_pause - cur_p2)
            self._draw_mini_stats(events, eff_now, elapsed2)

    def _draw_mini_timeline(self, events, now, completed_pauses, paused_since) -> None:
        c = self._dash_canvas
        if not c:
            return
        c.delete("all")
        TL  = 600   # 10 minutes
        TW  = W - 24
        H   = 20
        ws  = now - TL
        eff = paused_since if paused_since else now

        c.create_rectangle(0, 0, TW, H, fill="#111111", outline="")

        for i, (ts, state) in enumerate(events):
            seg_end = events[i + 1][0] if i + 1 < len(events) else eff
            if seg_end < ws:
                continue
            x0 = max(0.0, (ts - ws) / TL * TW)
            x1 = min(float(TW), (seg_end - ws) / TL * TW)
            if x1 > x0:
                c.create_rectangle(x0, 2, x1, H - 2,
                                   fill=POSTURE_COLORS[state], outline="")

        for p_s, p_e in completed_pauses:
            if p_e < ws:
                continue
            x0 = max(0.0, (p_s - ws) / TL * TW)
            x1 = min(float(TW), (p_e - ws) / TL * TW)
            if x1 > x0:
                c.create_rectangle(x0, 2, x1, H - 2, fill="#555555", outline="")

        if paused_since:
            x0 = max(0.0, (paused_since - ws) / TL * TW)
            x1 = min(float(TW), (now - ws) / TL * TW)
            if x1 > x0:
                c.create_rectangle(x0, 2, x1, H - 2, fill="#555555", outline="")

    def _draw_mini_stats(self, events, effective_now, elapsed) -> None:
        time_in = {s: 0.0 for s in PostureState}
        for i, (ts, state) in enumerate(events):
            seg_end = events[i + 1][0] if i + 1 < len(events) else effective_now
            time_in[state] += seg_end - ts

        for state in PostureState:
            t   = time_in[state]
            pct = (t / elapsed * 100) if elapsed > 0 else 0.0
            mm, ss = int(t // 60), int(t % 60)
            if (state, "time") in self._dash_stat_labels:
                self._dash_stat_labels[(state, "time")].config(text=f"{mm:02d}:{ss:02d}")
            if (state, "pct") in self._dash_stat_labels:
                self._dash_stat_labels[(state, "pct")].config(text=f"{pct:.0f}%")

    # ── Camera refresh ────────────────────────────────────────────────

    def _refresh_camera(self) -> None:
        """Display the latest PNG frame (base64) in the camera canvas."""
        with self._cam_lock:
            png_b64 = self._cam_frame
            self._cam_frame = None
        if png_b64 is None or self._cam_canvas is None:
            return
        try:
            photo = tk.PhotoImage(data=png_b64)
            self._cam_photo = photo   # keep ref so GC doesn't collect
            self._cam_canvas.delete("all")
            self._cam_canvas.create_image(
                CAM_W // 2, CAM_H // 2, image=self._cam_photo, anchor="center",
            )
        except Exception:
            pass

    # ── Button callbacks ──────────────────────────────────────────────

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        if self._on_pause_cb:
            self._on_pause_cb(self._paused)

    def _do_recalibrate(self) -> None:
        if self._paused:
            self._paused = False
            if self._on_pause_cb:
                self._on_pause_cb(False)
        if self._on_recal:
            self._on_recal()

    def _do_stop(self) -> None:
        if messagebox.askyesno(
            "PostureProject",
            "¿Detener la sesión actual?",
            icon="warning",
        ):
            if self._on_stop:
                self._on_stop()

    def _toggle_camera(self) -> None:
        self._cam_open = not self._cam_open
        if self._cam_btn:
            self._cam_btn.configure(
                bg=ACCENT if self._cam_open else BG,
                fg="white" if self._cam_open else FG_DIM,
            )
        if self._cam_panel:
            if self._cam_open:
                self._cam_panel.pack(fill="x")
            else:
                self._cam_panel.pack_forget()
        if self._on_cam:
            self._on_cam()

    def _toggle_dashboard(self) -> None:
        self._dash_open = not self._dash_open
        if self._dash_btn:
            self._dash_btn.configure(
                bg=ACCENT if self._dash_open else BG,
                fg="white" if self._dash_open else FG_DIM,
            )
        if self._dash_panel:
            if self._dash_open:
                self._dash_panel.pack(fill="x")
            else:
                self._dash_panel.pack_forget()

    # ── Drag support ──────────────────────────────────────────────────

    def _bind_drag_recursive(self, widget: tk.Widget) -> None:
        if not isinstance(widget, (tk.Button, tk.Spinbox, tk.Entry, tk.Canvas)):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>",     self._drag_motion)
        for child in widget.winfo_children():
            self._bind_drag_recursive(child)

    def _drag_start(self, event: tk.Event) -> None:
        if self._win:
            self._drag_ox = event.x_root - self._win.winfo_x()
            self._drag_oy = event.y_root - self._win.winfo_y()

    def _drag_motion(self, event: tk.Event) -> None:
        if self._win:
            x = event.x_root - self._drag_ox
            y = event.y_root - self._drag_oy
            self._win.geometry(f"+{x}+{y}")
