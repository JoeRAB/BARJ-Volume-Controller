"""
gui/dialogs.py

Every modal dialog in one module:
  CloseDialog        - X-button: minimize to tray / quit, with remember option
  ConnectingDialog   - shown while waiting for the Arduino, port changer built in
  ErrorDialog        - single-instance serial/audio error with raw-data diagnosis
  SettingsDialog     - serial port, slider count, smoothing, theme, close action
  DependencyChecker  - import/system checks (no UI)
  DependencyDialog   - itemised dependency list with one-click pip install
  SliderPanel        - one hardware-slider card: dropdown, VU meter, status
"""

import datetime
import importlib
import platform
import subprocess
import sys
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk, simpledialog, filedialog
from typing import Callable, List, Optional

from gui.theme import T, F, RoundedButton, Tooltip

DOTS = ["   ", ".  ", ".. ", "..."]



class _ThemedDialog(tk.Toplevel):
    """A small modal dialog that follows the app theme. Used for info /
    warning / error messages and yes/no confirmations, so popups match the
    light/dark theme instead of using the unthemed OS messagebox.

    kind: "info" | "warning" | "error" | "confirm"
    Result is stored in .result: True (OK/Yes) or False (Cancel/No).
    """

    _ICONS = {"info": "ℹ", "warning": "⚠", "error": "⛔", "confirm": "❓"}

    def __init__(self, parent, title: str, message: str, kind: str = "info",
                 ok_text: str = "OK", cancel_text: Optional[str] = None):
        super().__init__(parent)
        self.result = False
        self._kind = kind
        self.title(title)
        self.configure(bg=T.bg_surface)
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda e: self._cancel())
        self.bind("<Return>", lambda e: self._ok())
        self._build(title, message, ok_text, cancel_text)
        self._center(parent)
        self.after(10, self._safe_grab)

    def _safe_grab(self):
        try: self.grab_set()
        except Exception: pass

    def _accent_for_kind(self):
        return {"info": T.accent, "warning": T.warn,
                "error": T.err, "confirm": T.accent}.get(self._kind, T.accent)

    def _build(self, title, message, ok_text, cancel_text):
        colour = self._accent_for_kind()
        # Coloured left accent bar
        tk.Frame(self, bg=colour, width=4).place(relx=0, rely=0,
                                                 relheight=1, anchor="nw")
        outer = tk.Frame(self, bg=T.bg_surface, padx=26, pady=22)
        outer.pack()

        # Icon + title row
        head = tk.Frame(outer, bg=T.bg_surface)
        head.pack(anchor="w", fill="x", pady=(0, 8))
        tk.Label(head, text=self._ICONS.get(self._kind, "ℹ"),
                 font=(F.ui, 18), bg=T.bg_surface, fg=colour
                 ).pack(side="left", padx=(0, 10))
        tk.Label(head, text=title, font=F.header,
                 bg=T.bg_surface, fg=T.fg).pack(side="left")

        # Message
        tk.Label(outer, text=message, font=F.body,
                 bg=T.bg_surface, fg=T.fg_muted,
                 wraplength=360, justify="left").pack(anchor="w", pady=(0, 16))

        # Buttons
        bf = tk.Frame(outer, bg=T.bg_surface)
        bf.pack(anchor="e")
        if cancel_text is not None:
            RoundedButton(bf, text=cancel_text, command=self._cancel,
                          style="default", width=100, height=34, font=F.body,
                          bg_under=T.bg_surface).pack(side="right", padx=(8, 0))
        style = "danger" if self._kind == "error" else "primary"
        RoundedButton(bf, text=ok_text, command=self._ok,
                      style=style, width=100, height=34, font=F.body_b,
                      bg_under=T.bg_surface).pack(side="right")

    def _ok(self):
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        try:
            px = parent.winfo_x() + parent.winfo_width() // 2
            py = parent.winfo_y() + parent.winfo_height() // 2
            self.geometry(f"+{px - self.winfo_reqwidth() // 2}"
                          f"+{py - self.winfo_reqheight() // 2}")
        except Exception:
            pass


def themed_message(parent, title: str, message: str, kind: str = "info"):
    """Themed replacement for messagebox.showinfo/showwarning/showerror."""
    dlg = _ThemedDialog(parent, title, message, kind=kind, ok_text="OK")
    parent.wait_window(dlg)


def themed_confirm(parent, title: str, message: str,
                   ok_text: str = "Yes", cancel_text: str = "Cancel") -> bool:
    """Themed replacement for messagebox.askyesno. Returns True if confirmed."""
    dlg = _ThemedDialog(parent, title, message, kind="confirm",
                        ok_text=ok_text, cancel_text=cancel_text)
    parent.wait_window(dlg)
    return dlg.result



class CloseDialog(tk.Toplevel):
    """
    Result is read from .result after the dialog closes:
        "tray"  - minimize to system tray
        "quit"  - quit the application
        None    - user cancelled (Esc / window close)
    .remember is True if the checkbox was ticked.
    """

    def __init__(self, parent: tk.Tk, tray_available: bool):
        super().__init__(parent)
        self.result: Optional[str] = None
        self.remember = False

        self.title("Close BARJ Volume Controller")
        self.configure(bg=T.bg_surface)
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda e: self._cancel())

        self._build(tray_available)
        self._center(parent)
        self.after(10, self._safe_grab)

    def _safe_grab(self):
        try: self.grab_set()
        except Exception: pass


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

        # Buttons
        btns = tk.Frame(outer, bg=T.bg_surface)
        btns.pack(fill="x", pady=(0, 14))

        if tray_available:
            RoundedButton(btns, text="Minimize to Tray",
                          command=lambda: self._choose("tray"),
                          style="primary", width=150, height=36, font=F.body_b,
                          bg_under=T.bg_surface).pack(side="left")
            RoundedButton(btns, text="Quit App",
                          command=lambda: self._choose("quit"),
                          style="default", width=110, height=36, font=F.body,
                          bg_under=T.bg_surface).pack(side="left", padx=(8, 0))
        else:
            RoundedButton(btns, text="Quit App",
                          command=lambda: self._choose("quit"),
                          style="primary", width=130, height=36, font=F.body_b,
                          bg_under=T.bg_surface).pack(side="left")

        RoundedButton(btns, text="Cancel", command=self._cancel,
                      style="ghost", width=90, height=36, font=F.small,
                      bg_under=T.bg_surface).pack(side="right")

        # Remember checkbox
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


# Connecting Dialog


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


# Error Dialog

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

        self.title("BARJ Volume Controller - Error")
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


# Settings Dialog

BAUD_RATES = ["9600","19200","38400","57600","115200"]


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, config_mgr, list_ports: Callable,
                 on_save: Optional[Callable] = None):
        super().__init__(parent)
        self.config_mgr = config_mgr
        self._list_ports = list_ports
        self._on_save   = on_save
        self.title("Settings - BARJ Volume Controller")
        self.configure(bg=T.bg_surface)
        self.resizable(False, False)
        self.transient(parent)
        self._build()
        self.after(10, self._safe_grab)

    def _safe_grab(self):
        try: self.grab_set()
        except Exception: pass

    def _build(self):
        outer = tk.Frame(self, bg=T.bg_surface, padx=28, pady=24)
        outer.pack()

        tk.Label(outer, text="Settings", font=F.header,
                 bg=T.bg_surface, fg=T.accent).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0,16))

        def row(label, r):
            tk.Label(outer, text=label, font=F.body,
                     bg=T.bg_surface, fg=T.fg_muted, anchor="w"
                     ).grid(row=r, column=0, sticky="w", padx=(0,16), pady=6)

        def entry_style():
            return dict(bg=T.bg_input, fg=T.fg, insertbackground=T.fg,
                        relief="flat", font=F.body,
                        highlightthickness=1,
                        highlightbackground=T.border,
                        highlightcolor=T.accent)

        # Serial Port
        row("Serial Port", 1)
        pf = tk.Frame(outer, bg=T.bg_surface)
        pf.grid(row=1, column=1, sticky="w", pady=6)
        self._port_var = tk.StringVar(value=self.config_mgr.get("serial","port",default=""))
        self._port_combo = ttk.Combobox(pf, textvariable=self._port_var,
                                        width=16, font=F.small)
        self._port_combo.pack(side="left")
        tk.Button(pf, text="↻", command=self._refresh_ports,
                  bg=T.btn_bg, fg=T.fg, relief="flat",
                  font=(F.ui,12), padx=6, cursor="hand2"
                  ).pack(side="left", padx=(4,0))
        self._refresh_ports()

        # Baud Rate
        row("Baud Rate", 2)
        self._baud_var = tk.StringVar(
            value=str(self.config_mgr.get("serial","baud_rate",default=9600)))
        ttk.Combobox(outer, textvariable=self._baud_var,
                     values=BAUD_RATES, width=10, state="readonly",
                     font=F.small
                     ).grid(row=2, column=1, sticky="w", pady=6)

        # Slider Count
        row("Slider Count", 3)
        self._count_var = tk.IntVar(
            value=self.config_mgr.get("sliders","count",default=5))
        tk.Spinbox(outer, from_=1, to=12, textvariable=self._count_var,
                   width=5, **entry_style()
                   ).grid(row=3, column=1, sticky="w", pady=6)

        # Smoothing
        row("Smoothing", 4)
        sf = tk.Frame(outer, bg=T.bg_surface)
        sf.grid(row=4, column=1, sticky="w", pady=6)
        self._smooth_var = tk.DoubleVar(
            value=self.config_mgr.get("sliders","smoothing",default=0.6))
        self._smooth_lbl = tk.Label(sf,
            text=f"{self._smooth_var.get():.2f}",
            font=F.small_b, bg=T.bg_surface, fg=T.accent_soft, width=4)
        self._smooth_lbl.pack(side="right")
        tk.Scale(sf, from_=0.01, to=1.0, resolution=0.01, orient="horizontal",
                 variable=self._smooth_var, length=140,
                 bg=T.bg_surface, fg=T.fg, troughcolor=T.meter_track,
                 highlightthickness=0, showvalue=False,
                 command=lambda v: self._smooth_lbl.config(text=f"{float(v):.2f}")
                 ).pack(side="left")

        tk.Label(outer, text="← more smooth   more responsive →",
                 font=F.tiny, bg=T.bg_surface, fg=T.fg_subtle
                 ).grid(row=5, column=0, columnspan=2, pady=(0,16))

        # When closing window
        row("Close Button", 6)
        _CLOSE_LABELS = {
            "ask":  "Ask every time",
            "tray": "Minimize to tray",
            "quit": "Quit the app",
        }
        self._close_keys = list(_CLOSE_LABELS.keys())
        current_action = self.config_mgr.get("ui", "close_action", default="ask")
        self._close_var = tk.StringVar(
            value=_CLOSE_LABELS.get(current_action, "Ask every time"))
        ttk.Combobox(outer, textvariable=self._close_var,
                     values=list(_CLOSE_LABELS.values()),
                     width=18, state="readonly", font=F.small
                     ).grid(row=6, column=1, sticky="w", pady=6)
        self._close_labels = _CLOSE_LABELS

        # Invert sliders
        row("Flip adjustment direction", 7)
        # (theme selector added as row 8 below)
        self._invert_var = tk.BooleanVar(
            value=bool(self.config_mgr.get("sliders", "invert", default=False)))
        tk.Checkbutton(outer,
                       text="Flip direction (for backwards-wired pots)",
                       variable=self._invert_var,
                       font=F.small, bg=T.bg_surface, fg=T.fg_muted,
                       activebackground=T.bg_surface, activeforeground=T.fg,
                       selectcolor=T.bg_input,
                       highlightthickness=0, bd=0, cursor="hand2"
                       ).grid(row=7, column=1, sticky="w", pady=6)

        # Theme
        row("Theme", 8)
        _THEME_LABELS = {
            "auto":  "Match OS setting",
            "light": "Light",
            "dark":  "Dark",
        }
        self._theme_labels = _THEME_LABELS
        current_theme = self.config_mgr.get("ui", "theme", default="auto")
        self._theme_var = tk.StringVar(
            value=_THEME_LABELS.get(current_theme, "Match OS setting"))
        ttk.Combobox(outer, textvariable=self._theme_var,
                     values=list(_THEME_LABELS.values()),
                     width=18, state="readonly", font=F.small
                     ).grid(row=8, column=1, sticky="w", pady=6)

        # Start on login
        row("Startup", 9)
        from autostart import is_start_on_login_enabled
        self._startup_var = tk.BooleanVar(value=is_start_on_login_enabled())
        tk.Checkbutton(outer, text="Start automatically on login",
                       variable=self._startup_var, font=F.small,
                       bg=T.bg_surface, fg=T.fg_muted,
                       activebackground=T.bg_surface, activeforeground=T.fg,
                       selectcolor=T.bg_input, highlightthickness=0, bd=0,
                       cursor="hand2"
                       ).grid(row=9, column=1, sticky="w", pady=(6, 0))

        # Launch minimized
        self._minimized_var = tk.BooleanVar(
            value=bool(self.config_mgr.get("ui", "launch_minimized", default=False)))
        tk.Checkbutton(outer, text="Start minimized to the system tray",
                       variable=self._minimized_var, font=F.small,
                       bg=T.bg_surface, fg=T.fg_muted,
                       activebackground=T.bg_surface, activeforeground=T.fg,
                       selectcolor=T.bg_input, highlightthickness=0, bd=0,
                       cursor="hand2"
                       ).grid(row=10, column=1, sticky="w", pady=(0, 6))

        # Separator
        tk.Frame(outer, bg=T.separator, height=1
                 ).grid(row=11, column=0, columnspan=2, sticky="ew", pady=(0,14))

        # Backup / import-export
        tk.Label(outer, text="Profiles & Backup", font=F.body_b,
                 bg=T.bg_surface, fg=T.fg).grid(row=12, column=0, columnspan=2,
                                                sticky="w", pady=(0, 6))
        io = tk.Frame(outer, bg=T.bg_surface)
        io.grid(row=13, column=0, columnspan=2, sticky="w", pady=(0, 4))
        RoundedButton(io, text="Export Profile", command=self._export_profile,
                      style="default", width=130, height=30, font=F.small,
                      bg_under=T.bg_surface).pack(side="left", padx=(0, 6))
        RoundedButton(io, text="Import Profile", command=self._import_profile,
                      style="default", width=130, height=30, font=F.small,
                      bg_under=T.bg_surface).pack(side="left")
        io2 = tk.Frame(outer, bg=T.bg_surface)
        io2.grid(row=14, column=0, columnspan=2, sticky="w", pady=(4, 0))
        RoundedButton(io2, text="Back Up All…", command=self._export_all,
                      style="ghost", width=130, height=28, font=F.tiny,
                      bg_under=T.bg_surface).pack(side="left", padx=(0, 6))
        RoundedButton(io2, text="Restore All…", command=self._import_all,
                      style="ghost", width=130, height=28, font=F.tiny,
                      bg_under=T.bg_surface).pack(side="left")

        # Separator
        tk.Frame(outer, bg=T.separator, height=1
                 ).grid(row=15, column=0, columnspan=2, sticky="ew", pady=(14,14))

        # Buttons
        bf = tk.Frame(outer, bg=T.bg_surface)
        bf.grid(row=16, column=0, columnspan=2)
        RoundedButton(bf, text="Save", command=self._save, style="primary",
                      width=110, height=36, font=F.body_b,
                      bg_under=T.bg_surface).pack(side="left")
        RoundedButton(bf, text="Cancel", command=self.destroy, style="default",
                      width=110, height=36, font=F.body,
                      bg_under=T.bg_surface).pack(side="left", padx=(10, 0))

    def _refresh_ports(self):
        ports = self._list_ports()
        self._port_combo["values"] = ports
        if not self._port_var.get() and ports:
            self._port_var.set(ports[0])

    # Import / export handlers

    def _export_profile(self):
        name = self.config_mgr.current_profile
        path = filedialog.asksaveasfilename(
            parent=self, title="Export Profile",
            defaultextension=".yaml",
            initialfile=f"{name}.barj-profile.yaml",
            filetypes=[("BARJ profile", "*.yaml"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.config_mgr.export_profile(name, path)
            themed_message(self, "Exported",
                           f"Profile '{name}' exported.", kind="info")
        except Exception as e:
            themed_message(self, "Export Failed", str(e), kind="error")

    def _import_profile(self):
        path = filedialog.askopenfilename(
            parent=self, title="Import Profile",
            filetypes=[("BARJ profile", "*.yaml"), ("All files", "*.*")])
        if not path:
            return
        try:
            name = self.config_mgr.import_profile(path)
            themed_message(self, "Imported",
                           f"Profile imported as '{name}'.", kind="info")
            if self._on_save:
                self._on_save()   # refresh the profile list in the main window
        except Exception as e:
            themed_message(self, "Import Failed", str(e), kind="error")

    def _export_all(self):
        path = filedialog.asksaveasfilename(
            parent=self, title="Back Up All Settings",
            defaultextension=".yaml",
            initialfile="barj-backup.yaml",
            filetypes=[("BARJ backup", "*.yaml"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.config_mgr.export_all(path)
            themed_message(self, "Backed Up",
                           "All settings and profiles were backed up.",
                           kind="info")
        except Exception as e:
            themed_message(self, "Backup Failed", str(e), kind="error")

    def _import_all(self):
        if not themed_confirm(
                self, "Restore All",
                "Restoring replaces ALL current settings and profiles "
                "with the backup. Continue?",
                ok_text="Restore", cancel_text="Cancel"):
            return
        path = filedialog.askopenfilename(
            parent=self, title="Restore All Settings",
            filetypes=[("BARJ backup", "*.yaml"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.config_mgr.import_all(path)
            themed_message(self, "Restored",
                           "Settings restored. Restart the app to apply "
                           "everything cleanly.", kind="info")
            if self._on_save:
                self._on_save()
        except Exception as e:
            themed_message(self, "Restore Failed", str(e), kind="error")

    def _save(self):
        count = self._count_var.get()
        if not 1 <= count <= 12:
            themed_message(self, "Invalid", "Slider count must be 1–12.",
                           kind="warning")
            return
        self.config_mgr.set(self._port_var.get(),         "serial","port")
        self.config_mgr.set(int(self._baud_var.get()),    "serial","baud_rate")
        self.config_mgr.set(int(count),                   "sliders","count")
        self.config_mgr.set(round(self._smooth_var.get(),2), "sliders","smoothing")
        theme_key = {v: k for k, v in self._theme_labels.items()}
        self.config_mgr.set(
            theme_key.get(self._theme_var.get(), "auto"), "ui", "theme")
        self.config_mgr.set(bool(self._invert_var.get()),    "sliders","invert")
        # Map the displayed label back to its config key
        label_to_key = {v: k for k, v in self._close_labels.items()}
        self.config_mgr.set(
            label_to_key.get(self._close_var.get(), "ask"), "ui", "close_action")
        # Launch minimized preference
        self.config_mgr.set(bool(self._minimized_var.get()),
                            "ui", "launch_minimized")
        # Start on login - write/remove the autostart entry to match
        from autostart import set_start_on_login
        set_start_on_login(bool(self._startup_var.get()))
        if self._on_save: self._on_save()
        self.destroy()

# Dependency Check

@dataclass
class Dep:
    display_name: str
    import_name:  str
    pip_package:  str
    required:     bool
    description:  str
    platforms:    List[str] = field(default_factory=lambda: ["Linux","Windows","Darwin"])
    status:       Optional[bool] = None

DEPS: List[Dep] = [
    Dep("pyserial",  "serial",   "pyserial",  True,  "Arduino serial communication"),
    Dep("PyYAML",    "yaml",     "pyyaml",    True,  "Config file read/write"),
    Dep("pulsectl",  "pulsectl", "pulsectl",  True,  "Linux audio control",  platforms=["Linux"]),
    Dep("pycaw",     "pycaw",    "pycaw",     True,  "Windows audio control",platforms=["Windows"]),
    Dep("comtypes",  "comtypes", "comtypes",  True,  "Windows COM interface", platforms=["Windows"]),
    Dep("pystray",   "pystray",  "pystray",   False, "System tray icon"),
    Dep("Pillow",    "PIL",      "Pillow",    False, "Tray icon rendering"),
]

@dataclass
class SysCheck:
    name: str; description: str; required: bool
    status: Optional[bool] = None; detail: str = ""; fix_hint: str = ""

def _run_sys_checks() -> List[SysCheck]:
    checks: List[SysCheck] = []
    if platform.system() != "Linux": return checks
    c = SysCheck("Audio server","PulseAudio or PipeWire running",True,
                 fix_hint="systemctl --user start pipewire pipewire-pulse")
    try:
        r = subprocess.run(["pactl","info"],capture_output=True,timeout=3)
        c.status = r.returncode == 0
        if not c.status: c.detail = r.stderr.decode(errors="ignore").strip()
    except FileNotFoundError:
        c.status=False; c.detail="'pactl' not found"
        c.fix_hint="sudo apt install pulseaudio-utils"
    except Exception as e: c.status=False; c.detail=str(e)
    checks.append(c)
    import grp, os
    sg = None
    for g in ("dialout","uucp"):
        try: grp.getgrnam(g); sg=g; break
        except KeyError: pass
    g2 = SysCheck("Serial port access",f"User in '{sg or 'dialout'}' group",False,
                  fix_hint=f"sudo usermod -aG {sg or 'dialout'} $USER  (log out/in)")
    if sg:
        try: g2.status = sg in [grp.getgrgid(x).gr_name for x in os.getgroups()]
        except Exception as e: g2.status=False; g2.detail=str(e)
    else: g2.status=True
    checks.append(g2)
    return checks

def install_packages(packages):
    if not packages: return True,""
    cmd = [sys.executable,"-m","pip","install",*packages]
    try:
        r = subprocess.run(cmd,capture_output=True,text=True,timeout=300)
        if r.returncode!=0 and "externally-managed" in r.stderr:
            r = subprocess.run(cmd+["--break-system-packages"],
                               capture_output=True,text=True,timeout=300)
        return r.returncode==0, r.stdout+r.stderr
    except Exception as e: return False,str(e)


class DependencyChecker:
    def __init__(self):
        self.system     = platform.system()
        self.deps       = [d for d in DEPS if self.system in d.platforms]
        self.sys_checks = _run_sys_checks()
        self.recheck()

    def recheck(self):
        importlib.invalidate_caches()
        for d in self.deps:
            try:
                if d.import_name in sys.modules: importlib.reload(sys.modules[d.import_name])
                else: importlib.import_module(d.import_name)
                d.status=True
            except Exception: d.status=False

    @property
    def missing(self): return [d for d in self.deps if not d.status]
    @property
    def missing_required(self): return [d for d in self.deps if d.required and not d.status]
    @property
    def sys_failures(self): return [c for c in self.sys_checks if not c.status]
    @property
    def all_ok(self): return not self.missing and not any(c.required for c in self.sys_failures)


class DependencyDialog(tk.Toplevel):
    def __init__(self, parent, checker: DependencyChecker):
        super().__init__(parent)
        self.checker = checker
        self.proceed = False
        self.title("BARJ Volume Controller - Dependencies")
        self.configure(bg=T.bg_surface)
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build()
        self.after(10, self._safe_grab)

    def _safe_grab(self):
        try: self.grab_set()
        except Exception: pass

    def _build(self):
        for w in self.winfo_children(): w.destroy()
        outer = tk.Frame(self, bg=T.bg_surface, padx=28, pady=24)
        outer.pack()

        tk.Label(outer, text="Dependency Check", font=F.title,
                 bg=T.bg_surface, fg=T.accent).pack(anchor="w")
        tk.Label(outer, text="Status of required and optional components:",
                 font=F.small, bg=T.bg_surface, fg=T.fg_muted
                 ).pack(anchor="w", pady=(2,14))

        # Dep list
        card = tk.Frame(outer, bg=T.bg_card,
                        highlightbackground=T.border, highlightthickness=1)
        card.pack(fill="x", pady=(0,4))

        for i, dep in enumerate(self.checker.deps):
            self._dep_row(card, dep, i)

        # System checks
        if self.checker.sys_checks:
            tk.Label(outer, text="System checks:", font=F.small_b,
                     bg=T.bg_surface, fg=T.fg_muted
                     ).pack(anchor="w", pady=(12,4))
            sc = tk.Frame(outer, bg=T.bg_card,
                          highlightbackground=T.border, highlightthickness=1)
            sc.pack(fill="x", pady=(0,4))
            for i, chk in enumerate(self.checker.sys_checks):
                self._sys_row(sc, chk, i)

        # Actions
        tk.Frame(outer, bg=T.separator, height=1).pack(fill="x", pady=(16,14))
        missing = self.checker.missing
        if missing:
            tk.Label(outer,
                     text="Do you want to install missing dependencies?",
                     font=F.body_b, bg=T.bg_surface, fg=T.fg
                     ).pack(anchor="w", pady=(0,10))
            bf = tk.Frame(outer, bg=T.bg_surface)
            bf.pack(anchor="w")
            tk.Button(bf, text="Install Missing Dependencies",
                      command=self._install,
                      bg=T.btn_primary, fg=T.btn_primary_fg, relief="flat",
                      font=F.body_b, padx=16, pady=7, cursor="hand2"
                      ).pack(side="left")
            if not self.checker.missing_required:
                tk.Button(bf, text="Skip & Continue", command=self._continue,
                          bg=T.btn_bg, fg=T.btn_fg, relief="flat",
                          font=F.body, padx=16, pady=7, cursor="hand2"
                          ).pack(side="left", padx=(8,0))
            else:
                tk.Button(bf, text="Quit", command=self._close,
                          bg=T.btn_bg, fg=T.btn_fg, relief="flat",
                          font=F.body, padx=16, pady=7, cursor="hand2"
                          ).pack(side="left", padx=(8,0))
        else:
            tk.Label(outer, text="✓  All dependencies satisfied.",
                     font=F.body_b, bg=T.bg_surface, fg=T.ok
                     ).pack(anchor="w", pady=(0,10))
            tk.Button(outer, text="Continue",
                      command=self._continue,
                      bg=T.ok, fg=T.bg_surface, relief="flat",
                      font=F.body_b, padx=20, pady=7, cursor="hand2"
                      ).pack(anchor="w")

    def _dep_row(self, parent, dep: Dep, idx: int):
        alt = idx % 2 == 1
        bg  = T.bg_elevated if alt else T.bg_card
        row = tk.Frame(parent, bg=bg, padx=14, pady=8)
        row.pack(fill="x")
        # Left: name + description
        lf = tk.Frame(row, bg=bg)
        lf.pack(side="left", fill="x", expand=True)
        tag = "  (optional)" if not dep.required else ""
        tk.Label(lf, text=dep.display_name + tag, font=F.body_b,
                 bg=bg, fg=T.fg, anchor="w").pack(anchor="w")
        tk.Label(lf, text=dep.description, font=F.tiny,
                 bg=bg, fg=T.fg_muted, anchor="w").pack(anchor="w")
        # Right: status
        if dep.status:
            status_txt, status_col = "Installed", T.ok
        else:
            status_txt = "Missing"
            status_col = T.err if dep.required else T.warn
        tk.Label(row, text=f"-  {status_txt}", font=F.body_b,
                 bg=bg, fg=status_col).pack(side="right")

    def _sys_row(self, parent, chk: SysCheck, idx: int):
        alt = idx % 2 == 1
        bg  = T.bg_elevated if alt else T.bg_card
        row = tk.Frame(parent, bg=bg, padx=14, pady=8)
        row.pack(fill="x")
        lf = tk.Frame(row, bg=bg)
        lf.pack(side="left", fill="x", expand=True)
        tk.Label(lf, text=chk.name, font=F.body_b,
                 bg=bg, fg=T.fg, anchor="w").pack(anchor="w")
        desc = chk.detail or chk.description
        tk.Label(lf, text=desc, font=F.tiny,
                 bg=bg, fg=T.fg_muted, anchor="w",
                 wraplength=300, justify="left").pack(anchor="w")
        if not chk.status and chk.fix_hint:
            tk.Label(lf, text=f"Fix:  {chk.fix_hint}", font=F.code,
                     bg=bg, fg=T.accent_soft, anchor="w",
                     wraplength=320, justify="left").pack(anchor="w")
        if chk.status:  txt,col = "OK", T.ok
        elif chk.required: txt,col = "Missing", T.err
        else:           txt,col = "Warning", T.warn
        tk.Label(row, text=f"-  {txt}", font=F.body_b,
                 bg=bg, fg=col).pack(side="right")

    def _install(self):
        packages = [d.pip_package for d in self.checker.missing]
        for w in self.winfo_children(): w.destroy()
        pg = tk.Frame(self, bg=T.bg_surface, padx=40, pady=40)
        pg.pack()
        tk.Label(pg, text="Installing…", font=F.title,
                 bg=T.bg_surface, fg=T.accent).pack()
        tk.Label(pg, text=", ".join(packages), font=F.small,
                 bg=T.bg_surface, fg=T.fg_muted, wraplength=360).pack(pady=(6,0))
        self.update()
        ok, out = install_packages(packages)
        self.checker.recheck()
        if ok and not self.checker.missing_required:
            self._build()
        else:
            self._fail(out)

    def _fail(self, output):
        for w in self.winfo_children(): w.destroy()
        f = tk.Frame(self, bg=T.bg_surface, padx=28, pady=22); f.pack()
        tk.Label(f, text="⚠  Install Incomplete", font=F.header,
                 bg=T.bg_surface, fg=T.err).pack(anchor="w", pady=(0,8))
        tk.Label(f, text="Install manually with pip:",
                 font=F.body, bg=T.bg_surface, fg=T.fg, justify="left"
                 ).pack(anchor="w")
        cmd = "pip install " + " ".join(d.pip_package for d in self.checker.missing)
        box = tk.Frame(f, bg=T.bg_code, padx=10, pady=6,
                       highlightbackground=T.border, highlightthickness=1)
        box.pack(fill="x", pady=(4,10))
        t = tk.Text(box, height=1, bg=T.bg_code, fg=T.ok, font=F.code, relief="flat")
        t.insert("1.0", cmd); t.configure(state="disabled"); t.pack(fill="x")
        tail = "\n".join(output.strip().splitlines()[-6:])
        if tail:
            tk.Label(f, text="pip output:", font=F.small_b,
                     bg=T.bg_surface, fg=T.fg_muted).pack(anchor="w")
            ob = tk.Frame(f, bg=T.bg_code, padx=8, pady=6,
                          highlightbackground=T.border, highlightthickness=1)
            ob.pack(fill="x", pady=(2,10))
            ot = tk.Text(ob, height=5, bg=T.bg_code, fg=T.fg_muted,
                         font=F.code, relief="flat", wrap="word")
            ot.insert("1.0", tail); ot.configure(state="disabled"); ot.pack(fill="x")
        bf = tk.Frame(f, bg=T.bg_surface); bf.pack(fill="x")
        tk.Button(bf, text="Retry", command=self._build,
                  bg=T.btn_primary, fg=T.btn_primary_fg, relief="flat",
                  font=F.body_b, padx=16, pady=6, cursor="hand2"
                  ).pack(side="left")
        if not self.checker.missing_required:
            tk.Button(bf, text="Continue", command=self._continue,
                      bg=T.btn_bg, fg=T.btn_fg, relief="flat",
                      font=F.body, padx=16, pady=6, cursor="hand2"
                      ).pack(side="left", padx=(8,0))
        else:
            tk.Button(bf, text="Quit", command=self._close,
                      bg=T.btn_bg, fg=T.btn_fg, relief="flat",
                      font=F.body, padx=16, pady=6, cursor="hand2"
                      ).pack(side="left", padx=(8,0))

    def _continue(self): self.proceed=True; self.destroy()
    def _close(self):    self.proceed=False; self.destroy()


# Slider Panel

METER_W = 52
METER_H = 200


class SliderSettingsDialog(tk.Toplevel):
    """Per-slider settings: mute, invert, and min/max calibration.

    Reads current values from config_mgr.get_slider_settings(index) and
    writes back via config_mgr.set_slider_setting(index, key, value).
    Calls on_apply() after saving so the caller can restart serial.
    """

    # Smoothing dropdown: label -> stored value (None means "use global")
    _SMOOTH_LABELS = {
        "Use Global": None,
        "Low (responsive)": 0.85,
        "Medium": 0.6,
        "High (smooth)": 0.3,
    }

    def __init__(self, parent, config_mgr, index: int,
                 label: str, get_raw=None, on_apply=None):
        super().__init__(parent)
        self.config_mgr = config_mgr
        self.index      = index
        self._get_raw   = get_raw     # callable -> current raw ADC for this slider
        self._on_apply  = on_apply
        self.title(f"{label} - Settings")
        self.configure(bg=T.bg_surface)
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        s = config_mgr.get_slider_settings(index)
        self._muted_var  = tk.BooleanVar(value=bool(s["muted"]))
        self._invert_var = tk.BooleanVar(value=bool(s["invert"]))
        self._cal_min    = int(s["cal_min"])
        self._cal_max    = int(s["cal_max"])
        self._smoothing  = s["smoothing"]   # None = use global, else a float
        self._poll_job   = None             # live-raw polling timer
        self._build(label)
        # Grab only once the window is actually on-screen - calling grab_set()
        # before the window is viewable raises "grab failed: window not viewable".
        self.after(10, self._safe_grab)

    def _safe_grab(self):
        try:
            self.grab_set()
        except Exception:
            pass

    def _build(self, label):
        outer = tk.Frame(self, bg=T.bg_surface, padx=28, pady=24)
        outer.pack()

        tk.Label(outer, text=label, font=F.header,
                 bg=T.bg_surface, fg=T.accent
                 ).pack(anchor="w", pady=(0, 2))
        tk.Label(outer, text="Per-slider hardware settings",
                 font=F.small, bg=T.bg_surface, fg=T.fg_muted
                 ).pack(anchor="w", pady=(0, 16))

        def checkrow(text, var, hint):
            tk.Checkbutton(outer, text=text, variable=var, font=F.body,
                           bg=T.bg_surface, fg=T.fg,
                           activebackground=T.bg_surface, activeforeground=T.fg,
                           selectcolor=T.bg_input, highlightthickness=0, bd=0,
                           cursor="hand2", anchor="w"
                           ).pack(anchor="w", fill="x")
            tk.Label(outer, text=hint, font=F.tiny, bg=T.bg_surface,
                     fg=T.fg_subtle, anchor="w", justify="left",
                     wraplength=320).pack(anchor="w", pady=(0, 12))

        checkrow("Mute this slider", self._muted_var,
                 "Forces this slider's level to 0% until unmuted.")
        checkrow("Flip this slider's direction", self._invert_var,
                 "Reverses just this slider - useful when one pot is wired "
                 "backwards while the others are correct.")

        # Calibration
        tk.Frame(outer, bg=T.separator, height=1
                 ).pack(fill="x", pady=(0, 12))
        tk.Label(outer, text="Calibration", font=F.body_b,
                 bg=T.bg_surface, fg=T.fg).pack(anchor="w")
        tk.Label(outer,
                 text="Set the raw values your pot reaches at each extreme so "
                      "it maps cleanly to 0–100%. Turn the pot fully, then "
                      "click Capture.",
                 font=F.tiny, bg=T.bg_surface, fg=T.fg_subtle,
                 wraplength=320, justify="left").pack(anchor="w", pady=(0, 8))

        cal = tk.Frame(outer, bg=T.bg_surface)
        cal.pack(fill="x", pady=(0, 4))

        # Min
        tk.Label(cal, text="Min (0%)", font=F.small, bg=T.bg_surface,
                 fg=T.fg_muted, width=10, anchor="w").grid(row=0, column=0, pady=3)
        self._min_lbl = tk.Label(cal, text=str(self._cal_min), font=F.body_b,
                                 bg=T.bg_surface, fg=T.accent_soft, width=6)
        self._min_lbl.grid(row=0, column=1, padx=6)
        RoundedButton(cal, text="Capture", command=self._capture_min,
                      style="default", width=84, height=30, font=F.small,
                      bg_under=T.bg_surface).grid(row=0, column=2)

        # Max
        tk.Label(cal, text="Max (100%)", font=F.small, bg=T.bg_surface,
                 fg=T.fg_muted, width=10, anchor="w").grid(row=1, column=0, pady=3)
        self._max_lbl = tk.Label(cal, text=str(self._cal_max), font=F.body_b,
                                 bg=T.bg_surface, fg=T.accent_soft, width=6)
        self._max_lbl.grid(row=1, column=1, padx=6)
        RoundedButton(cal, text="Capture", command=self._capture_max,
                      style="default", width=84, height=30, font=F.small,
                      bg_under=T.bg_surface).grid(row=1, column=2)

        RoundedButton(outer, text="Reset calibration", command=self._reset_cal,
                      style="ghost", width=150, height=28, font=F.tiny,
                      bg_under=T.bg_surface).pack(anchor="w", pady=(8, 0))

        # Live raw value readout (updates as the pot is turned) - makes
        # calibration much easier than guessing.
        live = tk.Frame(outer, bg=T.bg_surface)
        live.pack(anchor="w", pady=(10, 0))
        tk.Label(live, text="Live raw value:", font=F.tiny,
                 bg=T.bg_surface, fg=T.fg_muted).pack(side="left")
        self._raw_lbl = tk.Label(live, text="-", font=F.small_b,
                                 bg=T.bg_surface, fg=T.accent_soft, width=6)
        self._raw_lbl.pack(side="left", padx=(6, 0))
        self._poll_raw()   # start the live update loop

        # Smoothing override
        tk.Frame(outer, bg=T.separator, height=1).pack(fill="x", pady=(14, 12))
        sm = tk.Frame(outer, bg=T.bg_surface)
        sm.pack(fill="x")
        tk.Label(sm, text="Smoothing", font=F.body_b,
                 bg=T.bg_surface, fg=T.fg).pack(anchor="w")
        tk.Label(sm, text="How much this slider's movement is smoothed. "
                          "'Use Global' follows the app-wide setting.",
                 font=F.tiny, bg=T.bg_surface, fg=T.fg_subtle,
                 wraplength=320, justify="left").pack(anchor="w", pady=(0, 6))
        self._smooth_var = tk.StringVar(
            value=self._smoothing_to_label(self._smoothing))
        ttk.Combobox(sm, textvariable=self._smooth_var,
                     values=list(self._SMOOTH_LABELS.keys()),
                     width=16, state="readonly", font=F.small
                     ).pack(anchor="w")

        # Buttons
        tk.Frame(outer, bg=T.separator, height=1
                 ).pack(fill="x", pady=(14, 14))
        bf = tk.Frame(outer, bg=T.bg_surface)
        bf.pack()
        RoundedButton(bf, text="Save", command=self._save, style="primary",
                      width=110, height=36, font=F.body_b,
                      bg_under=T.bg_surface).pack(side="left")
        RoundedButton(bf, text="Cancel", command=self._cancel, style="default",
                      width=110, height=36, font=F.body,
                      bg_under=T.bg_surface).pack(side="left", padx=(10, 0))

    @classmethod
    def _smoothing_to_label(cls, value):
        """Map a stored smoothing value back to its dropdown label."""
        for label, v in cls._SMOOTH_LABELS.items():
            if v is None and value is None:
                return label
            if v is not None and value is not None and abs(v - value) < 0.001:
                return label
        return "Use Global"   # unknown custom value falls back

    def _poll_raw(self):
        """Update the live raw-value label ~5×/sec while the dialog is open."""
        if self._get_raw:
            v = self._get_raw()
            if v is not None and self._raw_lbl.winfo_exists():
                self._raw_lbl.config(text=str(int(v)))
        self._poll_job = self.after(200, self._poll_raw)

    def _cancel(self):
        if self._poll_job:
            try: self.after_cancel(self._poll_job)
            except Exception: pass
            self._poll_job = None
        self.destroy()

    def _capture_min(self):
        if self._get_raw:
            v = self._get_raw()
            if v is not None:
                self._cal_min = int(v); self._min_lbl.config(text=str(self._cal_min))

    def _capture_max(self):
        if self._get_raw:
            v = self._get_raw()
            if v is not None:
                self._cal_max = int(v); self._max_lbl.config(text=str(self._cal_max))

    def _reset_cal(self):
        self._cal_min, self._cal_max = 0, 1023
        self._min_lbl.config(text="0"); self._max_lbl.config(text="1023")

    def _save(self):
        i = self.index
        self.config_mgr.set_slider_setting(i, "muted", bool(self._muted_var.get()))
        self.config_mgr.set_slider_setting(i, "invert", bool(self._invert_var.get()))
        # Guard against inverted/empty calibration range
        lo, hi = self._cal_min, self._cal_max
        if hi <= lo:
            lo, hi = 0, 1023
        self.config_mgr.set_slider_setting(i, "cal_min", lo)
        self.config_mgr.set_slider_setting(i, "cal_max", hi)
        # Per-slider smoothing override (None = use global)
        self.config_mgr.set_slider_setting(
            i, "smoothing", self._SMOOTH_LABELS.get(self._smooth_var.get()))
        if self._poll_job:
            try: self.after_cancel(self._poll_job)
            except Exception: pass
            self._poll_job = None
        if self._on_apply:
            self._on_apply()
        self.destroy()


class TargetPicker(tk.Toplevel):
    """Multi-select popup for choosing what a slider controls.

    Rules enforced live:
      - The three special targets (Master / All Others / Unassigned) are
        mutually exclusive with each other AND with apps. Selecting one
        clears any app ticks and the other specials.
      - Ticking one or more apps clears any special selection.
    Result passed to on_apply is either a keyword string
    ('none'|'master'|'all_others') or a list[str] of app names.
    """

    _SPECIALS = [("master", "Master volume"),
                 ("all_others", "All other apps"),
                 ("none", "Nothing (unassigned)")]

    def __init__(self, parent, available_apps, current, on_apply=None):
        super().__init__(parent)
        self._on_apply = on_apply
        self.title("Assign slider")
        self.configure(bg=T.bg_surface)
        self.resizable(False, False)
        self.transient(parent)

        # Seed selection state
        cur_apps = set(current) if isinstance(current, list) else set()
        cur_special = current if isinstance(current, str) else None
        if cur_special not in ("master", "all_others", "none"):
            cur_special = None if cur_apps else "none"

        self._special_var = tk.StringVar(value=cur_special or "")
        # Union of running apps and any already-assigned (maybe not running) apps
        apps = list(dict.fromkeys(list(available_apps) + sorted(cur_apps)))
        self._app_vars = {a: tk.BooleanVar(value=(a in cur_apps)) for a in apps}

        self._build(apps)
        self.after(10, self._safe_grab)

    def _safe_grab(self):
        try: self.grab_set()
        except Exception: pass

    def _build(self, apps):
        outer = tk.Frame(self, bg=T.bg_surface, padx=24, pady=20)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="What should this slider control?",
                 font=F.body_b, bg=T.bg_surface, fg=T.fg
                 ).pack(anchor="w", pady=(0, 2))
        tk.Label(outer,
                 text="Pick a single special target, or tick one or more apps.",
                 font=F.tiny, bg=T.bg_surface, fg=T.fg_muted
                 ).pack(anchor="w", pady=(0, 12))

        # Special targets - custom glyph rows (○ hollow / ● filled) so the
        # selected/unselected look is fully under our control and reliably
        # shows hollow when apps are ticked instead. Clicking a row selects
        # that special and clears all app ticks.
        self._special_rows = {}   # key -> (glyph_label, text_label)
        for key, label in self._SPECIALS:
            row = tk.Frame(outer, bg=T.bg_surface, cursor="hand2")
            row.pack(anchor="w", fill="x", pady=2)
            glyph = tk.Label(row, text="○", font=(F.ui, 15),
                             bg=T.bg_surface, fg=T.fg_muted, width=2)
            glyph.pack(side="left")
            txt = tk.Label(row, text=label, font=F.body,
                           bg=T.bg_surface, fg=T.fg, anchor="w")
            txt.pack(side="left")
            for w in (row, glyph, txt):
                w.bind("<Button-1>", lambda e, k=key: self._pick_special(k))
            self._special_rows[key] = (glyph, txt)

        tk.Frame(outer, bg=T.separator, height=1).pack(fill="x", pady=12)
        tk.Label(outer, text="Applications", font=F.small_b,
                 bg=T.bg_surface, fg=T.fg_muted).pack(anchor="w", pady=(0, 6))

        if apps:
            # Scrollable list if there are many apps
            list_host = tk.Frame(outer, bg=T.bg_surface)
            list_host.pack(fill="both", expand=True)
            max_h = 200
            canvas = tk.Canvas(list_host, bg=T.bg_surface, highlightthickness=0,
                               height=min(max_h, max(28, len(apps) * 32)))
            inner = tk.Frame(canvas, bg=T.bg_surface)
            canvas.create_window((0, 0), window=inner, anchor="nw")
            if len(apps) * 32 > max_h:
                sb = ttk.Scrollbar(list_host, orient="vertical",
                                   command=canvas.yview)
                canvas.configure(yscrollcommand=sb.set)
                sb.pack(side="right", fill="y")
                inner.bind("<Configure>",
                           lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.pack(side="left", fill="both", expand=True)

            self._app_rows = {}   # app -> glyph label
            for a in apps:
                row = tk.Frame(inner, bg=T.bg_surface, cursor="hand2")
                row.pack(anchor="w", fill="x", pady=1)
                glyph = tk.Label(row, text=("☑" if self._app_vars[a].get() else "☐"),
                                 font=(F.ui, 15), bg=T.bg_surface,
                                 fg=T.accent_soft if self._app_vars[a].get()
                                 else T.fg_muted, width=2)
                glyph.pack(side="left")
                txt = tk.Label(row, text=a, font=F.body,
                               bg=T.bg_surface, fg=T.fg, anchor="w")
                txt.pack(side="left")
                for w in (row, glyph, txt):
                    w.bind("<Button-1>", lambda e, k=a: self._toggle_app(k))
                self._app_rows[a] = glyph
        else:
            tk.Label(outer, text="No apps are currently playing audio.",
                     font=F.tiny, bg=T.bg_surface, fg=T.fg_subtle
                     ).pack(anchor="w")
            self._app_rows = {}

        # Buttons
        tk.Frame(outer, bg=T.separator, height=1).pack(fill="x", pady=(14, 14))
        bf = tk.Frame(outer, bg=T.bg_surface)
        bf.pack()
        RoundedButton(bf, text="Apply", command=self._apply, style="primary",
                      width=110, height=34, font=F.body_b,
                      bg_under=T.bg_surface).pack(side="left")
        RoundedButton(bf, text="Cancel", command=self.destroy, style="default",
                      width=110, height=34, font=F.body,
                      bg_under=T.bg_surface).pack(side="left", padx=(10, 0))

        self._refresh_glyphs()   # set initial ○/●/☐/☑ state

    # -- mutual-exclusion logic --
    def _pick_special(self, key):
        # Selecting a special target clears all app ticks (mutually exclusive)
        self._special_var.set(key)
        for v in self._app_vars.values():
            v.set(False)
        self._refresh_glyphs()

    def _toggle_app(self, app):
        var = self._app_vars[app]
        var.set(not var.get())
        # Ticking any app clears the special selection so the two never mix
        if any(v.get() for v in self._app_vars.values()):
            self._special_var.set("")
        self._refresh_glyphs()

    def _refresh_glyphs(self):
        """Sync every ○/● radio glyph and ☐/☑ app glyph to current state.
        With apps ticked, the special var is empty so all radios show hollow."""
        sel = self._special_var.get()
        for key, (glyph, _txt) in getattr(self, "_special_rows", {}).items():
            on = (key == sel)
            glyph.config(text="●" if on else "○",
                         fg=T.accent_soft if on else T.fg_muted)
        for app, glyph in getattr(self, "_app_rows", {}).items():
            on = self._app_vars[app].get()
            glyph.config(text="☑" if on else "☐",
                         fg=T.accent_soft if on else T.fg_muted)

    def _apply(self):
        special = self._special_var.get()
        chosen_apps = [a for a, v in self._app_vars.items() if v.get()]
        if chosen_apps:
            result = chosen_apps
        elif special in ("master", "all_others", "none"):
            result = special
        else:
            result = "none"
        if self._on_apply:
            self._on_apply(result)
        self.destroy()


class SliderPanel(tk.Frame):
    """
    One hardware-slider card: editable label, app dropdown, dot status
    indicator, rounded VU meter, and percentage. Subtle hover lift.
    Themed at creation; call rebuild_theme() to re-skin after a toggle.
    """

    CORNER = 8   # meter corner radius

    def __init__(self, parent, index: int,
                 on_change: Optional[Callable] = None,
                 on_label_change: Optional[Callable] = None,
                 on_settings: Optional[Callable] = None, **kw):
        super().__init__(parent, bg=T.bg_card,
                         highlightbackground=T.border,
                         highlightthickness=1, **kw)
        self.index           = index
        self._on_change      = on_change
        self._on_label_change = on_label_change
        self._on_settings    = on_settings
        self._value          = 0.0
        self._active_state   = "unassigned"
        self._label_text     = f"Slider {index + 1}"
        self._muted          = False
        self._build()
        # Hover lift on the whole card
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")

    # Build                                                                #

    def _build(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(bg=T.bg_card, highlightbackground=T.border)

        # Accent strip across the top of the card
        tk.Frame(self, bg=T.accent, height=3).pack(fill="x")

        inner = tk.Frame(self, bg=T.bg_card, padx=16, pady=16)
        inner.pack(fill="both", expand=True)

        # ── Header: numbered badge + editable label + rename pencil ──
        hdr = tk.Frame(inner, bg=T.bg_card)
        hdr.pack(fill="x", pady=(0, 12))

        tk.Label(hdr, text=str(self.index + 1),
                 font=F.badge, bg=T.accent, fg=T.accent_fg,
                 width=2, padx=3, pady=2).pack(side="left")

        self._label_lbl = tk.Label(hdr, text=self._label_text,
                                    font=F.body_b, bg=T.bg_card, fg=T.fg,
                                    anchor="w", cursor="hand2")
        self._label_lbl.pack(side="left", padx=(8, 0))
        self._label_lbl.bind("<Button-1>", lambda e: self._begin_rename())

        pencil = tk.Label(hdr, text="✎", font=F.small, bg=T.bg_card,
                          fg=T.fg_subtle, cursor="hand2")
        pencil.pack(side="right")
        pencil.bind("<Button-1>", lambda e: self._begin_rename())
        pencil.bind("<Enter>", lambda e: pencil.config(fg=T.accent_soft))
        pencil.bind("<Leave>", lambda e: pencil.config(fg=T.fg_subtle))
        Tooltip(pencil, "Rename this slider")

        gear = tk.Label(hdr, text="⋯", font=F.body_b, bg=T.bg_card,
                        fg=T.fg_subtle, cursor="hand2")
        gear.pack(side="right", padx=(0, 6))
        gear.bind("<Button-1>", lambda e: self._open_settings())
        gear.bind("<Enter>", lambda e: gear.config(fg=T.accent_soft))
        gear.bind("<Leave>", lambda e: gear.config(fg=T.fg_subtle))
        Tooltip(gear, "Mute, invert, or calibrate this slider")

        # ── Target selector: a button that opens a multi-select popup ──
        # A slider can control one special target (Master / All Others /
        # Unassigned) OR any number of individual apps - never a mix.
        self._target_value = "none"        # str keyword, or list[str] of apps
        self._available_apps: List[str] = []
        self._target_btn = RoundedButton(
            inner, text="Unassigned", command=self._open_target_picker,
            style="default", width=10, height=30, font=F.small,
            bg_under=T.bg_card)
        self._target_btn.pack(fill="x")

        # ── Status: coloured dot + short label ──
        status_row = tk.Frame(inner, bg=T.bg_card)
        status_row.pack(fill="x", pady=(8, 14))
        self._status_dot = tk.Label(status_row, text="●", font=F.small,
                                    bg=T.bg_card, fg=T.fg_subtle)
        self._status_dot.pack(side="left")
        self._status_txt = tk.Label(status_row, text="Unassigned", font=F.small,
                                    bg=T.bg_card, fg=T.fg_muted, anchor="w")
        self._status_txt.pack(side="left", padx=(6, 0))

        # ── VU meter (Canvas, rounded). Fills its frame horizontally so the
        # bar widens with the window; height stays fixed. ──
        meter_frame = tk.Frame(inner, bg=T.bg_card)
        meter_frame.pack(fill="x", pady=(0, 4))
        self._meter_w = METER_W   # current drawn width; updated on <Configure>
        self._last_pct = -1       # set before the Configure bind below
        self._canvas = tk.Canvas(meter_frame, width=METER_W,
                                 height=METER_H, bg=T.bg_card,
                                 highlightthickness=0)
        self._canvas.pack(fill="x")
        self._canvas.bind("<Configure>", self._on_meter_resize)
        self._build_meter()

        # ── Percentage / state readout ──
        self._pct_label = tk.Label(inner, text="0%",
                                   font=F.header, bg=T.bg_card,
                                   fg=T.fg, anchor="center")
        self._pct_label.pack(pady=(10, 0))

    def _round_rect(self, x1, y1, x2, y2, r):
        """Coordinate list for a smooth rounded rectangle polygon."""
        return [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y2-r, x2, y2,
                x2-r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y1+r, x1, y1]

    def _on_meter_resize(self, event):
        """Canvas width changed (window resized) - redraw to the new width."""
        if event.width > 1 and abs(event.width - self._meter_w) >= 1:
            self._meter_w = event.width
            self._build_meter()
            self._last_pct = -2     # force the fill bar to redraw at new width
            self.set_value(self._value)

    def _build_meter(self):
        w = self._meter_w
        r = self.CORNER
        m = 4   # inset margin so the fill sits inside the track
        self._canvas.delete("all")
        # Track always uses the normal track colour; the FILL colour conveys
        # state (grey=none, dim=app not running, green/red=active).
        self._track_id = self._canvas.create_polygon(
            self._round_rect(0, 0, w, METER_H, r),
            smooth=True, splinesteps=12, fill=T.meter_track, outline="")
        # Fill bar (rounded) - inset, starts at zero height
        self._bar_id = self._canvas.create_polygon(
            self._round_rect(m, METER_H - m, w - m, METER_H - m, r - m),
            smooth=True, splinesteps=12, fill=T.meter_low, outline="")
        # Tick marks (subtle, inside the track on the right edge)
        for pct in (0.25, 0.50, 0.75):
            y = int(METER_H * (1 - pct))
            self._canvas.create_line(w - 8, y, w - 4, y,
                                     fill=T.fg_subtle, width=1)

    # Public API                                                           #

    def set_value(self, value: float):
        self._value = max(0.0, min(1.0, value))
        pct = int(self._value * 100)
        if pct == self._last_pct:
            return
        self._last_pct = pct
        if self._active_state in ("none", "unassigned"):
            self._pct_label.config(text="-", fg=T.fg_subtle)
        else:
            self._pct_label.config(text=f"{pct}%", fg=T.fg)
        self._draw_bar()

    _SPECIAL = {"none": "Unassigned", "master": "Master", "all_others": "All Others"}

    def set_dropdown_values(self, values: List[str]):
        """Receive the current list of assignable app targets (running apps,
        minus those owned by other sliders). Stored for the picker popup."""
        self._available_apps = list(values)

    def get_target(self):
        """Return the slider's target: a keyword string
        ('none'|'master'|'all_others') or a list[str] of app names."""
        return self._target_value

    def set_target(self, target):
        """Accept a keyword string, a single app name, or a list of apps.
        A single non-special string is normalised to a one-item list."""
        if isinstance(target, list):
            apps = [a for a in target if a and str(a).strip()]
            self._target_value = apps if apps else "none"
        else:
            t = (target or "").strip()
            if t == "" or t.lower() in self._SPECIAL:
                self._target_value = t.lower() if t else "none"
            else:
                self._target_value = [t]
        self._update_target_button()

    def _target_summary(self) -> str:
        """Human label for the current target shown on the button."""
        v = self._target_value
        if isinstance(v, list):
            if not v:
                return "Unassigned"
            if len(v) == 1:
                return v[0]
            return f"{len(v)} apps"
        return self._SPECIAL.get(v, v or "Unassigned")

    def _update_target_button(self):
        if hasattr(self, "_target_btn"):
            self._target_btn.set_text(self._target_summary())

    def _open_target_picker(self):
        TargetPicker(self.winfo_toplevel(), self._available_apps,
                     self._target_value, on_apply=self._on_picker_apply)

    def _on_picker_apply(self, new_target):
        self._target_value = new_target
        self._update_target_button()
        if self._on_change:
            self._on_change(self)

    def get_label(self) -> str:
        return self._label_text

    def set_label(self, label: str):
        self._label_text = label or f"Slider {self.index + 1}"
        if hasattr(self, "_label_lbl") and self._label_lbl.winfo_exists():
            self._label_lbl.config(text=self._label_text)

    def set_active(self, state: str):
        """state: 'active' | 'inactive' | 'none' | 'unassigned'"""
        prev = self._active_state
        self._active_state = state
        if not hasattr(self, "_status_dot") or not self._status_dot.winfo_exists():
            return
        # When muted, the status row shows "Muted" - keep it, but we've still
        # recorded the real state above so unmuting restores the right label.
        if not self._muted:
            spec = {
                "active":     (T.ok,        "Active"),
                "inactive":   (T.warn,      "Not running"),
                "none":       (T.fg_subtle, "None"),
                "unassigned": (T.fg_subtle, "Unassigned"),
            }.get(state, (T.fg_subtle, "Unassigned"))
            self._status_dot.config(fg=spec[0])
            self._status_txt.config(text=spec[1])
        # State affects the FILL colour (grey/dim/active), so force a redraw
        # of the bar whenever the state changes.
        if prev != state:
            self._last_pct = -2   # force set_value to redraw the bar
            self.set_value(self._value)

    def rebuild_theme(self):
        saved_target = self._target_value
        saved_apps   = self._available_apps
        self._build()
        self._available_apps = saved_apps
        self.set_target(saved_target)
        self.set_label(self._label_text)
        self.set_value(self._value)
        self.set_active(self._active_state)
        self.set_muted(self._muted)

    # Rename flow                                                          #

    def _begin_rename(self):
        new = simpledialog.askstring(
            "Rename Slider", "Label for this slider:",
            initialvalue=self._label_text, parent=self.winfo_toplevel())
        if new is None:
            return
        new = new.strip() or f"Slider {self.index + 1}"
        self.set_label(new)
        if self._on_label_change:
            self._on_label_change(self)

    def _open_settings(self):
        if self._on_settings:
            self._on_settings(self)

    def set_muted(self, muted: bool):
        """Reflect mute state on the badge/label (level is forced to 0 in
        the serial layer; this is purely the visual cue)."""
        self._muted = muted
        if hasattr(self, "_label_lbl") and self._label_lbl.winfo_exists():
            self._label_lbl.config(fg=T.fg_subtle if muted else T.fg)
        if hasattr(self, "_status_txt") and self._status_txt.winfo_exists():
            if muted:
                self._status_dot.config(fg=T.err)
                self._status_txt.config(text="Muted")
            else:
                self.set_active(self._active_state)

    # Drawing / hover                                                      #

    def _draw_bar(self):
        v = self._value
        r = self.CORNER
        m = 4   # must match the inset in _build_meter
        w = self._meter_w
        usable = METER_H - 2 * m
        bar_h = int(v * usable)
        bottom = METER_H - m
        top_y = bottom - bar_h
        # Colour by state:
        #   none / unassigned  → grey (controls nothing)
        #   inactive (app not running) → dimmed green
        #   active → normal green→red
        #   muted handled separately (forced to 0 + red label)
        state = self._active_state
        if state in ("none", "unassigned"):
            colour = T.meter_idle
        elif state == "inactive":
            colour = T.meter_dim
        else:
            colour = T.meter_low if v < 0.80 else T.meter_high
        rr = min(r - m, max(0, bar_h // 2))
        self._canvas.coords(self._bar_id,
                            *self._round_rect(m, top_y, w - m, bottom, rr))
        self._canvas.itemconfig(self._bar_id, fill=colour)

    def _on_enter(self, _=None):
        self.configure(highlightbackground=T.accent)

    def _on_leave(self, _=None):
        self.configure(highlightbackground=T.border)

