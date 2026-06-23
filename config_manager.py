"""
BARJ Volume Controller

Config stored at:
  Linux:   ~/.config/barj-volume-controller/config.yaml
  Windows: %APPDATA%/BARJ Volume Controller/config.yaml

Never modified by the installer - safe across updates.
"""

import os
import platform
import yaml
import logging
from pathlib import Path
from copy import deepcopy
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "serial": {
        "port": "COM3",
        "baud_rate": 9600,
    },
    "sliders": {
        "count": 5,
        "smoothing": 0.6,
        "invert": False,    # global flip for backwards-wired pots
    },
    "ui": {
        "show_connecting_on_launch": True,   # show connecting dialog when app starts
        "theme": "auto",          # "auto" | "dark" | "light"
        "close_action": "ask",    # "ask" | "tray" | "quit"
        "launch_minimized": False,  # start hidden in the tray
        "start_on_login": False,    # autostart entry managed by autostart.py
    },
    # Per-slider tuning, indexed by slider number. Kept separate from profiles
    # so it describes the PHYSICAL hardware (calibration/invert/smoothing of a
    # given pot), which shouldn't change when you switch app-assignment profiles.
    #   muted:    bool  - slider muted (level forced to 0)
    #   invert:   bool  - flip this one slider (XORs with the global invert)
    #   cal_min:  int   - raw ADC value that should map to 0%   (0-1023)
    #   cal_max:  int   - raw ADC value that should map to 100% (0-1023)
    #   smoothing: float|null - per-slider override; null = use global
    "slider_settings": {},
    "profiles": {
        "Default": [
            {"target": "master",     "label": "Master"},
            {"target": "all_others", "label": "All Others"},
            {"target": "",           "label": "Slider 3"},
            {"target": "",           "label": "Slider 4"},
            {"target": "",           "label": "Slider 5"},
        ]
    },
    "current_profile": "Default",
}


def get_config_path() -> Path:
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home()))
        config_dir = base / "BARJ Volume Controller"
    else:
        xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        config_dir = xdg / "barj-volume-controller"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.yaml"


class ConfigManager:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or get_config_path()
        self.config: dict = {}
        self.load()
        logger.info(f"Config: {self.config_path}")

    def load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    loaded = yaml.safe_load(f) or {}
                self.config = self._deep_merge(deepcopy(DEFAULT_CONFIG), loaded)
            except Exception as e:
                logger.warning(f"Failed to load config: {e}. Using defaults.")
                self.config = deepcopy(DEFAULT_CONFIG)
        else:
            self.config = deepcopy(DEFAULT_CONFIG)
            self.save()

    def save(self):
        try:
            with open(self.config_path, "w") as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def _deep_merge(self, base: dict, override: dict) -> dict:
        result = base.copy()
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def get(self, *keys, default=None):
        val = self.config
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k, default)
            else:
                return default
        return val if val is not None else default

    def set(self, value, *keys):
        d = self.config
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value
        self.save()

    # Per-slider hardware settings (calibration / invert / mute / smoothing)

    _SLIDER_DEFAULTS = {
        "muted": False,
        "invert": False,
        "cal_min": 0,
        "cal_max": 1023,
        "smoothing": None,   # None → use the global smoothing value
    }

    def get_slider_settings(self, index: int) -> dict:
        """Return this slider's settings merged over the defaults."""
        store = self.config.setdefault("slider_settings", {})
        entry = store.get(str(index), {})
        merged = dict(self._SLIDER_DEFAULTS)
        merged.update(entry)
        return merged

    def set_slider_setting(self, index: int, key: str, value):
        store = self.config.setdefault("slider_settings", {})
        entry = store.setdefault(str(index), {})
        entry[key] = value
        self.save()

    @property
    def current_profile(self) -> str:
        return self.config.get("current_profile", "Default")

    @current_profile.setter
    def current_profile(self, name: str):
        self.config["current_profile"] = name
        self.save()

    def get_profile_names(self) -> list:
        return list(self.config.get("profiles", {}).keys())

    def get_profile_assignments(self, profile_name: Optional[str] = None) -> list:
        name  = profile_name or self.current_profile
        count = self.config.get("sliders", {}).get("count", 5)
        assignments = list(self.config.get("profiles", {}).get(name, []))
        while len(assignments) < count:
            i = len(assignments)
            assignments.append({"target": "", "label": f"Slider {i + 1}"})
        return assignments[:count]

    def set_profile_assignments(self, assignments: list, profile_name: Optional[str] = None):
        name = profile_name or self.current_profile
        self.config.setdefault("profiles", {})[name] = assignments
        self.save()

    def add_profile(self, name: str):
        if name not in self.config.setdefault("profiles", {}):
            count = self.config.get("sliders", {}).get("count", 5)
            self.config["profiles"][name] = [
                {"target": "", "label": f"Slider {i + 1}"} for i in range(count)
            ]
            self.save()

    def delete_profile(self, name: str) -> bool:
        profiles = self.config.get("profiles", {})
        if name in profiles and len(profiles) > 1:
            del profiles[name]
            if self.current_profile == name:
                self.config["current_profile"] = list(profiles.keys())[0]
            self.save()
            return True
        return False

    # Import / export

    def export_profile(self, name: str, path) -> bool:
        """Write a single profile (its assignments) to a YAML file."""
        profiles = self.config.get("profiles", {})
        if name not in profiles:
            return False
        payload = {
            "barj_export": "profile",
            "name": name,
            "assignments": profiles[name],
        }
        with open(path, "w") as f:
            yaml.dump(payload, f, default_flow_style=False, sort_keys=False)
        return True

    def import_profile(self, path) -> str:
        """Import a single profile from a YAML file. Returns the imported
        profile name (uniquified if it clashes), or raises on bad data."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict) or data.get("barj_export") != "profile":
            raise ValueError("Not a BARJ profile file.")
        name = str(data.get("name", "Imported")).strip() or "Imported"
        assignments = data.get("assignments")
        if not isinstance(assignments, list):
            raise ValueError("Profile file has no assignments.")
        # Uniquify the name if it already exists
        base, n, final = name, 2, name
        existing = self.config.setdefault("profiles", {})
        while final in existing:
            final = f"{base} ({n})"; n += 1
        existing[final] = assignments
        self.save()
        return final

    def export_all(self, path) -> bool:
        """Write the entire configuration (all profiles + settings) to YAML."""
        payload = dict(self.config)
        payload["barj_export"] = "full"
        with open(path, "w") as f:
            yaml.dump(payload, f, default_flow_style=False, sort_keys=False)
        return True

    def import_all(self, path) -> bool:
        """Replace the entire configuration from a full-backup YAML file.
        Merges over defaults so missing keys are filled in."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict) or data.get("barj_export") != "full":
            raise ValueError("Not a BARJ full-backup file.")
        data.pop("barj_export", None)
        self.config = self._deep_merge(deepcopy(DEFAULT_CONFIG), data)
        self.save()
        return True

