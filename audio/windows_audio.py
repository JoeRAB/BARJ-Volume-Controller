"""
audio/windows_audio.py
Windows audio controller using pycaw (Windows Core Audio API).

Install:  pip install pycaw comtypes
"""

import logging
from typing import List
from .base import AudioController

logger = logging.getLogger(__name__)

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, ISimpleAudioVolume
    from comtypes import CLSCTX_ALL
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False


def _clamp(val: float) -> float:
    return max(0.0, min(1.0, val))


class WindowsAudioController(AudioController):

    def __init__(self):
        if not PYCAW_AVAILABLE:
            raise RuntimeError("pycaw / comtypes not installed.\nRun: pip install pycaw comtypes")

    def _get_endpoint_volume(self):
        speakers = AudioUtilities.GetSpeakers()
        interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return interface.QueryInterface(IAudioEndpointVolume)

    def set_master_volume(self, level: float):
        try:
            self._get_endpoint_volume().SetMasterVolumeLevelScalar(_clamp(level), None)
        except Exception as e:
            logger.error(f"set_master_volume: {e}")

    def get_master_volume(self) -> float:
        try:
            return self._get_endpoint_volume().GetMasterVolumeLevelScalar()
        except Exception as e:
            logger.error(f"get_master_volume: {e}")
            return 0.0

    def set_app_volume(self, process_name: str, level: float):
        target = process_name.lower()
        try:
            for session in AudioUtilities.GetAllSessions():
                if session.Process and session.Process.name().lower() == target:
                    session._ctl.QueryInterface(ISimpleAudioVolume).SetMasterVolume(_clamp(level), None)
        except Exception as e:
            logger.error(f"set_app_volume({process_name}): {e}")

    def get_running_audio_apps(self) -> List[str]:
        apps = set()
        try:
            for session in AudioUtilities.GetAllSessions():
                if session.Process:
                    apps.add(session.Process.name())
        except Exception as e:
            logger.error(f"get_running_audio_apps: {e}")
        return sorted(apps)
