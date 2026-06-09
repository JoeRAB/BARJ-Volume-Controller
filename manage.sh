#!/usr/bin/env bash
# =============================================================================
# BARJ Volume Controller — Manager
# Single command to install, update, or uninstall.
#
# Usage:
#   chmod +x manage.sh && ./manage.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

say()     { echo -e "$*"; }
info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
die()     { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }
blank()   { echo ""; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="barj-volume-controller"
APP_DISPLAY="BARJ Volume Controller"
DEFAULT_INSTALL_DIR="$HOME/.local/share/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/$APP_NAME"
PYTHON_BIN="python3"

# =============================================================================
# UTILITY
# =============================================================================

# Returns 0 (true) if a valid install exists at the given path
is_install() {
    local path="$1"
    [[ -f "$path/main.py" ]] && [[ -d "$path/venv" ]]
}

# Detect the package manager
detect_pkg_mgr() {
    if   command -v apt-get &>/dev/null; then echo "apt"
    elif command -v dnf     &>/dev/null; then echo "dnf"
    elif command -v pacman  &>/dev/null; then echo "pacman"
    elif command -v zypper  &>/dev/null; then echo "zypper"
    else echo "none"
    fi
}

# Try to install a single system package; skip if unavailable
try_pkg() {
    local mgr="$1" pkg="$2"
    case "$mgr" in
        apt)
            if apt-cache show "$pkg" &>/dev/null 2>&1; then
                sudo apt-get install -y "$pkg" -qq \
                    && echo -e "    ${GREEN}✓${RESET} $pkg" \
                    || echo -e "    ${YELLOW}⚠${RESET} $pkg (failed, continuing)"
            else
                echo -e "    ${YELLOW}⊘${RESET} $pkg (not available)"
            fi ;;
        dnf)
            sudo dnf install -y "$pkg" --quiet 2>/dev/null \
                && echo -e "    ${GREEN}✓${RESET} $pkg" \
                || echo -e "    ${YELLOW}⊘${RESET} $pkg (not available)" ;;
        pacman)
            sudo pacman -S --noconfirm "$pkg" 2>/dev/null \
                && echo -e "    ${GREEN}✓${RESET} $pkg" \
                || echo -e "    ${YELLOW}⊘${RESET} $pkg (not available)" ;;
        zypper)
            sudo zypper install -y "$pkg" 2>/dev/null \
                && echo -e "    ${GREEN}✓${RESET} $pkg" \
                || echo -e "    ${YELLOW}⊘${RESET} $pkg (not available)" ;;
    esac
}

# Check if a Python package is importable
pip_check() { "$PYTHON_BIN" -c "import $1" 2>/dev/null; }

# =============================================================================
# DEP CHECK  (shared by install and update)
# =============================================================================

run_dep_check() {
    # Populate arrays in caller's scope
    DEP_NAMES=(  "pyserial"  "PyYAML"  "pulsectl"  "pystray"  "Pillow" )
    DEP_IMPORTS=( "serial"   "yaml"    "pulsectl"  "pystray"  "PIL"    )
    DEP_PKGS=(   "pyserial"  "pyyaml"  "pulsectl"  "pystray"  "Pillow" )
    DEP_STATUS=()

    blank
    say "${BOLD}Checking Python dependencies:${RESET}"
    blank

    local has_missing=false
    for i in "${!DEP_NAMES[@]}"; do
        if pip_check "${DEP_IMPORTS[$i]}"; then
            DEP_STATUS+=("installed")
            printf "  %-14s - ${GREEN}Installed${RESET}\n" "${DEP_NAMES[$i]}"
        else
            DEP_STATUS+=("missing")
            printf "  %-14s - ${YELLOW}Missing${RESET}\n" "${DEP_NAMES[$i]}"
            has_missing=true
        fi
    done

    blank
    if $has_missing; then
        read -rp "$(echo -e "${BOLD}Do you want to install missing dependencies? [Y/n]: ${RESET}")" ans
        blank
        case "${ans,,}" in
            n|no) say "${YELLOW}Cancelled. No changes made.${RESET}"; exit 0 ;;
        esac
    else
        info "All Python dependencies already satisfied."
    fi
}

# =============================================================================
# INSTALL STEPS  (called by both install and update)
# =============================================================================

step_system_packages() {
    local mgr="$1"
    info "Installing system packages…"
    [[ "$mgr" == "apt" ]] && sudo apt-get update -qq
    case "$mgr" in
        apt)
            try_pkg apt python3-pip
            try_pkg apt python3-venv
            try_pkg apt python3-tk
            try_pkg apt python3-gi
            try_pkg apt gir1.2-gtk-3.0
            local found_indicator=false
            for pkg in gir1.2-ayatana-appindicator3-0.1 gir1.2-appindicator3-0.1; do
                if apt-cache show "$pkg" &>/dev/null 2>&1; then
                    sudo apt-get install -y "$pkg" -qq \
                        && echo -e "    ${GREEN}✓${RESET} $pkg" \
                        && found_indicator=true && break
                fi
            done
            $found_indicator || echo -e "    ${YELLOW}⊘${RESET} AppIndicator (not found — tray may not show on all desktops)"
            ;;
        dnf)    try_pkg dnf python3-pip; try_pkg dnf python3-tkinter; try_pkg dnf python3-gobject ;;
        pacman) try_pkg pacman python-pip; try_pkg pacman tk; try_pkg pacman python-gobject ;;
        zypper) try_pkg zypper python3-pip; try_pkg zypper python3-tk ;;
        none)   warn "No package manager — skipping system packages." ;;
    esac
}

step_venv() {
    local install_dir="$1"
    info "Creating Python virtual environment…"
    [[ -d "$install_dir/venv" ]] && rm -rf "$install_dir/venv"
    if ! "$PYTHON_BIN" -m venv "$install_dir/venv" 2>/dev/null; then
        local py_ver
        py_ver=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        warn "Trying python${py_ver}-venv…"
        [[ "$(detect_pkg_mgr)" == "apt" ]] \
            && sudo apt-get install -y "python${py_ver}-venv" -qq
        "$PYTHON_BIN" -m venv "$install_dir/venv" || die "Cannot create venv."
    fi
    success "Venv ready."
}

step_pip() {
    local install_dir="$1"
    info "Installing Python packages into venv…"
    local venv_pip="$install_dir/venv/bin/pip"
    "$venv_pip" install --upgrade pip --quiet
    for i in "${!DEP_NAMES[@]}"; do
        "$venv_pip" install "${DEP_PKGS[$i]}" --quiet \
            && echo -e "    ${GREEN}✓${RESET} ${DEP_NAMES[$i]}" \
            || echo -e "    ${YELLOW}⚠${RESET} ${DEP_NAMES[$i]} (failed)"
    done
}

step_copy_files() {
    local install_dir="$1"
    info "Copying application files…"
    for item in main.py serial_reader.py config_manager.py app_detector.py \
                tray_icon.py audio gui arduino; do
        local src="$SCRIPT_DIR/$item"
        [[ -e "$src" ]] \
            && cp -r "$src" "$install_dir/" \
            && echo -e "    ${GREEN}✓${RESET} $item" \
            || echo -e "    ${YELLOW}⊘${RESET} $item (not found in $SCRIPT_DIR)"
    done
}

step_launcher() {
    local install_dir="$1"
    info "Creating launcher and app menu entry…"

    mkdir -p "$BIN_DIR" "$DESKTOP_DIR"

    cat > "$BIN_DIR/$APP_NAME" << LAUNCHER
#!/usr/bin/env bash
exec "$install_dir/venv/bin/python" "$install_dir/main.py" "\$@"
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
    echo -e "    ${GREEN}✓${RESET} App menu entry"

    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        warn "~/.local/bin not in PATH. Add to ~/.bashrc:"
        warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
}

step_serial_group() {
    info "Checking serial port group…"
    local grp=""
    for g in dialout uucp; do
        getent group "$g" &>/dev/null && grp="$g" && break
    done
    if [[ -z "$grp" ]]; then
        warn "No dialout/uucp group found."
    elif groups "$USER" | grep -qw "$grp"; then
        echo -e "    ${GREEN}✓${RESET} Already in group '$grp'"
    else
        sudo usermod -aG "$grp" "$USER"
        echo -e "    ${GREEN}✓${RESET} Added to group '$grp'"
        NEEDS_RELOGIN=true
    fi
}

print_summary() {
    local install_dir="$1"
    blank
    say "${BOLD}${GREEN}╔══════════════════════════════════════════╗${RESET}"
    say "${BOLD}${GREEN}║              All Done!                   ║${RESET}"
    say "${BOLD}${GREEN}╚══════════════════════════════════════════╝${RESET}"
    blank
    say "  ${BOLD}Launch:${RESET}"
    say "    ${CYAN}barj-volume-controller${RESET}           (normal)"
    say "    ${CYAN}barj-volume-controller --debug${RESET}   (show raw Arduino values)"
    blank
    say "  ${BOLD}Application files:${RESET}"
    say "    ${CYAN}$install_dir${RESET}"
    blank
    say "  ${BOLD}Config and profiles:${RESET}"
    say "    ${CYAN}$CONFIG_DIR/config.yaml${RESET}"
    say "    ${GREEN}(Never modified by this script)${RESET}"
    blank
    if [[ "${NEEDS_RELOGIN:-false}" == true ]]; then
        say "  ${YELLOW}⚠  Log out and back in for serial port access to take effect.${RESET}"
        blank
    fi
    say "  First run: click ${BOLD}⚙ Settings${RESET} and select your serial port."
    say "  Common ports:  /dev/ttyACM0   /dev/ttyUSB0"
    blank
}

# =============================================================================
# ACTIONS
# =============================================================================

do_install() {
    local install_dir="$1"
    local pkg_mgr
    pkg_mgr=$(detect_pkg_mgr)

    # Validate Python
    command -v "$PYTHON_BIN" &>/dev/null || die "python3 not found."
    local py_ver
    py_ver=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    local major="${py_ver%%.*}" minor="${py_ver#*.}"
    [[ "$major" -lt 3 || ( "$major" -eq 3 && "$minor" -lt 10 ) ]] \
        && die "Python 3.10+ required (found $py_ver)."

    run_dep_check

    blank
    say "  ${BOLD}Install location:${RESET}  ${CYAN}$install_dir${RESET}"
    say "  ${BOLD}Config location:${RESET}   ${CYAN}$CONFIG_DIR/config.yaml${RESET}"
    blank
    read -rp "$(echo -e "${BOLD}Proceed with installation? [Y/n]: ${RESET}")" ans
    blank
    case "${ans,,}" in
        n|no) say "${YELLOW}Installation cancelled. No changes made.${RESET}"; exit 0 ;;
    esac

    NEEDS_RELOGIN=false
    mkdir -p "$install_dir"

    step_system_packages "$pkg_mgr"
    step_venv            "$install_dir"
    step_pip             "$install_dir"
    step_copy_files      "$install_dir"
    step_launcher        "$install_dir"
    step_serial_group

    print_summary "$install_dir"
}

do_update() {
    local install_dir="$1"
    local pkg_mgr
    pkg_mgr=$(detect_pkg_mgr)

    blank
    say "  ${BOLD}Updating installation at:${RESET}"
    say "    ${CYAN}$install_dir${RESET}"
    if [[ -f "$CONFIG_DIR/config.yaml" ]]; then
        say "  ${BOLD}Config found — will not be touched:${RESET}"
        say "    ${CYAN}$CONFIG_DIR/config.yaml${RESET}"
    fi
    blank

    run_dep_check

    blank
    read -rp "$(echo -e "${BOLD}Proceed with update? [Y/n]: ${RESET}")" ans
    blank
    case "${ans,,}" in
        n|no) say "${YELLOW}Update cancelled. No changes made.${RESET}"; exit 0 ;;
    esac

    NEEDS_RELOGIN=false

    step_system_packages "$pkg_mgr"
    step_venv            "$install_dir"
    step_pip             "$install_dir"
    step_copy_files      "$install_dir"
    step_launcher        "$install_dir"
    step_serial_group

    print_summary "$install_dir"
}

do_uninstall() {
    local install_dir="$1"

    # Build the full list of locations to remove. We always clean BOTH the
    # passed-in install dir AND the default location, so no stray folders are
    # ever left behind (which previously caused false "update" detection).
    local -a remove_dirs=()
    local -a remove_files=()

    # App directories (dedupe default + custom)
    remove_dirs+=("$DEFAULT_INSTALL_DIR")
    if [[ "$install_dir" != "$DEFAULT_INSTALL_DIR" ]]; then
        remove_dirs+=("$install_dir")
    fi

    # Launcher + desktop entry
    remove_files+=("$BIN_DIR/$APP_NAME")
    remove_files+=("$DESKTOP_DIR/$APP_NAME.desktop")

    blank
    say "${BOLD}The following will be removed:${RESET}"
    for d in "${remove_dirs[@]}";  do [[ -e "$d" ]] && say "  ${CYAN}$d${RESET}"; done
    for f in "${remove_files[@]}"; do [[ -e "$f" ]] && say "  ${CYAN}$f${RESET}"; done
    blank

    local del_config="n"
    if [[ -d "$CONFIG_DIR" ]]; then
        say "  ${BOLD}Your config and profiles are at:${RESET}"
        say "  ${CYAN}$CONFIG_DIR${RESET}"
        blank
        read -rp "$(echo -e "${YELLOW}Also delete your config and saved profiles? [y/N]: ${RESET}")" del_config
        blank
    fi

    read -rp "$(echo -e "${BOLD}Proceed with uninstall? [y/N]: ${RESET}")" ans
    blank
    case "${ans,,}" in
        y|yes) ;;
        *) say "Uninstall cancelled."; exit 0 ;;
    esac

    # Remove all app directories
    for d in "${remove_dirs[@]}"; do
        if [[ -d "$d" ]]; then
            rm -rf "$d" && success "Removed: $d"
        fi
    done

    # Remove all files
    for f in "${remove_files[@]}"; do
        if [[ -e "$f" ]]; then
            rm -f "$f" && success "Removed: $f"
        fi
    done

    command -v update-desktop-database &>/dev/null \
        && update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

    # Config — only if explicitly requested
    if [[ "${del_config,,}" == "y" ]]; then
        [[ -d "$CONFIG_DIR" ]] && rm -rf "$CONFIG_DIR" && success "Removed: $CONFIG_DIR"
    else
        blank
        say "  ${GREEN}Config kept at:${RESET}"
        say "  ${CYAN}$CONFIG_DIR${RESET}"
        say "  Reinstalling will pick it back up automatically."
    fi

    blank
    say "${BOLD}${GREEN}BARJ Volume Controller has been fully uninstalled.${RESET}"
    blank
}

# =============================================================================
# SCAN + MENU
# =============================================================================

ask_for_custom_path() {
    blank
    say "  Enter the full path to your BARJ Volume Controller installation."
    say "  Example:  /home/joe/.local/share/barj-volume-controller"
    say "  (Press Tab to autocomplete the path)"
    blank
    read -rep "$(echo -e "${BOLD}Path: ${RESET}")" custom_path
    blank

    # Expand ~ if entered
    custom_path="${custom_path/#\~/$HOME}"

    if [[ -z "$custom_path" ]]; then
        say "${YELLOW}No path entered. Returning to main menu.${RESET}"
        return 1
    fi

    if is_install "$custom_path"; then
        success "Installation found at: $custom_path"
        return 0
    else
        warn "No BARJ Volume Controller installation found at: $custom_path"
        blank
        read -rp "$(echo -e "${BOLD}Install here instead? [Y/n]: ${RESET}")" ans_install_here
        case "${ans_install_here,,}" in
            n|no) say "Returning to menu."; return 1 ;;
            *)    do_install "$custom_path"; exit 0 ;;
        esac
    fi
}

main() {
    clear
    blank
    say "${BOLD}${CYAN}╔══════════════════════════════════════════╗${RESET}"
    say "${BOLD}${CYAN}║   BARJ Volume Controller — Manager       ║${RESET}"
    say "${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
    blank

    # ── Scan default location ─────────────────────────────────────────────────
    FOUND_DIR=""
    if is_install "$DEFAULT_INSTALL_DIR"; then
        FOUND_DIR="$DEFAULT_INSTALL_DIR"
    fi

    # ── Route based on whether an install was found ───────────────────────────
    if [[ -n "$FOUND_DIR" ]]; then

        say "  ${GREEN}Installation found:${RESET}"
        say "    ${CYAN}$FOUND_DIR${RESET}"
        blank
        say "  What would you like to do?"
        blank
        say "    1)  Update"
        say "    2)  Uninstall"
        say "    3)  Cancel"
        blank
        read -rp "$(echo -e "${BOLD}Enter choice [1/2/3]: ${RESET}")" choice
        blank

        case "$choice" in
            1) do_update   "$FOUND_DIR" ;;
            2) do_uninstall "$FOUND_DIR" ;;
            3) say "Cancelled."; exit 0 ;;
            *) say "${YELLOW}Invalid choice.${RESET}"; exit 1 ;;
        esac

    else

        say "  ${YELLOW}No installation found at the default location.${RESET}"
        blank
        say "  What would you like to do?"
        blank
        say "    1)  Install  (to $DEFAULT_INSTALL_DIR)"
        say "    2)  Provide a path to an existing installation"
        say "    3)  Cancel"
        blank
        read -rp "$(echo -e "${BOLD}Enter choice [1/2/3]: ${RESET}")" choice
        blank

        case "$choice" in
            1)
                do_install "$DEFAULT_INSTALL_DIR"
                ;;
            2)
                if ask_for_custom_path; then
                    # ask_for_custom_path sets custom_path if found
                    blank
                    say "  What would you like to do?"
                    blank
                    say "    1)  Update"
                    say "    2)  Uninstall"
                    say "    3)  Cancel"
                    blank
                    read -rp "$(echo -e "${BOLD}Enter choice [1/2/3]: ${RESET}")" choice2
                    blank
                    case "$choice2" in
                        1) do_update    "$custom_path" ;;
                        2) do_uninstall "$custom_path" ;;
                        3) say "Cancelled."; exit 0 ;;
                        *) say "${YELLOW}Invalid choice.${RESET}"; exit 1 ;;
                    esac
                fi
                ;;
            3)
                say "Cancelled."
                exit 0
                ;;
            *)
                say "${YELLOW}Invalid choice.${RESET}"
                exit 1
                ;;
        esac

    fi
}

main
