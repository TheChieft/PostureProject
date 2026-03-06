"""
ui_overlay.py
-------------
Always-on-top vertical bar overlay on the left edge of the screen.
Uses tkinter (bundled with CPython) — no extra dependencies needed.

Visual design
-------------
- Thin strip (BAR_WIDTH pixels) anchored to the left of the primary display
- Full screen height
- Colour / thickness change per PostureState:
    GREEN  → green,  narrow  (BAR_WIDTH * 0.4)
    YELLOW → yellow, medium  (BAR_WIDTH * 0.7)
    RED    → red,    full    (BAR_WIDTH)
- A small semi-transparent info panel shows score + FPS when DEBUG=True
- Calibration phase: blue progress bar fills from bottom to top

Threading note:
  tkinter must run on the main thread.  The overlay is updated via
  the after() scheduler so it never blocks the caller.
"""

from __future__ import annotations
import logging
import time
import tkinter as tk
from tkinter import font as tkfont
from typing import TYPE_CHECKING

from state_machine import PostureState

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Layout constants
# ------------------------------------------------------------------
BAR_WIDTH = 28          # Maximum bar width in pixels
MARGIN = 0              # Offset from left screen edge
UPDATE_MS = 80          # Redraw interval (~12 fps UI refresh)

STATE_COLORS = {
    PostureState.GREEN:  "#2ECC71",
    PostureState.YELLOW: "#F1C40F",
    PostureState.RED:    "#E74C3C",
}

STATE_WIDTH_RATIO = {
    PostureState.GREEN:  0.4,
    PostureState.YELLOW: 0.7,
    PostureState.RED:    1.0,
}

CALIBRATION_COLOR = "#3498DB"


class OverlayWindow:
    """
    Creates and manages the always-on-top overlay strip.

    The window is a narrow transparent strip covering full screen height
    on the left edge.  It draws onto a Canvas.
    """

    def __init__(self, debug: bool = False, x_offset: int = 0):
        self.debug = debug
        self._x_offset = x_offset
        self._root: tk.Tk | None = None
        self._canvas: tk.Canvas | None = None

        # Runtime state (updated from main thread via update())
        self._state = PostureState.GREEN
        self._score = 0.0
        self._fps = 0.0
        self._calibrating = False
        self._calib_progress = 0.0   # 0.0 – 1.0
        self._calib_samples = 0

        self._screen_w = 0
        self._screen_h = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Create the Tk root window and enter the main loop."""
        self._root = tk.Tk()
        self._screen_w = self._root.winfo_screenwidth()
        self._screen_h = self._root.winfo_screenheight()

        # Window geometry: narrow strip, full height, at x_offset
        self._root.geometry(f"{BAR_WIDTH}x{self._screen_h}+{self._x_offset + MARGIN}+0")
        self._root.overrideredirect(True)        # No title bar
        self._root.attributes("-topmost", True)  # Always on top
        self._root.attributes("-alpha", 0.85)    # Slight transparency
        self._root.configure(bg="black")
        self._root.resizable(False, False)

        self._canvas = tk.Canvas(
            self._root,
            width=BAR_WIDTH,
            height=self._screen_h,
            bg="black",
            highlightthickness=0,
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Debug font
        if self.debug:
            try:
                self._dbg_font = tkfont.Font(family="Consolas", size=7)
            except Exception:
                self._dbg_font = tkfont.Font(size=7)

        self._schedule_draw()
        logger.info("Overlay window started (%dx%d strip).",
                    BAR_WIDTH, self._screen_h)
        self._root.mainloop()

    def close(self):
        """Destroy the overlay window."""
        if self._root:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass
            self._root = None
        logger.info("Overlay window closed.")

    # ------------------------------------------------------------------
    # State updates (called from worker thread via thread-safe after())
    # ------------------------------------------------------------------

    def update_posture(self, state: PostureState, score: float, fps: float):
        """Update displayed posture state. Thread-safe via after()."""
        self._state = state
        self._score = score
        self._fps = fps
        self._calibrating = False

    def update_calibration(self, progress: float, sample_count: int):
        """Show calibration progress bar. Thread-safe via after()."""
        self._calibrating = True
        self._calib_progress = max(0.0, min(1.0, progress))
        self._calib_samples = sample_count

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _schedule_draw(self):
        """Schedule the next redraw via tkinter's event loop."""
        self._draw()
        if self._root:
            self._root.after(UPDATE_MS, self._schedule_draw)

    def _draw(self):
        c = self._canvas
        if c is None:
            return
        c.delete("all")

        h = self._screen_h

        if self._calibrating:
            self._draw_calibration(c, h)
        else:
            self._draw_posture_bar(c, h)

        if self.debug:
            self._draw_debug(c)

    def _draw_posture_bar(self, c: tk.Canvas, h: int):
        """Draw the coloured posture indicator bar."""
        color = STATE_COLORS[self._state]
        ratio = STATE_WIDTH_RATIO[self._state]
        bar_w = max(2, int(BAR_WIDTH * ratio))

        # Background
        c.create_rectangle(0, 0, BAR_WIDTH, h, fill="black", outline="")
        # Indicator bar
        c.create_rectangle(0, 0, bar_w, h, fill=color, outline="")

        # Subtle state label at top
        label_map = {
            PostureState.GREEN:  "▲",
            PostureState.YELLOW: "!",
            PostureState.RED:    "✕",
        }
        label_color = "white" if self._state == PostureState.RED else "black"
        try:
            c.create_text(
                bar_w // 2, 14,
                text=label_map[self._state],
                fill=label_color,
                font=("Arial", 9, "bold"),
            )
        except Exception:
            pass

    def _draw_calibration(self, c: tk.Canvas, h: int):
        """Draw blue progress bar filling from bottom upward."""
        fill_h = int(h * self._calib_progress)
        # Background
        c.create_rectangle(0, 0, BAR_WIDTH, h, fill="#1A1A2E", outline="")
        # Progress fill
        c.create_rectangle(
            0, h - fill_h, BAR_WIDTH, h,
            fill=CALIBRATION_COLOR, outline=""
        )
        # "CAL" text
        try:
            c.create_text(
                BAR_WIDTH // 2, 20,
                text="C\nA\nL",
                fill="white",
                font=("Arial", 7, "bold"),
                justify=tk.CENTER,
            )
        except Exception:
            pass

    def _draw_debug(self, c: tk.Canvas):
        """Tiny debug text panel at the bottom of the bar."""
        lines = [
            f"{self._state.name[:3]}",
            f"S:{self._score:.2f}",
            f"F:{self._fps:.0f}",
        ]
        y = self._screen_h - 50
        for line in lines:
            c.create_text(
                BAR_WIDTH // 2, y,
                text=line,
                fill="white",
                font=self._dbg_font,
            )
            y += 14
