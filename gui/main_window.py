"""
gui/main_window.py — BARJ Volume Controller main window
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import logging
from typing import List, Optional

from config_manager import ConfigManager
from serial_reader import SerialReader
from app_detector import AppDetector
from audio import get_audio_controller
from gui.slider_panel import SliderPanel
from gui.settings_dialog import SettingsDialog
from gui.dependency_check import DependencyStatusPanel, run_checks
from tray_icon import TrayIcon

logger = logging.getLogger(__name__)

APP_TITLE = "BARJ Volume Controller"
APP_SHORT = "BARJ VC"

BG_ROOT   = "#181825"
BG_HEADER = "#1e1e2e"
BG_STATUS = "#11111b"
FG        = "#cdd6f4"
FG_MUTED  = "#6c7086"
ACCENT    = "#cba6f7"
BTN_BG    = "#45475a"
BTN_FG    = "#cdd6f4"
OK_GREEN  = "#a6e3a1"
WARN      = "#f9e2af"


class MainWindow(tk.Tk):

    APP_POLL_INTERVAL   = 5
    CONN_CHECK_INTERVAL = 2000

    def __init__(self, debug: bool = False):
        super().__init__()
        self.debug = debug
        self.title(APP_TITLE)
        self.configure(bg=BG_ROOT)
        self.resizable(True, False)

        # ---- Dependency check ----
        checker = run_checks(self)
        if checker is None:
            return   # blocking dialog closed the window

        # ---- Core objects ----
        self.config_mgr = ConfigManager()

        try:
            self.audio = get_audio_controller()
        except Exception as e:
            messagebox.showerror("Audio Error",
                f"Could not initialise audio controller:\n{e}\n\nVolume control disabled.")
            self.audio = None

        self.detector = AppDetector(
            audio_controller=self.audio,
            callback=self._on_apps_updated,
            interval=self.APP_POLL_INTERVAL,
        ) if self.audio else None

        self.serial_reader: Optional[SerialReader] = None
        self._slider_panels: List[SliderPanel] = []

        # ---- Build UI ----
        self._build_header()

        # Dependency status panel (optional failures only — non-blocking)
        if checker.optional_failures or any(
            not c.required for c in checker.sys_failures
        ):
            DependencyStatusPanel(self, checker).pack(fill="x")

        self._build_body()
        self._build_status_bar()
        self._apply_ttk_theme()

        # ---- Start services ----
        self._rebuild_slider_panels()
        self._load_profile(self.config_mgr.current_profile)
        self._start_serial()
        if self.detector:
            self.detector.start()
        self._schedule_conn_check()

        # ---- Tray ----
        self._tray = TrayIcon(on_show_hide=self._toggle_window, on_quit=self._quit_app)
        self._tray_available = self._tray.start()
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

    # ================================================================== #
    # UI                                                                   #
    # ================================================================== #

    def _build_header(self):
        bar = tk.Frame(self, bg=BG_HEADER, pady=10)
        bar.pack(fill="x")

        tk.Label(bar, text=f"🎚  {APP_TITLE}",
                 font=("Segoe UI", 13, "bold"), bg=BG_HEADER, fg=ACCENT
                 ).pack(side="left", padx=14)

        tk.Button(bar, text="✕  Quit", command=self._quit_app,
                  bg=BTN_BG, fg=BTN_FG, relief="flat",
                  font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2"
                  ).pack(side="right", padx=4)

        tk.Button(bar, text="⚙  Settings", command=self._open_settings,
                  bg=BTN_BG, fg=BTN_FG, relief="flat",
                  font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2"
                  ).pack(side="right", padx=4)

        pf = tk.Frame(bar, bg=BG_HEADER)
        pf.pack(side="right", padx=10)
        tk.Label(pf, text="Profile:", bg=BG_HEADER, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(side="left")

        self._profile_var   = tk.StringVar()
        self._profile_combo = ttk.Combobox(pf, textvariable=self._profile_var,
                                           width=13, state="readonly",
                                           font=("Segoe UI", 9))
        self._profile_combo.pack(side="left", padx=(4, 2))
        self._profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)

        for text, cmd in [(" + ", self._add_profile), (" − ", self._delete_profile)]:
            tk.Button(pf, text=text, command=cmd, bg=BTN_BG, fg=BTN_FG,
                      relief="flat", font=("Segoe UI", 10, "bold"), cursor="hand2"
                      ).pack(side="left", padx=1)

        self._refresh_profile_list()

    def _build_body(self):
        self._body = tk.Frame(self, bg=BG_ROOT, padx=14, pady=14)
        self._body.pack(fill="both", expand=True)

    def _build_status_bar(self):
        bar = tk.Frame(self, bg=BG_STATUS, pady=5)
        bar.pack(fill="x", side="bottom")

        self._status_label = tk.Label(bar, text="● Connecting…",
                                       bg=BG_STATUS, fg=WARN,
                                       font=("Segoe UI", 8))
        self._status_label.pack(side="left", padx=12)

        # Config path hint
        cfg = str(self.config_mgr.config_path) if hasattr(self, "config_mgr") else ""
        tk.Label(bar, text=f"Config: {cfg}",
                 bg=BG_STATUS, fg=FG_MUTED, font=("Segoe UI", 7)
                 ).pack(side="right", padx=12)

        if self.debug:
            tk.Label(bar, text="⚠ DEBUG MODE",
                     bg=BG_STATUS, fg="#f38ba8",
                     font=("Segoe UI", 8, "bold")).pack(side="right", padx=12)

    def _apply_ttk_theme(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TCombobox",
                         fieldbackground="#313244", background=BTN_BG,
                         foreground=FG, selectforeground=FG,
                         selectbackground="#45475a")
        style.map("TCombobox", fieldbackground=[("readonly", "#313244")])

    # ================================================================== #
    # Slider panels                                                        #
    # ================================================================== #

    def _rebuild_slider_panels(self):
        for w in self._body.winfo_children():
            w.destroy()
        self._slider_panels.clear()
        count = self.config_mgr.get("sliders", "count", default=5)
        for i in range(count):
            panel = SliderPanel(self._body, index=i,
                                on_change=self._on_slider_assignment_changed)
            panel.grid(row=0, column=i, padx=6, pady=4, sticky="n")
            self._slider_panels.append(panel)
        if self.detector:
            self._on_apps_updated(self.detector.get_dropdown_values())

    # ================================================================== #
    # Profiles                                                             #
    # ================================================================== #

    def _refresh_profile_list(self):
        self._profile_combo["values"] = self.config_mgr.get_profile_names()
        self._profile_var.set(self.config_mgr.current_profile)

    def _load_profile(self, name: str):
        assignments = self.config_mgr.get_profile_assignments(name)
        for i, panel in enumerate(self._slider_panels):
            panel.set_target(assignments[i].get("target", "") if i < len(assignments) else "")

    def _save_current_assignments(self):
        self.config_mgr.set_profile_assignments([
            {"target": p.get_target(), "label": f"Slider {p.index + 1}"}
            for p in self._slider_panels
        ])

    def _on_profile_selected(self, _=None):
        name = self._profile_var.get()
        self.config_mgr.current_profile = name
        self._load_profile(name)

    def _add_profile(self):
        name = simpledialog.askstring("New Profile", "Profile name:", parent=self)
        if name and name.strip():
            self.config_mgr.add_profile(name.strip())
            self.config_mgr.current_profile = name.strip()
            self._refresh_profile_list()
            self._load_profile(name.strip())

    def _delete_profile(self):
        name = self._profile_var.get()
        if not messagebox.askyesno("Delete Profile", f"Delete '{name}'?", parent=self):
            return
        if not self.config_mgr.delete_profile(name):
            messagebox.showwarning("Cannot Delete",
                                   "Can't delete the last profile.", parent=self)
            return
        self._refresh_profile_list()
        self._load_profile(self.config_mgr.current_profile)

    # ================================================================== #
    # App detection                                                        #
    # ================================================================== #

    def _on_apps_updated(self, app_list: List[str]):
        self.after(0, lambda a=app_list:
                   [p.set_dropdown_values(a) for p in self._slider_panels])

    # ================================================================== #
    # Serial / audio                                                       #
    # ================================================================== #

    def _start_serial(self):
        port   = self.config_mgr.get("serial", "port",       default="COM3")
        baud   = self.config_mgr.get("serial", "baud_rate",  default=9600)
        count  = self.config_mgr.get("sliders", "count",     default=5)
        smooth = self.config_mgr.get("sliders", "smoothing", default=0.15)
        if self.serial_reader:
            self.serial_reader.stop()
        self.serial_reader = SerialReader(
            port=port, baud_rate=baud, num_sliders=count,
            smoothing=smooth, callback=self._on_serial_values, debug=self.debug)
        self.serial_reader.start()

    def _on_serial_values(self, values: List[float]):
        self.after(0, lambda v=values: self._apply_values(v))

    def _apply_values(self, values: List[float]):
        assignments = self.config_mgr.get_profile_assignments()
        for i, panel in enumerate(self._slider_panels):
            if i >= len(values):
                break
            panel.set_value(values[i])
            if self.audio and i < len(assignments):
                target = assignments[i].get("target", "")
                try:
                    self.audio.apply_slider(target, values[i])
                except Exception as e:
                    logger.debug(f"apply_slider: {e}")

    def _on_slider_assignment_changed(self, _):
        self._save_current_assignments()

    # ================================================================== #
    # Settings                                                             #
    # ================================================================== #

    def _open_settings(self):
        SettingsDialog(parent=self, config_mgr=self.config_mgr,
                       list_ports=SerialReader.list_ports,
                       on_save=self._on_settings_saved)

    def _on_settings_saved(self):
        self._rebuild_slider_panels()
        self._load_profile(self.config_mgr.current_profile)
        self._start_serial()

    # ================================================================== #
    # Connection status                                                    #
    # ================================================================== #

    def _schedule_conn_check(self):
        self._check_connection()
        self.after(self.CONN_CHECK_INTERVAL, self._schedule_conn_check)

    def _check_connection(self):
        connected = self.serial_reader is not None and self.serial_reader.connected
        port = self.config_mgr.get("serial", "port", default="?")
        if connected:
            self._status_label.config(text=f"● Connected  ({port})", fg=OK_GREEN)
        else:
            self._status_label.config(text=f"● Connecting… ({port})", fg=WARN)

    # ================================================================== #
    # Tray / lifecycle                                                     #
    # ================================================================== #

    def _toggle_window(self):
        self.after(0, self._do_toggle)

    def _do_toggle(self):
        if self.winfo_viewable():
            self.withdraw()
        else:
            self.deiconify()
            self.lift()
            self.focus_force()

    def _on_window_close(self):
        if self._tray_available:
            self.withdraw()
            self._tray.notify(APP_TITLE, "Running in the system tray.")
        else:
            if messagebox.askyesno("Quit", f"Quit {APP_TITLE}?", parent=self):
                self._quit_app()

    def _quit_app(self):
        self.after(0, self._do_quit)

    def _do_quit(self):
        if self.serial_reader:
            self.serial_reader.stop()
        if self.detector:
            self.detector.stop()
        self._tray.stop()
        self.destroy()
