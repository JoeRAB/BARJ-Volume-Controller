# volume_mixer.spec
# PyInstaller spec file for Volume Mixer
#
# Builds two EXEs:
#   dist\barj-volume-controller.exe        — windowed (no console), for normal use
#   dist\barj-volume-controller-debug.exe  — console window, for --debug mode
#
# Build with:  pyinstaller volume_mixer.spec

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Hidden imports that PyInstaller misses via static analysis
HIDDEN_IMPORTS = [
    # pycaw / Windows Core Audio
    "pycaw.pycaw",
    "pycaw.utils",
    "comtypes",
    "comtypes.client",
    "comtypes.server",
    "comtypes.server.factory",
    "comtypes.typeinfo",
    "comtypes._cominterface_meta",
    # pystray Windows backend
    "pystray._win32",
    # Pillow image formats used by pystray icon
    "PIL._tkinter_finder",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.PngImagePlugin",
    # tkinter
    "tkinter",
    "tkinter.ttk",
    "tkinter.messagebox",
    "tkinter.simpledialog",
    # stdlib
    "queue",
    "threading",
    "logging.handlers",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Linux-only — not needed in Windows build
        "pulsectl",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Target 1: Windowed EXE (normal use, no console window) ───────────────────
exe_windowed = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="barj-volume-controller",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # No console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # Replace with "icon.ico" if you have one
    version=None,
)

# ── Target 2: Debug EXE (console visible, --debug flag works normally) ────────
exe_debug = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="barj-volume-controller-debug",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,           # Console window visible — debug prints work
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
