"""
gui/settings_dialog.py  —  themed settings modal
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional
from gui.theme import T, F

BAUD_RATES = ["9600","19200","38400","57600","115200"]


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, config_mgr, list_ports: Callable,
                 on_save: Optional[Callable] = None):
        super().__init__(parent)
        self.config_mgr = config_mgr
        self._list_ports = list_ports
        self._on_save   = on_save
        self.title("Settings — BARJ Volume Controller")
        self.configure(bg=T.bg_surface)
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self._build()

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
            value=self.config_mgr.get("sliders","smoothing",default=0.15))
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
        row("Invert Sliders", 7)
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

        # Separator
        tk.Frame(outer, bg=T.separator, height=1
                 ).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(0,14))

        # Buttons
        bf = tk.Frame(outer, bg=T.bg_surface)
        bf.grid(row=9, column=0, columnspan=2)
        tk.Button(bf, text="Save", command=self._save,
                  bg=T.btn_primary, fg=T.btn_primary_fg, relief="flat",
                  font=F.body_b, padx=20, pady=7, cursor="hand2"
                  ).pack(side="left")
        tk.Button(bf, text="Cancel", command=self.destroy,
                  bg=T.btn_bg, fg=T.btn_fg, relief="flat",
                  font=F.body, padx=20, pady=7, cursor="hand2"
                  ).pack(side="left", padx=(8,0))

    def _refresh_ports(self):
        ports = self._list_ports()
        self._port_combo["values"] = ports
        if not self._port_var.get() and ports:
            self._port_var.set(ports[0])

    def _save(self):
        count = self._count_var.get()
        if not 1 <= count <= 12:
            messagebox.showwarning("Invalid","Slider count must be 1–12.",parent=self)
            return
        self.config_mgr.set(self._port_var.get(),         "serial","port")
        self.config_mgr.set(int(self._baud_var.get()),    "serial","baud_rate")
        self.config_mgr.set(int(count),                   "sliders","count")
        self.config_mgr.set(round(self._smooth_var.get(),2), "sliders","smoothing")
        self.config_mgr.set(bool(self._invert_var.get()),    "sliders","invert")
        # Map the displayed label back to its config key
        label_to_key = {v: k for k, v in self._close_labels.items()}
        self.config_mgr.set(
            label_to_key.get(self._close_var.get(), "ask"), "ui", "close_action")
        if self._on_save: self._on_save()
        self.destroy()
