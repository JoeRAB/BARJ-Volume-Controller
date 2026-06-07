#!/usr/bin/env bash
# =============================================================================
# BARJ Volume Controller — Linux Installer  (distro-agnostic)
#
# Supports (anything with Python 3.10+ and a recognised package manager):
#   apt    — Ubuntu · Debian · Linux Mint · Pop!_OS · Raspberry Pi OS · ...
#   dnf    — Fedora · RHEL · CentOS Stream · AlmaLinux · Rocky Linux · ...
#   pacman — Arch · Manjaro · EndeavourOS · Garuda · ...
#   zypper — openSUSE Leap · Tumbleweed · SLES · ...
#   (no package manager found — skips system deps, continues with pip only)
#
# Config is stored in ~/.config/barj-volume-controller/config.yaml
# and is NEVER touched by this installer — safe to re-run for updates.
#
# Usage:
#   chmod +x install_linux.sh && ./install_linux.sh
#
# Update (re-run at any time — config is preserved):
#   ./install_linux.sh
# =============================================================================

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
die()     { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }
sep()     { echo -e "${BOLD}${CYAN}────────────────────────────────────────${RESET}"; }

# Try to install a single package; warn and continue if unavailable.
try_pkg() {
    local mgr="$1" pkg="$2"
    case "$mgr" in
        apt)
            if apt-cache show "$pkg" &>/dev/null 2>&1; then
                sudo apt-get install -y "$pkg" -qq \
                    && echo -e "    ${GREEN}✓${RESET} $pkg" \
                    || echo -e "    ${YELLOW}⚠${RESET} $pkg (install failed, continuing)"
            else
                echo -e "    ${YELLOW}⊘${RESET} $pkg (not in apt, skipping)"
            fi
            ;;
        dnf)
            sudo dnf install -y "$pkg" --quiet 2>/dev/null \
                && echo -e "    ${GREEN}✓${RESET} $pkg" \
                || echo -e "    ${YELLOW}⊘${RESET} $pkg (not available, skipping)"
            ;;
        pacman)
            sudo pacman -S --noconfirm "$pkg" 2>/dev/null \
                && echo -e "    ${GREEN}✓${RESET} $pkg" \
                || echo -e "    ${YELLOW}⊘${RESET} $pkg (not available, skipping)"
            ;;
        zypper)
            sudo zypper install -y "$pkg" 2>/dev/null \
                && echo -e "    ${GREEN}✓${RESET} $pkg" \
                || echo -e "    ${YELLOW}⊘${RESET} $pkg (not available, skipping)"
            ;;
    esac
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="barj-volume-controller"
APP_DISPLAY="BARJ Volume Controller"
INSTALL_DIR="$HOME/.local/share/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
# Config lives here — completely separate from install dir, never deleted
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/$APP_NAME"

# ── Banner ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║   BARJ Volume Controller — Linux Install  ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

# ── Step 1: Detect OS / package manager ──────────────────────────────────────
sep
info "Step 1/9 — Detecting system…"

# Identify distro for friendly display
DISTRO="Unknown"
if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    DISTRO="${PRETTY_NAME:-${NAME:-Unknown}}"
fi
info "Distro:  $DISTRO"

if   command -v apt-get &>/dev/null; then PKG_MGR="apt"
elif command -v dnf     &>/dev/null; then PKG_MGR="dnf"
elif command -v pacman  &>/dev/null; then PKG_MGR="pacman"
elif command -v zypper  &>/dev/null; then PKG_MGR="zypper"
else
    PKG_MGR="none"
    warn "No supported package manager found."
    warn "System packages will be skipped — ensure python3, python3-tk,"
    warn "and python3-venv are installed before continuing."
fi
info "Package manager: ${PKG_MGR}"
success "System detected."

# ── Step 2: Install system packages ──────────────────────────────────────────
sep
info "Step 2/9 — Installing system dependencies…"

if [[ "$PKG_MGR" == "apt" ]]; then
    sudo apt-get update -qq
fi

if [[ "$PKG_MGR" != "none" ]]; then
    echo ""
    echo -e "  ${BOLD}Core (required):${RESET}"
    case "$PKG_MGR" in
        apt)
            try_pkg apt python3-pip
            try_pkg apt python3-venv
            try_pkg apt python3-tk
            ;;
        dnf)
            try_pkg dnf python3-pip
            try_pkg dnf python3-tkinter
            ;;
        pacman)
            try_pkg pacman python-pip
            try_pkg pacman tk
            ;;
        zypper)
            try_pkg zypper python3-pip
            try_pkg zypper python3-tk
            ;;
    esac

    echo ""
    echo -e "  ${BOLD}Tray icon support (optional — GObject/AppIndicator):${RESET}"
    case "$PKG_MGR" in
        apt)
            try_pkg apt python3-gi
            try_pkg apt gir1.2-gtk-3.0

            # AppIndicator — try each known package name newest-first
            FOUND_INDICATOR=false
            for pkg in \
                gir1.2-ayatana-appindicator3-0.1 \
                gir1.2-appindicator3-0.1 \
                gir1.2-appindicator-0.1
            do
                if apt-cache show "$pkg" &>/dev/null 2>&1; then
                    sudo apt-get install -y "$pkg" -qq \
                        && echo -e "    ${GREEN}✓${RESET} $pkg" \
                        && FOUND_INDICATOR=true && break
                fi
            done
            $FOUND_INDICATOR || echo -e "    ${YELLOW}⊘${RESET} AppIndicator (not found — tray may not show on all desktops)"
            ;;
        dnf)
            try_pkg dnf python3-gobject
            try_pkg dnf gtk3
            try_pkg dnf libappindicator-gtk3
            ;;
        pacman)
            try_pkg pacman python-gobject
            try_pkg pacman gtk3
            try_pkg pacman libappindicator-gtk3
            ;;
        zypper)
            try_pkg zypper python3-gobject-cairo
            try_pkg zypper gtk3-devel
            ;;
    esac
fi

success "System dependencies done."

# ── Step 3: Check Python version ─────────────────────────────────────────────
sep
info "Step 3/9 — Checking Python version…"

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" &>/dev/null || die "python3 not found. Install it and re-run."

PY_VER=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR="${PY_VER%%.*}"
PY_MINOR="${PY_VER#*.}"

[[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 10 ) ]] \
    && die "Python 3.10+ required (found $PY_VER). Install a newer Python and retry."

success "Python $PY_VER ✓"

# ── Step 4: Config safety notice ─────────────────────────────────────────────
sep
info "Step 4/9 — Checking config safety…"

if [[ -f "$CONFIG_DIR/config.yaml" ]]; then
    success "Existing config found at $CONFIG_DIR/config.yaml"
    success "Config will NOT be modified — your profiles are safe."
else
    info "No existing config found."
    info "Config will be created on first launch at:"
    info "  $CONFIG_DIR/config.yaml"
fi

# ── Step 5: Create install directory ─────────────────────────────────────────
sep
info "Step 5/9 — Preparing install directory…"

mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$DESKTOP_DIR"

if [[ -d "$INSTALL_DIR/venv" ]]; then
    warn "Existing venv found — removing and rebuilding (config is untouched)."
    rm -rf "$INSTALL_DIR/venv"
fi

success "Install directory ready: $INSTALL_DIR"

# ── Step 6: Create Python venv ────────────────────────────────────────────────
sep
info "Step 6/9 — Creating Python virtual environment…"

if ! "$PYTHON_BIN" -m venv "$INSTALL_DIR/venv" 2>/dev/null; then
    warn "python3 -m venv failed — trying python${PY_VER}-venv package…"
    case "$PKG_MGR" in
        apt)    sudo apt-get install -y "python${PY_VER}-venv" -qq ;;
        dnf)    sudo dnf install -y "python${PY_VER}" ;;
        pacman|zypper|none) true ;;
    esac
    "$PYTHON_BIN" -m venv "$INSTALL_DIR/venv" \
        || die "Still cannot create venv. Check your Python installation."
fi

success "Venv ready."

# ── Step 7: Install Python packages ───────────────────────────────────────────
sep
info "Step 7/9 — Installing Python packages into venv…"

VENV_PIP="$INSTALL_DIR/venv/bin/pip"
"$VENV_PIP" install --upgrade pip --quiet

echo ""
echo -e "  ${BOLD}Installing:${RESET}"
for pkg in pyserial pyyaml "pystray>=0.19.4" "Pillow>=10.0.0" pulsectl; do
    "$VENV_PIP" install "$pkg" --quiet \
        && echo -e "    ${GREEN}✓${RESET} $pkg" \
        || echo -e "    ${YELLOW}⚠${RESET} $pkg (failed)"
done
echo ""

success "Python packages installed."

# ── Step 8: Copy source files (never touches config) ─────────────────────────
sep
info "Step 8/9 — Copying application files…"

for item in main.py serial_reader.py config_manager.py app_detector.py \
            tray_icon.py audio gui arduino; do
    src="$SCRIPT_DIR/$item"
    if [[ -e "$src" ]]; then
        cp -r "$src" "$INSTALL_DIR/"
        echo -e "    ${GREEN}✓${RESET} $item"
    else
        echo -e "    ${YELLOW}⊘${RESET} $item (not found, skipping)"
    fi
done
echo ""

# Launcher
cat > "$BIN_DIR/$APP_NAME" << LAUNCHER
#!/usr/bin/env bash
# BARJ Volume Controller launcher
exec "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/main.py" "\$@"
LAUNCHER
chmod +x "$BIN_DIR/$APP_NAME"
echo -e "    ${GREEN}✓${RESET} Launcher: $BIN_DIR/$APP_NAME"

# .desktop entry
cat > "$DESKTOP_DIR/$APP_NAME.desktop" << DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=$APP_DISPLAY
Comment=Hardware volume controller with Arduino potentiometers
Exec=$BIN_DIR/$APP_NAME
Icon=audio-volume-high
Terminal=false
Categories=AudioVideo;Audio;Utility;
Keywords=volume;mixer;audio;arduino;barj;
StartupNotify=true
DESKTOP
chmod +x "$DESKTOP_DIR/$APP_NAME.desktop"
echo -e "    ${GREEN}✓${RESET} App menu entry"

command -v update-desktop-database &>/dev/null \
    && update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

# Check ~/.local/bin is on PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    warn "~/.local/bin is not in your PATH."
    warn "Add this to ~/.bashrc or ~/.profile:"
    warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

success "Files installed."

# ── Step 9: Serial port group + desktop environment warnings ──────────────────
sep
info "Step 9/9 — Serial port access…"

# Determine correct group name (dialout on Debian/Ubuntu, uucp on Arch/Fedora)
SERIAL_GROUP=""
for grp in dialout uucp; do
    getent group "$grp" &>/dev/null && SERIAL_GROUP="$grp" && break
done

NEEDS_RELOGIN=false
if [[ -z "$SERIAL_GROUP" ]]; then
    warn "No dialout/uucp group found — serial access may need manual config."
elif groups "$USER" | grep -qw "$SERIAL_GROUP"; then
    success "Already in group '$SERIAL_GROUP' ✓"
else
    sudo usermod -aG "$SERIAL_GROUP" "$USER"
    warn "Added '$USER' to group '$SERIAL_GROUP'."
    NEEDS_RELOGIN=true
fi

# Desktop environment tray note
DE="${XDG_CURRENT_DESKTOP:-}"
if echo "$DE" | grep -qi "gnome"; then
    echo ""
    echo -e "  ${YELLOW}GNOME detected:${RESET} The tray icon needs the"
    echo -e "  'AppIndicator and KStatusNotifierItem Support' GNOME extension."
    echo -e "  Install: ${CYAN}https://extensions.gnome.org/extension/615/${RESET}"
    echo -e "  (The app runs fine without it — just no tray icon.)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║          Installation Complete!          ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  Launch:       ${BOLD}barj-volume-controller${RESET}"
echo -e "  Debug mode:   ${BOLD}barj-volume-controller --debug${RESET}"
echo -e "  App menu:     Audio/Video → ${BOLD}$APP_DISPLAY${RESET}"
echo ""
echo -e "  Config file (yours, never deleted by updates):"
echo -e "  ${CYAN}$CONFIG_DIR/config.yaml${RESET}"
echo ""

if $NEEDS_RELOGIN; then
    echo -e "${YELLOW}  ⚠  Log out and back in before the Arduino serial port works.${RESET}"
    echo -e "${YELLOW}     (Group '$SERIAL_GROUP' change requires a new login session.)${RESET}"
    echo ""
fi

echo -e "  First run: click ${BOLD}⚙ Settings${RESET} and select your serial port."
echo -e "  Common ports:  /dev/ttyACM0   /dev/ttyUSB0"
echo ""
