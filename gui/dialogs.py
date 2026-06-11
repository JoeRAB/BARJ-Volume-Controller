"""
gui/dialogs.py

All small modal dialogs in one module:
  CloseDialog       — X-button: minimize to tray / quit, with remember option
  ConnectingDialog  — shown while waiting for the Arduino, port changer built in
  ErrorDialog       — single-instance serial/audio error with raw-data diagnosis
"""

import datetime
import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

from gui.theme import T, F

DOTS = ["   ", ".  ", ".. ", "..."]


# ========================================================================== #
# Close Dialog
# ========================================================================== #

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


# ========================================================================== #
# Connecting Dialog
# ========================================================================== #



class ConnectingDialog(tk.Toplevel):
    POLL_MS = 500

    def __init__(self, parent, get_port: Callable, list_ports: Callable,
                 on_port_change: Callable):
        super().__init__(parent)
        self._parent        = parent
        self._get_port      = get_port
        self._list_ports    = list_ports
        self._on_port_change = on_port_change
        self._dot_idx  = 0
        self._dismissed = False
        self._anim_job: Optional[str] = None

        self.title("BARJ Volume Controller")
        self.configure(bg=T.bg_surface)
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._dismiss)
        self._build()
        self._center()
        self._animate()

    def _build(self):
        outer = tk.Frame(self, bg=T.bg_surface, padx=32, pady=28)
        outer.pack()

        # Icon row
        icon_row = tk.Frame(outer, bg=T.bg_surface)
        icon_row.pack(anchor="w", pady=(0, 4))
        tk.Label(icon_row, text="🔌", font=(F.ui, 22),
                 bg=T.bg_surface).pack(side="left", padx=(0, 10))
        tk.Label(icon_row, text="Connecting to Hardware",
                 font=F.header, bg=T.bg_surface, fg=T.fg
                 ).pack(side="left")

        # Animated status
        self._status_var = tk.StringVar()
        self._status_lbl = tk.Label(outer, textvariable=self._status_var,
                                    font=F.body, bg=T.bg_surface, fg=T.warn,
                                    width=38, anchor="w")
        self._status_lbl.pack(pady=(0, 20))

        # Divider
        tk.Frame(outer, bg=T.separator, height=1).pack(fill="x", pady=(0, 16))

        # Port selector row
        tk.Label(outer, text="Serial Port", font=F.small_b,
                 bg=T.bg_surface, fg=T.fg_muted, anchor="w"
                 ).pack(anchor="w", pady=(0, 4))

        pf = tk.Frame(outer, bg=T.bg_surface)
        pf.pack(fill="x", pady=(0, 14))
        self._port_var = tk.StringVar(value=self._get_port())
        self._combo = ttk.Combobox(pf, textvariable=self._port_var,
                                   width=20, font=F.small)
        self._combo.pack(side="left")
        tk.Button(pf, text="↻", command=self._refresh,
                  bg=T.btn_bg, fg=T.fg, relief="flat",
                  font=(F.ui, 12), padx=6, cursor="hand2"
                  ).pack(side="left", padx=(6, 0))
        self._refresh()

        # Apply button
        tk.Button(outer, text="Apply & Reconnect",
                  command=self._apply,
                  bg=T.btn_primary, fg=T.btn_primary_fg, relief="flat",
                  font=F.body_b, padx=16, pady=7, cursor="hand2"
                  ).pack(fill="x")

        # Dismiss link
        tk.Button(outer, text="Dismiss  (app keeps retrying in background)",
                  command=self._dismiss,
                  bg=T.bg_surface, fg=T.fg_subtle, relief="flat",
                  font=F.tiny, cursor="hand2"
                  ).pack(pady=(10, 0))

    def notify_connected(self):
        self._cancel_anim()
        if self.winfo_exists():
            self.destroy()

    def show_reconnecting(self):
        if self._dismissed: return
        if self.winfo_exists():
            self._port_var.set(self._get_port())
            self.deiconify(); self.lift()
        self._animate()

    def update_port_display(self, port):
        if self.winfo_exists():
            self._port_var.set(port)

    def _refresh(self):
        ports = self._list_ports()
        self._combo["values"] = ports
        if not self._port_var.get() and ports:
            self._port_var.set(ports[0])

    def _apply(self):
        p = self._port_var.get().strip()
        if p: self._on_port_change(p)

    def _animate(self):
        if not self.winfo_exists(): return
        dots = DOTS[self._dot_idx % len(DOTS)]
        self._status_var.set(f"Waiting for {self._get_port()}{dots}")
        self._dot_idx += 1
        self._anim_job = self.after(self.POLL_MS, self._animate)

    def _cancel_anim(self):
        if self._anim_job:
            try: self.after_cancel(self._anim_job)
            except Exception: pass
            self._anim_job = None

    def _dismiss(self):
        self._dismissed = True
        self._cancel_anim()
        if self.winfo_exists(): self.withdraw()

    def _center(self):
        self.update_idletasks()
        px = self._parent.winfo_x() + self._parent.winfo_width()  // 2
        py = self._parent.winfo_y() + self._parent.winfo_height() // 2
        self.geometry(f"+{px - self.winfo_reqwidth()//2}+{py - self.winfo_reqheight()//2}")


# ========================================================================== #
# Error Dialog
# ========================================================================== #

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

