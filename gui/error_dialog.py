"""
gui/error_dialog.py

Single-instance error dialog for serial/audio errors.

Rules:
  - Only one dialog open at a time (further errors are queued or dropped)
  - Shows error type, human-readable message, and raw serial data (if any)
  - "Dismiss" resets the lock so future errors can show again
  - Designed for diagnosing solder/wiring problems
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
import datetime

BG       = "#181825"
BG_CARD  = "#1e1e2e"
BG_CODE  = "#11111b"
FG       = "#cdd6f4"
FG_MUTED = "#6c7086"
ACCENT   = "#cba6f7"
ERR      = "#f38ba8"
WARN     = "#f9e2af"
OK       = "#a6e3a1"
BTN_BG   = "#45475a"

_KIND_LABELS = {
    "parse":      ("⚡ Serial Data Error",   WARN),
    "disconnect": ("🔌 Hardware Disconnected", ERR),
    "connect":    ("🔌 Cannot Connect",        ERR),
}


class ErrorDialog(tk.Toplevel):
    """
    Shows a single error with full diagnostic detail.

    Parameters
    ----------
    parent      : MainWindow (tk.Tk)
    kind        : error kind string (SerialError.PARSE etc.)
    message     : human-readable explanation
    raw_line    : the raw serial bytes that caused a parse error (may be "")
    on_dismiss  : called with no args when the user clicks Dismiss
    """

    def __init__(self, parent: tk.Tk, kind: str, message: str,
                 raw_line: str = "", on_dismiss: Optional[Callable] = None):
        super().__init__(parent)
        self._on_dismiss = on_dismiss
        self.title("BARJ Volume Controller — Error")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.lift()
        self.protocol("WM_DELETE_WINDOW", self._dismiss)

        label, colour = _KIND_LABELS.get(kind, ("⚠ Error", WARN))
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        self._build(label, colour, message, raw_line, timestamp)
        self._center(parent)

    # ------------------------------------------------------------------ #

    def _build(self, label: str, colour: str,
               message: str, raw_line: str, timestamp: str):
        outer = tk.Frame(self, bg=BG, padx=28, pady=22)
        outer.pack()

        # Header
        tk.Label(outer, text=label,
                 font=("Segoe UI", 13, "bold"), bg=BG, fg=colour
                 ).pack(anchor="w")
        tk.Label(outer, text=f"  {timestamp}",
                 font=("Segoe UI", 8), bg=BG, fg=FG_MUTED
                 ).pack(anchor="w", pady=(0, 12))

        # Message (word-wrapped)
        tk.Label(outer, text=message,
                 font=("Segoe UI", 10), bg=BG, fg=FG,
                 wraplength=420, justify="left"
                 ).pack(anchor="w", pady=(0, 12))

        # Raw data block (only for parse errors)
        if raw_line:
            tk.Label(outer, text="Raw data received from Arduino:",
                     font=("Segoe UI", 9, "bold"), bg=BG, fg=FG_MUTED
                     ).pack(anchor="w", pady=(0, 4))

            code_frame = tk.Frame(outer, bg=BG_CODE, padx=10, pady=8)
            code_frame.pack(fill="x", pady=(0, 12))

            raw_text = tk.Text(code_frame, height=3, bg=BG_CODE, fg=OK,
                               font=("Courier", 9), relief="flat",
                               wrap="char", selectbackground=BTN_BG)
            raw_text.insert("1.0", raw_line)
            raw_text.configure(state="disabled")
            raw_text.pack(fill="x")

            tk.Label(outer,
                     text="💡 Tip: valid data looks like   0|512|1023|256|768\n"
                          "   Garbled characters suggest a loose/cold solder joint.",
                     font=("Segoe UI", 8), bg=BG, fg=FG_MUTED,
                     justify="left"
                     ).pack(anchor="w", pady=(0, 12))

        # Dismiss button
        tk.Button(outer, text="Dismiss",
                  command=self._dismiss,
                  bg=colour, fg=BG,
                  font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=20, pady=6, cursor="hand2"
                  ).pack()

    def _dismiss(self):
        if self._on_dismiss:
            self._on_dismiss()
        if self.winfo_exists():
            self.destroy()

    def _center(self, parent: tk.Tk):
        self.update_idletasks()
        px = parent.winfo_x() + parent.winfo_width()  // 2
        py = parent.winfo_y() + parent.winfo_height() // 2
        w  = self.winfo_reqwidth()
        h  = self.winfo_reqheight()
        self.geometry(f"+{px - w // 2}+{py - h // 2}")
