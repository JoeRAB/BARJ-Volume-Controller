"""
pulsectl wrapper with robust error handling.

  * A single threading lock serialises ALL pulse access. pulsectl's
    Pulse object is NOT thread-safe, and both the serial thread and the
    app-detector thread call it - concurrent access can hard-crash
    (segfault) the whole process, which no Python try/except can catch.
  * Volume is applied on every serial frame (no de-duplication), so a
    newly-created stream (e.g. the next video) is brought to the slider's
    level within one frame. Each sink_input_list() call reads live.
  * Every pulse call is wrapped; disconnects trigger a lazy reconnect.
"""

import logging
import threading
import time
from typing import List, Optional
from . import AudioController

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
    SINK_CACHE_TTL  = 5.0    # seconds to trust the cached default-sink name

    def __init__(self):
        if not PULSECTL_AVAILABLE:
            raise RuntimeError("pulsectl not installed.\nRun: pip install pulsectl")
        self._pulse: Optional["pulsectl.Pulse"] = None
        # One lock guards every interaction with self._pulse.
        self._lock = threading.Lock()
        # Cache the default sink NAME to skip server_info round trips at
        # knob-turn rate. Refreshed every SINK_CACHE_TTL seconds. (This caches
        # only the sink *name*, not the stream list, so it doesn't affect how
        # quickly new streams are picked up.)
        self._sink_name_cache: Optional[str] = None
        self._sink_cache_time: float = 0.0
        self._connect()

    # Connection management                                                #

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
                    logger.warning("PulseAudio disconnected - will reconnect.")
                    self._pulse = None
                    time.sleep(self.RECONNECT_DELAY)
                except pulsectl.PulseOperationFailed as e:
                    logger.debug(f"PulseAudio operation failed: {e}")
                    return None
                except Exception as e:
                    logger.error(f"PulseAudio error: {e}")
                    return None
            return None

    # Helpers                                                              #

    def _default_sink(self, pulse) -> Optional["pulsectl.PulseSinkInfo"]:
        try:
            now = time.time()
            # Use the cached sink name when fresh; one sink_list call is
            # still needed to get a live object, but we skip server_info.
            if (self._sink_name_cache is None or
                    now - self._sink_cache_time > self.SINK_CACHE_TTL):
                self._sink_name_cache = pulse.server_info().default_sink_name
                self._sink_cache_time = now

            sinks = pulse.sink_list()
            for sink in sinks:
                if sink.name == self._sink_name_cache:
                    return sink
            # Cached name no longer exists (device changed) - refresh now
            self._sink_name_cache = pulse.server_info().default_sink_name
            self._sink_cache_time = now
            for sink in sinks:
                if sink.name == self._sink_name_cache:
                    return sink
            return sinks[0] if sinks else None
        except Exception as e:
            logger.debug(f"_default_sink: {e}")
            return None

    # Sink-input matching                                                  #

    @staticmethod
    def _input_names(inp) -> tuple:
        """(process_binary, application_name) for a sink input, lower-cased."""
        return (inp.proplist.get("application.process.binary", "").lower(),
                inp.proplist.get("application.name", "").lower())

    @classmethod
    def _input_matches(cls, inp, target: str) -> bool:
        """True if `target` (lower-cased) is a substring of the input's process
        binary or application name. The shared rule used by every app match."""
        binary, app_name = cls._input_names(inp)
        return target in binary or target in app_name

    @staticmethod
    def _input_display_name(inp) -> str:
        """The name to SHOW for a sink input, in its original case: the process
        binary if present, else the application name, else empty. (Distinct from
        _input_names, which lower-cases for matching.)"""
        return (inp.proplist.get("application.process.binary") or
                inp.proplist.get("application.name") or "")

    # Volume control                                                       #

    def set_master_volume(self, level: float):
        level = _clamp(level)
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
        target = process_name.lower()
        def _do(pulse):
            matched = False
            for inp in pulse.sink_input_list():
                if self._input_matches(inp, target):
                    pulse.volume_set_all_chans(inp, level)
                    matched = True
            if not matched:
                logger.debug(f"No audio session for '{process_name}'")
        self._safe(_do)

    def set_all_others_volume(self, level: float, exclude):
        """
        Set volume on every sink input NOT matching any excluded target.
        Matching mirrors set_app_volume (see _input_matches).
        """
        level = _clamp(level)
        excl = {e.strip().lower() for e in exclude if e and e.strip()}

        def _do(pulse):
            for inp in pulse.sink_input_list():
                if any(self._input_matches(inp, t) for t in excl):
                    continue   # owned by another slider
                pulse.volume_set_all_chans(inp, level)
        self._safe(_do)

    def get_running_audio_apps(self) -> List[str]:
        def _do(pulse):
            apps = set()
            for inp in pulse.sink_input_list():
                name = self._input_display_name(inp)
                if name:
                    apps.add(name)
            return sorted(apps)
        return self._safe(_do) or []
