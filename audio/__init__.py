"""
audio/__init__.py
AudioController abstract base + platform auto-selection.
"""

import platform
import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


class AudioController(ABC):

    @abstractmethod
    def set_master_volume(self, level: float):
        """Set the default playback device volume. level is 0.0–1.0."""

    @abstractmethod
    def get_master_volume(self) -> float:
        """Return current master volume as 0.0–1.0."""

    @abstractmethod
    def set_app_volume(self, process_name: str, level: float):
        """Set volume for all audio sessions belonging to process_name."""

    @abstractmethod
    def set_all_others_volume(self, level: float, exclude: Set[str]):
        """
        Set volume on every running audio app whose name does NOT match
        any entry in `exclude` (the targets assigned to other sliders).
        Matching must mirror set_app_volume's matching rules.
        """

    @abstractmethod
    def get_running_audio_apps(self) -> List[str]:
        """Return sorted list of process names currently producing audio."""

    def apply_slider(self, target: str, level: float,
                     exclude: Optional[Set[str]] = None):
        """
        Route a slider value to its assigned target.
        `exclude` is the set of app targets assigned to OTHER sliders —
        only used by 'all_others'.
        """
        if not target:
            return
        t = target.strip().lower()
        if t == "none":
            return          # explicit "controls nothing" assignment
        if t == "master":
            self.set_master_volume(level)
        elif t == "all_others":
            self.set_all_others_volume(level, exclude or set())
        else:
            self.set_app_volume(target, level)


def get_audio_controller() -> AudioController:
    system = platform.system()
    if system == "Windows":
        from .windows_audio import WindowsAudioController
        return WindowsAudioController()
    elif system == "Linux":
        from .linux_audio import LinuxAudioController
        return LinuxAudioController()
    else:
        raise RuntimeError(
            f"Unsupported platform: {system}. "
            "Only Windows and Linux are supported."
        )
