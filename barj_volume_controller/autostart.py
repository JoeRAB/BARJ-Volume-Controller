"""
Cross-platform "launch on startup" management.

Modes: 'open' (normal window), 'minimized' (start minimized),
       'tray' (start hidden in system tray).

The chosen mode is passed to the app via a CLI flag:
  --startup-mode open|minimized|tray

Implementations:
  - Linux:   ~/.config/autostart/barj.desktop (XDG autostart)
  - macOS:   ~/Library/LaunchAgents/com.barj.volumecontroller.plist
  - Windows: HKCU Run registry key
"""

import os
import sys
import subprocess


APP_ID = "BARJ"
LABEL = "com.barj.volumecontroller"


def _launch_command(mode):
    """Command used to start the app at login, with the chosen mode."""
    exe = sys.executable
    # When frozen (PyInstaller) sys.argv[0] is the app; otherwise run module.
    if getattr(sys, "frozen", False):
        return [exe, "--startup-mode", mode]
    script = os.path.abspath(sys.argv[0])
    return [exe, script, "--startup-mode", mode]


# ---------------- Linux ----------------
def _linux_path():
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "autostart", "barj.desktop")


def _linux_set(enabled, mode):
    path = _linux_path()
    if not enabled:
        if os.path.exists(path):
            os.remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cmd = " ".join(_launch_command(mode))
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=BARJ Volume Controller\n"
            f"Exec={cmd}\n"
            "X-GNOME-Autostart-enabled=true\n"
            "Terminal=false\n"
        )


# ---------------- macOS ----------------
def _macos_path():
    return os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")


def _macos_set(enabled, mode):
    path = _macos_path()
    if not enabled:
        if os.path.exists(path):
            subprocess.run(["launchctl", "unload", path], check=False)
            os.remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    args = "".join(f"        <string>{a}</string>\n" for a in _launch_command(mode))
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0"><dict>\n'
            f"    <key>Label</key><string>{LABEL}</string>\n"
            "    <key>ProgramArguments</key><array>\n"
            f"{args}"
            "    </array>\n"
            "    <key>RunAtLoad</key><true/>\n"
            "</dict></plist>\n"
        )
    subprocess.run(["launchctl", "load", path], check=False)


# ---------------- Windows ----------------
def _windows_set(enabled, mode):
    import winreg
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE,
    )
    try:
        if enabled:
            cmd = " ".join(f'"{a}"' if " " in a else a for a in _launch_command(mode))
            winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_ID)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def set_autostart(enabled, mode="open"):
    if sys.platform.startswith("win"):
        _windows_set(enabled, mode)
    elif sys.platform == "darwin":
        _macos_set(enabled, mode)
    else:
        _linux_set(enabled, mode)
