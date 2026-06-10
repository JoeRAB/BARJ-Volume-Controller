"""
gui/main_window.py  —  BARJ Volume Controller main window
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import logging
from typing import List, Optional

from config_manager import ConfigManager
from serial_reader import SerialReader, SerialError
from app_detector import AppDetector
from audio import get_audio_controller
from gui.theme import T, F, Tooltip
from gui.slider_panel import SliderPanel
from gui.settings_dialog import SettingsDialog
from gui.connecting_dialog import ConnectingDialog
from gui.error_dialog import ErrorDialog
from tray_icon import TrayIcon

logger = logging.getLogger(__name__)
APP_TITLE = "BARJ Volume Controller"
RECONNECT_DIALOG_DELAY = 3000


class MainWindow(tk.Tk):

    APP_POLL_INTERVAL   = 5
    CONN_CHECK_INTERVAL = 1000

    def __init__(self, debug: bool = False):
        super().__init__()
        self.debug = debug
        self.title(APP_TITLE)
        self.resizable(True, False)

        # ---- Load theme preference before anything draws ----
        self.config_mgr = ConfigManager()
        theme_pref = self.config_mgr.get("ui", "theme", default="auto")
        T.apply(theme_pref)
        self.configure(bg=T.bg_root)

        # ---- Dependency check (silent unless a REQUIRED dep is missing) ----
        from gui.dependency_check import DependencyChecker, DependencyDialog
        checker = DependencyChecker()
        if checker.missing_required:
            # App genuinely can't run — show the dialog so the user can install
            dlg = DependencyDialog(self, checker)
            self.wait_window(dlg)
            if not (dlg.proceed or checker.all_ok):
                self.destroy()
                return

        # ---- Audio ----
        try:
            self.audio = get_audio_controller()
        except Exception as e:
            messagebox.showerror("Audio Error",
                f"Could not initialise audio:\n{e}\n\nVolume control disabled.")
            self.audio = None

        self.detector = AppDetector(
            audio_controller=self.audio,
            callback=self._on_apps_updated,
            interval=self.APP_POLL_INTERVAL,
        ) if self.audio else None

        self.serial_reader: Optional[SerialReader] = None
        self._slider_panels: List[SliderPanel] = []
        self._error_dialog_active = False
        self._connecting_dialog: Optional[ConnectingDialog] = None
        self._was_connected   = False
        self._reconnect_job: Optional[str] = None

        # ---- Build UI ----
        self._setup_ttk_style()
        self._build_ui()

        # ---- Services ----
        self._start_serial()
        if self.detector:
            self.detector.start()
        self._schedule_conn_check()

        # ---- Tray ----
        self._tray = TrayIcon(on_show_hide=self._toggle_window,
                              on_quit=self._quit_app,
                              on_show=self._show_window,
                              on_hide=self._hide_window)
        self._tray_available = self._tray.start()
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Drive the tray's GTK loop from tkinter so AppIndicator menu
        # clicks register on Linux. No-op on other backends/platforms.
        self._pump_tray()

    def _pump_tray(self):
        try:
            self._tray.pump()
        except Exception:
            pass
        self.after(100, self._pump_tray)

    # ================================================================== #
    # Theme                                                                #
    # ================================================================== #

    def _setup_ttk_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TCombobox",
                         fieldbackground=T.bg_input,
                         background=T.btn_bg,
                         foreground=T.fg,
                         selectforeground=T.fg,
                         selectbackground=T.bg_elevated,
                         arrowcolor=T.fg_muted)
        style.map("TCombobox",
                  fieldbackground=[("readonly", T.bg_input)],
                  foreground=[("readonly", T.fg)])

    def _toggle_theme(self):
        T.toggle()
        new = T.name
        self.config_mgr.set(new, "ui", "theme")
        self._rebuild_ui()

    def _rebuild_ui(self):
        """Destroy and re-create every widget to apply new theme."""
        for w in self.winfo_children():
            w.destroy()
        self._slider_panels.clear()
        self.configure(bg=T.bg_root)
        self._setup_ttk_style()
        self._build_ui()
        self._load_profile(self.config_mgr.current_profile)
        if self.detector:
            self._on_apps_updated(self.detector.get_dropdown_values())

    # ================================================================== #
    # Build UI                                                             #
    # ================================================================== #

    def _build_ui(self):
        self._build_header()
        self._build_body()
        self._build_status_bar()
        self._rebuild_slider_panels()
        self._load_profile(self.config_mgr.current_profile)

    def _build_header(self):
        bar = tk.Frame(self, bg=T.header_bg, pady=0)
        bar.pack(fill="x")

        # Bottom border line
        tk.Frame(bar, bg=T.separator, height=1).place(relx=0, rely=1,
                                                       relwidth=1, anchor="sw")

        inner = tk.Frame(bar, bg=T.header_bg, padx=14, pady=10)
        inner.pack(fill="x")

        # Left: app title
        tk.Label(inner, text="🎚  BARJ Volume Controller",
                 font=F.title, bg=T.header_bg, fg=T.accent
                 ).pack(side="left")

        # Right side buttons (right-to-left order)
        def hdr_btn(parent, text, cmd, primary=False, tip=None):
            bg = T.btn_primary if primary else T.btn_bg
            fg = T.btn_primary_fg if primary else T.btn_fg
            b = tk.Button(parent, text=text, command=cmd,
                          bg=bg, fg=fg, relief="flat",
                          font=F.small, padx=10, pady=5,
                          cursor="hand2",
                          activebackground=T.bg_elevated,
                          activeforeground=T.fg)
            b.pack(side="right", padx=3)
            if tip:
                Tooltip(b, tip)
            return b

        hdr_btn(inner, "✕  Quit", self._quit_app,
                tip="Quit the application")
        hdr_btn(inner, "⚙  Settings", self._open_settings,
                tip="Serial port, slider count, smoothing")

        # Theme toggle
        self._theme_btn = tk.Button(
            inner, text=T.theme_icon, command=self._toggle_theme,
            bg=T.btn_bg, fg=T.fg, relief="flat",
            font=(F.ui, 13), padx=8, pady=4,
            cursor="hand2",
            activebackground=T.bg_elevated, activeforeground=T.fg)
        self._theme_btn.pack(side="right", padx=3)
        Tooltip(self._theme_btn, "Switch between light and dark mode")

        # Profile selector
        sep = tk.Frame(inner, bg=T.separator, width=1)
        sep.pack(side="right", padx=8, fill="y", pady=4)

        pf = tk.Frame(inner, bg=T.header_bg)
        pf.pack(side="right")

        tk.Label(pf, text="Profile", font=F.tiny, bg=T.header_bg,
                 fg=T.fg_muted).pack(side="left", padx=(0, 4))

        self._profile_var   = tk.StringVar()
        self._profile_combo = ttk.Combobox(pf, textvariable=self._profile_var,
                                           width=13, state="readonly",
                                           font=F.small)
        self._profile_combo.pack(side="left")
        self._profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)
        Tooltip(self._profile_combo, "Switch between saved slider profiles")

        for txt, cmd, tip in [
            ("＋", self._add_profile,    "Create a new empty profile"),
            ("✎", self._rename_profile, "Rename the current profile"),
            ("⧉", self._save_as_profile,"Save current profile under a new name"),
            ("－", self._delete_profile, "Delete the current profile"),
        ]:
            b = tk.Button(pf, text=txt, command=cmd,
                          bg=T.btn_bg, fg=T.fg_muted, relief="flat",
                          font=F.small_b, padx=6, pady=4,
                          cursor="hand2",
                          activebackground=T.bg_elevated)
            b.pack(side="left", padx=1)
            Tooltip(b, tip)

        self._refresh_profile_list()

    def _build_body(self):
        self._body = tk.Frame(self, bg=T.bg_root, padx=16, pady=16)
        self._body.pack(fill="both", expand=True)

    def _build_status_bar(self):
        bar = tk.Frame(self, bg=T.status_bg, pady=5)
        bar.pack(fill="x", side="bottom")
        tk.Frame(bar, bg=T.separator, height=1).place(relx=0, rely=0,
                                                       relwidth=1, anchor="nw")
        self._status_dot = tk.Label(bar, text="●", bg=T.status_bg,
                                     fg=T.warn, font=F.tiny)
        self._status_dot.pack(side="left", padx=(12, 2))
        self._status_label = tk.Label(bar, text="Connecting…",
                                       bg=T.status_bg, fg=T.warn, font=F.tiny)
        self._status_label.pack(side="left")

        cfg = str(self.config_mgr.config_path)
        tk.Label(bar, text=f"Config: {cfg}",
                 bg=T.status_bg, fg=T.fg_subtle, font=F.tiny
                 ).pack(side="right", padx=12)

        if self.debug:
            tk.Label(bar, text="DEBUG", bg=T.err, fg="white",
                     font=F.badge, padx=4).pack(side="right", padx=8)

    # ================================================================== #
    # Sliders                                                              #
    # ================================================================== #

    def _rebuild_slider_panels(self):
        for w in self._body.winfo_children():
            w.destroy()
        self._slider_panels.clear()
        count = self.config_mgr.get("sliders", "count", default=5)
        for i in range(count):
            p = SliderPanel(self._body, index=i,
                            on_change=self._on_slider_changed)
            p.grid(row=0, column=i, padx=6, pady=4, sticky="n")
            self._slider_panels.append(p)
        if self.detector:
            self._on_apps_updated(self.detector.get_dropdown_values())

    # ================================================================== #
    # Profiles                                                             #
    # ================================================================== #

    def _refresh_profile_list(self):
        self._profile_combo["values"] = self.config_mgr.get_profile_names()
        self._profile_var.set(self.config_mgr.current_profile)

    def _load_profile(self, name):
        a = self.config_mgr.get_profile_assignments(name)
        for i, p in enumerate(self._slider_panels):
            p.set_target(a[i].get("target","") if i < len(a) else "")

    def _save_assignments(self):
        self.config_mgr.set_profile_assignments([
            {"target": p.get_target(), "label": f"Slider {p.index+1}"}
            for p in self._slider_panels])

    def _on_profile_selected(self, _=None):
        name = self._profile_var.get()
        self.config_mgr.current_profile = name
        self._load_profile(name)

    def _add_profile(self):
        n = simpledialog.askstring("New Profile", "Profile name:", parent=self)
        if n and n.strip():
            self.config_mgr.add_profile(n.strip())
            self.config_mgr.current_profile = n.strip()
            self._refresh_profile_list()
            self._load_profile(n.strip())

    def _delete_profile(self):
        n = self._profile_var.get()
        if not messagebox.askyesno("Delete", f"Delete profile '{n}'?", parent=self):
            return
        if not self.config_mgr.delete_profile(n):
            messagebox.showwarning("Cannot Delete",
                                   "Can't delete the last profile.", parent=self)
            return
        self._refresh_profile_list()
        self._load_profile(self.config_mgr.current_profile)

    def _rename_profile(self):
        old = self._profile_var.get()
        new = simpledialog.askstring(
            "Rename Profile", "New name:",
            initialvalue=old, parent=self)
        if not new or not new.strip():
            return
        new = new.strip()
        if new == old:
            return
        if not self.config_mgr.rename_profile(old, new):
            messagebox.showwarning(
                "Cannot Rename",
                f"A profile named '{new}' already exists.", parent=self)
            return
        self._refresh_profile_list()
        self._load_profile(self.config_mgr.current_profile)

    def _save_as_profile(self):
        """Duplicate the current profile's assignments under a new name."""
        # Capture the live slider assignments first
        self._save_assignments()
        src = self._profile_var.get()
        new = simpledialog.askstring(
            "Save As", "Save current profile as:",
            initialvalue=f"{src} copy", parent=self)
        if not new or not new.strip():
            return
        new = new.strip()
        if new in self.config_mgr.get_profile_names():
            messagebox.showwarning(
                "Name In Use",
                f"A profile named '{new}' already exists.", parent=self)
            return
        # Create the new profile, copy assignments into it, switch to it
        assignments = self.config_mgr.get_profile_assignments(src)
        self.config_mgr.add_profile(new)
        self.config_mgr.set_profile_assignments(assignments, new)
        self.config_mgr.current_profile = new
        self._refresh_profile_list()
        self._load_profile(new)

    # ================================================================== #
    # App detection                                                        #
    # ================================================================== #

    def _on_apps_updated(self, app_list):
        self.after(0, lambda a=app_list:
                   [p.set_dropdown_values(a) for p in self._slider_panels])

    # ================================================================== #
    # Serial / audio                                                       #
    # ================================================================== #

    def _start_serial(self):
        port   = self.config_mgr.get("serial","port",      default="COM3")
        baud   = self.config_mgr.get("serial","baud_rate", default=9600)
        count  = self.config_mgr.get("sliders","count",    default=5)
        smooth = self.config_mgr.get("sliders","smoothing",default=0.15)
        if self.serial_reader:
            self.serial_reader.stop()
        self.serial_reader = SerialReader(
            port=port, baud_rate=baud, num_sliders=count,
            smoothing=smooth, callback=self._on_serial_values,
            error_callback=self._on_serial_error, debug=self.debug)
        self.serial_reader.start()

    def _on_serial_values(self, values):
        self.after(0, lambda v=values: self._apply_values(v))

    def _apply_values(self, values):
        assignments = self.config_mgr.get_profile_assignments()
        for i, panel in enumerate(self._slider_panels):
            if i >= len(values): break
            try:   panel.set_value(values[i])
            except Exception as e: logger.debug(f"set_value {i}: {e}")
            if self.audio and i < len(assignments):
                try:   self.audio.apply_slider(assignments[i].get("target",""), values[i])
                except Exception as e: logger.debug(f"apply_slider: {e}")

    def _on_slider_changed(self, _):
        self._save_assignments()

    # ================================================================== #
    # Error dialog (single instance)                                      #
    # ================================================================== #

    def _on_serial_error(self, err: SerialError):
        self.after(0, lambda e=err: self._show_error(e))

    def _show_error(self, err: SerialError):
        if self._error_dialog_active:
            return
        self._error_dialog_active = True
        ErrorDialog(self, err.kind, err.message, err.raw_line,
                    on_dismiss=lambda: setattr(self, "_error_dialog_active", False))

    # ================================================================== #
    # Connecting dialog                                                    #
    # ================================================================== #

    def _show_connecting_dialog(self):
        if self._connecting_dialog and self._connecting_dialog.winfo_exists():
            self._connecting_dialog.show_reconnecting()
            return
        self._connecting_dialog = ConnectingDialog(
            parent=self,
            get_port=lambda: self.config_mgr.get("serial","port",default="?"),
            list_ports=SerialReader.list_ports,
            on_port_change=self._on_port_changed)

    def _on_port_changed(self, new_port):
        self.config_mgr.set(new_port, "serial", "port")
        self._start_serial()

    # ================================================================== #
    # Connection status                                                    #
    # ================================================================== #

    def _schedule_conn_check(self):
        self._check_connection()
        self.after(self.CONN_CHECK_INTERVAL, self._schedule_conn_check)

    def _check_connection(self):
        connected = self.serial_reader is not None and self.serial_reader.connected
        port = self.config_mgr.get("serial","port",default="?")
        if connected:
            self._status_dot.config(fg=T.ok)
            self._status_label.config(text=f"Connected  ({port})", fg=T.ok)
            if self._connecting_dialog and self._connecting_dialog.winfo_exists():
                self._connecting_dialog.notify_connected()
            self._was_connected = True
        else:
            self._status_dot.config(fg=T.warn)
            self._status_label.config(text=f"Connecting…  ({port})", fg=T.warn)
            if self._was_connected:
                self._was_connected = False
                if self._reconnect_job:
                    self.after_cancel(self._reconnect_job)
                self._reconnect_job = self.after(
                    RECONNECT_DIALOG_DELAY, self._show_connecting_dialog)

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
        if self._connecting_dialog and self._connecting_dialog.winfo_exists():
            self._connecting_dialog.update_port_display(
                self.config_mgr.get("serial","port",default=""))

    # ================================================================== #
    # Tray / lifecycle                                                     #
    # ================================================================== #

    def _toggle_window(self):
        self.after(0, lambda: self.withdraw() if self.winfo_viewable()
                   else (self.deiconify(), self.lift(), self.focus_force()))

    def _show_window(self):
        self.after(0, lambda: (self.deiconify(), self.lift(), self.focus_force()))

    def _hide_window(self):
        self.after(0, self.withdraw)

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
        if self.serial_reader: self.serial_reader.stop()
        if self.detector:      self.detector.stop()
        self._tray.stop()
        self.destroy()
