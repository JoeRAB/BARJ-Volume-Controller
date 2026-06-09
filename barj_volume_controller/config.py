"""
Configuration & profile management for BARJ Volume Controller.

Config lives in a per-user config directory:
  - Linux:   ~/.config/BARJ/
  - macOS:   ~/Library/Application Support/BARJ/
  - Windows: %APPDATA%\\BARJ\\

config.json holds global settings + named profiles. A profile defines the
slider count and per-slider target mappings.
"""

import json
import os
import sys


APP_NAME = "BARJ"


def config_dir():
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, APP_NAME)
    elif sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~/Library/Application Support"), APP_NAME)
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        return os.path.join(base, APP_NAME)


def config_path():
    return os.path.join(config_dir(), "config.json")


DEFAULT_PROFILE = {
    "num_sliders": 5,
    # mapping: slider index (as string) -> list of target ids
    # target ids may be app ids or special: master / mic / system / all_others
    "mapping": {
        "0": ["master"],
        "1": [],
        "2": [],
        "3": [],
        "4": ["all_others"],
    },
    "invert_sliders": False,
}

DEFAULT_CONFIG = {
    "version": 1,
    "active_profile": "Default",
    "profiles": {"Default": DEFAULT_PROFILE},
    "device": {
        "port": "",          # serial port, e.g. COM4 or /dev/ttyACM0
        "baud_rate": 9600,
        "auto_detect": True, # prefer ports that respond to barj-id?
    },
    "noise_reduction": "default",  # low | default | high
    "autostart": {
        "enabled": False,
        "mode": "open",      # open | minimized | tray
    },
    "close_to_tray": True,
}


class Config:
    def __init__(self):
        self.data = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
        self.load()

    # ---- persistence -------------------------------------------------------
    def load(self):
        path = config_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self._merge(self.data, loaded)
            except Exception:
                pass
        return self

    def save(self):
        os.makedirs(config_dir(), exist_ok=True)
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def _merge(self, base, incoming):
        for k, v in incoming.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                self._merge(base[k], v)
            else:
                base[k] = v

    # ---- profile helpers ---------------------------------------------------
    def profile_names(self):
        return list(self.data["profiles"].keys())

    def active_profile(self):
        name = self.data["active_profile"]
        if name not in self.data["profiles"]:
            name = self.profile_names()[0]
            self.data["active_profile"] = name
        return self.data["profiles"][name]

    def set_active_profile(self, name):
        if name in self.data["profiles"]:
            self.data["active_profile"] = name

    def save_profile(self, name, profile):
        self.data["profiles"][name] = profile
        self.data["active_profile"] = name
        self.save()

    def delete_profile(self, name):
        if name in self.data["profiles"] and len(self.data["profiles"]) > 1:
            del self.data["profiles"][name]
            if self.data["active_profile"] == name:
                self.data["active_profile"] = self.profile_names()[0]
            self.save()
