"""
gui/connecting_dialog.py  —  themed hardware-connecting dialog
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional
from gui.theme import T, F

DOTS = ["   ", ".  ", ".. ", "..."]


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
