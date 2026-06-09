"""
Linux audio backend using pulsectl (works with PulseAudio and PipeWire-pulse).

Supports: master (default sink), mic (default source), per-app sink-inputs,
and all_others. 'system' is treated as a no-op on Linux (no separate channel).
"""

from .base import AudioBackend

try:
    import pulsectl
    _PULSE_OK = True
except Exception:
    _PULSE_OK = False


class LinuxBackend(AudioBackend):
    name = "linux"

    def __init__(self):
        if not _PULSE_OK:
            raise RuntimeError("pulsectl not available")
        self.pulse = pulsectl.Pulse("barj-volume-controller")

    def _app_key(self, sink_input):
        # Prefer the application.process.binary, fall back to app name
        props = sink_input.proplist
        binary = props.get("application.process.binary")
        name = props.get("application.name") or sink_input.name or "unknown"
        key = (binary or name).lower()
        return key, (name or binary or "Unknown")

    def list_sessions(self):
        out = []
        seen = set()
        try:
            for si in self.pulse.sink_input_list():
                key, label = self._app_key(si)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"id": key, "label": label, "pid": None})
        except Exception:
            pass
        return out

    def set_volume(self, target, level):
        level = max(0.0, min(1.0, level))
        try:
            if target == "master":
                sink = self.pulse.get_sink_by_name(self.pulse.server_info().default_sink_name)
                self.pulse.volume_set_all_chans(sink, level)
            elif target == "mic":
                src = self.pulse.get_source_by_name(self.pulse.server_info().default_source_name)
                self.pulse.volume_set_all_chans(src, level)
            elif target == "system":
                pass  # no dedicated system-sounds channel on Linux
            else:
                for si in self.pulse.sink_input_list():
                    key, _ = self._app_key(si)
                    if key == target.lower():
                        self.pulse.volume_set_all_chans(si, level)
        except Exception:
            pass

    def set_all_others(self, level, mapped_ids):
        level = max(0.0, min(1.0, level))
        mapped = {m.lower() for m in mapped_ids}
        try:
            for si in self.pulse.sink_input_list():
                key, _ = self._app_key(si)
                if key not in mapped:
                    self.pulse.volume_set_all_chans(si, level)
        except Exception:
            pass

    def cleanup(self):
        try:
            self.pulse.close()
        except Exception:
            pass
