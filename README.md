# 🎚 BARJ Volume Controller

A hardware volume controller for **Windows** and **Linux**, driven by an Arduino
with potentiometers. Compatible with standard deej wiring.

Each slider can control your system master volume, a specific app, or "all other"
unassigned apps — with named-device detection, profiles, a system tray icon, and
a built-in dependency checker.

---

## Install on Linux

### Quick install (one line)

```bash
curl -fsSL https://raw.githubusercontent.com/JoeRAB/BARJ-Volume-Controller/main/manage.sh | bash
```

This downloads the project to a temporary folder and launches the installer.
Works on any distro with `apt`, `dnf`, `pacman`, or `zypper`.

### From a clone (recommended for updating later)

```bash
git clone https://github.com/JoeRAB/BARJ-Volume-Controller.git ~/barj-vc \
  && cd ~/barj-vc && chmod +x manage.sh && ./manage.sh
```

`manage.sh` is the single script for **install, update, and uninstall** — it scans
for an existing installation and shows the relevant menu, and lets you pick a
custom install location.

### Update

```bash
cd ~/barj-vc && git pull && ./manage.sh
```

Choose **Update**. It reuses the same folder and **never touches your config or
profiles**.

### Uninstall

```bash
cd ~/barj-vc && ./manage.sh
```

Choose **Uninstall**. It deletes every file and folder the app created. It then
asks **"Keep config and profiles?"** — answer **Yes** (default) to keep only your
config folder for a future reinstall, or **No** to remove absolutely everything.

> **Your config lives at `~/.config/barj-volume-controller/config.yaml`** —
> separate from the install directory, never modified by install or update.

---

## Windows / Flatpak

Standalone Windows `.exe` packaging and a Flatpak for Flathub are planned for a
future release. For now, Windows users can run from source with Python 3.10+:

```powershell
git clone https://github.com/JoeRAB/BARJ-Volume-Controller.git
cd BARJ-Volume-Controller
pip install -r requirements.txt
python main.py
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

Upload `arduino/volume_mixer.ino` to your board. The top of the sketch has a
clearly-marked **CONFIGURATION** section: set `NUM_SLIDERS` to your pot count and
list each slider's analog pin in `SLIDER_PINS` (slider 1 first — this is the
left-to-right order in the app). To remap a slider, change its pin there and
re-upload.

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
│   ├── __init__.py              Platform auto-detect + AudioController + AppDetector
│   ├── windows_audio.py         pycaw (Windows Core Audio)
│   └── linux_audio.py           pulsectl (PulseAudio / PipeWire)
├── gui/
│   ├── __init__.py              Package marker
│   ├── theme.py                 Palettes, fonts, RoundedButton, Tooltip
│   ├── widgets.py               Slider cards + all dialogs
│   └── main_window.py           Main window
├── autostart.py                 Start-on-login (Linux/Windows)
├── config_manager.py            XDG/APPDATA config (update-safe)
├── serial_reader.py             Serial comms + smoothing + calibration
├── tray_icon.py                 System tray icon
├── main.py                      Entry point (--debug) + single-instance
└── manage.sh                    Linux install / update / uninstall
```
