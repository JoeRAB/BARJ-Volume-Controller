# 🎚 BARJ Volume Controller

A hardware volume controller for **Windows** and **Linux**, driven by an Arduino
with potentiometers. Compatible with standard deej wiring.

Each slider can control your system master volume, a specific app, or "all other"
unassigned apps — with named-device detection, profiles, a system tray icon, and
a built-in dependency checker.

---

## Install on Linux

One command — clones the repo and runs the manager:

```bash
git clone https://github.com/JoeRAB/BARJ-Volume-Controller.git ~/barj-vc \
  && cd ~/barj-vc && chmod +x manage.sh && ./manage.sh
```

`manage.sh` is the single script for **install, update, and uninstall**. On launch
it scans for an existing installation and shows the relevant menu.

Works on any distro with a supported package manager: `apt` · `dnf` · `pacman` · `zypper`

### Update

```bash
cd ~/barj-vc && git pull && ./manage.sh
```

When an existing install is detected, choose **Update**. The update reuses the same
install folder and **never touches your config or profiles**.

### Uninstall

```bash
cd ~/barj-vc && ./manage.sh
```

Choose **Uninstall**. It removes every app file and folder, then asks separately
whether to also delete your saved profiles (default keeps them).

> **Your config lives at `~/.config/barj-volume-controller/config.yaml`** —
> completely separate from the install directory, and never modified by the
> installer or updater.

---

## Install on Windows

### Option A — Run from source (Python 3.10+ required)

```powershell
git clone https://github.com/JoeRAB/BARJ-Volume-Controller.git
cd BARJ-Volume-Controller
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

Upload `arduino/volume_mixer.ino` to your board. Set `NUM_SLIDERS` to match your
pot count if different from 5.

---

## First-time setup

1. The **Connecting to Hardware** dialog appears on launch. Pick your serial port
   from the dropdown — detected devices show their name, e.g. `/dev/ttyACM0 — Arduino Uno`.
   The dialog disappears once connected. Tick **Don't show on launch** to skip it
   next time (re-enable later in ⚙ Settings).
2. Assign each slider using its dropdown:
   - **master** → system master volume
   - **all_others** → every running app *not* assigned to another slider
   - any app name (e.g. `firefox`, `spotify`) → that specific app
3. Each target can only be assigned to one slider. Picking it on a second slider
   clears it from the first.

---

## Slider behaviour

- App volumes are a **percentage of the master volume** — the audio system
  multiplies app × master internally, so app sliders never raise volume above
  what master allows.
- **Save As (💾)** in the header saves the current slider layout as a named profile.
- The **Profile** dropdown switches between saved profiles. Use **+** to create a
  blank profile and **−** to delete one.

---

## Dependency check

On startup the app verifies all required and optional packages and lists them:

```
pyserial       - Installed
PyYAML         - Installed
pulsectl       - Missing
pystray        - Installed
Pillow         - Installed

Do you want to install missing dependencies?
```

Choosing **Install** runs pip for the missing ones; choosing **No** closes the app
without changes.

---

## Debug mode

```bash
barj-volume-controller --debug
```

Prints every Arduino tick to the terminal:

```
[DEBUG] raw=[  512 |  255 |  768 |    0 | 1023 ]  smoothed=[ ... ]  norm=[ ... ]
```

Useful for diagnosing wiring or solder issues — bad data triggers a single,
rate-limited error dialog showing the raw bytes received.

---

## Config file

Stored at:
- **Linux:** `~/.config/barj-volume-controller/config.yaml`
- **Windows:** `%APPDATA%\BARJ Volume Controller\config.yaml`

Never deleted by updates or reinstalls.

```yaml
serial:
  port: /dev/ttyACM0
  baud_rate: 9600
sliders:
  count: 5
  smoothing: 0.15
ui:
  show_connecting_on_launch: true
profiles:
  Default:
    - {target: master, label: Master}
    - {target: all_others, label: All Others}
    - {target: firefox, label: Slider 3}
    - {target: '', label: Slider 4}
    - {target: '', label: Slider 5}
current_profile: Default
```

---

## Troubleshooting

**The manager asks to "update/uninstall" on a fresh machine**
A previous install left files behind. Clear them with:

```bash
rm -rf ~/.local/share/barj-volume-controller
rm -f  ~/.local/bin/barj-volume-controller
rm -f  ~/.local/share/applications/barj-volume-controller.desktop
```

Your config is not affected. (The current uninstaller removes all of these
automatically.)

**Arduino not detected on Linux**
Make sure you're in the serial group and have logged out/in since install:

```bash
groups | grep -E 'dialout|uucp'
```

**Tray icon missing on GNOME**
Install the
[AppIndicator extension](https://extensions.gnome.org/extension/615/).
The app still works without it.

---

## Project structure

```
BARJ-Volume-Controller/
├── arduino/
│   └── volume_mixer.ino         Arduino sketch
├── audio/
│   ├── __init__.py              Platform auto-detect
│   ├── base.py                  Abstract AudioController
│   ├── windows_audio.py         pycaw (Windows Core Audio)
│   └── linux_audio.py           pulsectl (PulseAudio / PipeWire)
├── gui/
│   ├── connecting_dialog.py     Connect-to-hardware dialog
│   ├── dependency_check.py      Startup dependency checker
│   ├── error_dialog.py          Single-instance error popup
│   ├── main_window.py           Main window
│   ├── settings_dialog.py       Settings modal
│   └── slider_panel.py          VU meter widget
├── app_detector.py              Background audio-app polling
├── config_manager.py            XDG/APPDATA config (update-safe)
├── serial_reader.py             Serial comms + EMA smoothing
├── tray_icon.py                 System tray icon
├── main.py                      Entry point (--debug)
├── barj_vc.spec                 PyInstaller spec
├── build_windows.ps1            Windows EXE build
├── install_windows.ps1          Windows from-source installer
└── manage.sh                    Linux install / update / uninstall
```
