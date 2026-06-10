"""
config_manager.py — BARJ Volume Controller

Config stored at:
  Linux:   ~/.config/barj-volume-controller/config.yaml
  Windows: %APPDATA%/BARJ Volume Controller/config.yaml

Never modified by the installer — safe across updates.
"""

import os
import platform
import yaml
import logging
from pathlib import Path
from copy import deepcopy

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "serial": {
        "port": "COM3",
        "baud_rate": 9600,
    },
    "sliders": {
        "count": 5,
        "smoothing": 0.15,
    },
    "ui": {
        "show_connecting_on_launch": True,   # show connecting dialog when app starts
        "theme": "auto",          # "auto" | "dark" | "light"
        "close_action": "ask",    # "ask" | "tray" | "quit"
    },
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
    def __init__(self, config_path: Path = None):
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

    @property
    def current_profile(self) -> str:
        return self.config.get("current_profile", "Default")

    @current_profile.setter
    def current_profile(self, name: str):
        self.config["current_profile"] = name
        self.save()

    def get_profile_names(self) -> list:
        return list(self.config.get("profiles", {}).keys())

    def get_profile_assignments(self, profile_name: str = None) -> list:
        name  = profile_name or self.current_profile
        count = self.config.get("sliders", {}).get("count", 5)
        assignments = list(self.config.get("profiles", {}).get(name, []))
        while len(assignments) < count:
            i = len(assignments)
            assignments.append({"target": "", "label": f"Slider {i + 1}"})
        return assignments[:count]

    def set_profile_assignments(self, assignments: list, profile_name: str = None):
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

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        profiles = self.config.get("profiles", {})
        if old_name in profiles and new_name not in profiles:
            profiles[new_name] = profiles.pop(old_name)
            if self.current_profile == old_name:
                self.config["current_profile"] = new_name
            self.save()
            return True
        return False
