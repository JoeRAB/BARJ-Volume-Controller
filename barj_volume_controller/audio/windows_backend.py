"""
Windows audio backend using pycaw + comtypes.

Supports: master, mic, system sounds, per-app sessions, and all_others.
"""

from .base import AudioBackend

try:
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import (
        AudioUtilities,
        IAudioEndpointVolume,
        ISimpleAudioVolume,
    )
    _PYCAW_OK = True
except Exception:
    _PYCAW_OK = False


class WindowsBackend(AudioBackend):
    name = "windows"

    def __init__(self):
        if not _PYCAW_OK:
            raise RuntimeError("pycaw/comtypes not available")

    # ---- endpoints ---------------------------------------------------------
    def _master_endpoint(self):
        devices = AudioUtilities.GetSpeakers()
        iface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(iface, POINTER(IAudioEndpointVolume))

    def _mic_endpoint(self):
        devices = AudioUtilities.GetMicrophone()
        iface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(iface, POINTER(IAudioEndpointVolume))

    # ---- sessions ----------------------------------------------------------
    def list_sessions(self):
        out = []
        seen = set()
        for s in AudioUtilities.GetAllSessions():
            if s.Process and s.Process.name():
                name = s.Process.name()
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                label = name
                try:
                    if s.DisplayName:
                        label = s.DisplayName
                except Exception:
                    pass
                out.append({"id": key, "label": label, "pid": s.Process.pid})
        return out

    def _app_sessions(self, app_id):
        result = []
        for s in AudioUtilities.GetAllSessions():
            if s.Process and s.Process.name().lower() == app_id.lower():
                vol = s._ctl.QueryInterface(ISimpleAudioVolume)
                result.append(vol)
        return result

    # ---- volume setters ----------------------------------------------------
    def set_volume(self, target, level):
        level = max(0.0, min(1.0, level))
        if target == "master":
            self._master_endpoint().SetMasterVolumeLevelScalar(level, None)
        elif target == "mic":
            self._mic_endpoint().SetMasterVolumeLevelScalar(level, None)
        elif target == "system":
            for s in AudioUtilities.GetAllSessions():
                if s.Process is None:  # system sounds session
                    vol = s._ctl.QueryInterface(ISimpleAudioVolume)
                    vol.SetMasterVolume(level, None)
        else:
            for vol in self._app_sessions(target):
                vol.SetMasterVolume(level, None)

    def set_all_others(self, level, mapped_ids):
        level = max(0.0, min(1.0, level))
        mapped = {m.lower() for m in mapped_ids}
        for s in AudioUtilities.GetAllSessions():
            if s.Process and s.Process.name().lower() not in mapped:
                vol = s._ctl.QueryInterface(ISimpleAudioVolume)
                vol.SetMasterVolume(level, None)
