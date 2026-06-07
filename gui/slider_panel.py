"""
gui/slider_panel.py
A single slider panel: label, app assignment dropdown, and a vertical VU meter.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

# Colour scheme
BG_PANEL    = "#1e1e2e"
BG_METER    = "#0d0d1a"
FG_TEXT     = "#cdd6f4"
FG_MUTED    = "#6c7086"
ACCENT_LOW  = "#a6e3a1"   # green  (<60%)
ACCENT_MID  = "#f9e2af"   # yellow (60–85%)
ACCENT_HIGH = "#f38ba8"   # red    (>85%)
BORDER      = "#313244"


class SliderPanel(tk.Frame):
    """
    Visual panel for one hardware slider.

    Public interface
    ----------------
    set_value(float)         — update the meter and percentage label (0.0–1.0)
    set_dropdown_values(list)— populate the app dropdown
    get_target() -> str      — current assignment text
    set_target(str)          — set the dropdown selection
    on_change(callback)      — called (with panel index) whenever the dropdown changes
    """

    METER_WIDTH  = 34
    METER_HEIGHT = 160

    def __init__(
        self,
        parent,
        index: int,
        on_change: Optional[Callable[["SliderPanel"], None]] = None,
        **kwargs,
    ):
        super().__init__(
            parent,
            bg=BG_PANEL,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=10,
            pady=10,
            **kwargs,
        )
        self.index = index
        self._on_change = on_change
        self._value = 0.0
        self._build()

    # ------------------------------------------------------------------ #
    # Build UI                                                             #
    # ------------------------------------------------------------------ #

    def _build(self):
        # --- Slider number header ---
        tk.Label(
            self,
            text=f"Slider {self.index + 1}",
            font=("Segoe UI", 9, "bold"),
            bg=BG_PANEL,
            fg=FG_MUTED,
        ).pack(pady=(0, 4))

        # --- App assignment dropdown ---
        self._target_var = tk.StringVar()
        self._target_var.trace_add("write", self._on_target_changed)

        self._dropdown = ttk.Combobox(
            self,
            textvariable=self._target_var,
            width=16,
            state="normal",
            font=("Segoe UI", 9),
        )
        self._dropdown.pack(pady=(0, 8))

        # --- VU meter canvas ---
        self._canvas = tk.Canvas(
            self,
            width=self.METER_WIDTH,
            height=self.METER_HEIGHT,
            bg=BG_METER,
            highlightthickness=0,
        )
        self._canvas.pack()

        # Background ticks (every 10%)
        for i in range(1, 10):
            y = int(self.METER_HEIGHT * (1 - i / 10))
            self._canvas.create_line(
                0, y, self.METER_WIDTH, y,
                fill="#2a2a3e", dash=(2, 3)
            )

        # The bar itself (starts at zero height)
        self._bar = self._canvas.create_rectangle(
            2, self.METER_HEIGHT, self.METER_WIDTH - 2, self.METER_HEIGHT,
            fill=ACCENT_LOW, outline="",
        )

        # --- Percentage label ---
        self._pct_label = tk.Label(
            self,
            text="0%",
            font=("Segoe UI", 9),
            bg=BG_PANEL,
            fg=FG_TEXT,
        )
        self._pct_label.pack(pady=(6, 0))

    # ------------------------------------------------------------------ #
    # Public methods                                                       #
    # ------------------------------------------------------------------ #

    def set_value(self, value: float):
        """Update the VU meter. value is 0.0–1.0."""
        self._value = max(0.0, min(1.0, value))
        pct = int(self._value * 100)
        self._pct_label.config(text=f"{pct}%")

        bar_h = int(self._value * (self.METER_HEIGHT - 4))
        top_y = self.METER_HEIGHT - bar_h
        self._canvas.coords(
            self._bar,
            2, top_y, self.METER_WIDTH - 2, self.METER_HEIGHT
        )

        if self._value < 0.60:
            colour = ACCENT_LOW
        elif self._value < 0.85:
            colour = ACCENT_MID
        else:
            colour = ACCENT_HIGH
        self._canvas.itemconfig(self._bar, fill=colour)

    def set_dropdown_values(self, values: List[str]):
        """Populate the dropdown without losing the current selection."""
        current = self._target_var.get()
        self._dropdown["values"] = values
        # Restore selection if it's still valid, otherwise keep as typed text
        if current in values:
            self._target_var.set(current)

    def get_target(self) -> str:
        return self._target_var.get().strip()

    def set_target(self, target: str):
        self._target_var.set(target or "")

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _on_target_changed(self, *_):
        if self._on_change:
            self._on_change(self)
