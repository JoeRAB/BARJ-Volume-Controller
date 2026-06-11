"""
gui/slider_panel.py  —  modern slider card with themed VU meter
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional
from gui.theme import T, F

METER_W = 44
METER_H = 180


class SliderPanel(tk.Frame):
    """
    One hardware-slider card: badge, label, app dropdown, VU meter, value.
    Themed at creation time; call rebuild_theme() to re-skin after a toggle.
    """

    def __init__(self, parent, index: int,
                 on_change: Optional[Callable] = None, **kw):
        super().__init__(parent, bg=T.bg_card,
                         highlightbackground=T.border,
                         highlightthickness=1, **kw)
        self.index      = index
        self._on_change = on_change
        self._value     = 0.0
        self._active_state = "unassigned"
        self._build()

    # ------------------------------------------------------------------ #
    # Build                                                                #
    # ------------------------------------------------------------------ #

    def _build(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(bg=T.bg_card, highlightbackground=T.border)

        # Thin accent strip at top
        tk.Frame(self, bg=T.accent, height=3).pack(fill="x")

        inner = tk.Frame(self, bg=T.bg_card, padx=10, pady=10)
        inner.pack(fill="both", expand=True)

        # Badge + header
        hdr = tk.Frame(inner, bg=T.bg_card)
        hdr.pack(fill="x", pady=(0, 6))

        badge = tk.Label(hdr, text=str(self.index + 1),
                         font=F.badge, bg=T.accent, fg=T.accent_fg,
                         width=2, padx=3, pady=1)
        badge.pack(side="left")

        tk.Label(hdr, text="Slider", font=F.tiny, bg=T.bg_card,
                 fg=T.fg_muted).pack(side="left", padx=(6, 0))

        # App dropdown
        self._target_var = tk.StringVar()
        self._target_var.trace_add("write", self._changed)
        self._combo = ttk.Combobox(inner, textvariable=self._target_var,
                                   width=14, font=F.small)
        self._combo.pack(fill="x", pady=(0, 2))

        # Assignment status: ● active / ○ not running / – unassigned
        self._status_lbl = tk.Label(inner, text="– unassigned",
                                    font=F.tiny, bg=T.bg_card,
                                    fg=T.fg_subtle, anchor="w")
        self._status_lbl.pack(fill="x", pady=(0, 8))

        # VU meter (Canvas)
        meter_frame = tk.Frame(inner, bg=T.bg_card)
        meter_frame.pack()

        self._canvas = tk.Canvas(meter_frame, width=METER_W,
                                 height=METER_H, bg=T.bg_card,
                                 highlightthickness=0)
        self._canvas.pack()

        # Track (background)
        r = METER_W // 2
        self._track_id = self._canvas.create_rectangle(
            4, 0, METER_W - 4, METER_H,
            fill=T.meter_track, outline="", width=0)

        # Fill bar (starts at zero)
        self._bar_id = self._canvas.create_rectangle(
            4, METER_H, METER_W - 4, METER_H,
            fill=T.meter_low, outline="", width=0)

        # Tick marks (25 / 50 / 75 %)
        for pct in (0.25, 0.50, 0.75):
            y = int(METER_H * (1 - pct))
            self._canvas.create_line(METER_W - 6, y, METER_W - 2, y,
                                     fill=T.fg_subtle, width=1)

        # Peak line
        self._peak_id = self._canvas.create_rectangle(
            4, METER_H, METER_W - 4, METER_H,
            fill=T.fg_muted, outline="", width=0)
        self._peak_value  = 0.0
        self._peak_hold   = 0

        # Percentage label
        self._pct_label = tk.Label(inner, text="0%",
                                   font=F.body_b, bg=T.bg_card,
                                   fg=T.fg, anchor="center")
        self._pct_label.pack(pady=(8, 0))

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def set_value(self, value: float):
        self._value = max(0.0, min(1.0, value))
        self._pct_label.config(text=f"{int(self._value * 100)}%")
        self._draw_bar()

    def set_dropdown_values(self, values: List[str]):
        # Only replace the option list; never touch the var — writing it
        # (even with the same value) fires the change trace.
        self._combo["values"] = values

    def get_target(self) -> str:
        return self._target_var.get().strip()

    def set_target(self, target: str):
        self._target_var.set(target or "")

    def set_active(self, state: str):
        """
        Update the assignment-status indicator.
        state: "active" | "inactive" | "unassigned"
        """
        self._active_state = state
        if not hasattr(self, "_status_lbl") or not self._status_lbl.winfo_exists():
            return
        if state == "active":
            self._status_lbl.config(text="● active", fg=T.ok)
        elif state == "inactive":
            self._status_lbl.config(text="○ not running", fg=T.warn)
        elif state == "none":
            self._status_lbl.config(text="– none", fg=T.fg_subtle)
        else:
            self._status_lbl.config(text="– unassigned", fg=T.fg_subtle)

    def rebuild_theme(self):
        """Re-skin after a theme toggle."""
        self._build()
        self.set_value(self._value)
        self.set_active(self._active_state)

    # ------------------------------------------------------------------ #
    # Drawing                                                              #
    # ------------------------------------------------------------------ #

    def _draw_bar(self):
        v    = self._value
        bar_h = int(v * METER_H)
        top_y = METER_H - bar_h

        self._canvas.configure(bg=T.bg_card)
        self._canvas.itemconfig(self._track_id, fill=T.meter_track)

        colour = (T.meter_low if v < 0.60
                  else T.meter_mid if v < 0.85
                  else T.meter_high)

        self._canvas.coords(self._bar_id, 4, top_y, METER_W - 4, METER_H)
        self._canvas.itemconfig(self._bar_id, fill=colour)

        # Simple peak hold (decays every ~15 frames)
        if v >= self._peak_value:
            self._peak_value = v
            self._peak_hold  = 15
        else:
            if self._peak_hold > 0:
                self._peak_hold -= 1
            else:
                self._peak_value = max(0.0, self._peak_value - 0.008)

        pk_y = int(METER_H * (1 - self._peak_value))
        self._canvas.coords(self._peak_id, 4, pk_y - 2, METER_W - 4, pk_y)
        self._canvas.itemconfig(self._peak_id,
                                fill=T.err if self._peak_value > 0.85 else T.fg_muted)

    # ------------------------------------------------------------------ #

    def _changed(self, *_):
        if self._on_change:
            self._on_change(self)
