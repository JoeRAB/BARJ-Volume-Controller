#!/usr/bin/env bash
# =============================================================================
# BARJ Volume Controller — Linux Uninstaller
#
# Removes:
#   ~/.local/share/barj-volume-controller   (app files + venv)
#   ~/.local/bin/barj-volume-controller     (launcher)
#   ~/.local/share/applications/barj-volume-controller.desktop
#
# Optionally removes:
#   ~/.config/barj-volume-controller        (your config and profiles)
#
# Does NOT remove:
#   System packages installed by the installer (python3-tk, etc.)
#   Your dialout/uucp group membership
#
# Usage:
#   chmod +x uninstall_linux.sh && ./uninstall_linux.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
removed() { echo -e "    ${GREEN}✓${RESET} removed: $*"; }
skipped() { echo -e "    ${YELLOW}⊘${RESET} not found: $*"; }

APP_NAME="barj-volume-controller"
INSTALL_DIR="$HOME/.local/share/$APP_NAME"
BIN_FILE="$HOME/.local/bin/$APP_NAME"
DESKTOP_FILE="$HOME/.local/share/applications/$APP_NAME.desktop"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/$APP_NAME"

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║  BARJ Volume Controller — Uninstaller   ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
echo ""

# ---- Config warning ----
if [[ -d "$CONFIG_DIR" ]]; then
    echo -e "${BOLD}Your config and profiles are stored at:${RESET}"
    echo -e "  ${CYAN}$CONFIG_DIR${RESET}"
    echo ""
    read -rp "$(echo -e "${YELLOW}Delete your config and saved profiles too? [y/N]:${RESET} ")" del_config
    echo ""
else
    del_config="n"
fi

# ---- Confirm ----
echo -e "${BOLD}The following will be removed:${RESET}"
echo -e "  $INSTALL_DIR"
echo -e "  $BIN_FILE"
echo -e "  $DESKTOP_FILE"
[[ "${del_config,,}" == "y" ]] && echo -e "  $CONFIG_DIR  ${RED}(including your profiles!)${RESET}"
echo ""
read -rp "$(echo -e "${YELLOW}Proceed with uninstall? [y/N]:${RESET} ")" confirm
echo ""

if [[ "${confirm,,}" != "y" ]]; then
    echo "Uninstall cancelled."
    exit 0
fi

# ---- Remove app files ----
info "Removing application files…"

if [[ -d "$INSTALL_DIR" ]]; then
    rm -rf "$INSTALL_DIR"
    removed "$INSTALL_DIR"
else
    skipped "$INSTALL_DIR"
fi

if [[ -f "$BIN_FILE" ]]; then
    rm -f "$BIN_FILE"
    removed "$BIN_FILE"
else
    skipped "$BIN_FILE"
fi

if [[ -f "$DESKTOP_FILE" ]]; then
    rm -f "$DESKTOP_FILE"
    removed "$DESKTOP_FILE"
    command -v update-desktop-database &>/dev/null \
        && update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
else
    skipped "$DESKTOP_FILE"
fi

# ---- Remove config (optional) ----
if [[ "${del_config,,}" == "y" ]]; then
    if [[ -d "$CONFIG_DIR" ]]; then
        rm -rf "$CONFIG_DIR"
        removed "$CONFIG_DIR"
    else
        skipped "$CONFIG_DIR"
    fi
else
    info "Config kept at: $CONFIG_DIR"
    info "Delete manually if needed: rm -rf \"$CONFIG_DIR\""
fi

# ---- Done ----
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║         Uninstall Complete               ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  BARJ Volume Controller has been removed."
if [[ "${del_config,,}" != "y" ]]; then
    echo -e "  Your profiles are still saved at:"
    echo -e "  ${CYAN}$CONFIG_DIR${RESET}"
    echo -e "  Reinstalling will pick them back up automatically."
fi
echo ""
