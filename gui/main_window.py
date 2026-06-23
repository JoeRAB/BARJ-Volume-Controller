"""
BARJ Volume Controller main window
"""

import tkinter as tk
from tkinter import ttk, simpledialog
import logging
from pathlib import Path
from typing import List, Optional

from config_manager import ConfigManager
from serial_reader import SerialReader, SerialError
from audio import get_audio_controller, AppDetector
from gui.theme import T, F, Tooltip, RoundedButton
from gui.widgets import (SliderPanel, ConnectingDialog, ErrorDialog, CloseDialog,
                         SettingsDialog, DependencyChecker, DependencyDialog,
                         SliderSettingsDialog, themed_message, themed_confirm)
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

        # Load theme preference before anything draws
        self.config_mgr = ConfigManager()
        theme_pref = self.config_mgr.get("ui", "theme", default="auto")
        T.apply(theme_pref)
        self.configure(bg=T.bg_root)

        # Dependency check (silent unless a REQUIRED dep is missing)
        checker = DependencyChecker()
        if checker.missing_required:
            # App genuinely can't run - show the dialog so the user can install
            dlg = DependencyDialog(self, checker)
            self.wait_window(dlg)
            if not (dlg.proceed or checker.all_ok):
                self.destroy()
                return

        # Audio
        try:
            self.audio = get_audio_controller()
        except Exception as e:
            themed_message(self, "Audio Error",
                f"Could not initialise audio:\n{e}\n\nVolume control disabled.",
                kind="error")
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
        self._loading_profile = False
        self._pending_values = None    # latest serial values awaiting GUI apply
        self._apply_pending  = False   # True while a drain is scheduled
        self._was_connected   = False
        self._reconnect_job: Optional[str] = None

        # Build UI
        self._setup_ttk_style()
        self._build_ui()

        # Enforce a sensible minimum so slider cards never clip (#12)
        self.update_idletasks()
        self.minsize(self.winfo_reqwidth(), self.winfo_reqheight())

        # Services
        self._start_serial()
        if self.detector:
            self.detector.start()
        self._schedule_conn_check()

        # Tray
        self._tray = TrayIcon(on_show_hide=self._toggle_window,
                              on_quit=self._quit_app,
                              on_show=self._show_window,
                              on_hide=self._hide_window,
                              get_profiles=self._get_profiles_for_tray,
                              on_profile_select=self._on_tray_profile_select)
        self._tray_available = self._tray.start()
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Ctrl+S saves the current profile
        self.bind_all("<Control-s>", lambda e: self._save_profile())

        # Launch minimized to tray if the user enabled it (and a tray exists)
        if (self.config_mgr.get("ui", "launch_minimized", default=False)
                and self._tray_available):
            self.after(200, self._do_hide)

    # Theme                                                                #

    def _setup_ttk_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Base combobox (header profile selector, settings dialogs)
        style.configure("TCombobox",
                         fieldbackground=T.bg_input,
                         background=T.bg_input,
                         foreground=T.fg,
                         bordercolor=T.border,
                         lightcolor=T.border,
                         darkcolor=T.border,
                         arrowcolor=T.fg_muted,
                         selectforeground=T.fg,
                         selectbackground=T.bg_input,
                         padding=4)
        style.map("TCombobox",
                  fieldbackground=[("readonly", T.bg_input)],
                  foreground=[("readonly", T.fg)],
                  bordercolor=[("focus", T.accent), ("active", T.accent_soft)],
                  arrowcolor=[("active", T.accent_soft)])

        # Slider-card combobox - slightly larger, accent on focus
        style.configure("Slider.TCombobox",
                         fieldbackground=T.bg_input,
                         background=T.bg_input,
                         foreground=T.fg,
                         bordercolor=T.border,
                         lightcolor=T.border,
                         darkcolor=T.border,
                         arrowcolor=T.fg_muted,
                         selectforeground=T.fg,
                         selectbackground=T.bg_input,
                         padding=5)
        style.map("Slider.TCombobox",
                  fieldbackground=[("readonly", T.bg_input)],
                  foreground=[("readonly", T.fg)],
                  bordercolor=[("focus", T.accent), ("active", T.accent_soft)],
                  arrowcolor=[("active", T.accent_soft)])

        # The dropdown list popup (shared by all comboboxes)
        self.option_add("*TCombobox*Listbox.background", T.bg_elevated)
        self.option_add("*TCombobox*Listbox.foreground", T.fg)
        self.option_add("*TCombobox*Listbox.selectBackground", T.accent)
        self.option_add("*TCombobox*Listbox.selectForeground", T.accent_fg)
        self.option_add("*TCombobox*Listbox.font", F.small)

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

    # Build UI                                                             #

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

        inner = tk.Frame(bar, bg=T.header_bg, padx=18, pady=14)
        inner.pack(fill="x")

        # Left: app title
        tk.Label(inner, text="🎚  BARJ Volume Controller",
                 font=F.title, bg=T.header_bg, fg=T.accent
                 ).pack(side="left")

        self._round_btns = []   # tracked so theme switches can refresh them

        # Settings - square cogwheel icon button
        self._settings_btn = RoundedButton(
            inner, text="⚙", command=self._open_settings,
            style="default", width=40, height=34, font=(F.ui, 15),
            bg_under=T.header_bg)
        self._settings_btn.pack(side="right", padx=3)
        Tooltip(self._settings_btn, "Serial port, slider count, smoothing, theme")
        self._round_btns.append(self._settings_btn)

        # Divider
        tk.Frame(inner, bg=T.separator, width=1).pack(
            side="right", padx=(10, 12), fill="y", pady=4)

        # Profile selector
        pf = tk.Frame(inner, bg=T.header_bg)
        pf.pack(side="right")

        tk.Label(pf, text="Profile", font=F.tiny, bg=T.header_bg,
                 fg=T.fg_muted).pack(side="left", padx=(0, 6))

        self._profile_var   = tk.StringVar()
        self._profile_combo = ttk.Combobox(pf, textvariable=self._profile_var,
                                           width=14, state="readonly",
                                           font=F.small)
        self._profile_combo.pack(side="left", padx=(0, 6))
        self._profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)
        Tooltip(self._profile_combo, "Switch between saved slider profiles")

        # Uniform square icon buttons for profile actions. No explicit Save
        # button - changes autosave to the active profile, with a brief
        # "Saved ✓" confirmation in the status bar (Ctrl+S also forces a save).
        for txt, cmd, tip in [
            ("⧉", self._save_as_profile, "Save as a new profile"),
            ("－", self._delete_profile,  "Delete the current profile"),
        ]:
            b = RoundedButton(pf, text=txt, command=cmd, style="ghost",
                              width=32, height=32, font=F.small_b,
                              bg_under=T.header_bg)
            b.pack(side="left", padx=2)
            Tooltip(b, tip)
            self._round_btns.append(b)

        self._refresh_profile_list()

    def _build_body(self):
        # Optional first-run hint banner (shown only when no port is set
        # and nothing has ever connected). Packed above the slider area.
        self._hint_bar = tk.Frame(self, bg=T.accent_soft)
        hint_inner = tk.Frame(self._hint_bar, bg=T.accent_soft, padx=14, pady=8)
        hint_inner.pack(fill="x")
        tk.Label(hint_inner,
                 text="👋  No serial port selected yet - open ⚙ Settings to "
                      "choose your Arduino's port and get started.",
                 bg=T.accent_soft, fg="#ffffff", font=F.small, anchor="w"
                 ).pack(side="left")
        tk.Label(hint_inner, text="✕", bg=T.accent_soft, fg="#ffffff",
                 font=F.small_b, cursor="hand2", padx=4
                 ).pack(side="right")
        # (the ✕ and the bar are wired up in _update_hint)
        for child in hint_inner.winfo_children():
            if child.cget("text") == "✕":
                child.bind("<Button-1>", lambda e: self._dismiss_hint())
        self._hint_dismissed = False

        self._body = tk.Frame(self, bg=T.bg_root, padx=22, pady=22)
        self._body.pack(fill="both", expand=True)
        self._update_hint()

    def _update_hint(self):
        """Show the first-run hint only when no port is configured and the
        user hasn't dismissed it. Hidden once a port is set or on dismiss."""
        if getattr(self, "_hint_dismissed", False):
            self._hint_bar.pack_forget()
            return
        port = self.config_mgr.get("serial", "port", default="")
        no_port = not port or port in ("?", "COM3")  # COM3 is the unconfigured default
        if no_port and not (self.serial_reader and self.serial_reader.connected):
            # Pack above the body
            self._hint_bar.pack(fill="x", before=self._body)
        else:
            self._hint_bar.pack_forget()

    def _dismiss_hint(self):
        self._hint_dismissed = True
        self._hint_bar.pack_forget()

    def _build_status_bar(self):
        # Widgets are recreated (e.g. theme toggle) - force the next
        # connection check to repaint them.
        self._last_conn_state = None
        bar = tk.Frame(self, bg=T.status_bg, pady=6)
        bar.pack(fill="x", side="bottom")
        tk.Frame(bar, bg=T.separator, height=1).place(relx=0, rely=0,
                                                       relwidth=1, anchor="nw")

        # Connection status as a subtle pill (dot + text inside a rounded frame)
        self._status_pill = tk.Frame(bar, bg=T.status_bg)
        self._status_pill.pack(side="left", padx=(12, 0))
        self._status_dot = tk.Label(self._status_pill, text="●", bg=T.status_bg,
                                     fg=T.err, font=F.tiny)
        self._status_dot.pack(side="left", padx=(8, 3), pady=2)
        self._status_label = tk.Label(self._status_pill, text="Connecting…",
                                       bg=T.status_bg, fg=T.err, font=F.tiny)
        self._status_label.pack(side="left", padx=(0, 10), pady=2)

        # Shortened config path (~/.config/… rather than the full /home/...)
        cfg = str(self.config_mgr.config_path)
        home = str(Path.home())
        if cfg.startswith(home):
            cfg = "~" + cfg[len(home):]
        tk.Label(bar, text=cfg, bg=T.status_bg, fg=T.fg_subtle, font=F.tiny
                 ).pack(side="right", padx=12)

        if self.debug:
            tk.Label(bar, text="DEBUG", bg=T.err, fg="white",
                     font=F.badge, padx=4).pack(side="right", padx=8)

    # Sliders                                                              #

    def _rebuild_slider_panels(self):
        for w in self._body.winfo_children():
            w.destroy()
        self._slider_panels.clear()
        count = self.config_mgr.get("sliders", "count", default=5)
        # Reset any column weights from a previous (different-count) build
        for c in range(64):
            try: self._body.grid_columnconfigure(c, weight=0)
            except Exception: break
        self._body.grid_rowconfigure(0, weight=1)
        for i in range(count):
            p = SliderPanel(self._body, index=i,
                            on_change=self._on_slider_changed,
                            on_label_change=self._on_label_changed,
                            on_settings=self._open_slider_settings)
            # sticky="nsew" + equal column weight makes the cards grow to fill
            # the window width (and height), eliminating dead space on resize.
            p.grid(row=0, column=i, padx=8, pady=4, sticky="nsew")
            self._body.grid_columnconfigure(i, weight=1, uniform="sliders")
            self._slider_panels.append(p)
        self._apply_mute_visuals()
        if self.detector:
            self._on_apps_updated(self.detector.get_dropdown_values())

    # Profiles                                                             #

    def _refresh_profile_list(self):
        self._profile_combo["values"] = self.config_mgr.get_profile_names()
        self._profile_var.set(self.config_mgr.current_profile)

    def _load_profile(self, name):
        a = self.config_mgr.get_profile_assignments(name)
        self._loading_profile = True
        try:
            for i, p in enumerate(self._slider_panels):
                entry = a[i] if i < len(a) else {}
                p.set_target(entry.get("target", ""))
                p.set_label(entry.get("label", f"Slider {i + 1}"))
        finally:
            self._loading_profile = False
        self._invalidate_assignments()
        self._set_save_state(saved=True)   # freshly loaded → nothing unsaved

    def _save_assignments(self):
        self.config_mgr.set_profile_assignments([
            {"target": p.get_target(), "label": p.get_label()}
            for p in self._slider_panels])
        # Autosave just persisted everything → nothing unsaved → grey the button
        self._set_save_state(saved=True)

    def _mark_dirty(self):
        """A slider/label/target changed - light the save button until the
        autosave (or Ctrl+S) persists it."""
        self._set_save_state(saved=False)

    def _set_save_state(self, saved: bool):
        """Track saved/unsaved state and show a brief 'Saved ✓' confirmation
        when changes are persisted. There's no Save button (changes autosave);
        this just drives the status-bar confirmation."""
        was_dirty = getattr(self, "_dirty", False)
        self._dirty = not saved
        # Confirm only on a real transition from unsaved → saved, so it doesn't
        # flash on initial load or profile switches.
        if saved and was_dirty and getattr(self, "_status_label", None):
            self._status_label.config(text="Saved ✓", fg=T.ok)
            self.after(1500, self._restore_status)

    def _restore_status(self):
        self._last_conn_state = None   # force the next check to repaint
        self._check_connection()

    def _on_label_changed(self, _panel):
        # Persist the edited slider label into the current profile
        self._save_assignments()

    def _open_slider_settings(self, panel):
        """Open the per-slider mute/invert/calibrate dialog for one card."""
        def get_raw():
            if self.serial_reader:
                return self.serial_reader.get_raw_value(panel.index)
            return None
        SliderSettingsDialog(
            self, self.config_mgr, panel.index,
            label=panel.get_label(),
            get_raw=get_raw,
            on_apply=self._on_slider_settings_saved)

    def _on_slider_settings_saved(self):
        # Restart serial so calibration / invert / smoothing take effect,
        # then refresh each card's mute indicator from config.
        self._start_serial()
        self._apply_mute_visuals()

    def _apply_mute_visuals(self):
        for p in self._slider_panels:
            muted = bool(self.config_mgr.get_slider_settings(p.index)["muted"])
            p.set_muted(muted)

    def _save_profile(self):
        """Explicitly save the current slider setup to the active profile
        (also bound to Ctrl+S)."""
        self._save_assignments()   # writes config + shows "Saved ✓" + greys btn

    def _on_profile_selected(self, _=None):
        name = self._profile_var.get()
        self.config_mgr.current_profile = name
        self._load_profile(name)
        self._invalidate_assignments()
        self._update_panel_active_states()

    # Tray profile switching

    def _get_profiles_for_tray(self):
        """Called from the tray thread - reads only, safe."""
        return (self.config_mgr.get_profile_names(),
                self.config_mgr.current_profile)

    def _on_tray_profile_select(self, name: str):
        """Called from the tray thread - marshal to the GUI thread."""
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
        """Called when a second launch is detected - raise the window."""
        self._do_show()

    def _delete_profile(self):
        n = self._profile_var.get()
        if not themed_confirm(self, "Delete Profile",
                              f"Delete profile '{n}'?",
                              ok_text="Delete", cancel_text="Cancel"):
            return
        if not self.config_mgr.delete_profile(n):
            themed_message(self, "Cannot Delete",
                           "Can't delete the last profile.", kind="warning")
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
            themed_message(self, "Name In Use",
                           f"A profile named '{new}' already exists.",
                           kind="warning")
            return
        # Create the new profile, copy assignments into it, switch to it
        assignments = self.config_mgr.get_profile_assignments(src)
        self.config_mgr.add_profile(new)
        self.config_mgr.set_profile_assignments(assignments, new)
        self.config_mgr.current_profile = new
        self._refresh_profile_list()
        self._load_profile(new)

    # App detection                                                        #

    def _on_apps_updated(self, app_list):
        def _apply(a=app_list):
            self._last_app_list = a
            self._update_panel_active_states()
        self.after(0, _apply)

    @staticmethod
    def _target_apps(target) -> set:
        """Lower-cased set of app names in a target (empty for specials/none)."""
        if isinstance(target, list):
            return {a.strip().lower() for a in target if a and a.strip()}
        t = (target or "").strip().lower()
        if t in ("", "none", "master", "all_others"):
            return set()
        return {t}

    def _refresh_dropdowns(self):
        """Give each panel the list of assignable APPS minus apps already
        taken by OTHER panels (one app per slider). The special keywords
        (none/master/all_others) are handled by the picker's radio buttons,
        so they're filtered out of the app checklist here."""
        full = getattr(self, "_last_app_list", None)
        if full is None and self.detector:
            full = self.detector.get_dropdown_values()
        if full is None:
            return
        specials = {"none", "master", "all_others"}
        apps_only = [v for v in full if v.strip().lower() not in specials]
        owned = [self._target_apps(p.get_target()) for p in self._slider_panels]
        for i, panel in enumerate(self._slider_panels):
            taken = set().union(*(owned[j] for j in range(len(owned)) if j != i)) \
                    if len(owned) > 1 else set()
            panel.set_dropdown_values(
                [v for v in apps_only if v.lower() not in taken])

    def _update_panel_active_states(self):
        """Refresh app filtering and each slider's ● active / ○ not running /
        – none / – unassigned indicator."""
        self._refresh_dropdowns()
        running = [a.lower() for a in
                   (self.detector.get_current_apps() if self.detector else [])]
        for p in self._slider_panels:
            target = p.get_target()
            apps = self._target_apps(target)
            if isinstance(target, list):
                if not apps:
                    p.set_active("unassigned")
                # Active if ANY assigned app is currently producing audio
                elif any(any(t in app for app in running) for t in apps):
                    p.set_active("active")
                else:
                    p.set_active("inactive")
            else:
                t = (target or "").strip().lower()
                if not t:
                    p.set_active("unassigned")
                elif t == "none":
                    p.set_active("none")
                elif t in ("master", "all_others"):
                    p.set_active("active")
                else:
                    p.set_active("inactive")

    # Serial / audio                                                       #

    def _start_serial(self):
        port   = self.config_mgr.get("serial", "port", default="")
        # First run / no real port saved → try to auto-detect a sole Arduino.
        if not port or port in ("COM3", "?"):
            detected = SerialReader.auto_detect_port()
            if detected:
                port = detected
                self.config_mgr.set(port, "serial", "port")
                logger.info(f"Auto-detected Arduino on {port}")
        baud   = self.config_mgr.get("serial","baud_rate", default=9600)
        count  = self.config_mgr.get("sliders","count",    default=5)
        smooth = self.config_mgr.get("sliders","smoothing",default=0.6)
        invert = self.config_mgr.get("sliders","invert",   default=False)
        slider_settings = [self.config_mgr.get_slider_settings(i)
                           for i in range(count)]
        if self.serial_reader:
            self.serial_reader.stop()
        self.serial_reader = SerialReader(
            port=port, baud_rate=baud, num_sliders=count, invert=bool(invert),
            smoothing=smooth, callback=self._on_serial_values,
            error_callback=self._on_serial_error, debug=self.debug,
            slider_settings=slider_settings)
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
        """Profile assignments, cached - rebuilt only when the profile or
        settings change, not 100×/sec on every serial tick."""
        if self._assignments_cache is None:
            assignments = self.config_mgr.get_profile_assignments()
            # Exclude set for 'all_others': every explicit app target assigned
            # to any slider - flattened across both single and multi-app
            # (list) targets. Specials never contribute apps.
            exclude = set()
            for a in assignments:
                exclude |= self._target_apps(a.get("target", ""))
            self._assignments_cache = (assignments, exclude)
        return self._assignments_cache

    def _invalidate_assignments(self):
        """Drop the cached profile mapping. Deliberately does NOT force a
        volume re-send: switching profiles or reassigning a slider must not
        push the current pot positions onto the newly-assigned apps. A
        target's volume only changes when its pot physically moves
        ("pickup" behaviour). Launch is the one exception - the tracker
        starts empty, so initial pot positions apply immediately."""
        self._assignments_cache = None

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
            audio = self.audio
            if audio and i < len(assignments):
                try:
                    self.audio.apply_slider(
                        assignments[i].get("target", ""), values[i],
                        exclude=exclude)
                except Exception as e: logger.debug(f"apply_slider: {e}")

    def _on_slider_changed(self, panel):
        if getattr(self, "_loading_profile", False):
            return   # programmatic set_target during a profile load
        # Duplicate prevention (one app per slider) is enforced up-front by
        # _update_panel_active_states / _refresh_dropdowns, which only offer
        # each panel the apps not already owned by another slider. The picker
        # applies atomically, so no post-hoc bounce is needed here.
        self._mark_dirty()
        self._invalidate_assignments()
        self._save_assignments()   # autosave → confirms + greys the button
        self._update_panel_active_states()

    # Error dialog (single instance)                                      #

    def _on_serial_error(self, err: SerialError):
        self.after(0, lambda e=err: self._show_error(e))

    def _show_error(self, err: SerialError):
        # "Cannot connect" is communicated by the red status bar, not a
        # popup - only show dialogs for parse/disconnect faults that point
        # to a wiring or hardware problem worth the user's attention.
        if err.kind == SerialError.CONNECT:
            return
        if self._error_dialog_active:
            return
        self._error_dialog_active = True
        ErrorDialog(self, err.kind, err.message, err.raw_line,
                    on_dismiss=lambda: setattr(self, "_error_dialog_active", False))

    # Connecting dialog                                                    #

    def _show_connecting_dialog(self):
        dlg = self._connecting_dialog
        if dlg and dlg.winfo_exists():
            dlg.show_reconnecting()
            return
        self._connecting_dialog = ConnectingDialog(
            parent=self,
            get_port=lambda: self.config_mgr.get("serial","port",default="?"),
            list_ports=SerialReader.list_ports,
            on_port_change=self._on_port_changed)

    def _on_port_changed(self, new_port):
        self.config_mgr.set(new_port, "serial", "port")
        self._start_serial()

    # Connection status                                                    #

    def _schedule_conn_check(self):
        self._check_connection()
        self.after(self.CONN_CHECK_INTERVAL, self._schedule_conn_check)

    def _check_connection(self):
        connected = self.serial_reader is not None and self.serial_reader.connected
        port = self.config_mgr.get("serial","port",default="?")

        # Only touch the widgets when something actually changed -
        # avoids a redundant redraw every second at steady state.
        state = (connected, port)
        if state != getattr(self, "_last_conn_state", None):
            self._last_conn_state = state
            if connected:
                col, txt = T.ok, f"Connected  ({port})"
            else:
                col, txt = T.err, f"Not connected  ({port})"
            self._status_dot.config(fg=col)
            self._status_label.config(text=txt, fg=col)
            self._update_hint()

        if connected:
            dlg = self._connecting_dialog
            if dlg and dlg.winfo_exists():
                dlg.notify_connected()
            self._was_connected = True
        else:
            if self._was_connected:
                self._was_connected = False
                if self._reconnect_job:
                    self.after_cancel(self._reconnect_job)
                self._reconnect_job = self.after(
                    RECONNECT_DIALOG_DELAY, self._show_connecting_dialog)

    # Settings                                                             #

    def _open_settings(self):
        SettingsDialog(parent=self, config_mgr=self.config_mgr,
                       list_ports=SerialReader.list_ports,
                       on_save=self._on_settings_saved)

    def _on_settings_saved(self):
        # Apply theme choice ("auto" resolves against the OS setting now)
        pref = self.config_mgr.get("ui", "theme", default="auto")
        before = T.name
        T.apply(pref)
        if T.name != before:
            self._rebuild_ui()           # full re-skin (includes panels)
        else:
            self._rebuild_slider_panels()
            self._load_profile(self.config_mgr.current_profile)
        self._refresh_profile_list()     # pick up any imported/restored profiles
        self._start_serial()
        dlg = self._connecting_dialog
        if dlg and dlg.winfo_exists():
            dlg.update_port_display(
                self.config_mgr.get("serial","port",default=""))

    # Tray / lifecycle                                                     #

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
            self.detector.pause()    # nobody's looking - stop polling

    def _on_window_close(self):
        action = self.config_mgr.get("ui", "close_action", default="ask")

        # No tray → minimizing isn't possible. Still use the themed dialog
        # (quit-only variant) rather than the OS-native messagebox, so it
        # follows the light/dark theme. Respects a remembered "quit" choice.
        if not self._tray_available:
            if action == "ask":
                dlg = CloseDialog(self, tray_available=False)
                self.wait_window(dlg)
                if dlg.result is None:
                    return  # cancelled
                if dlg.remember:
                    self.config_mgr.set("quit", "ui", "close_action")
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
                return  # cancelled - do nothing
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
