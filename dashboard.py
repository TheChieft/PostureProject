"""
dashboard.py
------------
Session dashboard window: timeline, live stats, and session controls.

Runs as a tk.Toplevel off the same tk.Tk root as OverlayWindow.
All data updates are thread-safe (worker thread writes via add_event /
session_started; tkinter draws from its own event loop via _schedule_draw).
"""

from __future__ import annotations
import time
import threading
import tkinter as tk
from typing import Callable

from state_machine import PostureState

# Colours matching the overlay bar
STATE_COLORS = {
    PostureState.GREEN:  "#2ECC71",
    PostureState.YELLOW: "#F1C40F",
    PostureState.RED:    "#E74C3C",
}
STATE_DIM = {          # Muted version for header labels
    PostureState.GREEN:  "#1A7A45",
    PostureState.YELLOW: "#8A7008",
    PostureState.RED:    "#8A1F1F",
}

TIMELINE_SECONDS = 600   # 10 minutes of visible history
UPDATE_MS = 500           # Dashboard refresh rate (ms)
BG = "#16213E"
BG2 = "#0F1826"
PAUSE_COLOR = "#4A4A6A"  # Grey-blue segment shown while session is paused


class DashboardWindow:
    """
    Control + timeline window.

    Constructor args:
        on_recalibrate  called (no args) when user clicks Recalibrar
        on_pause        called with (paused: bool) on Pausar / Reanudar
        on_stop         called (no args) when user clicks Detener or closes window
    """

    def __init__(self,
                 on_recalibrate: Callable[[], None],
                 on_pause: Callable[[bool], None],
                 on_stop: Callable[[], None]):
        self._on_recalibrate = on_recalibrate
        self._on_pause = on_pause
        self._on_stop = on_stop

        self._lock = threading.Lock()
        # List of (monotonic_timestamp, PostureState) — one entry per state change
        self._events: list[tuple[float, PostureState]] = []
        self._session_start: float | None = None
        self._paused = False
        self._paused_since: float | None = None  # monotonic time when pause started

        # Tk widgets (created in start())
        self._win: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None
        self._time_label: tk.Label | None = None
        self._pause_btn: tk.Button | None = None
        # (state, col) → Label;  col: 1=time, 2=pct, 3=entries
        self._stat_labels: dict[tuple[PostureState, int], tk.Label] = {}

    # ------------------------------------------------------------------
    # Public API — callable from any thread
    # ------------------------------------------------------------------

    def start(self, root: tk.Tk) -> None:
        """Create the Toplevel.  Must be called from the main thread."""
        self._win = tk.Toplevel(root)
        self._win.title("PostureProject — Dashboard")
        self._win.geometry("480x320")
        self._win.resizable(False, False)
        self._win.configure(bg=BG)
        self._win.protocol("WM_DELETE_WINDOW", self._on_stop)
        self._build_ui()
        self._schedule_draw()

    def session_started(self) -> None:
        """Call from worker when calibration completes and monitoring begins."""
        with self._lock:
            self._session_start = time.monotonic()
            self._events.clear()

    def add_event(self, state: PostureState) -> None:
        """Thread-safe.  Call from worker on every state transition."""
        with self._lock:
            self._events.append((time.monotonic(), state))

    def set_paused(self, paused: bool) -> None:
        """Thread-safe.  Stores pause start time for timeline rendering."""
        with self._lock:
            self._paused_since = time.monotonic() if paused else None

    def close(self) -> None:
        """Destroy the window.  Safe to call from any thread."""
        if self._win:
            try:
                self._win.after(0, self._win.destroy)
            except Exception:
                pass
            self._win = None

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        w = self._win

        # ── Header row ──────────────────────────────────────────────
        header = tk.Frame(w, bg=BG)
        header.pack(fill="x", padx=16, pady=(12, 2))
        tk.Label(header, text="Dashboard de sesión", bg=BG, fg="#DDD",
                 font=("Consolas", 11, "bold")).pack(side="left")
        self._time_label = tk.Label(header, text="Calibrando...", bg=BG,
                                     fg="#666", font=("Consolas", 10))
        self._time_label.pack(side="right")

        # ── Timeline ─────────────────────────────────────────────────
        tk.Label(w, text="Historial (últimos 10 min) →  ahora",
                 bg=BG, fg="#444", font=("Consolas", 7)).pack(anchor="e", padx=18)
        self._canvas = tk.Canvas(w, width=448, height=28, bg=BG2,
                                  highlightthickness=1, highlightbackground="#1E2E50")
        self._canvas.pack(padx=16, pady=(0, 10))

        # ── Stats grid ───────────────────────────────────────────────
        grid = tk.Frame(w, bg=BG)
        grid.pack(fill="x", padx=16)

        col_widths = [9, 9, 7, 9]
        headers = ["Estado", "Tiempo", "%", "Entradas"]
        for c, (h, cw) in enumerate(zip(headers, col_widths)):
            tk.Label(grid, text=h, bg=BG, fg="#444",
                     font=("Consolas", 8), width=cw, anchor="w"
                     ).grid(row=0, column=c, sticky="w")

        for r, state in enumerate(PostureState, start=1):
            color = STATE_COLORS[state]
            tk.Label(grid, text=f"  {state.name}", bg=BG, fg=color,
                     font=("Consolas", 9, "bold"), width=col_widths[0], anchor="w"
                     ).grid(row=r, column=0, sticky="w")
            for c in range(1, 4):
                lbl = tk.Label(grid, text="—", bg=BG, fg="#AAA",
                               font=("Consolas", 9), width=col_widths[c], anchor="w")
                lbl.grid(row=r, column=c, sticky="w")
                self._stat_labels[(state, c)] = lbl

        # ── Controls ─────────────────────────────────────────────────
        ctrl = tk.Frame(w, bg=BG)
        ctrl.pack(pady=(14, 12))
        btn = dict(font=("Consolas", 9, "bold"), relief="flat",
                   padx=14, pady=7, cursor="hand2")

        tk.Button(ctrl, text="Recalibrar", bg="#2471A3", fg="white",
                  command=self._click_recalibrate, **btn).pack(side="left", padx=6)
        self._pause_btn = tk.Button(ctrl, text="Pausar", bg="#CA6F1E", fg="white",
                                     command=self._toggle_pause, **btn)
        self._pause_btn.pack(side="left", padx=6)
        tk.Button(ctrl, text="Detener", bg="#922B21", fg="white",
                  command=self._on_stop, **btn).pack(side="left", padx=6)

    # ------------------------------------------------------------------
    # Draw loop
    # ------------------------------------------------------------------

    def _schedule_draw(self) -> None:
        self._draw()
        if self._win:
            self._win.after(UPDATE_MS, self._schedule_draw)

    def _draw(self) -> None:
        if not self._win:
            return
        now = time.monotonic()

        with self._lock:
            events = list(self._events)
            session_start = self._session_start

        # Session timer
        if session_start is None:
            if self._time_label:
                self._time_label.config(text="Calibrando...")
            self._draw_timeline([], now)
            return

        elapsed = now - session_start
        hh = int(elapsed // 3600)
        mm = int((elapsed % 3600) // 60)
        ss = int(elapsed % 60)
        if self._time_label:
            self._time_label.config(text=f"{hh:02d}:{mm:02d}:{ss:02d}")

        self._draw_timeline(events, now)
        self._draw_stats(events, now, elapsed)

    def _draw_timeline(self, events: list[tuple[float, PostureState]],
                       now: float) -> None:
        c = self._canvas
        if c is None:
            return
        c.delete("all")
        W, H = 448, 28
        win_start = now - TIMELINE_SECONDS

        with self._lock:
            paused_since = self._paused_since

        # When paused, real segments stop at pause time; grey fills the rest
        effective_now = paused_since if paused_since is not None else now

        c.create_rectangle(0, 0, W, H, fill=BG2, outline="")

        for i, (ts, state) in enumerate(events):
            seg_end = events[i + 1][0] if i + 1 < len(events) else effective_now
            if seg_end < win_start:
                continue
            x0 = max(0.0, (ts - win_start) / TIMELINE_SECONDS * W)
            x1 = min(float(W), (seg_end - win_start) / TIMELINE_SECONDS * W)
            if x1 > x0:
                c.create_rectangle(x0, 3, x1, H - 3,
                                   fill=STATE_COLORS[state], outline="")

        # Pause segment (grey-blue from pause_start to now)
        if paused_since is not None:
            x0 = max(0.0, (paused_since - win_start) / TIMELINE_SECONDS * W)
            x1 = min(float(W), (now - win_start) / TIMELINE_SECONDS * W)
            if x1 > x0:
                c.create_rectangle(x0, 3, x1, H - 3, fill=PAUSE_COLOR, outline="")
                if x1 - x0 > 30:
                    c.create_text((x0 + x1) / 2, H // 2, text="PAUSA",
                                  fill="#AAA", font=("Consolas", 7, "bold"))

        # Tick marks at 2, 5, 8 minutes ago
        for mins_ago in (2, 5, 8):
            x = W * (1.0 - mins_ago * 60 / TIMELINE_SECONDS)
            if 0 < x < W:
                c.create_line(x, 0, x, H, fill="#1E2E50", dash=(2, 3))
                c.create_text(x - 2, 2, text=f"-{mins_ago}m",
                              fill="#334", font=("Consolas", 6), anchor="nw")

    def _draw_stats(self, events: list[tuple[float, PostureState]],
                    now: float, elapsed: float) -> None:
        time_in: dict[PostureState, float] = {s: 0.0 for s in PostureState}
        entries: dict[PostureState, int] = {s: 0 for s in PostureState}

        for i, (ts, state) in enumerate(events):
            seg_end = events[i + 1][0] if i + 1 < len(events) else now
            time_in[state] += seg_end - ts
            entries[state] += 1

        for state in PostureState:
            t = time_in[state]
            pct = (t / elapsed * 100) if elapsed > 0 else 0.0
            mm, ss = int(t // 60), int(t % 60)
            self._stat_labels[(state, 1)].config(text=f"{mm:02d}:{ss:02d}")
            self._stat_labels[(state, 2)].config(text=f"{pct:.0f}%")
            self._stat_labels[(state, 3)].config(text=str(entries[state]))

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self._update_pause_btn()
        self.set_paused(self._paused)
        self._on_pause(self._paused)

    def _click_recalibrate(self) -> None:
        """Recalibrate: also resumes if currently paused."""
        if self._paused:
            self._paused = False
            self._update_pause_btn()
            self.set_paused(False)
            self._on_pause(False)
        self._on_recalibrate()

    def _update_pause_btn(self) -> None:
        if self._pause_btn:
            self._pause_btn.config(
                text="Reanudar" if self._paused else "Pausar",
                bg="#1E8449" if self._paused else "#CA6F1E",
            )
