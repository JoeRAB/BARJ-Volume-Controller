"""
manage launch-on-login for BARJ Volume Controller.

Linux:   writes/removes ~/.config/autostart/barj-volume-controller.desktop
Windows: writes/removes an HKCU Run registry value
macOS:   not implemented (returns False)

The functions are best-effort: they return True on success, False otherwise,
and never raise, so a failure to toggle autostart can't crash the app.
"""

import logging
import os
import platform
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_SYSTEM = platform.system()
_APP_NAME = "BARJ Volume Controller"
_AUTOSTART_ID = "barj-volume-controller"


def _launch_command() -> str:
    """Best-effort command that re-launches this app for start-on-login.

    Always includes --minimized so a boot launch can start hidden in the tray
    (the app only honours that flag when start-minimized is also enabled in
    settings). Prefers the installed launcher on Linux; otherwise falls back to
    'python3 /path/to/main.py' (or the frozen exe path under PyInstaller).
    """
    # PyInstaller frozen build: sys.executable IS the app
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'

    if _SYSTEM == "Linux":
        launcher = Path.home() / ".local" / "bin" / _AUTOSTART_ID
        if launcher.exists():
            return f'{launcher} --minimized'

    # Fallback: run main.py with the current interpreter
    main_py = Path(__file__).resolve().parent / "main.py"
    return f'"{sys.executable}" "{main_py}" --minimized'


# ── Linux ─────────────────────────────────────────────────────────────────────

def _linux_desktop_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / f"{_AUTOSTART_ID}.desktop"


def _linux_enable() -> bool:
    path = _linux_desktop_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={_APP_NAME}\n"
        f"Exec={_launch_command()}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "Categories=AudioVideo;Audio;Mixer;\n"
    )
    path.write_text(content)
    return True


def _linux_disable() -> bool:
    path = _linux_desktop_path()
    if path.exists():
        path.unlink()
    return True


def _linux_is_enabled() -> bool:
    return _linux_desktop_path().exists()


# ── Windows ─────────────────────────────────────────────────────────────────

_WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _win_enable() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0,
                        winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, _APP_NAME, 0, winreg.REG_SZ, _launch_command())
    return True


def _win_disable() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, _APP_NAME)
    except FileNotFoundError:
        pass   # value wasn't set - already "disabled"
    return True


def _win_is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY) as k:
            winreg.QueryValueEx(k, _APP_NAME)
        return True
    except FileNotFoundError:
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def set_start_on_login(enabled: bool) -> bool:
    """Enable or disable launch-on-login. Returns True on success."""
    try:
        if _SYSTEM == "Linux":
            return _linux_enable() if enabled else _linux_disable()
        if _SYSTEM == "Windows":
            return _win_enable() if enabled else _win_disable()
        logger.info("start-on-login not supported on this platform.")
        return False
    except Exception as e:
        logger.warning(f"Could not change start-on-login: {e}")
        return False


def is_start_on_login_enabled() -> bool:
    """Return True if an autostart entry currently exists."""
    try:
        if _SYSTEM == "Linux":
            return _linux_is_enabled()
        if _SYSTEM == "Windows":
            return _win_is_enabled()
        return False
    except Exception:
        return False
