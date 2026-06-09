#!/usr/bin/env bash
# =============================================================================
# BARJ Volume Controller — Linux Installer  (distro-agnostic)
# =============================================================================

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
die()     { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

# ── Progress bar ──────────────────────────────────────────────────────────────
TOTAL_STEPS=8
CURRENT_STEP=0

progress() {
    # Usage: progress "Step description"
    CURRENT_STEP=$(( CURRENT_STEP + 1 ))
    local pct=$(( CURRENT_STEP * 100 / TOTAL_STEPS ))
    local filled=$(( pct / 5 ))          # bar is 20 chars wide
    local empty=$(( 20 - filled ))
    local bar="" i
    for (( i=0; i<filled; i++ )); do bar+="█"; done
    for (( i=0; i<empty;  i++ )); do bar+="░"; done
    echo ""
    echo -e "  ${CYAN}[${bar}] ${pct}%  —  $1${RESET}"
    echo ""
}

# Try to install a single package; warn and continue if unavailable.
try_pkg() {
    local mgr="$1" pkg="$2"
    case "$mgr" in
        apt)
            if apt-cache show "$pkg" &>/dev/null 2>&1; then
                sudo apt-get install -y "$pkg" -qq \
                    && echo -e "    ${GREEN}✓${RESET} $pkg" \
                    || echo -e "    ${YELLOW}⚠${RESET} $pkg (install failed)"
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

# Check if a pip package is importable (returns 0=installed, 1=missing)
pip_check() {
    local import_name="$1"
    "$PYTHON_BIN" -c "import ${import_name}" 2>/dev/null
}

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="barj-volume-controller"
APP_DISPLAY="BARJ Volume Controller"
INSTALL_DIR="$HOME/.local/share/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/$APP_NAME"
PYTHON_BIN="python3"

# ── Banner ────────────────────────────────────────────────────────────────────
clear
echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║   BARJ Volume Controller — Installer     ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

# =============================================================================
# SECTION 1 — PRE-FLIGHT  (gather info, ask all questions, no changes yet)
# =============================================================================

# ── Detect distro ─────────────────────────────────────────────────────────────
DISTRO="Unknown"
[[ -f /etc/os-release ]] && source /etc/os-release && DISTRO="${PRETTY_NAME:-${NAME:-Unknown}}"
info "Distro: $DISTRO"

# ── Detect package manager ────────────────────────────────────────────────────
if   command -v apt-get &>/dev/null; then PKG_MGR="apt"
elif command -v dnf     &>/dev/null; then PKG_MGR="dnf"
elif command -v pacman  &>/dev/null; then PKG_MGR="pacman"
elif command -v zypper  &>/dev/null; then PKG_MGR="zypper"
else PKG_MGR="none"
fi
info "Package manager: $PKG_MGR"

# ── Check Python ──────────────────────────────────────────────────────────────
command -v "$PYTHON_BIN" &>/dev/null || die "python3 not found. Install it and re-run."
PY_VER=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR="${PY_VER%%.*}"; PY_MINOR="${PY_VER#*.}"
[[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 10 ) ]] \
    && die "Python 3.10+ required (found $PY_VER)."
info "Python $PY_VER"
echo ""

# ── Detect existing install ───────────────────────────────────────────────────
IS_UPDATE=false
if [[ -d "$INSTALL_DIR" || -f "$BIN_DIR/$APP_NAME" ]]; then
    echo -e "${YELLOW}╔══════════════════════════════════════════╗${RESET}"
    echo -e "${YELLOW}║  Existing installation detected!         ║${RESET}"
    echo -e "${YELLOW}╚══════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "  Install location:  ${CYAN}$INSTALL_DIR${RESET}"
    echo -e "  Config location:   ${CYAN}$CONFIG_DIR${RESET}"
    echo ""
    read -rp "$(echo -e "${BOLD}Do you want to update the existing installation? [Y/n]: ${RESET}")" ans_update
    echo ""
    case "${ans_update,,}" in
        n|no) echo "Update cancelled. Your installation is unchanged."; exit 0 ;;
        *)    IS_UPDATE=true; info "Updating existing installation…" ;;
    esac
fi

# ── Check Python pip dependencies ─────────────────────────────────────────────
echo -e "${BOLD}Checking Python dependencies:${RESET}"
echo ""

# name | import_name | pip_package | required(y/n)
declare -a DEP_NAMES=( "pyserial"  "PyYAML"  "pulsectl"  "pystray"  "Pillow"  )
declare -a DEP_IMPORTS=( "serial"  "yaml"    "pulsectl"  "pystray"  "PIL"     )
declare -a DEP_PKGS=(  "pyserial"  "pyyaml"  "pulsectl"  "pystray"  "Pillow"  )
declare -a DEP_STATUS=()

HAS_MISSING=false
for i in "${!DEP_NAMES[@]}"; do
    name="${DEP_NAMES[$i]}"
    import="${DEP_IMPORTS[$i]}"
    if pip_check "$import"; then
        DEP_STATUS+=("installed")
        printf "  %-14s - ${GREEN}Installed${RESET}\n" "$name"
    else
        DEP_STATUS+=("missing")
        printf "  %-14s - ${YELLOW}Missing${RESET}\n" "$name"
        HAS_MISSING=true
    fi
done
echo ""

# ── Ask about missing deps ────────────────────────────────────────────────────
INSTALL_DEPS=false
if $HAS_MISSING; then
    read -rp "$(echo -e "${BOLD}Do you want to install missing dependencies? [Y/n]: ${RESET}")" ans_deps
    echo ""
    case "${ans_deps,,}" in
        n|no)
            echo -e "${YELLOW}No changes made. Exiting.${RESET}"
            exit 0
            ;;
        *)
            INSTALL_DEPS=true
            ;;
    esac
else
    info "All Python dependencies already satisfied."
fi

# ── Final confirmation ────────────────────────────────────────────────────────
echo -e "${BOLD}Ready to install:${RESET}"
echo -e "  App files → ${CYAN}$INSTALL_DIR${RESET}"
echo -e "  Launcher  → ${CYAN}$BIN_DIR/$APP_NAME${RESET}"
echo -e "  Config    → ${CYAN}$CONFIG_DIR${RESET} (never overwritten)"
echo ""
read -rp "$(echo -e "${BOLD}Proceed with installation? [Y/n]: ${RESET}")" ans_proceed
echo ""
case "${ans_proceed,,}" in
    n|no) echo -e "${YELLOW}Installation cancelled. No changes made.${RESET}"; exit 0 ;;
esac

# =============================================================================
# SECTION 2 — INSTALLATION  (progress bar from here)
# =============================================================================

echo -e "${BOLD}Installing BARJ Volume Controller…${RESET}"

# ── Step 1: System packages ───────────────────────────────────────────────────
progress "Installing system packages"

if [[ "$PKG_MGR" == "apt" ]]; then
    sudo apt-get update -qq
fi

if [[ "$PKG_MGR" != "none" ]]; then
    case "$PKG_MGR" in
        apt)
            try_pkg apt python3-pip
            try_pkg apt python3-venv
            try_pkg apt python3-tk
            try_pkg apt python3-gi
            try_pkg apt gir1.2-gtk-3.0
            for pkg in gir1.2-ayatana-appindicator3-0.1 gir1.2-appindicator3-0.1 gir1.2-appindicator-0.1; do
                if apt-cache show "$pkg" &>/dev/null 2>&1; then
                    sudo apt-get install -y "$pkg" -qq \
                        && echo -e "    ${GREEN}✓${RESET} $pkg" && break
                fi
            done
            ;;
        dnf)   try_pkg dnf python3-pip; try_pkg dnf python3-tkinter; try_pkg dnf python3-gobject ;;
        pacman) try_pkg pacman python-pip; try_pkg pacman tk; try_pkg pacman python-gobject ;;
        zypper) try_pkg zypper python3-pip; try_pkg zypper python3-tk ;;
    esac
fi

# ── Step 2: Create directories ────────────────────────────────────────────────
progress "Creating directories"
mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$DESKTOP_DIR"
echo -e "    ${GREEN}✓${RESET} $INSTALL_DIR"

# ── Step 3: Create venv ───────────────────────────────────────────────────────
progress "Creating Python virtual environment"
[[ -d "$INSTALL_DIR/venv" ]] && rm -rf "$INSTALL_DIR/venv"
if ! "$PYTHON_BIN" -m venv "$INSTALL_DIR/venv" 2>/dev/null; then
    warn "Trying python${PY_VER}-venv…"
    [[ "$PKG_MGR" == "apt" ]] && sudo apt-get install -y "python${PY_VER}-venv" -qq
    "$PYTHON_BIN" -m venv "$INSTALL_DIR/venv" || die "Cannot create venv."
fi
echo -e "    ${GREEN}✓${RESET} Venv ready"

# ── Step 4: Install pip packages ──────────────────────────────────────────────
progress "Installing Python packages"
VENV_PIP="$INSTALL_DIR/venv/bin/pip"
"$VENV_PIP" install --upgrade pip --quiet
for i in "${!DEP_NAMES[@]}"; do
    pkg="${DEP_PKGS[$i]}"
    if $INSTALL_DEPS || [[ "${DEP_STATUS[$i]}" == "installed" ]]; then
        "$VENV_PIP" install "$pkg" --quiet \
            && echo -e "    ${GREEN}✓${RESET} $pkg" \
            || echo -e "    ${YELLOW}⚠${RESET} $pkg (failed)"
    fi
done

# ── Step 5: Copy source files ─────────────────────────────────────────────────
progress "Copying application files"
for item in main.py serial_reader.py config_manager.py app_detector.py \
            tray_icon.py audio gui arduino; do
    src="$SCRIPT_DIR/$item"
    [[ -e "$src" ]] \
        && cp -r "$src" "$INSTALL_DIR/" \
        && echo -e "    ${GREEN}✓${RESET} $item" \
        || echo -e "    ${YELLOW}⊘${RESET} $item (not found)"
done

# ── Step 6: Launcher + .desktop ───────────────────────────────────────────────
progress "Creating launcher and app menu entry"

cat > "$BIN_DIR/$APP_NAME" << LAUNCHER
#!/usr/bin/env bash
exec "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/main.py" "\$@"
LAUNCHER
chmod +x "$BIN_DIR/$APP_NAME"
echo -e "    ${GREEN}✓${RESET} Launcher: $BIN_DIR/$APP_NAME"

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
command -v update-desktop-database &>/dev/null \
    && update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
echo -e "    ${GREEN}✓${RESET} App menu entry created"

if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    warn "~/.local/bin not in PATH — add to ~/.bashrc:  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ── Step 7: Serial port group ─────────────────────────────────────────────────
progress "Configuring serial port access"
SERIAL_GROUP=""
for grp in dialout uucp; do
    getent group "$grp" &>/dev/null && SERIAL_GROUP="$grp" && break
done
NEEDS_RELOGIN=false
if [[ -z "$SERIAL_GROUP" ]]; then
    warn "No dialout/uucp group found — serial access may need manual config."
elif groups "$USER" | grep -qw "$SERIAL_GROUP"; then
    echo -e "    ${GREEN}✓${RESET} Already in group '$SERIAL_GROUP'"
else
    sudo usermod -aG "$SERIAL_GROUP" "$USER"
    echo -e "    ${GREEN}✓${RESET} Added to group '$SERIAL_GROUP'"
    NEEDS_RELOGIN=true
fi

# ── Step 8: Done ──────────────────────────────────────────────────────────────
progress "Installation complete"

DE="${XDG_CURRENT_DESKTOP:-}"
if echo "$DE" | grep -qi "gnome"; then
    warn "GNOME detected — tray icon needs the AppIndicator extension:"
    warn "  https://extensions.gnome.org/extension/615/"
fi

# =============================================================================
# SECTION 3 — SUMMARY
# =============================================================================

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║          Installation Complete!          ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${BOLD}Launch commands:${RESET}"
echo -e "    ${CYAN}barj-volume-controller${RESET}           (normal)"
echo -e "    ${CYAN}barj-volume-controller --debug${RESET}   (show raw Arduino values)"
echo ""
echo -e "  ${BOLD}Application files installed to:${RESET}"
echo -e "    ${CYAN}$INSTALL_DIR${RESET}"
echo ""
echo -e "  ${BOLD}Your config and profiles are stored at:${RESET}"
echo -e "    ${CYAN}$CONFIG_DIR/config.yaml${RESET}"
echo -e "    ${GREEN}(This file is never deleted or modified by the installer)${RESET}"
echo ""
echo -e "  ${BOLD}To uninstall:${RESET}"
echo -e "    ${CYAN}chmod +x $SCRIPT_DIR/uninstall_linux.sh && $SCRIPT_DIR/uninstall_linux.sh${RESET}"
echo ""

if $NEEDS_RELOGIN; then
    echo -e "${YELLOW}  ⚠  Log out and back in before the Arduino serial port will work.${RESET}"
    echo -e "${YELLOW}     (Group '$SERIAL_GROUP' change requires a new login session.)${RESET}"
    echo ""
fi

echo -e "  First run: click ${BOLD}⚙ Settings${RESET} and select your serial port."
echo -e "  Common ports:  /dev/ttyACM0   /dev/ttyUSB0"
echo ""
