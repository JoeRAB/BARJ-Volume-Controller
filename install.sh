#!/usr/bin/env bash
#
# BARJ Volume Controller - GitHub bootstrap installer (Linux & macOS)
#
# One-line install:
#   curl -fsSL https://raw.githubusercontent.com/JoeRAB/BARJ-Volume-Controller/main/packaging/install.sh | bash
#
# Downloads the latest source from GitHub and runs the full installer
# (packaging/barj.sh install), which checks dependencies and sets up the app.
#
set -euo pipefail

GH_OWNER="JoeRAB"
GH_REPO="BARJ-Volume-Controller"
GH_BRANCH="${BARJ_BRANCH:-main}"

# Prefer the latest published release; fall back to the branch archive.
RELEASE_URL="https://github.com/${GH_OWNER}/${GH_REPO}/releases/latest/download/${GH_REPO}.zip"
BRANCH_URL="https://github.com/${GH_OWNER}/${GH_REPO}/archive/refs/heads/${GH_BRANCH}.zip"

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

fetch() {
  # $1 url, $2 dest ; returns 0 on success
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$1" -o "$2"
  elif command -v wget >/dev/null 2>&1; then
    wget -q "$1" -O "$2"
  else
    echo "Need curl or wget to download." >&2; return 1
  fi
}

echo "Downloading BARJ Volume Controller from GitHub..."
if ! fetch "${RELEASE_URL}" "${TMP}/barj.zip" 2>/dev/null; then
  echo "No release asset found; using latest source from '${GH_BRANCH}'."
  fetch "${BRANCH_URL}" "${TMP}/barj.zip"
fi

unzip -q "${TMP}/barj.zip" -d "${TMP}/src"

# Locate the directory that contains packaging/barj.sh
INSTALLER="$(find "${TMP}/src" -path '*/packaging/barj.sh' | head -n1)"
if [ -z "${INSTALLER}" ]; then
  echo "Could not find packaging/barj.sh in the download." >&2
  exit 1
fi

chmod +x "${INSTALLER}"
echo "Running installer..."
bash "${INSTALLER}" install
