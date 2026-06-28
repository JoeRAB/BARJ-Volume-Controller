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
    def set_master_volume(self, level: float, force: bool = False):
        """Set the default playback device volume. level is 0.0–1.0."""

    @abstractmethod
    def get_master_volume(self) -> float:
        """Return current master volume as 0.0–1.0."""

    @abstractmethod
    def set_app_volume(self, process_name: str, level: float, force: bool = False):
        """Set volume for all audio sessions belonging to process_name."""

    @abstractmethod
    def set_all_others_volume(self, level: float, exclude: Set[str],
                              force: bool = False):
        """
        Set volume on every running audio app whose name does NOT match
        any entry in `exclude` (the targets assigned to other sliders).
        Matching must mirror set_app_volume's matching rules.
        """

    @abstractmethod
    def get_running_audio_apps(self) -> List[str]:
        """Return sorted list of process names currently producing audio."""

    def get_stream_count(self) -> int:
        """Number of active audio streams/sessions. Changes when a new stream
        appears even if it belongs to an app already in the list (e.g. the next
        video in the same browser). Backends override; default returns 0."""
        return 0

    def apply_slider(self, target, level: float,
                     exclude: Optional[Set[str]] = None, force: bool = False):
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

        `force` re-applies the level even if it hasn't changed since last time,
        and refreshes the backend's stream list first. Used when a NEW audio
        stream appears (e.g. the next video) so it inherits the slider position
        instead of playing at the OS default volume.
        """
        if not target:
            return

        if force:
            self.invalidate_stream_cache()

        # Normalise to a list for uniform handling. Special keywords only ever
        # appear as a lone string (the UI forbids mixing them with apps).
        if isinstance(target, str):
            t = target.strip().lower()
            if t == "none":
                return          # explicit "controls nothing" assignment
            if t == "master":
                self.set_master_volume(level, force=force)
                return
            if t == "all_others":
                self.set_all_others_volume(level, exclude or set(), force=force)
                return
            targets = [target]
        else:
            targets = [a for a in target if a and a.strip()]

        for app in targets:
            self.set_app_volume(app, level, force=force)

    def invalidate_stream_cache(self):
        """Drop any cached audio-stream list so the next call re-enumerates.
        Backends that cache stream lists override this; the default is a no-op."""
        pass


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
        self._cached_stream_count: int = 0    # active audio stream count


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
                    # This is only used to tell "running but silent" apart from
                    # "not running" in the per-slider status - NOT for the
                    # assignment list, which only offers apps making sound.
                    new_procs = _running_process_names()
                    procs_changed = new_procs != self._cached_procs
                    self._cached_procs = new_procs
                    apps_changed = apps != self._cached_apps
                    if apps_changed:
                        self._cached_apps = apps

                    # Stream count changes when a NEW stream appears even under
                    # an app already in the list (e.g. the next YouTube video in
                    # the same browser). The app-name list wouldn't change in
                    # that case, so we watch the count to still trigger a volume
                    # re-apply for the new stream.
                    try:
                        new_count = self.audio.get_stream_count()
                    except Exception:
                        new_count = self._cached_stream_count
                    count_changed = new_count != self._cached_stream_count
                    self._cached_stream_count = new_count

                    # Rebuild the dropdowns when the audio-app list changes (an
                    # app started/stopped making sound). Otherwise, if only the
                    # process set or the stream count changed, fire the lighter
                    # state callback (re-evaluate states + re-apply volume).
                    if apps_changed and self.callback:
                        self.callback(self.get_dropdown_values())
                    elif (procs_changed or count_changed) and self.state_callback:
                        self.state_callback()
                except Exception as e:
                    logger.error(f"AppDetector: {e}")
            # Sleep, but wake instantly on resume()/stop()
            self._wake.wait(self.interval)
            self._wake.clear()
