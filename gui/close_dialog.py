"""
gui/close_dialog.py

Shown when the user presses X (if ui.close_action is "ask").
Offers "Minimize to Tray" or "Quit", with a "Remember my choice"
checkbox. The remembered choice is saved to config and can be
changed later in Settings.
"""

import tkinter as tk
from typing import Optional
from gui.theme import T, F


class CloseDialog(tk.Toplevel):
    """
    Result is read from .result after the dialog closes:
        "tray"  — minimize to system tray
        "quit"  — quit the application
        None    — user cancelled (Esc / window close)
    .remember is True if the checkbox was ticked.
    """

    def __init__(self, parent: tk.Tk, tray_available: bool):
        super().__init__(parent)
        self.result: Optional[str] = None
        self.remember = False

        self.title("Close BARJ Volume Controller")
        self.configure(bg=T.bg_surface)
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda e: self._cancel())

        self._build(tray_available)
        self._center(parent)

    # ------------------------------------------------------------------ #

    def _build(self, tray_available: bool):
        outer = tk.Frame(self, bg=T.bg_surface, padx=28, pady=24)
        outer.pack()

        tk.Label(outer, text="Close BARJ Volume Controller?",
                 font=F.header, bg=T.bg_surface, fg=T.fg
                 ).pack(anchor="w", pady=(0, 4))

        sub = ("Minimize to the tray to keep your sliders working, "
               "or quit completely.") if tray_available else \
              ("The system tray isn't available, so the app must quit "
               "to close the window.")
        tk.Label(outer, text=sub, font=F.small,
                 bg=T.bg_surface, fg=T.fg_muted,
                 wraplength=360, justify="left"
                 ).pack(anchor="w", pady=(0, 16))

        # ---- Buttons ----
        btns = tk.Frame(outer, bg=T.bg_surface)
        btns.pack(fill="x", pady=(0, 14))

        if tray_available:
            tk.Button(btns, text="Minimize to Tray",
                      command=lambda: self._choose("tray"),
                      bg=T.btn_primary, fg=T.btn_primary_fg, relief="flat",
                      font=F.body_b, padx=16, pady=8, cursor="hand2"
                      ).pack(side="left")

        tk.Button(btns, text="Quit App",
                  command=lambda: self._choose("quit"),
                  bg=(T.btn_bg if tray_available else T.btn_primary),
                  fg=(T.btn_fg if tray_available else T.btn_primary_fg),
                  relief="flat",
                  font=(F.body if tray_available else F.body_b),
                  padx=16, pady=8, cursor="hand2"
                  ).pack(side="left", padx=(8, 0))

        tk.Button(btns, text="Cancel",
                  command=self._cancel,
                  bg=T.bg_surface, fg=T.fg_subtle, relief="flat",
                  font=F.small, padx=10, pady=8, cursor="hand2"
                  ).pack(side="right")

        # ---- Remember checkbox ----
        self._remember_var = tk.BooleanVar(value=False)
        cb = tk.Checkbutton(
            outer,
            text="Remember my choice and don't ask again",
            variable=self._remember_var,
            font=F.small,
            bg=T.bg_surface, fg=T.fg_muted,
            activebackground=T.bg_surface, activeforeground=T.fg,
            selectcolor=T.bg_input,
            highlightthickness=0, bd=0, cursor="hand2",
        )
        cb.pack(anchor="w")

        tk.Label(outer,
                 text="You can change this later in ⚙ Settings.",
                 font=F.tiny, bg=T.bg_surface, fg=T.fg_subtle
                 ).pack(anchor="w", pady=(2, 0))

    # ------------------------------------------------------------------ #

    def _choose(self, action: str):
        self.result   = action
        self.remember = self._remember_var.get()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

    def _center(self, parent: tk.Tk):
        self.update_idletasks()
        px = parent.winfo_x() + parent.winfo_width()  // 2
        py = parent.winfo_y() + parent.winfo_height() // 2
        self.geometry(f"+{px - self.winfo_reqwidth() // 2}"
                      f"+{py - self.winfo_reqheight() // 2}")
