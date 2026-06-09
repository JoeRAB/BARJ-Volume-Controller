<#
  BARJ Volume Controller - management script (Windows)

  Usage (from PowerShell):
    .\barj.ps1 install     # check deps, optionally install, install the app
    .\barj.ps1 uninstall   # remove app files (asks whether to keep config)
    .\barj.ps1 update      # download & install latest, keep config
    .\barj.ps1 check       # dependency check only

  Dependency check prints each requirement as "name - Installed/Missing",
  then asks whether to install the missing ones.
#>

param(
  [Parameter(Position = 0)]
  [ValidateSet("install", "uninstall", "update", "check")]
  [string]$Command = "install"
)

$AppName     = "BARJ Volume Controller"
$Pkg         = "barj_volume_controller"
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallDir  = Join-Path $env:LOCALAPPDATA "BARJ"
$VenvDir     = Join-Path $InstallDir "venv"
$ConfigDir   = Join-Path $env:APPDATA  "BARJ"
$StartMenu   = Join-Path $env:APPDATA  "Microsoft\Windows\Start Menu\Programs"
$GhOwner     = "JoeRAB"
$GhRepo      = "BARJ-Volume-Controller"
$GhBranch    = if ($env:BARJ_BRANCH) { $env:BARJ_BRANCH } else { "main" }
$RepoZipUrl  = if ($env:BARJ_REPO_ZIP_URL) { $env:BARJ_REPO_ZIP_URL } else { "https://github.com/$GhOwner/$GhRepo/archive/refs/heads/$GhBranch.zip" }

function Write-Status($name, $present) {
  if ($present) { Write-Host "$name - " -NoNewline; Write-Host "Installed" -ForegroundColor Green }
  else          { Write-Host "$name - " -NoNewline; Write-Host "Missing"   -ForegroundColor Red }
}

function Confirm-YesNo($prompt) {
  $r = Read-Host "$prompt [y/N]"
  return ($r -match '^[Yy]$')
}

function Test-Cmd($name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Check-Deps {
  Write-Host "Checking dependencies for $AppName...`n"
  $missing = @()

  $hasPy = (Test-Cmd "python") -or (Test-Cmd "py")
  Write-Status "Python 3" $hasPy
  if (-not $hasPy) { $missing += "python" }

  $hasPip = $false
  if ($hasPy) {
    $pyExe = if (Test-Cmd "py") { "py" } else { "python" }
    & $pyExe -m pip --version *> $null
    $hasPip = ($LASTEXITCODE -eq 0)
  }
  Write-Status "pip" $hasPip
  if (-not $hasPip) { $missing += "pip" }

  # tkinter ships with the python.org installer; flag if absent
  $hasTk = $false
  if ($hasPy) {
    $pyExe = if (Test-Cmd "py") { "py" } else { "python" }
    & $pyExe -c "import tkinter" *> $null
    $hasTk = ($LASTEXITCODE -eq 0)
  }
  Write-Status "tkinter (Tcl/Tk)" $hasTk
  if (-not $hasTk) { $missing += "tkinter" }

  Write-Host ""
  if ($missing.Count -gt 0) {
    Write-Host ("Missing: " + ($missing -join ", "))
    if (Confirm-YesNo "Install missing dependencies now?") {
      Install-SysDeps
    } else {
      Write-Host "Skipping. The app may not run correctly."
    }
  } else {
    Write-Host "All system dependencies satisfied."
  }
}

function Install-SysDeps {
  if (Test-Cmd "winget") {
    Write-Host "Installing Python via winget (includes pip + tkinter)..."
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    Write-Host "If 'python' isn't found, close and reopen PowerShell, then re-run."
  } else {
    Write-Host "winget not available. Install Python 3 from https://python.org/downloads (check 'Add to PATH' and 'tcl/tk')."
  }
}

function Get-PyExe {
  if (Test-Cmd "py") { return "py" } elseif (Test-Cmd "python") { return "python" } else { return $null }
}

function Do-Install {
  Check-Deps
  Write-Host "`nInstalling $AppName to $InstallDir..."
  $py = Get-PyExe
  if (-not $py) { Write-Host "Python not found. Aborting." -ForegroundColor Red; return }

  New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
  Copy-Item (Join-Path $ScriptDir $Pkg) -Destination $InstallDir -Recurse -Force
  Copy-Item (Join-Path $ScriptDir "requirements.txt") -Destination $InstallDir -Force

  & $py -m venv $VenvDir
  $venvPy = Join-Path $VenvDir "Scripts\python.exe"
  & $venvPy -m pip install --upgrade pip | Out-Null
  Write-Host "Installing Python packages (this may take a minute)..."
  & $venvPy -m pip install -r (Join-Path $InstallDir "requirements.txt")

  # Launcher .cmd
  $launcher = Join-Path $InstallDir "barj.cmd"
  "@echo off`r`nstart """" ""$venvPy"" -m $Pkg %*" | Set-Content -Encoding ASCII $launcher

  # pythonw launcher (no console) for shortcuts
  $venvPyw = Join-Path $VenvDir "Scripts\pythonw.exe"

  # Start Menu shortcut
  $ws = New-Object -ComObject WScript.Shell
  $lnk = $ws.CreateShortcut((Join-Path $StartMenu "BARJ Volume Controller.lnk"))
  $lnk.TargetPath = $venvPyw
  $lnk.Arguments  = "-m $Pkg"
  $lnk.WorkingDirectory = $InstallDir
  $lnk.Save()

  Write-Host "`nDone. Launch from the Start Menu (BARJ Volume Controller) or run:"
  Write-Host "  $launcher"
}

function Do-Uninstall {
  Write-Host "Uninstalling $AppName..."
  $keepConfig = $true
  if (Test-Path $ConfigDir) {
    if (Confirm-YesNo "Delete the configuration folder too ($ConfigDir)?") {
      $keepConfig = $false
    }
  }

  if (Test-Path $InstallDir) { Remove-Item $InstallDir -Recurse -Force }
  $sc = Join-Path $StartMenu "BARJ Volume Controller.lnk"
  if (Test-Path $sc) { Remove-Item $sc -Force }

  # autostart registry entry
  $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
  if (Get-ItemProperty -Path $runKey -Name "BARJ" -ErrorAction SilentlyContinue) {
    Remove-ItemProperty -Path $runKey -Name "BARJ"
  }

  if (-not $keepConfig) {
    if (Test-Path $ConfigDir) { Remove-Item $ConfigDir -Recurse -Force }
    Write-Host "Removed app files and configuration."
  } else {
    Write-Host "Removed app files. Configuration kept at: $ConfigDir"
  }
}

function Do-Update {
  Write-Host "Updating $AppName (configuration will be preserved)..."
  $tmp = Join-Path $env:TEMP ("barj_" + [System.Guid]::NewGuid().ToString())
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  $zip = Join-Path $tmp "barj.zip"
  try {
    Invoke-WebRequest -Uri $RepoZipUrl -OutFile $zip -UseBasicParsing
  } catch {
    Write-Host "Download failed: $_" -ForegroundColor Red; Remove-Item $tmp -Recurse -Force; return
  }
  Expand-Archive -Path $zip -DestinationPath (Join-Path $tmp "extracted") -Force
  $src = Get-ChildItem -Path (Join-Path $tmp "extracted") -Recurse -Directory -Filter $Pkg | Select-Object -First 1
  if (-not $src) { Write-Host "Package not found in download." -ForegroundColor Red; Remove-Item $tmp -Recurse -Force; return }

  Remove-Item (Join-Path $InstallDir $Pkg) -Recurse -Force -ErrorAction SilentlyContinue
  Copy-Item $src.FullName -Destination $InstallDir -Recurse -Force
  $req = Join-Path $src.Parent.FullName "requirements.txt"
  if (Test-Path $req) {
    Copy-Item $req -Destination $InstallDir -Force
    & (Join-Path $VenvDir "Scripts\python.exe") -m pip install -r (Join-Path $InstallDir "requirements.txt") --upgrade
  }
  Remove-Item $tmp -Recurse -Force
  Write-Host "Update complete. Config at $ConfigDir was untouched."
}

switch ($Command) {
  "install"   { Do-Install }
  "uninstall" { Do-Uninstall }
  "update"    { Do-Update }
  "check"     { Check-Deps }
}
