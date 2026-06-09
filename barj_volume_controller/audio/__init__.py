"""
Audio backend abstraction for BARJ Volume Controller.

Selects the correct platform-specific implementation:
  - Windows -> pycaw (per-app + master + mic + system + unmapped)
  - Linux   -> pulsectl (PulseAudio / PipeWire-pulse)
  - macOS   -> system master via osascript, per-app best-effort

Every backend exposes the same interface (see base.AudioBackend).
"""

import sys


def get_backend():
    """Return an instantiated AudioBackend for the current OS."""
    if sys.platform.startswith("win"):
        from .windows_backend import WindowsBackend
        return WindowsBackend()
    elif sys.platform.startswith("linux"):
        from .linux_backend import LinuxBackend
        return LinuxBackend()
    elif sys.platform == "darwin":
        from .macos_backend import MacOSBackend
        return MacOSBackend()
    else:
        from .base import AudioBackend
        return AudioBackend()  # no-op fallback


# Special target identifiers shared across the app
MASTER = "master"
MIC = "mic"
SYSTEM = "system"
ALL_OTHERS = "all_others"   # everything not explicitly mapped
