"""
audio/linux_audio.py  —  pulsectl wrapper with robust error handling.

Hardening against bad potentiometer solder joints:
  * A single threading lock serialises ALL pulse access. pulsectl's
    Pulse object is NOT thread-safe, and both the serial thread and the
    app-detector thread call it — concurrent access can hard-crash
    (segfault) the whole process, which no Python try/except can catch.
  * Volume writes are de-duplicated: if the target value hasn't moved
    by a meaningful amount we skip the call, so a jittery joint sending
    hundreds of values/sec can't flood PulseAudio.
  * Every pulse call is wrapped; disconnects trigger a lazy reconnect.
"""

import logging
import threading
import time
from typing import List, Optional
from .base import AudioController

logger = logging.getLogger(__name__)

try:
    import pulsectl
    PULSECTL_AVAILABLE = True
except ImportError:
    PULSECTL_AVAILABLE = False


def _clamp(val: float) -> float:
    return max(0.0, min(1.0, val))


class LinuxAudioController(AudioController):

    RECONNECT_DELAY = 3.0    # seconds between pulse reconnect attempts
    MIN_DELTA       = 0.01   # ignore volume changes smaller than this (1%)

    def __init__(self):
        if not PULSECTL_AVAILABLE:
            raise RuntimeError("pulsectl not installed.\nRun: pip install pulsectl")
        self._pulse: Optional["pulsectl.Pulse"] = None
        # One lock guards every interaction with self._pulse.
        self._lock = threading.Lock()
        # Remember the last value we actually sent for each target so we can
        # skip redundant / jittery writes from a noisy potentiometer.
        self._last_sent: dict = {}
        self._connect()

    # ------------------------------------------------------------------ #
    # Connection management                                                #
    # ------------------------------------------------------------------ #

    def _connect(self):
        try:
            self._pulse = pulsectl.Pulse("barj-volume-controller")
            logger.info("Connected to PulseAudio/PipeWire.")
        except Exception as e:
            logger.error(f"Could not connect to PulseAudio/PipeWire: {e}")
            self._pulse = None

    def _safe(self, fn):
        """
        Run fn(pulse) under the lock, recovering from disconnects.
        Returns fn's result or None. Never raises.
        """
        with self._lock:
            for _attempt in range(2):
                if self._pulse is None:
                    self._connect()
                if self._pulse is None:
                    return None
                try:
                    return fn(self._pulse)
                except pulsectl.PulseDisconnected:
                    logger.warning("PulseAudio disconnected — will reconnect.")
                    self._pulse = None
                    time.sleep(self.RECONNECT_DELAY)
                except pulsectl.PulseOperationFailed as e:
                    logger.debug(f"PulseAudio operation failed: {e}")
                    return None
                except Exception as e:
                    logger.error(f"PulseAudio error: {e}")
                    return None
            return None

    def _changed_enough(self, key: str, level: float) -> bool:
        """True if level differs from the last sent value by >= MIN_DELTA."""
        last = self._last_sent.get(key)
        if last is not None and abs(level - last) < self.MIN_DELTA:
            return False
        self._last_sent[key] = level
        return True

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _default_sink(self, pulse) -> Optional["pulsectl.PulseSinkInfo"]:
        try:
            name = pulse.server_info().default_sink_name
            for sink in pulse.sink_list():
                if sink.name == name:
                    return sink
            sinks = pulse.sink_list()
            return sinks[0] if sinks else None
        except Exception as e:
            logger.debug(f"_default_sink: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Volume control                                                       #
    # ------------------------------------------------------------------ #

    def set_master_volume(self, level: float):
        level = _clamp(level)
        if not self._changed_enough("master", level):
            return
        def _do(pulse):
            sink = self._default_sink(pulse)
            if sink:
                pulse.volume_set_all_chans(sink, level)
        self._safe(_do)

    def get_master_volume(self) -> float:
        def _do(pulse):
            sink = self._default_sink(pulse)
            return sink.volume.value_flat if sink else 0.0
        return self._safe(_do) or 0.0

    def set_app_volume(self, process_name: str, level: float):
        level = _clamp(level)
        if not self._changed_enough(f"app:{process_name}", level):
            return
        target = process_name.lower()
        def _do(pulse):
            matched = False
            for inp in pulse.sink_input_list():
                binary   = inp.proplist.get("application.process.binary", "").lower()
                app_name = inp.proplist.get("application.name", "").lower()
                if target in binary or target in app_name:
                    pulse.volume_set_all_chans(inp, level)
                    matched = True
            if not matched:
                logger.debug(f"No audio session for '{process_name}'")
        self._safe(_do)

    def get_running_audio_apps(self) -> List[str]:
        def _do(pulse):
            apps = set()
            for inp in pulse.sink_input_list():
                name = (inp.proplist.get("application.process.binary") or
                        inp.proplist.get("application.name") or "")
                if name:
                    apps.add(name)
            return sorted(apps)
        return self._safe(_do) or []
