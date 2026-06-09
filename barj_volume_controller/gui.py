"""
BARJ Volume Controller - GUI

CustomTkinter interface providing:
  - Named profile save/load/delete
  - Add / remove sliders dynamically (default 5)
  - Device dropdown with discovered ports (BARJ devices flagged)
  - Per-slider target assignment with auto-detected apps,
    plus Master / Mic / System / All Others
  - Close-to-tray
  - Launch-on-startup (off by default) with open / minimized / tray modes
"""

import sys
import threading

import customtkinter as ctk

from .config import Config
from .audio import get_backend, MASTER, MIC, SYSTEM, ALL_OTHERS
from .serial_device import list_ports, SerialReader
from .controller import Controller
from . import autostart

try:
    import pystray
    from PIL import Image, ImageDraw
    _TRAY_OK = True
except Exception:
    _TRAY_OK = False


SPECIAL_TARGETS = [
    ("Master (global volume)", MASTER),
    ("Microphone", MIC),
    ("System sounds", SYSTEM),
    ("All Others (unassigned)", ALL_OTHERS),
]


class BarjApp(ctk.CTk):
    def __init__(self, startup_mode="open"):
        super().__init__()
        self.title("BARJ Volume Controller")
        self.geometry("760x620")
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.config_mgr = Config()
        try:
            self.backend = get_backend()
        except Exception as e:
            print(f"Audio backend error: {e}", file=sys.stderr)
            from .audio.base import AudioBackend
            self.backend = AudioBackend()

        self.controller = Controller(self.backend, self.config_mgr)
        self.reader = None
        self.tray_icon = None
        self.slider_rows = []          # list of dicts per slider row widget set
        self.apps = []                 # discovered audio apps
        self.ports = []                # discovered serial ports

        self._build_ui()
        self._load_active_profile_into_ui()
        self.refresh_apps()
        self.refresh_ports()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Apply startup mode
        if startup_mode == "minimized":
            self.iconify()
        elif startup_mode == "tray":
            self.after(200, self.hide_to_tray)

        # Auto-connect if a port is stored
        stored = self.config_mgr.data["device"]["port"]
        if stored:
            self.after(500, self.connect_device)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ---- Top bar: profiles + device ----
        top = ctk.CTkFrame(self)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        top.grid_columnconfigure(1, weight=1)
        top.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(top, text="Profile:").grid(row=0, column=0, padx=(8, 4), pady=8)
        self.profile_menu = ctk.CTkOptionMenu(
            top, values=self.config_mgr.profile_names(), command=self.on_profile_selected
        )
        self.profile_menu.grid(row=0, column=1, sticky="ew", padx=4)
        self.profile_menu.set(self.config_mgr.data["active_profile"])

        ctk.CTkButton(top, text="Save", width=64, command=self.save_profile_dialog).grid(row=0, column=2, padx=4)
        ctk.CTkButton(top, text="Delete", width=64, command=self.delete_profile).grid(row=0, column=3, padx=(4, 8))

        ctk.CTkLabel(top, text="Device:").grid(row=1, column=0, padx=(8, 4), pady=8)
        self.device_menu = ctk.CTkOptionMenu(top, values=["(scanning...)"], command=self.on_device_selected)
        self.device_menu.grid(row=1, column=1, columnspan=2, sticky="ew", padx=4)
        ctk.CTkButton(top, text="Rescan", width=64, command=self.refresh_ports).grid(row=1, column=3, padx=4)
        self.connect_btn = ctk.CTkButton(top, text="Connect", width=80, command=self.connect_device)
        self.connect_btn.grid(row=1, column=4, padx=(4, 8))

        # ---- Slider controls bar ----
        ctrl = ctk.CTkFrame(self)
        ctrl.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        ctk.CTkButton(ctrl, text="+ Add slider", command=self.add_slider).pack(side="left", padx=6, pady=6)
        ctk.CTkButton(ctrl, text="Refresh apps", command=self.refresh_apps).pack(side="left", padx=6)
        self.invert_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(ctrl, text="Invert sliders", variable=self.invert_var,
                      command=self.on_invert_toggle).pack(side="left", padx=12)

        # ---- Scrollable slider list ----
        self.slider_frame = ctk.CTkScrollableFrame(self, label_text="Sliders")
        self.slider_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        self.slider_frame.grid_columnconfigure(0, weight=1)

        # ---- Bottom: settings ----
        bottom = ctk.CTkFrame(self)
        bottom.grid(row=3, column=0, sticky="ew", padx=10, pady=(5, 10))

        self.tray_var = ctk.BooleanVar(value=self.config_mgr.data.get("close_to_tray", True))
        ctk.CTkSwitch(bottom, text="Close to system tray", variable=self.tray_var,
                      command=self.on_tray_toggle).pack(side="left", padx=8, pady=8)

        self.startup_var = ctk.BooleanVar(value=self.config_mgr.data["autostart"]["enabled"])
        ctk.CTkSwitch(bottom, text="Launch on startup", variable=self.startup_var,
                      command=self.on_startup_toggle).pack(side="left", padx=8)

        self.startup_mode_menu = ctk.CTkOptionMenu(
            bottom, values=["open", "minimized", "tray"], width=120,
            command=self.on_startup_mode_change,
        )
        self.startup_mode_menu.set(self.config_mgr.data["autostart"]["mode"])
        self.startup_mode_menu.pack(side="left", padx=8)
        self._update_startup_mode_state()

        self.status = ctk.CTkLabel(self, text="Idle", anchor="w")
        self.status.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 8))

    # ------------------------------------------------------- slider rows
    def _target_choices(self):
        choices = [label for label, _ in SPECIAL_TARGETS]
        choices += [f"App: {a['label']}" for a in self.apps]
        return choices

    def _target_id_from_choice(self, choice):
        for label, tid in SPECIAL_TARGETS:
            if choice == label:
                return tid
        if choice.startswith("App: "):
            label = choice[len("App: "):]
            for a in self.apps:
                if a["label"] == label:
                    return a["id"]
        return None

    def _choice_from_target_id(self, tid):
        for label, t in SPECIAL_TARGETS:
            if t == tid:
                return label
        for a in self.apps:
            if a["id"] == tid:
                return f"App: {a['label']}"
        return tid  # unknown / not currently running

    def add_slider(self, targets=None):
        idx = len(self.slider_rows)
        row = ctk.CTkFrame(self.slider_frame)
        row.grid(row=idx, column=0, sticky="ew", pady=4)
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text=f"Slider {idx}", width=70).grid(row=0, column=0, padx=6, pady=6)

        choices = self._target_choices() or ["(no apps)"]
        menu = ctk.CTkOptionMenu(row, values=choices)
        menu.grid(row=0, column=1, sticky="ew", padx=6)
        if targets:
            menu.set(self._choice_from_target_id(targets[0]))
        else:
            menu.set(choices[0])

        bar = ctk.CTkProgressBar(row, width=140)
        bar.set(0)
        bar.grid(row=0, column=2, padx=6)

        remove = ctk.CTkButton(row, text="Remove", width=70,
                               command=lambda: self.remove_slider(idx))
        remove.grid(row=0, column=3, padx=6)

        self.slider_rows.append({"frame": row, "menu": menu, "bar": bar})

    def remove_slider(self, idx):
        if idx < 0 or idx >= len(self.slider_rows):
            return
        self.slider_rows[idx]["frame"].destroy()
        del self.slider_rows[idx]
        self._regrid_sliders()

    def _regrid_sliders(self):
        for i, rowset in enumerate(self.slider_rows):
            rowset["frame"].grid(row=i, column=0, sticky="ew", pady=4)
            for child in rowset["frame"].winfo_children():
                if isinstance(child, ctk.CTkLabel) and child.cget("text").startswith("Slider"):
                    child.configure(text=f"Slider {i}")
            # rebind remove button
            for child in rowset["frame"].winfo_children():
                if isinstance(child, ctk.CTkButton) and child.cget("text") == "Remove":
                    child.configure(command=lambda idx=i: self.remove_slider(idx))

    def _clear_sliders(self):
        for rowset in self.slider_rows:
            rowset["frame"].destroy()
        self.slider_rows = []

    # ------------------------------------------------------ profile I/O
    def _collect_profile(self):
        mapping = {}
        for i, rowset in enumerate(self.slider_rows):
            tid = self._target_id_from_choice(rowset["menu"].get())
            mapping[str(i)] = [tid] if tid else []
        return {
            "num_sliders": len(self.slider_rows),
            "mapping": mapping,
            "invert_sliders": self.invert_var.get(),
        }

    def _load_active_profile_into_ui(self):
        profile = self.config_mgr.active_profile()
        self.invert_var.set(profile.get("invert_sliders", False))
        self._clear_sliders()
        n = profile.get("num_sliders", 5)
        mapping = profile.get("mapping", {})
        for i in range(n):
            targets = mapping.get(str(i), [])
            self.add_slider(targets=targets)

    def on_profile_selected(self, name):
        self.config_mgr.set_active_profile(name)
        self.config_mgr.save()
        self._load_active_profile_into_ui()
        self._restart_reader_invert()

    def save_profile_dialog(self):
        dialog = ctk.CTkInputDialog(text="Profile name:", title="Save Profile")
        name = dialog.get_input()
        if not name:
            return
        self.config_mgr.save_profile(name, self._collect_profile())
        self.profile_menu.configure(values=self.config_mgr.profile_names())
        self.profile_menu.set(name)
        self.set_status(f"Saved profile '{name}'")

    def delete_profile(self):
        name = self.profile_menu.get()
        self.config_mgr.delete_profile(name)
        self.profile_menu.configure(values=self.config_mgr.profile_names())
        self.profile_menu.set(self.config_mgr.data["active_profile"])
        self._load_active_profile_into_ui()
        self.set_status(f"Deleted profile '{name}'")

    # ------------------------------------------------------- apps/ports
    def refresh_apps(self):
        def worker():
            try:
                self.apps = self.backend.list_sessions()
            except Exception:
                self.apps = []
            self.after(0, self._apply_app_choices)
        threading.Thread(target=worker, daemon=True).start()

    def _apply_app_choices(self):
        choices = self._target_choices() or ["(no apps)"]
        for rowset in self.slider_rows:
            current = rowset["menu"].get()
            rowset["menu"].configure(values=choices)
            if current in choices:
                rowset["menu"].set(current)
        self.set_status(f"Found {len(self.apps)} audio apps")

    def refresh_ports(self):
        self.device_menu.configure(values=["(scanning...)"])
        self.device_menu.set("(scanning...)")

        def worker():
            try:
                self.ports = list_ports(probe=True,
                                        baud=self.config_mgr.data["device"]["baud_rate"])
            except Exception:
                self.ports = []
            self.after(0, self._apply_port_choices)
        threading.Thread(target=worker, daemon=True).start()

    def _apply_port_choices(self):
        labels = []
        for p in self.ports:
            tag = " [BARJ]" if p["is_barj"] else ""
            labels.append(f"{p['port']} - {p['label']}{tag}")
        if not labels:
            labels = ["(no devices found)"]
        self.device_menu.configure(values=labels)
        stored = self.config_mgr.data["device"]["port"]
        chosen = next((l for l in labels if l.startswith(stored + " ")), None) if stored else None
        if not chosen:
            chosen = next((l for p, l in zip(self.ports, labels) if p["is_barj"]), labels[0])
        self.device_menu.set(chosen)
        self.set_status(f"Found {len(self.ports)} serial port(s)")

    def on_device_selected(self, label):
        port = label.split(" - ")[0]
        self.config_mgr.data["device"]["port"] = port
        self.config_mgr.save()

    # ------------------------------------------------------- connection
    def connect_device(self):
        label = self.device_menu.get()
        if " - " not in label:
            self.set_status("No valid device selected")
            return
        port = label.split(" - ")[0]
        self.config_mgr.data["device"]["port"] = port
        self.config_mgr.save()

        if self.reader:
            self.reader.stop()
            self.reader = None

        baud = self.config_mgr.data["device"]["baud_rate"]
        self.reader = SerialReader(
            port, baud,
            on_values=lambda v: self.after(0, self._on_values, v),
            on_status=lambda s: self.after(0, self.set_status, s),
            invert=self.invert_var.get(),
        )
        self.reader.start()
        self.connect_btn.configure(text="Reconnect")

    def _restart_reader_invert(self):
        if self.reader:
            self.connect_device()

    def _on_values(self, values):
        # update progress bars
        for i, rowset in enumerate(self.slider_rows):
            if i < len(values):
                rowset["bar"].set(values[i])
        # apply to audio
        self.controller.apply(values)

    # ------------------------------------------------------- settings
    def on_invert_toggle(self):
        prof = self.config_mgr.active_profile()
        prof["invert_sliders"] = self.invert_var.get()
        self.config_mgr.save()
        self._restart_reader_invert()

    def on_tray_toggle(self):
        self.config_mgr.data["close_to_tray"] = self.tray_var.get()
        self.config_mgr.save()

    def on_startup_toggle(self):
        enabled = self.startup_var.get()
        mode = self.startup_mode_menu.get()
        self.config_mgr.data["autostart"]["enabled"] = enabled
        self.config_mgr.data["autostart"]["mode"] = mode
        self.config_mgr.save()
        try:
            autostart.set_autostart(enabled, mode)
            self.set_status(f"Autostart {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            self.set_status(f"Autostart error: {e}")
        self._update_startup_mode_state()

    def on_startup_mode_change(self, mode):
        self.config_mgr.data["autostart"]["mode"] = mode
        self.config_mgr.save()
        if self.startup_var.get():
            try:
                autostart.set_autostart(True, mode)
            except Exception:
                pass

    def _update_startup_mode_state(self):
        state = "normal" if self.startup_var.get() else "disabled"
        self.startup_mode_menu.configure(state=state)

    # ------------------------------------------------------- tray/close
    def set_status(self, text):
        self.status.configure(text=text)

    def _make_tray_image(self):
        img = Image.new("RGB", (64, 64), (30, 35, 39))
        d = ImageDraw.Draw(img)
        for i, x in enumerate((14, 32, 50)):
            d.rectangle([x - 3, 12, x + 3, 52], fill=(80, 160, 240))
            d.ellipse([x - 7, 20 + i * 8, x + 7, 34 + i * 8], fill=(240, 240, 240))
        return img

    def hide_to_tray(self):
        if not _TRAY_OK:
            self.iconify()
            return
        self.withdraw()
        if self.tray_icon is None:
            menu = pystray.Menu(
                pystray.MenuItem("Show", self._tray_show, default=True),
                pystray.MenuItem("Quit", self._tray_quit),
            )
            self.tray_icon = pystray.Icon(
                "BARJ", self._make_tray_image(), "BARJ Volume Controller", menu
            )
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _tray_show(self, icon=None, item=None):
        self.after(0, self.deiconify)

    def _tray_quit(self, icon=None, item=None):
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.after(0, self.quit_app)

    def on_close(self):
        if self.tray_var.get():
            self.hide_to_tray()
        else:
            self.quit_app()

    def quit_app(self):
        if self.reader:
            self.reader.stop()
        try:
            self.backend.cleanup()
        except Exception:
            pass
        if self.tray_icon:
            self.tray_icon.stop()
        self.destroy()


def run(startup_mode="open"):
    app = BarjApp(startup_mode=startup_mode)
    app.mainloop()
