"""
app_detector.py
Polls the audio controller for running apps every N seconds.
'mic' removed from special targets.
"""

import threading
import time
import logging
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class AppDetector:
    SPECIAL_TARGETS = ["master"]   # mic removed

    def __init__(self, audio_controller, callback: Optional[Callable[[List[str]], None]] = None,
                 interval: float = 5.0):
        self.audio     = audio_controller
        self.callback  = callback
        self.interval  = interval
        self._thread: Optional[threading.Thread] = None
        self._running  = False
        self._cached_apps: List[str] = []

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True, name="AppDetector")
        self._thread.start()

    def stop(self):
        self._running = False

    def get_current_apps(self) -> List[str]:
        return list(self._cached_apps)

    def get_dropdown_values(self) -> List[str]:
        return self.SPECIAL_TARGETS + self._cached_apps

    def _loop(self):
        while self._running:
            try:
                apps = self.audio.get_running_audio_apps()
                if apps != self._cached_apps:
                    self._cached_apps = apps
                    if self.callback:
                        self.callback(self.get_dropdown_values())
            except Exception as e:
                logger.error(f"AppDetector: {e}")
            time.sleep(self.interval)
