"""
gui/connecting_dialog.py

Animated "Connecting to hardware" dialog that:
  - Appears on startup and whenever the Arduino disconnects
  - Auto-dismisses when the connection is established
  - Lets the user change the serial port without opening Settings
  - Can be dismissed manually (app still runs, status bar shows state)
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

BG       = "#1e1e2e"
BG_INNER = "#181825"
FG       = "#cdd6f4"
FG_MUTED = "#6c7086"
ACCENT   = "#cba6f7"
BTN_BG   = "#45475a"
WARN     = "#f9e2af"
OK       = "#a6e3a1"

DOTS = ["   ", ".  ", ".. ", "..."]


class ConnectingDialog(tk.Toplevel):
    """
    Shows while the app is waiting for the Arduino.
    Call `notify_connected()` to close it.
    Call `show()` to re-open it after a disconnect.

    Parameters
    ----------
    parent        : the MainWindow (tk.Tk)
    get_port      : callable returning the current port string
    list_ports    : callable returning list[str] of available ports
    on_port_change: called with (new_port: str) when user picks a port
    """

    POLL_MS   = 500    # how often to animate the dots
    RESHOW_MS = 3000   # delay before re-showing after a disconnect

    def __init__(self, parent: tk.Tk,
                 get_port: Callable[[], str],
                 list_ports: Callable[[], List[str]],
                 on_port_change: Callable[[str], None]):
        super().__init__(parent)
        self._parent        = parent
        self._get_port      = get_port
        self._list_ports    = list_ports
        self._on_port_change = on_port_change

        self._dot_index   = 0
        self._dismissed   = False   # user closed it intentionally
        self._connected   = False
        self._anim_job: Optional[str] = None

        self.title("BARJ Volume Controller")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)           # float above main window
        self.protocol("WM_DELETE_WINDOW", self._on_user_close)

        self._build()
        self._center()
        self._animate()

    # ------------------------------------------------------------------ #
    # Build                                                                #
    # ------------------------------------------------------------------ #

    def _build(self):
        outer = tk.Frame(self, bg=BG, padx=30, pady=24)
        outer.pack()

        # Icon + title
        tk.Label(outer, text="🔌  Connecting to Hardware",
                 font=("Segoe UI", 13, "bold"), bg=BG, fg=ACCENT
                 ).pack(pady=(0, 4))

        # Animated status line
        self._status_var = tk.StringVar()
        self._status_lbl = tk.Label(outer, textvariable=self._status_var,
                                    font=("Segoe UI", 10), bg=BG, fg=WARN,
                                    width=34, anchor="w")
        self._status_lbl.pack(pady=(0, 16))

        # ---- Port selector ----
        port_frame = tk.Frame(outer, bg=BG)
        port_frame.pack(fill="x", pady=(0, 4))

        tk.Label(port_frame, text="Serial Port:", bg=BG, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(side="left")

        self._port_var = tk.StringVar(value=self._get_port())
        self._port_combo = ttk.Combobox(port_frame, textvariable=self._port_var,
                                        width=18, font=("Segoe UI", 9))
        self._port_combo.pack(side="left", padx=(6, 4))

        tk.Button(port_frame, text="↻", command=self._refresh_ports,
                  bg=BTN_BG, fg=FG, relief="flat",
                  font=("Segoe UI", 11), cursor="hand2"
                  ).pack(side="left")

        self._refresh_ports()

        # Apply button
        tk.Button(outer, text="Apply Port & Reconnect",
                  command=self._apply_port,
                  bg=ACCENT, fg="#1e1e2e", relief="flat",
                  font=("Segoe UI", 10, "bold"),
                  padx=12, pady=5, cursor="hand2"
                  ).pack(fill="x", pady=(8, 0))

        # Dismiss link
        tk.Button(outer, text="Dismiss  (app will keep trying in background)",
                  command=self._on_user_close,
                  bg=BG, fg=FG_MUTED, relief="flat",
                  font=("Segoe UI", 8), cursor="hand2"
                  ).pack(pady=(10, 0))

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def notify_connected(self):
        """Call from main thread when serial connects — closes the dialog."""
        self._connected = True
        self._cancel_anim()
        if self.winfo_exists():
            self.destroy()

    def show_reconnecting(self):
        """Re-open after a disconnect (respects user dismiss preference)."""
        if self._dismissed:
            return
        self._connected = False

        if self.winfo_exists():
            self._port_var.set(self._get_port())
            self.deiconify()
            self.lift()
        # If it was destroyed (e.g. notify_connected), recreate isn't needed
        # because MainWindow creates a new instance on each disconnect.
        self._animate()

    def update_port_display(self, port: str):
        """Keep the port selector in sync if port changes elsewhere."""
        if self.winfo_exists():
            self._port_var.set(port)

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _refresh_ports(self):
        ports = self._list_ports()
        self._port_combo["values"] = ports
        if not self._port_var.get() and ports:
            self._port_var.set(ports[0])

    def _apply_port(self):
        new_port = self._port_var.get().strip()
        if new_port:
            self._on_port_change(new_port)

    def _animate(self):
        if self._connected or not self.winfo_exists():
            return
        port = self._get_port()
        dots = DOTS[self._dot_index % len(DOTS)]
        self._status_var.set(f"Connecting to {port}{dots}")
        self._dot_index += 1
        self._anim_job = self.after(self.POLL_MS, self._animate)

    def _cancel_anim(self):
        if self._anim_job:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None

    def _on_user_close(self):
        self._dismissed = True
        self._cancel_anim()
        if self.winfo_exists():
            self.withdraw()

    def _center(self):
        self.update_idletasks()
        pw = self._parent.winfo_x() + self._parent.winfo_width()  // 2
        ph = self._parent.winfo_y() + self._parent.winfo_height() // 2
        w  = self.winfo_width()
        h  = self.winfo_height()
        self.geometry(f"+{pw - w // 2}+{ph - h // 2}")
