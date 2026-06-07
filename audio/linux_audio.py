"""
audio/linux_audio.py
Linux audio controller using pulsectl.
Works with PulseAudio and PipeWire (via PulseAudio compatibility layer).

Install:  pip install pulsectl
"""

import logging
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

    def __init__(self):
        if not PULSECTL_AVAILABLE:
            raise RuntimeError("pulsectl not installed.\nRun: pip install pulsectl")
        self._pulse = pulsectl.Pulse("volume-mixer")

    def _default_sink(self) -> Optional["pulsectl.PulseSinkInfo"]:
        try:
            name = self._pulse.server_info().default_sink_name
            for sink in self._pulse.sink_list():
                if sink.name == name:
                    return sink
            sinks = self._pulse.sink_list()
            return sinks[0] if sinks else None
        except Exception as e:
            logger.error(f"_default_sink: {e}")
            return None

    def set_master_volume(self, level: float):
        try:
            sink = self._default_sink()
            if sink:
                self._pulse.volume_set_all_chans(sink, _clamp(level))
        except Exception as e:
            logger.error(f"set_master_volume: {e}")

    def get_master_volume(self) -> float:
        try:
            sink = self._default_sink()
            if sink:
                return sink.volume.value_flat
        except Exception as e:
            logger.error(f"get_master_volume: {e}")
        return 0.0

    def set_app_volume(self, process_name: str, level: float):
        target = process_name.lower()
        try:
            for inp in self._pulse.sink_input_list():
                binary   = inp.proplist.get("application.process.binary", "").lower()
                app_name = inp.proplist.get("application.name", "").lower()
                if target in binary or target in app_name:
                    self._pulse.volume_set_all_chans(inp, _clamp(level))
        except Exception as e:
            logger.error(f"set_app_volume({process_name}): {e}")

    def get_running_audio_apps(self) -> List[str]:
        apps = set()
        try:
            for inp in self._pulse.sink_input_list():
                name = inp.proplist.get("application.process.binary", "") or \
                       inp.proplist.get("application.name", "")
                if name:
                    apps.add(name)
        except Exception as e:
            logger.error(f"get_running_audio_apps: {e}")
        return sorted(apps)
