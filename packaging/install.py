#!/usr/bin/env python3
"""
BARJ Volume Controller - universal bootstrap installer (any OS with Python 3).

One-line install:
  Linux/macOS:
    python3 -c "$(curl -fsSL https://raw.githubusercontent.com/JoeRAB/BARJ-Volume-Controller/main/packaging/install.py)"
  Windows (PowerShell):
    python -c "$(irm https://raw.githubusercontent.com/JoeRAB/BARJ-Volume-Controller/main/packaging/install.py)"

Downloads the latest source from GitHub and runs the matching installer
(packaging/barj.sh on Linux/macOS, packaging/barj.ps1 on Windows).
"""

import os
import sys
import ssl
import zipfile
import tempfile
import subprocess
import urllib.request

GH_OWNER = "JoeRAB"
GH_REPO = "BARJ-Volume-Controller"
GH_BRANCH = os.environ.get("BARJ_BRANCH", "main")

RELEASE_URL = f"https://github.com/{GH_OWNER}/{GH_REPO}/releases/latest/download/{GH_REPO}.zip"
BRANCH_URL = f"https://github.com/{GH_OWNER}/{GH_REPO}/archive/refs/heads/{GH_BRANCH}.zip"


def download(url, dest):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "barj-bootstrap"})
    with urllib.request.urlopen(req, context=ctx) as r, open(dest, "wb") as f:
        f.write(r.read())


def find_file(root, name, must_contain=None):
    for dirpath, _, filenames in os.walk(root):
        if name in filenames:
            full = os.path.join(dirpath, name)
            if must_contain is None or must_contain in full:
                return full
    return None


def main():
    tmp = tempfile.mkdtemp(prefix="barj_boot_")
    zip_path = os.path.join(tmp, "barj.zip")

    print("Downloading BARJ Volume Controller from GitHub...")
    try:
        download(RELEASE_URL, zip_path)
    except Exception:
        print(f"No release asset found; using latest source from '{GH_BRANCH}'.")
        download(BRANCH_URL, zip_path)

    src = os.path.join(tmp, "src")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(src)

    print("Running installer...")
    if sys.platform.startswith("win"):
        installer = find_file(src, "barj.ps1", must_contain="packaging")
        if not installer:
            sys.exit("Could not find packaging/barj.ps1 in download.")
        subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", installer, "install"],
            check=False,
        )
    else:
        installer = find_file(src, "barj.sh", must_contain="packaging")
        if not installer:
            sys.exit("Could not find packaging/barj.sh in download.")
        os.chmod(installer, 0o755)
        subprocess.run(["bash", installer, "install"], check=False)


if __name__ == "__main__":
    main()
