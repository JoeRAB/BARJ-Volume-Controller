# build_windows.ps1
# Builds barj-volume-controller.exe and barj-volume-controller-debug.exe using PyInstaller.
#
# Prerequisites: Python 3.10+ installed and on PATH.
# Usage (from the project root in PowerShell):
#   .\build_windows.ps1
#
# Output: dist\barj-volume-controller.exe  and  dist\barj-volume-controller-debug.exe

$ErrorActionPreference = "Stop"

function Write-Step { Write-Host "[BUILD] $args" -ForegroundColor Cyan   }
function Write-OK   { Write-Host "[OK]    $args" -ForegroundColor Green  }
function Write-Fail { Write-Host "[ERROR] $args" -ForegroundColor Red    }

$PROJECT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$VENV_DIR    = Join-Path $PROJECT_DIR "build_venv"
$DIST_DIR    = Join-Path $PROJECT_DIR "dist"

Write-Host ""
Write-Host "╔══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║    BARJ Volume Controller — Windows EXE Build  ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Locate Python ─────────────────────────────────────────────────────────────
Write-Step "Locating Python 3.10+…"
$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            if ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -ge 10) {
                $pythonCmd = $cmd
                Write-OK "Found: $ver"
                break
            }
        }
    } catch { }
}
if (-not $pythonCmd) {
    Write-Fail "Python 3.10+ not found. Install from https://python.org"
    exit 1
}

# ── Create / reuse a build venv ───────────────────────────────────────────────
Write-Step "Setting up build virtual environment…"
if (-not (Test-Path $VENV_DIR)) {
    & $pythonCmd -m venv $VENV_DIR
}
$pip    = Join-Path $VENV_DIR "Scripts\pip.exe"
$python = Join-Path $VENV_DIR "Scripts\python.exe"

# ── Install build dependencies ────────────────────────────────────────────────
Write-Step "Installing build dependencies (PyInstaller + app packages)…"
& $pip install --upgrade pip --quiet
& $pip install `
    pyinstaller `
    pyserial `
    pyyaml `
    "pystray>=0.19.4" `
    "Pillow>=10.0.0" `
    pycaw `
    comtypes `
    --quiet
if ($LASTEXITCODE -ne 0) { Write-Fail "pip install failed."; exit 1 }
Write-OK "Dependencies installed."

# ── Run PyInstaller ───────────────────────────────────────────────────────────
Write-Step "Running PyInstaller (this takes ~60 seconds)…"
Set-Location $PROJECT_DIR
& $python -m PyInstaller volume_mixer.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { Write-Fail "PyInstaller failed."; exit 1 }

# ── Report results ────────────────────────────────────────────────────────────
$windowed = Join-Path $DIST_DIR "barj-volume-controller.exe"
$debug_exe = Join-Path $DIST_DIR "barj-volume-controller-debug.exe"

Write-Host ""
Write-Host "╔══════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║           Build Complete!            ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

if (Test-Path $windowed) {
    $size = [math]::Round((Get-Item $windowed).Length / 1MB, 1)
    Write-OK "barj-volume-controller.exe       ($size MB)  — normal use, no console"
}
if (Test-Path $debug_exe) {
    $size = [math]::Round((Get-Item $debug_exe).Length / 1MB, 1)
    Write-OK "barj-volume-controller-debug.exe ($size MB)  — shows console, use with --debug"
}

Write-Host ""
Write-Host "  EXEs are in: $DIST_DIR" -ForegroundColor White
Write-Host "  The EXEs are standalone — copy them anywhere, no Python needed." -ForegroundColor Yellow
Write-Host ""
