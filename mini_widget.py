"""
mini_widget.py
--------------
Compact floating always-on-top widget.

Shows:
 • A posture colour strip on the left edge
 • A focus session timer (work / break countdown)
 • A preset picker when no session is active

Layout — IDLE state (~165 px tall):
 ┌──────────────────────────────────────────────┐
 │▌  Sesión de trabajo               [📊]       │
 │   [25/5 min]  [30/10 min]                    │
 │   [45/15 min] [60/15 min]                    │
 │   [Personalizar…]                            │
 └──────────────────────────────────────────────┘

Layout — WORK / BREAK state (~72 px tall):
 ┌──────────────────────────────────────────────┐
 │▌  TRABAJO            24:35  [⏸][⏭][📊][■]  │
 │   ████████████████████░░░░░░░░░░░░░░░░░░░░░  │
 └──────────────────────────────────────────────┘

Drag anywhere on screen by clicking and dragging the background.
"""
from __future__ import annotations
import tkinter as tk
from typing import Callable

from state_machine import PostureState
from focus_session import FocusSession, Phase, PRESETS

# ── Colour palette ────────────────────────────────────────────────────
BG      = "#16213E"
BG2     = "#0D1526"
FG      = "#CCCCCC"
FG_DIM  = "#4A5A7A"
AWAY_C  = "#2A2A44"

POSTURE_COLORS = {
    PostureState.GREEN:  "#2ECC71",
    PostureState.YELLOW: "#F1C40F",
    PostureState.RED:    "#E74C3C",
}
PHASE_COLORS = {
    Phase.IDLE:  AWAY_C,
    Phase.WORK:  "#2471A3",
    Phase.BREAK: "#1E8449",
}
PHASE_LABELS = {
    Phase.WORK:  "TRABAJO",
    Phase.BREAK: "DESCANSO",
}

STRIP_W = 8    # posture colour strip width (px)
W       = 290  # widget total width (px)


class MiniWidget:
    """
    Small floating session widget.

    Create the instance before the tk.Tk root exists, then call
    start(root) from the main thread once it is ready.
    """

    def __init__(
        self,
        focus_session: FocusSession,
        on_show_dashboard: Callable[[], None],
    ) -> None:
        self._session = focus_session
        self._on_dash = on_show_dashboard

        # Posture state — written from worker thread, read on main thread.
        # Plain attribute assignment is atomic in CPython; no lock needed.
        self._posture: PostureState = PostureState.GREEN
        self._away: bool = False

        # Tk widget references (created in start())
        self._win:         tk.Toplevel | None = None
        self._strip:       tk.Frame    | None = None
        self._phase_lbl:   tk.Label    | None = None
        self._timer_lbl:   tk.Label    | None = None
        self._pause_btn:   tk.Button   | None = None
        self._prog_canvas: tk.Canvas   | None = None
        self._picker_frame:tk.Frame    | None = None
        self._active_frame:tk.Frame    | None = None

        # Internal state
        self._last_phase: Phase = Phase.IDLE
        self._drag_ox = 0
        self._drag_oy = 0

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self, root: tk.Tk) -> None:
        """Build the widget.  Must be called from the main thread."""
        sw = root.winfo_screenwidth()

        self._win = tk.Toplevel(root)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.attributes("-alpha", 0.93)
        self._win.configure(bg=BG2)
        self._win.resizable(False, False)
        self._win.geometry(f"{W}+{sw - W - 24}+20")

        self._build_ui()
        self._show_picker()
        self._schedule_draw()

    def close(self) -> None:
        if self._win:
            try:
                self._win.after(0, self._win.destroy)
            except Exception:
                pass
            self._win = None

    # ── Posture state API (called from worker thread) ─────────────────

    def update_posture(self, state: PostureState) -> None:
        self._posture = state
        self._away    = False

    def update_away(self) -> None:
        self._away = True

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        w = self._win
        btn = dict(relief="flat", cursor="hand2", bd=0,
                   activebackground="#2A3A5A")

        # ── Outer frame: strip (left) + content (right) ───────────────
        outer = tk.Frame(w, bg=BG2)
        outer.pack(fill="both", expand=True)

        self._strip = tk.Frame(outer, width=STRIP_W, bg=AWAY_C)
        self._strip.pack(side="left", fill="y")
        self._strip.pack_propagate(False)

        content = tk.Frame(outer, bg=BG2)
        content.pack(side="left", fill="both", expand=True)

        # Bind drag on the outer + content frames
        for widget in (outer, content):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>",     self._drag_motion)

        # ── IDLE: preset picker ───────────────────────────────────────
        self._picker_frame = tk.Frame(content, bg=BG2)

        # Title row
        title_row = tk.Frame(self._picker_frame, bg=BG2)
        title_row.pack(fill="x", padx=8, pady=(8, 6))
        title_row.bind("<ButtonPress-1>", self._drag_start)
        title_row.bind("<B1-Motion>",     self._drag_motion)

        tk.Label(
            title_row, text="Sesión de trabajo", bg=BG2, fg=FG,
            font=("Consolas", 9, "bold"),
        ).pack(side="left")

        tk.Button(
            title_row, text="📊", bg=BG2, fg=FG_DIM,
            font=("Consolas", 10), command=self._on_dash, **btn,
        ).pack(side="right", padx=2)

        # Preset buttons (2-column grid)
        grid = tk.Frame(self._picker_frame, bg=BG2)
        grid.pack(fill="x", padx=6, pady=(0, 6))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        preset_btn_cfg = dict(
            bg="#1A2B40", fg=FG, activebackground="#2471A3",
            activeforeground="white", relief="flat", cursor="hand2",
            font=("Consolas", 8), padx=4, pady=6, bd=0,
        )

        for i, (label, w_s, b_s) in enumerate(PRESETS):
            col = i % 2
            row = i // 2
            tk.Button(
                grid, text=label,
                command=lambda ws=w_s, bs=b_s: self._start_session(ws, bs),
                **preset_btn_cfg,
            ).grid(row=row, column=col, padx=3, pady=2, sticky="ew")

        # Custom preset button (full width, last row)
        tk.Button(
            grid, text="Personalizar…",
            command=self._open_custom_dialog,
            bg="#111E2E", fg=FG_DIM, activebackground="#2471A3",
            activeforeground="white", relief="flat", cursor="hand2",
            font=("Consolas", 8), padx=4, pady=5, bd=0,
        ).grid(row=len(PRESETS) // 2 + 1, column=0, columnspan=2,
               padx=3, pady=(2, 4), sticky="ew")

        # ── ACTIVE: timer + controls ──────────────────────────────────
        self._active_frame = tk.Frame(content, bg=BG2)

        row1 = tk.Frame(self._active_frame, bg=BG2)
        row1.pack(fill="x", padx=8, pady=(8, 2))
        row1.bind("<ButtonPress-1>", self._drag_start)
        row1.bind("<B1-Motion>",     self._drag_motion)

        self._phase_lbl = tk.Label(
            row1, text="TRABAJO", bg=BG2, fg=PHASE_COLORS[Phase.WORK],
            font=("Consolas", 9, "bold"), width=9, anchor="w",
        )
        self._phase_lbl.pack(side="left")

        self._timer_lbl = tk.Label(
            row1, text="25:00", bg=BG2, fg="white",
            font=("Consolas", 15, "bold"),
        )
        self._timer_lbl.pack(side="left", padx=(0, 6))

        # Right-side control buttons: stop, dash, skip, pause
        for text, cmd in [
            ("■",  self._stop_session),
            ("📊", self._on_dash),
            ("⏭", self._session.skip),
        ]:
            tk.Button(
                row1, text=text, bg=BG2, fg=FG_DIM,
                font=("Consolas", 10), command=cmd, **btn,
            ).pack(side="right", padx=1)

        self._pause_btn = tk.Button(
            row1, text="⏸", bg=BG2, fg=FG_DIM,
            font=("Consolas", 10), command=self._toggle_pause, **btn,
        )
        self._pause_btn.pack(side="right", padx=1)

        # Progress bar
        self._prog_canvas = tk.Canvas(
            self._active_frame, height=5, bg=BG2, highlightthickness=0,
        )
        self._prog_canvas.pack(fill="x", padx=8, pady=(2, 10))

    # ── Layout helpers ────────────────────────────────────────────────

    def _show_picker(self) -> None:
        if self._active_frame:
            self._active_frame.pack_forget()
        if self._picker_frame:
            self._picker_frame.pack(fill="both", expand=True)

    def _show_active(self) -> None:
        if self._picker_frame:
            self._picker_frame.pack_forget()
        if self._active_frame:
            self._active_frame.pack(fill="both", expand=True)

    # ── Draw loop ─────────────────────────────────────────────────────

    def _schedule_draw(self) -> None:
        self._draw()
        if self._win:
            self._win.after(250, self._schedule_draw)

    def _draw(self) -> None:
        phase = self._session.phase

        # Switch layout on phase change
        if phase != self._last_phase:
            self._last_phase = phase
            if phase == Phase.IDLE:
                self._show_picker()
            else:
                self._show_active()

        # Posture colour strip
        if self._strip:
            strip_color = (
                AWAY_C if self._away
                else POSTURE_COLORS.get(self._posture, AWAY_C)
            )
            self._strip.configure(bg=strip_color)

        if phase == Phase.IDLE:
            return

        # Timer
        remaining = self._session.remaining_secs
        mm = int(remaining // 60)
        ss = int(remaining % 60)
        if self._timer_lbl:
            self._timer_lbl.config(text=f"{mm:02d}:{ss:02d}")

        # Phase label + colour
        if self._phase_lbl:
            label = PHASE_LABELS.get(phase, "")
            color = PHASE_COLORS.get(phase, FG)
            self._phase_lbl.config(text=label, fg=color)

        # Pause button icon
        if self._pause_btn:
            self._pause_btn.config(
                text="▶" if self._session.is_paused else "⏸"
            )

        # Progress bar
        c = self._prog_canvas
        if c:
            c.delete("all")
            cw = c.winfo_width() or (W - STRIP_W - 16)
            fill_w = int(cw * self._session.progress)
            c.create_rectangle(0, 0, cw, 5, fill="#1A2B40", outline="")
            bar_color = PHASE_COLORS.get(phase, AWAY_C)
            if fill_w > 0:
                c.create_rectangle(0, 0, fill_w, 5, fill=bar_color, outline="")

    # ── Session callbacks ─────────────────────────────────────────────

    def _start_session(self, work_secs: int, break_secs: int) -> None:
        self._session.start(work_secs, break_secs)

    def _stop_session(self) -> None:
        self._session.stop()

    def _toggle_pause(self) -> None:
        if self._session.is_paused:
            self._session.resume()
        else:
            self._session.pause()

    def _open_custom_dialog(self) -> None:
        """Small dialog to set a custom work/break duration."""
        if self._win is None:
            return

        dlg = tk.Toplevel(self._win)
        dlg.title("Sesión personalizada")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.geometry("250x148")

        # Center near the widget
        wx = self._win.winfo_x()
        wy = self._win.winfo_y()
        dlg.geometry(f"+{wx}+{wy + 30}")

        lbl_cfg = dict(bg=BG, fg=FG, font=("Consolas", 9))
        entry_cfg = dict(bg="#1A2B40", fg=FG, relief="flat",
                         insertbackground=FG, width=6)

        tk.Label(dlg, text="Trabajo (min):", **lbl_cfg).grid(
            row=0, column=0, padx=14, pady=(16, 4), sticky="w")
        work_var = tk.IntVar(value=25)
        tk.Spinbox(dlg, from_=1, to=180, textvariable=work_var,
                   **entry_cfg).grid(row=0, column=1, padx=8)

        tk.Label(dlg, text="Descanso (min):", **lbl_cfg).grid(
            row=1, column=0, padx=14, pady=4, sticky="w")
        break_var = tk.IntVar(value=5)
        tk.Spinbox(dlg, from_=1, to=60, textvariable=break_var,
                   **entry_cfg).grid(row=1, column=1, padx=8)

        def _ok():
            w = max(1, work_var.get())
            b = max(1, break_var.get())
            dlg.destroy()
            self._session.start(w * 60, b * 60)

        tk.Button(
            dlg, text="Iniciar sesión",
            bg="#2471A3", fg="white", relief="flat",
            font=("Consolas", 9, "bold"), padx=14, pady=7,
            cursor="hand2", command=_ok,
        ).grid(row=2, column=0, columnspan=2, pady=14)

    # ── Drag support ──────────────────────────────────────────────────

    def _drag_start(self, event: tk.Event) -> None:
        if self._win:
            self._drag_ox = event.x_root - self._win.winfo_x()
            self._drag_oy = event.y_root - self._win.winfo_y()

    def _drag_motion(self, event: tk.Event) -> None:
        if self._win:
            x = event.x_root - self._drag_ox
            y = event.y_root - self._drag_oy
            self._win.geometry(f"+{x}+{y}")
