"""
launcher.py
-----------
Startup / mode-selection window for PostureProject.

Shows two mode cards:
  • Focus session (Sesión de concentración) — lets the user pick work/break durations
  • Posture-only  (Solo postura)             — monitoring without a timer

Calls on_start(mode, work_secs, break_secs) when the user clicks Iniciar.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable

from focus_session import PRESETS
from utils import center_window

# ── Windows 11 dark theme ──────────────────────────────────────────────
BG      = "#1e1e1e"
BG2     = "#252525"
BG3     = "#2d2d2d"
FG      = "#e4e4e4"
FG_DIM  = "#888888"
ACCENT  = "#0078D4"
FONT    = "Segoe UI Variable"

_W, _H = 580, 440


class LauncherWindow:
    """
    The startup window (owns the tk.Tk root / mainloop).

    Call start(on_start) to display the window and enter the event loop.
    on_start(mode, work_secs, break_secs) is invoked when the user confirms.
    """

    def __init__(self) -> None:
        self._root: tk.Tk | None = None
        self._mode_var: tk.StringVar | None = None
        self._work_var: tk.IntVar | None = None
        self._break_var: tk.IntVar | None = None
        self._preset_frame: tk.Frame | None = None
        self._on_start_cb: Callable[[str, int, int], None] | None = None

    # ── Public API ────────────────────────────────────────────────────

    @property
    def root(self) -> tk.Tk:
        if self._root is None:
            raise RuntimeError("LauncherWindow.root accessed before start()")
        return self._root

    def start(self, on_start: Callable[[str, int, int], None]) -> None:
        """Build the window and enter mainloop (blocks until app exits)."""
        self._on_start_cb = on_start
        self._root = tk.Tk()
        self._root.title("PostureProject")
        self._root.configure(bg=BG)
        self._root.resizable(False, False)

        # Try to load icon
        try:
            self._root.iconbitmap("assets/icon.ico")
        except Exception:
            pass

        center_window(self._root, _W, _H)
        self._build_ui()
        self._root.bind("<Return>", lambda _e: self._do_start())
        self._root.mainloop()

    def hide(self) -> None:
        """Minimize launcher to taskbar so the app remains visible to the user."""
        if self._root:
            try:
                self._root.iconify()
            except Exception:
                pass

    def show(self) -> None:
        """Make the launcher window visible again."""
        if self._root:
            try:
                self._root.deiconify()
                self._root.lift()
                self._root.focus_force()
            except Exception:
                pass

    def close(self) -> None:
        """Destroy the launcher and exit the event loop."""
        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass
            self._root = None

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = self._root

        root.columnconfigure(0, weight=1)

        # ── Branding ─────────────────────────────────────────────────
        brand = tk.Frame(root, bg=BG)
        brand.grid(row=0, column=0, pady=(28, 8))

        tk.Label(
            brand, text="PostureProject",
            bg=BG, fg="white",
            font=(FONT, 22, "bold"),
        ).pack()
        tk.Label(
            brand, text="Cuida tu postura mientras trabajas",
            bg=BG, fg=FG_DIM,
            font=(FONT, 10),
        ).pack(pady=(2, 0))

        # ── Separator ────────────────────────────────────────────────
        sep = tk.Frame(root, height=1, bg=BG3)
        sep.grid(row=1, column=0, sticky="ew", padx=40, pady=(0, 20))

        # ── Mode cards ───────────────────────────────────────────────
        self._mode_var = tk.StringVar(value="focus")

        cards_row = tk.Frame(root, bg=BG)
        cards_row.grid(row=2, column=0, sticky="ew", padx=40)

        self._card_focus = self._make_card(
            cards_row,
            emoji="🎯",
            title="Sesión de concentración",
            desc="Temporizador Pomodoro + seguimiento de postura",
            value="focus",
        )
        self._card_focus.pack(side="left", expand=True, fill="both", padx=(0, 8))

        self._card_posture = self._make_card(
            cards_row,
            emoji="👁",
            title="Solo postura",
            desc="Solo monitoreo de postura, sin temporizador",
            value="posture",
        )
        self._card_posture.pack(side="left", expand=True, fill="both", padx=(8, 0))

        # Refresh card highlight when mode changes
        self._mode_var.trace_add("write", lambda *_: self._refresh_cards())
        self._refresh_cards()

        # ── Preset / custom section (only shown in focus mode) ────────
        self._preset_outer = tk.Frame(root, bg=BG)
        self._preset_outer.grid(row=3, column=0, sticky="ew", padx=40, pady=(16, 0))

        self._preset_frame = tk.Frame(self._preset_outer, bg=BG)
        self._preset_frame.pack(fill="x")

        tk.Label(
            self._preset_frame,
            text="Duración de la sesión",
            bg=BG, fg=FG_DIM,
            font=(FONT, 8),
        ).pack(anchor="w", pady=(0, 6))

        # Preset buttons (2 columns)
        self._selected_preset: tuple[int, int] | None = None
        self._work_var  = tk.IntVar(value=25)
        self._break_var = tk.IntVar(value=5)

        grid = tk.Frame(self._preset_frame, bg=BG)
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        self._preset_btns: list[tk.Button] = []
        for i, (label, w_s, b_s) in enumerate(PRESETS):
            col = i % 2
            row = i // 2
            btn = tk.Button(
                grid, text=label,
                bg=BG3, fg=FG,
                activebackground=ACCENT, activeforeground="white",
                relief="flat", cursor="hand2",
                font=(FONT, 9), padx=6, pady=7, bd=0,
                command=lambda ws=w_s, bs=b_s, lbl=label: self._select_preset(ws, bs, lbl),
            )
            btn.grid(row=row, column=col, padx=3, pady=3, sticky="ew")
            self._preset_btns.append(btn)

        # Select first preset by default
        if PRESETS:
            first_ws, first_bs = PRESETS[0][1], PRESETS[0][2]
            self._select_preset(first_ws, first_bs, PRESETS[0][0])

        # Custom row
        custom_row = tk.Frame(self._preset_frame, bg=BG)
        custom_row.pack(fill="x", pady=(6, 0))

        tk.Label(
            custom_row, text="Personalizar:",
            bg=BG, fg=FG_DIM, font=(FONT, 8),
        ).pack(side="left", padx=(2, 8))

        tk.Label(custom_row, text="Trabajo (min)", bg=BG, fg=FG_DIM,
                 font=(FONT, 8)).pack(side="left")
        tk.Spinbox(
            custom_row, from_=1, to=240, textvariable=self._work_var,
            width=5, bg=BG3, fg=FG, relief="flat",
            insertbackground=FG, buttonbackground=BG3,
            command=self._on_custom_change,
        ).pack(side="left", padx=(2, 12))

        tk.Label(custom_row, text="Descanso (min)", bg=BG, fg=FG_DIM,
                 font=(FONT, 8)).pack(side="left")
        tk.Spinbox(
            custom_row, from_=1, to=60, textvariable=self._break_var,
            width=5, bg=BG3, fg=FG, relief="flat",
            insertbackground=FG, buttonbackground=BG3,
            command=self._on_custom_change,
        ).pack(side="left", padx=(2, 0))

        # ── Iniciar button ────────────────────────────────────────────
        btn_frame = tk.Frame(root, bg=BG)
        btn_frame.grid(row=4, column=0, pady=(20, 0))

        tk.Button(
            btn_frame, text="Iniciar",
            bg=ACCENT, fg="white",
            font=(FONT, 12, "bold"),
            relief="flat", cursor="hand2",
            padx=48, pady=10,
            activebackground="#005A9E", activeforeground="white",
            command=self._do_start,
        ).pack()

        tk.Label(
            btn_frame, text="o presiona Enter",
            bg=BG, fg=FG_DIM, font=(FONT, 8),
        ).pack(pady=(4, 0))

        # ── Privacy footer ────────────────────────────────────────────
        privacy = tk.Frame(root, bg=BG)
        privacy.grid(row=5, column=0, pady=(14, 16))
        tk.Label(
            privacy,
            text="🔒  Todo se procesa localmente · Sin conexión a internet · Sin envío de datos",
            bg=BG, fg=FG_DIM, font=(FONT, 8),
        ).pack()

    # ── Card helpers ──────────────────────────────────────────────────

    def _make_card(self, parent: tk.Frame, emoji: str, title: str,
                   desc: str, value: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG3, cursor="hand2",
                         relief="flat", bd=2)

        tk.Label(frame, text=emoji, bg=BG3, fg=FG,
                 font=("Segoe UI Emoji", 18)).pack(pady=(14, 2))
        tk.Label(frame, text=title, bg=BG3, fg="white",
                 font=(FONT, 9, "bold"), wraplength=200).pack()
        tk.Label(frame, text=desc, bg=BG3, fg=FG_DIM,
                 font=(FONT, 8), wraplength=200).pack(pady=(2, 14))

        # Click anywhere on card to select mode
        for widget in [frame] + frame.winfo_children():
            widget.bind("<Button-1>", lambda _e, v=value: self._set_mode(v))

        return frame

    def _set_mode(self, mode: str) -> None:
        if self._mode_var:
            self._mode_var.set(mode)
        # Show/hide preset section using grid_remove so order is preserved
        if mode == "focus":
            self._preset_outer.grid()
        else:
            self._preset_outer.grid_remove()

    def _refresh_cards(self) -> None:
        mode = self._mode_var.get() if self._mode_var else "focus"
        for card, value in [(self._card_focus, "focus"),
                            (self._card_posture, "posture")]:
            active = mode == value
            highlight = ACCENT if active else BG3
            self._recolor_frame(card, highlight)

    def _recolor_frame(self, frame: tk.Frame, color: str) -> None:
        frame.configure(bg=color)
        for child in frame.winfo_children():
            try:
                child.configure(bg=color)
            except Exception:
                pass

    # ── Preset selection ──────────────────────────────────────────────

    def _select_preset(self, work_secs: int, break_secs: int, label: str) -> None:
        self._selected_preset = (work_secs, break_secs)
        if self._work_var:
            self._work_var.set(work_secs // 60)
        if self._break_var:
            self._break_var.set(break_secs // 60)
        # Highlight selected preset button
        for i, (lbl, _w, _b) in enumerate(PRESETS):
            if i < len(self._preset_btns):
                is_sel = (lbl == label)
                self._preset_btns[i].configure(
                    bg=ACCENT if is_sel else BG3,
                    fg="white" if is_sel else FG,
                )

    def _on_custom_change(self) -> None:
        """Called when spinbox value changes — deselect preset buttons."""
        for btn in self._preset_btns:
            btn.configure(bg=BG3, fg=FG)
        self._selected_preset = None

    # ── Launch ────────────────────────────────────────────────────────

    def _do_start(self) -> None:
        if self._on_start_cb is None:
            return
        mode = self._mode_var.get() if self._mode_var else "posture"
        if mode == "focus":
            work_secs  = max(1, (self._work_var.get()  if self._work_var  else 25)) * 60
            break_secs = max(1, (self._break_var.get() if self._break_var else 5))  * 60
        else:
            work_secs  = 25 * 60
            break_secs =  5 * 60
        self.hide()
        self._on_start_cb(mode, work_secs, break_secs)
