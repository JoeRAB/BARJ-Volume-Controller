"""
app_detector.py
Polls audio controller for running apps every N seconds.
Polling pauses while the window is minimized to the tray and resumes
(with an immediate poll) when it's shown again.

Special targets (always at top of every dropdown):
  none       — slider controls nothing (may be assigned to many sliders)
  master     — system master volume
  all_others — any running app NOT explicitly assigned to another slider
"""

import threading
import logging
from typing import Callable, List, Optional

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

    # ------------------------------------------------------------------ #

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True,
                                         name="AppDetector")
        self._thread.start()

    def stop(self):
        self._running = False
        self._wake.set()

    def pause(self):
        """Stop polling (window hidden — nobody is looking at the list)."""
        self._paused = True

    def resume(self):
        """Resume polling and poll immediately so the UI is fresh."""
        if self._paused:
            self._paused = False
            self._wake.set()

    def get_current_apps(self) -> List[str]:
        return list(self._cached_apps)

    def get_dropdown_values(self) -> List[str]:
        return self.SPECIAL_TARGETS + self._cached_apps

    # ------------------------------------------------------------------ #

    def _loop(self):
        while self._running:
            if not self._paused:
                try:
                    apps = self.audio.get_running_audio_apps()
                    if apps != self._cached_apps:
                        self._cached_apps = apps
                        if self.callback:
                            self.callback(self.get_dropdown_values())
                except Exception as e:
                    logger.error(f"AppDetector: {e}")
            # Sleep, but wake instantly on resume()/stop()
            self._wake.wait(self.interval)
            self._wake.clear()
