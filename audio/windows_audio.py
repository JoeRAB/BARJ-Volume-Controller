"""
Windows audio controller using pycaw (Windows Core Audio API).

Performance notes:
  - The endpoint-volume COM interface is created once and reused
    (refreshed automatically if a call fails, e.g. device change).
  - Audio sessions are cached for SESSION_CACHE_TTL seconds because
    GetAllSessions() is an expensive COM enumeration. The cache is short
    so a newly-started stream is picked up quickly.

Install:  pip install pycaw comtypes
"""

import logging
import time
from typing import List, Set
from . import AudioController

logger = logging.getLogger(__name__)

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, ISimpleAudioVolume  # type: ignore
    from comtypes import CLSCTX_ALL  # type: ignore
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False


def _clamp(val: float) -> float:
    return max(0.0, min(1.0, val))


class WindowsAudioController(AudioController):

    SESSION_CACHE_TTL = 1.0    # seconds to reuse the session list

    def __init__(self):
        if not PYCAW_AVAILABLE:
            raise RuntimeError("pycaw / comtypes not installed.\nRun: pip install pycaw comtypes")
        self._endpoint = None            # cached IAudioEndpointVolume
        self._sessions = []              # cached session list
        self._sessions_time = 0.0

    # Helpers                                                              #

    def _get_endpoint(self):
        """Cached endpoint-volume interface; rebuilt on demand."""
        if self._endpoint is None:
            speakers = AudioUtilities.GetSpeakers()
            interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self._endpoint = interface.QueryInterface(IAudioEndpointVolume)
        return self._endpoint

    def _get_sessions(self, force: bool = False):
        """Session list, cached briefly - enumeration is expensive COM."""
        now = time.time()
        if force or not self._sessions or now - self._sessions_time > self.SESSION_CACHE_TTL:
            self._sessions = AudioUtilities.GetAllSessions()
            self._sessions_time = now
        return self._sessions

    # Master                                                               #

    def set_master_volume(self, level: float):
        level = _clamp(level)
        try:
            self._get_endpoint().SetMasterVolumeLevelScalar(level, None)
        except Exception as e:
            # Device may have changed - drop the cache and retry once
            logger.debug(f"set_master_volume retry: {e}")
            self._endpoint = None
            try:
                self._get_endpoint().SetMasterVolumeLevelScalar(level, None)
            except Exception as e2:
                logger.error(f"set_master_volume: {e2}")

    def get_master_volume(self) -> float:
        try:
            return self._get_endpoint().GetMasterVolumeLevelScalar()
        except Exception:
            self._endpoint = None
            try:
                return self._get_endpoint().GetMasterVolumeLevelScalar()
            except Exception as e:
                logger.error(f"get_master_volume: {e}")
                return 0.0

    # Per-app                                                              #

    @staticmethod
    def _session_name(session) -> str:
        try:
            return session.Process.name().lower() if session.Process else ""
        except Exception:
            return ""

    def set_app_volume(self, process_name: str, level: float):
        level = _clamp(level)
        target = process_name.lower()
        try:
            for session in self._get_sessions():
                name = self._session_name(session)
                if name and target in name:
                    try:
                        session._ctl.QueryInterface(ISimpleAudioVolume) \
                                    .SetMasterVolume(level, None)
                    except Exception:
                        # Stale cached session (app closed) - refresh and move on
                        self._get_sessions(force=True)
        except Exception as e:
            logger.error(f"set_app_volume({process_name}): {e}")

    def set_all_others_volume(self, level: float, exclude: Set[str]):
        """
        Set volume on every session NOT matching any excluded target.
        Matching mirrors set_app_volume: case-insensitive substring of
        the process name.
        """
        level = _clamp(level)
        excl = {e.strip().lower() for e in exclude if e and e.strip()}
        try:
            for session in self._get_sessions():
                name = self._session_name(session)
                if not name:
                    continue
                if any(t in name for t in excl):
                    continue   # owned by another slider
                try:
                    session._ctl.QueryInterface(ISimpleAudioVolume) \
                                .SetMasterVolume(level, None)
                except Exception:
                    self._get_sessions(force=True)
        except Exception as e:
            logger.error(f"set_all_others_volume: {e}")

    # Discovery                                                            #

    def get_running_audio_apps(self) -> List[str]:
        apps = set()
        try:
            for session in self._get_sessions(force=True):
                if session.Process:
                    apps.add(session.Process.name())
        except Exception as e:
            logger.error(f"get_running_audio_apps: {e}")
        return sorted(apps)
