# BARJ Volume Controller

A modern, cross-platform reimagining of [deej](https://github.com/omriharel/deej) — control per-app volume with real hardware sliders on an Arduino. Works on **all Linux distros, macOS, and Windows**, with a GUI for profiles, dynamic sliders, device selection, app auto-detection, system tray, and autostart.

## Features

- **Named profiles** — save, load, and delete slider configurations.
- **Dynamic sliders** — add/remove sliders in the GUI (defaults to 5).
- **Device dropdown** — lists serial ports; BARJ devices are auto-detected via a handshake and flagged `[BARJ]`.
- **App auto-detection** — running audio apps are listed and assignable per slider.
- **Special targets** — `Master` (global volume), `Microphone`, `System sounds` (Windows), and `All Others` (everything unassigned).
- **Close to system tray** — keep running in the background.
- **Launch on startup** (off by default) with **open / minimized / tray** modes.
- **Install / uninstall / update** scripts with a dependency checker.

## Repository layout

```
BARJ-Volume-Controller/
├── arduino/barj-sliders/barj-sliders.ino   Arduino firmware (Pro Micro/Leonardo)
├── barj_volume_controller/                 Python application package
│   ├── audio/                              per-OS audio backends
│   ├── gui.py                              CustomTkinter GUI
│   ├── controller.py                       slider → volume mapping
│   ├── serial_device.py                    port discovery + reader
│   ├── config.py                           profiles & settings
│   └── autostart.py                        launch-on-startup (per-OS)
├── packaging/
│   ├── install.sh / install.ps1            one-line GitHub bootstrap installers
│   ├── barj.sh                             Linux/macOS management script
│   └── barj.ps1                            Windows management script
├── requirements.txt
├── LICENSE
└── README.md
```

## Arduino setup

1. Open `arduino/barj-sliders/barj-sliders.ino` in the Arduino IDE.
2. Set board to **SparkFun Pro Micro** (or **Arduino Leonardo**).
3. Edit `NUM_SLIDERS` and `SLIDER_PINS` to match your wiring (default: 5 sliders on A0–A3, A6).
4. Upload. The board streams pipe-separated values (`0|512|1023|...`) and answers a `barj-id?` handshake so the GUI can identify it automatically.

## Download

**Source:** <https://github.com/JoeRAB/BARJ-Volume-Controller>

- **Clone:** `git clone https://github.com/JoeRAB/BARJ-Volume-Controller.git`
- **Zip:** click *Code → Download ZIP* on GitHub, or grab a tagged build from the [Releases page](https://github.com/JoeRAB/BARJ-Volume-Controller/releases).

## Install

### One-line install (downloads from GitHub and runs the installer)

**Linux / macOS**
```bash
curl -fsSL https://raw.githubusercontent.com/JoeRAB/BARJ-Volume-Controller/main/packaging/install.sh | bash
```

**Windows** (PowerShell)
```powershell
irm https://raw.githubusercontent.com/JoeRAB/BARJ-Volume-Controller/main/packaging/install.ps1 | iex
```

### From a downloaded/cloned copy

**Linux / macOS**
```bash
cd BARJ-Volume-Controller
./packaging/barj.sh install
```

**Windows** (PowerShell)
```powershell
cd BARJ-Volume-Controller
# If scripts are blocked: Set-ExecutionPolicy -Scope Process Bypass
.\packaging\barj.ps1 install
```

The installer checks dependencies, prints each as `name - Installed` / `name - Missing`, asks before installing missing ones, then sets up an isolated environment and a launcher / Start Menu entry.

## Update (keeps your config)

```bash
./packaging/barj.sh update          # Linux/macOS
.\packaging\barj.ps1 update          # Windows
```

By default this pulls the latest source from the `main` branch of the GitHub repo. Override with `BARJ_REPO_ZIP_URL` (e.g. to point at a specific release asset) or `BARJ_BRANCH`.

## Uninstall

```bash
./packaging/barj.sh uninstall        # Linux/macOS
.\packaging\barj.ps1 uninstall        # Windows
```

Removes all app files and folders, autostart entries, and shortcuts. You'll be asked whether to also delete the configuration folder.

## Run

After install: launch **BARJ Volume Controller** from your menu, or run `barj` (Linux/macOS) / the Start Menu shortcut (Windows).

To run from source without installing:
```bash
pip install -r requirements.txt
python -m barj_volume_controller
```

## Configuration

Stored as `config.json` in:
- Linux: `~/.config/BARJ/`
- macOS: `~/Library/Application Support/BARJ/`
- Windows: `%APPDATA%\BARJ\`

Profiles record slider count and each slider's target. Targets may be an app, `master`, `mic`, `system`, or `all_others`.

## Platform notes on audio

- **Windows** — full support (master, mic, system sounds, per-app, all-others) via `pycaw`.
- **Linux** — master, mic, per-app, and all-others via PulseAudio/PipeWire (`pulsectl`). No separate "system sounds" channel.
- **macOS** — master and mic via the OS; per-app control isn't exposed by stock macOS, so those targets degrade gracefully (app list still shown for assignment).

## License

Inspired by deej (MIT). Provided as-is.
