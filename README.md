# 🎚 BARJ Volume Controller

A hardware volume controller for **Windows** and **Linux**, driven by an Arduino
with potentiometers. Compatible with standard deej wiring.

---

## Install on Linux

**One command** — clones the repo and runs the installer:

```bash
git clone https://github.com/JoeRAB/BARJ-Volume-Controller.git ~/barj-vc \
  && cd ~/barj-vc && chmod +x install_linux.sh && ./install_linux.sh
```

The installer works on any distro with a supported package manager:
`apt` · `dnf` · `pacman` · `zypper`

**To update** — re-run the installer. Your config and profiles are safe:

```bash
cd ~/barj-vc && git pull && ./install_linux.sh
```

> **Config is stored at `~/.config/barj-volume-controller/config.yaml`** —
> completely separate from the install directory and never modified by the installer.

---

## Install on Windows

### Option A — Run from source (Python 3.10+ required)

```powershell
git clone https://github.com/JoeRAB/BARJ-Volume-Controller.git
cd barj-volume-controller
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # first time only
.\install_windows.ps1
```

### Option B — Standalone EXE (no Python needed)

Download `barj-volume-controller.exe` from the
[Releases](https://github.com/JoeRAB/BARJ-Volume-Controller/releases) page.

**Build the EXE yourself:**

```powershell
.\build_windows.ps1
# Output: dist\barj-volume-controller.exe
#         dist\barj-volume-controller-debug.exe
```

---

## Hardware

- Arduino (Uno, Nano, Mega, etc.)
- 1–12 potentiometers (10 kΩ recommended)

**Wire each pot:**

```
Left pin  (GND)   →  Arduino GND
Middle    (wiper) →  A0, A1, A2, …
Right pin (5V)    →  Arduino 5V
```

Upload `arduino/volume_mixer.ino` to your board. Set `NUM_SLIDERS` to match
your pot count if different from 5.

---

## First-time setup

1. Open **⚙ Settings**, select your serial port, click **Save**
   - Linux: `/dev/ttyACM0` or `/dev/ttyUSB0`
   - Windows: `COM3`, `COM4`, etc.
2. Assign each slider in the dropdown
   - `master` → system volume
   - Any other name → per-app volume (`firefox`, `spotify`, `chrome.exe`, …)
3. Apps playing audio appear in the dropdown automatically

---

## Dependency check

On startup, BARJ Volume Controller checks all required and optional
dependencies and shows a status panel if anything is missing, with
copy-paste fix commands so you know exactly what to run.

---

## Debug mode

```bash
barj-volume-controller --debug
```

Prints every Arduino tick to the terminal:

```
[DEBUG] raw=[  512 |  255 |  768 |    0 | 1023 ]  smoothed=[ ... ]  norm=[ ... ]
```

---

## Config file

Stored at `~/.config/barj-volume-controller/config.yaml` (Linux) or
`%APPDATA%\BARJ Volume Controller\config.yaml` (Windows). Never deleted by
updates or reinstalls.

```yaml
serial:
  port: /dev/ttyACM0
  baud_rate: 9600
sliders:
  count: 5
  smoothing: 0.15
profiles:
  Default:
    - {target: master, label: Master}
    - {target: firefox, label: Firefox}
    - {target: '', label: Slider 3}
    - {target: '', label: Slider 4}
    - {target: '', label: Slider 5}
current_profile: Default
```

---

## Project structure

```
barj-volume-controller/
├── arduino/
│   └── volume_mixer.ino         Arduino sketch
├── audio/
│   ├── __init__.py              Platform auto-detect
│   ├── base.py                  Abstract AudioController
│   ├── windows_audio.py         pycaw (Windows Core Audio)
│   └── linux_audio.py           pulsectl (PulseAudio / PipeWire)
├── gui/
│   ├── dependency_check.py      Startup dep checker + status panel
│   ├── main_window.py           Main window
│   ├── slider_panel.py          VU meter widget
│   └── settings_dialog.py       Settings modal
├── app_detector.py              Background audio-app polling
├── config_manager.py            XDG/APPDATA config (update-safe)
├── serial_reader.py             Serial comms + EMA smoothing
├── tray_icon.py                 System tray icon
├── main.py                      Entry point (--debug)
├── barj_vc.spec                 PyInstaller spec
├── build_windows.ps1            Windows EXE build script
├── install_linux.sh             Linux installer (distro-agnostic)
└── install_windows.ps1          Windows from-source installer
```
