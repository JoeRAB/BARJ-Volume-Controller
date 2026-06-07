# =============================================================================
# BARJ Volume Controller — Windows Installer (PowerShell)
#
# What it does:
#   1. Checks Python 3.10+ is installed
#   2. Creates a Python venv at %APPDATA%\BARJVolumeController
#   3. Installs pip packages
#   4. Copies source files
#   5. Creates a launcher batch file
#   6. Creates a Start Menu shortcut
#
# Usage (run in PowerShell as a normal user — no admin required):
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # (first time only)
#   .\install_windows.ps1
# =============================================================================

$ErrorActionPreference = "Stop"

# ── Config ───────────────────────────────────────────────────────────────────
$APP_NAME    = "BARJVolumeController"
$INSTALL_DIR = Join-Path $env:APPDATA $APP_NAME
$VENV_DIR    = Join-Path $INSTALL_DIR "venv"
$SCRIPT_DIR  = Split-Path -Parent $MyInvocation.MyCommand.Path
$LAUNCHER    = Join-Path $INSTALL_DIR "barj-volume-controller.bat"
$START_MENU  = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\BARJ Volume Controller.lnk"

function Write-Step  { Write-Host "[INFO]  $args" -ForegroundColor Cyan   }
function Write-OK    { Write-Host "[OK]    $args" -ForegroundColor Green  }
function Write-Warn  { Write-Host "[WARN]  $args" -ForegroundColor Yellow }
function Write-Fail  { Write-Host "[ERROR] $args" -ForegroundColor Red    }

# ── Banner ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║    BARJ Volume Controller — Windows Install    ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── 1. Locate Python ─────────────────────────────────────────────────────────
Write-Step "Locating Python 3.10+…"

$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -eq 3 -and $minor -ge 10) {
                $pythonCmd = $cmd
                Write-OK "Found: $ver (using '$cmd')"
                break
            }
        }
    } catch { }
}

if (-not $pythonCmd) {
    Write-Fail "Python 3.10+ not found."
    Write-Host "  Download from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  Make sure to check 'Add Python to PATH' during install." -ForegroundColor Yellow
    exit 1
}

# ── 2. Create install directory ───────────────────────────────────────────────
Write-Step "Creating install directory: $INSTALL_DIR"
if (Test-Path $INSTALL_DIR) {
    Write-Warn "Install directory already exists — updating in place."
}
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
Write-OK "Directory ready."

# ── 3. Create venv ───────────────────────────────────────────────────────────
Write-Step "Creating Python virtual environment…"
if (Test-Path $VENV_DIR) {
    Write-Warn "Existing venv found — removing and recreating."
    Remove-Item -Recurse -Force $VENV_DIR
}
& $pythonCmd -m venv $VENV_DIR
if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to create venv."; exit 1 }
Write-OK "Venv created."

$pip    = Join-Path $VENV_DIR "Scripts\pip.exe"
$python = Join-Path $VENV_DIR "Scripts\python.exe"

# ── 4. Install packages ───────────────────────────────────────────────────────
Write-Step "Installing Python packages…"
& $pip install --upgrade pip --quiet
& $pip install pyserial pyyaml "pystray>=0.19.4" "Pillow>=10.0.0" pycaw comtypes --quiet
if ($LASTEXITCODE -ne 0) { Write-Fail "pip install failed."; exit 1 }
Write-OK "Python packages installed."

# ── 5. Copy source files ──────────────────────────────────────────────────────
Write-Step "Copying source files…"
$copyItems = @("main.py","serial_reader.py","config_manager.py","app_detector.py","tray_icon.py","audio","gui","arduino")
foreach ($item in $copyItems) {
    $src = Join-Path $SCRIPT_DIR $item
    if (Test-Path $src) {
        Copy-Item -Recurse -Force $src $INSTALL_DIR
    } else {
        Write-Warn "Not found, skipping: $item"
    }
}
Write-OK "Source files copied."

# ── 6. Create launcher .bat ───────────────────────────────────────────────────
Write-Step "Creating launcher…"
$batContent = @"
@echo off
REM BARJ Volume Controller launcher
REM Pass --debug to print raw serial values to this console window.
"$python" "$INSTALL_DIR\main.py" %*
"@
Set-Content -Path $LAUNCHER -Value $batContent -Encoding ASCII
Write-OK "Launcher created: $LAUNCHER"

# ── 7. Create Start Menu shortcut ────────────────────────────────────────────
Write-Step "Creating Start Menu shortcut…"
try {
    $wsh     = New-Object -ComObject WScript.Shell
    $link    = $wsh.CreateShortcut($START_MENU)
    $link.TargetPath       = $LAUNCHER
    $link.WorkingDirectory = $INSTALL_DIR
    $link.Description      = "Hardware BARJ Volume Controller"
    $link.IconLocation     = "shell32.dll,168"   # speaker icon
    $link.Save()
    Write-OK "Start Menu shortcut created."
} catch {
    Write-Warn "Could not create Start Menu shortcut: $_"
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║        Installation Complete!        ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Run from Start Menu: 'BARJ Volume Controller'"  -ForegroundColor White
Write-Host "  Or double-click:     $LAUNCHER"       -ForegroundColor White
Write-Host "  Debug mode:          barj-volume-controller.bat --debug"  -ForegroundColor White
Write-Host ""
Write-Host "  First time? Open Settings (⚙) and set your COM port (e.g. COM3)." -ForegroundColor Yellow
Write-Host ""
