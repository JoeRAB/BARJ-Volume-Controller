"""
audio/__init__.py
Auto-selects the correct AudioController for the running OS.
"""

import platform
import logging
from .base import AudioController

logger = logging.getLogger(__name__)


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
