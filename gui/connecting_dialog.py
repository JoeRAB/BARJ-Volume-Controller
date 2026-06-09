"""
gui/connecting_dialog.py

Animated "Connecting to hardware" dialog.
  - Appears immediately on launch (no delay)
  - Shows detected device names alongside port paths
  - Checkbox to suppress on future launches
  - Re-appears automatically when connection drops
  - Port can be changed without opening Settings
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
    Parameters
    ----------
    parent           : MainWindow (tk.Tk)
    get_port         : callable → current raw port string (e.g. '/dev/ttyACM0')
    list_port_labels : callable → list of display strings (e.g. ['/dev/ttyACM0 — Arduino Uno'])
    extract_port     : callable(display_str) → raw port string
    on_port_change   : called with raw port when user applies a new selection
    on_suppress      : called with bool — True means "don't show on launch" was ticked
    """

    POLL_MS   = 500
    RESHOW_MS = 3000

    def __init__(self, parent: tk.Tk,
                 get_port: Callable[[], str],
                 list_port_labels: Callable[[], List[str]],
                 extract_port: Callable[[str], str],
                 on_port_change: Callable[[str], None],
                 on_suppress: Callable[[bool], None],
                 show_on_launch: bool = True):
        super().__init__(parent)
        self._parent          = parent
        self._get_port        = get_port
        self._list_port_labels = list_port_labels
        self._extract_port    = extract_port
        self._on_port_change  = on_port_change
        self._on_suppress     = on_suppress

        self._dot_index  = 0
        self._dismissed  = False
        self._connected  = False
        self._anim_job: Optional[str] = None

        self.title("BARJ Volume Controller")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_user_close)

        self._build(show_on_launch)
        self._center()
        self._animate()

    # ------------------------------------------------------------------ #
    # Build                                                                #
    # ------------------------------------------------------------------ #

    def _build(self, show_on_launch: bool):
        outer = tk.Frame(self, bg=BG, padx=30, pady=24)
        outer.pack()

        tk.Label(outer, text="🔌  Connecting to Hardware",
                 font=("Segoe UI", 13, "bold"), bg=BG, fg=ACCENT
                 ).pack(pady=(0, 4))

        self._status_var = tk.StringVar()
        tk.Label(outer, textvariable=self._status_var,
                 font=("Segoe UI", 10), bg=BG, fg=WARN,
                 width=36, anchor="w"
                 ).pack(pady=(0, 16))

        # ---- Port selector ----
        port_frame = tk.Frame(outer, bg=BG)
        port_frame.pack(fill="x", pady=(0, 4))

        tk.Label(port_frame, text="Serial Port:", bg=BG, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(side="left")

        self._port_var = tk.StringVar()
        self._port_combo = ttk.Combobox(port_frame, textvariable=self._port_var,
                                        width=26, font=("Segoe UI", 9))
        self._port_combo.pack(side="left", padx=(6, 4))

        tk.Button(port_frame, text="↻", command=self._refresh_ports,
                  bg=BTN_BG, fg=FG, relief="flat",
                  font=("Segoe UI", 11), cursor="hand2"
                  ).pack(side="left")

        # Populate and pre-select current port
        self._refresh_ports()

        # Apply button
        tk.Button(outer, text="Apply Port & Reconnect",
                  command=self._apply_port,
                  bg=ACCENT, fg="#1e1e2e", relief="flat",
                  font=("Segoe UI", 10, "bold"),
                  padx=12, pady=5, cursor="hand2"
                  ).pack(fill="x", pady=(8, 0))

        # ---- Don't show on launch checkbox ----
        tk.Frame(outer, bg=BG, height=12).pack()   # spacer

        self._suppress_var = tk.BooleanVar(value=not show_on_launch)
        tk.Checkbutton(outer,
                       text="Don't show this dialog on launch",
                       variable=self._suppress_var,
                       command=self._on_suppress_changed,
                       bg=BG, fg=FG_MUTED,
                       selectcolor=BG,
                       activebackground=BG,
                       activeforeground=FG,
                       font=("Segoe UI", 9),
                       cursor="hand2"
                       ).pack(anchor="w")

        # Dismiss link
        tk.Button(outer, text="Dismiss  (app will keep trying in background)",
                  command=self._on_user_close,
                  bg=BG, fg=FG_MUTED, relief="flat",
                  font=("Segoe UI", 8), cursor="hand2"
                  ).pack(pady=(6, 0))

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def notify_connected(self):
        self._connected = True
        self._cancel_anim()
        if self.winfo_exists():
            self.destroy()

    def show_reconnecting(self):
        if self._dismissed:
            return
        self._connected = False
        if self.winfo_exists():
            self._port_var.set(
                self._find_current_label()
            )
            self.deiconify()
            self.lift()
        self._animate()

    def update_port_display(self, port: str):
        if self.winfo_exists():
            labels = self._list_port_labels()
            from serial_reader import SerialReader
            label  = SerialReader.find_label_for_port(port, labels)
            self._port_var.set(label)

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _find_current_label(self) -> str:
        """Match stored port to a display label, or return raw port."""
        raw = self._get_port()
        labels = self._list_port_labels()
        from serial_reader import SerialReader
        return SerialReader.find_label_for_port(raw, labels)

    def _refresh_ports(self):
        labels = self._list_port_labels()
        self._port_combo["values"] = labels
        self._port_var.set(self._find_current_label())

    def _apply_port(self):
        display = self._port_var.get().strip()
        if display:
            raw_port = self._extract_port(display)
            self._on_port_change(raw_port)

    def _on_suppress_changed(self):
        # suppress=True means "don't show" → show_on_launch=False
        self._on_suppress(not self._suppress_var.get())

    def _animate(self):
        if self._connected or not self.winfo_exists():
            return
        raw  = self._get_port()
        dots = DOTS[self._dot_index % len(DOTS)]
        self._status_var.set(f"Connecting to {raw}{dots}")
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
        w  = self.winfo_reqwidth()
        h  = self.winfo_reqheight()
        self.geometry(f"+{pw - w // 2}+{ph - h // 2}")
