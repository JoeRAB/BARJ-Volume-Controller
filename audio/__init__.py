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
    def set_master_volume(self, level: float, force: bool = False, ramp=None):
        """Set the default playback device volume. level is 0.0–1.0.
        force=True writes even if unchanged (used by authoritative sliders)."""

    @abstractmethod
    def get_master_volume(self) -> float:
        """Return current master volume as 0.0–1.0."""

    @abstractmethod
    def set_app_volume(self, process_name: str, level: float,
                       force: bool = False, ramp=None):
        """Set volume for all audio sessions belonging to process_name.
        force=True writes even if unchanged (used by authoritative sliders).
        ramp, if given, is the max volume change per call: instead of jumping to
        `level`, step the stream's current volume toward it by at most `ramp`, so
        an authoritative correction glides in rather than spiking."""

    @abstractmethod
    def set_all_others_volume(self, level: float, exclude: Set[str],
                              force: bool = False, ramp=None):
        """
        Set volume on every running audio app whose name does NOT match
        any entry in `exclude` (the targets assigned to other sliders).
        Matching must mirror set_app_volume's matching rules.
        force=True writes even if unchanged; ramp eases the change in (see
        set_app_volume).
        """

    @abstractmethod
    def get_running_audio_apps(self) -> List[str]:
        """Return sorted list of process names currently producing audio."""

    def apply_slider(self, target, level: float,
                     exclude: Optional[Set[str]] = None,
                     force: bool = False, ramp=None):
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

        `force` (authoritative slider) makes the backend write the volume even
        if it matches what we last set, so external changes (e.g. Firefox tying
        YouTube's slider to the stream volume) get overridden each tick. `ramp`
        eases those corrections in gradually instead of jumping (see
        set_app_volume) so dragging a browser slider fades rather than spikes.
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
                self.set_master_volume(level, force=force, ramp=ramp)
                return
            if t == "all_others":
                self.set_all_others_volume(level, exclude or set(),
                                           force=force, ramp=ramp)
                return
            targets = [target]
        else:
            targets = [a for a in target if a and a.strip()]

        for app in targets:
            self.set_app_volume(app, level, force=force, ramp=ramp)

    def current_input_ids(self):
        """Return a set of identifiers for the audio streams currently playing,
        used by the GUI to spot a brand-new stream (e.g. an unpaused video) and
        bring it to its slider's level immediately rather than on the slower
        periodic sweep.

        Return None if the backend can't enumerate streams cheaply; callers then
        fall back to the periodic sweep. The default is None (unsupported)."""
        return None


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
                 interval: float = 5.0,
                 state_callback: Optional[Callable[[], None]] = None):
        self.audio    = audio_controller
        self.callback = callback
        # Called (no args) when only the running-process set changed, so the UI
        # can re-evaluate active/silent/inactive without a full dropdown rebuild.
        self.state_callback = state_callback
        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._paused  = False
        self._wake    = threading.Event()   # interrupts the sleep
        self._cached_apps: List[str] = []     # apps currently producing audio
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
                    # Refresh the running-process set too (cheap). Used only to
                    # tell "running but silent" apart from "not running" in the
                    # per-slider status - NOT for the assignment list, which only
                    # offers apps currently making sound.
                    new_procs = _running_process_names()
                    procs_changed = new_procs != self._cached_procs
                    self._cached_procs = new_procs
                    apps_changed = apps != self._cached_apps
                    if apps_changed:
                        self._cached_apps = apps

                    # Rebuild the dropdowns when the audio-app list changes (an
                    # app started/stopped making sound). Otherwise, if only the
                    # process set changed, just re-evaluate the status dots.
                    if apps_changed and self.callback:
                        self.callback(self.get_dropdown_values())
                    elif procs_changed and self.state_callback:
                        self.state_callback()
                except Exception as e:
                    logger.error(f"AppDetector: {e}")
            # Sleep, but wake instantly on resume()/stop()
            self._wake.wait(self.interval)
            self._wake.clear()
