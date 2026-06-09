"""
audio/base.py
Abstract base class — mic removed.
"""

from abc import ABC, abstractmethod
from typing import List


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
    def get_running_audio_apps(self) -> List[str]:
        """Return sorted list of process names currently producing audio."""

    def apply_slider(self, target: str, level: float):
        """
        Route a slider value to its assigned target.
        Special keyword: 'master'
        Anything else is treated as a process name.
        """
        if not target:
            return
        t = target.strip().lower()
        if t == "master":
            self.set_master_volume(level)
        else:
            self.set_app_volume(target, level)
