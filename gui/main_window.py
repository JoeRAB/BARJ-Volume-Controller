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
from gui.dialogs import ConnectingDialog, ErrorDialog, CloseDialog
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

        # Catch any exception raised inside a tkinter callback (e.g. while
        # applying a slider value) so a transient glitch from a bad solder
        # joint logs an error instead of tearing down the whole app.
        self.report_callback_exception = self._on_tk_exception

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
        # Perf: cached (assignments, exclude_set); None = rebuild on next use
        self._assignments_cache = None
        self._last_ui_values: list = []
        self._save_job = None   # pending debounced config save
        self._pending_values = None    # latest serial values awaiting GUI apply
        self._apply_pending  = False   # True while a drain is scheduled
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
                              on_hide=self._hide_window,
                              get_profiles=self._get_profiles_for_tray,
                              on_profile_select=self._on_tray_profile_select)
        self._tray_available = self._tray.start()
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

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
            ("💾", self._save_profile,   "Save the current profile"),
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
        # Widgets are recreated (e.g. theme toggle) — force the next
        # connection check to repaint them.
        self._last_conn_state = None
        bar = tk.Frame(self, bg=T.status_bg, pady=5)
        bar.pack(fill="x", side="bottom")
        tk.Frame(bar, bg=T.separator, height=1).place(relx=0, rely=0,
                                                       relwidth=1, anchor="nw")
        self._status_dot = tk.Label(bar, text="●", bg=T.status_bg,
                                     fg=T.err, font=F.tiny)
        self._status_dot.pack(side="left", padx=(12, 2))
        self._status_label = tk.Label(bar, text="Connecting…",
                                       bg=T.status_bg, fg=T.err, font=F.tiny)
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
        self._invalidate_assignments()

    def _save_assignments(self):
        self.config_mgr.set_profile_assignments([
            {"target": p.get_target(), "label": f"Slider {p.index+1}"}
            for p in self._slider_panels])

    def _save_profile(self):
        """Explicitly save the current slider setup to the active profile."""
        self._save_assignments()
        name = self.config_mgr.current_profile
        # Brief confirmation in the status bar
        self._status_label.config(text=f"Profile '{name}' saved", fg=T.ok)
        self.after(2000, self._check_connection)

    def _on_profile_selected(self, _=None):
        name = self._profile_var.get()
        self.config_mgr.current_profile = name
        self._load_profile(name)
        self._invalidate_assignments()
        self._update_panel_active_states()

    # ---- Tray profile switching ----

    def _get_profiles_for_tray(self):
        """Called from the tray thread — reads only, safe."""
        return (self.config_mgr.get_profile_names(),
                self.config_mgr.current_profile)

    def _on_tray_profile_select(self, name: str):
        """Called from the tray thread — marshal to the GUI thread."""
        self.after(0, lambda: self._select_profile(name))

    def _select_profile(self, name: str):
        if name not in self.config_mgr.get_profile_names():
            return
        self.config_mgr.current_profile = name
        self._profile_var.set(name)
        self._load_profile(name)
        self._invalidate_assignments()
        self._update_panel_active_states()

    def show_from_external(self):
        """Called when a second launch is detected — raise the window."""
        self._do_show()

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
        def _apply(a=app_list):
            for p in self._slider_panels:
                p.set_dropdown_values(a)
            self._update_panel_active_states()
        self.after(0, _apply)

    def _update_panel_active_states(self):
        """Refresh each slider's ● active / ○ not running / – unassigned
        indicator against the currently-running audio apps."""
        running = [a.lower() for a in
                   (self.detector.get_current_apps() if self.detector else [])]
        for p in self._slider_panels:
            target = p.get_target().strip().lower()
            if not target:
                p.set_active("unassigned")
            elif target in ("master", "all_others"):
                p.set_active("active")
            elif any(target in app for app in running):
                # substring match — mirrors how the audio layer matches apps
                p.set_active("active")
            else:
                p.set_active("inactive")

    # ================================================================== #
    # Serial / audio                                                       #
    # ================================================================== #

    def _start_serial(self):
        port   = self.config_mgr.get("serial","port",      default="COM3")
        baud   = self.config_mgr.get("serial","baud_rate", default=9600)
        count  = self.config_mgr.get("sliders","count",    default=5)
        smooth = self.config_mgr.get("sliders","smoothing",default=0.15)
        invert = self.config_mgr.get("sliders","invert",   default=False)
        if self.serial_reader:
            self.serial_reader.stop()
        self.serial_reader = SerialReader(
            port=port, baud_rate=baud, num_sliders=count, invert=bool(invert),
            smoothing=smooth, callback=self._on_serial_values,
            error_callback=self._on_serial_error, debug=self.debug)
        self.serial_reader.start()

    def _on_serial_values(self, values):
        # Called from the serial thread ~100×/sec. Coalesce: keep only the
        # latest values and schedule at most ONE pending GUI apply, instead
        # of queueing a tkinter event per serial line. Latest-wins also
        # prevents a backlog of stale values being replayed if the GUI
        # stalls briefly (e.g. during a theme rebuild).
        self._pending_values = values
        if not self._apply_pending:
            self._apply_pending = True
            try:
                self.after(33, self._drain_serial_values)   # ~30 fps
            except Exception:
                self._apply_pending = False

    def _drain_serial_values(self):
        self._apply_pending = False
        v = self._pending_values
        if v is not None:
            self._apply_values(v)

    def _get_cached_assignments(self):
        """Profile assignments, cached — rebuilt only when the profile or
        settings change, not 100×/sec on every serial tick."""
        if self._assignments_cache is None:
            assignments = self.config_mgr.get_profile_assignments()
            # Exclude set for 'all_others': every explicit app target
            # (not the special keywords) assigned to any slider.
            exclude = {a.get("target", "").strip()
                       for a in assignments
                       if a.get("target", "").strip().lower()
                       not in ("", "master", "all_others")}
            self._assignments_cache = (assignments, exclude)
        return self._assignments_cache

    def _invalidate_assignments(self):
        self._assignments_cache = None
        # Force re-send of all volumes after a mapping change
        self._last_ui_values = []

    def _apply_values(self, values):
        assignments, exclude = self._get_cached_assignments()
        # Pad UI-change tracker to length
        while len(self._last_ui_values) < len(values):
            self._last_ui_values.append(-1.0)

        for i, panel in enumerate(self._slider_panels):
            if i >= len(values): break
            # Skip panels whose value hasn't visibly moved (saves canvas
            # redraws and audio calls at idle; audio layer also gates).
            if abs(values[i] - self._last_ui_values[i]) < 0.002:
                continue
            self._last_ui_values[i] = values[i]
            try:   panel.set_value(values[i])
            except Exception as e: logger.debug(f"set_value {i}: {e}")
            if self.audio and i < len(assignments):
                try:
                    self.audio.apply_slider(
                        assignments[i].get("target", ""), values[i],
                        exclude=exclude)
                except Exception as e: logger.debug(f"apply_slider: {e}")

    def _on_slider_changed(self, _):
        # Debounce: the dropdown fires on every keystroke; save once,
        # shortly after the user stops typing.
        self._invalidate_assignments()
        if self._save_job:
            try: self.after_cancel(self._save_job)
            except Exception: pass
        self._save_job = self.after(600, self._flush_assignments)

    def _flush_assignments(self):
        self._save_job = None
        self._save_assignments()
        self._invalidate_assignments()
        self._update_panel_active_states()

    # ================================================================== #
    # Error dialog (single instance)                                      #
    # ================================================================== #

    def _on_serial_error(self, err: SerialError):
        self.after(0, lambda e=err: self._show_error(e))

    def _show_error(self, err: SerialError):
        # "Cannot connect" is communicated by the red status bar, not a
        # popup — only show dialogs for parse/disconnect faults that point
        # to a wiring or hardware problem worth the user's attention.
        if err.kind == SerialError.CONNECT:
            return
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

        # Only touch the widgets when something actually changed —
        # avoids a redundant redraw every second at steady state.
        state = (connected, port)
        if state != getattr(self, "_last_conn_state", None):
            self._last_conn_state = state
            if connected:
                self._status_dot.config(fg=T.ok)
                self._status_label.config(text=f"Connected  ({port})", fg=T.ok)
            else:
                self._status_dot.config(fg=T.err)
                self._status_label.config(text=f"Not connected  ({port})", fg=T.err)

        if connected:
            if self._connecting_dialog and self._connecting_dialog.winfo_exists():
                self._connecting_dialog.notify_connected()
            self._was_connected = True
        else:
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
        self.after(0, lambda: self._do_hide() if self.winfo_viewable()
                   else self._do_show())

    def _show_window(self):
        self.after(0, self._do_show)

    def _hide_window(self):
        self.after(0, self._do_hide)

    def _do_show(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        if self.detector:
            self.detector.resume()   # immediate poll → fresh dropdowns

    def _do_hide(self):
        self.withdraw()
        if self.detector:
            self.detector.pause()    # nobody's looking — stop polling

    def _on_window_close(self):
        action = self.config_mgr.get("ui", "close_action", default="ask")

        # No tray → minimizing isn't possible; quit (confirm only if set to ask)
        if not self._tray_available:
            if action == "ask":
                if messagebox.askyesno("Quit", f"Quit {APP_TITLE}?", parent=self):
                    self._quit_app()
            else:
                self._quit_app()
            return

        if action == "tray":
            self._minimize_to_tray()
        elif action == "quit":
            self._quit_app()
        else:  # "ask"
            dlg = CloseDialog(self, tray_available=True)
            self.wait_window(dlg)
            if dlg.result is None:
                return  # cancelled — do nothing
            if dlg.remember:
                self.config_mgr.set(dlg.result, "ui", "close_action")
            if dlg.result == "tray":
                self._minimize_to_tray()
            else:
                self._quit_app()

    def _minimize_to_tray(self):
        self._do_hide()
        self._tray.notify(APP_TITLE, "Running in the system tray.")

    def _quit_app(self):
        self.after(0, self._do_quit)

    def _do_quit(self):
        # Flush any pending debounced assignment save first
        if self._save_job:
            try: self.after_cancel(self._save_job)
            except Exception: pass
            self._save_assignments()
        if self.serial_reader: self.serial_reader.stop()
        if self.detector:      self.detector.stop()
        self._tray.stop()
        self.destroy()

    def _on_tk_exception(self, exc_type, exc_value, exc_tb):
        """
        Last-resort handler for exceptions raised inside tkinter callbacks.
        Logs the error and keeps the app alive instead of crashing. This is
        what stops a transient bad-solder glitch from taking the app down.
        """
        import traceback
        logger.error("Unhandled GUI callback error (recovered):\n" +
                     "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
