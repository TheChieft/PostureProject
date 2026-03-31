"""
utils.py
--------
Shared UI helpers for PostureProject.
"""
from __future__ import annotations
import tkinter as tk


def center_window(win: tk.Misc, w: int, h: int) -> None:
    """Resize and center a Tk window on screen."""
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")
