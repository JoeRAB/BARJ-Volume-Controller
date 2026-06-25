"""
AudioController abstract base, platform auto-selection, and the
AppDetector that polls which apps are running and which are producing audio.
"""

import platform
import logging
import threading
from abc import ABC, abstractmethod
from typing import Callable, List, Optional, Set

logger = logging.getLogger(__name__)

# psutil lets us tell "running but silent" apart from "not running at all".
# It's optional: without it we fall back to audio-only detection (an app only
# shows as running when it's actively producing sound).
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


def _running_process_names() -> Set[str]:
    """Lowercased names of all running processes (empty set if psutil absent)."""
    if not PSUTIL_AVAILABLE:
        return set()
    names = set()
    for proc in psutil.process_iter(["name"]):
        try:
            n = (proc.info.get("name") or "").lower()
            if n:
                names.add(n)
                # Also add the name without a common executable suffix so
                # "firefox" matches a process called "firefox-bin", etc.
                if n.endswith(".exe"):
                    names.add(n[:-4])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return names


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

    def apply_slider(self, target, level: float,
                     exclude: Optional[Set[str]] = None):
        """
        Route a slider value to its assigned target.

        `target` may be:
          - a special keyword string: "none" | "master" | "all_others"
          - a single app name (string)
          - a list of app names (multi-app slider) - the level is applied to
            every assigned app that is currently producing audio; apps that
            aren't running are simply ignored.

        `exclude` is the set of app targets assigned to OTHER sliders -
        only used by 'all_others'.
        """
        if not target:
            return

        # Normalise to a list for uniform handling. Special keywords only ever
        # appear as a lone string (the UI forbids mixing them with apps).
        if isinstance(target, str):
            t = target.strip().lower()
            if t == "none":
                return          # explicit "controls nothing" assignment
            if t == "master":
                self.set_master_volume(level)
                return
            if t == "all_others":
                self.set_all_others_volume(level, exclude or set())
                return
            targets = [target]
        else:
            targets = [a for a in target if a and a.strip()]

        for app in targets:
            self.set_app_volume(app, level)


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


# App Detector

logger = logging.getLogger(__name__)


class AppDetector:
    SPECIAL_TARGETS = ["none", "master", "all_others"]

    def __init__(self, audio_controller,
                 callback: Optional[Callable[[List[str]], None]] = None,
                 interval: float = 5.0):
        self.audio    = audio_controller
        self.callback = callback
        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._paused  = False
        self._wake    = threading.Event()   # interrupts the sleep
        self._cached_apps: List[str] = []
        self._cached_procs: Set[str] = set()  # running process names (psutil)


    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True,
                                         name="AppDetector")
        self._thread.start()

    def stop(self):
        self._running = False
        self._wake.set()

    def pause(self):
        """Stop polling (window hidden - nobody is looking at the list)."""
        self._paused = True

    def resume(self):
        """Resume polling and poll immediately so the UI is fresh."""
        if self._paused:
            self._paused = False
            self._wake.set()

    def get_current_apps(self) -> List[str]:
        return list(self._cached_apps)

    def get_running_processes(self) -> Set[str]:
        """Lowercased names of running processes (empty if psutil unavailable)."""
        return set(self._cached_procs)

    def get_dropdown_values(self) -> List[str]:
        return self.SPECIAL_TARGETS + self._cached_apps


    def _loop(self):
        while self._running:
            if not self._paused:
                try:
                    apps = self.audio.get_running_audio_apps()
                    # Refresh the running-process set too (cheap, optional).
                    self._cached_procs = _running_process_names()
                    if apps != self._cached_apps:
                        self._cached_apps = apps
                        if self.callback:
                            self.callback(self.get_dropdown_values())
                except Exception as e:
                    logger.error(f"AppDetector: {e}")
            # Sleep, but wake instantly on resume()/stop()
            self._wake.wait(self.interval)
            self._wake.clear()
