"""
gui/settings_dialog.py
Modal settings dialog for serial port, baud rate, slider count, and smoothing.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional

BG       = "#1e1e2e"
BG_FIELD = "#313244"
FG       = "#cdd6f4"
ACCENT   = "#cba6f7"
BTN_BG   = "#45475a"

BAUD_RATES = ["9600", "19200", "38400", "57600", "115200"]


class SettingsDialog(tk.Toplevel):
    """
    Modal settings window.

    Parameters
    ----------
    parent     : parent widget
    config_mgr : ConfigManager instance
    list_ports : callable returning list of serial port strings
    on_save    : called (no args) after settings are saved
    """

    def __init__(
        self,
        parent,
        config_mgr,
        list_ports: Callable[[], list],
        on_save: Optional[Callable] = None,
    ):
        super().__init__(parent)
        self.config_mgr = config_mgr
        self._list_ports = list_ports
        self._on_save = on_save

        self.title("Settings")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()          # modal
        self.transient(parent)

        self._build()
        self._refresh_ports()
        self.wait_window()

    # ------------------------------------------------------------------ #
    # Build                                                                #
    # ------------------------------------------------------------------ #

    def _build(self):
        pad = {"padx": 12, "pady": 6}

        frame = tk.Frame(self, bg=BG, padx=24, pady=20)
        frame.pack()

        def label(text, row):
            tk.Label(
                frame, text=text, bg=BG, fg=FG,
                font=("Segoe UI", 10), anchor="w"
            ).grid(row=row, column=0, sticky="w", **pad)

        # ---- Serial Port ----
        label("Serial Port", 0)
        port_frame = tk.Frame(frame, bg=BG)
        port_frame.grid(row=0, column=1, sticky="w", **pad)

        self._port_var = tk.StringVar(value=self.config_mgr.get("serial", "port", default=""))
        self._port_combo = ttk.Combobox(port_frame, textvariable=self._port_var, width=14)
        self._port_combo.pack(side="left")

        tk.Button(
            port_frame, text="↻", command=self._refresh_ports,
            bg=BTN_BG, fg=FG, relief="flat", font=("Segoe UI", 11), cursor="hand2"
        ).pack(side="left", padx=(4, 0))

        # ---- Baud Rate ----
        label("Baud Rate", 1)
        self._baud_var = tk.StringVar(
            value=str(self.config_mgr.get("serial", "baud_rate", default=9600))
        )
        ttk.Combobox(
            frame, textvariable=self._baud_var,
            values=BAUD_RATES, width=10, state="readonly"
        ).grid(row=1, column=1, sticky="w", **pad)

        # ---- Slider Count ----
        label("Slider Count", 2)
        self._count_var = tk.IntVar(
            value=self.config_mgr.get("sliders", "count", default=5)
        )
        tk.Spinbox(
            frame, from_=1, to=12, textvariable=self._count_var,
            width=5, bg=BG_FIELD, fg=FG, insertbackground=FG,
            buttonbackground=BTN_BG, relief="flat", font=("Segoe UI", 10)
        ).grid(row=2, column=1, sticky="w", **pad)

        # ---- Smoothing ----
        label("Smoothing", 3)
        smooth_frame = tk.Frame(frame, bg=BG)
        smooth_frame.grid(row=3, column=1, sticky="w", **pad)

        self._smooth_var = tk.DoubleVar(
            value=self.config_mgr.get("sliders", "smoothing", default=0.15)
        )
        self._smooth_label = tk.Label(
            smooth_frame,
            text=f"{self._smooth_var.get():.2f}",
            bg=BG, fg=ACCENT, width=4, font=("Segoe UI", 9)
        )
        self._smooth_label.pack(side="right")

        tk.Scale(
            smooth_frame,
            from_=0.01, to=1.0, resolution=0.01, orient="horizontal",
            variable=self._smooth_var, length=120,
            bg=BG, fg=FG, troughcolor=BG_FIELD,
            highlightthickness=0, showvalue=False,
            command=lambda v: self._smooth_label.config(text=f"{float(v):.2f}")
        ).pack(side="left")

        tk.Label(
            frame,
            text="← more smooth          more responsive →",
            bg=BG, fg=FG_HINT, font=("Segoe UI", 8), justify="center"
        ).grid(row=4, column=0, columnspan=2)

        # ---- Buttons ----
        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(16, 0))

        tk.Button(
            btn_frame, text="Save", command=self._save,
            bg=ACCENT, fg="#1e1e2e", font=("Segoe UI", 10, "bold"),
            relief="flat", padx=16, pady=6, cursor="hand2"
        ).pack(side="left", padx=6)

        tk.Button(
            btn_frame, text="Cancel", command=self.destroy,
            bg=BTN_BG, fg=FG, font=("Segoe UI", 10),
            relief="flat", padx=16, pady=6, cursor="hand2"
        ).pack(side="left", padx=6)

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _refresh_ports(self):
        ports = self._list_ports()
        self._port_combo["values"] = ports
        if not self._port_var.get() and ports:
            self._port_var.set(ports[0])

    def _save(self):
        count = self._count_var.get()
        if count < 1 or count > 12:
            messagebox.showwarning("Invalid", "Slider count must be between 1 and 12.", parent=self)
            return

        self.config_mgr.set(self._port_var.get(), "serial", "port")
        self.config_mgr.set(int(self._baud_var.get()), "serial", "baud_rate")
        self.config_mgr.set(int(count), "sliders", "count")
        self.config_mgr.set(round(self._smooth_var.get(), 2), "sliders", "smoothing")

        if self._on_save:
            self._on_save()
        self.destroy()


# subtle grey hint colour used above
FG_HINT = "#585b70"
