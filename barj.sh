#!/usr/bin/env bash
#
# BARJ Volume Controller - management script (Linux & macOS)
#
# Commands:
#   ./barj.sh install     Check deps, optionally install them, install the app
#   ./barj.sh uninstall   Remove app files (asks whether to keep config)
#   ./barj.sh update       Download & install latest, keep config
#
# Dependency check prints each requirement as:
#   name - Installed     or     name - Missing
# then asks whether to install the missing ones.
#
set -u

APP_NAME="BARJ Volume Controller"
PKG="barj_volume_controller"
INSTALL_DIR="${HOME}/.local/share/BARJ"
BIN_DIR="${HOME}/.local/bin"
BIN_PATH="${BIN_DIR}/barj"
VENV_DIR="${INSTALL_DIR}/venv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Where to fetch updates from. Adjust to your fork/release URL.
REPO_ZIP_URL="${BARJ_REPO_ZIP_URL:-https://example.com/barj/latest.zip}"

OS="$(uname -s)"

# ---- config dir (matches config.py) ----
if [ "${OS}" = "Darwin" ]; then
  CONFIG_DIR="${HOME}/Library/Application Support/BARJ"
else
  CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/BARJ"
fi

color() { printf "\033[%sm%s\033[0m" "$1" "$2"; }
ok()    { color "0;32" "Installed"; }
miss()  { color "0;31" "Missing"; }

confirm() {
  # $1 = prompt ; returns 0 for yes
  local reply
  read -r -p "$1 [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

# -------------------------------------------------------- dependency check
check_python() { command -v python3 >/dev/null 2>&1; }

check_deps() {
  echo "Checking dependencies for ${APP_NAME}..."
  echo

  MISSING_SYS=()

  # Python 3
  if check_python; then echo "python3 - $(ok)"; else echo "python3 - $(miss)"; MISSING_SYS+=("python3"); fi

  # pip / venv
  if python3 -m venv --help >/dev/null 2>&1; then echo "python3-venv - $(ok)"; else echo "python3-venv - $(miss)"; MISSING_SYS+=("python3-venv"); fi
  if python3 -m pip --version >/dev/null 2>&1; then echo "python3-pip - $(ok)"; else echo "python3-pip - $(miss)"; MISSING_SYS+=("python3-pip"); fi

  if [ "${OS}" = "Linux" ]; then
    # PulseAudio/PipeWire client lib used by pulsectl
    if command -v pactl >/dev/null 2>&1; then echo "pulseaudio/pipewire (pactl) - $(ok)"; else echo "pulseaudio/pipewire (pactl) - $(miss)"; MISSING_SYS+=("pulseaudio-utils"); fi
    # Tk runtime for the GUI
    if python3 -c "import tkinter" >/dev/null 2>&1; then echo "python3-tk - $(ok)"; else echo "python3-tk - $(miss)"; MISSING_SYS+=("python3-tk"); fi
  fi

  echo
  if [ ${#MISSING_SYS[@]} -gt 0 ]; then
    echo "Missing system packages: ${MISSING_SYS[*]}"
    if confirm "Install missing system dependencies now?"; then
      install_sys_deps "${MISSING_SYS[@]}"
    else
      echo "Skipping system dependency installation. The app may not run correctly."
    fi
  else
    echo "All system dependencies satisfied."
  fi
}

install_sys_deps() {
  local pkgs=("$@")
  if [ "${OS}" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then
      # macOS: python via brew covers python3/venv/pip/tk
      brew install python-tk@3.12 || brew install python
    else
      echo "Homebrew not found. Install it from https://brew.sh then re-run."
    fi
    return
  fi
  # Linux: detect package manager
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update && sudo apt-get install -y "${pkgs[@]}"
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip python3-virtualenv python3-tkinter pulseaudio-utils
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --needed --noconfirm python python-pip tk libpulse
  elif command -v zypper >/dev/null 2>&1; then
    sudo zypper install -y python3 python3-pip python3-tk pulseaudio-utils
  else
    echo "Could not detect a supported package manager. Install manually: ${pkgs[*]}"
  fi
}

# -------------------------------------------------------- install
do_install() {
  check_deps
  echo
  echo "Installing ${APP_NAME} to ${INSTALL_DIR}..."
  mkdir -p "${INSTALL_DIR}" "${BIN_DIR}"

  # Copy package + requirements into install dir
  cp -r "${SCRIPT_DIR}/${PKG}" "${INSTALL_DIR}/"
  cp "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"

  # Create venv and install python deps
  python3 -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/pip" install --upgrade pip >/dev/null
  echo "Installing Python packages (this may take a minute)..."
  "${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

  # Launcher
  cat > "${BIN_PATH}" <<EOF
#!/usr/bin/env bash
exec "${VENV_DIR}/bin/python" -m ${PKG} "\$@"
EOF
  chmod +x "${BIN_PATH}"

  # Desktop entry (Linux)
  if [ "${OS}" = "Linux" ]; then
    local apps_dir="${HOME}/.local/share/applications"
    mkdir -p "${apps_dir}"
    cat > "${apps_dir}/barj.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=${APP_NAME}
Exec=${BIN_PATH}
Terminal=false
Categories=AudioVideo;Audio;
EOF
  fi

  echo
  echo "Done. Launch with: barj"
  case ":$PATH:" in
    *":${BIN_DIR}:"*) ;;
    *) echo "Note: add ${BIN_DIR} to your PATH to run 'barj' directly." ;;
  esac
}

# -------------------------------------------------------- uninstall
do_uninstall() {
  echo "Uninstalling ${APP_NAME}..."
  local keep_config=1
  if [ -d "${CONFIG_DIR}" ]; then
    if confirm "Delete the configuration folder too (${CONFIG_DIR})?"; then
      keep_config=0
    fi
  fi

  rm -rf "${INSTALL_DIR}"
  rm -f  "${BIN_PATH}"
  rm -f  "${HOME}/.local/share/applications/barj.desktop"
  # autostart entries
  rm -f  "${XDG_CONFIG_HOME:-${HOME}/.config}/autostart/barj.desktop"
  rm -f  "${HOME}/Library/LaunchAgents/com.barj.volumecontroller.plist" 2>/dev/null

  if [ "${keep_config}" -eq 0 ]; then
    rm -rf "${CONFIG_DIR}"
    echo "Removed app files and configuration."
  else
    echo "Removed app files. Configuration kept at: ${CONFIG_DIR}"
  fi
}

# -------------------------------------------------------- update
do_update() {
  echo "Updating ${APP_NAME} (configuration will be preserved)..."
  local tmp; tmp="$(mktemp -d)"
  echo "Downloading latest from ${REPO_ZIP_URL}..."
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "${REPO_ZIP_URL}" -o "${tmp}/barj.zip" || { echo "Download failed."; rm -rf "${tmp}"; exit 1; }
  else
    wget -q "${REPO_ZIP_URL}" -O "${tmp}/barj.zip" || { echo "Download failed."; rm -rf "${tmp}"; exit 1; }
  fi
  unzip -q "${tmp}/barj.zip" -d "${tmp}/extracted"
  local src; src="$(find "${tmp}/extracted" -name "${PKG}" -type d | head -n1)"
  if [ -z "${src}" ]; then echo "Could not find package in download."; rm -rf "${tmp}"; exit 1; fi

  # Replace package, keep venv + config
  rm -rf "${INSTALL_DIR}/${PKG}"
  cp -r "${src}" "${INSTALL_DIR}/"
  local req; req="$(dirname "${src}")/requirements.txt"
  [ -f "${req}" ] && cp "${req}" "${INSTALL_DIR}/" && "${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt" --upgrade

  rm -rf "${tmp}"
  echo "Update complete. Config at ${CONFIG_DIR} was untouched."
}

usage() {
  echo "Usage: $0 {install|uninstall|update|check}"
}

case "${1:-}" in
  install)   do_install ;;
  uninstall) do_uninstall ;;
  update)    do_update ;;
  check)     check_deps ;;
  *)         usage; exit 1 ;;
esac
