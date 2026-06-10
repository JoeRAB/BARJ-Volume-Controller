"""
gui/error_dialog.py  —  themed single-instance error dialog
"""

import tkinter as tk
from typing import Callable, Optional
import datetime
from gui.theme import T, F

_KIND_LABELS = {
    "parse":      ("⚡ Serial Data Error",    "warn"),
    "disconnect": ("🔌 Hardware Disconnected", "err"),
    "connect":    ("🔌 Cannot Connect",        "err"),
}


class ErrorDialog(tk.Toplevel):
    def __init__(self, parent, kind: str, message: str,
                 raw_line: str = "", on_dismiss: Optional[Callable] = None):
        super().__init__(parent)
        self._on_dismiss = on_dismiss
        label, colour_key = _KIND_LABELS.get(kind, ("⚠ Error", "warn"))
        colour = getattr(T, colour_key)
        ts = datetime.datetime.now().strftime("%H:%M:%S")

        self.title("BARJ Volume Controller — Error")
        self.configure(bg=T.bg_surface)
        self.resizable(False, False)
        self.transient(parent)
        self.lift()
        self.protocol("WM_DELETE_WINDOW", self._dismiss)
        self._build(label, colour, message, raw_line, ts)
        self._center(parent)

    def _build(self, label, colour, message, raw_line, ts):
        outer = tk.Frame(self, bg=T.bg_surface, padx=28, pady=24)
        outer.pack()

        # Coloured left accent bar
        tk.Frame(self, bg=colour, width=4).place(relx=0, rely=0,
                                                  relheight=1, anchor="nw")

        # Header
        tk.Label(outer, text=label, font=F.header,
                 bg=T.bg_surface, fg=colour).pack(anchor="w")
        tk.Label(outer, text=ts, font=F.tiny,
                 bg=T.bg_surface, fg=T.fg_subtle).pack(anchor="w", pady=(2,12))

        # Message
        tk.Label(outer, text=message, font=F.body,
                 bg=T.bg_surface, fg=T.fg,
                 wraplength=420, justify="left").pack(anchor="w", pady=(0,12))

        # Raw data
        if raw_line:
            tk.Label(outer, text="Raw data from Arduino:",
                     font=F.small_b, bg=T.bg_surface, fg=T.fg_muted
                     ).pack(anchor="w", pady=(0,4))
            box = tk.Frame(outer, bg=T.bg_code,
                           highlightbackground=T.border, highlightthickness=1,
                           padx=10, pady=8)
            box.pack(fill="x", pady=(0,8))
            t = tk.Text(box, height=min(4, raw_line.count("\n")+2),
                        bg=T.bg_code, fg=T.ok,
                        font=F.code, relief="flat", wrap="char",
                        selectbackground=T.btn_bg)
            t.insert("1.0", raw_line)
            t.configure(state="disabled")
            t.pack(fill="x")
            tk.Label(outer,
                     text="💡 Valid data looks like:  0|512|1023|256|768\n"
                          "   Garbled output usually means a loose or cold solder joint.",
                     font=F.tiny, bg=T.bg_surface, fg=T.fg_muted, justify="left"
                     ).pack(anchor="w", pady=(0,12))

        # Separator
        tk.Frame(outer, bg=T.separator, height=1).pack(fill="x", pady=(0,14))

        # Dismiss
        tk.Button(outer, text="Dismiss",
                  command=self._dismiss,
                  bg=colour, fg=T.bg_surface if T.name=="light" else "white",
                  font=F.body_b, relief="flat", padx=20, pady=7,
                  cursor="hand2").pack(anchor="w")

    def _dismiss(self):
        if self._on_dismiss: self._on_dismiss()
        if self.winfo_exists(): self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        px = parent.winfo_x() + parent.winfo_width()  // 2
        py = parent.winfo_y() + parent.winfo_height() // 2
        self.geometry(f"+{px-self.winfo_reqwidth()//2}+{py-self.winfo_reqheight()//2}")
